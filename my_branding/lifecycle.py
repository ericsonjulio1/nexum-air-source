"""Free-tier site lifecycle helpers (app-side).

The HOST timer (saas/trial-lifecycle.py) idle-parks perpetually-free tenants:
after a stretch with no human activity it disables the site's scheduler (the only
recurring cost an otherwise-idle site still incurs) so a dormant Free site costs
~nothing on the shared box. These two helpers are the app-side counterparts:

* ``report_idle_days`` — called by the host via ``bench execute`` to learn how
  many days it's been since the most recent human activity (so the host knows what
  to park / eventually delete). Prints a parseable ``NEXUM_IDLE_DAYS=<n>`` line.
* ``wake_scheduler`` — an ``on_login`` hook so a returning customer's parked Free
  site re-enables its own scheduler immediately, before the next host sweep runs.

Both only ever act on Free sites, identified by the presence of ``nexum_doc_caps``
in site_config (only Free plans carry doc caps)."""

import frappe


def _last_human_activity():
	"""Most recent sign-in OR request by a desk user (System User other than
	Administrator/Guest), as a datetime; None if no one ever signed in.

	``last_login`` alone is not activity (H5, v204): frappe writes it only when a NEW
	session starts (sessions.py Session.start). Every request on an existing session
	refreshes the cookie expiry (240 h by default) and, at most every 10 min, writes
	User.last_active (Session.update, sessions.py:441 in frappe 16.36.1; also set at
	login). A tenant who switched the idle lock off and works daily in one long session
	never logs in again, so on last_login alone their site looked idle: parked at day 30
	and DELETED at day 90 by saas/trial-lifecycle.py while in use.

	MAX over users of GREATEST(last_login, last_active) equals the greater of the two
	column maxima, so the SQL takes each MAX and Python compares them. MariaDB's
	GREATEST() returns NULL if any argument is NULL, and last_login is a varchar
	("Read Only" field, sometimes '') while last_active is a datetime."""
	from frappe.utils import get_datetime

	row = frappe.db.sql(
		"""SELECT MAX(last_login), MAX(last_active) FROM `tabUser`
		   WHERE user_type = 'System User'
		     AND name NOT IN ('Administrator', 'Guest')"""
	)
	stamps = [get_datetime(v) for v in (row[0] if row else ()) if v]
	return max(stamps) if stamps else None


def report_idle_days():
	"""Print ``NEXUM_IDLE_DAYS=<n>`` — whole days since the most recent human
	activity on this site (see ``_last_human_activity``), or ``-1`` if no one has ever
	signed in. The host idle-sweep greps this exact line out of stdout. Returns the
	same int."""
	from frappe.utils import now_datetime

	last = _last_human_activity()
	if not last:
		print("NEXUM_IDLE_DAYS=-1")
		return -1
	# -1 is reserved for "never signed in", and the host then measures idleness from
	# the site's age. A stamp slightly in the future (clock step, or a tenant changing
	# the System Settings time zone) is current activity: report 0, never -1.
	days = max((now_datetime() - last).days, 0)
	print("NEXUM_IDLE_DAYS=%d" % days)
	return days


def wake_scheduler(login_manager=None):
	"""``on_login``: re-enable the scheduler on a Free site that the host idle-sweep
	parked, so a returning customer's background jobs resume at once. No-op on paid
	sites (no doc caps) and when the scheduler is already enabled. Best-effort: a
	login must never fail because of this."""
	try:
		if not frappe.conf.get("nexum_doc_caps"):
			return  # not a Free site
		from frappe.utils.scheduler import is_scheduler_disabled

		if is_scheduler_disabled():
			frappe.db.set_single_value("System Settings", "enable_scheduler", 1)
			frappe.db.commit()
	except Exception:
		frappe.log_error(
			title="my_branding wake_scheduler failed",
			message=frappe.get_traceback(),
		)
