// v205 browser fixes (sweep group D1): behaviour tests for brand.js, idle_lock.js,
// idle_activity.js, login.js, spa-brand.js and spa-brand.css.
//
//   node --test my_branding/tests/batch205_client.test.cjs
//
// No dependencies: each asset runs as shipped in a vm sandbox on top of the small fake
// DOM below (tree, selectors, TreeWalker, MutationObserver), with fake timers, fetch,
// Web Locks and BroadcastChannel. Every finding has at least one test that fails on the
// code before the fix (copy the pre-fix assets next to a copy of this file to check).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PUBLIC = path.join(__dirname, '..', 'public');
const read = (rel) => fs.readFileSync(path.join(PUBLIC, rel), 'utf8');
const flush = async (turns = 3) => {
	for (let i = 0; i < turns; i++) await new Promise((resolve) => setImmediate(resolve));
};

// One brand.js section: from the comment line holding `start` to the one holding `end`.
function section(src, start, end) {
	const a = src.indexOf(start);
	const b = src.indexOf(end, a);
	assert.ok(a !== -1 && b !== -1, 'section markers moved: ' + start);
	return src.slice(src.lastIndexOf('\n', a) + 1, src.lastIndexOf('\n', b) + 1);
}

// --- selectors: lists, descendant/child combinators, tag #id .class [attr op v] :not() ---
function splitTop(sel) {
	const out = [];
	let depth = 0, quote = null, cur = '';
	for (const ch of sel) {
		if (quote) { cur += ch; if (ch === quote) quote = null; continue; }
		if (ch === '"' || ch === "'") quote = ch;
		if (ch === '[' || ch === '(') depth++;
		if (ch === ']' || ch === ')') depth--;
		if (ch === ',' && !depth) { out.push(cur.trim()); cur = ''; continue; }
		cur += ch;
	}
	if (cur.trim()) out.push(cur.trim());
	return out;
}
function closeAt(str, start, open, close) {
	let depth = 0, quote = null;
	for (let i = start; i < str.length; i++) {
		const ch = str[i];
		if (quote) { if (ch === quote) quote = null; continue; }
		if (ch === '"' || ch === "'") { quote = ch; continue; }
		if (ch === open) depth++;
		else if (ch === close && --depth === 0) return i;
	}
	throw new Error('unbalanced selector: ' + str);
}
function parseCompound(str) {
	const c = { tag: null, id: null, classes: [], attrs: [], nots: [] };
	let i = 0;
	const t = /^(\*|[a-zA-Z][\w-]*)/.exec(str);
	if (t) { if (t[1] !== '*') c.tag = t[1].toLowerCase(); i = t[1].length; }
	while (i < str.length) {
		if (str[i] === '#' || str[i] === '.') {
			const name = /^[\w-]+/.exec(str.slice(i + 1))[0];
			if (str[i] === '#') c.id = name; else c.classes.push(name);
			i += 1 + name.length;
		} else if (str[i] === '[') {
			const end = closeAt(str, i, '[', ']');
			const m = /^\s*([\w-]+)\s*(?:([$^~*]?=)\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]*)))?\s*$/.exec(str.slice(i + 1, end));
			c.attrs.push({ name: m[1], op: m[2] || null, val: m[3] ?? m[4] ?? m[5] ?? null });
			i = end + 1;
		} else if (str.startsWith(':not(', i)) {
			const end = closeAt(str, i + 4, '(', ')');
			c.nots.push(parseCompound(str.slice(i + 5, end)));
			i = end + 1;
		} else throw new Error('unsupported selector: ' + str);
	}
	return c;
}
function parseComplex(sel) {
	const parts = [];
	let depth = 0, quote = null, cur = '';
	for (let i = 0; i < sel.length; i++) {
		const ch = sel[i];
		if (quote) { cur += ch; if (ch === quote) quote = null; continue; }
		if (ch === '"' || ch === "'") quote = ch;
		if (ch === '[' || ch === '(') depth++;
		if (ch === ']' || ch === ')') depth--;
		if (!depth && (ch === ' ' || ch === '>')) {
			let comb = ' ', j = i;
			for (; j < sel.length && (sel[j] === ' ' || sel[j] === '>'); j++) if (sel[j] === '>') comb = '>';
			if (cur) { parts.push(parseCompound(cur)); cur = ''; }
			parts.push(comb);
			i = j - 1;
			continue;
		}
		cur += ch;
	}
	if (cur) parts.push(parseCompound(cur));
	return parts;
}
const selectorCache = new Map();
function compile(sel) {
	if (!selectorCache.has(sel)) selectorCache.set(sel, splitTop(sel).map(parseComplex));
	return selectorCache.get(sel);
}
function matchCompound(el, c) {
	if (!el || el.nodeType !== 1) return false;
	if (c.tag && el.tagName.toLowerCase() !== c.tag) return false;
	if (c.id && el.getAttribute('id') !== c.id) return false;
	for (const k of c.classes) if (!el.classList.contains(k)) return false;
	for (const a of c.attrs) {
		const v = el.getAttribute(a.name);
		if (v === null) return false;
		if ((a.op === '=' && v !== a.val) || (a.op === '$=' && !v.endsWith(a.val)) ||
			(a.op === '^=' && !v.startsWith(a.val)) || (a.op === '*=' && !v.includes(a.val)) ||
			(a.op === '~=' && !v.split(/\s+/).includes(a.val))) return false;
	}
	return !c.nots.some((n) => matchCompound(el, n));
}
function matchFrom(el, parts, i) {
	if (!matchCompound(el, parts[i])) return false;
	if (i === 0) return true;
	if (parts[i - 1] === '>') return !!el.parentElement && matchFrom(el.parentElement, parts, i - 2);
	for (let a = el.parentElement; a; a = a.parentElement) if (matchFrom(a, parts, i - 2)) return true;
	return false;
}
const matches = (el, sel) => compile(sel).some((parts) => matchFrom(el, parts, parts.length - 1));

