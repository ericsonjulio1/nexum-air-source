// Exercise the patched upstream implementations, not copies of their methods.
// BENCH_ROOT points to a v211 bench (or an extracted, patched v210 source tree).
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const root = process.env.BENCH_ROOT;
assert.ok(root, 'Set BENCH_ROOT');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const resourceDir = 'apps/gameplan/frontend/node_modules/frappe-ui/src/resources/';
const withoutImports = text => text.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\n/gm, '');

function resources() {
  const watchers = [];
  let mixin;
  const ctx = { console, reactive: x => x, watch: (get, cb) => {
    watchers.push(cb); cb(get());
  }, getCacheKey: key => key ? JSON.stringify(key) : null,
  saveLocal() {}, getLocal: () => Promise.resolve(null), getConfig() {},
  createResource(options) { return {
    fetches: 0, loading: false, fetched: false,
    fetch() { this.fetches++; return Promise.resolve(); },
    submit() { this.fetches++; return Promise.resolve(); },
  }; }, createDocumentResource() { throw Error('not a list'); } };
  // Use Vue's real reactive proxies when running inside the built image.
  if (fs.existsSync(path.join(root, 'apps/gameplan/frontend/node_modules/vue'))) {
    ctx.reactive = require(path.join(root, 'apps/gameplan/frontend/node_modules/vue')).reactive;
  }
  vm.createContext(ctx);
  vm.runInContext(read(resourceDir + 'realtime.js').replace(/export /g, ''), ctx);
  vm.runInContext(withoutImports(read(resourceDir + 'listResource.js')).replace(/export /g, ''), ctx);
  vm.runInContext(withoutImports(read(resourceDir + 'plugin.js')).replace('export default', 'globalThis.plugin ='), ctx);
  ctx.plugin.install({ mixin(value) { mixin = value; } });
  return { ctx, mixin, watchers };
}

test('uncached list disposal stops global row fanout and only its realtime listener', () => {
  const { ctx } = resources();
  const listeners = new Set();
  const socket = { emit() {}, on: (_, fn) => listeners.add(fn), off: (_, fn) => listeners.delete(fn) };
  const opts = { doctype: 'GP Followed Project', realtime: true };
  const departed = ctx.createListResource(opts, { $socket: socket });
  const active = ctx.createListResource(opts, { $socket: socket });
  departed.setData([{ name: 'one', title: 'before' }]);
  active.setData([{ name: 'one', title: 'before' }]);
  assert.equal(listeners.size, 2);
  departed.dispose(); departed.dispose();
  ctx.updateRowInListResource(opts.doctype, { name: 'one', title: 'after' });
  assert.equal(departed.data[0].title, 'before');
  assert.equal(active.data[0].title, 'after');
  assert.equal(listeners.size, 1);
  for (const handler of listeners) handler({ doctype: opts.doctype, name: 'one' });
  assert.equal(active.fetchOne.fetches, 1);
  assert.equal(departed.fetchOne.fetches, 0);
  active.dispose();
  assert.equal(listeners.size, 0);
});

test('a shared cached list survives one component leaving', () => {
  const { ctx } = resources();
  const opts = { doctype: 'GP Discussion', cache: ['shared'] };
  const first = ctx.createListResource(opts, {});
  first.setData([{ name: 'one', title: 'before' }]);
  first.dispose();
  const second = ctx.createListResource(opts, {});
  assert.equal(first, second);
  ctx.updateRowInListResource(opts.doctype, { name: 'one', title: 'after' });
  assert.equal(second.data[0].title, 'after');
});

test('resource mixin releases replaced, disabled and unmounted list consumers', () => {
  const { ctx, mixin, watchers } = resources();
  const options = { type: 'list', doctype: 'GP Followed Project', filters: { active: 1 } };
  const instance = { $options: { resources: { followed: () => options } } };
  mixin.created.call(instance);
  const old = instance._resources.followed;
  old.setData([{ name: 'one', title: 'old' }]);
  watchers[0]({ ...options, filters: { active: 2 } }, options);
  const current = instance._resources.followed;
  current.setData([{ name: 'one', title: 'current' }]);
  ctx.updateRowInListResource(options.doctype, { name: 'one', title: 'new' });
  assert.equal(old.data[0].title, 'old');
  assert.equal(current.data[0].title, 'new');
  watchers[0](null, options);
  assert.equal(instance._resources.followed, undefined);
  ctx.updateRowInListResource(options.doctype, { name: 'one', title: 'disabled' });
  assert.equal(current.data[0].title, 'new');
  watchers[0](options, null);
  const final = instance._resources.followed;
  final.setData([{ name: 'one', title: 'last' }]);
  mixin.beforeUnmount.call(instance);
  ctx.updateRowInListResource(options.doctype, { name: 'one', title: 'unmounted' });
  assert.equal(final.data[0].title, 'last');
});

test('discussion first activation does not duplicate auto fetch; later activation refreshes', () => {
  const source = read('apps/gameplan/frontend/src/components/DiscussionList.vue').split('<script>')[1].split('</script>')[0];
  const ctx = { TextEditor: {}, Tooltip: {} };
  vm.runInNewContext(withoutImports(source).replace('export default', 'globalThis.component ='), ctx);
  let reloads = 0;
  const resource = { list: { loading: false }, reload: () => reloads++ };
  const instance = { ...ctx.component.data(), $resources: { discussions: resource } };
  ctx.component.activated.call(instance);
  assert.equal(reloads, 0);
  ctx.component.activated.call(instance);
  assert.equal(reloads, 1);
  resource.list.loading = true;
  ctx.component.activated.call(instance);
  assert.equal(reloads, 1, 'an already in-flight list is not duplicated');
});

function chartWidget() {
  const ctx = { Widget: class { delete(...args) { return args; } },
    frappe: { provide() {} } };
  vm.runInNewContext(withoutImports(read('apps/frappe/frappe/public/js/frappe/widgets/chart_widget.js'))
    .replace('export default class', 'globalThis.ChartWidget = class'), ctx);
  const instance = Object.create(ctx.ChartWidget.prototype);
  let destroys = 0;
  instance.dashboard_chart = { destroy() { destroys++; } };
  return { instance, destroys: () => destroys };
}

test('chart refresh destroys the old instance once before making a replacement', () => {
  const { instance, destroys } = chartWidget();
  instance.set_body = () => {};
  instance.make_chart = () => assert.equal(destroys(), 1);
  instance.refresh();
  instance.destroy_chart();
  assert.equal(destroys(), 1);
});

test('chart removal disposes its chart and preserves the parent deletion contract', () => {
  const { instance, destroys } = chartWidget();
  assert.deepEqual(instance.delete(false, true), [false, true]);
  assert.equal(instance.deleted, true);
  assert.equal(destroys(), 1);
});

test('a chart removed while settings load cannot create another chart', async () => {
  const { instance, destroys } = chartWidget();
  let resolve;
  instance.get_settings = () => new Promise(done => { resolve = done; });
  instance.setup_container = () => assert.fail('removed widget rendered again');
  instance.make_chart();
  instance.delete(false);
  resolve();
  await Promise.resolve();
  assert.equal(destroys(), 1);
});
