# Copyright (c) 2026, Nexum Air
"""Nexum Subscription — hq-side mirror of a tenant's Xendit recurring plan
(XENDIT-SPEC section 3). Source of truth for money state is Xendit; for tenant
lifecycle it is tenants.tsv on the host. This doctype only mirrors, for
dashboards and the reconciliation poller — the worker updates it, never the
other way around."""

from frappe.model.document import Document


class NexumSubscription(Document):
    pass
