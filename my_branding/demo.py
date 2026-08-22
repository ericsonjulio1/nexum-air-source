"""Demo-site (demo.nexumair.com) reconcilers — no-ops everywhere else.

Gated on site_config `is_demo_site` so these can ship in the image and run on every
tenant's migrate without touching anyone but the demo.
"""

import frappe


# roles the shared demo login needs so EVERY launcher tile opens (the tiles come from
# app hooks regardless of role; a tile that lands on "No permission" is a broken demo)
DEMO_USER = "demo@nexumair.com"
DEMO_EXTRA_ROLES = ["Loan Manager"]


def reconcile_demo_health():
    """after_migrate (runs right after the nightly golden restore): keep the public demo
    launcher whole. (1) Workspace Sidebars with ZERO items are invisible on the v16 /desk
    grid for everyone (frappe filters Workspace-Sidebar icons by `bootinfo.workspace_
    sidebar_item` having items) — the 07-24 golden carried 47 empty sidebars, so the
    ERP tiles (Selling/Stock/Accounting children…) vanished from the live demo: re-import
    the app's sidebar JSON (force) when one exists, else rebuild from the workspace; (2)
    the demo user carries the roles each tile needs. No-op off the demo site; never
    aborts a migrate."""
    if not frappe.conf.get("is_demo_site"):
        return
    try:
        _heal_empty_sidebars()
    except Exception:
        frappe.log_error(title="reconcile_demo_health sidebars failed", message=frappe.get_traceback())
    try:
        _ensure_demo_roles()
    except Exception:
        frappe.log_error(title="reconcile_demo_health roles failed", message=frappe.get_traceback())


def _sidebar_json_path(title):
    """Path of <app>/workspace_sidebar/<scrub(title)>.json in any installed app, or None."""
    import os

    fname = f"{frappe.scrub(title)}.json"
    for app in frappe.get_installed_apps():
        try:
            path = frappe.get_app_path(app, "workspace_sidebar", fname)
        except Exception:
            continue
        if os.path.exists(path):
            return path
    return None


def _heal_empty_sidebars():
    from frappe.desk.doctype.workspace_sidebar.workspace_sidebar import (
        create_workspace_sidebar_for_workspaces,
    )
    from frappe.modules.import_file import import_file_by_path

    if not frappe.db.table_exists("Workspace Sidebar"):
        return
    empty = frappe.db.sql(
        """SELECT ws.name FROM `tabWorkspace Sidebar` ws
            WHERE ws.name != 'My Workspaces'
              AND NOT EXISTS (SELECT 1 FROM `tabWorkspace Sidebar Item` i WHERE i.parent = ws.name)""",
        pluck="name",
    )
    if not empty:
        return
    rebuild_from_workspace = False
    for name in empty:
        path = _sidebar_json_path(name)
        if path:
            import_file_by_path(path, force=True)
        else:
            # workspace-derived sidebar (SPA apps / Settings): drop + let frappe regenerate
            frappe.delete_doc("Workspace Sidebar", name, force=True, ignore_permissions=True)
            rebuild_from_workspace = True
    if rebuild_from_workspace:
        create_workspace_sidebar_for_workspaces()
    frappe.clear_cache()
    frappe.logger("my_branding").info("demo: healed %d empty workspace sidebar(s): %s" % (len(empty), empty))


def _ensure_demo_roles():
    if not frappe.db.exists("User", DEMO_USER):
        return
    user = frappe.get_doc("User", DEMO_USER)
    have = {r.role for r in user.roles}
    missing = [r for r in DEMO_EXTRA_ROLES if r not in have and frappe.db.exists("Role", r)]
    if missing:
        user.add_roles(*missing)


def reconcile_demo_start():
    """Delete the legacy golden-DB Web Page at route 'start' so the versioned
    my_branding/www/start.py page (server-side auto-login) serves instead —
    DocumentPage resolves BEFORE TemplatePage, so while the Web Page exists it
    shadows the www route. The nightly demo reset restores the golden DB (which
    still contains the page) and then runs migrate, so this self-heals daily."""
    if not frappe.conf.get("is_demo_site"):
        return
    try:
        for name in frappe.get_all("Web Page", filters={"route": "start"}, pluck="name"):
            frappe.delete_doc("Web Page", name, force=True, ignore_permissions=True)
    except Exception:
        frappe.log_error(title="reconcile_demo_start failed", message=frappe.get_traceback())
