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

Runs after every migrate, self-healing existing sites and any future tenant.
Each step only acts when the numbered target leaf actually exists, so
standard-chart sites (demo/smoketest/...) are no-ops. Hardened: a failure in
one company/step never aborts the migrate.
"""

import frappe


def _leaf(company, prefix):
	return frappe.db.get_value(
		"Account", {"company": company, "name": ["like", prefix + "%"], "is_group": 0}, "name"
	)


def reconcile_ph_coa_defaults():
	for company in frappe.get_all("Company", pluck="name"):
		try:
			_fix_company(company)
		except Exception:
			# message must be the traceback (batch-183, sweep C35): passing a label
			# as the second positional arg logged the literal string and dropped the
			# actual exception entirely
			frappe.log_error(
				title=f"coa_guard failed for {company}",
				message=frappe.get_traceback(),
			)
	frappe.db.commit()


def _fix_company(company):
	ap = _leaf(company, "2101 - Accounts Payable - Trade")
	if ap:
		current = frappe.db.get_value("Company", company, "default_payable_account")
		if current and "Customer Deposits" in current:
			frappe.db.set_value("Company", company, "default_payable_account", ap)

	# the chart's baked-in demo account — drop it while it is still unused.
	# Match account_name EXACTLY (2026-08-29 sweep): the old `like
	# "%Raw Materials - Demo%"` also caught tenant-created accounts such as
	# "Raw Materials - Demolition - <abbr>" and force-deleted them on every
	# migrate — the same lesson the VAT block below already documents (MB-1).
	leak = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Raw Materials - Demo"}, "name"
	)
	if leak and not frappe.db.count("GL Entry", {"account": leak}):
		frappe.delete_doc("Account", leak, force=True, ignore_permissions=True)

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
		# park the generic catch-all VAT leaf once nothing routes to it
		if (
			generic
			and not frappe.db.get_value("Account", generic, "disabled")
			and not frappe.db.count("GL Entry", {"account": generic})
		):
			frappe.db.set_value("Account", generic, "disabled", 1)

	# upstream renumbered the PH chart (erpnext 5281d538ce / PR #56817, 16.27+): the leaf
	# is "1542 - Inventory in Transit" on sites created after that, "1532 - ..." before —
	# match by account_name so both heal (still typed "Stock Adjustment" upstream)
	transit = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Inventory in Transit", "is_group": 0}, "name"
	) or _leaf(company, "1532 - Inventory in Transit")
	if transit and frappe.db.get_value("Account", transit, "account_type") == "Stock Adjustment":
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
		repointed_rates = []
		for row in doc.taxes:
			if row.tax_type == generic:
				row.tax_type = vout
				changed = True
				repointed_rates.append(row.tax_rate or 0)
		# the appended input-VAT row INHERITS the repointed row's rate (batch-183,
		# sweep C11): the hardcoded 12.0 silently turned a zero-rated/exempt template
		# into one that computes 12% input VAT on every purchase. All-zero rates =
		# a zero-rated template — no input-VAT row belongs on it at all.
		if changed and not any(r.tax_type == vin for r in doc.taxes) \
				and any(r for r in repointed_rates):
			# first NON-ZERO rate (review L4): a mixed template whose first generic
			# row was 0% would otherwise append a useless 0% input-VAT row
			doc.append("taxes", {"tax_type": vin,
			                     "tax_rate": next(r for r in repointed_rates if r)})
		if changed:
			doc.flags.ignore_permissions = True
			doc.save()
