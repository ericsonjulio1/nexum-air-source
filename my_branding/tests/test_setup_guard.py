"""Provisioning must not turn a pending or failed native setup into a success.

All setup writes are intercepted. The lock-contention case runs the installed
Framework setup_complete itself, whose duplicate-request response is status=ok.
"""
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import frappe
from frappe.desk.page.setup_wizard import setup_wizard

from my_branding import setup_guard


class TestAutocompleteSetup(unittest.TestCase):

	def invoke(self, result=None, *, completed=False, already_complete=False, native_timeout=False):
		state = {"complete": already_complete}
		writes = []
		native_sql = frappe.db.sql

		def record(method):
			def write(*args, **kwargs):
				writes.append((method, args, kwargs))
			return write

		def sql(query, *args, **kwargs):
			# Let Framework load metadata/translations, while intercepting the
			# legacy direct completion UPDATE along with every other SQL write.
			if str(query).lstrip().lower().startswith(("select", "show", "desc")):
				return native_sql(query, *args, **kwargs)
			return record("sql")(query, *args, **kwargs)

		def stock(args):
			state["complete"] = completed
			return result

		@contextmanager
		def lock_busy(*args, **kwargs):
			raise setup_wizard.LockTimeoutError("setup already running")
			yield

		with ExitStack() as stack:
			stack.enter_context(patch.object(frappe, "only_for"))
			stack.enter_context(patch("frappe.utils.nowdate", return_value="2026-10-16"))
			stack.enter_context(patch.object(frappe, "is_setup_complete", side_effect=lambda: state["complete"]))
			stack.enter_context(patch.object(frappe, "get_installed_apps", return_value=["frappe", "erpnext", "crm"]))
			for method in ("set_value", "commit", "set_default", "set_single_value"):
				stack.enter_context(patch.object(frappe.db, method, side_effect=record(method)))
			stack.enter_context(patch.object(frappe.db, "sql", side_effect=sql))
			if native_timeout:
				stack.enter_context(patch.object(setup_wizard, "filelock", lock_busy))
			else:
				stack.enter_context(patch.object(setup_wizard, "setup_complete", side_effect=stock))
			try:
				response = setup_guard.autocomplete_setup("Audit Tenant")
			except frappe.ValidationError:
				response = "refused"
		return response, writes

	def assert_no_completion_writes(self, writes):
		self.assertFalse(any(method == "sql" for method, _, _ in writes), "Do not mark installed apps complete")
		self.assertFalse(any(method == "set_single_value" for method, _, _ in writes),
			"Native setup owns the global completion flag")

	def test_native_lock_timeout_is_not_completed_setup(self):
		response, writes = self.invoke(native_timeout=True)
		self.assertEqual(response, "refused")
		self.assert_no_completion_writes(writes)

	def test_failed_pending_or_unknown_results_never_finalize_setup(self):
		for result in ({"status": "fail"}, {"status": "registered"}, {}, None):
			with self.subTest(result=result):
				response, writes = self.invoke(result)
				self.assertEqual(response, "refused")
				self.assert_no_completion_writes(writes)

	def test_ok_without_native_completion_does_not_finalize_setup(self):
		response, writes = self.invoke({"status": "ok"})
		self.assertEqual(response, "refused")
		self.assert_no_completion_writes(writes)

	def test_failed_result_is_not_success_even_if_native_flags_are_set(self):
		response, writes = self.invoke({"status": "fail"}, completed=True)
		self.assertEqual(response, "refused")
		self.assert_no_completion_writes(writes)

	def test_success_preserves_native_completion_and_resume_settings(self):
		response, writes = self.invoke({"status": "ok"}, completed=True)
		self.assertEqual(response, {"status": "completed", "company": "Audit Tenant"})
		self.assert_no_completion_writes(writes)
		settings = next(args[2] for method, args, _ in writes if method == "set_value")
		self.assertEqual((settings["country"], settings["currency"]), ("Philippines", "PHP"))
		self.assertIn(("set_default", ("crm_demo_data_created", "1"), {}), writes)

	def test_already_complete_is_a_noop(self):
		response, writes = self.invoke(already_complete=True)
		self.assertEqual(response, {"status": "already complete"})
		self.assertEqual(writes, [])
