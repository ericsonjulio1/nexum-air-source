"""Worker-facing billing helpers (XENDIT-SPEC section 3).

The host billing worker (saas/billing-worker.py) drives everything through
``bench execute`` calls into this module — the same host/site split the
provisioning pipeline uses. Each function prints ONE JSON document on stdout
(bench execute's return-value repr is not machine-stable across frappe
versions, so we print explicitly and the worker parses the last JSON line).

Nothing here touches tenants.tsv, mail, or maintenance mode — those stay
host-side in the worker, next to the scripts that already own them.
"""

import json

import frappe
from frappe.utils import now_datetime


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, default=str))


def get_pending(limit=20):
    """Unprocessed, pipeline-known Billing Events, oldest first."""
    rows = frappe.get_all(
        "Billing Event",
        filters={"processed": 0},
        fields=["name", "event_id", "event_type", "reference_id", "subdomain",
                "payload", "creation"],
        order_by="creation asc",
        limit=int(limit),
    )
    _emit({"ok": True, "events": rows})


def mark_processed(name, error=None, subdomain=None):
    """Stamp one Billing Event as handled (or failed, with the error kept for
    the audit trail — a failed event stays processed=0 only when ``error`` is
    passed as retryable='1' semantics are NOT wanted; the worker decides)."""
    if not frappe.db.exists("Billing Event", name):
        _emit({"ok": False, "error": "no such Billing Event: %s" % name})
        return
    values = {"processed": 1, "processed_on": now_datetime()}
    if error:
        values["processing_error"] = str(error)[:500]
    if subdomain:
        values["subdomain"] = str(subdomain)[:140]
    frappe.db.set_value("Billing Event", name, values, update_modified=False)
    frappe.db.commit()
    _emit({"ok": True})


def upsert_subscription(subdomain, plan=None, status=None, paid_until=None,
                        xendit_customer_id=None, xendit_plan_id=None,
                        payment_method_type=None, last_event=None):
    """Create-or-update the hq mirror row for one tenant's subscription. The
    worker calls this after acting; Xendit stays the money source of truth."""
    fields = {k: v for k, v in {
        "plan": plan, "status": status, "paid_until": paid_until,
        "xendit_customer_id": xendit_customer_id,
        "xendit_plan_id": xendit_plan_id,
        "payment_method_type": payment_method_type,
        "last_event": last_event,
    }.items() if v is not None}
    if frappe.db.exists("Nexum Subscription", subdomain):
        if fields:
            frappe.db.set_value("Nexum Subscription", subdomain, fields)
    else:
        doc = frappe.get_doc(dict(fields, doctype="Nexum Subscription",
                                  subdomain=subdomain))
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    _emit({"ok": True, "subdomain": subdomain})


def find_subdomain_for_plan(xendit_plan_id):
    """Map a Xendit recurring plan id back to the tenant it bills — set when
    xendit-setup/checkout created the plan with reference_id=subdomain and
    mirrored here. Falls back to empty (worker alerts on unmapped events)."""
    sub = frappe.db.get_value("Nexum Subscription",
                              {"xendit_plan_id": xendit_plan_id}, "subdomain")
    _emit({"ok": True, "subdomain": sub or ""})
