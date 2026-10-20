"""Demo-site (demo.nexumair.com) reconcilers — no-ops everywhere else.

Gated on site_config `is_demo_site` so these can ship in the image and run on every
tenant's migrate without touching anyone but the demo.
"""

import frappe


# roles the shared demo login needs so EVERY launcher tile opens (the tiles come from
# app hooks regardless of role; a tile that lands on "No permission" is a broken demo)
DEMO_USER = "demo@nexumair.com"
DEMO_EXTRA_ROLES = ["Loan Manager"]
# the navigation shells the public demo must show, as Sidebar shell name -> its Module Def
# (the Maintenance shell belongs to module EAM); a shell is expected only if its module exists
DEMO_CORE_SHELLS = {
    "Accounts": "Accounts",
    "Selling": "Selling",
    "Buying": "Buying",
    "Stock": "Stock",
    "Assets": "Assets",
    "Maintenance": "EAM",
}


def reconcile_demo_health():
    """after_migrate (runs right after the nightly golden restore): keep the public demo
    launcher whole. (1) Before Frappe 16.50, Workspace Sidebars with ZERO items were
    invisible on the /desk grid for everyone (frappe filtered Workspace-Sidebar icons by
    `bootinfo.workspace_sidebar_item` having items) — the 07-24 golden carried 47 empty
    sidebars, so the ERP tiles (Selling/Stock/Accounting children…) vanished from the live
    demo: re-import the app's sidebar JSON (force) when one exists, else rebuild from the
    workspace. From 16.50 navigation comes from the `Sidebar` doctype and Workspace Sidebar
    is an inert archive, so that heal stands down; (2) the demo user carries the roles each
    tile needs; (3) on 16.50+, check the navigation the demo login actually resolves and log
    "reconcile_demo_health navigation unhealthy" when a core shell is missing or empty (the
    ops watchdog alerts on reconcile_demo_* Error Logs). (3) reports, it doesn't repair:
    there is no known 16.50+ failure to repair yet. No-op off the demo site; never aborts a
    migrate."""
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
    try:
        problems = _demo_navigation_problems()
        if problems:
            frappe.log_error(title="reconcile_demo_health navigation unhealthy", message="\n".join(problems))
    except Exception:
        frappe.log_error(title="reconcile_demo_health navigation check failed", message=frappe.get_traceback())


def _modern_navigation():
    """True from Frappe 16.50, where the `Sidebar` doctype drives desk navigation
    (frappe.boot.get_module_sidebars) and `Workspace Sidebar` is only kept as an archive."""
    return bool(frappe.db.exists("DocType", "Sidebar"))


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
    if not frappe.db.table_exists("Workspace Sidebar"):
        return
    if _modern_navigation():
        # 16.50+: frappe documents Workspace Sidebar as "kept as an inert archive. Nothing
        # reads this at runtime and nothing writes a row to it" — its rows are what keeps the
        # Sidebar conversion re-runnable, so deleting/re-importing them here could only damage
        # that. (On 16.52 the import below no longer exists, so this raised every reset.)
        return
    from frappe.desk.doctype.workspace_sidebar.workspace_sidebar import (
        create_workspace_sidebar_for_workspaces,
    )
    from frappe.modules.import_file import import_file_by_path

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


def _demo_navigation_problems():
    """READ-ONLY. What is wrong with the navigation the demo login resolves on 16.50+, as
    readable lines ([] when healthy, and on older Frappe, where the legacy heal applies).

    Resolves `get_module_sidebars()` — the same per-user payload the desk boots with — AS the
    demo user, since a shell Administrator sees can still be missing for the public login.
    The session user is restored even when resolution raises."""
    if not _modern_navigation():
        return []
    if not frappe.db.exists("User", DEMO_USER):
        return [f"demo user {DEMO_USER} does not exist, so the public demo login has no navigation"]
    from frappe.boot import get_module_sidebars

    previous = getattr(frappe.session, "user", None) or "Administrator"
    frappe.set_user(DEMO_USER)
    try:
        payload = get_module_sidebars() or {}
    finally:
        frappe.set_user(previous)
    if not payload:
        return [f"{DEMO_USER} resolves no navigation shells at all"]
    problems = []
    for shell, module in DEMO_CORE_SHELLS.items():
        if not frappe.db.exists("Module Def", module):
            continue
        entry = payload.get(shell)
        if not entry:
            problems.append(f"shell '{shell}' (module {module}) is missing from {DEMO_USER}'s navigation")
        elif not entry.get("items"):
            problems.append(f"shell '{shell}' (module {module}) has no items for {DEMO_USER}")
    return problems


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
