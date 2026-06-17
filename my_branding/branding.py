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
	"ERPNext": brand_config.BRAND,
	"ERPNext Integrations": "%s Integrations" % brand_config.BRAND,
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
		for name in names:
			frappe.db.set_value(
				"Navbar Item", name, "route", SUPPORT_ROUTE, update_modified=False
			)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_navbar failed", message=frappe.get_traceback()
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
	"logo_url": "/assets/my_branding/images/icons/insights_app.svg",
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
	if not frappe.db.table_exists("Website Settings"):
		return
	try:
		if frappe.db.get_single_value("Website Settings", "home_page") != LANDING:
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
				if "frappe.io" in (data.get("text") or ""):
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
		for i, w in enumerate(rows, start=1):
			seq = i * 10
			if w.sequence_id != seq:
				frappe.db.set_value("Workspace", w.name, "sequence_id", seq, update_modified=False)
	except Exception:
		frappe.log_error(
			title="my_branding reconcile_workspace_order failed", message=frappe.get_traceback()
		)


# Tiered desk-launcher order: CORE ERP -> BUSINESS -> ENTERPRISE -> system/admin,
# matching the Nexum Air plan tiers. Keyed on the Desktop Icon `label` (== the
# launcher tile's data-id). The /desk launcher renders top-level icons ordered by
# `idx` (frappe.desk...desktop_icon.get_desktop_icons), so assigning these idx gives
# the order server-side — no client-side DOM sorting, no flicker, persistent. Labels
# not listed keep their own idx and fall wherever; folder children (e.g. Accounting's
# Invoicing/Payments) stay grouped under their parent regardless.
DESKTOP_ICON_ORDER = [
	# --- CORE ERP (baseline / Essentials: erpnext modules) ---
	"Accounting", "Selling", "Buying", "Stock", "Manufacturing",
	"Subcontracting", "Assets", "Projects", "Quality", "Organization",
	# --- BUSINESS (crm, hrms, helpdesk, insights, lending) ---
	"Frappe CRM", "Frappe HR", "Helpdesk", "Insights", "Lending",
	# --- ENTERPRISE (drive, slides, gameplan, builder, lms) ---
	"Frappe Drive", "Slides", "Teams", "Frappe Builder", "Frappe Learning", "Learning",
	# --- system / admin (last) ---
	"Settings", "Framework",
]


def reconcile_desktop_icon_order():
	"""after_migrate: stamp the tiered launcher order onto Desktop Icon `idx` so the
	/desk app grid reads CORE ERP -> BUSINESS -> ENTERPRISE -> system. Idempotent +
	hardened so it can never abort a migrate. Spaced by 10s (10,20,30,...) so a future
	tile can be slotted between two without a full renumber. Clears the desktop_icons
	cache for ALL users so the new order shows without a hard restart (the stock
	clear_desktop_icons_cache() only clears the migrate-runner's own entry)."""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	try:
		for i, label in enumerate(DESKTOP_ICON_ORDER, start=1):
			idx = i * 10
			for name in frappe.get_all("Desktop Icon", filters={"label": label}, pluck="name"):
				if frappe.db.get_value("Desktop Icon", name, "idx") != idx:
					frappe.db.set_value("Desktop Icon", name, "idx", idx, update_modified=False)
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
