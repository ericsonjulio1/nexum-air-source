"""Own the database boundary between a reusable tenant name and billing identity.

Checkout holds the subscription row lock through provider session persistence.
Deletion closes that same row before enumerating plans. Worker mutations compare
generation under the row lock, so an old event cannot overwrite a new checkout.
"""
import json
import re
from pathlib import Path

import frappe
from frappe.utils import get_bench_path

from my_branding.tenant_identity import read_generation, UnboundGeneration, valid_generation

MIRROR_FIELDS = ("plan", "status", "paid_until", "last_paid_event", "last_event_at",
                 "last_event", "pending_plan", "pending_plan_id", "xendit_plan_id",
                 "xendit_customer_id", "payment_method_type", "checkout_session_id",
                 "checkout_url", "checkout_expires_on")
WORKER_FIELDS = ("status", "paid_until", "last_paid_event", "last_event_at", "last_event", "payment_method_type")


def _site(subdomain):
    if not isinstance(subdomain, str) or not re.fullmatch(r"[a-z0-9-]+", subdomain):
        raise frappe.ValidationError("Invalid tenant subdomain")
    return subdomain + ".nexumair.com"


def _generation(subdomain):
    return read_generation(Path(get_bench_path()) / "sites", _site(subdomain), require_ready=True)


def _worker_permission(permission):
    if not frappe.conf.get("is_signup_host"):
        raise frappe.PermissionError("Billing administration is only available on HQ")
    frappe.has_permission("Nexum Subscription", permission, throw=True)


def _current_rows(query, values):
    # MariaDB's snapshot-isolation option otherwise aborts a locking read after
    # waiting for a concurrent writer. Scope the override to this statement;
    # do not weaken the request's other reads or leave pooled-session state.
    return frappe.db.sql("SET STATEMENT innodb_snapshot_isolation=OFF FOR " + query,
                         values, as_dict=True)


def _set_locked(doctype, name, fields):
    """Validate and audit an already-locked row without an older snapshot.

    These two owned DocTypes have no document-event lifecycle handlers. Keep
    their validation and Version history while using the current-write SQL
    required after a concurrent lock wait on MariaDB snapshot isolation.
    """
    allowed = {
        "Nexum Subscription": {*MIRROR_FIELDS, "tenant_generation", "billing_closed", "previous_generations"},
        "Billing Checkout Attempt": {"state", "needs_deactivation", "superseded_by"},
    }
    if doctype not in allowed or set(fields) - allowed[doctype]:
        raise ValueError("Unsupported locked billing update")
    row = _current_rows("select * from `tab" + doctype + "` where name=%s for update", (name,))[0]
    before = frappe.get_doc(dict(row, doctype=doctype))
    doc = frappe.get_doc(dict(row, doctype=doctype))
    doc._doc_before_save = before
    doc.update(fields)
    doc._validate()
    for key, value in fields.items():
        field = doc.meta.get_field(key)
        if value and field.fieldtype in ("Date", "Datetime"):
            try:
                doc.set(key, frappe.utils.getdate(value) if field.fieldtype == "Date"
                        else frappe.utils.get_datetime(value))
            except (ValueError, TypeError) as exc:
                raise frappe.ValidationError("Invalid billing date: " + key) from exc
    fields = {key: doc.get(key) for key in fields}
    fields = dict(fields, modified=frappe.utils.now_datetime(), modified_by=frappe.session.user)
    assignments = ", ".join("`" + field + "`=%s" for field in fields)
    _current_rows("UPDATE `tab" + doctype + "` SET " + assignments + " WHERE name=%s",
                  (*fields.values(), name))
    frappe.db.value_cache.clear()
    frappe.clear_document_cache(doctype, name)
    doc.update(fields)
    doc.save_version()


def _locked_subscription(subdomain, generation=None):
    _site(subdomain)
    if generation and not frappe.db.exists("Nexum Subscription", subdomain):
        frappe.get_doc(dict(doctype="Nexum Subscription", subdomain=subdomain,
                            tenant_generation=generation, status="Pending")).insert(ignore_permissions=True)
    # Locking reads see the latest committed version even under REPEATABLE READ.
    rows = _current_rows("select * from `tabNexum Subscription` where name=%s for update", (subdomain,))
    return rows[0] if rows else None


