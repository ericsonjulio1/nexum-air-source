import frappe

from my_branding import brand_config

# ERPNext ships the Settings workspace as several standard docs that all carry
# the label "ERPNext Settings" and get re-synced on every `bench migrate`:
#   - Workspace          (erpnext/setup/workspace/erpnext_settings/...)
#   - Workspace Sidebar  (erpnext/workspace_sidebar/erpnext_settings.json)
#   - Desktop Icon       (generated; its `label` is what the launcher grid shows)
# We rebrand all of them to the brand's "<Brand> Settings" and drop the duplicates
# the standard sync recreates, so the rename survives migrations.
OLD_WORKSPACE = "ERPNext Settings"
NEW_WORKSPACE = brand_config.SETTINGS_WORKSPACE

# doctype -> fields that should be set to the new label on the surviving doc
_DERIVED = {
	"Workspace": ["label", "title"],
	"Workspace Sidebar": ["label", "title"],
	"Desktop Icon": ["label", "link_to"],
}


def _rename_or_dedupe(doctype):
	"""Ensure NEW exists and OLD doesn't for a doctype keyed by the label."""
	if not frappe.db.table_exists(doctype):
		return
	has_old = frappe.db.exists(doctype, OLD_WORKSPACE)
	has_new = frappe.db.exists(doctype, NEW_WORKSPACE)
	if has_old and has_new:
		# standard sync recreated the original — drop it, keep the branded one
		frappe.delete_doc(
			doctype, OLD_WORKSPACE, force=True, ignore_permissions=True, ignore_missing=True
		)
	elif has_old and not has_new:
		frappe.rename_doc(doctype, OLD_WORKSPACE, NEW_WORKSPACE, force=True)


def _set_labels(doctype, fields):
	if not (frappe.db.table_exists(doctype) and frappe.db.exists(doctype, NEW_WORKSPACE)):
		return
	meta = frappe.get_meta(doctype)
	vals = {f: NEW_WORKSPACE for f in fields if meta.has_field(f)}
	if vals:
		frappe.db.set_value(doctype, NEW_WORKSPACE, vals, update_modified=False)


# Desk-wide string overrides applied via the Translation doctype. The desk
# renders app names through `_()` (e.g. the app launcher reads each app's
# `add_to_apps_screen` title — HRMS ships "Frappe HR"), so a Translation row
# retitles them everywhere the desk shows that string, with no app-source edits.
# (The standalone frappe-ui SPAs use their OWN i18n and are handled separately in
# my_branding.spa_brand / spa-brand.js.)
# "Frappe X" -> "<Brand> X" for every app's native string + the Support label.
# Derived from brand_config (one source of truth). These render the desk launcher
# TILE labels (Desktop Icons) and the "Support" help link via Frappe's `_()`.
#
# EXTRA: exact-match strings that aren't "Frappe X" forms. Safe to Translation
# (unlike bare common words such as "Drive"/"Builder" — see naming.py): a
# Translation only fires when the WHOLE rendered string equals the source, and
# these exact strings are always the brand leak (deep settings screens, module
# lists, Installed Applications).
EXTRA_TRANSLATIONS = {
	"ERPNext": brand_config.display_name("erpnext"),
	"ERPNext Integrations": "%s Integrations" % brand_config.display_name("erpnext"),
	# The classic CRM/Support workspaces render a "Switch to Frappe CRM/Helpdesk"
	# sidebar button (client-side __()); exact-match Translations relabel them.
	"Switch to Frappe CRM": "Switch to CRM",
	"Switch to Frappe Helpdesk": "Switch to Helpdesk",
}
TRANSLATIONS = {**brand_config.native_to_brand(), **EXTRA_TRANSLATIONS}

# Frappe ships a standard "Frappe Support" navbar help item pointing at its OWN
# external support site (https://frappe.io/support) — wrong on both counts for a
# white-label deploy. We rebrand the label via TRANSLATIONS above and repoint the
# URL here to our own Helpdesk so the link can never send customers to frappe.io.
# (We leave the DB item_label as "Frappe Support" so the standard navbar sync
# doesn't re-add a duplicate; the label is fixed at render time by the Translation.)
SUPPORT_ROUTE = brand_config.SUPPORT_ROUTE


def ensure_translations():
	"""after_migrate: ensure the desk string overrides exist (idempotent).

	Wrapped so it can never abort a `bench migrate`; worst case an override is
	skipped and retried next migrate.
	"""
	if not frappe.db.table_exists("Translation"):
		return
	for source, target in TRANSLATIONS.items():
		try:
			existing = frappe.db.get_value(
				"Translation",
				{"language": "en", "source_text": source},
				["name", "translated_text"],
			)
			if existing:
				name, current = existing
				if current != target:
					frappe.db.set_value("Translation", name, "translated_text", target)
			else:
				frappe.get_doc(
					{
						"doctype": "Translation",
						"language": "en",
						"source_text": source,
						"translated_text": target,
					}
				).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="my_branding ensure_translations failed",
				message=f"{source}\n{frappe.get_traceback()}",
			)


def reconcile_navbar():
	"""after_migrate: repoint the standard "Frappe Support" navbar help link from
	Frappe's external support site to our own Helpdesk.

	Wrapped so it can never abort a migrate; worst case the link keeps its old
	route and is retried next migrate.
	"""
	if not frappe.db.table_exists("Navbar Item"):
		return
	try:
		names = frappe.get_all(
			"Navbar Item", filters={"item_label": "Frappe Support"}, pluck="name"
		)
		# /helpdesk only exists where the helpdesk app is installed (batch-183, sweep
		# C30): free/starter tenants got a dead 404 Support link — point them at
		# support mail instead.
		route = (
			SUPPORT_ROUTE
			if "helpdesk" in frappe.get_installed_apps()
			else "mailto:admin@nexumair.com"
		)
		for name in names:
			frappe.db.set_value(
				"Navbar Item", name, "route", route, update_modified=False
			)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_navbar failed", message=frappe.get_traceback()
		)


