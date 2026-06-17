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

app_include_css = "/assets/my_branding/css/brand.css?v=20260610b"
app_include_js = "/assets/my_branding/js/brand.js?v=20260615b"
web_include_css = [
	"/assets/my_branding/css/brand.css?v=20260610b",
	"/assets/my_branding/css/login.css?v=20260612a",
]
# split login page (left brand diagram + right credentials); login.js guards on
# #page-login so it only acts on /login, never other web pages.
web_include_js = "/assets/my_branding/js/login.js?v=20260611a"
website_theme_scss = "my_branding/public/scss/website"

website_context = {
	"favicon": "/assets/my_branding/images/favicon.png",
	"splash_image": "/assets/my_branding/images/nexum-logo-full.png",
	"app_name": "Nexum Air",
}

fixtures = [
	{"dt": "Navbar Settings"},
	{"dt": "Website Settings"},
	{"dt": "Website Theme", "filters": [["custom", "=", 1]]},
	{"dt": "Letter Head"},
	{"dt": "Custom Field", "filters": [["module", "=", "My Branding"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "My Branding"]]},
	# Rebranded Settings workspace (was "ERPNext Settings", now plain "Settings");
	# reconcile hook below removes the duplicate the standard ERPNext sync recreates.
	{"dt": "Workspace", "filters": [["name", "=", "Settings"]]},
]

# Keep the rebranded "Settings" workspace from being duplicated by the standard
# ERPNext workspace sync on each migrate, and re-assert desk string overrides
# (e.g. "Frappe HR" -> "HR").
after_migrate = [
	"my_branding.branding.reconcile_workspaces",
	"my_branding.branding.ensure_translations",
	"my_branding.branding.reconcile_navbar",
	"my_branding.branding.ensure_insights_desktop_icon",
	"my_branding.branding.ensure_settings_desktop_icon",
	"my_branding.branding.ensure_gameplan_tile_label",
	"my_branding.branding.reconcile_app_workspace_labels",
	"my_branding.branding.reconcile_content_leaks",
	"my_branding.roles.ensure_role_profiles",
	"my_branding.branding.ensure_email_settings",
	"my_branding.branding.ensure_app_landing",
	"my_branding.branding.reconcile_workspace_order",
	"my_branding.branding.reconcile_desktop_icon_order",
]

# Rebrand the "ERPNext" app title shown in the workspace sidebar header.
extend_bootinfo = "my_branding.boot.boot_session"

# Paint Nexum Air branding onto the standalone frappe-ui SPAs (Frappe HR, ...),
# which serve their own HTML and never load brand.css. Post-processes their
# rendered response — no app-source edits, so it survives app updates.
after_request = ["my_branding.spa_brand.inject_brand_assets"]

# Relabel the /apps switcher + navbar app dropdown to the Nexum Air names
# (scoped rename — safer than Translation-ing bare words like "Drive"/"ERPNext").
override_whitelisted_methods = {
	"frappe.apps.get_apps": "my_branding.naming.get_apps",
	# Builder's own apps endpoint (bypasses frappe.apps.get_apps) — rebrand its
	# "Desk"/"ERPNext" labels + teal logos.
	"builder.api.get_apps": "my_branding.naming.builder_get_apps",
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
	},
	# Drive keeps its own doctype for uploads — same quota, same enforcement
	# (the handler skips is_group folders and counts both tables).
	"Drive File": {
		"before_insert": "my_branding.storage.enforce_file_quota",
	},
}

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

