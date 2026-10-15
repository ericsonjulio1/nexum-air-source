#!/usr/bin/env python3
"""Read-only suite navigation, appearance and financial doorway acceptance."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ['BASE_URL'].rstrip('/')
OUTPUT = Path(os.environ.get('OUTPUT_DIR', '/tmp/nexum-suite-smoke'))


def ready(page):
    page.wait_for_load_state('networkidle')
    for _ in range(3):
        if not page.locator('.modal.show').count():
            break
        page.keyboard.press('Escape')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
        context = browser.new_context(viewport={'width':1440, 'height':1000}, color_scheme='dark', reduced_motion='reduce')
        if sid := os.environ.get('SID'):
            context.add_cookies([{'name':'sid', 'value':sid, 'url':BASE}])
        else:
            assert context.request.post(BASE+'/api/method/login', form={
                'usr':os.environ.get('USER_ID','Administrator'), 'pwd':os.environ['PASSWORD'],
            }).ok
        # Deliberately stale preferences must not defeat the signed-in Desk setting.
        context.add_init_script("localStorage.setItem('theme','dark'); localStorage.setItem('vueuse-color-scheme','dark');")
        page = context.new_page()
        page.goto(BASE+'/desk')
        page.locator('.desktop-icon').first.wait_for()
        expected = page.locator('html').get_attribute('data-theme')
        for route, label in [('helpdesk','Helpdesk'),('crm','CRM'),('drive','Drive'),('insights/dashboards','Insights'),('g','Teams')]:
            page.goto(BASE+'/'+route)
            ready(page)
            page.get_by_role('button',name=label,exact=False).first.wait_for()
            assert page.locator('html').get_attribute('data-theme') == expected, (label, expected)
            print('PASS',label,'follows Nexum Air theme despite stale app preference',flush=True)
            page.get_by_role('button',name=label,exact=False).first.click()
            apps = page.get_by_role('menuitem',name='Apps',exact=True)
            apps.hover()
            item = page.get_by_role('menuitem',name='Nexum Air',exact=True)
            item.wait_for(state='visible')
            assert item.count()==1
            page.get_by_role('menuitem',name='Desk',exact=True).wait_for(state='hidden')
            assert page.get_by_role('menuitem',name='Desk',exact=True).count()==0
            assert page.locator('#nexum-apps-btn').count()==0
            page.screenshot(path=str(OUTPUT/(label.lower()+'-apps.png')))
            item.focus()
            item.press('Enter')
            page.locator('.desktop-icon img[alt="Nexum Air"]').wait_for(state='visible')
            assert page.url.rstrip('/')==BASE+'/desk', page.url
            print('PASS',label,'has one keyboard-accessible Nexum Air entry in its top-left Apps menu',flush=True)

        page.goto(BASE+'/desk/accounts/accounting')
        ready(page)
        card=page.locator('[shortcut_name="Financial Overview"] .widget')
        card.wait_for(state='visible')
        card.click()
        page.wait_for_function("frappe.app.sidebar.current_module === 'Accounts' && !!document.querySelector('.fo-cards section')")
        assert page.evaluate('frappe.get_current_page().title')=='Financial Overview'
        assert page.locator('.fo-tabs a').count() >= 10
        page.screenshot(path=str(OUTPUT/'accounts-financial-overview.png'))
        print('PASS Accounts opens the full Financial Overview in the Accounts sidebar',flush=True)
        page.locator('.fo-tabs a[data-view="maintenance"]').click()
        page.wait_for_function("frappe.get_route()[1] === 'maintenance' && frappe.app.sidebar.current_module === 'Accounts'")
        assert page.evaluate('frappe.get_current_page().title')=='Financial Overview'
        page.goto(BASE+'/desk/maintenance-costs')
        ready(page)
        page.wait_for_function("frappe.get_route()[0] === 'financial-overview' && frappe.get_route()[1] === 'maintenance'")
        assert page.evaluate('frappe.app.sidebar.current_module')=='Accounts'
        page.goto(BASE+'/desk/maintenance')
        ready(page)
        assert page.locator('.sidebar-items a').filter(has_text='Maintenance Costs').count()==0
        assert page.locator('.sidebar-items a').filter(has_text='Financial Overview').count()==0
        assert page.locator('.dock-item:visible').count() >= 10
        page.screenshot(path=str(OUTPUT/'maintenance-navigation.png'))
        print('PASS Maintenance has no Financial Overview doorway; all finance views remain in Accounts',flush=True)

        page.goto(BASE+'/desk/accounts/accounting')
        ready(page)
        page.locator('.dashboard-widget-box svg').first.wait_for()
        page.wait_for_timeout(1200)
        style=page.locator('.dashboard-widget-box').first.evaluate("e=>({background:getComputedStyle(e).backgroundColor,radius:getComputedStyle(e).borderRadius})")
        assert style['radius']=='14px',style
        assert style['background']==('rgb(255, 255, 255)' if expected=='light' else 'rgb(32, 40, 46)'),style
        assert page.locator('.number-widget-box').first.evaluate("e=>getComputedStyle(e).borderTopWidth")=='3px'
        assert page.evaluate('NexumCharts.palette()[0]') in ['#168c83','#53c6b7']
        page.screenshot(path=str(OUTPUT/'accounts-report-style.png'))
        print('PASS native workspace charts use the shared report card and palette',flush=True)
        browser.close()


if __name__=='__main__':
    main()
