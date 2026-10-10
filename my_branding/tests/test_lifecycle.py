"""Free-site idle reading counts session activity, not only logins (H5, v204).

frappe writes User.last_login only when a new session starts, while every request on a
live session refreshes User.last_active. Reading last_login alone made a tenant working
daily in one long session look idle: parked at day 30, deleted at day 90.

Probe users are bare tabUser rows inside a savepoint and are rolled back. Each probe's
stamp lies in the future, so it is the site-wide maximum whatever the real users did.
Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_lifecycle
"""
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_datetime, now_datetime

from my_branding import lifecycle

SAVEPOINT = "nx_lifecycle_test"


def _probe_user(last_login, last_active, user_type="System User"):
	name = "nx-idle-probe-%s@example.com" % frappe.generate_hash(length=8)
	frappe.db.sql(
		"""INSERT INTO `tabUser` (name, email, first_name, user_type, enabled, last_login, last_active)
		   VALUES (%s, %s, 'Idle Probe', %s, 1, %s, %s)""",
		(name, name, user_type, last_login, last_active),
	)
	return name


def _stamp(days):
	"""A datetime `days` from now, at whole-second precision (stored as datetime(6))."""
	return get_datetime(add_days(now_datetime(), days)).replace(microsecond=0)


class TestIdleReading(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint(SAVEPOINT)

	def tearDown(self):
		frappe.db.rollback(save_point=SAVEPOINT)

	def test_active_session_counts_even_with_a_stale_login(self):
		# signed in 400 days ago and has kept working on that session ever since
		active = _stamp(1)
		_probe_user(str(_stamp(-400)), active)
		self.assertEqual(lifecycle._last_human_activity(), active)
		self.assertEqual(lifecycle.report_idle_days(), 0)

	def test_login_still_counts_when_last_active_is_null(self):
		login = _stamp(2)
		_probe_user(str(login), None)
		self.assertEqual(lifecycle._last_human_activity(), login)

	def test_empty_login_string_is_ignored(self):
		active = _stamp(3)
		_probe_user("", active)
		self.assertEqual(lifecycle._last_human_activity(), active)

	def test_website_users_are_not_tenant_activity(self):
		before = lifecycle._last_human_activity()
		_probe_user(str(_stamp(5)), _stamp(5), user_type="Website User")
		self.assertEqual(lifecycle._last_human_activity(), before)

	def test_never_signed_in_reads_minus_one(self):
		for row in ([(None, None)], [("", None)]):
			with patch.object(frappe.db, "sql", return_value=row):
				self.assertEqual(lifecycle.report_idle_days(), -1)

	def test_old_activity_reads_whole_days(self):
		with patch.object(lifecycle, "_last_human_activity", return_value=_stamp(-45)):
			self.assertEqual(lifecycle.report_idle_days(), 45)
