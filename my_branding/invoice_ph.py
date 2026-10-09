"""Nexum Invoice (PH) — the official, BIR-layout Sales Invoice print format + the
Company fields that drive it (2026-08-23, first used for Nordstern Engineering Design
Services on hq).

* Print Format "Nexum Invoice (PH)" is a STANDARD Jinja format shipped in this app's
  module folder (my_branding/my_branding/print_format/nexum_invoice_ph/) so migrate
  syncs it on every tenant. It is self-contained (no Letter Head): logo, trade name,
  registered name, address, TIN with the VAT / NON-VAT qualifier, contact line, the
  "NOT VALID FOR CLAIM OF INPUT TAX" legend for Non-VAT registrants, customer TIN /
  address, items, taxes, totals, amount in words, signature lines and an optional
  permit/footer text.
* Company custom fields (section "Invoice (PH)"): nx_registered_name, nx_tax_registration
  (VAT / Non-VAT), nx_invoice_footer. Created by `ensure_company_invoice_fields`
  (after_migrate, idempotent, hardened). Values are per-tenant DATA — nothing here
  sets them; hq's Nordstern values were set by hand (see memory).
* `set_default_for_company(...)` is a helper for `bench execute` to make the format
  the Sales Invoice default on a given site (Property Setter), used on hq.
"""

import frappe

PRINT_FORMAT = "Nexum Invoice (PH)"

COMPANY_FIELDS = {
	"Company": [
		{
			"fieldname": "nx_invoice_ph_section",
			"label": "Invoice (PH)",
			"fieldtype": "Section Break",
			"insert_after": "date_of_commencement",
			"collapsible": 1,
		},
		{
			"fieldname": "nx_registered_name",
			"label": "Registered Name (BIR)",
			"fieldtype": "Data",
			"insert_after": "nx_invoice_ph_section",
			"description": "Taxpayer name on the BIR Certificate of Registration, if different from the company/trade name (printed on invoices).",
		},
		{
			"fieldname": "nx_tax_registration",
			"label": "Tax Registration",
			"fieldtype": "Select",
			"options": "\nVAT\nNon-VAT",
			"insert_after": "nx_registered_name",
			"description": "Drives the TIN qualifier (VAT / NON-VAT Reg. TIN) and the input-tax legend on invoices.",
		},
		{
			"fieldname": "nx_invoice_ph_cb",
			"fieldtype": "Column Break",
			"insert_after": "nx_tax_registration",
		},
		{
			"fieldname": "nx_invoice_footer",
			"label": "Invoice Footer / Permit Text",
			"fieldtype": "Small Text",
			"insert_after": "nx_invoice_ph_cb",
			"description": "Optional line(s) printed at the bottom of every invoice (e.g. BIR permit / ATP details, payment instructions).",
		},
	]
}


def ensure_company_invoice_fields():
	"""after_migrate: Company fields the PH invoice format reads. Idempotent + hardened."""
	if not frappe.db.table_exists("Company"):
		return
	try:
		from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

		create_custom_fields(COMPANY_FIELDS, ignore_validate=True, update=True)
	except Exception:
		frappe.log_error(title="my_branding ensure_company_invoice_fields failed", message=frappe.get_traceback())


def set_default_for_company(doctype="Sales Invoice"):
	"""bench execute helper: make Nexum Invoice (PH) the default print format for `doctype`
	on this site (Property Setter default_print_format). Returns the resulting value."""
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		frappe.throw(f"{PRINT_FORMAT} not synced on this site")
	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocType",
			"property": "default_print_format",
			"value": PRINT_FORMAT,
			"property_type": "Data",
		},
		validate_fields_for_doctype=False,
	)
	frappe.clear_cache(doctype=doctype)
	return frappe.db.get_value("Property Setter", f"{doctype}-main-default_print_format", "value")