def ensure_letter_heads():
	"""after_migrate: INSERT-ONLY letterhead seeding (batch-183, sweep C37) — replaces
	the unfiltered Letter Head fixture, which re-saved both shipped letterheads on
	every migrate: a tenant's content edit was silently reverted and re-saving the
	Grey one with is_default=1 stole the default back from the tenant's own choice.
	Reads the seed/letter_head.json data file; creates a letterhead only
	when a doc of that name does not exist, and claims is_default only when the
	site has no default letterhead at all. Never updates an existing doc."""
	import json
	import os

	if not frappe.db.table_exists("Letter Head"):
		return
	try:
		# Seed data lives in seed/, NOT fixtures/: frappe's sync_fixtures force-imports
		# every *.json under fixtures/ on each migrate regardless of hooks.fixtures
		# (delete + re-insert), which reverted tenant letterhead edits and re-claimed the
		# default on every deploy even after C37 moved this to an insert-only reconciler.
		path = frappe.get_app_path("my_branding", "seed", "letter_head.json")
		if not os.path.exists(path):
			return
		with open(path) as f:
			seeds = json.load(f)
		for seed in seeds:
			name = seed.get("name") or seed.get("letter_head_name")
			if not name or frappe.db.exists("Letter Head", name):
				continue
			doc = frappe.get_doc(dict(seed, doctype="Letter Head"))
			if doc.get("is_default") and frappe.db.exists("Letter Head", {"is_default": 1}):
				doc.is_default = 0  # never steal an existing default
			doc.flags.ignore_permissions = True
			doc.insert(ignore_if_duplicate=True)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_letter_heads failed", message=frappe.get_traceback()
		)


# Website Settings and Navbar Settings are tenant-editable Singles; the brand owns only
# these keys on them (M3, v204). Both used to be fixtures, and frappe's sync_fixtures
# force-imports every *.json under fixtures/ on each migrate (delete + re-insert of the
# whole Single), so every deploy wiped the tenant's top bar and footer items, Google
# Analytics id, head_html, route redirects, website theme, help items and announcement.
# The shipped values now live in seed/ and only these keys are re-applied. app_name
# always follows brand_config.BRAND, so a rebrand needs no stamped data. home_page belongs
# to ensure_app_landing and title_prefix to ensure_web_title_prefix.
_SITE_BRAND_KEYS = {
	"Website Settings": ("app_name", "app_logo", "disable_signup"),
	"Navbar Settings": ("app_logo",),
}
_SITE_BRAND_SEEDS = {
	"Website Settings": "website_settings.json",
	"Navbar Settings": "navbar_settings.json",
}


def site_brand_settings():
	"""``{doctype: {fieldname: value}}`` the brand owns on Website/Navbar Settings."""
	import json

	out = {}
	for doctype, keys in _SITE_BRAND_KEYS.items():
		with open(frappe.get_app_path("my_branding", "seed", _SITE_BRAND_SEEDS[doctype])) as f:
			seed = json.load(f)[0]
		out[doctype] = {key: seed[key] for key in keys if key in seed}
	out["Website Settings"]["app_name"] = brand_config.BRAND
	return out


def ensure_site_brand_settings():
	"""after_migrate: re-assert ONLY the brand-owned keys on Website Settings and Navbar
	Settings, each only when it differs (idempotent). Writes single values in place, with
	no document save, so every other field and every child table (top bar, footer,
	redirects, help and settings dropdowns) stays as the tenant left it.

	The standard help-dropdown items need no seeding here: frappe adds them at install
	(utils/install.py add_standard_navbar_items) and re-syncs them on every migrate, before
	after_migrate runs (migrate.py sync_standard_items); reconcile_navbar repoints "Frappe
	Support". Hardened so it can never abort a migrate."""
	try:
		for doctype, values in site_brand_settings().items():
			for fieldname, value in values.items():
				if frappe.db.get_single_value(doctype, fieldname, cache=False) != value:
					frappe.db.set_single_value(doctype, fieldname, value)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_site_brand_settings failed", message=frappe.get_traceback()
		)


def reconcile_workspaces():
	"""after_migrate: keep the Settings workspace + derived docs branded Nexum Air.

	This runs during the `bench migrate` that every ERPNext update triggers, so
	every step is wrapped: a failure here can NEVER abort the update. Worst case
	the rebrand is skipped and simply retried on the next migrate. Errors are
	written to the Error Log for diagnosis.
	"""
	if not frappe.db.table_exists("Workspace"):
		return

	# Rename Workspace Sidebar first so Desktop Icon's link_to is updated by the
	# rename, then the Workspace, then the Desktop Icon.
	for dt in ("Workspace Sidebar", "Workspace", "Desktop Icon"):
		try:
			_rename_or_dedupe(dt)
		except Exception:
			frappe.log_error(title="my_branding reconcile rename failed", message=f"{dt}\n{frappe.get_traceback()}")

	for dt, fields in _DERIVED.items():
		try:
			_set_labels(dt, fields)
		except Exception:
			frappe.log_error(title="my_branding reconcile relabel failed", message=f"{dt}\n{frappe.get_traceback()}")

	try:
		frappe.clear_cache()
	except Exception:
		frappe.log_error(title="my_branding reconcile clear_cache failed", message=frappe.get_traceback())


# Insights ships no `add_to_apps_screen` hook and has no desk workspace, so it
# gets no launcher Desktop Icon and never appears in the /app/desktop module grid.
# Create one (links to the /insights SPA, teal icon) modelled exactly on the
# Slides/Gameplan/Helpdesk app tiles (standard=0, icon_type=App, link_type=External).
INSIGHTS_ICON = {
	"label": "Insights",
	"app": "insights",
	"logo_url": "/assets/my_branding/images/icons/insights_app.svg?v=c1",
	"link": "/insights",
	"link_type": "External",
	"icon_type": "App",
	"standard": 0,
	"hidden": 0,
}


