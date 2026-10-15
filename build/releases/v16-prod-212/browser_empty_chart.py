"""Read-only regression for native empty-chart ownership; no records are changed.

Set BASE_URL, OUTPUT_DIR, CHROMIUM_PATH and SID_FILE. Optional
CHROMIUM_HOST_RULES supports a private origin tunnel.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

base = os.environ['BASE_URL'].rstrip('/')
output = Path(os.environ['OUTPUT_DIR'])
output.mkdir(parents=True, exist_ok=True)
result = {}
with sync_playwright() as p:
    launch = {'headless': True}
    if os.environ.get('CHROMIUM_PATH'):
        launch['executable_path'] = os.environ['CHROMIUM_PATH']
    if os.environ.get('CHROMIUM_HOST_RULES'):
        launch['args'] = ['--host-resolver-rules=' + os.environ['CHROMIUM_HOST_RULES']]
    browser = p.chromium.launch(**launch)
    context = browser.new_context()
    sid = json.loads(Path(os.environ['SID_FILE']).read_text())['sid']
    context.add_cookies([{'name': 'sid', 'value': sid, 'domain': urlparse(base).hostname,
                         'path': '/', 'secure': base.startswith('https:')}])
    page = context.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(90000)
    try:
        page.goto(base + '/desk/assets')
        page.wait_for_function('!!window.frappe?.widget?.widget_factory?.chart')
        page.wait_for_load_state('networkidle')
        page.evaluate('''() => {
            const widget = Object.create(frappe.widget.widget_factory.chart.prototype);
            widget.chart_doc = {type: 'Line'};
            widget.height = 240;
            widget.empty = $('<div>').appendTo(document.body);
            widget.get_chart_colors = () => ['#168c83'];
            window.__qaEmptyWidget = widget;
            window.__qaEmptyRefs = [];
            const make = frappe.utils.make_chart;
            frappe.utils.make_chart = function(...args) {
                const chart = make.apply(this, args);
                window.__qaEmptyRefs.push(new WeakRef(chart));
                return chart;
            };
        }''')
        for _ in range(10):
            page.evaluate('window.__qaEmptyWidget.show_empty_state()')
            page.wait_for_timeout(150)
        page.wait_for_timeout(2000)
        cdp = context.new_cdp_session(page)
        cdp.send('HeapProfiler.collectGarbage')
        retained = 'window.__qaEmptyRefs.map(r => r.deref()).filter(Boolean).map(c => ({connected: c.container.isConnected}))'
        result['after_ten_redraws'] = page.evaluate(retained)
        assert result['after_ten_redraws'] == [{'connected': True}], result
        # Exercise the owner's real cleanup; do not dispose individual chart refs.
        page.evaluate('''() => {
            window.__qaEmptyWidget.destroy_chart();
            window.__qaEmptyWidget.empty.remove();
            delete window.__qaEmptyWidget;
        }''')
        page.wait_for_timeout(2000)
        cdp.send('HeapProfiler.collectGarbage')
        result['after_owner_cleanup'] = page.evaluate(retained)
        assert result['after_owner_cleanup'] == [], result
        result['passed'] = True
        print('PASS empty charts: ten redraws retain one active chart; owner cleanup retains none', flush=True)
    finally:
        (output / 'empty-charts.json').write_text(json.dumps(result, indent=2) + '\n')
        browser.close()
