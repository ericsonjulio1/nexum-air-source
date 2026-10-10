"""Batch 205 (v205) server fixes in my_branding — sweep group D2.

idx 88   idle_lock.ensure_setup: the two-hour deploy grace is for the first roll-out only.
idx 89   Nexum Invoice (PH): Paid / Amount Due in the party account's currency.
idx 91   Nexum Invoice (PH): a tax included in the price is not added a second time.
idx 92   Home Receivables / Payables: the AR / AP report's ledger (credit notes, advances).
idx 93   coa_guard: the generic VAT leaf stays enabled while a live transaction carries it.
idx 94   Home widgets: their docs ride in boot (server half of the getdoc-wave fix).
idx 95   Nexum Invoice (PH): the seller address the invoice picked, else the primary one.
idx 159  doc caps: an Auto Repeat the Free cap paused resumes after the upgrade.
idx 160  seeded PH holiday list: Sundays are weekly offs (new lists + a patch for untouched ones).
idx 173  Home KPIs: company resolution honours User Permissions.

Unless a test says otherwise, rows are written inside a savepoint and rolled back.
Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_batch205_server
"""

import datetime
import html as html_lib
import re
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from my_branding import coa_guard, doc_caps, home, idle_lock, setup_apps
from my_branding.patches import add_sundays_to_seeded_ph_holiday_lists as sundays_patch

SAVEPOINT = "nx_b205"


@contextmanager
def _savepoint():
	frappe.db.savepoint(SAVEPOINT)
	try:
		yield
	finally:
		frappe.db.rollback(save_point=SAVEPOINT)


def _default_company():
	frappe.set_user("Administrator")
	return home._company()


# --------------------------------------------------------------------------- idx 88
class TestIdleLockDeployGrace(unittest.TestCase):
	SIDS = ("nx-b205-seed-new", "nx-b205-seed-kept")

	def setUp(self):
		for sid in self.SIDS:
			frappe.db.sql(
				"insert into `tabSessions` (sid, user, status, sessiondata, lastupdate) "
				"values (%s, 'Administrator', 'Active', '{}', now())",
				sid,
			)
		idle_lock.mark_activity("nx-b205-seed-kept", at=1_000_000)

	def tearDown(self):
		for sid in self.SIDS:
			frappe.db.delete("Sessions", {"sid": sid})
			frappe.cache.delete_value(idle_lock._KEY.format(sid))
		frappe.db.commit()  # ensure_setup commits, so the rows above must be undone for real

	def test_later_migrates_start_the_count_now(self):
		"""deploy.sh FLUSHALLs right before migrate: a session nobody uses after the deploy
		must go stale idle+150 s later, not two hours later."""
		before = int(time.time())
		with patch.object(idle_lock, "_ready", return_value=True):
			idle_lock.ensure_setup()
		stamped = idle_lock.last_activity("nx-b205-seed-new")
		self.assertIsNotNone(stamped)
		self.assertLessEqual(stamped, int(time.time()) + 1, "a future stamp re-grants the deploy grace")
		self.assertGreaterEqual(stamped, before)
		self.assertEqual(idle_lock.last_activity("nx-b205-seed-kept"), 1_000_000)
		limit = idle_lock.server_limit_seconds()
		self.assertTrue(idle_lock.is_stale("nx-b205-seed-new", now=stamped + limit + 1))

	def test_first_roll_out_keeps_the_grace(self):
		before = int(time.time())
		with patch.object(idle_lock, "_ready", return_value=False), patch.object(
			frappe.db, "set_default"
		) as set_default:
			idle_lock.ensure_setup()
		self.assertGreaterEqual(
			idle_lock.last_activity("nx-b205-seed-new"), before + idle_lock.DEPLOY_GRACE_SECONDS
		)
		self.assertEqual(idle_lock.last_activity("nx-b205-seed-kept"), 1_000_000)
		set_default.assert_called_once_with(idle_lock.READY_DEFAULT, "1")


# --------------------------------------------------------------------------- invoice (89/91/95)
def _template():
	path = frappe.get_app_path(
		"my_branding", "my_branding", "print_format", "nexum_invoice_ph", "nexum_invoice_ph.html"
	)
	with open(path) as f:
		return f.read()


