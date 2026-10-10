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
check runs uncached and exact. Journal Entry also leaves out the entries ERPNext books
by itself (see ``_is_system_journal``).
"""

import json

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, nowdate, time_diff_in_seconds

# master data has no submit workflow -> count all rows; everything else -> non-cancelled only
_MASTER_DATA = {"Customer", "Supplier", "Item"}

# A recurring copy Auto Repeat makes at the cap is refused like any other insert (it is
# the user's own document, see M13 below). frappe's Auto Repeat then disables the
# schedule and moves its next date past the refused one, and nothing switched it back on
# when the tenant upgraded (batch205 idx 159). So the refusal leaves a note on the Auto
# Repeat's timeline, and resume_capped_auto_repeats() re-enables such a schedule once the
# plan no longer caps its doctype. The note text is the marker it looks for (untranslated).
_PAUSED_NOTE = "Paused by the Free plan limit"
_RESUMED_NOTE = "Resumed after the Free plan limit was lifted"
# Auto Repeat disables the schedule and moves its date seconds after the note; a later
# change means a person has handled the schedule, so it is left alone.
_UNTOUCHED_SECONDS = 600

# Journal Entries ERPNext books by itself (M13, v204) are exempt from the Free-plan cap,
# from both the insert check and the count. They derive from documents the cap already
# counts (an invoice or payment) or from the fixed-asset register. Counting them made the
# daily depreciation job fail for every asset once a tenant reached the cap, and aborted
# the user's own foreign-currency Payment Entry / invoice submit and credit-note
# reconciliation. Only markers ERPNext itself sets identify them:
#  * is_system_generated = 1: ERPNext's read-only flag on exchange gain/loss entries
#    (accounts/utils.py create_gain_loss_journal), Payment Reconciliation credit/debit
#    notes and the common-party advance entry (controllers/accounts_controller.py).
#  * fixed-asset entries ("Depreciation Entry" / "Asset Disposal"). At insert they are
#    recognised by doc.flags.ignore_permissions, which ERPNext's asset code sets
#    (assets/doctype/asset/depreciation.py). A form or API payload can never carry
#    doc.flags (frappe drops a "flags" key, RESERVED_KEYWORDS). In the count they are
#    recognised by the link ERPNext writes back on submit (Depreciation
#    Schedule.journal_entry / Asset.journal_entry_for_scrap).
# voucher_type alone never exempts: it is a plain dropdown on the JE form, so a hand-made
# "Depreciation Entry" or "Credit Note" is still capped and counted. Auto Repeat copies
# are the user's own recurring entries, even though Auto Repeat inserts them with
# ignore_permissions. Residual: is_system_generated is read-only on the form, but the REST
# API and a Data Import column can still set it; that takes deliberate effort and is
# accepted for a soft Free-plan cap.
_ASSET_JOURNAL_TYPES = ("Depreciation Entry", "Asset Disposal")


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


def _is_system_journal(doc):
	"""True for a Journal Entry ERPNext is booking by itself (rule above)."""
	if doc.get("is_system_generated"):
		return True
	return (
		doc.get("voucher_type") in _ASSET_JOURNAL_TYPES
		and bool(doc.flags.get("ignore_permissions"))
		and not doc.get("auto_repeat")
	)


def _journal_entry_count():
	"""Non-cancelled Journal Entries that count against the cap: the user's own, without
	ERPNext's system entries (rule above). Free sites are small, and the EXISTS lookups only
	run for the rare fixed-asset voucher types."""
	return frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabJournal Entry` je
		 WHERE je.docstatus < 2
		   AND IFNULL(je.is_system_generated, 0) = 0
		   AND NOT (je.voucher_type = 'Depreciation Entry' AND EXISTS (
		        SELECT 1 FROM `tabDepreciation Schedule` ds WHERE ds.journal_entry = je.name))
		   AND NOT (je.voucher_type = 'Asset Disposal' AND EXISTS (
		        SELECT 1 FROM `tabAsset` a WHERE a.journal_entry_for_scrap = je.name))
		"""
	)[0][0]


