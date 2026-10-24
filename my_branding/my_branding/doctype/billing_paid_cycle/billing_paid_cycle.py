"""Transactional outbox for applied paid cycles: unique per Billing Event,
carries the computed target_paid_until so a crash-resume re-applies exactly
the same entitlement (idempotency law: redelivery must never double-extend)."""

import frappe
from frappe.model.document import Document


class BillingPaidCycle(Document):
	pass


def on_doctype_update():
	frappe.db.add_index("Billing Paid Cycle", ["subdomain", "tenant_generation", "completed"],
	                    index_name="billing_cycle_tenant_generation")
