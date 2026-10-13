const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../public/js/navigation.js'), 'utf8');

function setup(modern = true) {
	class Page { get_breadcrumbs() { return this.breadcrumbs || []; } render_breadcrumbs() { this.rendered = this.get_breadcrumbs(); } }
	let current = new Page();
	const events = {}, tasks = [];
	const frappe = { boot: modern ? { module_sidebars: { Maintenance: { label: 'Maintenance' }, Accounts: { label: 'Accounts' } } } : {},
		ui: { Page }, app: { sidebar: { current_module: 'Maintenance' } }, get_current_page: () => current,
		router: { on: (name, fn) => { events[name] = fn; } } };
	const context = { frappe, document: {}, __: x => x, queueMicrotask: fn => tasks.push(fn),
		$: () => ({ on: (name, fn) => { events[name] = fn; } }) };
	vm.runInNewContext(source, context);
	return { frappe, Page, events, tasks, context, page: current,
		flush() { while (tasks.length) tasks.shift()(); }, select(page) { current = page; } };
}
const plain = value => JSON.parse(JSON.stringify(value));

test('Maintenance has home and workspace navigation without mutating the page trail', () => {
	const s = setup(); s.page.breadcrumbs = [{ label: 'Schedule Compliance' }]; s.flush();
	assert.deepEqual(plain(s.page.rendered), [
		{ href: '/desk', prefix: 'house', title: 'Home' },
		{ label: 'Maintenance', href: '/desk/maintenance' }, { label: 'Schedule Compliance' }]);
	assert.deepEqual(s.page.breadcrumbs, [{ label: 'Schedule Compliance' }]);
});
test('changing sidebar repaints the visible page without stale Maintenance context', () => {
	const s = setup(); s.page.breadcrumbs = [{ label: 'General Ledger' }]; s.flush();
	s.events.sidebar_setup(); s.frappe.app.sidebar.current_module = 'Accounts'; s.flush();
	assert.deepEqual(plain(s.page.rendered).map(x => x.label || x.title), ['Home', 'General Ledger']);
});
test('background pages and dialog pages keep their own breadcrumb state', () => {
	const s = setup(); const other = new s.Page(); other.breadcrumbs = [{ label: 'Other' }];
	assert.deepEqual(other.get_breadcrumbs(), other.breadcrumbs);
	s.page.show_breadcrumbs = false; assert.deepEqual(s.page.get_breadcrumbs(), []);
});
test('Maintenance home is not repeated and repeated script evaluation does not stack adapters', () => {
	const s = setup(); s.page.breadcrumbs = [{ label: 'Maintenance' }];
	vm.runInNewContext(source, s.context); s.flush();
	assert.equal(s.page.rendered.length, 2);
});
test('older Framework keeps its existing breadcrumb implementation', () => {
	const s = setup(false); s.page.breadcrumbs = [{ label: 'Legacy' }];
	assert.deepEqual(s.page.get_breadcrumbs(), [{ label: 'Legacy' }]);
	assert.equal(s.tasks.length, 0);
});

test('Maintenance uses stable shell identity with a translated workspace label', () => {
    const s = setup(); s.frappe.boot.module_sidebars.Maintenance.label = 'Wartung';
    s.page.breadcrumbs = [{ label: 'Plan' }]; s.flush();
    assert.equal(s.page.rendered[1].label, 'Wartung');
    s.page.breadcrumbs = [{ label: 'Wartung' }]; s.page.render_breadcrumbs();
    assert.equal(s.page.rendered.length, 2);
});
