// Real-time Chrome proof using the production frappe-charts assets and the actual brand.js IIFEs.
// node my_branding/tests/chart_width_browser.mjs <chrome> <production-assets-dir> [output-dir]
// Assets: frappe-charts.umd.js + frappe-charts.min.css. Output defaults to ignored build/.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const [chrome, assets, outputArg] = process.argv.slice(2);
if (!chrome || !assets) throw new Error('Usage: node chart_width_browser.mjs <chrome> <production-assets-dir> [output-dir]');
const output = path.resolve(outputArg || path.join(repo, 'build/chart-width-proof'));
assert.ok(output.startsWith(repo + path.sep), 'All proof artifacts must stay inside this repository');
await mkdir(output, { recursive: true });
const baseline = '636bb1a'; // v218 runtime brand.js, before this working-tree change
const oldBrand = execFileSync('git', ['show', `${baseline}:my_branding/public/js/brand.js`], { cwd: repo, encoding: 'utf8' });
const newBrand = await readFile(path.join(repo, 'my_branding/public/js/compatibility.js'), 'utf8');
function section(source, marker) {
	const heading = source.indexOf(marker);
	assert.ok(heading >= 0, `Missing chart section: ${marker}`);
	const start = source.indexOf('(function () {', heading);
	const end = source.indexOf('\n})();', start);
	assert.ok(start >= 0 && end > start);
	return source.slice(start, end + '\n})();'.length);
}
function chartSource(source) {
	return section(source, '// Shared report palette,') + '\n' + section(source, '// Frappe chart terminal x-axis');
}
const scripts = { native: '', v218: chartSource(oldBrand), edited: newBrand + '\nwindow.NexumCompatibility.install("chartPalette"); window.NexumCompatibility.install("chartSizing");'  };
const library = await readFile(path.join(assets, 'frappe-charts.umd.js'));
const css = await readFile(path.join(assets, 'frappe-charts.min.css'));
const scenarios = ['one-period', 'three-periods', 'twelve-periods', 'stacked', 'axis-mixed', 'resize', 'wide-stacked', 'realtime'];
const html = String.raw`<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="/charts.css">
<style>body{margin:0;font-family:sans-serif}#wrap{width:1100px;padding:18px}#chart{width:100%}</style>
<div id="wrap"><div id="chart"></div></div><pre id="out">pending</pre>
<script src="/charts.js"></script>
<script>
window.proofErrors = [];
window.onerror = function(message) { window.proofErrors.push(String(message)); };
window.onunhandledrejection = function(event) { window.proofErrors.push(String(event.reason)); };
(async function () {
  const params = new URLSearchParams(location.search), mode = params.get('mode'), scenario = params.get('scenario');
  const Chart = window['frappe-charts'].Chart;
  // desk.bundle defines RealtimeChart before app_include_js loads brand.js.
  window.frappe = { Chart, ui: { RealtimeChart: class extends Chart {} } };
  if (mode !== 'native') await new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = '/brand-chart.js?mode=' + mode;
    script.onload = resolve; script.onerror = reject; document.head.appendChild(script);
  });
  const periods = scenario === 'three-periods' ? 3 : scenario === 'twelve-periods' ? 12 : 1;
  const types = scenario === 'axis-mixed' ? ['bar', 'bar', 'line'] : ['bar', 'bar', 'bar'];
  const values = [1250000, 830000, 420000];
  const options = { type: scenario === 'axis-mixed' ? 'axis-mixed' : 'bar', height: 280,
    data: { labels: Array.from({length: periods}, (_, i) => 'Period ' + (i + 1)),
      datasets: types.map((chartType, i) => ({name: ['Income', 'Expense', 'Net Profit'][i], chartType,
        values: Array.from({length: periods}, (_, j) => values[i] * (1 + j / 10))})) },
    barOptions: {stacked: scenario === 'stacked' || scenario === 'wide-stacked'} };
  const wrap = document.getElementById('wrap');
  if (scenario === 'wide-stacked') wrap.style.width = '1600px';
  const start = performance.now();
  const Constructor = scenario === 'realtime' ? frappe.ui.RealtimeChart : frappe.Chart;
  const chart = new Constructor('#chart', options);
  window.proofChart = chart;
  let resized = false, updated = false, resizeDuringAnimation = false;
  if (scenario === 'resize') setTimeout(() => {
    resizeDuringAnimation = !!document.querySelector('#chart animate');
    wrap.style.width = '800px'; resized = true;
  }, 850);
  // Exercise chart.update as well as the entry animation in every case.
  setTimeout(() => {
    chart.update({labels: options.data.labels.slice(), datasets: options.data.datasets.map(d => ({
      name: d.name, chartType: d.chartType, values: d.values.map(v => v * 0.8)}))});
    updated = true;
  }, 1500);
  const samples = [];
  function sample() {
    const elapsed = performance.now() - start;
    const bars = Array.from(document.querySelectorAll('#chart svg rect.bar'));
    // Bounding boxes include the active SMIL clone, not just base SVG attributes.
    const max = Math.max(0, ...bars.map(bar => bar.getBoundingClientRect().width));
    samples.push([elapsed, max]);
    if (elapsed < 2400) return requestAnimationFrame(sample);
    const over = samples.filter(s => s[1] > 56.01); // only floating-point/layout tolerance
    const result = {mode, scenario, frames: samples.length,
      maxWidth: Math.max(...samples.map(s => s[1])), finalWidth: max,
      framesOver56: over.length, wideWindowMs: over.length ? [over[0][0], over[over.length - 1][0]] : null,
      resized, resizeDuringAnimation, updated, errors: window.proofErrors, samples};
    window.proofResult = result;
    document.getElementById('out').textContent = JSON.stringify(result);
  }
  requestAnimationFrame(sample);
})().catch(error => { window.proofResult = {error: String(error), stack: error.stack}; });
</script>`;

