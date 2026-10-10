"""Free-plan Journal Entry cap leaves ERPNext's own entries alone (M13, v204).

ERPNext books Journal Entries by itself (daily depreciation, exchange gain/loss,
reconciliation credit/debit notes, the common-party advance). They must neither be
blocked by the cap nor use it up, while a hand-made entry, including one whose voucher
type was merely picked from the dropdown, stays capped and counted.

Rows are written inside a savepoint and rolled back; nothing is committed.
Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_doc_caps
"""
import unittest
from contextlib import contextmanager

import frappe

from my_branding import doc_caps

SAVEPOINT = "nx_doc_caps_test"


@contextmanager
def _caps(**caps):
	"""Temporarily make this a Free site with these nexum_doc_caps."""
	old = frappe.conf.get("nexum_doc_caps")
	frappe.conf.nexum_doc_caps = caps
	try:
		yield
	finally:
		if old is None:
			frappe.conf.pop("nexum_doc_caps", None)
		else:
			frappe.conf.nexum_doc_caps = old


def _journal(**fields):
	"""An unsaved Journal Entry, shaped like the one its creator builds."""
	doc = frappe.new_doc("Journal Entry")
	doc.update({"voucher_type": "Journal Entry", **fields})
	return doc


def _depreciation_entry():
	"""As ERPNext's _make_journal_entry_for_depreciation builds it (depreciation.py)."""
	doc = _journal(voucher_type="Depreciation Entry")
	doc.flags.ignore_permissions = True
	return doc


def _row(**fields):
	"""A bare tabJournal Entry row (inside the savepoint) for the count."""
	values = {
		"name": "_nx-m13-" + frappe.generate_hash(length=10),
		"docstatus": 1,
		"voucher_type": "Journal Entry",
		"is_system_generated": 0,
		**fields,
	}
	frappe.db.sql(
		"INSERT INTO `tabJournal Entry` ({}) VALUES ({})".format(
			", ".join(f"`{k}`" for k in values), ", ".join(["%s"] * len(values))
		),
		tuple(values.values()),
	)
	return values["name"]


def _link_to_depreciation_schedule(journal_entry):
	"""What JournalEntry.update_journal_entry_link_on_depr_schedule writes on submit."""
	frappe.db.sql(
		"""INSERT INTO `tabDepreciation Schedule` (name, parent, parenttype, parentfield, journal_entry)
		   VALUES (%s, '_nx-m13-schedule', 'Asset Depreciation Schedule', 'depreciation_schedule', %s)""",
		("_nx-m13-" + frappe.generate_hash(length=10), journal_entry),
	)


class TestJournalEntryCap(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint(SAVEPOINT)

	def tearDown(self):
		frappe.db.rollback(save_point=SAVEPOINT)

	def _blocked(self, doc):
		"""Run the real before_insert hook chain; True when the Free-plan cap refuses it."""
		try:
			doc.run_method("before_insert")
		except frappe.ValidationError as e:
			self.assertIn("Free plan", str(e))
			return True
		return False

	def test_hand_made_entries_count_and_system_ones_do_not(self):
		base = doc_caps._count("Journal Entry")
		_row()  # an ordinary manual entry
		_row(voucher_type="Credit Note")  # dropdown pick, made by hand
		_row(voucher_type="Depreciation Entry")  # dropdown pick, never linked by ERPNext
		_row(docstatus=0)  # a draft still holds its slot
		_row(docstatus=2)  # a cancelled entry frees its slot
		_row(voucher_type="Exchange Gain Or Loss", is_system_generated=1)
		_row(voucher_type="Credit Note", is_system_generated=1)  # Payment Reconciliation
		depreciation = _row(voucher_type="Depreciation Entry")
		_link_to_depreciation_schedule(depreciation)
		self.assertEqual(doc_caps._count("Journal Entry"), base + 4)

	def test_manual_entry_is_still_capped(self):
		_row()
		with _caps(**{"Journal Entry": doc_caps._count("Journal Entry")}):
			self.assertTrue(self._blocked(_journal()))
			# picking a system-looking voucher type in the form does not get round the cap
			self.assertTrue(self._blocked(_journal(voucher_type="Depreciation Entry")))
			self.assertTrue(self._blocked(_journal(voucher_type="Credit Note")))
			# Auto Repeat inserts the user's recurring copies with ignore_permissions
			copy = _depreciation_entry()
			copy.auto_repeat = "_nx-m13-auto-repeat"
			self.assertTrue(self._blocked(copy))

	def test_depreciation_entry_is_neither_blocked_nor_counted(self):
		_row()
		count = doc_caps._count("Journal Entry")
		with _caps(**{"Journal Entry": count}):
			self.assertFalse(self._blocked(_depreciation_entry()))
			disposal = _journal(voucher_type="Asset Disposal")
			disposal.flags.ignore_permissions = True
			self.assertFalse(self._blocked(disposal))
		# once ERPNext submits it and links it to the schedule row, it stays out of the count
		_link_to_depreciation_schedule(_row(voucher_type="Depreciation Entry"))
		self.assertEqual(doc_caps._count("Journal Entry"), count)

	def test_erpnext_system_generated_entries_are_not_blocked(self):
		_row()
		with _caps(**{"Journal Entry": doc_caps._count("Journal Entry")}):
			# exchange gain/loss booked while the user's own Payment Entry submits
			gain_loss = _journal(voucher_type="Exchange Gain Or Loss", is_system_generated=1)
			self.assertFalse(self._blocked(gain_loss))
			# common-party advance booked while an invoice submits
			self.assertFalse(self._blocked(_journal(is_system_generated=1)))

	def test_other_capped_doctypes_count_as_before(self):
		self.assertEqual(doc_caps._count("Customer"), frappe.db.count("Customer"))
		self.assertEqual(
			doc_caps._count("Sales Invoice"), frappe.db.count("Sales Invoice", {"docstatus": ["<", 2]})
		)
