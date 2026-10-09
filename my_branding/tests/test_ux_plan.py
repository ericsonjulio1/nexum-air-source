"""UX plan 2026-08-23 (steps 1-4) — integration tests on a bench site.

Run via:  bench --site <site> run-tests --module my_branding.tests.test_ux_plan
"""
import json
import unittest

import frappe

from my_branding import home, plan, simple_mode


class _ConfPlan:
	"""Temporarily force frappe.conf.nexum_plan."""

	def __init__(self, value):
		self.value = value

	def __enter__(self):
		self.old = frappe.conf.get("nexum_plan")
		frappe.conf.nexum_plan = self.value
		return self

	def __exit__(self, *a):
		if self.old is None:
			frappe.conf.pop("nexum_plan", None)
		else:
			frappe.conf.nexum_plan = self.old


class TestPlan(unittest.TestCase):
	def test_conf_plan_wins(self):
		with _ConfPlan("starter"):
			self.assertEqual(plan.get_plan(), "starter")
			self.assertTrue(plan.is_simple_plan())
		with _ConfPlan("business"):
			self.assertFalse(plan.is_simple_plan())

	def test_inferred_plan_is_a_known_slug(self):
		with _ConfPlan(""):
			self.assertIn(plan.get_plan(), plan.PLANS)

	def test_advanced_toggle_per_user(self):
		with _ConfPlan("free"):
			plan.set_advanced_fields(0)
			self.assertEqual(plan.simple_mode_for_session(), 1)
			plan.set_advanced_fields(1)
			self.assertEqual(plan.simple_mode_for_session(), 0)
			plan.set_advanced_fields(0)
			self.assertEqual(plan.simple_mode_for_session(), 1)


class TestSimpleMode(unittest.TestCase):
	def _ps(self, dt, f, prop):
		return frappe.db.get_value("Property Setter", f"{dt}-{f}-{prop}", ["value", "is_system_generated"], as_dict=True)

	def test_apply_then_remove_is_clean(self):
		with _ConfPlan("starter"):
			simple_mode.reconcile_simple_mode()
			row = self._ps("Sales Invoice", "is_return", "depends_on")
			self.assertIsNotNone(row)
			self.assertIn("!frappe.boot.nx_simple_mode", row.value)
			# original depends_on preserved inside the gate
			self.assertIn("!doc.is_debit_note", row.value)
			self.assertEqual(row.is_system_generated, 1)
			self.assertEqual(self._ps("Sales Invoice Item", "warehouse", "in_list_view").value, "0")
			# meta reflects it
			df = frappe.get_meta("Sales Invoice").get_field("is_return")
			self.assertIn("nx_simple_mode", df.depends_on)
			# idempotent: second run changes nothing
			self.assertFalse(simple_mode.apply_simple_mode())
		with _ConfPlan("business"):
			simple_mode.reconcile_simple_mode()
			self.assertIsNone(self._ps("Sales Invoice", "is_return", "depends_on"))
			self.assertIsNone(self._ps("Sales Invoice Item", "warehouse", "in_list_view"))
			df = frappe.get_meta("Sales Invoice").get_field("is_return")
			self.assertNotIn("nx_simple_mode", df.depends_on or "")

	def test_human_customisation_is_respected(self):
		with _ConfPlan("business"):
			simple_mode.reconcile_simple_mode()
		frappe.make_property_setter(
			{"doctype": "Sales Invoice", "fieldname": "incoterm", "property": "depends_on", "value": "eval:doc.customer", "property_type": "Data"},
			validate_fields_for_doctype=False,
			is_system_generated=False,
		)
		try:
			with _ConfPlan("starter"):
				simple_mode.reconcile_simple_mode()
				self.assertEqual(self._ps("Sales Invoice", "incoterm", "depends_on").value, "eval:doc.customer")
			with _ConfPlan("business"):
				simple_mode.reconcile_simple_mode()
				# the human one survives an upgrade too
				self.assertEqual(self._ps("Sales Invoice", "incoterm", "depends_on").value, "eval:doc.customer")
		finally:
			frappe.delete_doc("Property Setter", "Sales Invoice-incoterm-depends_on", force=True, ignore_permissions=True)
			frappe.clear_cache(doctype="Sales Invoice")

	def test_boot_payload(self):
		b = frappe._dict()
		with _ConfPlan("free"):
			plan.set_advanced_fields(0)
			simple_mode.boot(b)
		self.assertEqual(b.nx_plan, "free")
		self.assertEqual(b.nx_simple_plan, 1)
		self.assertEqual(b.nx_simple_mode, 1)


