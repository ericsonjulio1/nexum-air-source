"""Per-tenant document-count caps — Free-tier enforcement.

Each tenant's plan can set ``nexum_doc_caps`` in ``site_config.json``: a JSON
object mapping a DocType name to the maximum number of documents allowed on the
site (e.g. ``{"Customer": 10, "Sales Invoice": 50}``). When a new document of a
capped type would exceed the cap, the insert is blocked with a friendly
"upgrade your plan" message. Paid plans simply omit the key entirely -> unlimited.

This is the Free-tier sibling of the storage quota in ``storage.py`` and is wired
the same way (``doc_events`` in hooks.py, one ``before_insert`` per capped type).

Counting rule: master-data doctypes (Customer/Supplier/Item — no submit workflow)
count every record; transactional doctypes count every NON-CANCELLED document
(``docstatus < 2``, i.e. drafts + submitted) so the wall can't be skirted by
mass-drafting first, while cancelling a document frees a slot back. ``frappe.db.count``
is a single indexed ``COUNT(*)`` and Free sites are low-volume by definition, so the
check runs uncached and exact.
"""

import json

import frappe
from frappe import _

# master data has no submit workflow -> count all rows; everything else -> non-cancelled only
_MASTER_DATA = {"Customer", "Supplier", "Item"}


def _caps():
	"""Parsed ``{doctype: limit}`` from site_config; ``{}`` when unset (paid -> unlimited)."""
	raw = frappe.conf.get("nexum_doc_caps")
	if not raw:
		return {}
	if isinstance(raw, dict):
		return raw
	try:
		parsed = json.loads(raw)
		return parsed if isinstance(parsed, dict) else {}
	except (TypeError, ValueError):
		return {}


def enforce_doc_cap(doc, method=None):
	"""``before_insert`` on every capped doctype: block when the site is already at
	its plan cap for that doctype. Fail-OPEN — this runs on every insert of a capped
	type, so an unexpected internal error must NOT block a legitimate document; the
	cap ``frappe.throw`` is raised OUTSIDE the try so it still propagates normally."""
	try:
		caps = _caps()
		if not caps:
			return  # paid / unlimited
		limit = caps.get(doc.doctype)
		if not limit or int(limit) <= 0:
			return
		limit = int(limit)
		filters = {} if doc.doctype in _MASTER_DATA else {"docstatus": ["<", 2]}
		over_limit = frappe.db.count(doc.doctype, filters) >= limit
	except Exception:
		frappe.log_error(
			title="my_branding enforce_doc_cap failed (fail-open)",
			message=frappe.get_traceback(),
		)
		return

	if over_limit:
		frappe.throw(
			_(
				"You've reached your Free plan's limit of {0} {1} records. "
				"Upgrade to add more — all your existing data stays exactly as it is."
			).format(limit, _(doc.doctype)),
			title=_("Free plan limit reached"),
		)