// --- a small DOM ------------------------------------------------------------------
function makeDom({ path: pathname = '/app' } = {}) {
	const observers = new Set();
	const doc = { nodeType: 9, title: '', cookie: '', hidden: false, readyState: 'complete', activeElement: null };

	class Node {
		constructor(nodeType) { this.nodeType = nodeType; this.parentNode = null; this.childNodes = []; this.ownerDocument = doc; this._on = {}; }
		get parentElement() { return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }
		get firstChild() { return this.childNodes[0] || null; }
		get children() { return this.childNodes.filter((n) => n.nodeType === 1); }
		appendChild(n) { return this.insertBefore(n, null); }
		insertBefore(n, ref) {
			if (n.parentNode) n.parentNode.removeChild(n);
			const i = ref ? this.childNodes.indexOf(ref) : -1;
			if (i < 0) this.childNodes.push(n); else this.childNodes.splice(i, 0, n);
			n.parentNode = this;
			mutated(this, [n], []);
			return n;
		}
		removeChild(n) {
			const i = this.childNodes.indexOf(n);
			if (i >= 0) this.childNodes.splice(i, 1);
			n.parentNode = null;
			mutated(this, [], [n]);
			return n;
		}
		contains(n) { for (; n; n = n.parentNode) if (n === this) return true; return false; }
		addEventListener(type, fn) { (this._on[type] = this._on[type] || []).push(fn); }
		removeEventListener(type, fn) { this._on[type] = (this._on[type] || []).filter((f) => f !== fn); }
		dispatchEvent(ev) {
			ev = typeof ev === 'string' ? { type: ev } : ev;
			ev.target = ev.target || this;
			if (!('isTrusted' in ev)) ev.isTrusted = true;
			for (const fn of (this._on[ev.type] || []).slice()) fn.call(this, ev);
			return true;
		}
		get textContent() { return this.childNodes.map((n) => n.textContent).join(''); }
		set textContent(v) {
			const old = this.childNodes.splice(0);
			old.forEach((n) => { n.parentNode = null; });
			const added = v === '' || v == null ? [] : [new Text(String(v))];
			added.forEach((n) => { n.parentNode = this; this.childNodes.push(n); });
			mutated(this, added, old);
		}
	}
	class Text extends Node {
		constructor(v) { super(3); this.nodeName = '#text'; this.nodeValue = v; }
		get textContent() { return this.nodeValue; }
		set textContent(v) { this.nodeValue = String(v); }
	}
	class Element extends Node {
		constructor(tag) {
			super(1);
			this.tagName = tag.toUpperCase();
			this.nodeName = this.tagName;
			this.attributes = new Map();
			this.style = {};
			this.rect = null;
			this.rectReads = 0;
			const el = this;
			this.classList = {
				contains: (c) => el._classes().includes(c),
				add: (...cs) => el._setClasses([...new Set(el._classes().concat(cs))]),
				remove: (...cs) => el._setClasses(el._classes().filter((c) => !cs.includes(c))),
				toggle: (c, force) => {
					const on = force === undefined ? !el.classList.contains(c) : !!force;
					if (on) el.classList.add(c); else el.classList.remove(c);
					return on;
				},
			};
		}
		_classes() { return (this.getAttribute('class') || '').split(/\s+/).filter(Boolean); }
		_setClasses(list) { this.setAttribute('class', list.join(' ')); }
		getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; }
		setAttribute(k, v) { this.attributes.set(k, String(v)); }
		hasAttribute(k) { return this.attributes.has(k); }
		removeAttribute(k) { this.attributes.delete(k); }
		matches(sel) { return matches(this, sel); }
		closest(sel) { for (let e = this; e && e.nodeType === 1; e = e.parentNode) if (e.matches(sel)) return e; return null; }
		querySelectorAll(sel) {
			const out = [];
			const walk = (n) => n.childNodes.forEach((c) => { if (c.nodeType === 1) { if (c.matches(sel)) out.push(c); walk(c); } });
			walk(this);
			return out;
		}
		// Markup assigned through innerHTML is not parsed: a query for something it
		// would contain gets a stand-in element (memoized), enough for the lock card.
		querySelector(sel) {
			const found = this.querySelectorAll(sel)[0];
			if (found || this._html == null) return found || null;
			const c = compile(sel)[0].slice(-1)[0];
			const stub = new Element(c.tag || 'div');
			if (c.id) stub.setAttribute('id', c.id);
			c.attrs.forEach((a) => stub.setAttribute(a.name, a.val ?? ''));
			this.appendChild(stub);
			return stub;
		}
		set innerHTML(v) { this.textContent = ''; this._html = String(v); }
		get innerHTML() { return this._html || ''; }
		focus() { doc.activeElement = this; }
		get offsetParent() {
			for (let e = this; e && e.nodeType === 1; e = e.parentNode) if (e.style.display === 'none') return null;
			return this.parentElement;
		}
		getBoundingClientRect() {
			this.rectReads++;
			const zero = { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };
			return this.offsetParent === null ? zero : this.rect || zero;
		}
	}
	for (const [prop, attr] of [['id', 'id'], ['className', 'class'], ['src', 'src'], ['href', 'href'],
		['type', 'type'], ['rel', 'rel'], ['alt', 'alt'], ['title', 'title']]) {
		Object.defineProperty(Element.prototype, prop, {
			get() { return this.getAttribute(attr) || ''; },
			set(v) { this.setAttribute(attr, v); },
		});
	}

	function mutated(target, addedNodes, removedNodes) {
		for (const o of observers) o._notify({ type: 'childList', target, addedNodes, removedNodes });
	}
	class MutationObserver {
		constructor(cb) { this.cb = cb; this.targets = []; this.queue = []; this.pending = false; }
		observe(target, opts) { this.targets.push({ target, opts: opts || {} }); observers.add(this); }
		disconnect() { this.targets = []; observers.delete(this); }
		takeRecords() { return this.queue.splice(0); }
		_notify(rec) {
			const hit = this.targets.some(({ target, opts }) => opts.childList &&
				(rec.target === target || (opts.subtree && target.contains(rec.target))));
			if (!hit) return;
			this.queue.push(rec);
			if (this.pending) return;
			this.pending = true;
			queueMicrotask(() => {
				this.pending = false;
				const recs = this.takeRecords();
				if (recs.length) this.cb(recs, this);
			});
		}
	}

	const html = new Element('html');
	const head = new Element('head');
	const body = new Element('body');
	html.appendChild(head);
	html.appendChild(body);
	Object.assign(doc, {
		documentElement: html, head, body, _on: {},
		createElement: (tag) => new Element(tag),
		createTextNode: (v) => new Text(String(v)),
		getElementById: (id) => html.querySelectorAll('#' + id)[0] || null,
		querySelectorAll: (sel) => (html.matches(sel) ? [html] : []).concat(html.querySelectorAll(sel)),
		querySelector: (sel) => doc.querySelectorAll(sel)[0] || null,
		addEventListener: Node.prototype.addEventListener,
		removeEventListener: Node.prototype.removeEventListener,
		dispatchEvent: Node.prototype.dispatchEvent,
		createTreeWalker(root, whatToShow, filter) {
			const texts = [];
			(function walk(n) { n.childNodes.forEach((c) => (c.nodeType === 3 ? texts.push(c) : c.nodeType === 1 && walk(c))); })(root);
			let i = 0;
			return { nextNode() {
				while (i < texts.length) {
					const n = texts[i++];
					if (!filter || filter.acceptNode(n) === 1) return n;
				}
				return null;
			} };
		},
	});
	// h('div', {class: 'x'}, child, 'text', ...)
	function h(tag, attrs, ...kids) {
		const el = new Element(tag);
		for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
		kids.forEach((k) => el.appendChild(typeof k === 'string' ? new Text(k) : k));
		return el;
	}
	return { doc, h, MutationObserver, location: { pathname, href: pathname } };
}