def ensure_insights_desktop_icon():
	"""after_migrate: make Insights show on the desk module launcher (it ships no
	registration of its own). Idempotent + hardened so it can never abort migrate."""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		if "insights" not in frappe.get_installed_apps():
			return
		existing = frappe.db.get_value("Desktop Icon", {"label": "Insights", "app": "insights"})
		if existing:
			# keep it pointed at our teal icon / route
			frappe.db.set_value(
				"Desktop Icon",
				existing,
				{
					"logo_url": INSIGHTS_ICON["logo_url"],
					"link": INSIGHTS_ICON["link"],
					"link_type": INSIGHTS_ICON["link_type"],
					"icon_type": INSIGHTS_ICON["icon_type"],
					"hidden": 0,
				},
				update_modified=False,
			)
		else:
			frappe.get_doc(dict(doctype="Desktop Icon", **INSIGHTS_ICON)).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_insights_desktop_icon failed", message=frappe.get_traceback()
		)


def ensure_maintenance_desktop_icon():
	"""Keep the legacy breadcrumb icon, with Maintenance entered through Assets.
	Owner decision 2026-10-15 supersedes the separate Operations tile. The EAM
	workspace reconciler adds the Assets card and sidebar entry in both modes.
	"""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		if "eam" not in frappe.get_installed_apps():
			return
		name = frappe.db.get_value("Desktop Icon", {"label": "Maintenance", "app": "eam"})
		if not name:
			return  # eam's fixture not synced yet — next migrate picks it up
		updates = {
			"hidden": 1,
			"logo_url": "/assets/my_branding/images/icons/maintenance.svg?v=c1",
		}
		current = frappe.db.get_value(
			"Desktop Icon", name, ["hidden", "logo_url"], as_dict=True)
		if current and (current.hidden != 1 or current.logo_url != updates["logo_url"]):
			frappe.db.set_value("Desktop Icon", name, updates, update_modified=False)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_maintenance_desktop_icon failed",
			message=frappe.get_traceback())


def ensure_settings_desktop_icon():
	"""after_migrate: the renamed "Settings" workspace is NOT a standard workspace
	name (ERPNext ships "ERPNext Settings"), so migrate's orphan-removal deletes
	its Desktop Icon every migrate. The launcher grid reads STORED Desktop Icon
	docs (get_desktop_icons doesn't derive from Workspaces), so the Settings tile
	vanishes. Recreate it from the Settings workspace (idempotent + hardened).
	Runs in after_migrate, i.e. AFTER orphan-removal, so the tile survives."""
	if not (frappe.db.table_exists("Desktop Icon") and frappe.db.table_exists("Workspace")):
		return
	try:
		label = brand_config.SETTINGS_WORKSPACE  # "Settings"
		if not frappe.db.exists("Workspace", label):
			return
		if frappe.db.exists("Desktop Icon", {"label": label}):
			return
		ws = frappe.db.get_value("Workspace", label, ["icon"], as_dict=True) or {}
		# Group under the ERPNext app icon so it lands in the same launcher grid.
		# Use an EXTERNAL link to the workspace route (/app/<scrub>) rather than a
		# "Workspace Sidebar" link_to: migrate also orphan-deletes the Settings
		# Workspace Sidebar, so a link_to would fail link validation.
		parent = frappe.db.get_value(
			"Desktop Icon", {"icon_type": "App", "app": "erpnext"}, "name"
		)
		icon = frappe.new_doc("Desktop Icon")
		icon.update(
			{
				"label": label,
				"link_type": "External",
				"icon_type": "Link",
				"link": "/app/" + frappe.scrub(label).replace("_", "-"),
				"icon": ws.get("icon") or "setting",
				"app": "erpnext",
				"parent_icon": parent,
				"standard": 1,  # show for all users (single brand.css [data-id=Settings] paints it)
			}
		)
		icon.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_settings_desktop_icon failed", message=frappe.get_traceback()
		)


