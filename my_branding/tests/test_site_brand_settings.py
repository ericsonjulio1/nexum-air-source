"""Website/Navbar Settings keep tenant edits across migrates (M3, v204).

Both Singles used to be fixtures, and frappe's sync_fixtures force-imports every *.json
under fixtures/ on each migrate (delete + re-insert), wiping tenant edits on every
deploy. branding.ensure_site_brand_settings now re-asserts only the brand-owned keys.

Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_site_brand_settings
"""
import os
import unittest

import frappe
from frappe.utils.fixtures import sync_fixtures

from my_branding import brand_config, branding

TENANT_LINK = "_nx-m3 tenant link"


class TestSiteBrandSettings(unittest.TestCase):
	def test_settings_are_seed_data_not_fixtures(self):
		for fname in ("website_settings.json", "navbar_settings.json"):
			self.assertFalse(os.path.exists(frappe.get_app_path("my_branding", "fixtures", fname)))
			self.assertTrue(os.path.exists(frappe.get_app_path("my_branding", "seed", fname)))
		listed = {
			f.get("dt") if isinstance(f, dict) else f
			for f in frappe.get_hooks("fixtures", app_name="my_branding")
		}
		self.assertFalse(listed & {"Website Settings", "Navbar Settings"})

	def test_brand_keys_are_only_the_brand_owned_ones(self):
		brand = branding.site_brand_settings()
		self.assertEqual(
			{dt: set(values) for dt, values in brand.items()},
			{"Website Settings": {"app_name", "app_logo", "disable_signup"}, "Navbar Settings": {"app_logo"}},
		)
		self.assertEqual(brand["Website Settings"]["app_name"], brand_config.BRAND)
		self.assertEqual(brand["Website Settings"]["disable_signup"], 1)
		self.assertTrue(brand["Website Settings"]["app_logo"].startswith("/assets/my_branding/images/"))
		self.assertTrue(brand["Navbar Settings"]["app_logo"].startswith("/assets/my_branding/images/"))

	def test_migrate_keeps_tenant_edits_and_fixes_brand_keys(self):
		brand = branding.site_brand_settings()
		saved_ga = frappe.db.get_single_value("Website Settings", "google_analytics_id", cache=False)
		try:
			# a tenant's edits (written at the data level: what is stored is what migrate
			# meets, however it got there), plus brand keys someone changed
			frappe.db.set_single_value("Website Settings", "google_analytics_id", "G-NXM3TEST")
			frappe.get_doc(
				{
					"doctype": "Top Bar Item",
					"parent": "Website Settings",
					"parenttype": "Website Settings",
					"parentfield": "top_bar_items",
					"idx": 99,
					"label": TENANT_LINK,
					"url": "/nx-m3-tenant",
				}
			).db_insert()
			frappe.db.set_single_value("Website Settings", "app_logo", "/files/not-the-brand.png")
			frappe.db.set_single_value("Navbar Settings", "app_logo", "/files/not-the-brand-white.png")

			# what bench migrate runs for this app: the fixture sync, then the reconciler
			sync_fixtures("my_branding")
			branding.ensure_site_brand_settings()

			ws = frappe.get_doc("Website Settings")
			self.assertEqual(ws.google_analytics_id, "G-NXM3TEST")
			self.assertIn(TENANT_LINK, [row.label for row in ws.top_bar_items])
			for doctype, values in brand.items():
				for fieldname, value in values.items():
					self.assertEqual(frappe.db.get_single_value(doctype, fieldname, cache=False), value)
		finally:
			frappe.db.set_single_value("Website Settings", "google_analytics_id", saved_ga)
			frappe.db.delete("Top Bar Item", {"parent": "Website Settings", "label": TENANT_LINK})
			branding.ensure_site_brand_settings()
			frappe.db.commit()

	def test_reconciler_is_idempotent(self):
		branding.ensure_site_brand_settings()
		before = frappe.db.get_single_value("Website Settings", "modified", cache=False)
		branding.ensure_site_brand_settings()
		self.assertEqual(frappe.db.get_single_value("Website Settings", "modified", cache=False), before)

	def test_app_landing_runs_on_the_single(self):
		# its old table_exists() guard was always False for a Single, so home_page only
		# ever came from the fixture; without the fixture it must set it itself
		saved = frappe.db.get_single_value("Website Settings", "home_page", cache=False)
		try:
			frappe.db.set_single_value("Website Settings", "home_page", "")
			branding.ensure_app_landing()
			home_page = frappe.db.get_single_value("Website Settings", "home_page", cache=False)
			self.assertEqual(home_page, "login")
		finally:
			frappe.db.set_single_value("Website Settings", "home_page", saved)
			frappe.db.commit()
