"""Demo-site (demo.nexumair.com) reconcilers — no-ops everywhere else.

Gated on site_config `is_demo_site` so these can ship in the image and run on every
tenant's migrate without touching anyone but the demo.
"""

import frappe


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