def ensure_home_desktop_icon():
	"""after_migrate: make the standard Home workspace reachable from the /desk launcher.
	frappe syncs a "Home" Desktop Icon from the Home Workspace Sidebar but it lands hidden
	with no parent app, so the grid never shows it and an owner landing on the launcher
	never sees the owner-first Home (Get-set-up panel + Receivables/Payables/Cash row).
	Unhide it and group it under the ERPNext app icon (same parent as Selling/Stock) so
	it renders as the first tile of the launcher (see LAUNCHER_SECTIONS). Idempotent +
	hardened. Runs BEFORE the visibility/order reconcilers (hooks order).
	⚠️ my_branding also SHIPS the record as `my_branding/desktop_icon/home.json` (app=
	my_branding, hidden=0, parent ERPNext): migrate's orphan removal deletes any standard
	Desktop Icon whose `app` has no `<app>/desktop_icon/<name>.json` — erpnext ships its own
	(hidden=1) file, and pointing `app` at my_branding without our file got the icon
	deleted on the next migrate. This function is the belt-and-suspenders over that file."""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		if not frappe.db.exists("Desktop Icon", "Home") or not frappe.db.exists("Workspace", "Home"):
			return
		parent = frappe.db.get_value("Desktop Icon", {"icon_type": "App", "app": "erpnext"}, "name")
		row = frappe.db.get_value("Desktop Icon", "Home", ["hidden", "parent_icon", "standard", "app"], as_dict=True)
		vals = {}
		if row.hidden:
			vals["hidden"] = 0
		if parent and row.parent_icon != parent:
			vals["parent_icon"] = parent
		if not row.standard:
			vals["standard"] = 1
		# The launcher draws a tile's <img> from assets/<icon.app>/icons/desktop_icons/solid/
		# <scrub(label)>.svg (frappe.utils.get_desktop_icon); erpnext ships no home.svg, so
		# the tile fell back to the grey letter avatar (the brand.css background-image paint
		# only helps once the new CSS is loaded — the desktop app showed an "H" meanwhile).
		# my_branding ships public/icons/desktop_icons/{solid,subtle}/home.svg -> point the
		# icon's app at my_branding so it renders a real <img> like every other tile.
		if row.app != "my_branding":
			vals["app"] = "my_branding"
		if vals:
			frappe.db.set_value("Desktop Icon", "Home", vals, update_modified=False)
			frappe.cache.delete_key("desktop_icons")
		# The tile routes to the sidebar's FIRST Link item (frappe utils.get_desktop_icon
		# route) and erpnext ships the Home sidebar as Item, Home, Customer, … — so the
		# tile would open the Item list. Put the Home workspace link first (DB-level idx,
		# the sidebar is a standard doc re-synced each migrate; no doc.save -> no
		# developer-mode export). Idempotent.
		if frappe.db.table_exists("Workspace Sidebar Item"):
			rows = frappe.get_all(
				"Workspace Sidebar Item",
				filters={"parent": "Home", "parenttype": "Workspace Sidebar"},
				fields=["name", "idx", "type", "link_type", "link_to"],
				order_by="idx asc",
			)
			home_rows = [r for r in rows if r.type == "Link" and r.link_type == "Workspace" and r.link_to == "Home"]
			if home_rows and rows and rows[0].name != home_rows[0].name:
				ordered = [home_rows[0]] + [r for r in rows if r.name != home_rows[0].name]
				for i, r in enumerate(ordered, start=1):
					if r.idx != i:
						frappe.db.set_value("Workspace Sidebar Item", r.name, "idx", i, update_modified=False)
				frappe.clear_cache()
	except Exception:
		frappe.log_error(title="my_branding ensure_home_desktop_icon failed", message=frappe.get_traceback())


def ensure_owner_landing():
	"""after_migrate: land owner-type users on the owner-first Home workspace instead of the
	bare /desk launcher. frappe's get_home_page() returns the user's `default_workspace`
	URL when set (ranked above role/portal/website defaults), so the post-login redirect
	AND the bare `/` the desktop app opens both resolve to /app/home. Only users who have
	System Manager and NO default_workspace yet are touched (a user who picked another
	default keeps it; the launcher stays one click away via the Home tile / navbar)."""
	if not frappe.db.table_exists("User") or not frappe.db.exists("Workspace", "Home"):
		return
	try:
		users = frappe.get_all(
			"Has Role",
			filters={"role": "System Manager", "parenttype": "User"},
			pluck="parent",
			distinct=True,
		)
		changed = False
		for u in users:
			if u in ("Administrator", "Guest"):
				continue
			row = frappe.db.get_value("User", u, ["enabled", "user_type", "default_workspace"], as_dict=True)
			if not row or not row.enabled or row.user_type != "System User" or row.default_workspace:
				continue
			frappe.db.set_value("User", u, "default_workspace", "Home", update_modified=False)
			changed = True
		if changed:
			frappe.cache.delete_key("home_page")
	except Exception:
		frappe.log_error(title="my_branding ensure_owner_landing failed", message=frappe.get_traceback())


def ensure_gameplan_tile_label():
	"""after_migrate: the desk launcher Desktop Icon for gameplan registers the bare
	label "Gameplan" (NOT "Frappe Gameplan"), so the Translation rebrand never reaches
	it — and its controller re-derives that label from the app on every save, so a
	normal save reverts. Force it to the brand display name ("Teams") with a direct DB
	write (bypasses the controller). Idempotent + hardened so it can't abort migrate."""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		want = brand_config.display_name("gameplan")
		for name in frappe.get_all("Desktop Icon", filters={"app": "gameplan"}, pluck="name"):
			if frappe.db.get_value("Desktop Icon", name, "label") != want:
				frappe.db.set_value("Desktop Icon", name, "label", want, update_modified=False)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_gameplan_tile_label failed", message=frappe.get_traceback()
		)


def ensure_email_settings():
	"""after_migrate: outgoing tenant email is white-label. Frappe appends a
	"Sent via ERPNext" footer (linking frappe.io) to every outgoing email unless
	System Settings disables it — wrong for a white-label deploy, so turn it off
	per site. (The SMTP transport itself is global conf: mail_* keys +
	always_use_account_email_id_as_sender=1 in common_site_config — sender is
	forced to the authorized domain, original user kept as display name.)
	Idempotent + hardened so it can never abort a migrate."""
	try:
		if frappe.db.get_single_value("System Settings", "disable_standard_email_footer") != 1:
			frappe.db.set_single_value("System Settings", "disable_standard_email_footer", 1)
		# email_body.py reads frappe.db.get_default(...), NOT the Single — the two
		# only sync on a full System Settings save, so set the default explicitly.
		# NB: defaults store STRINGS ("0" is truthy!) — compare numerically.
		if frappe.utils.cint(frappe.db.get_default("disable_standard_email_footer")) != 1:
			frappe.db.set_default("disable_standard_email_footer", 1)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_email_settings failed", message=frappe.get_traceback()
		)


