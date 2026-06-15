# =============================================================================
# THE single source of truth for the white-label brand.
#
# To rebrand to a totally new name/colour:
#   1. Edit the values in this file (BRAND, the per-app suffixes, the palette).
#   2. (Optional) drop new logo artwork in public/images/ (see scripts/REBRAND.md).
#   3. Run  scripts/rebrand.sh   — it stamps the new name + palette into the
#      static assets (CSS / JS / icon SVGs / fixtures) and prints the deploy steps.
#   4. Run the reconcile hooks + restart (rebrand.sh prints the exact commands).
#
# The Python layer (naming.py / branding.py / spa_brand.py / boot.py) DERIVES
# everything below at runtime, so those need no editing on a rebrand — only this
# file + the static-asset stamp.
#
# Keep this module dependency-free (no `import frappe`) so it can be imported
# anywhere and parsed by rebrand.sh.
# =============================================================================

# 1. The brand word that replaces "Frappe"/"ERPNext" across the product.
BRAND = "Nexum Air"

# 2. Per-app product naming. For each Frappe app:
#      suffix  : appended after BRAND for the display name ("" -> just BRAND)
#      display : OPTIONAL explicit display name; overrides the BRAND+suffix form.
#                Used so launcher tiles read clean functional names ("CRM", not
#                "Nexum Air CRM") while Nexum Air stays the product brand. It still
#                removes "Frappe" via `native`. Set to None to use BRAND+suffix.
#      native  : the "Frappe X" string that app ships (the match target we replace;
#                this is Frappe's string, so it does NOT change on a rebrand)
#      route   : the SPA route to brand (None for desk-only apps like erpnext)
APPS = {
	# the framework itself: deep desk screens (Settings groups, module breadcrumbs,
	# Installed Applications) render its app_title "Frappe Framework" — brand it too.
	# "Framework" matches the launcher tile label in DESKTOP_ICON_ORDER.
	"frappe":   {"suffix": "Framework", "display": "Framework", "native": "Frappe Framework", "route": None},
	"erpnext":  {"suffix": "",         "display": None,       "native": None,              "route": None},
	"hrms":     {"suffix": "HR",       "display": "HR",       "native": "Frappe HR",       "route": "/hrms"},
	"crm":      {"suffix": "CRM",      "display": "CRM",      "native": "Frappe CRM",      "route": "/crm"},
	"helpdesk": {"suffix": "Helpdesk", "display": "Helpdesk", "native": "Frappe Helpdesk", "route": "/helpdesk"},
	"drive":    {"suffix": "Drive",    "display": "Drive",    "native": "Frappe Drive",    "route": "/drive"},
	"insights": {"suffix": "Insights", "display": "Insights", "native": "Frappe Insights", "route": "/insights", "extra_swaps": [["ERPNext", "Nexum Air"]]},
	"builder":  {"suffix": "Builder",  "display": "Builder",  "native": "Frappe Builder",  "route": "/builder"},
	"lms":      {"suffix": "Learning", "display": "Learning", "native": "Frappe Learning", "route": "/lms"},
	"gameplan": {"suffix": "Teams",    "display": "Teams",    "native": "Frappe Gameplan", "route": "/g", "extra_swaps": [["Gameplan", "Teams"]]},
	"slides":   {"suffix": "Slides",   "display": "Slides",   "native": None,              "route": "/slides"},
}

# 3. Colour palette. ALSO stamped into the static CSS + icon SVGs by rebrand.sh
#    (the Python layer doesn't use these — they're here so the palette has one home).
PRIMARY         = "#2E5562"  # solid brand colour (links, buttons, active states)
PRIMARY_DARKEST = "#1C2B30"  # pressed/active
GRADIENT_START  = "#2E5562"  # squircle gradient stops (dark -> mid -> light)
GRADIENT_MID    = "#557E94"
GRADIENT_END    = "#9DBEC8"  # also the "light" tint used on dark surfaces

# 4. Where the desk "Support" help link points.
SUPPORT_ROUTE = "/helpdesk"

# 5. Frappe's native "Support" link label (the match target) — not ours.
SUPPORT_NATIVE = "Frappe Support"


# --- derived helpers (do not edit) ------------------------------------------
def branded_name(app):
	"""Always the BRAND-prefixed form, e.g. 'Nexum Air' (erpnext) / 'Nexum Air HR'
	(hrms). Used for the in-app SPA wordmarks where we keep the full brand."""
	cfg = APPS.get(app) or {}
	suffix = cfg.get("suffix")
	return ("%s %s" % (BRAND, suffix)).strip() if suffix else BRAND


def display_name(app):
	"""Launcher / desk tile name. Honours an explicit `display` override (clean
	functional name like 'CRM'); otherwise falls back to the BRAND-prefixed form."""
	cfg = APPS.get(app) or {}
	if cfg.get("display") is not None:
		return cfg["display"]
	return branded_name(app)


def app_titles():
	"""app -> display name. For naming.APP_TITLES (apps switcher + desk header)."""
	return {app: display_name(app) for app in APPS}


def native_to_brand():
	"""'Frappe HR' -> 'Nexum Air HR', plus the Support label. For the desk
	Translation overrides (branding.TRANSLATIONS)."""
	out = {}
	for app, cfg in APPS.items():
		if cfg.get("native"):
			out[cfg["native"]] = display_name(app)
	out[SUPPORT_NATIVE] = "%s Support" % BRAND
	return out


def spa_brand():
	"""route -> {name, old, extra}. For spa_brand.SPA_BRAND (the in-SPA injection).
	Uses the BRAND-prefixed name so the in-app wordmark stays 'Nexum Air HR' etc.
	`extra` is an optional list of [from, to] text swaps (e.g. Insights mentions
	'ERPNext' in its data-source picker -> 'Nexum Air')."""
	out = {}
	for app, cfg in APPS.items():
		if cfg.get("route"):
			out[cfg["route"]] = {
				"name": branded_name(app),
				"old": cfg.get("native"),
				"extra": cfg.get("extra_swaps") or [],
			}
	return out


# Common derived names. The Settings workspace tile reads plain "Settings"
# (Nexum Air stays the product brand, not a per-tile prefix).
SETTINGS_WORKSPACE = "Settings"
