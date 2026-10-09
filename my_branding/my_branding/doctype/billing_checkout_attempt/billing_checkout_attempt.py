"""One row per Xendit checkout session/recurring plan: the durable
plan_id -> (tenant, priced tier, lifecycle) record the billing worker resolves
events through. Scalar mirror slots proved un-auditable under overwrites
(review-gate rounds 2-3); this table is append-only per plan."""

from frappe.model.document import Document


class BillingCheckoutAttempt(Document):
	pass
