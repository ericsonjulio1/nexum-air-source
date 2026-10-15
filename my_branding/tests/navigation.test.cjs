const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../public/js/navigation.js'), 'utf8');

function setup(modern = true) {
	class Page { get_breadcrumbs() { return this.breadcrumbs || []; } render_breadcrumbs() { this.rendered = this.get_breadcrumbs(); } }
	class Workspace {
		add_custom_cards_in_content() {
			let index = -1;
			this.content.forEach((b, i) => { if (b.type === 'card') index = i; });
			if (index >= 0) this.content.splice(index + 1, 0,
				{ type: 'card', data: { card_name: 'Custom Documents', col: 4 } },
				{ type: 'card', data: { card_name: 'Custom Reports', col: 4 } });
		}
	}
	let current = new Page();
	const events = {}, tasks = [];
	const frappe = { boot: modern ? { module_sidebars: { Maintenance: { label: 'Maintenance' }, Accounts: { label: 'Accounts' } } } : {},
		views: { Workspace }, ui: { Page, sidebar_item: { get_route: (item, edit, shell) => `${shell}:${item.link_to}:${edit}` } }, app: { sidebar: { current_module: 'Maintenance' } }, get_current_page: () => current,
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

test('Assets doorway remains beside its cards after Framework injects custom-card placeholders', () => {
	const s = setup();
	const workspace = new s.frappe.views.Workspace();
	workspace._page = { name: 'Assets' };
	workspace.content = [
		{ type: 'card', data: { card_name: 'Asset Reports' } },
		{ type: 'card', data: { card_name: 'Setup' } },
		{ id: 'eam-maintenance-entry', type: 'shortcut', data: { shortcut_name: 'Maintenance', col: 4 } },
		{ type: 'paragraph', data: { text: 'Tenant note' } },
	];
	workspace.add_custom_cards_in_content();
	assert.equal(workspace.content[2].id, 'eam-maintenance-entry');
	assert.deepEqual(plain(workspace.content.slice(3).map(b => b.data.card_name || b.data.text)),
		['Custom Documents', 'Custom Reports', 'Tenant note']);
	workspace._page = { name: 'Other' };
	workspace.content = [{ type: 'card', data: { card_name: 'Setup' } }];
	workspace.add_custom_cards_in_content();
	assert.equal(workspace.content.length, 3);
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

test('Assets Maintenance doorway switches shell without changing other sidebar links or editor routes', () => {
	const s = setup();
	const link = { type: 'Link', link_type: 'Workspace', link_to: 'Maintenance' };
	assert.equal(s.frappe.ui.sidebar_item.get_route(link, false, 'Assets'), '/desk/maintenance');
	assert.equal(s.frappe.ui.sidebar_item.get_route(link, true, 'Assets'), 'Assets:Maintenance:true');
	assert.equal(s.frappe.ui.sidebar_item.get_route(link, false, 'Maintenance'), 'Maintenance:Maintenance:false');
	assert.equal(s.frappe.ui.sidebar_item.get_route({ ...link, link_to: 'Asset' }, false, 'Assets'), 'Assets:Asset:false');
	vm.runInNewContext(source, s.context);
	assert.equal(s.frappe.ui.sidebar_item.get_route(link, false, 'Assets'), '/desk/maintenance');
});
