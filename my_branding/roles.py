"""Standard staff Role Profiles shipped on every tenant.

Design (user decisions 2026-06-10):
- The tenant OWNER keeps System Manager + the full business role set (granted by
  provision-tenant.sh). STAFF users get scoped access via these per-function
  Role Profiles instead — the owner just picks one from the dropdown on the
  User form, no raw-role archaeology.
- Sales is SPLIT: "Sales Staff" works their own CRM leads, "Sales Manager" sees
  the whole pipeline (the modern CRM app's org_hierarchy permission_query hides
  other people's leads from non-managers, so the Sales Manager role IS the
  visibility switch).
- Merge-up semantics: missing profiles are created and missing roles ADDED, but
  roles a tenant added to a profile are never removed — their customizations
  win over our spec. A profile is skipped entirely while none of its roles
  exist (that app isn't installed on the plan).

Wired as an after_migrate hook, so every existing and future tenant gets the
set, and app updates can't drop it.
"""

import frappe

# profile name -> roles (only those existing on the site are applied)
ROLE_PROFILES = {
	"Accountant": ["Accounts Manager", "Accounts User"],
	"Sales Staff": ["Sales User", "Sales Master Manager"],
	"Sales Manager": ["Sales Manager", "Sales User", "Sales Master Manager"],
	"Purchasing": ["Purchase User", "Purchase Master Manager"],
	"Inventory": ["Stock User", "Stock Manager", "Item Manager"],
	"Manufacturing": ["Manufacturing User"],
	"Maintenance": ["Maintenance Manager", "Maintenance User", "Asset Manager"],
	"Projects": ["Projects User"],
	"HR": ["HR Manager", "HR User"],
	"Support Agent": ["Agent"],
	"Employee (Self-Service)": ["Employee", "Employee Self Service"],
}


def ensure_role_profiles():
	"""after_migrate: seed/merge the standard staff Role Profiles (idempotent,
	hardened — a failure can never abort a migrate)."""
	if not frappe.db.table_exists("Role Profile"):
		return
	for profile, want_roles in ROLE_PROFILES.items():
		try:
			roles = [r for r in want_roles if frappe.db.exists("Role", r)]
			if not roles:
				continue  # function's app not on this plan

			if frappe.db.exists("Role Profile", profile):
				doc = frappe.get_doc("Role Profile", profile)
				have = {row.role for row in doc.roles}
				missing = [r for r in roles if r not in have]
				if not missing:
					continue
				for r in missing:
					doc.append("roles", {"role": r})
				doc.save(ignore_permissions=True)
			else:
				frappe.get_doc(
					{
						"doctype": "Role Profile",
						"role_profile": profile,
						"roles": [{"role": r} for r in roles],
					}
				).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="my_branding ensure_role_profiles failed",
				message=f"{profile}\n{frappe.get_traceback()}",
			)


def ensure_owner_asset_manager():
	"""after_migrate: backfill "Asset Manager" onto existing tenants' Owner users.

	Asset Manager gates the eam ("Maintenance") app's Asset Meter / Asset Meter
	Reading doctypes. provision-tenant.sh grants the site's customer-admin (the
	Owner) System Manager plus the full core ROLES bundle — including Maintenance
	Manager and Maintenance User — in one atomic frappe.client.insert at
	user-creation time, but Asset Manager was missing from that bundle (fixed
	going forward). No other provisioning path in this app grants System Manager
	+ Maintenance Manager together, so on every site this app manages, an
	enabled, non-Administrator/Guest user holding BOTH roles today is the tenant
	Owner (or someone the Owner deliberately cloned into an equivalent power
	role, who should equally get Asset Manager). Idempotent (add_roles skips
	roles already held) and hardened — a failure can never abort a migrate.
	"""
	if not frappe.db.table_exists("Role") or not frappe.db.exists("Role", "Asset Manager"):
		return  # eam not installed on this site/plan

	try:
		sys_mgrs = set(
			frappe.get_all(
				"Has Role",
				filters={"role": "System Manager", "parenttype": "User"},
				pluck="parent",
			)
		)
		maint_mgrs = set(
			frappe.get_all(
				"Has Role",
				filters={"role": "Maintenance Manager", "parenttype": "User"},
				pluck="parent",
			)
		)
		candidates = sys_mgrs & maint_mgrs - {"Administrator", "Guest"}
		if not candidates:
			return
		enabled = set(
			frappe.get_all(
				"User",
				filters={"name": ["in", list(candidates)], "enabled": 1},
				pluck="name",
			)
		)
	except Exception:
		frappe.log_error(
			title="my_branding ensure_owner_asset_manager failed (candidate lookup)",
			message=frappe.get_traceback(),
		)
		return

	for user in enabled:
		try:
			doc = frappe.get_doc("User", user)
			if "Asset Manager" not in {row.role for row in doc.roles}:
				doc.add_roles("Asset Manager")
		except Exception:
			frappe.log_error(
				title="my_branding ensure_owner_asset_manager failed",
				message=f"{user}\n{frappe.get_traceback()}",
			)
