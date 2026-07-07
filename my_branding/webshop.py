"""Make the Online Store (Frappe Webshop) discoverable on the desk.

Webshop is a WEBSITE app — it ships no desk workspace or launcher tile, so on
Enterprise tenants the store is invisible from /app even though it's installed
(the customer-facing storefront lives at /all-products). This after_migrate hook
surfaces it in THREE places, each with its own gate (learned the hard way —
see the per-helper comments), so the store shows on both the modern /app
workspace nav AND the legacy /desk module grid:

  1. an "Online Store" Workspace (shortcuts to Webshop Settings, the product
     catalogue, and the live storefront);
  2. a "Workspace Sidebar" doc named "Online Store" — REQUIRED for the legacy
     /desk Link tile to pass its permission check (see _ensure_desktop_icon);
  3. a top-level Desktop Icon (the /desk launcher tile) with the brand
     storefront glyph.

Only acts where webshop is installed (Enterprise plan). Idempotent + SELF-HEALING
(repairs icons created by older versions of this file) + hardened so it can never
abort a migrate. Mirrors branding.ensure_settings_desktop_icon.
"""

import json

import frappe

_WS = "Online Store"
_STOREFRONT = "/all-products"
_LOGO = "/assets/my_branding/images/icons/online-store.svg"
_ROUTE = "/app/online-store"


def _ensure_workspace():
	if frappe.db.exists("Workspace", _WS):
		return
	h = lambda: frappe.generate_hash(length=10)
	shortcuts = [
		{"type": "DocType", "link_to": "Webshop Settings", "label": "Webshop Settings", "color": "Grey"},
		{"type": "DocType", "link_to": "Website Item", "label": "Products", "color": "Grey", "doc_view": "List"},
		{"type": "URL", "url": _STOREFRONT, "label": "View Storefront", "color": "Grey"},
	]
	links = [
		{"type": "Card Break", "label": "Online Store", "link_count": 4, "hidden": 0, "onboard": 0, "is_query_report": 0},
		{"type": "Link", "label": "Webshop Settings", "link_to": "Webshop Settings", "link_type": "DocType", "hidden": 0, "onboard": 0, "is_query_report": 0, "link_count": 0},
		{"type": "Link", "label": "Products (Website Item)", "link_to": "Website Item", "link_type": "DocType", "hidden": 0, "onboard": 0, "is_query_report": 0, "link_count": 0},
		{"type": "Link", "label": "Item Group", "link_to": "Item Group", "link_type": "DocType", "hidden": 0, "onboard": 0, "is_query_report": 0, "link_count": 0},
		{"type": "Link", "label": "Website Settings", "link_to": "Website Settings", "link_type": "DocType", "hidden": 0, "onboard": 0, "is_query_report": 0, "link_count": 0},
	]
	content = [
		{"id": h(), "type": "header", "data": {"text": '<span class="h4"><b>Online Store</b></span>', "col": 12}},
		{"id": h(), "type": "shortcut", "data": {"shortcut_name": "Webshop Settings", "col": 4}},
		{"id": h(), "type": "shortcut", "data": {"shortcut_name": "Products", "col": 4}},
		{"id": h(), "type": "shortcut", "data": {"shortcut_name": "View Storefront", "col": 4}},
		{"id": h(), "type": "card", "data": {"card_name": "Online Store", "col": 4}},
	]
	ws = frappe.new_doc("Workspace")
	ws.title = _WS
	ws.label = _WS
	ws.public = 1
	ws.icon = "retail"
	# Own the workspace under the webshop app so the v16 desk launcher (which
	# groups workspaces by their app and DROPS any app-less/module-less page)
	# renders the tile. Setting module is enough — Workspace.validate resolves
	# app="webshop" via get_module_app. Without this the workspace exists but
	# never appears in the apps grid.
	ws.module = "Webshop"
	ws.content = json.dumps(content)
	for s in shortcuts:
		ws.append("shortcuts", s)
	for l in links:
		ws.append("links", l)
	ws.insert(ignore_permissions=True)


def _ensure_sidebar():
	"""Create a "Workspace Sidebar" doc named "Online Store".

	The legacy /desk launcher renders a Link-type Desktop Icon only if its label
	(lowercased) is a key in boot's workspace_sidebar_item map — and that map is
	keyed by Workspace Sidebar names (every visible /desk Link tile, e.g. Selling
	/ Lending / Subcontracting, has a matching Workspace Sidebar doc). Webshop
	only gets an AUTO-generated sidebar keyed by its module ("webshop"), so a tile
	labelled "Online Store" finds no key and is silently dropped. Creating this
	doc registers the "online store" key, mirroring how the stock modules work.
	"""
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return
	if frappe.db.exists("Workspace Sidebar", _WS):
		return
	sb = frappe.new_doc("Workspace Sidebar")
	sb.title = _WS
	sb.header_icon = "retail"
	sb.module = "Webshop"
	sb.app = "webshop"
	sb.standard = 0
	sb.append(
		"items",
		{"label": "Home", "link_type": "Workspace", "icon": "retail", "type": "Link", "link_to": _WS, "collapsible": 1},
	)
	sb.insert(ignore_permissions=True)


def _ensure_desktop_icon():
	if not frappe.db.table_exists("Desktop Icon"):
		return
	# never create a launcher tile that routes to a missing workspace
	if not frappe.db.exists("Workspace", _WS):
		return
	# Fields that make the icon a TOP-LEVEL /desk tile with the brand glyph.
	# parent_icon MUST be empty: an icon nested under another (older versions set
	# it to the ERPNext app icon) renders inside that parent, never on the top
	# grid. logo_url drives the tile glyph (the `icon` sprite name is a fallback;
	# without a logo_url the tile degrades to a letter avatar).
	want = {
		"link_type": "External",
		"icon_type": "Link",
		"link": _ROUTE,
		"icon": "retail",
		"logo_url": _LOGO,
		"app": "erpnext",
		"parent_icon": None,
		"hidden": 0,
		"standard": 1,
		# Position the tile next to the Lending app on the /desk grid (Lending=150,
		# Drive=160 — 155 slots it between them). Tiles render in idx order.
		"idx": 155,
	}
	existing = frappe.db.get_value("Desktop Icon", {"label": _WS}, "name")
	if existing:
		# self-heal icons created by older versions of this file (nested / no glyph
		# / wrong position)
		frappe.db.set_value("Desktop Icon", existing, want)
		return
	icon = frappe.new_doc("Desktop Icon")
	icon.update({"label": _WS, **want})
	icon.insert(ignore_permissions=True)
	# Desktop Icon auto-assigns idx on insert; force our slot afterwards.
	frappe.db.set_value("Desktop Icon", icon.name, "idx", 155)


def ensure_online_store_workspace():
	"""after_migrate: surface the Online Store (webshop) on the desk. No-op unless
	webshop is installed (Enterprise plan). Idempotent + self-healing + hardened so
	it can never abort a migrate."""
	if not frappe.db.table_exists("Workspace"):
		return
	try:
		if "webshop" not in frappe.get_installed_apps():
			return
		_ensure_workspace()
		_ensure_sidebar()
		_ensure_desktop_icon()
	except Exception:
		frappe.log_error(
			title="my_branding ensure_online_store_workspace failed",
			message=frappe.get_traceback(),
		)
