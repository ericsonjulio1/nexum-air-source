"""Idle screen lock — the server half.

Spec: docs/superpowers/specs/2026-10-06-idle-screen-lock-design.md

The desk (public/js/idle_lock.js) warns after `idle_minutes` without human activity,
ends the session 60 s later and locks the page in place. This module is what makes the
lock a security control rather than a screen cover: it records human activity per
session (heartbeats from the desk and the SPAs) and refuses a cookie session that has
shown none for longer than the limit, even when no browser is running. Background
polling never counts — only heartbeats do.
"""

import time

import frappe
from frappe import _
from frappe.utils import cint

DEFAULT_MINUTES = 3
MIN_MINUTES, MAX_MINUTES = 1, 240
WARNING_SECONDS = 60
GRACE_SECONDS = 90  # heartbeat throttle lag (60 s) + network slack
DEPLOY_GRACE_SECONDS = 2 * 3600
READY_DEFAULT = "nexum_idle_lock_ready"
_KEY = "nexum_idle:{}"

SETTINGS_FIELDS = {
	"System Settings": [
		{
			"fieldname": "nexum_idle_lock_section",
			"label": "Screen lock",
			"fieldtype": "Section Break",
			"insert_after": "max_signups_allowed_per_hour",
		},
		{
			"fieldname": "nexum_idle_lock_enabled",
			"label": "Lock the screen when idle",
			"fieldtype": "Check",
			"default": "1",
			"insert_after": "nexum_idle_lock_section",
		},
		{
			"fieldname": "nexum_idle_lock_minutes",
			"label": "Minutes of inactivity before the warning",
			"fieldtype": "Int",
			"default": str(DEFAULT_MINUTES),
			"depends_on": "nexum_idle_lock_enabled",
			"insert_after": "nexum_idle_lock_enabled",
			"description": "After this many minutes without mouse, keyboard or touch activity a "
			"60-second warning appears; with no answer the session ends and the screen locks. 1–240.",
		},
	]
}


def clamp_minutes(value):
	"""Idle minutes within 1–240; empty or 0 means the default."""
	minutes = cint(value) or DEFAULT_MINUTES
	return max(MIN_MINUTES, min(MAX_MINUTES, minutes))


def get_settings():
	"""{"enabled": bool, "idle_minutes": int} for this site.

	Site config `nexum_idle_lock` = 0 switches it off; a demo site (`is_demo_site`) is
	off unless that key is set explicitly. Otherwise the System Settings fields decide.
	Unreadable settings fail closed: on, at the default minutes."""
	override = frappe.conf.get("nexum_idle_lock")
	if override is not None:
		if not cint(override):
			return {"enabled": False, "idle_minutes": DEFAULT_MINUTES}
	elif frappe.conf.get("is_demo_site"):
		return {"enabled": False, "idle_minutes": DEFAULT_MINUTES}
	try:
		enabled = frappe.get_system_settings("nexum_idle_lock_enabled")
		minutes = frappe.get_system_settings("nexum_idle_lock_minutes")
	except Exception:
		enabled = minutes = None
	return {
		"enabled": True if enabled is None else bool(cint(enabled)),
		"idle_minutes": clamp_minutes(minutes),
	}


def server_limit_seconds(settings=None):
	"""Seconds without a heartbeat after which the server ends a session."""
	settings = settings or get_settings()
	return settings["idle_minutes"] * 60 + WARNING_SECONDS + GRACE_SECONDS


def _flush_settings_cache():
	frappe.clear_document_cache("System Settings", "System Settings")
	frappe.local.system_settings = None


def _ttl(at):
	"""Keep a record at least as long as Frappe keeps the session, so a missing record
	means 'never seen' rather than 'expired'."""
	from frappe.sessions import get_expiry_in_seconds

	lifetime = max(cint(get_expiry_in_seconds()), server_limit_seconds())
	return max(0, int(at - time.time())) + lifetime + 3600


def mark_activity(sid, at=None):
	"""Record human activity for session `sid` at epoch `at` (default: now)."""
	if not sid or sid == "Guest":
		return
	at = int(time.time()) if at is None else int(at)
	frappe.cache.set_value(_KEY.format(sid), at, expires_in_sec=_ttl(at))


