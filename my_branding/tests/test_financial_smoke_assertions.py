"""Negative controls for the standalone smoke gate; never execute its transactions."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[2] / "saas" / "financial-smoke-test.py"


def functions(**values):
	tree = ast.parse(SOURCE.read_text())
	namespace = dict(values)
	exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[]), str(SOURCE), "exec"), namespace)
	return namespace


def gate(name, **values):
	tree = ast.parse(SOURCE.read_text())
	node = next(node for node in tree.body if isinstance(node, ast.Assign) and any(
		isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
		and target.value.id == "checks" and isinstance(target.slice, ast.Constant)
		and target.slice.value == name for target in node.targets
	))
	return eval(compile(ast.Expression(node.value), str(SOURCE), "eval"), functions(**values))


def vat_gate(output, input_tax, withholding):
	return gate("vat_ok", ov=output, iv=input_tax, ew=withholding)


class TestFinancialSmokeAssertions(unittest.TestCase):
	def test_exact_synthetic_vat_and_withholding_pass(self):
		self.assertTrue(vat_gate(1200, 1200, 200))

	def test_incorrect_positive_withholding_fails(self):
		for amount in (0.01, 1, 20, 199.99, 200.01, 2000):
			with self.subTest(amount=amount):
				self.assertFalse(vat_gate(1200, 1200, amount))

	def test_one_cent_vat_error_fails(self):
		self.assertFalse(vat_gate(1199.99, 1200, 200))
		self.assertFalse(vat_gate(1200, 1200.01, 200))

	def test_missing_asset_accounts_fail_instead_of_recording_skip_success(self):
		frappe = Mock()
		frappe.get_all.return_value = []
		namespace = functions(frappe=frappe, CO="Synthetic Company")
		with self.assertRaisesRegex(RuntimeError, "asset accounts"):
			namespace["fixed_asset"]()

	def depreciation_proof(self, journal_entry="SYN-JE", submitted=True, gl_amount=100):
		frappe = Mock()
		frappe.utils.getdate.side_effect = lambda value: value
		frappe.db.exists.return_value = submitted
		frappe.db.sql.return_value = [SimpleNamespace(amount=gl_amount)]
		schedule = SimpleNamespace(reload=Mock(), depreciation_schedule=[
			SimpleNamespace(schedule_date="2026-10-16", journal_entry=journal_entry)])
		namespace = functions(frappe=frappe, CO="Synthetic Company", nowdate=lambda: "2026-10-16")
		return namespace["_verify_depreciation_posted"](schedule, 100, "Synthetic Depreciation Account")

	def test_silent_depreciation_noop_fails(self):
		with self.assertRaisesRegex(RuntimeError, "without posting"):
			self.depreciation_proof(journal_entry=None)

	def test_draft_depreciation_journal_fails(self):
		with self.assertRaisesRegex(RuntimeError, "not submitted"):
			self.depreciation_proof(submitted=False)

	def test_missing_or_wrong_depreciation_gl_fails(self):
		for amount in (0, 99, 100.01, 101):
			with self.subTest(amount=amount), self.assertRaisesRegex(RuntimeError, "GL does not equal"):
				self.depreciation_proof(gl_amount=amount)

	def test_submitted_depreciation_with_exact_gl_passes(self):
		self.assertEqual(self.depreciation_proof(), (100, ["SYN-JE"]))

	def test_empty_or_failed_native_reports_fail_gate(self):
		for report in ({}, {"trial_balance_rows": 1}, {"balance_sheet_rows": 1},
			{"trial_balance_rows": 1, "balance_sheet_rows": 1, "trial_balance_error": "synthetic error"},
			{"trial_balance_rows": 1, "balance_sheet_rows": 1, "balance_sheet_error": "synthetic mismatch"}):
			with self.subTest(report=report):
				self.assertFalse(gate("reports_ok", rep=report))

	def test_both_nonempty_validated_reports_pass_gate(self):
		self.assertTrue(gate("reports_ok", rep={"trial_balance_rows": 3, "balance_sheet_rows": 5}))