def _retire_plans(row):
    """Record cleanup before resetting a mirror; preserve each plan's ownership."""
    generation = row.tenant_generation
    for plan_id in {row.get("xendit_plan_id"), row.get("pending_plan_id")} - {None, ""}:
        found = _current_rows("select name from `tabBilling Checkout Attempt` where name=%s for update", (plan_id,))
        if not found:
            frappe.get_doc(dict(doctype="Billing Checkout Attempt", plan_id=plan_id,
                                subdomain=row.name, tenant_generation=generation,
                                state="Superseded", needs_deactivation=1)).insert(ignore_permissions=True)
    for attempt in _current_rows("select name,state from `tabBilling Checkout Attempt` "
                                  "where subdomain=%s and tenant_generation=%s for update", (row.name, generation)):
        if attempt.name == row.get("xendit_plan_id") and row.get("status") == "Inactive":
            _set_locked("Billing Checkout Attempt", attempt.name,
                                {"state": "Inactive", "needs_deactivation": 0})
            continue
        if attempt.state != "Inactive":
            _set_locked("Billing Checkout Attempt", attempt.name,
                                {"state": "Superseded", "needs_deactivation": 1})


def prepare_checkout(subdomain, *, allow_closed=False):
    """Internal guest-checkout operation; caller commits before releasing its lock."""
    try:
        generation = _generation(subdomain)
    except UnboundGeneration as exc:
        raise frappe.ValidationError(str(exc)) from exc
    if not generation:
        raise frappe.ValidationError("Tenant is not available for checkout")
    row = _locked_subscription(subdomain, generation)
    # Site removal/replacement could occur while the row lock was being acquired.
    if _generation(subdomain) != generation:
        raise frappe.ValidationError("Tenant changed while opening checkout; try again")
    previous = row.get("tenant_generation")
    if previous != generation:
        if not valid_generation(previous) and any(row.get(key) for key in
                ("xendit_plan_id", "pending_plan_id", "xendit_customer_id", "paid_until")):
            raise frappe.ValidationError("Legacy billing ownership needs support reconciliation")
        history = json.loads(row.get("previous_generations") or "[]")
        if not isinstance(history, list):
            raise frappe.ValidationError("Billing history needs support reconciliation")
        if previous:
            history.append({key: str(row[key]) if row.get(key) is not None else None
                            for key in (*MIRROR_FIELDS, "tenant_generation")})
            _retire_plans(row)
        cleared = {key: None for key in MIRROR_FIELDS}
        cleared.update(status="Pending", tenant_generation=generation, billing_closed=0,
                       previous_generations=json.dumps(history))
        _set_locked("Nexum Subscription", subdomain, cleared)
        row.update(cleared)
    if row.get("billing_closed") and not allow_closed:
        raise frappe.ValidationError("Tenant billing is closing; contact support")
    return row


def save_pending_checkout(subdomain, generation, fields):
    """Persist a provider response inside the transaction opened by prepare_checkout."""
    row = _locked_subscription(subdomain)
    if (not row or row.get("tenant_generation") != generation or row.get("billing_closed")
            or fields.get("tenant_generation") != generation):
        raise frappe.ValidationError("Checkout ownership changed; reconciliation required")
    _set_locked("Nexum Subscription", subdomain, fields)


@frappe.whitelist(methods=["POST"])
def tenant_context(subdomain):
    _worker_permission("read")
    try:
        generation = _generation(subdomain)
    except UnboundGeneration:
        return {"state": "unbound", "tenant_generation": None}
    return {"state": "live" if generation else "missing", "tenant_generation": generation}


@frappe.whitelist(methods=["POST"])
def update_subscription(subdomain, tenant_generation, fields):
    _worker_permission("write")
    if not valid_generation(tenant_generation):
        raise frappe.ValidationError("An explicit tenant generation is required")
    fields = frappe.parse_json(fields) if isinstance(fields, str) else fields
    if not isinstance(fields, dict) or not fields or set(fields) - set(WORKER_FIELDS):
        raise frappe.ValidationError("Unsupported subscription update")
    row = _locked_subscription(subdomain)
    if not row or row.get("tenant_generation") != tenant_generation:
        raise frappe.ValidationError("Subscription belongs to a different tenant generation")
    cancelling = fields.get("status") == "Cancelled"
    if not cancelling and (row.get("billing_closed") or _generation(subdomain) != tenant_generation):
        raise frappe.ValidationError("Tenant is closing, missing, or has been replaced")
    if cancelling:
        fields = dict(fields, billing_closed=1)
    _set_locked("Nexum Subscription", subdomain, fields)
    return {"ok": True}


