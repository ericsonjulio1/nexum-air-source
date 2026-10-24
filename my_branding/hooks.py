app_name = "my_branding"
app_title = "Nexum Air Branding"
app_publisher = "EJ"
app_description = "Branding customizations for our Nexum Air deployment"
app_email = "admin@nexumair.com"
app_license = "mit"

# Branding
# --------
app_logo_url = "/assets/my_branding/images/nexum-mark.png"
brand_html = '<span style="font-weight:700;color:#fff;letter-spacing:0.3px;">Nexum Air</span>'

_BRAND_CSS_VER = "20261016d"
app_include_css = [
	f"/assets/my_branding/css/brand.css?v={_BRAND_CSS_VER}",
	"/assets/my_branding/css/report-theme.css?v=20261016d",
	"/assets/my_branding/css/idle_lock.css?v=20261006a",
]
app_include_js = [
	"/assets/my_branding/js/report-theme.js?v=20261016d",
	"/assets/my_branding/js/compatibility.js?v=20261022-architecture1",
	"/assets/my_branding/js/brand.js?v=20261022-architecture1",
	"/assets/my_branding/js/navigation.js?v=20261016d",
	# idle screen lock: warning, lock in place, unlock (see idle_lock.py)
	"/assets/my_branding/js/idle_lock.js?v=20261010a",
]
web_include_css = [
	f"/assets/my_branding/css/brand.css?v={_BRAND_CSS_VER}",
	"/assets/my_branding/css/login.css?v=20261003-loop1",
]
# split login page (left industrial animation + right credentials); login.js guards on
# #page-login so it only acts on /login, never other web pages.
web_include_js = "/assets/my_branding/js/login.js?v=20261016-spacious2"
website_theme_scss = "my_branding/public/scss/website"

website_context = {
	"favicon": "/assets/my_branding/images/favicon.png",
	"splash_image": "/assets/my_branding/images/nexum-logo-full.png",
	"app_name": "Nexum Air",
}

fixtures = [
	# Website Settings / Navbar Settings moved to branding.ensure_site_brand_settings (M3,
	# v204): frappe's sync_fixtures force-imports EVERY *.json under fixtures/ on each
	# migrate (delete + re-insert), so the whole Singles were reset on every deploy and
	# tenant edits (top bar, footer, GA id, head_html, help items...) were wiped. Their
	# JSON now lives in seed/ and only the brand-owned keys are re-applied.
	# Website Theme stays: only themes exported from the brand's own site land in
	# fixtures/website_theme.json (today an empty list, so the import is a no-op);
	# tenant-made themes are never in the file and are never touched.
	{"dt": "Website Theme", "filters": [["custom", "=", 1]]},
	# Letter Head moved to branding.ensure_letter_heads (insert-only reconciler,
	# batch-183 sweep C37): the unfiltered fixture re-saved both letterheads on
	# every migrate, reverting tenant content edits and their default choice.
	{"dt": "Custom Field", "filters": [["module", "=", "My Branding"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "My Branding"]]},
	# Rebranded Settings workspace (was "ERPNext Settings", now plain "Settings");
	# reconcile hook below removes the duplicate the standard ERPNext sync recreates.
	{"dt": "Workspace", "filters": [["name", "=", "Settings"]]},
]