// --- fake timers, storage, fetch, Web Locks, BroadcastChannel ------------------------
function makeClock(start = 1000000) {
	let now = start, seq = 0;
	const timers = new Map();
	const add = (fn, ms, every) => { timers.set(++seq, { fn, at: now + (ms || 0), every }); return seq; };
	return {
		now: () => now,
		setTimeout: (fn, ms) => add(fn, ms, 0),
		setInterval: (fn, ms) => add(fn, ms, ms),
		clearTimeout: (id) => timers.delete(id),
		clearInterval: (id) => timers.delete(id),
		async advance(ms) {
			const end = now + ms;
			for (;;) {
				let next = null;
				for (const [id, t] of timers) if (t.at <= end && (!next || t.at < next[1].at)) next = [id, t];
				if (!next) break;
				now = next[1].at;
				if (next[1].every) next[1].at += next[1].every; else timers.delete(next[0]);
				next[1].fn();
				await flush(1);
			}
			now = end;
			await flush();
		},
	};
}
function makeStorage() {
	const m = new Map();
	return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
}
function makeFetch(clock) {
	const calls = [];
	function fetch(url, opts = {}) {
		let resolve, reject;
		const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
		const call = {
			url: String(url), opts, settled: false, at: clock ? clock.now() : 0,
			respond(status, body) {
				if (call.settled) return;
				call.settled = true;
				resolve({ ok: status >= 200 && status < 300, status,
					json: () => (body === undefined ? Promise.reject(new SyntaxError('empty')) : Promise.resolve(body)) });
			},
			fail(err) {
				if (call.settled) return;
				call.settled = true;
				reject(err || new TypeError('Failed to fetch'));
			},
		};
		if (opts.signal) {
			const abort = () => call.fail(new DOMException('The operation was aborted.', 'AbortError'));
			if (opts.signal.aborted) abort(); else opts.signal.addEventListener('abort', abort);
		}
		calls.push(call);
		return promise;
	}
	fetch.calls = calls;
	fetch.to = (part) => calls.filter((c) => c.url.includes(part));
	return fetch;
}
function makeLocks() {
	let tail = Promise.resolve();
	return {
		request(name, cb) {
			const run = tail.then(() => cb());
			tail = run.then(() => {}, () => {});
			return run;
		},
	};
}
function makeChannels() {
	const all = new Set();
	return class BroadcastChannel {
		constructor(name) { this.name = name; this.onmessage = null; all.add(this); }
		postMessage(data) {
			for (const c of all) if (c !== this && c.name === this.name) queueMicrotask(() => c.onmessage && c.onmessage({ data }));
		}
		close() { all.delete(this); }
	};
}
function windowEvents(ctx) {
	const on = {};
	ctx.addEventListener = (type, fn) => { (on[type] = on[type] || []).push(fn); };
	ctx.removeEventListener = (type, fn) => { on[type] = (on[type] || []).filter((f) => f !== fn); };
	ctx.dispatch = (type, ev = {}) => (on[type] || []).slice().forEach((fn) => fn(Object.assign({ type }, ev)));
	ctx.listeners = on;
}