def _owned_attempt(plan_id, subdomain, generation, tier=None, state="Pending"):
    rows = _current_rows("select * from `tabBilling Checkout Attempt` where name=%s for update", (plan_id,))
    if rows:
        row = rows[0]
        if row.subdomain != subdomain or row.tenant_generation != generation:
            raise frappe.ValidationError("Plan belongs to a different tenant generation")
        return row
    doc = frappe.get_doc(dict(doctype="Billing Checkout Attempt", plan_id=plan_id, subdomain=subdomain,
                              tenant_generation=generation, tier=tier, state=state)).insert(ignore_permissions=True)
    return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def activate_subscription(subdomain, tenant_generation, plan_id, expected_plan_id, fields):
    """Publish plan ownership and cleanup obligations in ONE guarded transaction."""
    _worker_permission("write")
    if not valid_generation(tenant_generation) or not isinstance(plan_id, str) or not plan_id or len(plan_id) > 140:
        raise frappe.ValidationError("Invalid activation identity")
    fields = frappe.parse_json(fields) if isinstance(fields, str) else fields
    if (not isinstance(fields, dict) or set(fields) - set(MIRROR_FIELDS)
            or fields.get("xendit_plan_id") != plan_id or fields.get("status") != "Active"):
        raise frappe.ValidationError("Invalid activation fields")
    row = _locked_subscription(subdomain)
    if (not row or row.get("tenant_generation") != tenant_generation or row.get("billing_closed")
            or _generation(subdomain) != tenant_generation):
        raise frappe.ValidationError("Tenant changed or checkout is closed")
    old_plan_id = str(row.get("xendit_plan_id") or "")
    if old_plan_id not in (expected_plan_id, plan_id):
        raise frappe.ValidationError("Another plan became current before activation")
    attempts = {identity: _owned_attempt(identity, subdomain, tenant_generation,
                                         fields.get("plan") if identity == plan_id else row.get("plan"),
                                         "Inactive" if identity != plan_id and row.get("status") == "Inactive" else "Pending")
                for identity in sorted({old_plan_id, plan_id} - {""})}
    if old_plan_id != plan_id and attempts[plan_id].state in ("Inactive", "Superseded"):
        raise frappe.ValidationError("Obsolete attempt cannot replace the current plan")
    cleanup = []
    if old_plan_id != plan_id:
        # The winning activation retires every competing checkout already in
        # this generation, including a paid attempt interrupted before promotion.
        # Otherwise its NEXT cycle could acquire a fresh base and undo the winner.
        # A duplicate activation of the current plan must leave later checkouts alone.
        others = _current_rows("select name from `tabBilling Checkout Attempt` where subdomain=%s "
                               "and tenant_generation=%s and name!=%s and state!='Inactive' order by name for update",
                               (subdomain, tenant_generation, plan_id))
        for other in others:
            _set_locked("Billing Checkout Attempt", other.name,
                        {"superseded_by": plan_id, "state": "Superseded", "needs_deactivation": 1})
            cleanup.append(other.name)
    # No commit occurs between these writes. close_checkout cannot interleave
    # its durable cleanup flag with this activation's flag reset.
    if _generation(subdomain) != tenant_generation:
        raise frappe.ValidationError("Tenant changed during activation")
    _set_locked("Nexum Subscription", subdomain, fields)
    _set_locked("Billing Checkout Attempt", plan_id, {"state": "Activated", "needs_deactivation": 0})
    return {"deactivate": cleanup}


@frappe.whitelist(methods=["POST"])
def close_checkout(subdomain, tenant_generation):
    """Serialize with checkout, then durably close and return ALL outstanding plans."""
    _worker_permission("write")
    if not valid_generation(tenant_generation) or _generation(subdomain) != tenant_generation:
        raise frappe.ValidationError("Refusing to close another tenant generation")
    row = prepare_checkout(subdomain, allow_closed=True)
    if row.tenant_generation != tenant_generation:
        raise frappe.ValidationError("Tenant changed while closing billing")
    _set_locked("Nexum Subscription", subdomain, {"billing_closed": 1})
    _retire_plans(row)
    # Include earlier generations too: an old outstanding checkout must not
    # become an untracked recurring charge after this reusable name is deleted.
    attempts = _current_rows("select name,plan_id,tenant_generation,state from `tabBilling Checkout Attempt` "
                              "where subdomain=%s and state!='Inactive' for update", (subdomain,))
    for attempt in attempts:
        _set_locked("Billing Checkout Attempt", attempt.name, {"needs_deactivation": 1})
    return {"mirror": dict(row, billing_closed=1), "plans": attempts}