# Keep the rebranded "Settings" workspace from being duplicated by the standard
# ERPNext workspace sync on each migrate, and re-assert desk string overrides
# (e.g. "Frappe HR" -> "HR"). Launcher visibility must run before launcher
# ordering so catch-all ordering sees the final parent/child hidden state.
after_migrate = [
	"my_branding.tenant_identity.ensure_current_generation",
	"my_branding.branding.reconcile_workspaces",
	"my_branding.branding.ensure_translations",
	"my_branding.branding.reconcile_navbar",
	"my_branding.branding.ensure_letter_heads",
	"my_branding.branding.ensure_insights_desktop_icon",
	"my_branding.branding.ensure_maintenance_desktop_icon",
	"my_branding.branding.ensure_settings_desktop_icon",
	"my_branding.branding.ensure_home_desktop_icon",
	"my_branding.branding.ensure_owner_landing",
	"my_branding.webshop.ensure_online_store_workspace",
	"my_branding.branding.ensure_gameplan_tile_label",
	"my_branding.branding.reconcile_app_workspace_labels",
	"my_branding.branding.reconcile_lms_admin_workspace",
	"my_branding.branding.reconcile_content_leaks",
	"my_branding.coa_guard.reconcile_ph_coa_defaults",
	"my_branding.pd_preview.ensure_pd_preview_images",
	"my_branding.roles.ensure_role_profiles",
	"my_branding.roles.ensure_owner_asset_manager",
	"my_branding.branding.ensure_email_settings",
	"my_branding.branding.ensure_app_landing",
	# brand-owned keys on Website/Navbar Settings (they are no longer fixtures)
	"my_branding.branding.ensure_site_brand_settings",
	"my_branding.branding.reconcile_onboarding",
	"my_branding.branding.reconcile_default_portal_home",
	"my_branding.branding.reconcile_workspace_visibility",
	"my_branding.core_focus.reconcile_core_focus",
	"my_branding.branding.ensure_web_title_prefix",
	"my_branding.branding.reconcile_workspace_order",
	"my_branding.branding.reconcile_framework_desktop_icon_visibility",
	"my_branding.branding.reconcile_desktop_icon_order",
	"my_branding.invoicing.ensure_invoice_design",
	"my_branding.demo.reconcile_demo_start",
	"my_branding.demo.reconcile_demo_health",
	# UX plan 2026-08-23: owner-first Home + module Getting-started panels, and the
	# per-plan simple-mode property setters (Free/Essentials).
	"my_branding.home.reconcile_home_workspace",
	"my_branding.simple_mode.reconcile_simple_mode",
	# Official PH invoice format: Company fields it reads (the Print Format itself is a
	# standard doc in my_branding/my_branding/print_format/, synced by migrate).
	"my_branding.invoice_ph.ensure_company_invoice_fields",
	# Idle screen lock: System Settings fields, deploy-grace seed, enforcement switch.
	"my_branding.idle_lock.ensure_setup",
	# Free -> paid: switch back on the Auto Repeats the Free document cap paused (the
	# upgrade's change-plan.sh migrate runs this; batch205 idx 159, see doc_caps.py).
	"my_branding.doc_caps.resume_capped_auto_repeats",
]

# "Invoice Design" button on the Sales Invoice form -> Print Designer editor
# for the branded "Invoice Design" format (see invoicing.py).
doctype_js = {
	"Sales Invoice": ["public/js/sales_invoice.js", "public/js/simple_mode.js"],
	"Purchase Invoice": "public/js/simple_mode.js",
	"Payment Entry": "public/js/simple_mode.js",
}

# Rebrand the "ERPNext" app title shown in the workspace sidebar header.
extend_bootinfo = [
	"my_branding.boot.boot_session",
	# the docs behind the Home KPI cards / Getting-started blocks, so their widgets skip
	# the getdoc round trip before loading their data (batch205 idx 94, see home.py)
	"my_branding.home.boot_widget_docs",
]

# Paint Nexum Air branding onto the standalone frappe-ui SPAs (Frappe HR, ...),
# which serve their own HTML and never load brand.css. Post-processes their
# rendered response — no app-source edits, so it survives app updates.
after_request = [
	"my_branding.spa_brand.inject_brand_assets",
	# idle screen lock: activity reporter on every non-desk page a desk user opens
	"my_branding.idle_lock.inject_activity_reporter",
]

