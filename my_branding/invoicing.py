"""Surface a customizable, branded invoice design (Print Designer).

print_designer is baked into every paid tier but ships invisible: its demo
format ("Sales Invoice PD Format v2") is plain grey and nothing on the desk
points a client at the visual editor. This after_migrate hook gives every
tenant a polished starting point plus two entry points to customize it:

  1. an "Invoice Design" Print Format — a slate-teal-branded clone of the
     Print Designer demo format. CREATE-ONLY: the whole point is that the
     client edits it in Print Designer, so a migrate must never clobber
     their customizations;
  2. that format becomes the Sales Invoice default print format — only if
     the tenant hasn't already chosen a default of their own.

The client-facing entry point is the "Invoice Design" button on the Sales
Invoice form (public/js/sales_invoice.js via doctype_js). v16-prod-85 also
put an "Invoice Designer" shortcut on the Selling workspace; the owner
found it clutter, so this hook now REMOVES that shortcut wherever an
earlier build created it.

No-op on sites without print_designer (Free tier installs erpnext +
my_branding only). Idempotent + hardened so it can never abort a migrate.
Mirrors webshop.ensure_online_store_workspace.
"""

import json

import frappe

_PF = "Invoice Design"
# v16-prod-85/86 shipped the format as "Nexum Air Invoice"; the owner wants the
# editor header (which displays the format NAME — it's a click-to-rename field,
# so CSS text tricks would break renaming) to read "Invoice Design" instead.
_OLD_PF = "Nexum Air Invoice"
_SRC = "Sales Invoice PD Format v2"
_SHORTCUT = "Invoice Designer"

# The demo format's neutral-grey ink ramp -> the brand slate-teal ramp
# (primary #2E5562, darkest #1C2B30; mid/light tints derived in-family).
_COLOR_MAP = {
	"#171B1F": "#1C2B30",  # headings / strong ink
	"#333C44": "#2E5562",  # emphasis ink -> brand primary
	"#505A62": "#4A6A78",  # secondary labels (AA-safe on white)
	"#F4F5F6": "#EAF1F3",  # table-header band -> light slate tint
}

# Every field of the source doc that embeds colors (Print Designer keeps the
# canvas as JSON strings; a plain text replace is safe because the greys only
# appear as style values).
_BLOB_FIELDS = (
	"print_designer_print_format",
	"print_designer_header",
	"print_designer_body",
	"print_designer_footer",
	"print_designer_settings",
	"css",
)


def _rebrand(text):
	for old, new in _COLOR_MAP.items():
		text = text.replace(old, new).replace(old.lower(), new)
	return text


def _rename_legacy_format():
	"""One-time: carry v16-prod-85/86 tenants from "Nexum Air Invoice" to
	"Invoice Design". A tenant who already renamed the format themselves has
	neither name — nothing happens."""
	if frappe.db.exists("Print Format", _OLD_PF) and not frappe.db.exists("Print Format", _PF):
		# frappe.rename_doc (the whitelisted wrapper) rejects ignore_permissions;
		# use the model-layer function directly.
		from frappe.model.rename_doc import rename_doc

		rename_doc("Print Format", _OLD_PF, _PF, ignore_permissions=True, show_alert=False)


def _ensure_print_format():
	if frappe.db.exists("Print Format", _PF):
		return
	if not frappe.db.exists("Print Format", _SRC):
		return  # older/newer print_designer without the demo format — nothing to clone
	src = frappe.get_doc("Print Format", _SRC)
	doc = frappe.copy_doc(src)
	doc.name = _PF
	# a DB-owned custom format the client may edit — NOT an app template
	doc.standard = "No"
	doc.print_designer_template_app = None
	doc.print_designer_preview_img = None  # site-specific /private/files path
	for field in _BLOB_FIELDS:
		if doc.get(field):
			doc.set(field, _rebrand(doc.get(field)))
	doc.insert(ignore_permissions=True)


# defaults we own and may upgrade: the stock value erpnext/setup/install.py::
# set_default_print_formats stamps on every new site, and our own former format
# name (rename_doc does NOT rewrite Data-type property setter values). Anything
# else = the tenant picked their own default — never touched.
_UPGRADEABLE_DEFAULTS = ("Sales Invoice with Item Image", _OLD_PF)


def _ensure_default_format():
	"""Make the branded format the Sales Invoice print default. Overrides only
	the absent/stock/our-legacy default — a default the tenant picked themselves
	is never touched."""
	if not frappe.db.exists("Print Format", _PF):
		return
	ps = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Sales Invoice", "property": "default_print_format"},
		["name", "value"],
		as_dict=True,
	)
	if ps is None:
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(
			"Sales Invoice", None, "default_print_format", _PF, "Data", for_doctype=True
		)
	elif ps.value in _UPGRADEABLE_DEFAULTS:
		frappe.db.set_value("Property Setter", ps.name, "value", _PF, update_modified=False)


def _remove_selling_shortcut():
	"""Strip the v16-prod-85 "Invoice Designer" shortcut (row + content block)
	from the Selling workspace on every tenant that got it. Idempotent no-op
	once gone."""
	if not frappe.db.exists("Workspace", "Selling"):
		return
	ws = frappe.get_doc("Workspace", "Selling")
	changed = False
	keep = [s for s in ws.shortcuts if s.label != _SHORTCUT]
	if len(keep) != len(ws.shortcuts):
		ws.set("shortcuts", keep)
		changed = True
	content = json.loads(ws.content or "[]")
	pruned = [
		b
		for b in content
		if not (
			b.get("type") == "shortcut" and (b.get("data") or {}).get("shortcut_name") == _SHORTCUT
		)
	]
	if len(pruned) != len(content):
		ws.content = json.dumps(pruned)
		changed = True
	if changed:
		ws.flags.ignore_links = True
		ws.save(ignore_permissions=True)


def ensure_invoice_design():
	"""after_migrate: branded Print Designer invoice + entry points. No-op unless
	print_designer is installed (paid tiers). Idempotent + hardened so it can
	never abort a migrate."""
	if not frappe.db.table_exists("Print Format"):
		return
	try:
		if "print_designer" not in frappe.get_installed_apps():
			return
		_rename_legacy_format()
		_ensure_print_format()
		_ensure_default_format()
		_remove_selling_shortcut()
		try:
			frappe.cache.delete_key("bootinfo")
		except Exception:
			pass
	except Exception:
		frappe.log_error(
			title="my_branding ensure_invoice_design failed",
			message=frappe.get_traceback(),
		)
