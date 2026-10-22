"""Quota-hook failure policy with a small Frappe adapter, no site required."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Callbacks:
    def __init__(self):
        self.items = []

    def add(self, callback):
        self.items.append(callback)

    def run(self):
        for callback in self.items:
            callback()


class HookFailureTests(unittest.TestCase):
    def setUp(self):
        frappe = ModuleType("frappe")
        frappe._ = lambda value: value
        frappe.conf = {"storage_quota_gb": 1}
        frappe.cache = Mock()
        frappe.log_error = Mock()
        frappe.get_traceback = lambda: "fixture traceback"
        frappe.QueryDeadlockError = type("QueryDeadlockError", (Exception,), {})
        frappe.QueryTimeoutError = type("QueryTimeoutError", (Exception,), {})
        frappe.db = SimpleNamespace(after_commit=Callbacks(), after_rollback=Callbacks(),
                                    is_deadlocked=lambda exc: False, is_timedout=lambda exc: False)
        utils = ModuleType("frappe.utils")
        utils.cint = int
        loader = importlib.util.spec_from_file_location("quota_hook_under_test", Path(__file__).parents[1] / "storage.py")
        self.storage = importlib.util.module_from_spec(loader)
        with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
            loader.loader.exec_module(self.storage)
        self.frappe = frappe
        self.doc = SimpleNamespace(doctype="File", flags={}, file_size=10)

    def test_wrapped_transaction_conflicts_propagate_instead_of_allowing_upload(self):
        for kind in (self.frappe.QueryDeadlockError, self.frappe.QueryTimeoutError):
            error = kind(Exception(1213, "driver error wrapped by Frappe"))
            with self.subTest(kind=kind.__name__), patch.object(self.storage, "check_and_hold", side_effect=error):
                with self.assertRaises(kind):
                    self.storage.enforce_file_quota(self.doc)
        self.frappe.log_error.assert_not_called()

    def test_snapshot_abort_is_reported_as_a_transaction_conflict(self):
        with patch.object(self.storage, "check_and_hold", side_effect=self.storage.QuotaTransactionConflict("snapshot")):
            with self.assertRaises(self.frappe.QueryDeadlockError):
                self.storage.enforce_file_quota(self.doc)
        self.frappe.log_error.assert_not_called()

    def test_cache_and_logging_outages_cannot_stop_later_transaction_callbacks(self):
        self.frappe.cache.delete_value.side_effect = ConnectionError("Redis unavailable")
        self.frappe.log_error.side_effect = ConnectionError("Log service unavailable")
        with patch.object(self.storage, "check_and_hold", return_value=True):
            self.storage.enforce_file_quota(self.doc)
        for callbacks in (self.frappe.db.after_commit, self.frappe.db.after_rollback):
            later = Mock()
            callbacks.add(later)
            callbacks.run()
            later.assert_called_once()

    def test_unexpected_non_transaction_failure_preserves_existing_fail_open_policy(self):
        with patch.object(self.storage, "check_and_hold", side_effect=RuntimeError("fixture")):
            self.storage.enforce_file_quota(self.doc)
        self.frappe.log_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
