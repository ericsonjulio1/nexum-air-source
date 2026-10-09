"""Idle screen lock — server half (my_branding/idle_lock.py).

Spec: docs/superpowers/specs/2026-10-06-idle-screen-lock-design.md
Run via:  bench --site <site> run-tests --module my_branding.tests.test_idle_lock
"""
import time
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from my_branding import idle_lock

FAKE_SID = "nx-idle-test-sid"


def _set_settings(enabled=1, minutes=3):
    frappe.db.set_single_value(
        "System Settings",
        {"nexum_idle_lock_enabled": enabled, "nexum_idle_lock_minutes": minutes},
    )
    idle_lock._flush_settings_cache()


@contextmanager
def _conf(**values):
    """Temporarily set site-config keys; None means 'absent'."""
    old = {k: frappe.conf.get(k) for k in values}
    frappe.conf.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                frappe.conf.pop(k, None)
            else:
                frappe.conf[k] = v


@contextmanager
def _request(path, user="Administrator", sid=FAKE_SID, user_type=None):
    """Pretend to be inside a request for `path` from session `sid`."""
    old_session = frappe.local.session
    old_request = getattr(frappe.local, "request", None)
    data = frappe._dict(user_type=user_type) if user_type else frappe._dict()
    frappe.local.session = frappe._dict(user=user, sid=sid, data=data)
    frappe.local.request = SimpleNamespace(path=path)
    try:
        yield sid
    finally:
        frappe.local.session = old_session
        frappe.local.request = old_request


class TestIdleLockSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        idle_lock.ensure_settings_fields()
        cls._saved = (
            frappe.get_system_settings("nexum_idle_lock_enabled"),
            frappe.get_system_settings("nexum_idle_lock_minutes"),
        )

    @classmethod
    def tearDownClass(cls):
        _set_settings(*cls._saved)
        frappe.db.commit()

    def setUp(self):
        _set_settings(1, 3)
        frappe.cache.delete_value(idle_lock._KEY.format(FAKE_SID))
        self._neutral = _conf(nexum_idle_lock=None, is_demo_site=None)
        self._neutral.__enter__()

    def tearDown(self):
        self._neutral.__exit__(None, None, None)
        frappe.cache.delete_value(idle_lock._KEY.format(FAKE_SID))

    def test_clamp_minutes(self):
        for given, expected in ((None, 3), (0, 3), ("7", 7), (5, 5), (-2, 1), (999, 240)):
            self.assertEqual(idle_lock.clamp_minutes(given), expected, given)

    def test_fields_exist_after_setup(self):
        meta = frappe.get_meta("System Settings")
        self.assertTrue(meta.has_field("nexum_idle_lock_enabled"))
        self.assertTrue(meta.has_field("nexum_idle_lock_minutes"))

    def test_settings_default_on_at_three_minutes(self):
        self.assertEqual(idle_lock.get_settings(), {"enabled": True, "idle_minutes": 3})

    def test_settings_follow_system_settings(self):
        _set_settings(0, 10)
        self.assertEqual(idle_lock.get_settings(), {"enabled": False, "idle_minutes": 10})

    def test_site_config_switches_off(self):
        with _conf(nexum_idle_lock=0):
            self.assertFalse(idle_lock.get_settings()["enabled"])

    def test_demo_site_off_unless_overridden(self):
        with _conf(is_demo_site=1):
            self.assertFalse(idle_lock.get_settings()["enabled"])
            with _conf(nexum_idle_lock=1):
                self.assertTrue(idle_lock.get_settings()["enabled"])

    def test_server_limit_is_idle_plus_warning_plus_grace(self):
        self.assertEqual(idle_lock.server_limit_seconds({"enabled": True, "idle_minutes": 3}), 330)

    def test_validate_clamps_minutes(self):
        doc = frappe.get_doc("System Settings")
        doc.nexum_idle_lock_minutes = 999
        idle_lock.validate_system_settings(doc)
        self.assertEqual(doc.nexum_idle_lock_minutes, 240)

    def test_mark_and_read_activity(self):
        idle_lock.mark_activity(FAKE_SID, at=1_000_000)
        self.assertEqual(idle_lock.last_activity(FAKE_SID), 1_000_000)

    def test_heartbeat_marks_activity(self):
        before = int(time.time())
        with _request("/api/method/my_branding.idle_lock.heartbeat"):
            self.assertEqual(idle_lock.heartbeat(), {"ok": True})
        self.assertGreaterEqual(idle_lock.last_activity(FAKE_SID), before)

    def test_on_session_creation_marks_activity(self):
        with _request("/api/method/login"):
            idle_lock.on_session_creation(login_manager=None)
        self.assertIsNotNone(idle_lock.last_activity(FAKE_SID))

    def test_on_session_creation_ignores_guest(self):
        with _request("/", user="Guest"):
            idle_lock.on_session_creation(login_manager=None)
        self.assertIsNone(idle_lock.last_activity(FAKE_SID))

    def test_session_token_returns_token_and_user(self):
        with _request("/api/method/my_branding.idle_lock.session_token"):
            out = idle_lock.session_token()
        self.assertEqual(out["user"], "Administrator")
        self.assertTrue(out["csrf_token"])