class TestHomeWorkspace(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		home.reconcile_home_workspace()

	def test_blocks_and_cards_exist(self):
		self.assertTrue(frappe.db.exists("Custom HTML Block", home.HOME_BLOCK))
		for k, (_ws, block) in home.MODULE_BLOCKS.items():
			if home.module_workspace(k):
				self.assertTrue(frappe.db.exists("Custom HTML Block", block), block)
		for label, method, doctype in home.NUMBER_CARDS:
			nc = frappe.get_doc("Number Card", label)
			self.assertEqual(nc.type, "Custom")
			self.assertEqual(nc.method, method)
			self.assertEqual(nc.document_type, doctype)

	def test_home_content_starts_with_panel_and_kpi_row(self):
		content = json.loads(frappe.db.get_value("Workspace", "Home", "content"))
		self.assertEqual(content[0]["type"], "custom_block")
		self.assertEqual(content[0]["data"]["custom_block_name"], home.HOME_BLOCK)
		cards = [b["data"]["number_card_name"] for b in content[1:4]]
		self.assertEqual(cards, [n for n, _m, _d in home.NUMBER_CARDS])
		ws = frappe.get_doc("Workspace", "Home")
		self.assertIn(home.HOME_BLOCK, [r.custom_block_name for r in ws.custom_blocks])
		self.assertEqual(len([r for r in ws.number_cards if r.number_card_name in cards]), 3)
		# the rest of the stock Home survived
		self.assertTrue(any(b["type"] == "shortcut" for b in content))

	def test_module_workspaces_start_with_panel(self):
		for key, (_c, block) in home.MODULE_BLOCKS.items():
			ws_name = home.module_workspace(key)
			if not ws_name:
				continue
			content = json.loads(frappe.db.get_value("Workspace", ws_name, "content"))
			self.assertEqual(content[0]["type"], "custom_block", ws_name)
			self.assertEqual(content[0]["data"]["custom_block_name"], block)

	def test_reconcile_is_idempotent(self):
		before = frappe.db.get_value("Workspace", "Home", "modified")
		home.reconcile_home_workspace()
		self.assertEqual(frappe.db.get_value("Workspace", "Home", "modified"), before)

	def test_self_heals_when_block_is_removed(self):
		ws = frappe.get_doc("Workspace", "Home")
		content = json.loads(ws.content)
		ws.content = json.dumps([b for b in content if b.get("type") != "custom_block"])
		ws.flags.ignore_permissions = True
		ws.save()
		home.reconcile_home_workspace()
		content = json.loads(frappe.db.get_value("Workspace", "Home", "content"))
		self.assertEqual(content[0]["data"]["custom_block_name"], home.HOME_BLOCK)

	def test_checklist_api_shapes(self):
		with _ConfPlan("starter"):
			self._shapes()

	def _shapes(self):
		for name in ("home", "accounts", "selling", "stock"):
			d = home.get_checklist(name)
			self.assertEqual(d["name"], name)
			self.assertGreaterEqual(d["total"], 3)
			for s in d["steps"]:
				self.assertIn(s["kind"], ("exists", "visit"))
				self.assertIsInstance(s["route"], list)
		self.assertRaises(frappe.ValidationError, home.get_checklist, "nope")

	def test_visit_and_hide_are_per_user_and_reversible(self):
		with _ConfPlan("starter"):
			self._visit_hide()

	def _visit_hide(self):
		home.mark_visited("accounts", "coa")
		d = home.get_checklist("accounts")
		self.assertTrue(next(s for s in d["steps"] if s["key"] == "coa")["done"])
		home.hide_checklist("stock")
		self.assertEqual(home.get_checklist("stock")["hidden"], 1)
		home.show_checklist("stock")
		self.assertEqual(home.get_checklist("stock")["hidden"], 0)
		frappe.defaults.clear_user_default("nx_ck:accounts:coa")

	def test_panels_off_for_mature_enterprise_sites(self):
		with _ConfPlan("enterprise"):
			# dev/test sites are older than 45 days -> hidden; override re-enables
			old = frappe.conf.get("nx_setup_panels")
			try:
				frappe.conf.pop("nx_setup_panels", None)
				created = frappe.db.get_value("Company", {}, "creation", order_by="creation asc")
				from frappe.utils import date_diff, nowdate
				mature = created and date_diff(nowdate(), created) > home._MATURE_DAYS
				self.assertEqual(home.panels_enabled_for_site(), not mature)
				frappe.conf.nx_setup_panels = 1
				self.assertTrue(home.panels_enabled_for_site())
				self.assertEqual(home.get_checklist("home")["hidden"], 0)
				frappe.conf.nx_setup_panels = 0
				self.assertEqual(home.get_checklist("home")["hidden"], 1)
			finally:
				frappe.conf.pop("nx_setup_panels", None)
				if old is not None:
					frappe.conf.nx_setup_panels = old
		with _ConfPlan("starter"):
			self.assertTrue(home.panels_enabled_for_site())

	def test_boot_flags_agree_with_get_checklist(self):
		"""brand.js skips the get_checklist call when boot says hidden, so the two must
		never disagree — in either direction, across plan, override and per-user hide."""
		old = frappe.conf.get("nx_setup_panels")
		try:
			for plan_slug, override in (("starter", None), ("enterprise", 0), ("enterprise", 1)):
				with _ConfPlan(plan_slug):
					if override is None:
						frappe.conf.pop("nx_setup_panels", None)
					else:
						frappe.conf.nx_setup_panels = override
					home.hide_checklist("selling")
					try:
						boot = home.checklist_boot()
						for name in home.CHECKLIST_NAMES:
							with self.subTest(plan=plan_slug, override=override, name=name):
								self.assertEqual(name in boot["hidden"], bool(home.get_checklist(name)["hidden"]))
					finally:
						home.show_checklist("selling")
		finally:
			frappe.conf.pop("nx_setup_panels", None)
			if old is not None:
				frappe.conf.nx_setup_panels = old

	def test_get_checklist_runs_only_the_requested_checks(self):
		"""Each step's done check is lazy: asking for one checklist must not query the
		tables behind the other three (Quotation is only on Selling)."""
		from unittest import mock

		with _ConfPlan("starter"), mock.patch.object(home, "_exists", wraps=home._exists) as probe:
			home.get_checklist("home")
		self.assertFalse([c for c in probe.call_args_list if c.args and c.args[0] in ("Quotation", "Delivery Note")])

	def test_number_card_methods(self):
		for fn in (home.receivables, home.payables, home.cash_and_bank):
			r = fn()
			self.assertEqual(r["fieldtype"], "Currency")
			self.assertIsInstance(r["value"], float)
			self.assertEqual(r["route"][0], "query-report")

	def test_number_card_methods_need_read_permission(self):
		frappe.set_user("Guest")
		try:
			for fn in (home.receivables, home.payables, home.cash_and_bank):
				self.assertRaises(frappe.PermissionError, fn)
		finally:
			frappe.set_user("Administrator")


class TestHomeTileAndLanding(unittest.TestCase):
	def test_home_desktop_icon_visible_under_erpnext(self):
		from my_branding import branding

		frappe.db.set_value("Desktop Icon", "Home", {"hidden": 1, "parent_icon": ""}, update_modified=False)
		branding.ensure_home_desktop_icon()
		row = frappe.db.get_value("Desktop Icon", "Home", ["hidden", "parent_icon", "app"], as_dict=True)
		self.assertEqual(row.hidden, 0)
		self.assertEqual(row.app, "my_branding")
		import os
		self.assertTrue(os.path.exists(os.path.join(frappe.get_app_path("my_branding"), "public", "icons", "desktop_icons", "solid", "home.svg")))
		self.assertEqual(row.parent_icon, frappe.db.get_value("Desktop Icon", {"icon_type": "App", "app": "erpnext"}, "name"))
		self.assertEqual(branding.LAUNCHER_SECTIONS[0]["labels"], ["Home"])
		first = frappe.get_all("Workspace Sidebar Item", filters={"parent": "Home", "parenttype": "Workspace Sidebar"}, fields=["link_type", "link_to"], order_by="idx asc", limit=1)
		self.assertEqual((first[0].link_type, first[0].link_to), ("Workspace", "Home"))

	def test_owner_landing_sets_default_workspace_once(self):
		from my_branding import branding

		email = "nx-owner-landing-test@example.com"
		if not frappe.db.exists("User", email):
			u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Owner Test", "user_type": "System User", "send_welcome_email": 0})
			u.append("roles", {"role": "System Manager"})
			u.flags.ignore_permissions = True
			u.insert()
		try:
			frappe.db.set_value("User", email, "default_workspace", None, update_modified=False)
			branding.ensure_owner_landing()
			self.assertEqual(frappe.db.get_value("User", email, "default_workspace"), "Home")
			# a user who chose something else is left alone
			frappe.db.set_value("User", email, "default_workspace", "Selling", update_modified=False)
			branding.ensure_owner_landing()
			self.assertEqual(frappe.db.get_value("User", email, "default_workspace"), "Selling")
			# and get_home_page honours it
			frappe.set_user(email)
			frappe.cache.hdel("home_page", email)
			from frappe.website.utils import get_home_page
			self.assertIn("selling", get_home_page())
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)