// =====================================================================================
// idx 78 — brand.js: simple-mode "More filters" looks again after route filters land
// =====================================================================================
function loadPresets() {
	const { doc } = makeDom();
	const src = section(read('js/brand.js'), 'Report presets for simple mode', 'Bare-root landing');
	class QueryReport {
		constructor(name, dfs) {
			const form = doc.createElement('div');
			doc.body.appendChild(form);
			this.report_name = name;
			this.report_settings = { filters: dfs };
			this.page = { page_form: $(form) };
		}
		// upstream query_report.js setup_filters: builds the bar from defaults only
		setup_filters() {
			this.page.page_form.els[0].textContent = '';
			this.filters = this.report_settings.filters.map((df) => {
				const wrapper = doc.createElement('div');
				this.page.page_form.els[0].appendChild(wrapper);
				return { df, wrapper, value: df.default === undefined ? '' : df.default,
					get_value() { return this.value; },
					set_value(v) { this.value = v; return Promise.resolve(); } };
			});
		}
		// upstream set_route_filters: sets each value asynchronously, after setup_filters
		set_route_filters(route) {
			const names = Object.keys(route || {});
			return this.filters.filter((f) => names.includes(f.df.fieldname))
				.reduce((p, f) => p.then(() => f.set_value(route[f.df.fieldname])), Promise.resolve());
		}
	}
	function wrap(els) {
		return {
			els,
			text(v) { if (v === undefined) return els.map((e) => e.textContent).join(''); els.forEach((e) => { e.textContent = v; }); return this; },
			on(type, fn) { els.forEach((e) => e.addEventListener(type, fn)); return this; },
			toggleClass(c, on) { els.forEach((e) => e.classList.toggle(c, on)); return this; },
			find(sel) { return wrap(els.flatMap((e) => e.querySelectorAll(sel))); },
			remove() { els.forEach((e) => e.parentNode && e.parentNode.removeChild(e)); return this; },
			append(x) { els[0].appendChild(x.els ? x.els[0] : x); return this; },
		};
	}
	function $(x) {
		if (typeof x === 'string') {
			const b = doc.createElement('button');
			b.className = /class="([^"]*)"/.exec(x)[1];
			return wrap([b]);
		}
		return wrap(x && x.els ? x.els : [x]);
	}
	const ctx = {
		frappe: { boot: { nx_simple_mode: 1 }, views: { QueryReport } },
		cint: (v) => parseInt(v, 10) || 0,
		__: (t, args) => (args ? t.replace(/\{(\d+)\}/g, (m, i) => args[i]) : t),
		$, document: doc, setInterval: () => 0, clearInterval: () => {},
	};
	ctx.window = ctx;
	vm.runInNewContext(src, ctx, { filename: 'brand.js#presets' });
	return { QueryReport, doc };
}
const GL_FILTERS = () => [
	{ fieldname: 'company', default: 'NEDS' }, { fieldname: 'from_date' }, { fieldname: 'account' },
	{ fieldname: 'finance_book' }, { fieldname: 'cost_center' }, { fieldname: 'project' },
	{ fieldname: 'include_default_book_entries', default: 1 },
];
const hiddenNames = (report) => report.filters.filter((f) => f.wrapper.classList.contains('nx-adv-hidden')).map((f) => f.df.fieldname);
const moreButton = (report) => report.page.page_form.els[0].querySelector('.nx-more-filters');

test('idx 78: a drill-down that sets a hidden filter opens the More filters row', async () => {
	const { QueryReport } = loadPresets();
	const gl = new QueryReport('General Ledger', GL_FILTERS());
	gl.setup_filters(); // refresh_report: setup_filters first...
	assert.deepEqual(hiddenNames(gl), ['finance_book', 'cost_center', 'project', 'include_default_book_entries']);
	assert.equal(moreButton(gl).textContent, 'More filters (4)');
	// ...then the P&L row click's route_options (financial_statements.js open_general_ledger)
	await gl.set_route_filters({ account: 'Sales - N', cost_center: ['Main - N'], project: [] });
	await flush();
	assert.deepEqual(hiddenNames(gl), [], 'the applied Cost Center must be visible');
	assert.equal(moreButton(gl).textContent, 'Fewer filters');
});

test('idx 78: route values equal to the defaults keep the row collapsed; collapsing shows the active count', async () => {
	const { QueryReport } = loadPresets();
	const plain = new QueryReport('General Ledger', GL_FILTERS());
	plain.setup_filters();
	await plain.set_route_filters({ account: 'Sales - N', cost_center: '', project: '' }); // ERPNext sends "" for unset
	await flush();
	assert.equal(hiddenNames(plain).length, 4);
	assert.equal(moreButton(plain).textContent, 'More filters (4)');

	// eam Financial Overview links pass include_default_book_entries=0 (default is 1)
	const eam = new QueryReport('Trial Balance', GL_FILTERS());
	eam.setup_filters();
	await eam.set_route_filters({ include_default_book_entries: 0, finance_book: 'Tax' });
	await flush();
	assert.deepEqual(hiddenNames(eam), []);
	moreButton(eam).dispatchEvent({ type: 'click' }); // the user collapses it again
	assert.equal(hiddenNames(eam).length, 4);
	assert.equal(moreButton(eam).textContent, 'More filters (4) · 2 active');
});

// =====================================================================================
// idle_lock.js harness (idx 79, idx 149)
// =====================================================================================
function loadIdleLock({ user = 'a@example.com', token = 'tok-A1' } = {}) {
	const { doc, MutationObserver } = makeDom({ path: '/app/purchase-invoice/new-1' });
	const clock = makeClock();
	const fetch = makeFetch(clock);
	const BroadcastChannel = makeChannels();
	let appReady = null;
	const frappe = {
		Application: function () {},
		session: { user, user_fullname: 'User A', user_email: user },
		boot: { nexum_idle_lock: { enabled: true, idle_minutes: 3 } },
		utils: { escape_html: (s) => s },
		csrf_token: token,
	};
	frappe.Application.prototype.handle_session_expired = function () { ctx.nativeExpired = true; };
	const ctx = {
		frappe, document: doc, location: { href: '/app/purchase-invoice/new-1' },
		localStorage: makeStorage(), navigator: { onLine: true, locks: makeLocks() },
		fetch, BroadcastChannel, MutationObserver, AbortController, URLSearchParams, console,
		Date: { now: clock.now },
		setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
		setInterval: clock.setInterval, clearInterval: clock.clearInterval,
		__: (t) => t,
		DOMParser: class { parseFromString(s) { return { body: { textContent: String(s).replace(/<[^>]*>/g, '') } }; } },
		$: (target) => ({ on(evt, fn) { if (target === doc && evt === 'app_ready') appReady = fn; } }),
	};
	ctx.window = ctx;
	windowEvents(ctx);
	vm.runInNewContext(read('js/idle_lock.js'), ctx, { filename: 'idle_lock.js' });
	assert.equal(typeof appReady, 'function');
	appReady();
	const peer = new BroadcastChannel('nexum-idle'); // another tab on this browser
	const lockEl = () => doc.getElementById('nx-idle-lock');
	const submit = async (password) => {
		lockEl().querySelector('#nx-idle-password').value = password;
		lockEl().querySelector('form').dispatchEvent({ type: 'submit', preventDefault() {} });
		await flush();
	};
	return { ctx, doc, clock, fetch, peer, lockEl, submit, frappe };
}