def ensure_app_landing():
	"""after_migrate: send the bare tenant root (``/``) into the software instead of
	the public website/marketing layer.

	Customers are handed the bare domain (welcome email, the URL they remember), but
	on a stock Frappe site ``/`` serves the WEBSITE home page, not the desk — so they
	land on a marketing-looking page rather than their ERP (EmEA's "keeps coming back
	to the landing page" feedback, 2026-06-17). Point Website Settings' home page at
	``login``: guests get the sign-in screen, and an already-authenticated user is
	bounced straight on to the desk (/app). The welcome email also deep-links to
	``/app`` directly. Idempotent + hardened so it can never abort a migrate.

	NB: this gives up the public website ROOT for tenants (fine for the services /
	boutique tenants we host). Revisit if a tenant ever needs a public marketing site
	on its own domain — they'd use a custom home page instead.
	"""
	LANDING = "login"
	# NOT frappe.db.table_exists(): a Single has no `tab` table, so that guard was always
	# False and this hook never ran. home_page only came from the Website Settings fixture,
	# and without the fixture (M3, v204) new tenants would have lost the landing.
	if not frappe.db.exists("DocType", "Website Settings"):
		return
	try:
		if frappe.db.get_single_value("Website Settings", "home_page", cache=False) != LANDING:
			frappe.db.set_single_value("Website Settings", "home_page", LANDING)
		# home page is cached (per-user) under the "home_page" key — drop it so the
		# change shows without a restart, matching the other reconcile hooks.
		try:
			frappe.cache.delete_key("home_page")
		except Exception:
			pass
	except Exception:
		frappe.log_error(
			title="my_branding ensure_app_landing failed", message=frappe.get_traceback()
		)


def reconcile_app_workspace_labels():
	"""after_migrate: public Workspaces shipped by the apps still carry "Frappe X"
	LABELS ("Frappe CRM", "Frappe Builder") that the desk sidebar renders verbatim
	(workspace labels don't pass through `_()`, so the Translation rebrand never
	reaches them). Set label/title to the brand display name while KEEPING the doc
	name — renaming the doc would break the standard-workspace sync match and the
	/app/<route> URLs. Idempotent + hardened so it can never abort a migrate."""
	if not frappe.db.table_exists("Workspace"):
		return
	try:
		meta = frappe.get_meta("Workspace")
		fields = [f for f in ("label", "title") if meta.has_field(f)]
		# Workspace.label has a UNIQUE constraint and ERPNext's classic desk already
		# ships e.g. a "CRM" workspace (Lead/Opportunity module) — so the clean
		# display names would collide. Use the full branded form ("Nexum Air CRM"),
		# which is collision-free and tells the two apart in the sidebar.
		labels = {
			cfg["native"]: brand_config.branded_name(app)
			for app, cfg in brand_config.APPS.items()
			if cfg.get("native")
		}
		for native, branded in labels.items():
			# key on the LABEL (what the sidebar renders) — the doc name may differ
			for name in frappe.get_all("Workspace", filters={"label": native}, pluck="name"):
				try:
					frappe.db.set_value(
						"Workspace", name, {f: branded for f in fields}, update_modified=False
					)
				except Exception:
					frappe.log_error(
						title="my_branding workspace relabel failed",
						message=f"{name} -> {branded}\n{frappe.get_traceback()}",
					)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_app_workspace_labels failed", message=frappe.get_traceback()
		)


def reconcile_lms_admin_workspace():
	"""after_migrate: the LMS app puts TWO launcher tiles that both read "Learning"
	— the app tile "Frappe Learning" (-> /lms, the learner SPA) and its desk
	WORKSPACE tile (-> /desk/lms-course), which is really the course-admin / records
	view. We differentiate the workspace tile in the ASSET layer instead of the
	data: brand.css paints it a distinct records icon and brand.js relabels its
	caption to "Learning Admin".

	The Desktop Icon `label` MUST stay "Learning": frappe's launcher gates a
	workspace-link tile on `bootinfo.workspace_sidebar_item.get(icon.label.lower())`
	(get_desktop_icons), and `create_desktop_icons_from_workspace` sets that label to
	the workspace NAME — so any other label makes the tile vanish entirely (learned
	the hard way in v16-prod-111). So here we only HEAL the label back to "Learning"
	if a prior build changed it, and set the Workspace `title` (the header shown when
	the workspace is opened) to "Learning Admin". Idempotent + hardened; can never
	abort a migrate."""
	try:
		# HEAL: the launcher tile must carry label == workspace name "Learning".
		if frappe.db.table_exists("Desktop Icon") and frappe.db.exists("Desktop Icon", "Learning"):
			if frappe.db.get_value("Desktop Icon", "Learning", "label") != "Learning":
				frappe.db.set_value("Desktop Icon", "Learning", "label", "Learning", update_modified=False)
		if frappe.db.table_exists("Workspace") and frappe.db.exists("Workspace", "Learning"):
			meta = frappe.get_meta("Workspace")
			vals = {}
			if meta.has_field("label") and frappe.db.get_value("Workspace", "Learning", "label") != "Learning":
				vals["label"] = "Learning"  # keep label == name; header rename is via `title`
			if meta.has_field("title"):
				vals["title"] = "Learning Admin"
			if vals:
				frappe.db.set_value("Workspace", "Learning", vals, update_modified=False)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_lms_admin_workspace failed",
			message=frappe.get_traceback(),
		)


def _is_frappe_leak_block(text):
	"""True only for the specific Frappe-brand paragraph leaks that standard
	workspaces re-ship on migrate — the classic CRM/Support "deprecated, use Frappe
	CRM/Helpdesk instead" banner, and Learning's docs.frappe.io link. A tenant's own
	paragraph that merely cites a frappe.io URL is NOT a leak and must survive, so we
	require the deprecation phrasing or a docs/help link, not a bare 'frappe.io'."""
	low = (text or "").lower()
	if "frappe.io" not in low:
		return False
	# NO bare-URL disjunct (batch-183, sweep C36): "https://frappe.io/..." matches
	# essentially every real citation a tenant could paste, which silently deleted
	# their own paragraph on every migrate — exactly what this guard promises not to
	# do. The known leak blocks all carry deprecation phrasing or a docs link.
	return (
		"deprecated" in low
		or "use frappe" in low
		or "switch to frappe" in low
		or "docs.frappe.io" in low
	)