class TestInvoicePH(unittest.TestCase):
	def test_print_format_json_in_sync_with_sources(self):
		import pathlib, subprocess, sys

		root = pathlib.Path(frappe.get_app_path("my_branding")).parent
		r = subprocess.run([sys.executable, str(root / "scripts" / "build_print_formats.py"), "--check"], capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

	def test_company_fields_and_format_exist(self):
		from my_branding import invoice_ph

		invoice_ph.ensure_company_invoice_fields()
		for f in ("nx_registered_name", "nx_tax_registration", "nx_invoice_footer"):
			self.assertTrue(frappe.db.exists("Custom Field", f"Company-{f}"), f)
		self.assertTrue(frappe.db.exists("Print Format", invoice_ph.PRINT_FORMAT))
		pf = frappe.get_doc("Print Format", invoice_ph.PRINT_FORMAT)
		self.assertEqual((pf.standard, pf.custom_format, pf.doc_type), ("Yes", 1, "Sales Invoice"))
		self.assertIn("NOT VALID FOR CLAIM OF INPUT TAX", pf.html)

	def test_renders_html_for_a_sales_invoice(self):
		name = frappe.db.get_value("Sales Invoice", {"docstatus": ["<", 2]}, "name")
		if not name:
			self.skipTest("no Sales Invoice on this site")
		html = frappe.get_print("Sales Invoice", name, print_format="Nexum Invoice (PH)")
		self.assertIn('class="nxi"', html)
		self.assertIn("Amount in words", html)
