const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const brand = fs.readFileSync(path.join(__dirname, '../public/js/brand.js'), 'utf8');
const start = brand.indexOf('(function () {', brand.indexOf('// Frappe chart terminal x-axis'));
const source = brand.slice(start, brand.indexOf('\n})();', start) + '\n})();'.length);

function setup() {
	class AxisChart {
		constructor(parent, options) {
			this.width = options.width || 1020;
			this.data = options.data;
			this.barOptions = options.barOptions || {};
			this.state = {};
			this.calls = [];
			this.calcXPositions('initial');
		}
		calcXPositions(...args) {
			this.calls.push(args);
			this.state.unitWidth = this.width / this.data.labels.length;
			return 'native result';
		}
	}
	const nativeCalc = AxisChart.prototype.calcXPositions;
	function Chart(parent, options) { return new AxisChart(parent, options); }
	class RealtimeChart extends Chart {
		constructor(parent, event, limit, options) {
			super(parent, options);
			this.event = event;
			this.limit = limit;
		}
	}
	const frappe = { Chart, ui: { RealtimeChart } };
	const context = { frappe, setInterval: () => 0, clearInterval: () => {} };
	context.window = context;
	vm.runInNewContext(source, context, { filename: 'brand.js#chart' });
	const make = (periods = 1, types = ['bar', 'bar', 'bar'], barOptions = {}) => new frappe.Chart(null, {
		data: { labels: Array.from({ length: periods }, (_, i) => String(i)),
			datasets: types.map(chartType => ({ chartType, values: Array(periods).fill(1) })) }, barOptions,
	});
	return { make, context, AxisChart, nativeCalc, frappe };
}

// The public frappe-charts sizing formula, checked against the production rc27 source.
function width(chart) {
	const count = chart.barOptions.stacked ? 1 : chart.data.datasets.filter(d => d.chartType === 'bar').length;
	return chart.state.unitWidth * (1 - (chart.barOptions.spaceRatio || 0.5)) / Math.max(1, count);
}
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`);

test('one period and three datasets are 56px before the animated update renders', () => {
	const s = setup(), chart = s.make();
	assert.equal(chart.calcXPositions('update'), 'native result');
	close(width(chart), 56);
	assert.deepEqual(chart.calls, [['initial'], ['update']]);
	close(width(s.make()), 56); // subsequent charts also cap their zero-data draw
});

test('twelve periods keep the native ratio and native narrow bars', () => {
	const chart = setup().make(12);
	chart.calcXPositions();
	assert.equal(chart.barOptions.spaceRatio, 0.5);
	close(width(chart), 1020 / 12 / 2 / 3);
});

test('stacked datasets occupy one 56px bar slot', () => {
	const chart = setup().make(1, ['bar', 'bar', 'bar'], { stacked: 1 });
	chart.calcXPositions();
	close(width(chart), 56);
});

test('wide stacked slots stay 56px even when the required ratio exceeds .95', () => {
	const chart = setup().make(1, ['bar', 'bar', 'bar'], { stacked: 1 });
	chart.width = 1520;
	chart.calcXPositions();
	assert.ok(chart.barOptions.spaceRatio > 0.95);
	close(width(chart), 56);
});

test('an author ratio above .95 is preserved rather than widening their bars', () => {
	const chart = setup().make(1, ['bar', 'bar', 'bar'], { spaceRatio: 0.98, stacked: 1 });
	chart.calcXPositions();
	assert.equal(chart.barOptions.spaceRatio, 0.98);
	close(width(chart), 20.4);
});

test('axis-mixed counts only bar datasets and leaves the data unchanged', () => {
	const chart = setup().make(1, ['bar', 'bar', 'line']);
	const before = JSON.stringify(chart.data);
	chart.calcXPositions();
	close(width(chart), 56);
	assert.equal(JSON.stringify(chart.data), before);
});

test('the original author ratio remains a floor across recalculations', () => {
	const chart = setup().make(1, ['bar', 'bar', 'bar'], { spaceRatio: 0.9 });
	chart.calcXPositions();
	assert.equal(chart.barOptions.spaceRatio, 0.9);
	close(width(chart), 34);
	chart.width = 3000;
	chart.calcXPositions();
	close(width(chart), 56);
	chart.width = 600;
	chart.calcXPositions();
	assert.equal(chart.barOptions.spaceRatio, 0.9);
});

test('resize recalculates from the original ratio rather than keeping a previous cap', () => {
	const chart = setup().make();
	chart.calcXPositions();
	close(width(chart), 56);
	chart.width = 300;
	chart.calcXPositions();
	assert.equal(chart.barOptions.spaceRatio, 0.5);
	close(width(chart), 50);
	chart.width = 2040;
	chart.calcXPositions();
	close(width(chart), 56);
	chart.barOptions = { spaceRatio: 0.8 };
	chart.width = 300;
	chart.calcXPositions();
	assert.equal(chart.barOptions.spaceRatio, 0.8, 'a replacement options object has its own floor');
});

test('a shared options object retains its original author ratio', () => {
	const s = setup(), options = { spaceRatio: 0.6 };
	const first = s.make(1, ['bar', 'bar', 'bar'], options);
	first.calcXPositions();
	close(width(first), 56);
	const second = s.make(12, ['bar', 'bar', 'bar'], options);
	assert.equal(second.barOptions.spaceRatio, 0.6);
});

test('the prototype is patched once across instances and repeated script loads', () => {
	const s = setup();
	s.make();
	const patched = s.AxisChart.prototype.calcXPositions;
	assert.notEqual(patched, s.nativeCalc);
	s.make();
	vm.runInNewContext(source, s.context);
	const chart = s.make();
	assert.equal(s.AxisChart.prototype.calcXPositions, patched);
	chart.calcXPositions('resize');
	assert.deepEqual(chart.calls, [['initial'], ['resize']]);
});

test('invalid geometry or unavailable options do not break native calculation', () => {
	const chart = setup().make();
	chart.width = Infinity;
	assert.equal(chart.calcXPositions(), 'native result');
	assert.equal(chart.barOptions.spaceRatio, undefined);
	chart.width = 0;
	assert.doesNotThrow(() => chart.calcXPositions());
	chart.barOptions = null;
	assert.doesNotThrow(() => chart.calcXPositions());
});

test('an early-captured RealtimeChart is covered even when it is the first chart', () => {
	const { frappe } = setup();
	const chart = new frappe.ui.RealtimeChart(null, 'tick', 8, {
		data: { labels: ['2026'], datasets: [1, 2, 3].map(v => ({ chartType: 'bar', values: [v] })) },
	});
	chart.calcXPositions();
	close(width(chart), 56);
	assert.equal(chart.event, 'tick');
	assert.equal(chart.limit, 8);
});
