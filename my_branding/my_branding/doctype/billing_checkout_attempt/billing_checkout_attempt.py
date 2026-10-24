"""One row per Xendit checkout session/recurring plan: the durable
plan_id -> (tenant, priced tier, lifecycle) record the billing worker resolves
events through. Scalar mirror slots proved un-auditable under overwrites
(review-gate rounds 2-3); this table is append-only per plan."""

import frappe
from frappe.model.document import Document


class BillingCheckoutAttempt(Document):
	pass


def on_doctype_update():
	frappe.db.add_index("Billing Checkout Attempt", ["subdomain", "tenant_generation", "state"],
	                    index_name="billing_attempt_tenant_generation")
	frappe.db.add_index("Billing Checkout Attempt", ["needs_deactivation", "deactivation_attempted_on", "creation"],
	                    index_name="billing_attempt_cleanup_order")
