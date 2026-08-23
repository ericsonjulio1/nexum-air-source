"""Simple-mode Sales Invoice / Purchase Invoice / Payment Entry for Free + Essentials
(UX plan 2026-08-23, step 2).

Mechanism: plain Property Setters (pure data, reversible) that put the rarely-needed
header fields behind a per-user "Show advanced fields" toggle:

    depends_on = eval:(!frappe.boot.nx_simple_mode || doc.<field>) && (<original>)

so the field is visible when (a) the desk is NOT in simple mode (Business/Enterprise,
or the user flipped the toggle), or (b) the document already carries a value — an
existing return / TDS invoice never hides its own flags. Returns, debit notes etc.
still work through the Create > menu (the flags are set programmatically).
The Items-grid Warehouse column is taken out of the list view (still in the row form;
`set_warehouse` fills it when Update Stock is on).

`reconcile_simple_mode` (after_migrate) applies the setters on simple plans and removes
exactly ours when a site is upgraded to Business/Enterprise (plan.py decides). Module is
left empty on purpose so the Property Setter fixture filter (module = My Branding) never
exports them.
"""

import frappe

from my_branding.plan import get_plan, is_simple_plan, simple_mode_for_session

_GATE = "!frappe.boot.nx_simple_mode"

# (doctype, fieldname) -> field is "advanced" for simple plans
ADVANCED_FIELDS = {
	"Sales Invoice": [
		"posting_time",
		"is_return",
		"is_debit_note",
		"apply_tds",
		"scan_barcode",
		"incoterm",
		"named_place",
		"shipping_rule",
		"tax_category",
		"is_pos",
	],
	"Purchase Invoice": [
		"posting_time",
		"is_return",
		"apply_tds",
		"scan_barcode",
		"incoterm",
		"named_place",
		"shipping_rule",
		"tax_category",
		"is_subcontracted",
		"rejected_warehouse",
	],
	"Payment Entry": [
		"apply_tds",
		"tax_withholding_category",
		"book_advance_payments_in_separate_party_account",
		"bank_account",
		"party_bank_account",
		"purchase_taxes_and_charges_template",
		"sales_taxes_and_charges_template",
	],
}
# grid columns dropped from the list view on simple plans (row form still has them)
GRID_COLUMNS = {
	"Sales Invoice Item": ["warehouse"],
	"Purchase Invoice Item": ["warehouse"],
}


def _pristine(doctype, fieldname, prop):
	"""The app-shipped value (tabDocField), NOT the property-setter-applied meta."""
	return frappe.db.get_value("DocField", {"parent": doctype, "fieldname": fieldname}, prop)


# fields that always carry a value on a new doc (defaults) -> the "already has a value"
# escape would make the gate a no-op, so these are gated on the flag alone
_NO_VALUE_ESCAPE = {"posting_time"}


def _gated_depends_on(doctype, fieldname):
	original = (_pristine(doctype, fieldname, "depends_on") or "").strip()
	own = f"({_GATE})" if fieldname in _NO_VALUE_ESCAPE else f"({_GATE} || doc.{fieldname})"
	if not original:
		return f"eval:{own}"
	if original.startswith("eval:"):
		return f"eval:{own} && ({original[5:].strip()})"
	# bare fieldname form
	return f"eval:{own} && doc.{original}"


def planned_setters():
	"""[(doctype, fieldname, property, value, property_type)] for simple mode."""
	out = []
	for dt, fields in ADVANCED_FIELDS.items():
		if not frappe.db.exists("DocType", dt):
			continue
		for f in fields:
			if not frappe.db.exists("DocField", {"parent": dt, "fieldname": f}):
				continue  # field dropped/renamed upstream -> skip, never throw
			out.append((dt, f, "depends_on", _gated_depends_on(dt, f), "Data"))
	for dt, cols in GRID_COLUMNS.items():
		if not frappe.db.exists("DocType", dt):
			continue
		for f in cols:
			if frappe.db.exists("DocField", {"parent": dt, "fieldname": f}):
				out.append((dt, f, "in_list_view", "0", "Check"))
	return out


def _ps_name(dt, f, prop):
	return f"{dt}-{f}-{prop}"


def _ours():
	"""Names of property setters we may have created (superset over all known rules)."""
	names = []
	for dt, fields in ADVANCED_FIELDS.items():
		names += [_ps_name(dt, f, "depends_on") for f in fields]
	for dt, cols in GRID_COLUMNS.items():
		names += [_ps_name(dt, f, "in_list_view") for f in cols]
	return names


def apply_simple_mode():
	changed = False
	for dt, f, prop, value, ptype in planned_setters():
		name = _ps_name(dt, f, prop)
		cur = frappe.db.get_value("Property Setter", name, ["value", "is_system_generated"], as_dict=True)
		if cur and cur.value == value:
			continue
		if cur and not cur.is_system_generated:
			# a human customised this property via Customize Form — don't fight them
			continue
		frappe.make_property_setter(
			{"doctype": dt, "fieldname": f, "property": prop, "value": value, "property_type": ptype},
			validate_fields_for_doctype=False,
			is_system_generated=True,
		)
		changed = True
	return changed


def remove_simple_mode():
	changed = False
	for name in _ours():
		row = frappe.db.get_value("Property Setter", name, ["name", "is_system_generated", "value"], as_dict=True)
		if not row:
			continue
		# only delete what we generated (gated depends_on / our in_list_view=0)
		if row.is_system_generated and (_GATE in (row.value or "") or name.endswith("-in_list_view")):
			frappe.delete_doc("Property Setter", name, force=True, ignore_permissions=True)
			changed = True
	return changed


def reconcile_simple_mode():
	"""after_migrate: simple plans get the setters, others get them removed. Hardened."""
	if not frappe.db.table_exists("Property Setter"):
		return
	try:
		changed = apply_simple_mode() if is_simple_plan() else remove_simple_mode()
		if changed:
			for dt in list(ADVANCED_FIELDS) + list(GRID_COLUMNS):
				frappe.clear_cache(doctype=dt)
	except Exception:
		frappe.log_error(title="my_branding reconcile_simple_mode failed", message=frappe.get_traceback())


def boot(bootinfo):
	"""extend_bootinfo payload used by the gated depends_on + brand.js report presets."""
	bootinfo.nx_plan = get_plan()
	bootinfo.nx_simple_mode = simple_mode_for_session()
	bootinfo.nx_simple_plan = 1 if is_simple_plan() else 0
