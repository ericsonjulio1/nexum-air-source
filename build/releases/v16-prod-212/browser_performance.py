"""Read-only regression checks against a running release. Requires Playwright.

Set BASE_URL, CHROMIUM_PATH, OUTPUT_DIR and either SID_FILE or USER_ID/PASSWORD.
SID_FILE contains {"sid": "..."}; it is never copied into the evidence output.
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
    ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
    if os.environ.get('SID_FILE'):
        sid = json.loads(Path(os.environ['SID_FILE']).read_text())['sid']
        ctx.add_cookies([{'name': 'sid', 'value': sid, 'domain': urlparse(base).hostname,
                         'path': '/', 'secure': base.startswith('https:')}])
    else:
        response = ctx.request.post(base + '/api/method/login', form={
            'usr': os.environ['USER_ID'], 'pwd': os.environ['PASSWORD']})
        assert response.ok, 'QA login failed'
    page = ctx.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(90000)
    cdp = ctx.new_cdp_session(page)
    cdp.send('Performance.enable')
    errors = []
    requests = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: requests.append(json.loads(r.post_data or '{}'))
            if 'gp_discussion.api.get_discussions' in r.url else None)

    def settle():
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(250)

    def memory():
        cdp.send('HeapProfiler.collectGarbage')
        return {'dom': cdp.send('Memory.getDOMCounters'), 'heap_bytes': next(
            m['value'] for m in cdp.send('Performance.getMetrics')['metrics']
            if m['name'] == 'JSHeapUsedSize')}

    def check_single(label, action, feed='recent', order='last_post_at desc'):
        requests.clear()
        with page.expect_response(lambda response: 'gp_discussion.api.get_discussions' in response.url) as response:
            action()
        assert response.value.ok, f'{label}: discussion request failed'
        # Reading the body waits for completion without leaving an outstanding
        # Response.finished context-close waiter in older Playwright versions.
        response.value.json()
        settle()
        assert len(requests) == 1, f'{label}: expected one request, got {len(requests)}'
        request = requests[0]
        filters = request.get('filters', {})
        if isinstance(filters, str):
            filters = json.loads(filters)
        assert filters.get('feed_type') == feed, (label, filters)
        assert request.get('order_by') == order, (label, request.get('order_by'))
        return {'action': label, 'requests': 1, 'feed': feed, 'order': order}

    try:
        result['requests'] = [check_single('initial load', lambda: page.goto(base + '/g'))]
        page.get_by_role('link', name='Discussions', exact=True).first.wait_for()
        samples = []
        for cycle in range(1, 21):
            tasks = page.get_by_role('link', name='My Tasks', exact=True).first
            target = tasks.get_attribute('href')
            tasks.click()
            # Lazy route loading can outlive the prior document's idle state.
            page.wait_for_url(base + target)
            settle()
            result['requests'].append(check_single(f'route revisit {cycle}', lambda:
                page.get_by_role('link', name='Discussions', exact=True).first.click()))
            if cycle in (1, 5, 10, 20):
                samples.append({'cycle': cycle, **memory()})
                print('Teams cycle', cycle, json.dumps(samples[-1]), flush=True)
        result['teams_memory'] = samples
        assert samples[-1]['dom']['nodes'] - samples[0]['dom']['nodes'] < 150, 'Teams retains route DOM'
        assert samples[-1]['dom']['jsEventListeners'] - samples[0]['dom']['jsEventListeners'] < 30, 'Teams retains route listeners'

        # Kept-alive tabs must still fetch fresh data when revisited.
        for label, feed in [('Unread', 'unread'), ('Following', 'following'),
                            ('Recent', 'recent'), ('Unread', 'unread'), ('Recent', 'recent')]:
            result['requests'].append(check_single('tab ' + label, lambda label=label:
                page.get_by_role('radio', name=label, exact=True).click(), feed=feed))
        result['requests'].append(check_single('sort Created', lambda:
            page.locator('select').select_option('creation desc'), order='creation desc'))
        result['requests'].append(check_single('restore Last post sort', lambda:
            page.locator('select').select_option('last_post_at desc')))
        print('PASS single discussion fetch and fresh tab/sort requests', flush=True)

        page.goto(base + '/desk/assets')
        page.locator('.dashboard-widget-box svg').first.wait_for()
        settle()
        page.evaluate('''() => {
            window.__qaCharts = [];
            const Original = frappe.Chart;
            frappe.Chart = new Proxy(Original, {construct(target, args, newTarget) {
                const chart = Reflect.construct(target, args, newTarget);
                window.__qaCharts.push(new WeakRef(chart));
                return chart;
            }});
        }''')
        charts = []
        for cycle in range(1, 11):
            page.locator('.dashboard-widget-box [data-action="action-refresh"]').first.evaluate('e => e.click()')
            page.wait_for_function('(n) => window.__qaCharts.length === n', arg=cycle)
            settle()
            if cycle in (1, 5, 10):
                sample = {'refreshes': cycle, **memory()}
                sample['retained'] = page.evaluate('''() => window.__qaCharts.map(r => r.deref())
                    .filter(Boolean).map(c => ({connected: c.container?.isConnected}))''')
                charts.append(sample)
                print('Chart refresh', cycle, json.dumps(sample), flush=True)
        result['charts'] = charts
        # Native entry/SMIL animation timers briefly retain the last charts even
        # after their resize/observer ownership is released. Wait beyond those
        # bounded timers without triggering a resize or doing any cleanup here.
        page.wait_for_timeout(2000)
        result['chart_settled_memory'] = memory()
        retained = page.evaluate('''() => window.__qaCharts.map(r => r.deref())
            .filter(Boolean).map(c => ({connected: c.container?.isConnected}))''')
        result['chart_settled'] = retained
        print('Settled charts', json.dumps(retained), flush=True)
        assert len(retained) == 1 and retained[0]['connected'], 'Old chart instances remain after Refresh and animation timers settle'
        assert charts[-1]['dom']['jsEventListeners'] - charts[0]['dom']['jsEventListeners'] < 5, 'Chart listeners accumulate'
        result['page_errors'] = errors
        assert not errors, errors
        result['passed'] = True
        print('PASS Teams teardown, discussion freshness and chart lifecycle', flush=True)
    finally:
        (output / 'performance.json').write_text(json.dumps(result, indent=2) + '\n')
        browser.close()
