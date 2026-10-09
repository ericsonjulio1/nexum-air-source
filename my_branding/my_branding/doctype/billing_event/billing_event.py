# Copyright (c) 2026, Nexum Air
"""Billing Event — the webhook inbox (XENDIT-SPEC section 3). The receiver
writes one row per delivered Xendit event and answers 200 immediately; the
host billing worker consumes unprocessed rows asynchronously. Money state is
never mutated in the web request."""

from frappe.model.document import Document


class BillingEvent(Document):
    pass