def reconcile_content_leaks():
	"""after_migrate: scrub Frappe-brand leaks that live INSIDE standard docs and
	get re-synced on every migrate, so neither Translations nor label relabels can
	reach them:
	  - Workspace.content paragraph blocks linking frappe.io (the classic CRM and
	    Support workspaces ship a "deprecated, use Frappe CRM/Helpdesk instead"
	    banner; Learning ships a docs.frappe.io link) — drop those blocks.
	  - The Builder workspace shortcut labelled "Open <strong>Frappe Builder</strong>"
	    (both the Workspace Shortcut child row and the content JSON copy).
	  - Workspace Sidebar TITLES still carrying the native "Frappe X" names (the
	    sidebar header renders the title verbatim). Workspace Sidebar `title` is
	    UNIQUE and the classic desk already has a "CRM" sidebar, so the new-CRM
	    sidebar gets the collision-free branded form ("<Brand> CRM").
	Idempotent + hardened so it can never abort a migrate."""
	import json

	if not frappe.db.table_exists("Workspace"):
		return
	try:
		for ws in frappe.get_all("Workspace", fields=["name", "content"]):
			if not ws.content or ("frappe.io" not in ws.content and "Frappe Builder" not in ws.content):
				continue
			try:
				blocks = json.loads(ws.content)
			except Exception:
				continue
			out, dirty = [], False
			for b in blocks:
				data = b.get("data") or {}
				if _is_frappe_leak_block(data.get("text")):
					dirty = True
					continue
				sc = data.get("shortcut_name") or ""
				if "Frappe Builder" in sc:
					data["shortcut_name"] = sc.replace("Frappe Builder", "Builder")
					dirty = True
				out.append(b)
			if dirty:
				frappe.db.set_value(
					"Workspace", ws.name, "content", json.dumps(out), update_modified=False
				)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_content_leaks workspaces failed",
			message=frappe.get_traceback(),
		)

	try:
		for name in frappe.get_all(
			"Workspace Shortcut", filters={"label": ("like", "%Frappe Builder%")}, pluck="name"
		):
			old = frappe.db.get_value("Workspace Shortcut", name, "label")
			frappe.db.set_value(
				"Workspace Shortcut",
				name,
				"label",
				old.replace("Frappe Builder", "Builder"),
				update_modified=False,
			)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_content_leaks shortcuts failed",
			message=frappe.get_traceback(),
		)

	if frappe.db.table_exists("Workspace Sidebar"):
		for sb, new in (
			("Frappe Builder", brand_config.display_name("builder")),
			("Frappe CRM", brand_config.branded_name("crm")),
		):
			try:
				if frappe.db.exists("Workspace Sidebar", sb) and frappe.db.get_value(
					"Workspace Sidebar", sb, "title"
				) != new:
					frappe.db.set_value(
						"Workspace Sidebar", sb, "title", new, update_modified=False
					)
			except Exception:
				frappe.log_error(
					title="my_branding reconcile_content_leaks sidebar failed",
					message=f"{sb}\n{frappe.get_traceback()}",
				)


def reconcile_workspace_order():
	"""after_migrate: give every public Workspace a UNIQUE sequence_id so the desk
	launcher (/desk) + sidebar stop SHUFFLING tied workspaces on each page load.

	Frappe ships many workspaces sharing the same sequence_id (8+ at seq 1, several
	at 2/5/6/7/8/9 ...). The launcher/sidebar order by sequence_id, so tied rows come
	back in arbitrary DB order -> the grid re-arranges every time you open it. We
	re-number all public workspaces 10,20,30,... in (sequence_id, name) order, which
	KEEPS the existing grouping and just breaks ties deterministically. update_modified
	=False so it doesn't churn modified timestamps. Idempotent + hardened so it can
	never abort a migrate. (The matching client-side desk-launcher re-sort that used
	to live in brand.js was removed — order is now owned by this data layer, and the
	native /desk grid is drag-to-reorder + persistent on top of it.)"""
	if not frappe.db.table_exists("Workspace"):
		return
	try:
		rows = frappe.get_all(
			"Workspace",
			filters={"public": 1},
			fields=["name", "sequence_id"],
			order_by="sequence_id asc, name asc",
		)
		# Pin the branded "Home" workspace to the LOWEST sequence_id. Frappe lands a
		# first-login user on the lowest-sequence_id public workspace they can access;
		# without this they land on whatever sorts first (often the developer "Build" or
		# the "Lending" vertical). Home first → every new client opens on a branded home.
		home = [w for w in rows if w.name == "Home"]
		ordered = home + [w for w in rows if w.name != "Home"]
		for i, w in enumerate(ordered, start=1):
			seq = i * 10
			if w.sequence_id != seq:
				frappe.db.set_value("Workspace", w.name, "sequence_id", seq, update_modified=False)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_workspace_order failed", message=frappe.get_traceback()
		)


# Ratified desk-launcher sections and order, keyed on the Desktop Icon `label`
# (== the launcher tile's data-id). These labels are linkage keys, not display
# names. The /desk launcher renders top-level icons ordered by `idx`
# (frappe.desk...desktop_icon.get_desktop_icons), so assigning these idx gives the
# order server-side — no client-side DOM sorting, no flicker, persistent. Labels
# not listed are placed after the curated set only when they can render top-level;
# folder children (e.g. Accounting's Invoicing/Payments) keep their own idx and
# stay grouped under their visible parent.
LAUNCHER_SECTIONS = [
	{
		# Dedicated first section for the owner-first Home workspace (Get-set-up panel +
		# KPI row) — one click from the launcher grid, NOT mixed into Sales & Money
		# (owner feedback 2026-08-23).
		"title": "Overview",
		"labels": ["Home"],
	},
	{
		"title": "Sales & Money",
		"labels": ["Accounting", "Selling", "Online Store", "Buying", "Stock", "Lending"],
	},
	{
		"title": "Operations",
		"labels": [
			"Manufacturing",
			"Subcontracting",
			"Assets",
			"Maintenance",
			"Projects",
			"Quality",
			"Organization",
		],
	},
	{
		"title": "Customers & Team",
		"labels": ["Frappe CRM", "Frappe HR", "Helpdesk", "Insights"],
	},
	{
		# Core-focus 2026-08-24: the office/collab tiles here are non-core and hidden
		# per site (core_focus.hidden_labels); Website moved to Administration so this
		# section simply disappears once its tiles are stripped.
		"title": "Files & Office",
		"labels": [
			"Frappe Drive",
			"Slides",
			"Teams",
			"Frappe Builder",
			"Frappe Learning",
			"Learning",
		],
	},
	{"title": "Administration", "labels": ["Website", "Settings", "My Workspaces", "Framework"]},
]