class TestIdleLockEnforcement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        idle_lock.ensure_setup()
        cls._saved = (
            frappe.get_system_settings("nexum_idle_lock_enabled"),
            frappe.get_system_settings("nexum_idle_lock_minutes"),
        )

    @classmethod
    def tearDownClass(cls):
        _set_settings(*cls._saved)
        frappe.db.commit()

    def setUp(self):
        _set_settings(1, 3)
        frappe.cache.delete_value(idle_lock._KEY.format(FAKE_SID))
        self._neutral = _conf(nexum_idle_lock=None, is_demo_site=None)
        self._neutral.__enter__()

    def tearDown(self):
        self._neutral.__exit__(None, None, None)
        frappe.cache.delete_value(idle_lock._KEY.format(FAKE_SID))

    def _enforce(self, path, **kw):
        """Run enforce() for `path`; returns (SessionExpired or None, delete, clear, login_manager)."""
        with _request(path, **kw), patch("frappe.sessions.delete_session") as delete, patch(
            "frappe.auth.clear_cookies"
        ) as clear, patch.object(frappe.local, "login_manager", MagicMock(), create=True) as lm:
            error = None
            try:
                idle_lock.enforce()
            except frappe.SessionExpired as e:
                error = e
            return error, delete, clear, lm

    def test_setup_switches_enforcement_on(self):
        self.assertTrue(idle_lock._ready())

    def test_is_stale(self):
        settings = idle_lock.get_settings()
        now = time.time()
        self.assertFalse(idle_lock.is_stale(FAKE_SID, settings, now))  # no record: not stale
        idle_lock.mark_activity(FAKE_SID, at=now - 329)
        self.assertFalse(idle_lock.is_stale(FAKE_SID, settings, now))
        idle_lock.mark_activity(FAKE_SID, at=now - 331)
        self.assertTrue(idle_lock.is_stale(FAKE_SID, settings, now))

    def test_fresh_session_passes(self):
        idle_lock.mark_activity(FAKE_SID)
        error, delete, _clear, _lm = self._enforce("/api/method/frappe.client.get_list")
        self.assertIsNone(error)
        delete.assert_not_called()

    def test_stale_api_request_ends_session_with_401(self):
        idle_lock.mark_activity(FAKE_SID, at=time.time() - 400)
        error, delete, clear, lm = self._enforce("/api/method/frappe.client.get_list")
        self.assertIsInstance(error, frappe.SessionExpired)
        delete.assert_called_once_with(FAKE_SID, user="Administrator", reason="Idle Lock")
        clear.assert_called_once()
        lm.login_as_guest.assert_not_called()
        self.assertIsNone(idle_lock.last_activity(FAKE_SID))

    def test_stale_page_request_continues_as_guest(self):
        idle_lock.mark_activity(FAKE_SID, at=time.time() - 400)
        error, delete, _clear, lm = self._enforce("/app/sales-invoice")
        self.assertIsNone(error)
        delete.assert_called_once()
        lm.login_as_guest.assert_called_once()

    def test_missing_record_starts_fresh(self):
        # A Redis flush (deploy.sh flushes the cache on every image switch) or eviction
        # deletes the records; that must never sign everyone out.
        before = int(time.time())
        error, delete, _clear, _lm = self._enforce("/api/method/frappe.client.get_list")
        self.assertIsNone(error)
        delete.assert_not_called()
        self.assertGreaterEqual(idle_lock.last_activity(FAKE_SID), before)

    def test_unexpected_error_lets_the_request_through(self):
        with patch.object(idle_lock, "last_activity", side_effect=RuntimeError("redis down")):
            error, delete, _clear, _lm = self._enforce("/api/method/frappe.client.get_list")
        self.assertIsNone(error)
        delete.assert_not_called()

    def test_stale_heartbeat_cannot_revive(self):
        idle_lock.mark_activity(FAKE_SID, at=time.time() - 400)
        error, _delete, _clear, _lm = self._enforce("/api/method/my_branding.idle_lock.heartbeat")
        self.assertIsInstance(error, frappe.SessionExpired)

    def test_skips_guest_login_logout_and_disabled(self):
        for path, kw in (
            ("/api/method/frappe.client.get_list", {"user": "Guest"}),
            ("/api/method/login", {}),
            ("/api/method/logout", {}),
            ("/api/v2/method/login", {}),
        ):
            error, delete, _clear, _lm = self._enforce(path, **kw)
            self.assertIsNone(error, path)
            delete.assert_not_called()
        _set_settings(0, 3)
        error, delete, _clear, _lm = self._enforce("/api/method/frappe.client.get_list")
        self.assertIsNone(error)
        delete.assert_not_called()

    def test_portal_users_are_not_checked(self):
        # Website (portal) users never load the desk script, so they never send
        # heartbeats; the lock is for desk users only.
        idle_lock.mark_activity(FAKE_SID, at=time.time() - 400)
        error, delete, _clear, _lm = self._enforce(
            "/api/method/frappe.client.get_list", user_type="Website User"
        )
        self.assertIsNone(error)
        delete.assert_not_called()

    def test_waits_for_setup(self):
        with patch.object(idle_lock, "_ready", return_value=False):
            error, delete, _clear, _lm = self._enforce("/api/method/frappe.client.get_list")
        self.assertIsNone(error)
        delete.assert_not_called()

    def test_seed_gives_unrecorded_sessions_two_hours_and_keeps_records(self):
        sids = ("nx-idle-seed-a", "nx-idle-seed-b")
        for sid in sids:
            frappe.db.sql(
                "insert into `tabSessions` (sid, user, status, sessiondata, lastupdate) "
                "values (%s, 'Administrator', 'Active', '{}', now())",
                sid,
            )
        try:
            idle_lock.mark_activity("nx-idle-seed-b", at=1_000_000)
            before = int(time.time())
            self.assertGreaterEqual(idle_lock.seed_existing_sessions(), 1)
            self.assertGreaterEqual(
                idle_lock.last_activity("nx-idle-seed-a"), before + idle_lock.DEPLOY_GRACE_SECONDS
            )
            self.assertEqual(idle_lock.last_activity("nx-idle-seed-b"), 1_000_000)
        finally:
            for sid in sids:
                frappe.db.delete("Sessions", {"sid": sid})
                frappe.cache.delete_value(idle_lock._KEY.format(sid))
            frappe.db.commit()