// =====================================================================================
// idx 79 — a remote unlock by another user keeps this tab locked (and its draft)
// =====================================================================================
test('idx 79: another user unlocking their own tab leaves this locked tab in place', async () => {
	const t = loadIdleLock();
	t.peer.postMessage({ type: 'lock' });
	await flush();
	assert.ok(t.lockEl(), 'locked in place');

	t.peer.postMessage({ type: 'unlock' }); // user B unlocked a tab on the shared PC
	await flush();
	const probe = t.fetch.to('idle_lock.session_token');
	assert.equal(probe.length, 1);
	probe[0].respond(200, { message: { user: 'b@example.com', csrf_token: 'tok-B' } });
	await flush();
	assert.equal(t.ctx.location.href, '/app/purchase-invoice/new-1', 'must not navigate away (draft would be lost)');
	assert.ok(t.lockEl(), 'still locked');
	assert.equal(t.frappe.csrf_token, 'tok-A1', "B's token is never taken");

	// A comes back and unlocks with their own password: the page (and draft) is kept
	await t.submit('secret-A');
	t.fetch.to('/api/method/login')[0].respond(200, { message: 'Logged In', home_page: '/app' });
	await flush();
	t.fetch.to('idle_lock.session_token')[1].respond(200, { message: { user: 'a@example.com', csrf_token: 'tok-A2' } });
	await flush();
	assert.equal(t.lockEl(), null, 'unlocked');
	assert.equal(t.frappe.csrf_token, 'tok-A2');
	assert.equal(t.ctx.location.href, '/app/purchase-invoice/new-1');
});

test("idx 79: this tab's own unlock landing in another user's session still goes to /login", async () => {
	const t = loadIdleLock();
	t.peer.postMessage({ type: 'lock' });
	await flush();
	await t.submit('secret-A');
	t.fetch.to('/api/method/login')[0].respond(200, { message: 'Logged In', home_page: '/app' });
	await flush();
	t.fetch.to('idle_lock.session_token')[0].respond(200, { message: { user: 'b@example.com', csrf_token: 'tok-B' } });
	await flush();
	assert.equal(t.ctx.location.href, '/login');
	assert.equal(t.frappe.csrf_token, 'tok-A1');
});

// =====================================================================================
// idx 149 — a stalled logout or login can no longer hold the lock / Unlock forever
// =====================================================================================
test('idx 149: a stalled idle logout is abandoned after 10 s, then the unlock login goes out', async () => {
	const t = loadIdleLock();
	await t.clock.advance(3 * 60000 + 1000);
	assert.ok(t.doc.getElementById('nx-idle-warning'), 'warning after 3 idle minutes');
	await t.clock.advance(61000);
	assert.ok(t.lockEl(), 'locked when the warning ran out');
	const logout = t.fetch.to('/api/method/logout');
	assert.equal(logout.length, 1, 'one logout, left hanging (dead connection after wake)');

	await t.submit('secret-A');
	assert.equal(t.lockEl().querySelector('#nx-idle-unlock').disabled, true);
	await t.clock.advance(logout[0].at + 9500 - t.clock.now());
	assert.equal(t.fetch.to('/api/method/login').length, 0, 'login waits for the logout (Web Lock)');
	await t.clock.advance(1000);
	const login = t.fetch.to('/api/method/login');
	assert.equal(login.length, 1, 'the shared lock was released and the login sent');
	assert.equal(new URLSearchParams(login[0].opts.body).get('usr'), 'a@example.com');
	assert.equal(logout[0].opts.signal && logout[0].opts.signal.aborted, true, 'logout abandoned');

	login[0].respond(200, { message: 'Logged In', home_page: '/app' });
	await flush();
	t.fetch.to('idle_lock.session_token')[0].respond(200, { message: { user: 'a@example.com', csrf_token: 'tok-A2' } });
	await flush();
	assert.equal(t.lockEl(), null, 'unlocked, page kept');
});

test('idx 149: a stalled unlock login is abandoned after 15 s with a message and Unlock enabled', async () => {
	const t = loadIdleLock();
	t.peer.postMessage({ type: 'lock' });
	await flush();
	await t.submit('secret-A');
	const login = t.fetch.to('/api/method/login');
	assert.equal(login.length, 1);
	await t.clock.advance(login[0].at + 14500 - t.clock.now());
	assert.equal(t.lockEl().querySelector('#nx-idle-unlock').disabled, true, 'still waiting');
	await t.clock.advance(1000);
	assert.equal(t.lockEl().querySelector('#nx-idle-error').textContent, 'Could not reach the server. Try again.');
	assert.equal(t.lockEl().querySelector('#nx-idle-unlock').disabled, false, 'the user can retry without reloading');
	assert.equal(login[0].opts.signal && login[0].opts.signal.aborted, true);
});

test('idx 149: a quick logout and login clear their deadlines (nothing aborts later)', async () => {
	const t = loadIdleLock();
	await t.clock.advance(4 * 60000 + 2000);
	const logout = t.fetch.to('/api/method/logout')[0];
	logout.respond(200, { message: 'Logged Out' });
	await flush();
	await t.submit('secret-A');
	const login = t.fetch.to('/api/method/login')[0];
	login.respond(200, { message: 'Logged In', home_page: '/app' });
	await flush();
	await t.clock.advance(30000);
	assert.notEqual(logout.opts.signal && logout.opts.signal.aborted, true);
	assert.notEqual(login.opts.signal && login.opts.signal.aborted, true);
});

// =====================================================================================
// idx 148 — idle_activity.js takes the new CSRF token after an unlock elsewhere
// =====================================================================================
function loadActivity({ cookieUser = 'a%40example.com' } = {}) {
	const { doc } = makeDom({ path: '/crm/leads' });
	doc.cookie = 'sid=abc; system_user=yes; full_name=User%20A; user_id=' + cookieUser + '; user_image=';
	const clock = makeClock();
	const fetch = makeFetch();
	const ctx = {
		document: doc, fetch, localStorage: makeStorage(), Date: { now: clock.now },
		setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
		__NEXUM_IDLE__: { csrf: 'tok-old' }, csrf_token: 'tok-old', // frappe-ui reads window.csrf_token
	};
	ctx.window = ctx;
	windowEvents(ctx);
	vm.runInNewContext(read('js/idle_activity.js'), ctx, { filename: 'idle_activity.js' });
	const beats = () => fetch.to('idle_lock.heartbeat');
	return { ctx, doc, fetch, beats, clock };
}