def launcher_sections():
	"""Per-SITE launcher sections (core-focus 2026-08-24). Strips the labels of
	apps hidden on this site (core_focus.hidden_labels) from the ratified base
	layout above, drops any section that empties, and on internal sites
	(nx_internal_tools, i.e. hq) appends the trailing "Internal Tools" footer
	section holding the internal-tool tiles. Consumed by boot.boot_session
	(brand.js renders the section headers from bootinfo) and by
	reconcile_desktop_icon_order. Hardened: on any error fall back to the full
	base layout — a wrongly-ordered launcher beats a broken boot."""
	try:
		from my_branding.core_focus import INTERNAL_SECTION, hidden_labels, internal_tools_site

		hidden = hidden_labels()
		internal = internal_tools_site()
		internal_set = set(INTERNAL_SECTION["labels"]) if internal else set()
		out = []
		for section in LAUNCHER_SECTIONS:
			labels = [
				label
				for label in section["labels"]
				if label not in hidden and label not in internal_set
			]
			if labels:
				out.append({"title": section["title"], "labels": labels})
		if internal:
			out.append(
				{"title": INTERNAL_SECTION["title"], "labels": list(INTERNAL_SECTION["labels"])}
			)
		return out
	except Exception:
		frappe.log_error(title="my_branding launcher_sections failed", message=frappe.get_traceback())
		return [
			{"title": section["title"], "labels": list(section["labels"])}
			for section in LAUNCHER_SECTIONS
		]


def desktop_icon_order():
	"""Flat per-site tile order derived from launcher_sections()."""
	return [label for section in launcher_sections() for label in section["labels"]]


def reconcile_desktop_icon_order():
	"""after_migrate: stamp the tiered launcher order onto Desktop Icon `idx` so the
	/desk app grid reads CORE ERP -> BUSINESS -> ENTERPRISE -> system. Idempotent +
	hardened so it can never abort a migrate. Spaced by 10s (10,20,30,...) so a future
	tile can be slotted between two without a full renumber. Unlisted visible icons
	that have no visible parent are kept in their existing relative order and stamped
	after the curated set; children nested under a visible folder retain their own idx.
	Clears the desktop_icons cache for ALL users so the new order shows without a hard
	restart (the stock clear_desktop_icons_cache() only clears the migrate-runner's
	own entry)."""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		order = desktop_icon_order()
		for i, label in enumerate(order, start=1):
			idx = i * 10
			for name in frappe.get_all("Desktop Icon", filters={"label": label}, pluck="name"):
				if frappe.db.get_value("Desktop Icon", name, "idx") != idx:
					frappe.db.set_value("Desktop Icon", name, "idx", idx, update_modified=False)

		# desktop.js builds its parent lookup from visible labels only. Mirror that
		# rule so only icons that would render top-level receive catch-all indices;
		# children of visible folders keep the idx used within their folder.
		rows = frappe.get_all(
			"Desktop Icon",
			fields=["name", "label", "parent_icon", "hidden", "idx"],
			order_by="idx asc, name asc",
		)
		visible_labels = {row.label for row in rows if row.hidden != 1}
		curated_labels = set(order)
		trailing = [
			row
			for row in rows
			if row.hidden != 1
			and row.label not in curated_labels
			and (not row.parent_icon or row.parent_icon not in visible_labels)
		]
		for i, row in enumerate(trailing, start=len(order) + 1):
			idx = i * 10
			if row.idx != idx:
				frappe.db.set_value(
					"Desktop Icon", row.name, "idx", idx, update_modified=False
				)

		# Drop the whole per-user cache hash (not just this user's entry) so every
		# logged-in user picks up the new order, not only the migrate-runner.
		try:
			frappe.cache.delete_key("desktop_icons")
			frappe.cache.delete_key("bootinfo")
		except Exception:
			pass
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_desktop_icon_order failed", message=frappe.get_traceback()
		)


def reconcile_framework_desktop_icon_visibility():
	"""after_migrate: hide Framework and its developer-facing child icons site-wide.

	desktop.js removes hidden icons before building its parent lookup (`icon_map`).
	Hiding Framework alone therefore orphans its visible children and promotes them
	into the top-level launcher grid. Hide every current/future Framework child too,
	except Website: Website is an intentional content-management tile whose visibility
	and curated position are governed by desktop_icon_order(). Idempotent + hardened so
	it can never abort a migrate.
	"""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		names = frappe.get_all(
			"Desktop Icon", filters={"label": "Framework"}, pluck="name"
		)
		names += frappe.get_all(
			"Desktop Icon",
			filters={"parent_icon": "Framework", "label": ("!=", "Website")},
			pluck="name",
		)
		for name in names:
			if frappe.db.get_value("Desktop Icon", name, "hidden") != 1:
				frappe.db.set_value("Desktop Icon", name, "hidden", 1, update_modified=False)
		try:
			frappe.cache.delete_key("desktop_icons")
			frappe.cache.delete_key("bootinfo")
		except Exception:
			pass
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_framework_desktop_icon_visibility failed",
			message=frappe.get_traceback(),
		)


