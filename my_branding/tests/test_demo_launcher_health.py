"""2026-08-22 demo launcher fixes — integration tests on a bench site.

Run via:  bench --site <site> run-tests --module my_branding.tests.test_demo_launcher_health
"""
import unittest
from unittest.mock import patch

import frappe

from my_branding import branding, demo, spa_brand  # noqa


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
        if demo._modern_navigation():
            self.skipTest("Frappe 16.50+: Workspace Sidebar is an archive (TestDemoNavigation)")
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


def _healthy_payload():
    return {shell: {"name": shell, "module": module, "items": [{"label": "x"}]}
            for shell, module in demo.DEMO_CORE_SHELLS.items()}


class TestDemoNavigation(unittest.TestCase):
    """2026-10-20: on Frappe 16.50+ the heal must leave the Workspace Sidebar archive alone
    and the demo login's resolved navigation is checked instead."""

    def setUp(self):
        if not demo._modern_navigation():
            self.skipTest("pre-16.50 Frappe: the legacy sidebar heal applies")
        self._old = frappe.conf.get("is_demo_site")
        frappe.conf.is_demo_site = 1
        if not frappe.db.exists("User", demo.DEMO_USER):
            frappe.get_doc({"doctype": "User", "email": demo.DEMO_USER, "first_name": "Demo",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.conf.is_demo_site = self._old
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _errors(self, title):
        return frappe.db.count("Error Log", {"method": title})

    def test_archive_untouched_and_no_sidebar_error(self):
        sidebar = frappe.db.get_value("Workspace Sidebar Item", {}, "parent")
        if not sidebar:
            self.skipTest("no archived Workspace Sidebar rows on this site")
        frappe.db.delete("Workspace Sidebar Item", {"parent": sidebar})
        before = self._errors("reconcile_demo_health sidebars failed")
        with patch("frappe.boot.get_module_sidebars", return_value=_healthy_payload()):
            demo.reconcile_demo_health()
        self.assertEqual(frappe.db.count("Workspace Sidebar Item", {"parent": sidebar}), 0)
        self.assertTrue(frappe.db.exists("Workspace Sidebar", sidebar))
        self.assertEqual(self._errors("reconcile_demo_health sidebars failed"), before)

    def test_healthy_navigation_reports_nothing(self):
        before = self._errors("reconcile_demo_health navigation unhealthy")
        with patch("frappe.boot.get_module_sidebars", return_value=_healthy_payload()):
            self.assertEqual(demo._demo_navigation_problems(), [])
            demo.reconcile_demo_health()
        self.assertEqual(self._errors("reconcile_demo_health navigation unhealthy"), before)

    def test_missing_or_empty_core_shell_is_logged(self):
        if not frappe.db.exists("Module Def", "Selling"):
            self.skipTest("Selling module absent")
        payload = _healthy_payload()
        del payload["Selling"]
        payload["Accounts"]["items"] = []
        before = self._errors("reconcile_demo_health navigation unhealthy")
        with patch("frappe.boot.get_module_sidebars", return_value=payload):
            problems = demo._demo_navigation_problems()
            demo.reconcile_demo_health()
        self.assertTrue(any("'Selling'" in p and "missing" in p for p in problems), problems)
        self.assertTrue(any("'Accounts'" in p and "no items" in p for p in problems), problems)
        self.assertEqual(self._errors("reconcile_demo_health navigation unhealthy"), before + 1)

    def test_resolved_as_demo_user_and_user_restored(self):
        seen = []
        with patch("frappe.boot.get_module_sidebars",
                   side_effect=lambda: seen.append(frappe.session.user) or _healthy_payload()):
            demo._demo_navigation_problems()
        self.assertEqual(seen, [demo.DEMO_USER])
        self.assertEqual(frappe.session.user, "Administrator")

    def test_user_restored_when_resolution_raises(self):
        with patch("frappe.boot.get_module_sidebars", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                demo._demo_navigation_problems()
        self.assertEqual(frappe.session.user, "Administrator")
        before = self._errors("reconcile_demo_health navigation check failed")
        with patch("frappe.boot.get_module_sidebars", side_effect=RuntimeError("boom")):
            demo.reconcile_demo_health()  # swallowed into Error Log, never aborts the migrate
        self.assertEqual(self._errors("reconcile_demo_health navigation check failed"), before + 1)

    def test_missing_demo_user_is_a_problem(self):
        with patch.object(demo, "DEMO_USER", "no-such-demo-user@example.invalid"):
            problems = demo._demo_navigation_problems()
        self.assertEqual(len(problems), 1)
        self.assertIn("does not exist", problems[0])

    def test_noop_off_demo_site(self):
        frappe.conf.is_demo_site = 0
        before = self._errors("reconcile_demo_health navigation unhealthy")
        with patch("frappe.boot.get_module_sidebars", return_value={}):
            demo.reconcile_demo_health()
        self.assertEqual(self._errors("reconcile_demo_health navigation unhealthy"), before)


if __name__ == "__main__":
    unittest.main()


class TestDefaultPortalHome(unittest.TestCase):
    """helpdesk sets Portal Settings.default_portal_home=/helpdesk; frappe ranks it above
    Website Settings, so system users' post-login home became the Helpdesk SPA. The
    reconciler resets it to /app (desk). (2026-08-23 bump fallout.)"""

    def setUp(self):
        self._orig = frappe.db.get_single_value("Portal Settings", "default_portal_home")

    def tearDown(self):
        frappe.db.set_value("Portal Settings", "Portal Settings", "default_portal_home", self._orig)
        frappe.db.commit()

    def test_helpdesk_value_is_reset_to_empty(self):
        frappe.db.set_value("Portal Settings", "Portal Settings", "default_portal_home", "/helpdesk")
        branding.reconcile_default_portal_home()
        self.assertEqual(frappe.db.get_single_value("Portal Settings", "default_portal_home"), "")

    def test_interim_app_value_also_reset(self):
        frappe.db.set_value("Portal Settings", "Portal Settings", "default_portal_home", "/app")
        branding.reconcile_default_portal_home()
        self.assertEqual(frappe.db.get_single_value("Portal Settings", "default_portal_home"), "")

    def test_other_value_left_untouched(self):
        frappe.db.set_value("Portal Settings", "Portal Settings", "default_portal_home", "/custom-portal")
        branding.reconcile_default_portal_home()
        self.assertEqual(frappe.db.get_single_value("Portal Settings", "default_portal_home"), "/custom-portal")