class _Resp:
    def __init__(self, html):
        self._html = html
        self.mimetype = "text/html"

    def get_data(self, as_text=False):
        return self._html

    def set_data(self, html):
        self._html = html


class TestActivityReporterInjection(unittest.TestCase):
    HTML = "<html><head><title>Bank Reconciliation</title></head><body></body></html>"

    def setUp(self):
        idle_lock.ensure_settings_fields()
        _set_settings(1, 3)

    def _inject(self, path, user="Administrator", user_type=None, status=200, **conf):
        r = _Resp(self.HTML)
        r.status_code = status
        with _conf(**conf), _request(path, user=user, user_type=user_type):
            idle_lock.inject_activity_reporter(r, SimpleNamespace(path=path))
        return r._html

    def test_injected_on_non_desk_pages_for_desk_users(self):
        for path in ("/banking", "/crm", "/me", "/printview"):
            html = self._inject(path, nexum_idle_lock=None, is_demo_site=None)
            self.assertIn("idle_activity.js", html, path)
            self.assertEqual(html.count("idle_activity.js"), 1, path)

    def test_not_injected_on_the_desk_or_for_others(self):
        neutral = {"nexum_idle_lock": None, "is_demo_site": None}
        self.assertNotIn("idle_activity.js", self._inject("/app/todo", **neutral))
        self.assertNotIn("idle_activity.js", self._inject("/desk/todo", **neutral))
        self.assertNotIn("idle_activity.js", self._inject("/banking", user="Guest", **neutral))
        self.assertNotIn("idle_activity.js", self._inject("/me", user_type="Website User", **neutral))
        self.assertNotIn("idle_activity.js", self._inject("/banking", status=404, **neutral))
        self.assertNotIn("idle_activity.js", self._inject("/banking", nexum_idle_lock=0, is_demo_site=None))
        self.assertNotIn("idle_activity.js", self._inject("/banking", nexum_idle_lock=None, is_demo_site=1))