# Workspaces a paying client should never meet in their sidebar: developer tooling
# (DocType/Server Script editors), integration plumbing, Frappe's boilerplate empty
# state, and the niche Lending vertical. We ALSO de-duplicate the classic ERPNext
# Support/CRM workspaces when the standalone Helpdesk/CRM apps are installed (both
# would otherwise show side by side).
_HIDE_WORKSPACES_ALWAYS = ["Build", "Integrations", "Welcome Workspace"]
# Workspaces an earlier reconciler hid but that MUST be reachable: the /desk launcher
# carries a "Lending" tile (the lending app's own apps-screen icon) that routes to this
# workspace; hidden, every non-System-Manager user got "No permission for Page"
# (2026-08-22 demo report). Its own `roles` (Loan Manager) already scope who sees it
# in the sidebar, so hiding bought nothing but a dead tile.
_UNHIDE_WORKSPACES = ["Lending"]


def reconcile_default_portal_home():
	"""after_migrate: undo helpdesk's `default_portal_home = "/helpdesk"`.

	helpdesk (>=1.29) sets Portal Settings.default_portal_home to /helpdesk (fresh
	install + the `set_default_portal_settings` migrate patch). frappe's get_home_page()
	ranks the portal default ABOVE Website Settings, so on a multi-app site EVERY system
	user's post-login home became /helpdesk — the desk/desktop app opened onto the
	Helpdesk SPA instead of the ERP desk (reported 2026-08-23 after the 16.31/helpdesk-1.29
	bump). Reset it to EMPTY (the pre-bump state): get_home_page() then falls through to
	Website Settings.home_page (our split-brand "login" page), and the bare website root
	`/` — which the desktop app opens — correctly lands a logged-in system user on /desk.
	(A literal /app is WRONG here: get_home_page() strips it to "app" and the WEBSITE root
	has no such route -> "Page not found"; /app only works as a desk URL, not a home_page.)
	Genuine Helpdesk customers are unaffected: the HD Customer / HD Customer Manager roles
	carry their own role.home_page=/helpdesk, which get_home_page() ranks ABOVE the portal
	default. Idempotent, hardened, clears the per-user home_page cache."""
	try:
		if not frappe.db.exists("DocType", "Portal Settings"):
			return
		current = frappe.db.get_single_value("Portal Settings", "default_portal_home")
		# undo helpdesk's /helpdesk (and the interim wrong /app, if a site still carries it)
		if current in ("/helpdesk", "/app"):
			frappe.db.set_value("Portal Settings", "Portal Settings", "default_portal_home", "")
			try:
				frappe.cache.delete_key("home_page")
			except Exception:
				pass
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_default_portal_home failed", message=frappe.get_traceback()
		)


def reconcile_workspace_visibility():
	"""after_migrate: hide dev/admin/duplicate/boilerplate workspaces from the client
	desk sidebar (is_hidden=1). The workspace stays reachable via search; a client owner
	(not a Workspace Manager) simply no longer sees it in the sidebar. Idempotent +
	hardened so it can never abort a migrate."""
	if not frappe.db.table_exists("Workspace"):
		return
	try:
		installed = frappe.get_installed_apps()
		hide = list(_HIDE_WORKSPACES_ALWAYS)
		if "helpdesk" in installed:
			hide.append("Support")  # classic ERPNext Support duplicates the Helpdesk app
		if "crm" in installed:
			hide.append("CRM")  # built-in ERPNext CRM duplicates the standalone Frappe CRM
		for name in hide:
			try:
				if frappe.db.exists("Workspace", name) and not frappe.db.get_value(
					"Workspace", name, "is_hidden"
				):
					frappe.db.set_value("Workspace", name, "is_hidden", 1, update_modified=False)
			except Exception:
				frappe.log_error(
					title="my_branding hide workspace failed", message=f"{name}\n{frappe.get_traceback()}"
				)
		for name in _UNHIDE_WORKSPACES:
			try:
				if frappe.db.exists("Workspace", name) and frappe.db.get_value(
					"Workspace", name, "is_hidden"
				):
					frappe.db.set_value("Workspace", name, "is_hidden", 0, update_modified=False)
			except Exception:
				frappe.log_error(
					title="my_branding unhide workspace failed", message=f"{name}\n{frappe.get_traceback()}"
				)
		try:
			frappe.cache.delete_key("bootinfo")
		except Exception:
			pass
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_workspace_visibility failed", message=frappe.get_traceback()
		)


def reconcile_onboarding():
	"""after_migrate: turn OFF Frappe's onboarding system per tenant. System Settings
	`enable_onboarding` gates BOTH the per-module "Getting Started / <Module> Setup"
	stepper cards AND the standard form-tours (guided overlays the first time a client
	opens Customer/Supplier). A provisioned client was already set up FOR them, so these
	only read as clutter / "demo data". We also mark any Module Onboarding rows complete
	(belt-and-suspenders). Idempotent + hardened so it can never abort a migrate."""
	try:
		if frappe.db.get_single_value("System Settings", "enable_onboarding") != 0:
			frappe.db.set_single_value("System Settings", "enable_onboarding", 0)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_onboarding setting failed", message=frappe.get_traceback()
		)
	try:
		if frappe.db.table_exists("Module Onboarding"):
			for n in frappe.get_all("Module Onboarding", filters={"is_complete": 0}, pluck="name"):
				frappe.db.set_value("Module Onboarding", n, "is_complete", 1, update_modified=False)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_onboarding mo failed", message=frappe.get_traceback()
		)


def ensure_web_title_prefix():
	"""after_migrate: brand web-page <title> / browser tab / link-preview. Frappe leaves
	Website Settings `title_prefix` blank, so /login and portal pages show bare titles
	("Login"). Set it to the brand. Idempotent + hardened so it can never abort a migrate."""
	if not frappe.db.table_exists("Website Settings"):
		return
	try:
		if frappe.db.get_single_value("Website Settings", "title_prefix") != brand_config.BRAND:
			frappe.db.set_single_value("Website Settings", "title_prefix", brand_config.BRAND)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_web_title_prefix failed", message=frappe.get_traceback()
		)