def _render(doc):
	return frappe.render_template(_template(), {"doc": doc})


def _sum_rows(rendered):
	"""[(row class, label, amount)] of the totals table."""
	table = re.search(r'<table class="nxi-sum">(.*?)</table>', rendered, re.S).group(1)
	out = []
	for cls, label, value in re.findall(
		r'<tr(?: class="([^"]*)")?><td>(.*?)</td><td>(.*?)</td></tr>', table, re.S
	):
		text = lambda s: re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", s))).strip()
		out.append((cls, text(label), text(value)))
	return out


def _amount(text):
	"""'- ₱ 1,234.50' or '₱ -1,234.50' -> -1234.5"""
	number = flt(re.sub(r"[^0-9.]", "", text))
	return -number if "-" in text else number


def _invoice(company, taxes=(), discount=None, apply_on="Grand Total", rate=1000, currency=None, conversion_rate=1, party_account_currency=None):
	"""An unsaved Sales Invoice whose totals come from ERPNext's own engine."""
	currency = currency or frappe.get_cached_value("Company", company, "default_currency")
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"company": company,
			"customer_name": "Batch 205 test customer",
			"currency": currency,
			"conversion_rate": conversion_rate,
			"plc_conversion_rate": conversion_rate,
			"price_list_currency": currency,
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"party_account_currency": party_account_currency or currency,
		}
	)
	si.append(
		"items",
		{"item_name": "Design work", "description": "Design work", "qty": 1, "rate": rate, "uom": "Nos", "stock_uom": "Nos", "conversion_factor": 1},
	)
	for t in taxes:
		si.append("taxes", t)
	if discount:
		si.apply_discount_on = apply_on
		si.additional_discount_percentage = discount
	si.calculate_taxes_and_totals()
	return si


def _tax(description, rate, included):
	return {"charge_type": "On Net Total", "account_head": "_nx-b205 tax", "description": description, "rate": rate, "included_in_print_rate": included}


VAT_INCL = _tax("VAT 12%", 12, 1)
VAT_EXCL = _tax("VAT 12%", 12, 0)
SERVICE = _tax("Service charge 10%", 10, 0)


class TestInvoicePHTotals(unittest.TestCase):
	"""idx 91: the printed lines add up to Total in every tax / discount setup."""

	@classmethod
	def setUpClass(cls):
		cls.company = _default_company()
		if not cls.company:
			raise unittest.SkipTest("no Company on this site")

	def assertAddsUp(self, si):
		rows = _sum_rows(_render(si))
		labels = [label for _cls, label, _v in rows]
		grand = [r for r in rows if r[0] == "nxi-grand"]
		self.assertEqual(len(grand), 1, rows)
		before_total = rows[: rows.index(grand[0])]
		self.assertEqual(before_total[0][1], "Subtotal", rows)
		total = sum(_amount(v) for _cls, _label, v in before_total)
		self.assertAlmostEqual(total, _amount(grand[0][2]), places=2, msg=rows)
		# an included tax is information under Total, never part of the sum
		for t in si.taxes:
			if t.included_in_print_rate and t.tax_amount_after_discount_amount:
				self.assertIn("incl. " + t.description, labels, rows)
				self.assertNotIn(t.description, [label for _c, label, _v in before_total], rows)
		return rows

	def test_included_vat_is_not_added_twice(self):
		rows = self.assertAddsUp(_invoice(self.company, [VAT_INCL], rate=1120))
		self.assertEqual(
			[(c, label) for c, label, _v in rows], [("", "Subtotal"), ("nxi-grand", "Total"), ("nxi-incl", "incl. VAT 12%")]
		)
		self.assertEqual(_amount(rows[-1][2]), 120)

	def test_included_vat_with_discounts(self):
		for apply_on in ("Grand Total", "Net Total"):
			with self.subTest(apply_on=apply_on):
				si = _invoice(self.company, [VAT_INCL], discount=10, apply_on=apply_on, rate=1120)
				rows = self.assertAddsUp(si)
				# shown on the VAT-inclusive footing: 10% of the 1,120 subtotal either way
				self.assertEqual(_amount(next(v for _c, label, v in rows if label.startswith("Discount"))), -112)
				self.assertEqual(_amount(rows[-1][2]), si.taxes[0].tax_amount_after_discount_amount)

	def test_included_and_added_taxes_mixed(self):
		for discount, apply_on in ((None, None), (10, "Grand Total"), (10, "Net Total")):
			with self.subTest(discount=discount, apply_on=apply_on):
				self.assertAddsUp(_invoice(self.company, [VAT_INCL, SERVICE], discount=discount, apply_on=apply_on, rate=1120))

	def test_exclusive_vat_prints_as_before(self):
		rows = self.assertAddsUp(_invoice(self.company, [VAT_EXCL]))
		self.assertEqual([(label, _amount(v)) for _c, label, v in rows], [("Subtotal", 1000), ("VAT 12%", 120), ("Total", 1120)])
		rows = self.assertAddsUp(_invoice(self.company, [VAT_EXCL], discount=10, apply_on="Grand Total"))
		self.assertEqual(
			[(label, _amount(v)) for _c, label, v in rows],
			[("Subtotal", 1000), ("Discount (10%)", -112), ("VAT 12%", 120), ("Total", 1008)],
		)
		self.assertAddsUp(_invoice(self.company, [VAT_EXCL], discount=10, apply_on="Net Total"))


