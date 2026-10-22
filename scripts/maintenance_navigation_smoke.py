#!/usr/bin/env python3
"""Assets card placement and persistent Maintenance navigation; no business writes.

BASE_URL, PASSWORD (or SID), USER_ID, CHROMIUM_PATH and OUTPUT_DIR follow the
other browser smoke scripts. Requires an Assets workspace and EAM.
"""
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
    page.wait_for_function("[...document.querySelectorAll('.number-card-loading')].every(e => !e.getBoundingClientRect().width)")
    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')


def rail(page):
    return page.locator('.dock-item:visible').evaluate_all('(items) => items.map(e => e.getAttribute("aria-label"))')


def capture(page, name):
    if OUTPUT:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        page.wait_for_function("""() => {
            const widgets = [...document.querySelectorAll('.widget')].filter(e => e.getBoundingClientRect().width);
            return widgets.length && widgets.every(widget => {
                if (widget.innerText.includes('Loading...')) return false;
                for (let e = widget; e; e = e.parentElement) {
                    if (getComputedStyle(e).opacity !== '1') return false;
                }
                return true;
            });
        }""")
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
        sections = {'work-orders': 'Work Orders', 'pm-planning': 'PM Planning',
                    'reports': 'Reports', 'spare-parts': 'Spare Parts'}
        assert card.locator('[data-nexum-maintenance-section]').all_text_contents() == list(sections.values())
        assert card.get_attribute('role') == 'group', 'Nested links must not sit inside a link role'
        for action in ({'modifiers': ['Meta']}, {'button': 'middle'}):
            with ctx.expect_page() as opened:
                card.locator('[data-nexum-maintenance-section="reports"]').click(**action)
            child = opened.value
            child.wait_for_url(BASE + '/desk/maintenance?section=reports')
            ready(child)
            assert page.url == BASE + '/desk/assets', 'Modified link clicks must keep the source page intact'
            assert len(ctx.pages) == 2, 'A modified link must open exactly one page'
            child.close()
        print('PASS Maintenance section links preserve Command-click and middle-click behavior')
        expected = rail(page)
        assert 'Assets' in expected and len(expected) > 1
        before = len(ctx.pages)
        card.locator('.nx-maintenance-home').click()
        page.wait_for_function("frappe.app.sidebar.current_module === 'Maintenance'")
        ready(page)
        assert page.url.rstrip('/') == BASE + '/desk/maintenance'
        assert len(ctx.pages) == before
        assert rail(page) == expected, 'Maintenance must retain the Nexum Air module rail'
        assert page.locator('[shortcut_name="Maintenance Workbench"]').count() == 0
        assert page.locator('[card_name="Work Orders"] a').filter(has_text='Workbench').count() == 0
        assert page.locator('.sidebar-items a[href$="maintenance-workbench"]').count() == 1
        groups = page.locator('.sidebar-items .indent + .nested-container')
        assert groups.count() >= 5, 'Maintenance must use native nested section groups'
        assert groups.evaluate_all('elements => elements.every(e => getComputedStyle(e).borderLeftWidth === "1px")')
        assert groups.locator('.sidebar-item-icon:visible').count() == 0, 'Grouped links must use the native guide instead of repeated icons'
        print('PASS native sidebar guide lines and one sidebar-only Workbench entry')
        capture(page, 'maintenance-with-rail.png')
        cards = [page.locator(f'[card_name="{name}"] .widget').bounding_box()
                 for name in ('Work Orders', 'PM Planning', 'Reports')]
        assert max(b['y'] for b in cards) - min(b['y'] for b in cards) < 2, 'Link cards must start on one row below the KPIs'
        numbers = page.locator('[number_card_name] .widget').evaluate_all('(elements) => elements.map(e => e.getBoundingClientRect().bottom)')
        assert cards[0]['y'] > max(numbers), 'Link cards must not fill an incomplete KPI row'
        divider = page.locator('.ce-block[data-id="MaintSpacer001"] .widget.spacer')
        assert divider.evaluate('(e) => getComputedStyle(e).borderTopWidth') == '0px'
        print('PASS Maintenance cards align below the KPI rows without a visible divider')
        print('PASS Assets card opens Maintenance in place with the same module rail')
        for section, label in sections.items():
            page.goto(BASE + '/desk/assets')
            ready(page)
            link = page.locator(f'[data-nexum-maintenance-section="{section}"]')
            if section == 'pm-planning':
                link.focus()
                page.keyboard.press('Enter')
            else:
                link.click()
            page.wait_for_function("frappe.app.sidebar.current_module === 'Maintenance'")
            ready(page)
            assert parse_qs(urlparse(page.url).query).get('section') == [section]
            heading = page.locator(f'[card_name="{label}"] .widget-title')
            page.wait_for_function('(e) => document.activeElement === e', arg=heading.element_handle())
            header = page.locator('.page-head:visible').bounding_box()
            assert heading.bounding_box()['y'] >= header['y'] + header['height'], 'Section heading must clear the sticky page header'
            assert heading.bounding_box()['y'] < 900, f'{label} section was not scrolled into view'
            if section == 'spare-parts':
                target = page.locator('[card_name="Spare Parts"] .widget').bounding_box()
                assert target['y'] + target['height'] <= 1000, 'Spare Parts links must remain visible after KPI data finishes loading'
            assert len(ctx.pages) == before and rail(page) == expected
            print(f'PASS Assets {label} link opens and focuses its Maintenance section in place')
        capture(page, 'maintenance-spare-parts.png')
        page.reload()
        ready(page)
        page.wait_for_function("document.activeElement?.closest('[card_name]')?.getAttribute('card_name') === 'Spare Parts'")
        print('PASS direct section URL survives reload')
        # Refresh/direct links and child routes must share the host rail as well.
        for route in ('/desk/maintenance', '/desk/maintenance-work-order', '/desk/maintenance-workbench', '/desk/query-report/Schedule%20Compliance'):
            assert page.goto(BASE + route).ok
            ready(page)
            assert page.evaluate('frappe.app.sidebar.current_module') == 'Maintenance', route
            assert rail(page) == expected, route
            assert '/my_branding/images/icons/erp_app.svg' in page.locator('.dock-logo img').get_attribute('src')
            print('PASS Maintenance navigation and ERP logo persist on ' + route)
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