test('idx 148: a heartbeat refused for a stale token fetches the new one (same user) and retries', async () => {
	const t = loadActivity();
	t.doc.dispatchEvent({ type: 'mousemove' });
	assert.equal(t.beats().length, 1);
	assert.equal(t.beats()[0].opts.headers['X-Frappe-CSRF-Token'], 'tok-old');
	t.beats()[0].respond(400, { exc_type: 'CSRFTokenError' });
	await flush();
	const probe = t.fetch.to('idle_lock.session_token');
	assert.equal(probe.length, 1, 'asks the server for the current token');
	probe[0].respond(200, { message: { user: 'a@example.com', csrf_token: 'tok-new' } });
	await flush();
	assert.equal(t.ctx.csrf_token, 'tok-new', "the SPA's own requests recover too");
	assert.equal(t.beats().length, 2, 'heartbeat retried');
	assert.equal(t.beats()[1].opts.headers['X-Frappe-CSRF-Token'], 'tok-new');
});

test('idx 148: a desk unlock (nexum-idle:gen) refreshes the token before anything fails', async () => {
	const t = loadActivity();
	t.ctx.dispatch('storage', { key: 'nexum-idle:gen', newValue: '1760000000000' });
	await flush();
	const probe = t.fetch.to('idle_lock.session_token');
	assert.equal(probe.length, 1, 'asks for the current token on the unlock signal');
	probe[0].respond(200, { message: { user: 'a@example.com', csrf_token: 'tok-new' } });
	await flush();
	assert.equal(t.ctx.csrf_token, 'tok-new');
	assert.equal(t.ctx.__NEXUM_IDLE__.csrf, 'tok-new');
	assert.equal(t.beats().length, 0, 'no heartbeat without activity');
});

test("idx 148: another user's token is never taken", async () => {
	const t = loadActivity();
	t.doc.dispatchEvent({ type: 'keydown' });
	t.beats()[0].respond(400, {});
	await flush();
	const probe = t.fetch.to('idle_lock.session_token');
	if (probe.length) probe[0].respond(200, { message: { user: 'b@example.com', csrf_token: 'tok-B' } });
	await flush();
	assert.equal(t.ctx.csrf_token, 'tok-old');
	assert.equal(t.beats().length, 1, 'no retry as someone else');
});

// =====================================================================================
// idx 82 — login.js: every <source> failing hides the dead "Play motion" toggle
// =====================================================================================
function loadLogin() {
	const { doc, h } = makeDom({ path: '/login' });
	doc.body.appendChild(h('div', { id: 'page-login' }, h('div', { class: 'login-content' }, h('form', { class: 'form-login' }))));
	const created = doc.createElement;
	let video = null;
	doc.createElement = (tag) => {
		const el = created(tag);
		if (tag === 'video') {
			video = el;
			el.plays = [];
			el.play = () => new Promise((resolve, reject) => el.plays.push({ resolve, reject }));
			el.pause = () => { el.plays.splice(0).forEach((p) => p.reject(new DOMException('paused', 'AbortError'))); };
			el.load = () => {};
		}
		return el;
	};
	const ctx = {
		document: doc, navigator: {},
		matchMedia: (q) => ({ matches: q.includes('min-width'), addEventListener() {} }),
	};
	ctx.window = ctx;
	vm.runInNewContext(read('js/login.js'), ctx, { filename: 'login.js' });
	const toggle = doc.querySelector('.nexum-motion-toggle');
	const art = doc.querySelector('.nexum-art');
	return { doc, video, toggle, art, sources: () => video.querySelectorAll('source') };
}

test('idx 82: when the last <source> fails the toggle is hidden instead of a dead "Play motion"', async () => {
	const t = loadLogin();
	assert.equal(t.sources().length, 2);
	// the browser refuses to start (e.g. autoplay blocked): "Play motion" is offered
	t.video.plays[0].reject(new DOMException('blocked', 'NotAllowedError'));
	await flush();
	assert.equal(t.toggle.hidden, false);
	assert.equal(t.toggle.textContent, 'Play motion');
	// ...but no format can load at all: errors fire at each <source>, never at <video>
	t.sources()[0].dispatchEvent({ type: 'error' });
	t.sources()[1].dispatchEvent({ type: 'error' });
	await flush();
	assert.equal(t.toggle.hidden, true, 'nothing left to play: no toggle');
	assert.equal(t.art.classList.contains('has-video'), false, 'the poster stays');
});

test('idx 82: one unsupported format alone is not a failure (the next source plays)', async () => {
	const t = loadLogin();
	t.sources()[0].dispatchEvent({ type: 'error' }); // webm refused, mp4 still to try
	t.video.dispatchEvent({ type: 'playing' });
	await flush();
	assert.equal(t.art.classList.contains('has-video'), true);
	assert.equal(t.toggle.hidden, false);
	assert.equal(t.toggle.textContent, 'Pause motion');
});

