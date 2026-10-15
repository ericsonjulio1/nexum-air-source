#!/usr/bin/env python3
"""Assets card placement and persistent Maintenance navigation; no business writes.

BASE_URL, PASSWORD (or SID), USER_ID, CHROMIUM_PATH and OUTPUT_DIR follow the
other browser smoke scripts. Requires an Assets workspace and EAM.
"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE_URL', 'http://erpnext.localhost:8080').rstrip('/')
OUTPUT = Path(os.environ['OUTPUT_DIR']) if os.environ.get('OUTPUT_DIR') else None


def ready(page):
    page.wait_for_load_state('networkidle')
    page.locator('#nexum-splash').wait_for(state='detached')
    page.locator('.splash').wait_for(state='detached')
    for _ in range(4):
        if not page.locator('.modal.show').count():
            break
        page.keyboard.press('Escape')
    page.wait_for_function('!window.frappe?.request?.ajax_count')


def rail(page):
    return page.locator('.dock-item:visible').evaluate_all('(items) => items.map(e => e.getAttribute("aria-label"))')


def capture(page, name):
    if OUTPUT:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        page.wait_for_function("[...document.querySelectorAll('.widget')].every(e => getComputedStyle(e).opacity === '1')")
        page.mouse.move(1400, 980)
        page.screenshot(path=str(OUTPUT / name))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        if sid := os.environ.get('SID'):
            ctx.add_cookies([{'name': 'sid', 'value': sid, 'url': BASE}])
        else:
            assert ctx.request.post(BASE + '/api/method/login', form={
                'usr': os.environ.get('USER_ID', 'Administrator'), 'pwd': os.environ['PASSWORD'],
            }).ok, 'Login failed'
        page = ctx.new_page()
        assert page.goto(BASE + '/desk/assets').ok
        ready(page)
        card = page.locator('[shortcut_name="Maintenance"] .widget')
        card.wait_for(state='visible')
        reports = page.locator('[card_name="Asset Reports"] .widget').bounding_box()
        setup = page.locator('[card_name="Setup"] .widget').bounding_box()
        box = card.bounding_box()
        assert abs(box['y'] - reports['y']) < 2 and abs(box['y'] - setup['y']) < 2, 'Maintenance must share the Asset Reports / Setup row'
        assert box['x'] > setup['x'] > reports['x'], 'Maintenance must occupy the third card slot'
        assert abs(box['width'] - reports['width']) < 2 and abs(box['height'] - reports['height']) < 2, 'Maintenance must match its neighboring card dimensions'
        capture(page, 'assets-maintenance-card.png')
        print('PASS Maintenance fills the third card slot beside Asset Reports and Setup')
        expected = rail(page)
        assert 'Assets' in expected and len(expected) > 1
        before = len(ctx.pages)
        card.click()
        page.wait_for_function("frappe.app.sidebar.current_module === 'Maintenance'")
        ready(page)
        assert page.url.rstrip('/') == BASE + '/desk/maintenance'
        assert len(ctx.pages) == before
        assert rail(page) == expected, 'Maintenance must retain the Nexum Air module rail'
        capture(page, 'maintenance-with-rail.png')
        print('PASS Assets card opens Maintenance in place with the same module rail')
        # Refresh/direct links and child routes must share the host rail as well.
        for route in ('/desk/maintenance', '/desk/maintenance-work-order', '/desk/maintenance-workbench', '/desk/query-report/Schedule%20Compliance'):
            assert page.goto(BASE + route).ok
            ready(page)
            assert page.evaluate('frappe.app.sidebar.current_module') == 'Maintenance', route
            assert rail(page) == expected, route
            assert '/my_branding/images/icons/erpnext_app.svg' in page.locator('.dock-logo img').get_attribute('src')
            print('PASS Maintenance navigation and Nexum Air logo persist on ' + route)
        page.locator('.dock-item[aria-label="Assets"]').click()
        page.locator('[shortcut_name="Maintenance"] .widget').wait_for(state='visible')
        ready(page)
        assert page.evaluate('frappe.app.sidebar.current_module') == 'Assets'
        page.locator('.sidebar-items a[href="/desk/maintenance"]').click()
        page.wait_for_function("frappe.app.sidebar.current_module === 'Maintenance'")
        ready(page)
        assert rail(page) == expected
        print('PASS module rail returns to Assets and its sidebar link reopens Maintenance')
        browser.close()


if __name__ == '__main__':
    main()
