"""Nexum Air does not allow the PlutoPrint PDF generator (Frappe >= 16.55).

Why: the plutoprint wheel Frappe now requires vendors old native libraries (libcurl 7.61.1,
openssl 1.1.1k) that advisory scanners cannot see, and its bundled curl fetches any non-local
URL referenced by the printed HTML. Every tenant prints with wkhtmltopdf (Print Settings) and
chrome / wkhtmltopdf / unset (Print Formats), so refusing PlutoPrint changes nothing for them.
The package stays installed (Frappe's pyproject requires it); we only make it unselectable and
unreachable. Reversible: remove the hooks below, the reconciler's Property Setters are
system-generated and named `<DocType>-pdf_generator-options`.

Layers (each independent):
  1. validate on Print Settings / Print Format: saving PlutoPrint raises (UI, API, Data Import).
  2. before_request on print routes (and anywhere a request carries `pdf_generator`):
     an explicit `pdf_generator=PlutoPrint` argument, or a format / site setting that still
     resolves to PlutoPrint, is refused before any rendering starts. This is the render-time
     guard: Frappe's own `pdf_generator` hook list cannot pre-empt it (apps' hooks are
     appended after frappe's, and `get_plutoprint_pdf` is frappe's), and Print Designer's
     before_request only special-cases "chrome", so it would leave "PlutoPrint" to Frappe.
  3. reconcile_pdf_generators (after_migrate): drops the option from the two Select fields
     (Property Setter, derived from the shipped options so upstream drift is followed) and
     heals any stored PlutoPrint value on existing data.

Not covered (documented residual): server-side Python that passes pdf_generator="PlutoPrint"
explicitly to frappe.get_print / get_pdf outside a request. Tenants cannot run such code.
"""

import frappe

BLOCKED = "PlutoPrint"
_FIELD = "pdf_generator"
# doctype -> value a stored PlutoPrint is healed to
_HEAL = {"Print Settings": "wkhtmltopdf", "Print Format": ""}
_PRINT_PATHS = ("/api/method/frappe.utils.print_format.download_pdf", "/printview")


def _is_blocked(value):
	return isinstance(value, str) and value.strip().lower() == BLOCKED.lower()


def _message():
	return frappe._("The PlutoPrint PDF generator is not available on Nexum Air. Use wkhtmltopdf or chrome.")


def refuse_plutoprint_save(doc, method=None):
	"""doc_events validate for Print Settings and Print Format."""
	if _is_blocked(doc.get(_FIELD)):
		frappe.throw(_message(), title=frappe._("PDF generator not available"))


def refuse_plutoprint_request():
	"""before_request: refuse a print request that would render with PlutoPrint."""
	form = frappe.local.form_dict
	if _is_blocked(form.get(_FIELD)):
		frappe.throw(_message(), title=frappe._("PDF generator not available"))
	request = getattr(frappe.local, "request", None)
	if (getattr(request, "path", "") or "") not in _PRINT_PATHS:
		return
	try:
		from frappe.utils.print_utils import _print_format_doc_or_none, resolve_pdf_generator

		resolved = resolve_pdf_generator(_print_format_doc_or_none(form.get("format")), form.get(_FIELD) or None)
	except Exception:
		# resolution problems surface in Frappe's own render; never block printing on our probe
		return
	if _is_blocked(resolved):
		frappe.throw(_message(), title=frappe._("PDF generator not available"))


def options_without_blocked(options):
	"""Option string with PlutoPrint removed; every other option and the order are kept."""
	return "\n".join(o for o in (options or "").split("\n") if o.strip().lower() != BLOCKED.lower())


def _setter_name(doctype):
	return f"{doctype}-{_FIELD}-options"


def reconcile_pdf_generators():
	"""after_migrate: hide PlutoPrint in the UI and heal stored values. Hardened, idempotent."""
	try:
		for doctype, healed in _HEAL.items():
			shipped = frappe.db.get_value("DocField", {"parent": doctype, "fieldname": _FIELD}, "options")
			wanted = options_without_blocked(shipped)
			if shipped and wanted != shipped:
				name = _setter_name(doctype)
				cur = frappe.db.get_value("Property Setter", name, ["value", "is_system_generated"], as_dict=True)
				if not (cur and (cur.value == wanted or not cur.is_system_generated)):
					frappe.make_property_setter(
						{
							"doctype": doctype,
							"fieldname": _FIELD,
							"property": "options",
							"value": wanted,
							"property_type": "Text",
						},
						validate_fields_for_doctype=False,
						is_system_generated=True,
					)
					frappe.clear_cache(doctype=doctype)
			if doctype == "Print Settings":
				if _is_blocked(frappe.db.get_single_value(doctype, _FIELD)):
					frappe.db.set_single_value(doctype, _FIELD, healed)
			else:
				for name in frappe.get_all(doctype, filters={_FIELD: BLOCKED}, pluck="name"):
					frappe.db.set_value(doctype, name, _FIELD, healed, update_modified=False)
	except Exception:
		frappe.log_error(title="my_branding reconcile_pdf_generators failed", message=frappe.get_traceback())