// =====================================================================================
// idx 84 — brand.js chart label/mark pass: not on tooltip churn, not on hidden charts
// =====================================================================================
function loadChartPass() {
	const { doc, h, MutationObserver } = makeDom();
	const raf = [];
	class Chart { // the parts of frappe-charts 2.0.0-rc27 BaseChart/SvgTip the pass sees
		constructor(parent) {
			this.parent = parent;
			this.container = h('div', { class: 'chart-container' });
			parent.appendChild(this.container);
			this.drawSvg();
			this.title = h('span', { class: 'title' });
			this.list = h('ul', { class: 'data-point-list' });
			this.tip = h('div', { class: 'graph-svg-tip comparison' }, this.title, this.list);
			this.container.appendChild(this.tip); // makeTooltip: inside the same container
		}
		drawSvg() { // makeChartArea: the old svg is removed, a fresh one appended
			if (this.svg) this.container.removeChild(this.svg);
			const labels = ['Jan', 'Feb', 'Mar', 'Apr'].map((m, i) => {
				const text = h('text', {}, m);
				text.rect = { left: i * 100, right: i * 100 + 40, top: 0, bottom: 10, width: 40, height: 10 };
				return h('g', {}, text);
			});
			this.svg = h('svg', {}, h('g', { class: 'x axis' }, ...labels), h('rect', { class: 'bar', fill: '#007096', width: '30', x: '0' }));
			this.container.appendChild(this.svg);
		}
		hover(i) { // SvgTip.fill() on every mousemove
			this.title.textContent = 'Month ' + i;
			this.list.innerHTML = '';
			this.list.appendChild(h('li', {}, String(i)));
		}
		labels() { return this.container.querySelectorAll('.x.axis > g > text'); }
	}
	const frappe = { Chart };
	const ctx = {
		frappe, document: doc, MutationObserver,
		requestAnimationFrame: (cb) => raf.push(cb), setTimeout: () => 0, setInterval: () => 0, clearInterval: () => {},
	};
	ctx.window = ctx;
	windowEvents(ctx);
	const src = section(read('js/brand.js'), 'Frappe chart terminal x-axis label overlap', 'Balance Sheet chart: composition columns');
	vm.runInNewContext(src, ctx, { filename: 'brand.js#chart-labels' });
	const page = h('div', { class: 'page-container' });
	doc.body.appendChild(page);
	const chart = new frappe.Chart(page, {});
	const settle = async () => { await flush(); while (raf.length) raf.shift()(); await flush(); };
	const reads = () => chart.labels().reduce((n, l) => n + l.rectReads, 0);
	return { ctx, chart, page, settle, reads, raf };
}

test('idx 84: tooltip rewrites on hover do not re-run the label/mark pass; redraws still do', async () => {
	const t = loadChartPass();
	await t.settle();
	assert.ok(t.reads() > 0, 'first render is measured');
	const before = t.reads();
	for (let i = 0; i < 30; i++) t.chart.hover(i);
	await t.settle();
	assert.equal(t.reads(), before, 'hovering measures nothing');
	t.chart.drawSvg(); // a real redraw (data update, frappe-charts resize redraw)
	await t.settle();
	assert.ok(t.chart.labels()[0].rectReads > 0, 'the fresh svg is measured');
	assert.equal(t.chart.svg.querySelector('rect.bar').style.fillOpacity, '1', 'marks restyled');
});

test('idx 84: a chart on a hidden page is not measured on resize, so its labels are not stripped', async () => {
	const t = loadChartPass();
	await t.settle();
	t.page.style.display = 'none'; // Frappe hides the page when the user navigates away
	const before = t.reads();
	t.ctx.dispatch('resize');
	await t.settle();
	assert.equal(t.reads(), before, 'no forced layout for a hidden chart');
	assert.equal(t.chart.labels().filter((l) => l.style.visibility === 'hidden').length, 0, 'labels untouched');
	t.page.style.display = '';
	t.chart.drawSvg(); // frappe-charts' ResizeObserver redraws it when shown
	await t.settle();
	assert.ok(t.chart.labels()[0].rectReads > 0, 'measured again once visible');
});

// =====================================================================================
// spa-brand.js harness (idx 80, idx 150)
// =====================================================================================
function loadSpaBrand(pathname, brand, build) {
	const { doc, h, MutationObserver } = makeDom({ path: pathname });
	build(doc, h);
	const clock = makeClock();
	const ctx = {
		document: doc, location: { pathname, href: pathname }, navigator: {}, MutationObserver,
		localStorage: makeStorage(), sessionStorage: makeStorage(), __NEXUM_BRAND__: brand,
		NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3 },
		setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
		setInterval: clock.setInterval, clearInterval: clock.clearInterval,
	};
	ctx.window = ctx;
	windowEvents(ctx);
	vm.runInNewContext(read('js/spa-brand.js'), ctx, { filename: 'spa-brand.js' });
	return { ctx, doc, h, clock };
}
const CRM = { name: 'Nexum Air CRM', old: 'Frappe CRM', extra: [] };

test('idx 80: the wordmark swap brands app chrome but never user text in editors or text areas', async () => {
	const t = loadSpaBrand('/crm/leads/CRM-LEAD-0001', CRM, (doc, h) => {
		doc.body.appendChild(h('aside', { class: 'sidebar' }, h('span', { id: 'wordmark' }, 'Frappe CRM')));
		doc.body.appendChild(h('div', { class: 'ProseMirror', contenteditable: 'true', id: 'note' },
			h('p', {}, 'We are migrating from Frappe CRM')));
		doc.body.appendChild(h('div', { class: 'ProseMirror', contenteditable: 'false', id: 'email' },
			h('p', {}, 'Sent from Frappe CRM')));
		doc.body.appendChild(h('textarea', { id: 'raw' }, 'Frappe CRM export'));
		doc.body.appendChild(h('div', { 'data-nx-no-brand': '' }, h('span', { id: 'optout' }, 'Frappe CRM')));
	});
	const text = (id) => t.doc.getElementById(id).textContent;
	assert.equal(text('wordmark'), 'Nexum Air CRM');
	assert.equal(text('note'), 'We are migrating from Frappe CRM', 'editable note untouched');
	assert.equal(text('email'), 'Sent from Frappe CRM', 'read-only ProseMirror content untouched');
	assert.equal(text('raw'), 'Frappe CRM export');
	assert.equal(text('optout'), 'Frappe CRM');

	// ProseMirror re-renders a paragraph (Enter / paste): an ADDED node inside the editor
	const note = t.doc.getElementById('note');
	note.appendChild(t.h('p', {}, 'Frappe CRM pasted'));
	note.firstChild.appendChild(t.doc.createTextNode(' and Frappe CRM typed'));
	t.doc.body.appendChild(t.h('h1', { id: 'later' }, 'Welcome to Frappe CRM')); // new chrome
	await flush();
	assert.equal(note.textContent, 'We are migrating from Frappe CRM and Frappe CRM typedFrappe CRM pasted');
	assert.equal(text('later'), 'Welcome to Nexum Air CRM', 'chrome added later is still branded');
});

