"""2026-08-22 demo launcher fixes — integration tests on a bench site.

Run via:  bench --site <site> run-tests --module my_branding.tests.test_demo_launcher_health
"""
import unittest

import frappe

from my_branding import branding, demo, spa_brand


class _Resp:
    def __init__(self, html):
        self._html = html
        self.mimetype = "text/html"

    def get_data(self, as_text=False):
        return self._html

    def set_data(self, html):
        self._html = html


class _Req:
    path = "/crm"


class TestSpaBrandDemoTheme(unittest.TestCase):
    HTML = "<html><head><title>Frappe CRM</title></head><body></body></html>"

    def _inject(self, is_demo):
        old = frappe.conf.get("is_demo_site")
        frappe.conf.is_demo_site = is_demo
        try:
            r = _Resp(self.HTML)
            spa_brand.inject_brand_assets(r, _Req())
            return r._html
        finally:
            frappe.conf.is_demo_site = old

    def test_demo_site_resets_theme_to_light_before_brand_assets(self):
        html = self._inject(1)
        self.assertIn('localStorage.setItem("theme","light")', html)
        self.assertLess(html.index('localStorage.setItem("theme","light")'), html.index("spa-brand.js"))

    def test_other_sites_leave_theme_alone(self):
        html = self._inject(0)
        self.assertNotIn("localStorage.setItem", html)
        self.assertIn("spa-brand.js", html)


class TestLendingWorkspaceVisible(unittest.TestCase):
    def test_reconciler_unhides_lending(self):
        if not frappe.db.exists("Workspace", "Lending"):
            self.skipTest("lending not installed on this site")
        frappe.db.set_value("Workspace", "Lending", "is_hidden", 1, update_modified=False)
        branding.reconcile_workspace_visibility()
        self.assertEqual(frappe.db.get_value("Workspace", "Lending", "is_hidden"), 0)
        self.assertNotIn("Lending", branding._HIDE_WORKSPACES_ALWAYS)


class TestDemoSidebarHeal(unittest.TestCase):
    def setUp(self):
        self._old = frappe.conf.get("is_demo_site")
        frappe.conf.is_demo_site = 1

    def tearDown(self):
        frappe.conf.is_demo_site = self._old
        frappe.db.rollback()

    def test_empty_json_backed_sidebar_is_reimported(self):
        if not frappe.db.exists("Workspace Sidebar", "Selling"):
            self.skipTest("Selling sidebar absent")
        before = frappe.db.count("Workspace Sidebar Item", {"parent": "Selling"})
        self.assertGreater(before, 0)
        frappe.db.delete("Workspace Sidebar Item", {"parent": "Selling"})
        self.assertEqual(frappe.db.count("Workspace Sidebar Item", {"parent": "Selling"}), 0)
        demo.reconcile_demo_health()
        self.assertEqual(frappe.db.count("Workspace Sidebar Item", {"parent": "Selling"}), before)

    def test_demo_user_gets_loan_manager(self):
        if not frappe.db.exists("Role", "Loan Manager"):
            self.skipTest("lending not installed")
        if not frappe.db.exists("User", demo.DEMO_USER):
            frappe.get_doc({"doctype": "User", "email": demo.DEMO_USER, "first_name": "Demo",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)
        frappe.db.delete("Has Role", {"parent": demo.DEMO_USER, "role": "Loan Manager"})
        demo.reconcile_demo_health()
        self.assertTrue(frappe.db.exists("Has Role", {"parent": demo.DEMO_USER, "parenttype": "User", "role": "Loan Manager"}))

    def test_noop_off_demo_site(self):
        frappe.conf.is_demo_site = 0
        if not frappe.db.exists("Workspace Sidebar", "Selling"):
            self.skipTest("Selling sidebar absent")
        frappe.db.delete("Workspace Sidebar Item", {"parent": "Selling"})
        demo.reconcile_demo_health()
        self.assertEqual(frappe.db.count("Workspace Sidebar Item", {"parent": "Selling"}), 0)


if __name__ == "__main__":
    unittest.main()