def last_activity(sid):
	"""Epoch seconds of the last recorded human activity, or None."""
	if not sid:
		return None
	value = frappe.cache.get_value(_KEY.format(sid), use_local_cache=False)
	return None if value is None else cint(value)


def on_session_creation(login_manager=None):
	"""Hook: every new signed-in session starts with a fresh activity record (password
	and two-factor login, login_as, impersonation, email-link login)."""
	if frappe.session.user != "Guest":
		mark_activity(frappe.session.sid)


@frappe.whitelist(methods=["POST"])
def heartbeat():
	"""Desk and SPA pages: a human is active in this session. enforce() has already
	refused the request if the session went stale, so a dead session cannot revive."""
	mark_activity(frappe.session.sid)
	return {"ok": True}


@frappe.whitelist(methods=["GET"])
def session_token():
	"""After an in-place unlock: the new session's CSRF token (the page still holds the
	deleted session's) and its user, which the lock screen checks before unlocking."""
	from frappe.sessions import get_csrf_token

	token = get_csrf_token()
	session_obj = getattr(frappe.local, "session_obj", None)
	if session_obj and session_obj.sid == frappe.session.sid:
		session_obj.update(force=True)  # persist a freshly generated token
	return {"csrf_token": token, "user": frappe.session.user}


def validate_system_settings(doc, method=None):
	"""doc_events System Settings.validate: keep the minutes within 1–240."""
	if doc.meta.has_field("nexum_idle_lock_minutes"):
		doc.nexum_idle_lock_minutes = clamp_minutes(doc.nexum_idle_lock_minutes)


