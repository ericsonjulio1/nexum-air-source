const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.env.BENCH_ROOT + '/apps/frappe/frappe/public/js/frappe/widgets/chart_widget.js', 'utf8');

function widget() {
  const created = [];
  const element = { 0: {}, appendTo() { return this; }, empty() { return this; },
    show() { return this; }, hide() { return this; }, append() { return this; } };
  const ctx = { Widget: class { delete() {} }, __: s => s, $: () => element,
    frappe: { provide() {}, ui: { empty_state: () => '' }, utils: { make_chart() {
      const chart = { destroyed: 0, destroy() { this.destroyed++; } };
      created.push(chart); return chart;
    } } } };
  vm.runInNewContext(source.replace(/^import .*;\n/m, '')
    .replace('export default class', 'globalThis.ChartWidget = class'), ctx);
  const instance = Object.create(ctx.ChartWidget.prototype);
  Object.assign(instance, { empty: element, chart_doc: { type: 'Line' }, height: 240,
    get_chart_colors: () => ['#168c83'] });
  return { instance, element, created };
}

test('redrawing an empty line chart disposes each previous placeholder', () => {
  const { instance, created } = widget();
  for (let i = 0; i < 10; i++) instance.show_empty_state();
  assert.equal(created.length, 10);
  assert.ok(created.slice(0, -1).every(c => c.destroyed === 1));
  assert.equal(created.at(-1).destroyed, 0);
  instance.delete(false);
  assert.ok(created.every(c => c.destroyed === 1));
  instance.destroy_chart();
  assert.ok(created.every(c => c.destroyed === 1), 'repeated cleanup is idempotent');
});

test('data arriving replaces and disposes the no-data placeholder', async () => {
  const { instance, element, created } = widget();
  instance.show_empty_state();
  Object.assign(instance, { has_data: () => true, loading: element, error_state: element,
    chart_wrapper: element, get_source_doctype: async () => null,
    get_chart_args: () => ({ type: 'line' }) });
  await instance.render();
  assert.equal(created.length, 2);
  assert.equal(created[0].destroyed, 1);
  assert.equal(created[1].destroyed, 0);
  assert.equal(instance.empty_chart, undefined);
  assert.equal(instance.dashboard_chart, created[1]);
  instance.destroy_chart();
  assert.ok(created.every(c => c.destroyed === 1));
});

test('an empty response after widget deletion cannot recreate a placeholder', async () => {
  const { instance, element, created } = widget();
  Object.assign(instance, { has_data: () => false, loading: element,
    error_state: element, chart_wrapper: element });
  instance.delete(false);
  await instance.render();
  assert.equal(created.length, 0);
});

test('native component defaults do not retain an individual chart data callback', () => {
  const raw = fs.readFileSync(process.env.BENCH_ROOT +
    '/apps/frappe/node_modules/frappe-charts/src/js/objects/ChartComponents.js', 'utf8');
  const ctx = {};
  vm.runInNewContext(raw.replace(/^import[\s\S]*?;\n/gm, '')
    .replace('export function getComponent', 'function getComponent') +
    '\nglobalThis.factory = getComponent; globalThis.defaults = componentConfigs;', ctx);
  const firstData = () => ({ positions: [1], labels: ['first'] });
  const secondData = () => ({ positions: [2], labels: ['second'] });
  const first = ctx.factory('yAxis', { width: 100 }, firstData);
  const second = ctx.factory('yAxis', { width: 200 }, secondData);
  assert.equal(first.getData, firstData);
  assert.equal(second.getData, secondData);
  assert.equal(first.constants.width, 100);
  assert.equal(second.constants.width, 200);
  assert.equal(Object.hasOwn(ctx.defaults.yAxis, 'getData'), false);
  assert.equal(Object.hasOwn(ctx.defaults.yAxis, 'constants'), false);
});

test('all published chart entrypoints isolate their component defaults too', () => {
  for (const [format, defaultsName, constructorName] of [
    ['esm', 'Ct', 'Tt'], ['umd', 'Ct', 'Tt'], ['cjs', 'Tt', 'Ct'],
  ]) {
    const raw = fs.readFileSync(process.env.BENCH_ROOT +
      `/apps/frappe/node_modules/frappe-charts/dist/frappe-charts.${format}.js`, 'utf8');
    const factory = raw.match(/function Nt\(t,e,n\)\{var i=Object.keys[\s\S]*?new \w+\(a\)\}/)?.[0];
    assert.ok(factory, format);
    const defaults = { yAxis: { layerClass: 'y axis' } };
    const ctx = { [defaultsName]: defaults,
      [constructorName]: function(config) { Object.assign(this, config); } };
    vm.runInNewContext(factory + '; globalThis.factory = Nt;', ctx);
    const callback = () => 1;
    const component = ctx.factory('yAxis', { width: 100 }, callback);
    assert.equal(component.getData, callback);
    assert.equal(Object.hasOwn(defaults.yAxis, 'getData'), false, format);
  }
});
