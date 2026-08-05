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
			frappe.log_error(f"coa_guard failed for {company}", "my_branding.coa_guard")
	frappe.db.commit()


def _fix_company(company):
	ap = _leaf(company, "2101 - Accounts Payable - Trade")
	if ap:
		current = frappe.db.get_value("Company", company, "default_payable_account")
		if current and "Customer Deposits" in current:
			frappe.db.set_value("Company", company, "default_payable_account", ap)

	# the chart's baked-in demo account — drop it while it is still unused
	leak = frappe.db.get_value(
		"Account", {"company": company, "name": ["like", "%Raw Materials - Demo%"]}, "name"
	)
	if leak and not frappe.db.count("GL Entry", {"account": leak}):
		frappe.delete_doc("Account", leak, force=True, ignore_permissions=True)

	vin = _leaf(company, "1611 - VAT Input Tax - Goods")
	vout = _leaf(company, "2201 - VAT Output Tax")
	if vin and vout:
		_repoint_tax_templates(company, vin, vout)
		# park the generic catch-all VAT leaf once nothing routes to it
		generic = frappe.db.get_value(
			"Account",
			{"company": company, "name": ["like", "VAT - %"], "is_group": 0, "disabled": 0},
			"name",
		)
		if generic and not frappe.db.count("GL Entry", {"account": generic}):
			frappe.db.set_value("Account", generic, "disabled", 1)

	transit = _leaf(company, "1532 - Inventory in Transit")
	if transit and frappe.db.get_value("Account", transit, "account_type") == "Stock Adjustment":
		frappe.db.set_value("Account", transit, "account_type", "Stock")


def _repoint_tax_templates(company, vin, vout):
	for child_dt, parent_dt, target in (
		("Purchase Taxes and Charges", "Purchase Taxes and Charges Template", vin),
		("Sales Taxes and Charges", "Sales Taxes and Charges Template", vout),
	):
		for row in frappe.get_all(
			child_dt,
			filters={"parenttype": parent_dt, "account_head": ["like", "VAT - %"]},
			fields=["name", "parent"],
		):
			if frappe.db.get_value(parent_dt, row.parent, "company") == company:
				frappe.db.set_value(child_dt, row.name, "account_head", target, update_modified=False)

	for itt in frappe.get_all("Item Tax Template", filters={"company": company}, pluck="name"):
		doc = frappe.get_doc("Item Tax Template", itt)
		changed = False
		for row in doc.taxes:
			if row.tax_type and row.tax_type.startswith("VAT - "):
				row.tax_type = vout
				changed = True
		if changed and not any(r.tax_type == vin for r in doc.taxes):
			doc.append("taxes", {"tax_type": vin, "tax_rate": 12.0})
		if changed:
			doc.flags.ignore_permissions = True
			doc.save()
