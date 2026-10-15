import frappe

# Shared white-label name map (one source of truth — see naming.py). Rebrands the
# app titles shown in the desk (sidebar header + app-launcher group heading); the
# same map relabels the /apps switcher via the get_apps override.
from my_branding.naming import APP_LOGOS, APP_TITLES, can_access_insights


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
		# Core-focus 2026-08-24: hidden apps must not surface launcher tiles from
		# app_data either — the launcher skips any app whose app_route is empty.
		try:
			from my_branding.core_focus import hidden_apps

			_hidden = hidden_apps()
		except Exception:
			_hidden = frozenset()
		for app in bootinfo.get("app_data") or []:
			if isinstance(app, dict):
				if app.get("app_name") in _hidden:
					app["app_route"] = ""
				new_title = APP_TITLES.get(app.get("app_name"))
				if new_title:
					app["app_title"] = new_title
				# Apps mode and the dock read app_data directly, bypassing get_apps
				# and the legacy Desktop Icon fixtures. Reuse the same brand assets.
				logo = APP_LOGOS.get(app.get("app_name"))
				if logo:
					app["app_logo_url"] = logo
				# Insights ships no `add_to_apps_screen` hook and has no desk
				# workspace, so boot leaves its app_route empty and the launcher
				# skips the tile. Give it a route + teal logo so it shows like the
				# other apps — but ONLY for users who can actually open it. Without
				# an Insights role the SPA 403s to a blank page, so for everyone else
				# we leave app_route empty and the launcher skips the tile.
				if app.get("app_name") == "insights" and "insights" not in _hidden and can_access_insights():
					if not app.get("app_route"):
						app["app_route"] = "/insights"
					app["app_logo_url"] = "/assets/my_branding/images/icons/insights_app.svg?v=c1"
	except Exception:
		frappe.log_error(title="my_branding boot_session failed", message=frappe.get_traceback())

	try:
		# Per-site sections (core-focus): tenant sites get the core layout; internal
		# sites (nx_internal_tools) also get the trailing "Internal Tools" section.
		from my_branding.branding import launcher_sections as _launcher_sections

		bootinfo.nexumair_launcher_sections = _launcher_sections()
	except Exception:
		frappe.log_error(
			title="my_branding launcher sections bootinfo failed",
			message=frappe.get_traceback(),
		)

	# Getting-started panels: tell brand.js which checklists can only be hidden, so it
	# skips the get_checklist round trip on Home/Accounting/Selling/Stock visits.
	try:
		from my_branding.home import checklist_boot

		bootinfo.nx_checklists = checklist_boot()
	except Exception:
		frappe.log_error(title="my_branding checklist bootinfo failed", message=frappe.get_traceback())

	# UX plan 2026-08-23: plan + simple-mode flags read by the gated depends_on
	# property setters (simple_mode.py) and brand.js (report presets, form toggle).
	try:
		from my_branding.simple_mode import boot as _simple_mode_boot

		_simple_mode_boot(bootinfo)
	except Exception:
		frappe.log_error(title="my_branding simple_mode bootinfo failed", message=frappe.get_traceback())

	# Idle screen lock settings for idle_lock.js (see idle_lock.py). On failure the
	# script falls back to on / 3 minutes, matching the server's fail-closed default.
	try:
		from my_branding.idle_lock import get_settings as _idle_settings

		bootinfo.nexum_idle_lock = _idle_settings()
	except Exception:
		frappe.log_error(title="my_branding idle lock bootinfo failed", message=frappe.get_traceback())