# Relabel the /apps switcher + navbar app dropdown to the Nexum Air names
# (scoped rename — safer than Translation-ing bare words like "Drive"/"ERPNext").
override_whitelisted_methods = {
	"frappe.apps.get_apps": "my_branding.naming.get_apps",
	# Builder's own apps endpoint (bypasses frappe.apps.get_apps) — rebrand its
	# "Desk"/"ERPNext" labels + teal logos.
	"builder.api.get_apps": "my_branding.naming.builder_get_apps",
	# Guard the ERPNext setup wizard against a blank Country, which otherwise
	# 500s in install_fixtures and strands new tenants on the wizard
	# (curiosity.nexumair.com, 2026-06-17). Backfills the pre-seeded default
	# Country/currency, else raises a clean validation error.
	"frappe.desk.page.setup_wizard.setup_wizard.setup_complete": "my_branding.setup_guard.setup_complete",
}

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "my_branding",
# 		"logo": "/assets/my_branding/logo.png",
# 		"title": "My Branding",
# 		"route": "/my_branding",
# 		"has_permission": "my_branding.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/my_branding/css/my_branding.css"
# app_include_js = "/assets/my_branding/js/my_branding.js"

# include js, css files in header of web template
# web_include_css = "/assets/my_branding/css/my_branding.css"
# web_include_js = "/assets/my_branding/js/my_branding.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "my_branding/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "my_branding/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "my_branding.utils.jinja_methods",
# 	"filters": "my_branding.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "my_branding.install.before_install"
# after_install = "my_branding.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "my_branding.uninstall.before_uninstall"
# after_uninstall = "my_branding.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "my_branding.utils.before_app_install"
# after_app_install = "my_branding.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "my_branding.utils.before_app_uninstall"
# after_app_uninstall = "my_branding.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "my_branding.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "my_branding.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# Enforce per-plan file storage quota (storage_quota_gb in site_config; 0 = unlimited).
doc_events = {
	"File": {
		"before_insert": "my_branding.storage.enforce_file_quota",
		# File.validate copies a client-sent form field file_size over the measured size;
		# this runs after it and restores the real one, so SUM(file_size) holds (H3).
		"validate": "my_branding.storage.pin_true_file_size",
		# deleting a file lowers usage — bust the cached total so freed space is
		# reflected immediately rather than after the 30s TTL.
		"on_trash": "my_branding.storage.invalidate_used_cache",
	},
	# Drive keeps its own doctype for uploads — same quota, same enforcement
	# (the handler skips is_group folders and counts both tables). Drive measures the
	# size from the uploaded bytes on disk and never reads form_dict.file_size, so it
	# needs no validate pin.
	"Drive File": {
		"before_insert": "my_branding.storage.enforce_file_quota",
		"on_trash": "my_branding.storage.invalidate_used_cache",
	},
	"System Settings": {
		"validate": "my_branding.idle_lock.validate_system_settings",
	},
}

# Every capped DocType is wired from the same policy as provisioning.
from my_branding.plan_policy import CAPPED_DOCTYPES
for _capped_dt in CAPPED_DOCTYPES:
	doc_events.setdefault(_capped_dt, {})["before_insert"] = "my_branding.doc_caps.enforce_doc_cap"

# A returning customer on an idle-parked Free site re-enables its own scheduler.
on_login = "my_branding.lifecycle.wake_scheduler"

# Idle screen lock (idle_lock.py): every new signed-in session starts with a fresh
# human-activity record.
on_session_creation = ["my_branding.idle_lock.on_session_creation"]
# ...and the server refuses a cookie session with no human activity for longer than
# idle + 60 s warning + 90 s grace (see idle_lock.enforce).
before_request = ["my_branding.idle_lock.enforce"]

# /bin/x, /project/.env: a 404 instead of the print view's 500 for a miscased doctype
page_renderer = ["my_branding.print_route.MiscasedPrintRoute"]

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"my_branding.tasks.all"
# 	],
# 	"daily": [
# 		"my_branding.tasks.daily"
# 	],
# 	"hourly": [
# 		"my_branding.tasks.hourly"
# 	],
# 	"weekly": [
# 		"my_branding.tasks.weekly"
# 	],
# 	"monthly": [
# 		"my_branding.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "my_branding.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "my_branding.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "my_branding.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "my_branding.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["my_branding.utils.before_request"]
# after_request = ["my_branding.utils.after_request"]

# Job Events
# ----------
# before_job = ["my_branding.utils.before_job"]
# after_job = ["my_branding.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"my_branding.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
