"""Chart-of-accounts guard for tenants provisioned with ERPNext's verified
Philippines (numbered) chart.

Upstream erpnext's philippines.json ships two defects every PH-chart company
inherits (found in the 2026-07-24 all-tenant books audit):
  1. "Customer Deposits" is typed Payable, so company setup can pick it as
     default_payable_account over "2101 - Accounts Payable - Trade" — every
     supplier document then books AP into a customer-deposit liability
     (jcpdemesa's Demo company had PHP 184k posted there).
  2. A literal "Raw Materials - Demo" account is part of the chart.
Additionally the auto-created generic "VAT - <abbr>" account captures both
sides of VAT while the chart's dedicated 1611 (input, Asset) / 2201 (output,
Liability) leaves sit unused, and "1532 - Inventory in Transit" is typed
"Stock Adjustment" (a P&L difference type) instead of "Stock".

Runs after every migrate. Existing accounts are never deleted or disabled:
absence of GL does not prove that drafts, defaults or custom links do not use
them. A company's reconciliation is atomic; a failure is logged and later
companies can still be reconciled.
"""

import frappe


def _leaf(company, prefix):
	return frappe.db.get_value(
		"Account", {"company": company, "name": ["like", prefix + "%"], "is_group": 0}, "name"
	)


def reconcile_ph_coa_defaults():
	for company in frappe.get_all("Company", pluck="name"):
		frappe.db.savepoint("nx_coa_company")
		try:
			_fix_company(company)
		except Exception as error:
			traceback = frappe.get_traceback()
			try:
				frappe.db.rollback(save_point="nx_coa_company")
			except Exception:
				if not isinstance(error, (frappe.QueryDeadlockError, frappe.QueryTimeoutError)):
					# An unexpected savepoint failure must abort migration. Silently
					# rolling back everything could discard earlier hooks' writes.
					raise
				# These database failures can already have rolled back the whole
				# transaction, including the savepoint. Prior companies committed
				# separately, so recovery cannot erase their changes.
				frappe.db.rollback()
			frappe.log_error(
				title=f"coa_guard failed for {company}",
				message=traceback,
			)
		frappe.db.commit()


def _fix_company(company):
	ap = _leaf(company, "2101 - Accounts Payable - Trade")
	if ap:
		current = frappe.db.get_value("Company", company, "default_payable_account")
		if current and "Customer Deposits" in current:
			frappe.db.set_value("Company", company, "default_payable_account", ap)

	# Keep even the chart's baked-in demo leaf. Drafts, warehouse/item defaults,
	# budgets and custom Link fields can reference an account before it posts GL.

	vin = _leaf(company, "1611 - VAT Input Tax - Goods")
	vout = _leaf(company, "2201 - VAT Output Tax")
	if vin and vout:
		# The auto-created catch-all is named exactly "VAT - <company abbr>". Match it
		# EXACTLY — a `like "VAT - %"` here also caught tenant-created accounts such as
		# "VAT - Export Output - <abbr>" and silently rewrote/disabled them every
		# migrate, fighting a customization the tenant made on purpose.
		abbr = frappe.db.get_value("Company", company, "abbr")
		generic = (
			frappe.db.get_value(
				"Account",
				{"company": company, "name": "VAT - %s" % abbr, "is_group": 0},
				"name",
			)
			if abbr
			else None
		)
		_repoint_tax_templates(company, vin, vout, generic)
		# Do not disable the old leaf: tax tables are not an exhaustive inventory
		# of references (Journal/Payment drafts, POS settings, custom fields, etc.).

	# upstream renumbered the PH chart (erpnext 5281d538ce / PR #56817, 16.27+): the leaf
	# is "1542 - Inventory in Transit" on sites created after that, "1532 - ..." before —
	# match by account_name so both heal (still typed "Stock Adjustment" upstream)
	transit = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Inventory in Transit", "is_group": 0}, "name"
	) or _leaf(company, "1532 - Inventory in Transit")
	if (
		transit
		and frappe.db.get_value("Account", transit, "account_type") == "Stock Adjustment"
		and frappe.db.get_value("Company", company, "stock_adjustment_account") != transit
	):
		frappe.db.set_value("Account", transit, "account_type", "Stock")


def _repoint_tax_templates(company, vin, vout, generic):
	"""Repoint template rows that route to the auto-created generic VAT account onto
	the chart's dedicated 1611/2201 leaves. Only rows pointing at the EXACT generic
	account are touched — any other "VAT - ..." account is a tenant's own ledger."""
	if not generic:
		return
	for child_dt, parent_dt, target in (
		("Purchase Taxes and Charges", "Purchase Taxes and Charges Template", vin),
		("Sales Taxes and Charges", "Sales Taxes and Charges Template", vout),
	):
		for row in frappe.get_all(
			child_dt,
			filters={"parenttype": parent_dt, "account_head": generic},
			fields=["name", "parent"],
		):
			if frappe.db.get_value(parent_dt, row.parent, "company") == company:
				frappe.db.set_value(child_dt, row.name, "account_head", target, update_modified=False)

	for itt in frappe.get_all("Item Tax Template", filters={"company": company}, pluck="name"):
		doc = frappe.get_doc("Item Tax Template", itt)
		changed = False
		for row in list(doc.taxes):
			if row.tax_type == generic:
				# Item overrides are keyed by account. A missing input-VAT key
				# falls back to the purchase template's rate, so 0% and "not
				# applicable" must be copied to BOTH new accounts too. Preserve
				# an explicit input/output override the tenant already chose;
				# replacing generic with an existing output key creates a
				# duplicate and prevents the template from saving.
				for target in (vout, vin):
					if not any(existing.tax_type == target for existing in doc.taxes):
						doc.append("taxes", {
							"tax_type": target,
							"tax_rate": row.tax_rate or 0,
							"not_applicable": row.get("not_applicable") or 0,
						})
				doc.remove(row)
				changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save()