class TestInvoicePHAmountDue(unittest.TestCase):
	"""idx 89: outstanding_amount is in the party account's currency."""

	@classmethod
	def setUpClass(cls):
		cls.company = _default_company()
		if not cls.company:
			raise unittest.SkipTest("no Company on this site")
		cls.home_cur = frappe.get_cached_value("Company", cls.company, "default_currency")
		cls.foreign = "USD" if cls.home_cur != "USD" else "EUR"

	def _foreign_invoice(self, outstanding):
		si = _invoice(self.company, rate=100, currency=self.foreign, conversion_rate=56, party_account_currency=self.home_cur)
		si.docstatus = 1
		si.outstanding_amount = outstanding
		return si

	def _due_rows(self, si):
		return [(label, v) for _c, label, v in _sum_rows(_render(si)) if label.startswith(("Paid", "Amount Due"))]

	def test_unpaid_foreign_invoice_shows_no_paid_line(self):
		si = self._foreign_invoice(outstanding=5600)  # base_grand_total: nothing paid
		self.assertEqual(si.base_grand_total, 5600)
		self.assertEqual(self._due_rows(si), [])

	def test_part_paid_foreign_invoice_in_the_receivable_currency(self):
		rows = self._due_rows(self._foreign_invoice(outstanding=2750))
		self.assertEqual([label for label, _v in rows], ["Paid (%s)" % self.home_cur, "Amount Due (%s)" % self.home_cur])
		self.assertEqual([_amount(v) for _label, v in rows], [2850, 2750])

	def test_settled_foreign_invoice_in_the_invoice_currency(self):
		rows = self._due_rows(self._foreign_invoice(outstanding=0))
		self.assertEqual([(label, _amount(v)) for label, v in rows], [("Paid", 100), ("Amount Due", 0)])

	def test_same_currency_part_payment_unchanged(self):
		si = _invoice(self.company, rate=1000)
		si.docstatus = 1
		si.outstanding_amount = 400
		self.assertEqual([(label, _amount(v)) for label, v in self._due_rows(si)], [("Paid", 600), ("Amount Due", 400)])


class TestInvoicePHSellerAddress(unittest.TestCase):
	"""idx 95: the address picked on the invoice, else the primary enabled one."""

	@classmethod
	def setUpClass(cls):
		cls.company = _default_company()
		if not cls.company:
			raise unittest.SkipTest("no Company on this site")

	def _address(self, line, primary=0):
		doc = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": line,
				"address_type": "Office",
				"address_line1": line,
				"city": "Baler",
				"country": "Philippines",
				"is_primary_address": primary,
				"is_your_company_address": 1,
				"links": [{"link_doctype": "Company", "link_name": self.company}],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _printed(self, si):
		return re.search(r'<div class="nxi-addr">(.*?)</div>', _render(si), re.S)

	def test_picks_the_invoice_address_then_the_primary(self):
		with _savepoint():
			# creation order: the primary sits between the site's own address(es) and a newer
			# one, so neither an oldest-first nor a newest-first link lookup lands on it
			primary = self._address("_nx-b205 Primary Office", primary=1)
			time.sleep(0.01)
			chosen = self._address("_nx-b205 Branch Warehouse")
			si = _invoice(self.company)
			si.company_address = chosen
			self.assertIn("_nx-b205 Branch Warehouse", self._printed(si).group(1))
			si.company_address = None
			self.assertIn("_nx-b205 Primary Office", self._printed(si).group(1))
			frappe.db.set_value("Address", primary, "disabled", 1)
			printed = self._printed(si)
			self.assertNotIn("_nx-b205 Primary Office", printed.group(1) if printed else "")


