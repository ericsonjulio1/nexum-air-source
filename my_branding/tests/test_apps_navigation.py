"""Regression coverage for the Apps-mode upgrade (owner report 2026-10-15)."""
import unittest

import frappe

from my_branding import boot, naming


class TestAppsNavigation(unittest.TestCase):
	def test_boot_uses_existing_brand_icon_without_changing_app_access_or_landing(self):
		app = dict(app_name="erpnext", app_title="ERPNext", app_logo_url="/assets/erpnext/images/erpnext-logo.svg",
			app_route="/desk/home", on_apps_screen=True, dock=[{"name": "Assets"}])
		info = frappe._dict(app_data=[app])
		boot.boot_session(info)
		self.assertEqual(app["app_logo_url"], naming.APP_LOGOS["erpnext"])
		self.assertEqual(app["app_title"], "ERP")
		self.assertEqual(app["app_route"], "/desk/home")
		self.assertTrue(app["on_apps_screen"])
		self.assertEqual(app["dock"], [{"name": "Assets"}])

	def test_rebranding_does_not_expose_an_app_denied_by_framework(self):
		app = dict(app_name="erpnext", app_route="", on_apps_screen=False, dock=[])
		boot.boot_session(frappe._dict(app_data=[app]))
		self.assertEqual(app["app_route"], "")
		self.assertFalse(app["on_apps_screen"])
		self.assertEqual(app["dock"], [])

	def test_spa_erp_entry_returns_to_suite_and_other_apps_keep_their_routes(self):
		apps = {app["name"]: app for app in naming.get_apps()}
		self.assertEqual(apps["erpnext"]["route"], "/desk")
		self.assertEqual(apps["erpnext"]["title"], "ERP")
		self.assertIn("/erp_app.svg", apps["erpnext"]["logo"])
		if "crm" in apps:
			self.assertEqual(apps["crm"]["route"], "/crm")
