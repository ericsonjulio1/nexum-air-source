#!/usr/bin/env python3
"""Apps-mode branding and cross-app navigation checks (2026-10-15 regression).

Use BASE_URL, USER_ID, PASSWORD (or SID) and optional CHROMIUM_PATH / OUTPUT_DIR,
as with ux_contract_smoke.py. Requires a site with Apps mode and Helpdesk/EAM.
This changes no business data. The full UX contract remains a separate check.
"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://erpnext.localhost:8080").rstrip("/")
OUTPUT = Path(os.environ["OUTPUT_DIR"]) if os.environ.get("OUTPUT_DIR") else None


def ready(page):
    page.wait_for_load_state("networkidle")
    for _ in range(4):
        if not page.locator(".modal.show").count():
            break
        page.keyboard.press("Escape")


def screenshot(page, name):
    if OUTPUT:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUTPUT / name))


def launcher(page):
    page.locator('.desktop-icon img[alt="Nexum Air"]').wait_for(state="visible")
    assert page.url.rstrip("/") == BASE + "/desk", page.url


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH"))
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        if sid := os.environ.get("SID"):
            ctx.add_cookies([{"name": "sid", "value": sid, "url": BASE}])
        else:
            assert ctx.request.post(BASE + "/api/method/login", form={
                "usr": os.environ.get("USER_ID", "Administrator"), "pwd": os.environ["PASSWORD"],
            }).ok, "Login failed"
        page = ctx.new_page()
        page.goto(BASE + "/desk")
        launcher(page)
        logo = page.locator('.desktop-icon img[alt="Nexum Air"]')
        assert "/my_branding/images/icons/erpnext_app.svg" in logo.get_attribute("src")
        for icon in page.locator('.desktop-icon img[src*="/my_branding/images/icons/"]').all():
            assert icon.evaluate("e => getComputedStyle(e).filter") == "none"
        screenshot(page, "suite-launcher.png")
        print("PASS suite launcher uses the existing slate brand icons without hue shifts")

        page.locator('.desktop-icon .icon-title', has_text="Nexum Air").click()
        page.locator('.dock-item[aria-label="Assets"]').wait_for(state="visible")
        assert "/my_branding/images/icons/erpnext_app.svg" in page.locator('.dock-logo img').get_attribute("src")
        page.locator('.dock-item[aria-label="Assets"]').click()
        card = page.locator('[shortcut_name="Maintenance"] .widget')
        card.wait_for(state="visible")
        screenshot(page, "assets-maintenance-entry.png")
        before = len(ctx.pages)
        card.click()
        page.wait_for_function("frappe.app.sidebar.current_module === 'Maintenance'")
        assert page.url.rstrip("/") == BASE + "/desk/maintenance", page.url
        assert len(ctx.pages) == before, "Internal Maintenance card opened another window"
        print("PASS Nexum Air → Assets → Maintenance card opens the full workspace in place")

        page.goto(BASE + "/desk/assets")
        entry = page.locator('.sidebar-items a[href="/desk/maintenance"]')
        entry.wait_for(state="visible")
        assert entry.count() == 1
        entry.click()
        page.wait_for_function("frappe.app.sidebar.current_module === 'Maintenance'")
        assert page.url.rstrip("/") == BASE + "/desk/maintenance"
        print("PASS Assets sidebar enters Maintenance with its own navigation")

        for label, keyboard in (("Nexum Air", False), ("Nexum Air", True), ("CRM", False)):
            page.goto(BASE + "/helpdesk")
            ready(page)
            page.get_by_role("button", name="Helpdesk", exact=False).first.click()
            page.get_by_text("Apps", exact=True).last.hover()
            item = page.get_by_role("menuitem", name=label, exact=True)
            item.wait_for(state="visible")
            assert page.get_by_role("menuitem", name="Desk", exact=True).count() == 0
            if keyboard:
                item.focus()
                item.press("Enter")
            else:
                item.click()
            if label == "CRM":
                page.wait_for_url(BASE + "/crm/**")
            else:
                launcher(page)
            print(f"PASS Helpdesk {label} ({'keyboard' if keyboard else 'click'}) → {page.url.removeprefix(BASE)}")
        browser.close()


if __name__ == "__main__":
    main()
