"""COA migration preserves native invoice item-tax overrides (synthetic, rolled back)."""

import unittest
import uuid

import frappe
from frappe.utils import nowdate

from my_branding.coa_guard import _repoint_tax_templates


class TestCOATaxOverrides(unittest.TestCase):

	def setUp(self):
		self.savepoint = "nx215_coa_" + uuid.uuid4().hex[:12]
		frappe.db.savepoint(self.savepoint)
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			self.skipTest("requires an isolated test company")
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.prefix = "NX215 " + uuid.uuid4().hex[:10]
		parent = frappe.db.get_value("Account", {"company": self.company, "is_group": 1, "root_type": "Liability"}, "name")
		self.accounts = {}
		for kind in ("generic", "input", "output", "other"):
			account = frappe.get_doc({
				"doctype": "Account", "account_name": self.prefix + " " + kind,
				"company": self.company, "parent_account": parent, "account_type": "Tax",
			}).insert(ignore_permissions=True)
			self.accounts[kind] = account.name
		self.purchase_template = frappe.get_doc({
			"doctype": "Purchase Taxes and Charges Template", "title": self.prefix,
			"company": self.company, "taxes": [{"charge_type": "On Net Total",
				"account_head": self.accounts["generic"], "rate": 12, "description": "Synthetic VAT"}],
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)

	def migrate(self, rows):
		template = frappe.get_doc({
			"doctype": "Item Tax Template", "title": self.prefix,
			"company": self.company, "taxes": [
				{"tax_type": self.accounts[kind], "tax_rate": rate, "not_applicable": flag}
				for kind, rate, flag in rows
			],
		}).insert(ignore_permissions=True)
		_repoint_tax_templates(self.company, self.accounts["input"], self.accounts["output"], self.accounts["generic"])
		template.reload()
		return template

	def purchase_tax(self, item_template):
		"""Use persisted migrated templates, native item lookup and native PI totals."""
		from erpnext.stock.get_item_details import get_item_tax_map

		self.purchase_template.reload()
		invoice = frappe.new_doc("Purchase Invoice")
		invoice.update({"company": self.company, "currency": self.currency,
			"conversion_rate": 1, "plc_conversion_rate": 1, "price_list_currency": self.currency,
			"posting_date": nowdate(), "due_date": nowdate(), "party_account_currency": self.currency})
		for row in self.purchase_template.taxes:
			invoice.append("taxes", {"charge_type": row.charge_type, "account_head": row.account_head,
				"rate": row.rate, "description": row.description})
		invoice.append("items", {"item_name": "Synthetic exempt service", "qty": 1, "rate": 1000,
			"uom": "Nos", "stock_uom": "Nos", "conversion_factor": 1,
			"item_tax_template": item_template.name,
			"item_tax_rate": get_item_tax_map(doc=invoice, tax_template=item_template.name)})
		invoice.calculate_taxes_and_totals()
		return invoice.total_taxes_and_charges

	def test_zero_rate_stays_zero_on_native_purchase_invoice(self):
		template = self.migrate([("generic", 0, 0)])
		self.assertEqual(self.purchase_tax(template), 0)

	def test_not_applicable_stays_excluded_on_native_purchase_invoice(self):
		template = self.migrate([("generic", 0, 1)])
		self.assertEqual(self.purchase_tax(template), 0)
		for kind in ("input", "output"):
			row = next(row for row in template.taxes if row.tax_type == self.accounts[kind])
			self.assertEqual(row.not_applicable, 1)

	def test_taxable_rate_is_preserved_on_native_purchase_invoice(self):
		template = self.migrate([("generic", 7.5, 0)])
		self.assertEqual(self.purchase_tax(template), 75)

	def test_explicit_input_rate_and_unrelated_tax_are_preserved(self):
		template = self.migrate([("generic", 0, 0), ("input", 5, 0), ("other", 3, 0)])
		rates = {row.tax_type: row.tax_rate for row in template.taxes}
		self.assertEqual(rates[self.accounts["input"]], 5)
		self.assertEqual(rates[self.accounts["other"]], 3)
		self.assertEqual(rates[self.accounts["output"]], 0)
		self.assertEqual(self.purchase_tax(template), 50)

	def test_explicit_output_rate_is_preserved_without_duplicate_rows(self):
		template = self.migrate([("generic", 0, 0), ("output", 7, 0), ("other", 3, 0)])
		rates = {row.tax_type: row.tax_rate for row in template.taxes}
		self.assertEqual(len(rates), len(template.taxes))
		self.assertEqual(rates[self.accounts["output"]], 7)
		self.assertEqual(rates[self.accounts["other"]], 3)
		self.assertEqual(self.purchase_tax(template), 0)

	def test_repeated_migration_preserves_explicit_overrides(self):
		template = self.migrate([("generic", 0, 0), ("input", 5, 1), ("output", 7, 0)])
		before = [(r.tax_type, r.tax_rate, r.not_applicable) for r in template.taxes]
		_repoint_tax_templates(self.company, self.accounts["input"], self.accounts["output"], self.accounts["generic"])
		template.reload()
		self.assertEqual([(r.tax_type, r.tax_rate, r.not_applicable) for r in template.taxes], before)
