"""Which Nexum Air plan is this site on, and should the desk run in "simple mode"?

The plan is stamped into site_config by provision-tenant.sh (`nexum_plan`); sites that
predate the key (or the dev stack) fall back to an inference from the installed apps
(the plan->apps map lives in provision-tenant.sh: free = erpnext only, starter adds
print_designer, business adds hrms/crm/helpdesk/..., enterprise adds eam/lms/...).

"Simple mode" = the Free + Essentials(starter) presentation: collapsed advanced form
fields (simple_mode.py) + slimmer report filter bars (brand.js). Business/Enterprise
keep the full ERPNext surface. Any user can flip their own desk back to the full form
via the "Show advanced fields" toggle (user default `nx_advanced_fields`).
"""

import frappe

PLANS = ("free", "starter", "business", "enterprise")
SIMPLE_PLANS = ("free", "starter")
_ADV_KEY = "nx_advanced_fields"


def get_plan():
	"""Plan slug for this site. `nexum_plan` from site_config wins; else infer."""
	try:
		plan = (frappe.conf.get("nexum_plan") or "").strip().lower()
		if plan in PLANS:
			return plan
		apps = set(frappe.get_installed_apps())
		if "eam" in apps or "lms" in apps or "drive" in apps:
			return "enterprise"
		if "hrms" in apps or "crm" in apps or "helpdesk" in apps or "insights" in apps:
			return "business"
		if "print_designer" in apps:
			return "starter"
		return "free"
	except Exception:
		return "business"  # unknown -> full form, never strip fields by accident


def is_simple_plan():
	return get_plan() in SIMPLE_PLANS


def user_wants_advanced(user=None):
	try:
		return bool(frappe.cint(frappe.defaults.get_user_default(_ADV_KEY, user=user)))
	except Exception:
		return False


def simple_mode_for_session():
	"""1 when the desk should render the simplified surface for the current user."""
	return 1 if (is_simple_plan() and not user_wants_advanced()) else 0


@frappe.whitelist()
def set_advanced_fields(on=1):
	"""Per-user toggle behind the form menu "Show advanced fields" / "Use simple form"."""
	on = frappe.cint(on)
	if on:
		frappe.defaults.set_user_default(_ADV_KEY, 1)
	else:
		frappe.defaults.clear_user_default(_ADV_KEY)
	frappe.cache.hdel("bootinfo", frappe.session.user)
	return {"nx_simple_mode": simple_mode_for_session(), "nx_plan": get_plan()}