const server = createServer((req, res) => {
	const url = new URL(req.url, 'http://localhost');
	const content = url.pathname === '/charts.js' ? library : url.pathname === '/charts.css' ? css :
		url.pathname === '/brand-chart.js' ? scripts[url.searchParams.get('mode')] : html;
	res.setHeader('Content-Type', url.pathname.endsWith('.js') ? 'text/javascript' : url.pathname.endsWith('.css') ? 'text/css' : 'text/html');
	res.end(content);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const address = `http://127.0.0.1:${server.address().port}`;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const profile = path.join(output, `chrome-${Date.now()}`);
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
	'--disable-breakpad', `--user-data-dir=${profile}`, '--window-size=1800,800', '--remote-debugging-port=0', 'about:blank'], { stdio: 'ignore' });
let ws;
const results = [];
try {
	let port;
	for (let i = 0; i < 100 && !port; i++) {
		try { port = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; }
		catch { await sleep(100); }
	}
	assert.ok(port, 'Chrome did not start');
	const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
	ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
	await new Promise((resolve, reject) => { ws.addEventListener('open', resolve); ws.addEventListener('error', reject); });
	let id = 0;
	const pending = new Map();
	ws.addEventListener('message', event => {
		const m = JSON.parse(event.data), p = pending.get(m.id);
		if (!p) return;
		clearTimeout(p.timer); pending.delete(m.id);
		if (m.error) p.reject(new Error(JSON.stringify(m.error))); else p.resolve(m.result);
	});
	const send = (method, params = {}) => new Promise((resolve, reject) => {
		const n = ++id, timer = setTimeout(() => reject(new Error(`CDP timed out: ${method}`)), 10000);
		pending.set(n, { resolve, reject, timer }); ws.send(JSON.stringify({ id: n, method, params }));
	});
	await send('Page.enable');
	for (const scenario of scenarios) for (const mode of Object.keys(scripts)) {
		await send('Page.navigate', { url: `${address}/?mode=${mode}&scenario=${scenario}` });
		let result;
		for (let i = 0; i < 50; i++) {
			await sleep(100);
			const response = await send('Runtime.evaluate', { expression: 'window.proofResult', returnByValue: true });
			result = response.result?.value;
			if (result?.mode === mode && result?.scenario === scenario || result?.error) break;
		}
		assert.ok(result && !result.error, JSON.stringify(result || 'No browser result'));
		assert.ok(result.updated, 'chart.update did not execute');
		if (scenario === 'resize') assert.ok(result.resized && result.resizeDuringAnimation, 'Resize missed the animation');
		results.push(result);
		console.log(`${scenario.padEnd(16)} ${mode.padEnd(7)} max=${result.maxWidth.toFixed(2)}px over56=${result.framesOver56}/${result.frames} errors=${result.errors.length}`);
	}
} finally {
	ws?.close();
	proc.kill();
	server.close();
}
const hash = data => createHash('sha256').update(data).digest('hex');
await writeFile(path.join(output, 'results.json'), JSON.stringify({baseline, brandSha256: hash(newBrand),
	librarySha256: hash(library), scriptsSha256: Object.fromEntries(Object.entries(scripts).map(([k, v]) => [k, hash(v)])), results}, null, 2));
const failures = results.filter(r => r.mode === 'edited' && r.framesOver56 > 0);
assert.equal(failures.length, 0, `Edited charts exceeded 56px: ${failures.map(r => r.scenario).join(', ')}`);
for (const result of results) {
	assert.ok(result.finalWidth > 0, 'A chart disappeared');
	// rc27 can remove an already-replaced SVG when a ResizeObserver redraw lands
	// inside runSMILAnimation. Preserve/report that baseline defect, never hide new errors.
	const native = results.find(r => r.mode === 'native' && r.scenario === result.scenario);
	if (result.scenario !== 'resize') assert.deepEqual(result.errors, [], JSON.stringify(result));
	else assert.deepEqual(result.errors, native.errors, 'Resize introduced a new error');
}