test('idx 150: on Builder a user SVG on the canvas is neither hidden nor given a Nexum Air icon', () => {
	const t = loadSpaBrand('/builder/page/home', { name: 'Nexum Air Builder', old: 'Frappe Builder', extra: [] }, (doc, h) => {
		doc.body.appendChild(h('header', {}, h('img', { id: 'logo', src: '/assets/builder/images/builder_logo.png', class: 'h-7' })));
		doc.body.appendChild(h('div', { class: 'canvas' }, h('div', { 'data-block-id': 'b1', id: 'block' },
			h('div', {}, h('svg', { viewBox: '0 0 300 300', id: 'badge' })))));
	});
	const badge = t.doc.getElementById('badge');
	assert.equal(badge.parentElement.querySelectorAll('[data-nexum-logo-img]').length, 0, 'no icon inside the block');
	assert.equal(badge.parentElement.getAttribute('data-nexum-logo'), null);
	const logo = t.doc.getElementById('logo');
	assert.equal(logo.parentElement.querySelectorAll('img[data-nexum-logo-img]').length, 1, "Builder's own logo still swapped");
	assert.equal(t.doc.documentElement.getAttribute('data-nx-spa'), 'builder', 'what spa-brand.css keys on');
});

test("idx 150: other SPAs keep their svg logo swap (CRM's 300x300 mark)", () => {
	const t = loadSpaBrand('/crm/leads', CRM, (doc, h) => {
		doc.body.appendChild(h('div', { class: 'logo', id: 'crm' }, h('svg', { viewBox: '0 0 300 300' })));
	});
	const img = t.doc.getElementById('crm').querySelector('img[data-nexum-logo-img]');
	assert.ok(img, 'Nexum Air icon injected');
	assert.equal(img.getAttribute('src'), '/assets/my_branding/images/icons/crm_app2.svg');
});

test('idx 150: spa-brand.css hides the svg fingerprints everywhere except Builder', () => {
	const css = read('css/spa-brand.css').replace(/\/\*[\s\S]*?\*\//g, '');
	const rule = /([^{}]+)\{\s*display:\s*none\s*!important;?\s*\}/g;
	const selectors = [];
	for (let m; (m = rule.exec(css));) selectors.push(...m[1].split(',').map((s) => s.trim()));
	const svgs = selectors.filter((s) => s.includes('svg[viewBox='));
	assert.deepEqual(svgs.map((s) => s.replace(/^html:not\(\[data-nx-spa="builder"\]\)\s+/, '')).sort(),
		['svg[viewBox="0 0 117 117"]', 'svg[viewBox="0 0 118 118"]', 'svg[viewBox="0 0 300 300"]', 'svg[viewBox="0 0 80 79"]']);
	for (const s of svgs) assert.match(s, /^html:not\(\[data-nx-spa="builder"\]\) svg/, s);
	assert.ok(selectors.includes('img[src$="builder_logo.png"]'), "Builder's png logo is still hidden");
	// the scope only works if the html attribute selector matches what spa-brand.js sets
	const { doc, h } = makeDom();
	const svg = h('svg', { viewBox: '0 0 300 300' });
	doc.body.appendChild(svg);
	const scoped = svgs.find((s) => s.includes('300 300'));
	doc.documentElement.setAttribute('data-nx-spa', 'crm');
	assert.equal(svg.matches(scoped), true);
	doc.documentElement.setAttribute('data-nx-spa', 'builder');
	assert.equal(svg.matches(scoped), false);
});

// idx 94 (review of batch 205, finding 3) — brand.js answers each Home widget's FIRST
// with_doc from boot, and fakes no docinfo: a form opened on the card later must fetch
// its doc + docinfo (timeline, assignments, @mentions all need one).
function loadWidgetBoot(docs) {
	const src = section(read('js/brand.js'), 'Home KPI widgets: docs from boot', 'AGPL source-code offer');
	const locals = {};
	const fetched = [];
	const frappe = {
		boot: { nx_widget_docs: docs },
		model: {
			docinfo: {},
			sync(list) {
				for (const d of list) (locals[d.doctype] = locals[d.doctype] || {})[d.name] = d;
			},
			with_doc(doctype, name, callback) {
				fetched.push(doctype + '/' + name);
				callback && callback(name);
				return Promise.resolve((locals[doctype] || {})[name]);
			},
		},
		get_doc: (doctype, name) => (locals[doctype] || {})[name],
	};
	const ctx = { window: {}, frappe, locals, console };
	ctx.window.frappe = frappe;
	vm.runInNewContext(src, ctx, { filename: 'brand.js#widget-boot' });
	return { frappe, fetched, locals };
}

test('idx 94: the first with_doc per boot doc is local, later ones fetch, no docinfo is faked', async () => {
	const t = loadWidgetBoot([{ doctype: 'Number Card', name: 'Receivables', label: 'Receivables' }]);
	const first = await t.frappe.model.with_doc('Number Card', 'Receivables'); // as the widget calls it
	assert.equal(first.label, 'Receivables');
	assert.deepEqual(t.fetched, [], 'the widget render needs no request');
	assert.equal(t.frappe.model.docinfo['Number Card'], undefined, 'no fake docinfo for a form to trip on');
	await t.frappe.model.with_doc('Number Card', 'Receivables');
	assert.deepEqual(t.fetched, ['Number Card/Receivables'], 'a later open (the form) fetches');
	await t.frappe.model.with_doc('Number Card', 'Payables');
	assert.deepEqual(t.fetched, ['Number Card/Receivables', 'Number Card/Payables'], 'other docs are untouched');
});

test('idx 94: a form open is never answered from boot, even as the first call', async () => {
	const t = loadWidgetBoot([{ doctype: 'Number Card', name: 'Receivables' }]);
	let called = 0;
	await t.frappe.model.with_doc('Number Card', 'Receivables', () => called++); // formview passes a callback
	assert.equal(called, 1);
	assert.deepEqual(t.fetched, ['Number Card/Receivables']);
	const u = loadWidgetBoot([{ doctype: 'Number Card', name: 'Receivables' }]);
	u.frappe.get_route = () => ['Form', 'Number Card', 'Receivables'];
	await u.frappe.model.with_doc('Number Card', 'Receivables');
	assert.deepEqual(u.fetched, ['Number Card/Receivables'], 'no shortcut on a form route');
});

test('idx 94: no boot docs leaves with_doc alone', () => {
	const t = loadWidgetBoot([]);
	assert.equal(t.frappe.model.with_doc.name, 'with_doc');
});
