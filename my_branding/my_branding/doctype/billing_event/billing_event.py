# Copyright (c) 2026, Nexum Air
"""Billing Event — the webhook inbox (XENDIT-SPEC section 3). The receiver
writes one row per delivered Xendit event and answers 200 immediately; the
host billing worker consumes unprocessed rows asynchronously. Money state is
never mutated in the web request."""

import frappe
from frappe.model.document import Document


class BillingEvent(Document):
    pass


def on_doctype_update():
    frappe.db.add_index("Billing Event", ["processed", "last_attempted_on", "creation"],
                        index_name="billing_event_pending_attempt")
    frappe.db.add_index("Billing Event", ["owner_alert_status", "owner_alert_attempted_on", "creation"],
                        index_name="billing_event_pending_alert")