# --------------------------------------------------------------------------- home KPIs (92/173)
def _ple(company, account, account_type, amount, party, party_type=None, voucher_type="Sales Invoice", delinked=0, posting_date=None):
	name = "_nx-b205-" + frappe.generate_hash(length=10)
	values = {
		"name": name,
		"docstatus": 1,
		"company": company,
		"account": account,
		"account_type": account_type,
		"party_type": party_type or ("Customer" if account_type == "Receivable" else "Supplier"),
		"party": party,
		"voucher_type": voucher_type,
		"voucher_no": name,
		"against_voucher_type": voucher_type,
		"against_voucher_no": name,
		"amount": amount,
		"amount_in_account_currency": amount,
		"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
		"posting_date": posting_date or nowdate(),
		"delinked": delinked,
		"creation": frappe.utils.now(),
		"modified": frappe.utils.now(),
		"owner": "Administrator",
		"modified_by": "Administrator",
	}
	frappe.db.sql(
		"INSERT INTO `tabPayment Ledger Entry` ({}) VALUES ({})".format(
			", ".join(f"`{k}`" for k in values), ", ".join(["%s"] * len(values))
		),
		tuple(values.values()),
	)
	return name


def _party_account(company, account_type):
	return frappe.db.get_value("Account", {"company": company, "account_type": account_type, "is_group": 0}, "name")


class TestHomeOpenBalances(unittest.TestCase):
	"""idx 92: the cards net credit notes and unallocated advances like the AR/AP report."""

	@classmethod
	def setUpClass(cls):
		cls.company = _default_company()
		cls.receivable = cls.company and _party_account(cls.company, "Receivable")
		cls.payable = cls.company and _party_account(cls.company, "Payable")
		if not (cls.receivable and cls.payable):
			raise unittest.SkipTest("no receivable/payable account on this site")

	def setUp(self):
		frappe.set_user("Administrator")

	def test_receivables_net_credit_notes_and_advances(self):
		with _savepoint():
			base = home.receivables()["value"]
			c, acc = self.company, self.receivable
			_ple(c, acc, "Receivable", 10000, "_nx-b205 customer")  # invoice
			_ple(c, acc, "Receivable", -10000, "_nx-b205 customer")  # standalone credit note
			_ple(c, acc, "Receivable", -3000, "_nx-b205 customer", voucher_type="Payment Entry")  # unallocated advance
			_ple(c, acc, "Receivable", 5000, "_nx-b205 customer", delinked=1)  # cancelled
			_ple(c, acc, "Receivable", 700, "_nx-b205 employee", party_type="Employee")  # employee advance
			_ple(c, acc, "Receivable", 900, "_nx-b205 customer", posting_date=add_days(nowdate(), 3))  # future
			self.assertAlmostEqual(home.receivables()["value"], base - 3000, places=2)

	def test_payables_net_debit_notes_and_advances(self):
		with _savepoint():
			base = home.payables()["value"]
			c, acc = self.company, self.payable
			_ple(c, acc, "Payable", 4000, "_nx-b205 supplier", voucher_type="Purchase Invoice")  # owed
			_ple(c, acc, "Payable", -1000, "_nx-b205 supplier", voucher_type="Purchase Invoice")  # debit note
			_ple(c, acc, "Payable", -500, "_nx-b205 supplier", voucher_type="Payment Entry")  # advance paid
			self.assertAlmostEqual(home.payables()["value"], base + 2500, places=2)

	def test_receivables_card_matches_the_report_it_opens(self):
		from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute

		card = home.receivables()
		self.assertEqual(card["route"], ["query-report", "Accounts Receivable"])
		result = execute(frappe._dict({"company": self.company, "report_date": nowdate()}))
		data = result[1] if isinstance(result, (list, tuple)) else []
		report_total = sum(flt(r.get("outstanding")) for r in data if isinstance(r, dict))
		self.assertAlmostEqual(card["value"], report_total, places=2)


