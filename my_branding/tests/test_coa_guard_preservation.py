"""Account cleanup must not damage drafts/defaults; company failures are atomic."""

import copy
import unittest
from unittest.mock import Mock, patch

from my_branding import coa_guard


class TestCOAGuardPreservation(unittest.TestCase):
	def test_existing_demo_and_generic_accounts_are_not_deleted_or_disabled(self):
		db = Mock()
		db.count.return_value = 0
		db.exists.return_value = False
		def value(doctype, name, field):
			if doctype == "Company":
				return "SYN" if field == "abbr" else None
			if isinstance(name, dict):
				return None if name.get("account_name") == "Inventory in Transit" else "existing account"
			return 0
		db.get_value.side_effect = value
		delete = Mock()
		with patch.object(coa_guard.frappe, "db", db), patch.object(coa_guard.frappe, "delete_doc", delete), \
			patch.object(coa_guard, "_leaf", side_effect=lambda company, prefix: None if prefix.startswith(("2101", "1532")) else prefix), \
			patch.object(coa_guard, "_repoint_tax_templates"):
			coa_guard._fix_company("Synthetic Company")
		delete.assert_not_called()
		db.set_value.assert_not_called()

	def test_transit_used_as_stock_adjustment_default_keeps_its_type(self):
		db = Mock()
		def value(doctype, name, field):
			if doctype == "Company":
				return "transit" if field == "stock_adjustment_account" else None
			if isinstance(name, dict):
				return "transit" if name.get("account_name") == "Inventory in Transit" else None
			return "Stock Adjustment" if field == "account_type" else None
		db.get_value.side_effect = value
		with patch.object(coa_guard.frappe, "db", db), patch.object(coa_guard, "_leaf", return_value=None):
			coa_guard._fix_company("Synthetic Company")
		db.set_value.assert_not_called()

	def test_failed_company_rolls_back_its_earlier_writes_and_next_company_proceeds(self):
		state = {"failed": "original", "healthy": "original"}
		snapshot = {}
		db = Mock()
		def savepoint(name):
			snapshot.clear()
			snapshot.update(copy.deepcopy(state))
		def rollback(**kwargs):
			state.clear()
			state.update(snapshot)
		def fix(company):
			state[company] = "changed"
			if company == "failed":
				raise ValueError("synthetic template validation error")
		db.savepoint.side_effect = savepoint
		db.rollback.side_effect = rollback
		with patch.object(coa_guard.frappe, "db", db), \
			patch.object(coa_guard.frappe, "get_all", return_value=["failed", "healthy"]), \
			patch.object(coa_guard.frappe, "get_traceback", return_value="synthetic failure"), \
			patch.object(coa_guard.frappe, "log_error") as log, patch.object(coa_guard, "_fix_company", side_effect=fix):
			coa_guard.reconcile_ph_coa_defaults()
		self.assertEqual(state, {"failed": "original", "healthy": "changed"})
		db.rollback.assert_called_once_with(save_point="nx_coa_company")
		self.assertEqual(db.commit.call_count, 2)
		log.assert_called_once()

	def test_unexpected_savepoint_failure_does_not_silently_rollback_other_hooks(self):
		db = Mock()
		db.rollback.side_effect = RuntimeError("synthetic savepoint failure")
		with patch.object(coa_guard.frappe, "db", db), \
			patch.object(coa_guard.frappe, "get_all", return_value=["failed", "healthy"]), \
			patch.object(coa_guard.frappe, "get_traceback", return_value="synthetic failure"), \
			patch.object(coa_guard.frappe, "log_error") as log, \
			patch.object(coa_guard, "_fix_company", side_effect=ValueError("validation error")) as fix:
			with self.assertRaisesRegex(RuntimeError, "savepoint failure"):
				coa_guard.reconcile_ph_coa_defaults()
		db.rollback.assert_called_once_with(save_point="nx_coa_company")
		db.commit.assert_not_called()
		log.assert_not_called()
		fix.assert_called_once_with("failed")

	def test_transaction_loss_after_deadlock_or_timeout_allows_full_rollback(self):
		for error in (coa_guard.frappe.QueryDeadlockError, coa_guard.frappe.QueryTimeoutError):
			with self.subTest(error=error.__name__):
				db = Mock()
				db.rollback.side_effect = [RuntimeError("savepoint already lost"), None]
				with patch.object(coa_guard.frappe, "db", db), \
					patch.object(coa_guard.frappe, "get_all", return_value=["failed"]), \
					patch.object(coa_guard.frappe, "get_traceback", return_value="synthetic database failure"), \
					patch.object(coa_guard.frappe, "log_error") as log, \
					patch.object(coa_guard, "_fix_company", side_effect=error("synthetic transaction loss")):
					coa_guard.reconcile_ph_coa_defaults()
				self.assertEqual(db.rollback.call_count, 2)
				self.assertEqual(db.rollback.call_args_list[0].kwargs, {"save_point": "nx_coa_company"})
				self.assertEqual(db.rollback.call_args_list[1].kwargs, {})
				db.commit.assert_called_once_with()
				log.assert_called_once()
