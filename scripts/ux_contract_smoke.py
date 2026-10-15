#!/usr/bin/env python3
"""UX-contract smoke (see UX-CONTRACT.md in this directory).

Asserts the owner-ratified desk navigation behaviors against a running site.
Read-only: logs in, navigates, clicks the house icon — creates/changes nothing.

Usage:
  BASE_URL=http://erpnext.localhost:8080 USER=Administrator PASSWORD=admin \
      python3 scripts/ux_contract_smoke.py
  BASE_URL=https://sbl.nexumair.com SID=<session sid> python3 scripts/ux_contract_smoke.py

Requires: pip install playwright && playwright install chromium
Exit 0 = all contract checks PASS; non-zero = a ratified behavior is broken.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://erpnext.localhost:8080").rstrip("/")
USER = os.environ.get("USER_ID") or os.environ.get("USER", "Administrator")
PASSWORD = os.environ.get("PASSWORD", "admin")
SID = os.environ.get("SID")  # alternative to USER/PASSWORD on live tenants

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", label, ("(" + detail + ")") if detail else "")


def wait_desk(page):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)  # brand.js delegated handlers attach post-boot
    dismiss_modals(page)


def dismiss_modals(page):
    """Close any open Bootstrap modal (fresh users on live tenants get onboarding /
    session-default dialogs that intercept pointer events and hang every click —
    found on hq during the batch-185 live verify). Escape closes frappe dialogs."""
    for _ in range(4):
        if page.locator(".modal.show").count() == 0:
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)


def click_house(page):
    """Click the VISIBLE breadcrumb house anchor — some desk pages render a second,
    hidden `a[href="/desk"]` (found live on hq's workspace page), and clicking that
    one times out."""
    dismiss_modals(page)  # a dialog can land after wait_desk (late onboarding tour)
    anchors = page.locator('.navbar-breadcrumbs a[href="/desk"]')
    for i in range(anchors.count()):
        el = anchors.nth(i)
        if el.is_visible():
            el.click()
            return True
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH"))
        ctx = browser.new_context()
        if SID:
            host = BASE.split("//", 1)[1].split("/")[0].split(":")[0]
            ctx.add_cookies([{"name": "sid", "value": SID, "domain": host, "path": "/"}])
        page = ctx.new_page()
        if not SID:
            page.goto(BASE + "/login")
            page.fill("#login_email", USER)
            page.fill("#login_password", PASSWORD)
            page.click("button[type=submit], .btn-login")
            page.wait_for_load_state("networkidle")

        # --- 1: Maintenance report page carries the Maintenance sidebar ---
        page.goto(BASE + "/app/query-report/Schedule%20Compliance")
        wait_desk(page)
        title = page.evaluate(
            "() => (frappe.app && frappe.app.sidebar && (frappe.app.sidebar.current_module || frappe.app.sidebar.sidebar_title)) || ''")
        check("contract 1: Maintenance sidebar on report page",
              title.strip().lower() == "maintenance", "sidebar_title=" + repr(title))
        trail = page.evaluate("() => frappe.get_current_page?.().get_breadcrumbs?.() || []")
        check("contract 1: full Maintenance report breadcrumb trail",
              len(trail) >= 3 and trail[0].get("href") == "/desk"
              and any(c.get("label") == "Maintenance" for c in trail)
              and any(c.get("label") == "Schedule Compliance" for c in trail), repr(trail))
        home_link = page.locator('.sidebar-items a.item-anchor[href="/desk/maintenance"]')
        check("contract 1: sidebar Home link present", home_link.count() > 0)

        # --- 2: house from inside Maintenance -> /desk/maintenance ---
        click_house(page)
        page.wait_for_timeout(1500)
        path = page.evaluate("() => window.location.pathname")
        check("contract 2: house from Maintenance report -> Maintenance home",
              path.rstrip("/").endswith("/desk/maintenance"), "landed " + path)
        # pathname alone can't prove the router RENDERED the workspace (a bare
        # history.pushState would move the URL and leave the report on screen —
        # 2026-08-29 sweep gap). Assert the rendered page too: the router stamps
        # document.title and shows the Workspaces page-container.
        rendered = page.evaluate(
            """() => ({ title: document.title,
                        ws_visible: (() => { const el = document.getElementById('page-Workspaces');
                                             return !!el && el.offsetParent !== null; })() })""")
        check("contract 2: Maintenance workspace actually rendered",
              rendered["title"] == "Maintenance" and rendered["ws_visible"],
              "title=%r ws_visible=%r" % (rendered["title"], rendered["ws_visible"]))

        # --- 2b: house ON the Maintenance home -> launcher (escape hatch) ---
        page.goto(BASE + "/desk/maintenance")
        wait_desk(page)
        click_house(page)
        page.wait_for_timeout(1500)
        path = page.evaluate("() => window.location.pathname")
        on_launcher = page.locator(".desktop-container .desktop-icon").count() > 0
        check("contract 2b: house on Maintenance home -> launcher",
              on_launcher, "landed " + path)

        # --- 3: house outside Maintenance -> launcher, never a remembered workspace ---
        page.goto(BASE + "/app/sales-invoice")
        wait_desk(page)
        click_house(page)
        page.wait_for_timeout(1500)
        on_launcher = page.locator(".desktop-container .desktop-icon").count() > 0
        path = page.evaluate("() => window.location.pathname")
        check("contract 3: house outside Maintenance -> launcher",
              on_launcher and "maintenance" not in path, "landed " + path)

        # --- 4: Maintenance now lives under Assets (owner direction 2026-10-15) ---
        tile = page.locator('.desktop-icon[data-id="Maintenance"], .desktop-icon:has-text("Maintenance")')
        check("contract 4: no separate Maintenance launcher tile", tile.count() == 0)

        # --- 5: tile drag-to-reorder disabled (dragstart is prevented) ---
        prevented = page.evaluate(
            """() => { const t = document.querySelector('.desktop-container .desktop-icon');
                       if (!t) return null;
                       const ev = new DragEvent('dragstart', {bubbles: true, cancelable: true});
                       t.dispatchEvent(ev);
                       return ev.defaultPrevented; }""")
        check("contract 5: tile dragstart prevented", prevented is True, repr(prevented))

        page.goto(BASE + "/desk/assets")
        wait_desk(page)
        entry = page.locator('.sidebar-items a.item-anchor[href="/desk/maintenance"]')
        card = page.locator('[shortcut_name="Maintenance"] .widget')
        check("contract 4: Assets shows the Maintenance card", card.count() == 1 and card.is_visible())
        check("contract 4: Assets sidebar has one Maintenance entry", entry.count() == 1)
        if entry.count() == 1:
            entry.click()
            page.wait_for_function("() => frappe.app.sidebar.current_module === 'Maintenance'")
            check("contract 4: Assets entry opens the full Maintenance workspace",
                  page.evaluate("frappe.app.sidebar.current_module") == "Maintenance"
                  and page.url.rstrip('/').endswith('/desk/maintenance'))

        # --- 6: report opened outside Maintenance keeps a real workspace sidebar ---
        # (the v132 bug class: resolve_sidebar trusting stale localStorage bled the
        # Website/Framework sidebar onto report pages). Exact workspace may vary
        # (several link General Ledger); the contract is "a desk workspace, never
        # Website/Framework/empty". Runs LAST — it navigates off the launcher that
        # contracts 4/5 assert against.
        page.goto(BASE + "/app/query-report/General%20Ledger")
        wait_desk(page)
        title = page.evaluate(
            "() => (frappe.app && frappe.app.sidebar && (frappe.app.sidebar.current_module || frappe.app.sidebar.sidebar_title)) || ''")
        check("contract 6: no Website/Framework sidebar bleed on reports",
              title.strip().lower() not in ("", "website", "frappe framework"),
              "sidebar_title=" + repr(title))

        # --- 7: report table body re-fits when the viewport width changes ---
        # (the 2026-09-16 bug: frappe-datatable only re-fits layout:'fluid' tables on
        # resize; desk reports are 'fixed', so a table rendered on the laptop screen
        # and dragged to a wider display kept its body at the old width with its
        # vertical scrollbar stranded mid-page). Still on General Ledger from #6.
        measure = """() => { const w = document.querySelector('.page-container:not([style*="display: none"]) .datatable')
                               || document.querySelector('.datatable');
                             const b = w && w.querySelector('.dt-scrollable');
                             const r = b && b.querySelector('.dt-row');
                             if (!w || !b) return null;
                             return { wrapper: w.clientWidth, body: b.getBoundingClientRect().width,
                                      row: r ? r.getBoundingClientRect().width : null }; }"""
        page.set_viewport_size({"width": 1000, "height": 800})
        page.wait_for_timeout(900)
        narrow = page.evaluate(measure)
        page.set_viewport_size({"width": 1700, "height": 800})
        page.wait_for_timeout(900)
        wide = page.evaluate(measure)
        ok = False
        if narrow and wide and wide["wrapper"] > narrow["wrapper"] + 300:
            expected = wide["wrapper"] if wide["row"] is None else min(wide["wrapper"], wide["row"] + 10)
            ok = abs(wide["body"] - expected) <= 12 and wide["body"] > narrow["body"] + 100
        check("contract 7: report body re-fits after viewport resize",
              ok, "narrow=%r wide=%r" % (narrow, wide))

        # New Framework owns each page's title trail separately. Verify cached revisits too.
        for slug, title, shell in [("financial-overview", "Financial Overview", "Accounts"),
                            ("maintenance-workbench", "Maintenance Workbench", "Maintenance"),
                            ("financial-overview", "Financial Overview", "Accounts")]:
            page.goto(BASE + "/desk/" + slug)
            wait_desk(page)
            trail = page.evaluate("() => frappe.get_current_page().get_breadcrumbs()")
            check("contract 1: " + title + " preserves its title and " + shell + " trail",
                  len(trail) >= 3 and trail[0].get("href") == "/desk"
                  and trail[1].get("label") == shell and trail[-1].get("label") == title,
                  repr(trail))

        # --- 8: idle warning, then lock in place (2026-10-06) ---
        # Runs LAST: the lock ends this session on the server. A fresh context with
        # Playwright's fake clock, carrying this run's cookies, so nothing waits real
        # minutes. Creates nothing.
        ctx8 = browser.new_context()
        ctx8.clock.install()
        ctx8.add_cookies(ctx.cookies())
        p8 = ctx8.new_page()
        p8.goto(BASE + "/app")
        wait_desk(p8)
        cfg = p8.evaluate("() => (window.frappe && frappe.boot && frappe.boot.nexum_idle_lock) || null")
        if not cfg or not cfg.get("enabled"):
            check("contract 8: idle lock switched off on this site (skipped)", True, repr(cfg))
        else:
            p8.wait_for_function("() => document.documentElement.dataset.nxIdle === 'on'")
            ctx8.clock.fast_forward(cfg["idle_minutes"] * 60000 + 1000)
            p8.wait_for_timeout(400)
            check("contract 8: warning after the configured idle minutes",
                  p8.locator("#nx-idle-warning").is_visible())
            with p8.expect_response(lambda r: r.url.endswith("/api/method/logout")):
                ctx8.clock.fast_forward(61000)
            p8.wait_for_timeout(400)
            check("contract 8: locks in place when the warning runs out",
                  p8.locator("#nx-idle-lock").is_visible() and "/login" not in p8.url, p8.url)
            r = p8.request.get(BASE + "/api/method/frappe.auth.get_logged_user")
            check("contract 8: the server session is gone", r.status in (401, 403), str(r.status))
        ctx8.close()

        browser.close()

    failed = [r for r in results if not r[1]]
    print("\n%d/%d contract checks passed" % (len(results) - len(failed), len(results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
