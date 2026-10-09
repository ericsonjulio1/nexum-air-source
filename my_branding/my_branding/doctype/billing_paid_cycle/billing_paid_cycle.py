"""Transactional outbox for applied paid cycles: unique per Billing Event,
carries the computed target_paid_until so a crash-resume re-applies exactly
the same entitlement (idempotency law: redelivery must never double-extend)."""

from frappe.model.document import Document


class BillingPaidCycle(Document):
	pass
