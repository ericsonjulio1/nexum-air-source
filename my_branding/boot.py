import frappe

# Shared white-label name map (one source of truth — see naming.py). Rebrands the
# app titles shown in the desk (sidebar header + app-launcher group heading); the
# same map relabels the /apps switcher via the get_apps override.
from my_branding.naming import APP_TITLES, can_access_insights


def boot_session(bootinfo):
	"""extend_bootinfo: rebrand app titles shown in the desk.

	The sidebar header subtitle and the app-launcher group heading are
	`app.app_title` from `bootinfo.app_data`, sourced from each app's `app_title`
	hook (erpnext -> "ERPNext", hrms -> "Frappe HR"). We rewrite them here (runs
	every session, so it survives app updates).

	This runs on every desk load, so it's wrapped: a failure can never break the
	boot — worst case a title falls back to its native value for that session.
	"""
	try:
		for app in bootinfo.get("app_data") or []:
			if isinstance(app, dict):
				new_title = APP_TITLES.get(app.get("app_name"))
				if new_title:
					app["app_title"] = new_title
				# Insights ships no `add_to_apps_screen` hook and has no desk
				# workspace, so boot leaves its app_route empty and the launcher
				# skips the tile. Give it a route + teal logo so it shows like the
				# other apps — but ONLY for users who can actually open it. Without
				# an Insights role the SPA 403s to a blank page, so for everyone else
				# we leave app_route empty and the launcher skips the tile.
				if app.get("app_name") == "insights" and can_access_insights():
					if not app.get("app_route"):
						app["app_route"] = "/insights"
					app["app_logo_url"] = "/assets/my_branding/images/icons/insights_app.svg"
	except Exception:
		frappe.log_error(title="my_branding boot_session failed", message=frappe.get_traceback())
