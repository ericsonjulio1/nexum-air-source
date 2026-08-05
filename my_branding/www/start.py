"""/start — the nexumair.com landing page's "Live Demo" button target on demo.nexumair.com.

Previously this was a Web Page living ONLY in the demo golden DB snapshot (not version
control) whose inline JS POSTed the demo credentials from the browser. This versioned
replacement does the sign-in SERVER-side (same login_as pattern frappe's own
www/login.py uses for email-link login), so the demo credentials never appear in any
served HTML and the page is finally in the repo.

Gated on site_config `is_demo_site` (set via bench set-config on demo.nexumair.com
only, same mechanism as hq's is_signup_host) — every other tenant 404s. The legacy
golden-DB Web Page would SHADOW this route (DocumentPage resolves before TemplatePage),
so my_branding.demo.reconcile_demo_start deletes it after every migrate — including the
migrate the nightly demo reset runs right after each golden restore.
"""

import frappe

DEMO_USER = "demo@nexumair.com"

no_cache = 1


def get_context(context):
    if not frappe.conf.get("is_demo_site"):
        raise frappe.PageDoesNotExistError

    context.no_cache = 1

    # already in the demo account (or any account) — straight to the desk.
    # 302, NOT the default 301: browsers cache permanent redirects, which would
    # skip the auto-login for every future visit once the first one is cached.
    if frappe.session.user and frappe.session.user != "Guest":
        frappe.local.flags.redirect_location = "/app"
        raise frappe.Redirect(302)

    try:
        if frappe.db.get_value("User", DEMO_USER, "enabled"):
            frappe.local.login_manager.login_as(DEMO_USER)
            frappe.local.flags.redirect_location = "/app"
            raise frappe.Redirect(302)
    except frappe.Redirect:
        raise
    except Exception:
        # never trap a visitor on a broken splash — the template below renders a
        # manual "open the demo" path
        frappe.log_error(title="demo /start auto-login failed", message=frappe.get_traceback())

    return context
