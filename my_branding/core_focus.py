"""Core-ERP focus (2026-08-24 owner decision).

The product sells only core ERP + core-support: frappe, erpnext, hrms, crm,
payments, print_designer, eam, my_branding. Everything else is NON-CORE:

  - INTERNAL_TOOL_APPS (helpdesk, insights, drive, gameplan) stay visible ONLY on
    Nexum Air's own internal sites — gated by site_config `nx_internal_tools`
    (set on hq) — where they render as a trailing "Internal Tools" launcher
    section (branding.launcher_sections), i.e. the "footer apps".
  - The rest (lms, builder, slides, webshop, ecommerce_integrations, lending,
    telephony) are hidden EVERYWHERE.

Existing tenant sites still have non-core apps *installed* (uninstalls are
Phase 3 of the refocus); this module hides every surface they'd show on:
Desktop Icon launcher tiles, desk workspaces, the /apps switcher + navbar
dropdown + SPA "Apps" dropdowns (naming.get_apps), and the boot app_data tiles
(boot.boot_session). Sites that never had the apps installed no-op throughout.
"""

import frappe

NON_CORE_APPS = frozenset(
	{
		"helpdesk",
		"insights",
		"drive",
		"gameplan",
		"lms",
		"builder",
		"slides",
		"webshop",
		"ecommerce_integrations",
		"lending",
		"telephony",
	}
)

# Shown on internal (nx_internal_tools) sites only — the "footer apps".
INTERNAL_TOOL_APPS = frozenset({"helpdesk", "insights", "drive", "gameplan"})

# Desktop-Icon / launcher-tile labels each non-core app surfaces as (the icon's
# `app` field is the primary hide key; labels are the belt-and-suspenders for
# rows whose `app` points elsewhere — e.g. a workspace-derived tile).
APP_LABELS = {
	"helpdesk": ["Helpdesk"],
	"insights": ["Insights"],
	"drive": ["Frappe Drive"],
	"gameplan": ["Teams", "Gameplan"],
	"lms": ["Frappe Learning", "Learning"],
	"builder": ["Frappe Builder"],
	"slides": ["Slides"],
	"webshop": ["Online Store"],
	"lending": ["Lending"],
}

# Desk workspaces owned by non-core apps. Hidden together with their tiles so a
# visible tile can never point at a hidden workspace (the 2026-08-22 demo
# "No permission for Page" bug class) — and vice versa.
APP_WORKSPACES = {"lending": ["Lending"], "webshop": ["Online Store"]}

# The trailing launcher section internal sites get (branding.launcher_sections).
INTERNAL_SECTION = {
	"title": "Internal Tools",
	"labels": ["Helpdesk", "Insights", "Frappe Drive", "Teams"],
}


def internal_tools_site():
	"""True on Nexum Air's own sites (hq): site_config `nx_internal_tools`."""
	try:
		return bool(frappe.conf.get("nx_internal_tools"))
	except Exception:
		return False


def hidden_apps():
	"""The non-core apps hidden on THIS site. Hardened: unknown -> hide all
	non-core (a missing internal tool on hq beats a leaked one on a tenant)."""
	try:
		if internal_tools_site():
			return NON_CORE_APPS - INTERNAL_TOOL_APPS
		return NON_CORE_APPS
	except Exception:
		return NON_CORE_APPS


def hidden_labels():
	"""Launcher-tile labels hidden on THIS site (for launcher_sections)."""
	return {label for app in hidden_apps() for label in APP_LABELS.get(app, ())}


def reconcile_core_focus():
	"""after_migrate: stamp core-focus visibility onto Desktop Icons + Workspaces.

	Bidirectional and idempotent: hides every surface of a hidden app, and
	un-hides internal tools on an internal site (so flipping `nx_internal_tools`
	reconciles cleanly either way on the next migrate). Runs AFTER
	reconcile_workspace_visibility (which unhides Lending for the tile it used
	to dead-link — here we hide tile AND workspace together) and BEFORE the
	framework-visibility/order reconcilers (hooks order), so ordering sees the
	final hidden state. Hardened so it can never abort a migrate."""
	try:
		if not frappe.db.table_exists("Desktop Icon"):
			return
		hidden = hidden_apps()
		for app in sorted(NON_CORE_APPS):
			target = 1 if app in hidden else 0
			names = set(frappe.get_all("Desktop Icon", filters={"app": app}, pluck="name"))
			for label in APP_LABELS.get(app, ()):
				names.update(frappe.get_all("Desktop Icon", filters={"label": label}, pluck="name"))
			for name in names:
				if frappe.db.get_value("Desktop Icon", name, "hidden") != target:
					frappe.db.set_value("Desktop Icon", name, "hidden", target, update_modified=False)

		if frappe.db.table_exists("Workspace"):
			for app, workspaces in APP_WORKSPACES.items():
				target = 1 if app in hidden else 0
				for ws in workspaces:
					if frappe.db.exists("Workspace", ws) and frappe.db.get_value(
						"Workspace", ws, "is_hidden"
					) != target:
						frappe.db.set_value("Workspace", ws, "is_hidden", target, update_modified=False)

		try:
			frappe.cache.delete_key("desktop_icons")
			frappe.cache.delete_key("bootinfo")
		except Exception:
			pass
	except Exception:
		frappe.log_error(title="my_branding reconcile_core_focus failed", message=frappe.get_traceback())
