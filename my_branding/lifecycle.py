"""Free-tier site lifecycle helpers (app-side).

The HOST timer (saas/trial-lifecycle.py) idle-parks perpetually-free tenants:
after a stretch with no human login it disables the site's scheduler (the only
recurring cost an otherwise-idle site still incurs) so a dormant Free site costs
~nothing on the shared box. These two helpers are the app-side counterparts:

* ``report_idle_days`` — called by the host via ``bench execute`` to learn how
  many days it's been since the most recent human login (so the host knows what
  to park / eventually delete). Prints a parseable ``NEXUM_IDLE_DAYS=<n>`` line.
* ``wake_scheduler`` — an ``on_login`` hook so a returning customer's parked Free
  site re-enables its own scheduler immediately, before the next host sweep runs.

Both only ever act on Free sites, identified by the presence of ``nexum_doc_caps``
in site_config (only Free plans carry doc caps)."""

import frappe


def report_idle_days():
	"""Print ``NEXUM_IDLE_DAYS=<n>`` — whole days since the most recent human
	(non-system) login on this site, or ``-1`` if no one has ever logged in. The
	host idle-sweep greps this exact line out of stdout. Returns the same int."""
	from frappe.utils import get_datetime, now_datetime

	row = frappe.db.sql(
		"""SELECT MAX(last_login) FROM `tabUser`
		   WHERE user_type = 'System User'
		     AND name NOT IN ('Administrator', 'Guest')"""
	)
	last = row[0][0] if row and row[0] else None
	if not last:
		print("NEXUM_IDLE_DAYS=-1")
		return -1
	days = (now_datetime() - get_datetime(last)).days
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
