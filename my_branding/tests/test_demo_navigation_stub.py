"""2026-10-20 demo navigation check against a stub frappe — runs WITHOUT a bench:
    python3 my_branding/tests/test_demo_navigation_stub.py      (from the repo root)

Covers the 16.50+ branch logic of my_branding/demo.py (archive left alone, demo-user
resolution + restore, problem lines) where no 16.52 bench exists. On a bench, real frappe is
importable and this skips: test_demo_launcher_health.TestDemoNavigation covers it there.
"""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch


def _real_frappe_present():
    try:
        import frappe
    except ImportError:
        return False
    return True


class _Stub:
    """A frappe module stand-in with just what demo.py's 16.50+ path touches."""

    def __init__(self, payload=None, raises=None, doctypes=("Sidebar",), users=("demo@nexumair.com",),
                 modules=("Accounts", "Selling", "Buying", "Stock", "Assets", "EAM")):
        self.calls_as, self.errors, self.deleted = [], [], []
        self.payload, self.raises = payload, raises
        self.records = {("DocType", d) for d in doctypes} | {("User", u) for u in users} \
            | {("Module Def", m) for m in modules}
        self.mod = types.ModuleType("frappe")
        self.mod.conf = types.SimpleNamespace(get=lambda k: {"is_demo_site": 1}.get(k))
        self.mod.session = types.SimpleNamespace(user="Administrator")
        self.mod.db = types.SimpleNamespace(
            exists=lambda dt, name=None: (dt, name) in self.records,
            table_exists=lambda dt: True,
            sql=lambda *a, **k: self.fail("legacy SQL ran on 16.50+"),
        )
        self.mod.set_user = lambda u: setattr(self.mod.session, "user", u)
        self.mod.log_error = lambda title=None, message=None: self.errors.append((title, message))
        self.mod.get_traceback = lambda: "Traceback: stub"
        self.mod.delete_doc = lambda *a, **k: self.deleted.append(a)
        # _ensure_demo_roles (unchanged code) runs between the heal and the navigation check
        self.mod.get_doc = lambda dt, name: types.SimpleNamespace(
            roles=[types.SimpleNamespace(role="Loan Manager")], add_roles=lambda *r: None)
        self.boot = types.ModuleType("frappe.boot")
        self.boot.get_module_sidebars = self._resolve
        self.mod.boot = self.boot

    def fail(self, msg):
        raise AssertionError(msg)

    def _resolve(self):
        self.calls_as.append(self.mod.session.user)
        if self.raises:
            raise self.raises
        return self.payload

    def load_demo(self):
        path = os.path.join(os.path.dirname(__file__), "..", "demo.py")
        with patch.dict(sys.modules, {"frappe": self.mod, "frappe.boot": self.boot}):
            spec = importlib.util.spec_from_file_location("demo_under_test", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        return mod

    def run(self, fn, *a):
        with patch.dict(sys.modules, {"frappe": self.mod, "frappe.boot": self.boot}):
            return fn(*a)


def _healthy():
    return {s: {"items": [1]} for s in ("Accounts", "Selling", "Buying", "Stock", "Assets", "Maintenance")}


@unittest.skipIf(_real_frappe_present(), "real frappe present: see test_demo_launcher_health")
class TestDemoNavigationStub(unittest.TestCase):
    def test_healthy_navigation_no_errors_and_archive_untouched(self):
        st = _Stub(payload=_healthy())
        demo = st.load_demo()
        st.run(demo.reconcile_demo_health)
        self.assertEqual(st.errors, [])  # no "sidebars failed": the dead import is never reached
        self.assertEqual(st.deleted, [])
        self.assertEqual(st.calls_as, ["demo@nexumair.com"])
        self.assertEqual(st.mod.session.user, "Administrator")

    def test_missing_and_empty_shells_reported(self):
        payload = _healthy()
        del payload["Maintenance"]
        payload["Stock"]["items"] = []
        st = _Stub(payload=payload)
        demo = st.load_demo()
        problems = st.run(demo._demo_navigation_problems)
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(any("'Maintenance' (module EAM) is missing" in p for p in problems))
        self.assertTrue(any("'Stock'" in p and "no items" in p for p in problems))
        st.run(demo.reconcile_demo_health)
        self.assertEqual([t for t, _ in st.errors], ["reconcile_demo_health navigation unhealthy"])

    def test_shell_not_expected_when_module_absent(self):
        payload = _healthy()
        del payload["Maintenance"]
        st = _Stub(payload=payload, modules=("Accounts", "Selling", "Buying", "Stock", "Assets"))
        self.assertEqual(st.run(st.load_demo()._demo_navigation_problems), [])

    def test_empty_payload_and_missing_user(self):
        st = _Stub(payload={})
        self.assertEqual(len(st.run(st.load_demo()._demo_navigation_problems)), 1)
        st = _Stub(payload=_healthy(), users=())
        problems = st.run(st.load_demo()._demo_navigation_problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not exist", problems[0])
        self.assertEqual(st.calls_as, [])

    def test_user_restored_when_resolution_raises(self):
        st = _Stub(raises=RuntimeError("boom"))
        demo = st.load_demo()
        with self.assertRaises(RuntimeError):
            st.run(demo._demo_navigation_problems)
        self.assertEqual(st.mod.session.user, "Administrator")
        st.run(demo.reconcile_demo_health)  # never aborts: logged instead
        self.assertEqual([t for t, _ in st.errors], ["reconcile_demo_health navigation check failed"])
        self.assertEqual(st.mod.session.user, "Administrator")

    def test_pre_1650_frappe_skips_the_navigation_check(self):
        st = _Stub(payload={}, doctypes=())
        self.assertEqual(st.run(st.load_demo()._demo_navigation_problems), [])
        self.assertEqual(st.calls_as, [])


if __name__ == "__main__":
    unittest.main()