def _count(doctype):
	"""Documents of ``doctype`` that count against its cap (counting rule above)."""
	if doctype == "Journal Entry":
		return _journal_entry_count()
	filters = {} if doctype in _MASTER_DATA else {"docstatus": ["<", 2]}
	return frappe.db.count(doctype, filters)


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
		if doc.doctype == "Journal Entry" and _is_system_journal(doc):
			return  # ERPNext's own entry: never blocked, never counted (M13)
		over_limit = _count(doc.doctype) >= limit
	except Exception:
		frappe.log_error(
			title="my_branding enforce_doc_cap failed (fail-open)",
			message=frappe.get_traceback(),
		)
		return

	if over_limit:
		auto_repeat = _auto_repeat_of(doc)
		if auto_repeat:
			_note_paused(auto_repeat, doc, limit)
			# Auto Repeat logs this in the Error Log its "Document Creation Failed" email links to
			frappe.throw(
				_(
					"You've reached your Free plan's limit of {0} {1} records, so the recurring "
					"{1} from Auto Repeat {2} was not created and the schedule is paused. It "
					"resumes by itself after an upgrade; create the missed {1} by hand if it is "
					"still owed."
				).format(limit, _(doc.doctype), auto_repeat),
				title=_("Free plan limit reached"),
			)
		frappe.throw(
			_(
				"You've reached your Free plan's limit of {0} {1} records. "
				"Upgrade to add more — all your existing data stays exactly as it is."
			).format(limit, _(doc.doctype)),
			title=_("Free plan limit reached"),
		)


def _auto_repeat_of(doc):
	"""The Auto Repeat inserting `doc`, from the flag its make_new_document sets (a form or
	API payload can never carry doc.flags), else None."""
	ref = doc.flags.get("updater_reference") or {}
	return ref.get("docname") if ref.get("doctype") == "Auto Repeat" else None


def _note_paused(auto_repeat, doc, limit):
	"""Timeline note on the Auto Repeat the cap just refused. Auto Repeat swallows the
	error and the scheduler job commits, so the note persists; a failure here never
	changes the refusal itself."""
	try:
		due = doc.get("posting_date") or doc.get("transaction_date")
		frappe.get_doc("Auto Repeat", auto_repeat).add_comment(
			"Info",
			"%s: the %s due %s was not created (the plan allows %s). The schedule resumes "
			"by itself after an upgrade." % (_PAUSED_NOTE, doc.doctype, formatdate(due) if due else "today", limit),
		)
	except Exception:
		frappe.log_error(title="my_branding doc cap: Auto Repeat note failed", message=frappe.get_traceback())


def resume_capped_auto_repeats():
	"""after_migrate — the Free -> paid upgrade runs one (mark-paid.sh launches
	change-plan.sh, which migrates), and so does every deploy: re-enable each Auto Repeat
	the cap paused, once the site no longer caps its doctype, unless someone has changed
	the schedule since. The periods missed while it was paused are NOT generated: whether
	those documents are still owed is the owner's billing call, so the resume note says
	which ones to check. Idempotent + hardened, like the other reconcilers."""
	if not frappe.db.table_exists("Auto Repeat"):
		return
	try:
		caps = _caps()
		paused = frappe.get_all(
			"Auto Repeat", filters={"disabled": 1}, fields=["name", "reference_doctype", "modified"]
		)
	except Exception:
		frappe.log_error(title="my_branding resume_capped_auto_repeats failed", message=frappe.get_traceback())
		return
	for ar in paused:
		try:
			limit = caps.get(ar.reference_doctype)
			if limit and int(limit) > 0:
				continue  # still capped: re-enabling would only be refused again
			note = frappe.get_all(
				"Comment",
				filters={
					"reference_doctype": "Auto Repeat",
					"reference_name": ar.name,
					"comment_type": "Info",
					"content": ["like", _PAUSED_NOTE + "%"],
				},
				fields=["creation"],
				order_by="creation desc",
				limit=1,
			)
			if not note or time_diff_in_seconds(ar.modified, note[0].creation) > _UNTOUCHED_SECONDS:
				continue  # not paused by the cap, or handled by hand since
			doc = frappe.get_doc("Auto Repeat", ar.name)
			doc.disabled = 0
			doc.flags.ignore_permissions = True
			doc.save()
			# save() sets the first due date ON or after today, but frappe's daily run only
			# creates a document dated exactly today and never moves a past date on: a
			# resume after today's run left the schedule Active and idle for good. Move it
			# to the next due date; today's document is one of the missed ones noted below.
			if doc.next_schedule_date and getdate(doc.next_schedule_date) <= getdate(nowdate()):
				doc.db_set(
					"next_schedule_date",
					doc.get_next_schedule_date(schedule_date=getdate(nowdate())),
					update_modified=False,
				)
			doc.add_comment(
				"Info",
				"%s. %s documents due from %s through today were not created while it was "
				"paused; create them by hand if they are still owed."
				% (_RESUMED_NOTE, ar.reference_doctype, formatdate(note[0].creation)),
			)
		except Exception:
			frappe.log_error(
				title=f"my_branding resume_capped_auto_repeats failed for {ar.name}",
				message=frappe.get_traceback(),
			)
