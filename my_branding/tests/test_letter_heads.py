"""Letterhead seeding is insert-only across migrates (perf/correctness sweep 2026-10-02).

frappe's sync_fixtures force-imports EVERY *.json under an app's fixtures/ folder on each
migrate (delete + re-insert), whatever hooks.fixtures lists, so the seed must live elsewhere.

Run via:  bench --site <site> run-tests --module my_branding.tests.test_letter_heads
"""
import os
import unittest

import frappe
from frappe.utils.fixtures import sync_fixtures

from my_branding import branding

SEEDED = "Company Letterhead"


class TestLetterHeadSeed(unittest.TestCase):
	def test_seed_is_not_a_fixture(self):
		self.assertFalse(os.path.exists(frappe.get_app_path("my_branding", "fixtures", "letter_head.json")))
		self.assertTrue(os.path.exists(frappe.get_app_path("my_branding", "seed", "letter_head.json")))

	def test_migrate_keeps_tenant_edits_and_default(self):
		branding.ensure_letter_heads()
		self.assertTrue(frappe.db.exists("Letter Head", SEEDED))
		created = frappe.db.get_value("Letter Head", SEEDED, "creation")
		original = frappe.db.get_value("Letter Head", SEEDED, "content")
		tenant = "_Test Tenant Letterhead"
		previous_default = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
		try:
			frappe.db.set_value("Letter Head", SEEDED, "content", "<p>tenant edit</p>")
			if not frappe.db.exists("Letter Head", tenant):
				frappe.get_doc(dict(doctype="Letter Head", letter_head_name=tenant, source="HTML",
					content="<p>tenant</p>", is_default=1)).insert(ignore_permissions=True)
			else:
				frappe.db.set_value("Letter Head", tenant, "is_default", 1)
				frappe.db.sql("update `tabLetter Head` set is_default=0 where name!=%s", tenant)
			# what `bench migrate` runs for this app: fixture sync, then the reconciler
			sync_fixtures("my_branding")
			branding.ensure_letter_heads()
			self.assertEqual(frappe.db.get_value("Letter Head", SEEDED, "content"), "<p>tenant edit</p>")
			self.assertEqual(frappe.db.get_value("Letter Head", SEEDED, "creation"), created)
			self.assertEqual(frappe.db.get_value("Letter Head", {"is_default": 1}, "name"), tenant)
		finally:
			frappe.db.set_value("Letter Head", SEEDED, "content", original)
			if frappe.db.exists("Letter Head", tenant):
				frappe.delete_doc("Letter Head", tenant, ignore_permissions=True, force=True)
			if previous_default and frappe.db.exists("Letter Head", previous_default):
				frappe.db.set_value("Letter Head", previous_default, "is_default", 1)
			frappe.db.commit()
