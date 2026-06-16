import frappe

from my_branding.brand_config import app_titles

# Master white-label name map: app name -> the brand display name. Derived from
# brand_config (one source of truth). Used for:
#   - the /apps switcher + navbar app dropdown  (get_apps override, below)
#   - the desk sidebar header / app-launcher group heading  (boot.boot_session)
# The in-app SPA wordmarks/titles are handled separately (spa_brand), and the
# desk launcher TILE labels via Translation overrides (branding.TRANSLATIONS).
#
# We override get_apps rather than Translation-ing the titles, because several of
# them are bare common words ("Drive", "Builder", "Learning", "ERPNext", "CRM")
# that appear all over the UI — a global Translation would corrupt unrelated text.
# Overriding get_apps scopes the rename to exactly the apps screen.
APP_TITLES = app_titles()

# Per-app teal launcher icons (Nexum Air squircles in public/images/icons/). The
# frappe-ui SPA app-switcher (the in-app "Apps" dropdown) renders each app's
# `logo` from get_apps DIRECTLY and never loads brand.css — so the CSS icon-swaps
# don't reach it. Rewriting `logo` here rebrands those icons at the source, which
# also covers the /apps switcher + navbar dropdown.
ICON = "/assets/my_branding/images/icons/%s"
APP_LOGOS = {
	"erpnext": ICON % "erpnext_app.svg",
	"hrms": ICON % "hrms_app.svg",
	"crm": ICON % "crm_app2.svg",
	"gameplan": ICON % "gameplan_app2.svg",
	"builder": ICON % "builder_app.svg",
	"helpdesk": ICON % "helpdesk_app.svg",
	"lms": ICON % "lms_app2.svg",
	"drive": ICON % "drive_app.svg",
	"slides": ICON % "slides_app.svg",
	"insights": ICON % "insights_app.svg",
	"lending": ICON % "lending_app.svg",
}
# Automatic on-brand fallback: ANY app without a hand-made icon above gets this
# generic Nexum Air slate squircle, so a newly-adopted Frappe app never shows its
# raw Frappe-coloured logo in the apps screen. Add the app to APP_LOGOS later to
# give it a bespoke glyph.
DEFAULT_LOGO = ICON % "_default_app.svg"


def can_access_insights():
	"""True only if the CURRENT user can actually open the Insights SPA.

	Insights ships no `add_to_apps_screen` hook, so it bypasses get_apps'/boot's
	normal permission filtering and we add its tile by hand — but its own
	`get_user_info` 403s for anyone WITHOUT an Insights role (System Manager alone
	is NOT enough), and the SPA renders a blank page on that 403. So a user without
	the role must not be shown the tile at all. Administrator implicitly holds every
	role. Hardened: on any error hide the tile (a missing tile beats a dead link)."""
	try:
		return any(r.startswith("Insights") for r in frappe.get_roles())
	except Exception:
		return False


@frappe.whitelist()
def get_apps():
	"""override_whitelisted_methods for frappe.apps.get_apps — relabel the apps
	screen to the Nexum Air names + teal icons. Calls the real implementation (the
	function object, not the whitelisted path, so there's no recursion) and
	rewrites the display `title` and `logo`; `name`/`route` are untouched so
	routing is unaffected. Hardened: on any error fall back to the original list."""
	from frappe.apps import get_apps as _get_apps

	apps = _get_apps()
	try:
		for app in apps:
			new_title = APP_TITLES.get(app.get("name"))
			if new_title:
				app["title"] = new_title
			# custom icon if we have one, else the generic on-brand squircle so
			# any new/unmapped app auto-rebrands (never raw Frappe colours).
			app["logo"] = APP_LOGOS.get(app.get("name")) or DEFAULT_LOGO

		# Insights ships no `add_to_apps_screen` hook, so the stock apps screen
		# never lists it. Add it here (teal icon + branded title) when installed
		# and the user can access it, so it appears alongside the other apps.
		# The access gate matters: without an Insights role the SPA 403s to a
		# blank page, so a user who can't open it must not see the tile.
		if (
			"insights" in frappe.get_installed_apps()
			and can_access_insights()
			and not any(a.get("name") == "insights" for a in apps)
		):
			apps.append(
				{
					"name": "insights",
					"logo": "/assets/my_branding/images/icons/insights_app.svg",
					"title": APP_TITLES.get("insights") or "Insights",
					"route": "/insights",
				}
			)
	except Exception:
		frappe.log_error(title="my_branding get_apps relabel failed", message=frappe.get_traceback())
	return apps


# Builder ships its OWN apps endpoint (builder.api.get_apps) that bypasses
# frappe.apps.get_apps, prepends a "Desk" entry, and lists "ERPNext" with stock
# logos. Override it too: rebrand the two ERPNext-jargon titles + teal logos.
BUILDER_TITLE_OVERRIDES = {"frappe": "Home", "erpnext": "Nexum Air"}


@frappe.whitelist()
def builder_get_apps():
	"""override_whitelisted_methods for builder.api.get_apps — relabel "Desk"->
	"Home" and "ERPNext"->"Nexum Air" and swap to teal logos. Hardened: on any
	error fall back to Builder's original list."""
	from builder.api import get_apps as _builder_get_apps

	apps = _builder_get_apps()
	try:
		for app in apps:
			name = app.get("name")
			logo = APP_LOGOS.get(name) or (APP_LOGOS["erpnext"] if name == "frappe" else None)
			if logo:
				app["logo"] = logo
			new_title = BUILDER_TITLE_OVERRIDES.get(name) or APP_TITLES.get(name)
			if new_title:
				app["title"] = new_title
	except Exception:
		frappe.log_error(title="my_branding builder_get_apps relabel failed", message=frappe.get_traceback())
	return apps