def ensure_settings_fields():
	"""Create the "Screen lock" fields on System Settings. A Single's Check reads back
	as 0 until a value is stored, which would silently switch the lock off, so the
	defaults are stored once when no value exists yet. Idempotent."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(SETTINGS_FIELDS, ignore_validate=True, update=True)
	stored = set(
		frappe.db.sql_list(
			"select field from `tabSingles` where doctype='System Settings' "
			"and field in ('nexum_idle_lock_enabled', 'nexum_idle_lock_minutes')"
		)
	)
	defaults = {"nexum_idle_lock_enabled": 1, "nexum_idle_lock_minutes": DEFAULT_MINUTES}
	missing = {k: v for k, v in defaults.items() if k not in stored}
	if missing:
		frappe.db.set_single_value("System Settings", missing)
	_flush_settings_cache()


_SKIP_PATHS = frozenset(
	("/api/method/login", "/api/method/logout", "/api/v2/method/login", "/api/v2/method/logout")
)


def is_stale(sid, settings=None, now=None):
	"""True when `sid`'s last recorded human activity is older than the server limit.
	A missing record is not stale: see enforce()."""
	last = last_activity(sid)
	if last is None:
		return False
	now = time.time() if now is None else now
	return now - last > server_limit_seconds(settings)


def _ready():
	"""Enforcement starts only after ensure_setup() has seeded existing sessions."""
	return bool(cint(frappe.db.get_default(READY_DEFAULT)))


def _is_desk_user(session):
	"""The lock is for desk (System) users. Portal users never load the desk script, so
	they never send heartbeats and must not be checked."""
	user_type = (session.get("data") or {}).get("user_type")
	if not user_type:
		user_type = frappe.get_cached_value("User", session.get("user"), "user_type")
	return user_type == "System User"


def enforce():
	"""before_request: end a cookie session with no human activity for too long.

	Frappe runs before_request inside init_request, before validate_auth, so API-key and
	OAuth requests are still Guest here and are skipped, as are portal (Website) users.
	Login/logout are skipped too:
	login replaces the session anyway, and refusing it would fail the first sign-in
	attempt after a stale cookie."""
	session = getattr(frappe.local, "session", None)
	if not session or session.get("user") in (None, "", "Guest") or not _is_desk_user(session):
		return
	path = getattr(frappe.request, "path", "") or ""
	if path in _SKIP_PATHS or frappe.form_dict.get("cmd") in ("login", "logout"):
		return
	sid = session.get("sid")
	try:
		settings = get_settings()
		if not settings["enabled"] or not _ready():
			return
		if last_activity(sid) is None:
			# Every session gets a record at login, so a missing one means Redis lost it
			# (deploy.sh flushes the cache on each image switch; restarts, eviction).
			# Start counting now rather than signing everyone out.
			mark_activity(sid)
			return
		stale = is_stale(sid, settings)
	except Exception:
		# Never let a bug or an outage here take the whole desk down.
		frappe.logger("idle_lock").exception("idle-lock check skipped")
		return
	if stale:
		_end_session(sid, session.get("user"), path)


def _end_session(sid, user, path):
	"""Same steps as LoginManager.logout. API callers get a 401, which the desk turns
	into the lock screen; a page load continues as Guest so Frappe redirects to /login
	normally instead of rendering an error page."""
	from frappe.auth import clear_cookies
	from frappe.sessions import delete_session

	delete_session(sid, user=user, reason="Idle Lock")
	frappe.cache.delete_value(_KEY.format(sid))
	clear_cookies()
	if path.startswith("/api/"):
		raise frappe.SessionExpired(_("Your session was locked after a period of inactivity."))
	frappe.local.login_manager.login_as_guest()


def seed_existing_sessions(grace_seconds=DEPLOY_GRACE_SECONDS):
	"""Give every active session that has no activity record one, stamped
	`grace_seconds` ahead (default: the two-hour roll-out grace; 0 = now). Tabs opened
	before the roll-out run the old script and send no heartbeat; failing closed on them
	would bounce people to /login mid-entry. Sessions that already have a record keep
	it. Returns the number seeded."""
	until = int(time.time()) + grace_seconds
	sids = frappe.db.sql_list(
		"select sid from `tabSessions` where status='Active' and user not in ('Guest', '')"
	)
	seeded = 0
	for sid in sids:
		if last_activity(sid) is None:
			mark_activity(sid, at=until)
			seeded += 1
	return seeded


def ensure_setup():
	"""after_migrate — and run directly by the v16-prod-203 release, which skips migrate:
	create the settings fields, seed existing sessions, then switch enforcement on.
	Idempotent.

	Only the first roll-out (ready default not yet set) seeds with the two-hour grace.
	Every later migrate runs right after deploy.sh's FLUSHALL wiped all the activity
	records, so re-granting the grace handed every idle or abandoned session (a
	left-behind or stolen cookie) two more hours after each deploy (batch205 idx 88).
	Not seeding at all would be worse: enforce() starts a missing record fresh whenever
	the cookie is next presented, however late. So later runs stamp `now` — the count
	starts at the deploy. A tab in use loses nothing: its last real activity is older
	than the stamp, and its next heartbeat refreshes it."""
	ensure_settings_fields()
	if _ready():
		seed_existing_sessions(grace_seconds=0)
	else:
		seed_existing_sessions()
		frappe.db.set_default(READY_DEFAULT, "1")
	frappe.db.commit()


_DESK_ROOTS = ("/app", "/desk")  # the desk loads idle_lock.js itself
_REPORTER_MARKER = "nexum-idle-activity"


def inject_activity_reporter(response, request):
	"""after_request: give every non-desk page a desk user opens (the HR/CRM/Helpdesk
	SPAs, /banking, web forms, /me, print views) the small activity reporter, so working
	there keeps the shared session alive. The desk itself loads idle_lock.js instead.
	Hardened like spa_brand: any problem leaves the response untouched."""
	try:
		if (getattr(response, "mimetype", "") or "") != "text/html":
			return
		if getattr(response, "status_code", 200) != 200:
			return
		path = getattr(request, "path", "") or ""
		if path in _DESK_ROOTS or path.startswith(tuple(r + "/" for r in _DESK_ROOTS)):
			return
		session = getattr(frappe.local, "session", None)
		if not session or session.get("user") in (None, "", "Guest") or not _is_desk_user(session):
			return
		if not get_settings()["enabled"]:
			return
		html = response.get_data(as_text=True)
		if not html or _REPORTER_MARKER in html or "</head>" not in html:
			return
		cfg = frappe.as_json({"csrf": (session.get("data") or {}).get("csrf_token") or ""}, indent=None)
		inject = (
			"<!-- %s -->"
			"<script>window.__NEXUM_IDLE__=%s;</script>"
			'<script src="/assets/my_branding/js/idle_activity.js?v=20261010a"></script>'
		) % (_REPORTER_MARKER, cfg)
		response.set_data(html.replace("</head>", inject + "</head>", 1))
	except Exception:
		frappe.logger("idle_lock").exception("activity reporter injection skipped")