class TestHomeCompanyFence(unittest.TestCase):
	"""idx 173: a user fenced to some companies / customers never sees anyone else's totals."""

	EMAIL = "nx-b205-fenced@example.com"

	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		companies = frappe.get_all("Company", order_by="creation asc", pluck="name")
		if len(companies) < 3:
			raise unittest.SkipTest("needs three companies")
		cls.oldest, cls.allowed = companies[0], companies[1:3]

	def setUp(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("User", self.EMAIL):
			frappe.delete_doc("User", self.EMAIL, force=True, ignore_permissions=True)
		user = frappe.get_doc(
			{"doctype": "User", "email": self.EMAIL, "first_name": "Fenced", "user_type": "System User", "send_welcome_email": 0}
		)
		user.append("roles", {"role": "Accounts User"})
		user.flags.ignore_permissions = True
		user.insert()
		self.permissions = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self.permissions:
			frappe.delete_doc("User Permission", name, force=True, ignore_permissions=True)
		frappe.delete_doc("User", self.EMAIL, force=True, ignore_permissions=True)
		frappe.db.delete("Payment Ledger Entry", {"name": ["like", "_nx-b205-%"]})
		frappe.db.commit()

	def _fence(self, doctype, value):
		up = frappe.get_doc({"doctype": "User Permission", "user": self.EMAIL, "allow": doctype, "for_value": value, "apply_to_all_doctypes": 1})
		up.insert(ignore_permissions=True)
		self.permissions.append(up.name)
		frappe.clear_cache(user=self.EMAIL)

	def test_fenced_user_gets_a_permitted_company(self):
		for company in self.allowed:
			self._fence("Company", company)
		frappe.set_user(self.EMAIL)
		self.assertIn(home._company(), self.allowed)
		for fn in (home.receivables, home.payables, home.cash_and_bank):
			with self.subTest(fn=fn.__name__):
				self.assertIn(fn()["route_options"]["company"], self.allowed)

	def test_customer_fence_limits_receivables(self):
		receivable = _party_account(self.oldest, "Receivable")
		customers = frappe.get_all("Customer", pluck="name", limit=2, order_by="creation asc")
		if not receivable or len(customers) < 2:
			self.skipTest("needs a receivable account and two customers")
		frappe.db.delete("Payment Ledger Entry", {"name": ["like", "_nx-b205-%"]})
		mine, theirs = customers
		_ple(self.oldest, receivable, "Receivable", 1000, mine)
		_ple(self.oldest, receivable, "Receivable", 2000, theirs)
		self._fence("Company", self.oldest)
		self._fence("Customer", mine)
		expected = flt(
			frappe.db.sql(
				"select sum(amount) from `tabPayment Ledger Entry` where company=%s and party_type='Customer' "
				"and party=%s and delinked=0 and posting_date<=%s",
				(self.oldest, mine, nowdate()),
			)[0][0]
		)
		frappe.set_user(self.EMAIL)
		self.assertAlmostEqual(home.receivables()["value"], expected, places=2)


	def test_a_reader_without_company_read_still_gets_their_default(self):
		"""The fence is User Permissions, not the role's right to open Company: Auditor and
		HR User only have `select` on Company, and some card readers have none at all
		(review of batch 205, finding 4)."""
		# frappe keeps a user's company default under the scrubbed key
		frappe.defaults.set_user_default("company", self.allowed[0], self.EMAIL)
		try:
			frappe.set_user(self.EMAIL)
			with patch.object(frappe, "has_permission", return_value=False):
				self.assertEqual(home._company(), self.allowed[0])
		finally:
			frappe.set_user("Administrator")
			frappe.defaults.clear_user_default("company", self.EMAIL)

	def test_the_ledger_fences_apply_without_ledger_read(self):
		"""The AR/AP reports apply their User Permission match conditions to Purchase and
		Sales users too, and building them needs no read right on Payment Ledger Entry
		(review of batch 205, finding 2)."""
		import erpnext.accounts.utils as accounts_utils

		if not _party_account(self.oldest, "Payable"):
			self.skipTest("needs a payable account")
		real, calls = accounts_utils.build_qb_match_conditions, []

		def spy(doctype, user=None):
			calls.append(doctype)
			return real(doctype, user)

		frappe.set_user(self.EMAIL)
		with patch.object(accounts_utils, "build_qb_match_conditions", spy), patch.object(
			frappe, "has_permission", return_value=False
		):
			home._open_balance("Payable", self.oldest)
		self.assertEqual(calls, ["Payment Ledger Entry"])


# --------------------------------------------------------------------------- idx 94
class TestHomeWidgetBoot(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		home.reconcile_home_workspace()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_hook_is_wired(self):
		self.assertIn("my_branding.home.boot_widget_docs", frappe.get_hooks("extend_bootinfo"))

	def test_boot_carries_the_widget_docs(self):
		boot = frappe._dict()
		home.boot_widget_docs(boot)
		names = {(d["doctype"], d["name"]) for d in boot.nx_widget_docs}
		for label, method, _dt in home.NUMBER_CARDS:
			self.assertIn(("Number Card", label), names)
		self.assertIn(("Custom HTML Block", home.HOME_BLOCK), names)
		card = next(d for d in boot.nx_widget_docs if d["name"] == home.NUMBER_CARDS[0][0])
		self.assertEqual(card["method"], home.NUMBER_CARDS[0][1])  # what NumberCardWidget reads

	def test_only_docs_the_user_may_read(self):
		frappe.set_user("Guest")
		boot = frappe._dict()
		home.boot_widget_docs(boot)
		self.assertEqual(boot.nx_widget_docs, [])


# --------------------------------------------------------------------------- idx 93
class TestGenericVatParking(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		for company in frappe.get_all("Company", pluck="name"):
			abbr = frappe.get_cached_value("Company", company, "abbr")
			generic = frappe.db.get_value("Account", {"company": company, "name": "VAT - %s" % abbr, "is_group": 0}, "name")
			if (
				generic
				and coa_guard._leaf(company, "1611 - VAT Input Tax - Goods")
				and coa_guard._leaf(company, "2201 - VAT Output Tax")
				and not frappe.db.count("GL Entry", {"account": generic})
			):
				cls.company, cls.generic = company, generic
				return
		raise unittest.SkipTest("no PH-chart company with an unused generic VAT account")

	def _row(self, child_dt, parenttype, docstatus):
		frappe.db.sql(
			"INSERT INTO `tab{}` (name, parent, parenttype, parentfield, docstatus, account_head, charge_type, rate, idx) "
			"VALUES (%s, %s, %s, 'taxes', %s, %s, 'On Net Total', 12, 1)".format(child_dt),
			("_nx-b205-" + frappe.generate_hash(length=10), "_nx-b205-parent", parenttype, docstatus, self.generic),
		)

	def _disabled(self):
		return frappe.db.get_value("Account", self.generic, "disabled")

	def test_kept_enabled_while_an_order_or_draft_carries_it(self):
		for child_dt, parenttype, docstatus in (
			("Sales Taxes and Charges", "Sales Order", 1),
			("Purchase Taxes and Charges", "Purchase Order", 1),
			("Sales Taxes and Charges", "Quotation", 1),
			("Purchase Taxes and Charges", "Purchase Invoice", 0),
		):
			with self.subTest(parenttype=parenttype), _savepoint():
				frappe.db.set_value("Account", self.generic, "disabled", 0)
				self._row(child_dt, parenttype, docstatus)
				coa_guard._fix_company(self.company)
				self.assertFalse(self._disabled())

	def test_parked_once_only_cancelled_documents_carry_it(self):
		with _savepoint():
			frappe.db.set_value("Account", self.generic, "disabled", 0)
			self._row("Sales Taxes and Charges", "Sales Order", 2)
			coa_guard._fix_company(self.company)
			self.assertTrue(self._disabled())


# --------------------------------------------------------------------------- idx 159
@contextmanager
def _caps(**caps):
	old = frappe.conf.get("nexum_doc_caps")
	if caps:
		frappe.conf.nexum_doc_caps = caps
	else:
		frappe.conf.pop("nexum_doc_caps", None)
	try:
		yield
	finally:
		if old is None:
			frappe.conf.pop("nexum_doc_caps", None)
		else:
			frappe.conf.nexum_doc_caps = old


class TestAutoRepeatCapPause(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.reference = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "name")
		if not cls.reference:
			raise unittest.SkipTest("no submitted Sales Invoice to repeat")

	def setUp(self):
		frappe.db.savepoint(SAVEPOINT)
		self.ar = frappe.get_doc(
			{
				"doctype": "Auto Repeat",
				"reference_doctype": "Sales Invoice",
				"reference_document": self.reference,
				"frequency": "Monthly",
				"start_date": nowdate(),
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback(save_point=SAVEPOINT)

	def _refuse(self):
		"""What the scheduler does: insert the recurring copy, refused at the cap, then
		AutoRepeat.disable_auto_repeat()."""
		copy = frappe.copy_doc(frappe.get_doc("Sales Invoice", self.reference))
		copy.flags.updater_reference = {"doctype": "Auto Repeat", "docname": self.ar.name, "label": "via Auto Repeat"}
		with _caps(**{"Sales Invoice": doc_caps._count("Sales Invoice")}):
			with self.assertRaises(frappe.ValidationError) as caught:
				doc_caps.enforce_doc_cap(copy)
		frappe.db.set_value("Auto Repeat", self.ar.name, "disabled", 1)
		return str(caught.exception)

	def _notes(self, prefix):
		return frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Auto Repeat", "reference_name": self.ar.name, "content": ["like", prefix + "%"]},
			pluck="content",
		)

	def test_refusal_names_the_schedule_and_leaves_a_note(self):
		message = self._refuse()
		self.assertIn("Free plan", message)
		self.assertIn(self.ar.name, message)
		self.assertEqual(len(self._notes(doc_caps._PAUSED_NOTE)), 1)

	def test_resumes_once_the_cap_is_lifted(self):
		self._refuse()
		with _caps(**{"Sales Invoice": 50}):
			doc_caps.resume_capped_auto_repeats()
		self.assertEqual(frappe.db.get_value("Auto Repeat", self.ar.name, "disabled"), 1, "still capped")
		with _caps():
			doc_caps.resume_capped_auto_repeats()
		self.assertEqual(frappe.db.get_value("Auto Repeat", self.ar.name, "disabled"), 0)
		self.assertEqual(len(self._notes(doc_caps._RESUMED_NOTE)), 1)
		with _caps():
			doc_caps.resume_capped_auto_repeats()  # idempotent
		self.assertEqual(len(self._notes(doc_caps._RESUMED_NOTE)), 1)

	def test_a_resume_never_lands_on_a_date_the_daily_run_has_passed(self):
		"""save() picks the first due date ON or after today, but frappe's daily run only
		creates a document dated exactly today and never moves a past date on, so a Daily
		schedule resumed after today's run would sit on today and stay idle for good
		(review of batch 205, finding 1)."""
		frappe.db.set_value("Auto Repeat", self.ar.name, {"frequency": "Daily", "start_date": add_days(nowdate(), -5)})
		self._refuse()
		with _caps():
			doc_caps.resume_capped_auto_repeats()
		self.assertEqual(frappe.db.get_value("Auto Repeat", self.ar.name, "disabled"), 0)
		self.assertGreater(
			getdate(frappe.db.get_value("Auto Repeat", self.ar.name, "next_schedule_date")), getdate(nowdate())
		)

	def test_a_schedule_handled_by_hand_is_left_alone(self):
		self._refuse()
		later = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=1)
		frappe.db.set_value("Auto Repeat", self.ar.name, "modified", later, update_modified=False)
		with _caps():
			doc_caps.resume_capped_auto_repeats()
		self.assertEqual(frappe.db.get_value("Auto Repeat", self.ar.name, "disabled"), 1)

	def test_other_failures_are_not_resumed(self):
		frappe.db.set_value("Auto Repeat", self.ar.name, "disabled", 1)
		with _caps():
			doc_caps.resume_capped_auto_repeats()
		self.assertEqual(frappe.db.get_value("Auto Repeat", self.ar.name, "disabled"), 1)


# --------------------------------------------------------------------------- idx 160
def _sundays(year):
	day = datetime.date(year, 1, 1)
	day += datetime.timedelta(days=(6 - day.weekday()) % 7)
	out = []
	while day.year == year:
		out.append(day)
		day += datetime.timedelta(days=7)
	return out


class TestPhHolidayListSundays(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")  # run() and the heal patch save as Administrator

	def test_new_list_has_every_sunday(self):
		year = 2031
		doc = setup_apps._new_ph_holiday_list("Philippines %d" % year, year)
		named = dict(setup_apps._ph_holidays(year))
		rows = {str(getdate(r.holiday_date)): r for r in doc.holidays}
		for sunday in _sundays(year):
			row = rows[str(sunday)]
			if str(sunday) in named:
				self.assertEqual((row.description, cint(row.weekly_off)), (named[str(sunday)], 0))
			else:
				self.assertEqual(cint(row.weekly_off), 1)
		for date, description in named.items():
			self.assertEqual(rows[date].description, description)
		self.assertEqual(len(doc.holidays), len(set(named) | {str(d) for d in _sundays(year)}))

	def _seed_as_before(self, year, extra_row=False, weekly_off="Sunday", sunday_rows=False):
		"""A list in the shape the old run() seeded: named holidays only."""
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Philippines %d" % year,
				"from_date": "%d-01-01" % year,
				"to_date": "%d-12-31" % year,
				"weekly_off": weekly_off,
			}
		)
		for d, desc in setup_apps._ph_holidays(year):
			doc.append("holidays", {"holiday_date": d, "description": desc})
		if extra_row:
			doc.append("holidays", {"holiday_date": "%d-03-03" % year, "description": "Company anniversary"})
		if sunday_rows:
			doc.get_weekly_off_dates()
		doc.insert(ignore_permissions=True)
		return doc.name

	def _weekly_offs(self, name):
		return frappe.db.count("Holiday", {"parent": name, "weekly_off": 1})

	def test_patch_fixes_only_untouched_lists(self):
		with _savepoint():
			untouched = self._seed_as_before(2032)
			edited = self._seed_as_before(2033, extra_row=True)
			saved_by_tenant = self._seed_as_before(2034)
			frappe.db.set_value("Holiday List", saved_by_tenant, "modified_by", "nx-b205@example.com", update_modified=False)
			other_weekly_off = self._seed_as_before(2035, weekly_off="Saturday")
			before = {n: frappe.db.count("Holiday", {"parent": n}) for n in (edited, saved_by_tenant, other_weekly_off)}

			sundays_patch.execute()

			self.assertEqual(self._weekly_offs(untouched), len([d for d in _sundays(2032) if str(d) not in dict(setup_apps._ph_holidays(2032))]))
			self.assertEqual(
				frappe.db.get_value("Holiday List", untouched, "total_holidays"), frappe.db.count("Holiday", {"parent": untouched})
			)
			for name, rows in before.items():
				self.assertEqual(frappe.db.count("Holiday", {"parent": name}), rows, name)
				self.assertEqual(self._weekly_offs(name), 0, name)

			# idempotent: a second run (or a re-run migrate) changes nothing
			rows = frappe.db.count("Holiday", {"parent": untouched})
			sundays_patch.execute()
			self.assertEqual(frappe.db.count("Holiday", {"parent": untouched}), rows)

	def test_patch_leaves_a_list_whose_sundays_were_added_by_hand(self):
		with _savepoint():
			name = self._seed_as_before(2036, sunday_rows=True)
			rows = frappe.db.count("Holiday", {"parent": name})
			sundays_patch.execute()
			self.assertEqual(frappe.db.count("Holiday", {"parent": name}), rows)

	def test_patch_is_registered_after_the_2026_heal(self):
		path = frappe.get_app_path("my_branding", "patches.txt")
		with open(path) as f:
			lines = [line.strip() for line in f if line.strip() and not line.startswith(("#", "["))]
		self.assertLess(
			lines.index("my_branding.patches.heal_ph_holiday_list_2026"),
			lines.index("my_branding.patches.add_sundays_to_seeded_ph_holiday_lists"),
		)
