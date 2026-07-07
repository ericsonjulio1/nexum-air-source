// --- Stale-asset guard -------------------------------------------------------
// The Slides app registers a service worker at ROOT scope
// (apps/slides/frontend/src/main.ts: navigator.serviceWorker.register('/service-worker.js')
// with no {scope}, so it controls the whole origin). That SW intercepts EVERY
// /assets/* and /api/method/frappe.client.* request site-wide and serves them
// CACHE-FIRST, with the asset cache only purged when the SW file's baked-in
// `version` changes. On the multi-app desk that freezes an app's bundle (or a
// list/dashboard API response) across deploys, bypassing our no-store HTML
// headers entirely — the cause of "<app> won't load / loads stale after a
// deploy" (Lending, 2026-06-15). The desk should never be under a service
// worker, so on every desk load we unregister any SW and drop its caches; if one
// was actively controlling this page we reload ONCE (sessionStorage-guarded
// against loops) to discard anything it already served stale.
(function () {
	try {
		if (!("serviceWorker" in navigator)) return;
		navigator.serviceWorker.getRegistrations().then(function (regs) {
			if (!regs || !regs.length) return;
			var hadController = !!navigator.serviceWorker.controller;
			Promise.all(
				regs.map(function (r) { return r.unregister().catch(function () {}); })
			).then(function () {
				if (window.caches && caches.keys) {
					caches.keys().then(function (keys) {
						keys.forEach(function (k) {
							if (k.indexOf("slides-") === 0) { try { caches.delete(k); } catch (e) {} }
						});
					}).catch(function () {});
				}
				if (hadController && !sessionStorage.getItem("nx_sw_cleared")) {
					try { sessionStorage.setItem("nx_sw_cleared", "1"); } catch (e) {}
					location.reload();
				}
			});
		}).catch(function () {});
	} catch (e) {}
})();

// AGPL source-code offer (§13): a discreet, always-present link to the published
// Corresponding Source for the AGPL-licensed apps in this stack. See SOURCES.md.
// Restyle/relocate freely, but keep it reachable from the running app.
(function () {
	function add() {
		if (!document.body || document.getElementById("nx-source-link")) return;
		var a = document.createElement("a");
		a.id = "nx-source-link";
		a.href = "https://nexumair.com/source.html";
		a.target = "_blank"; a.rel = "noopener";
		a.textContent = "Source code";
		a.title = "Open-source licenses & source code (AGPL)";
		// Kept reachable on every page (AGPL §13) but visually unobtrusive: tucked in
		// the bottom-right corner, tiny + muted + no background, brightens on hover.
		a.style.cssText = "position:fixed;right:7px;bottom:4px;z-index:2000000;font-size:9px;line-height:1;color:#aab4bc;opacity:.22;text-decoration:none;font-family:inherit;letter-spacing:.2px;";
		a.addEventListener("mouseover", function () { a.style.opacity = "1"; });
		a.addEventListener("mouseout", function () { a.style.opacity = ".22"; });
		document.body.appendChild(a);
	}
	if (document.readyState !== "loading") add();
	else document.addEventListener("DOMContentLoaded", add);
})();

// Branded loading splash. Frappe's own .splash is removed by desk.js
// (make_page_container) as soon as #body exists, so we mount our own full-screen
// overlay (identical look) and fade it out the MOMENT the styled desk is actually
// on screen — instead of a fixed 5s wait. This feels snappy on a fast load yet
// still fully covers a slow one (PH->Germany latency), because we hide on the
// first desk-ready DOM marker, floored at MIN_MS (no flicker) and hard-capped at
// CAP_MS (the old behaviour, as a fallback if the marker never appears).
(function () {
	var CAP_MS = 5000; // never show longer than this
	var MIN_MS = 500; // never flash shorter than this
	// first of these to appear == the usable, styled desk is rendered
	var READY = ".layout-main-section, .workspace-sidebar, .desktop-container, .navbar .navbar-home";
	var el, done = false, observer = null, capTimer = null, scheduled = false;

	function navElapsed() {
		return window.performance && performance.now ? performance.now() : 0;
	}

	function readyNow() {
		try {
			return !!document.querySelector(READY);
		} catch (e) {
			return false;
		}
	}

	function hide() {
		if (done) return;
		done = true;
		if (observer) try { observer.disconnect(); } catch (e) {}
		if (capTimer) clearTimeout(capTimer);
		if (!el) return;
		el.classList.add("nexum-splash-hide");
		setTimeout(function () {
			if (el && el.parentNode) el.parentNode.removeChild(el);
		}, 600);
	}

	function maybeHide() {
		if (done || !readyNow()) return;
		setTimeout(hide, Math.max(0, MIN_MS - navElapsed())); // honour the floor
	}

	// coalesce mutation bursts into one check per frame (keeps the observer cheap
	// during the desk's heavy initial render)
	function onMutate() {
		if (scheduled || done) return;
		scheduled = true;
		(window.requestAnimationFrame || window.setTimeout)(function () {
			scheduled = false;
			maybeHide();
		});
	}

	function mount() {
		if (document.getElementById("nexum-splash")) return;
		el = document.createElement("div");
		el.id = "nexum-splash";
		(document.body || document.documentElement).appendChild(el);

		// fallback hard cap (old fixed behaviour) in case the ready-marker never shows
		capTimer = setTimeout(hide, Math.max(0, CAP_MS - navElapsed()));

		if (readyNow()) {
			maybeHide();
			return;
		}
		try {
			observer = new MutationObserver(onMutate);
			observer.observe(document.documentElement, { childList: true, subtree: true });
		} catch (e) {
			/* no MutationObserver -> cap timer still guarantees teardown */
		}
	}

	if (document.body) mount();
	else document.addEventListener("DOMContentLoaded", mount);
})();

// NOTE (2026-06-09): the client-side desk-launcher reorder that used to live here
// was REMOVED. It re-sorted `.desktop-container .desktop-icon` on every load via a
// MutationObserver, which is the SAME native grid Frappe's /desk "Desktop" page
// renders — and that native grid already sorts by `idx` (label tie-break) AND is
// drag-to-reorder + persistent (save_layout -> Desktop Icon idx). Our re-sort only
// ranked ~12 ERPNext modules and left every other app at an arbitrary position, so
// it (a) overrode the user's own saved arrangement on every open and (b) left the
// non-ranked apps shuffling. Dropping it lets the native, stable, user-arrangeable
// order win. Curated ordering, if wanted, should be done via Workspace sequence_id
// / Desktop Icon idx (data), not by re-sorting the DOM.

// Open the desk-launcher app tiles (Builder / Helpdesk / Insights / CRM / Teams /
// Drive / Lending / Learning ...) in the SAME window instead of spawning a new
// browser tab — or, in the Nativefier desktop app, the EXTERNAL browser. Frappe's
// desktop.js tags these tiles with target="_blank" because each app's route is an
// absolute http(s) URL (they're separate same-origin SPAs). We strip that target at
// click time (capture phase, so it runs before the navigation) → the click becomes
// an ordinary in-place navigation. Scoped to the launcher grid so genuine external
// links elsewhere in the desk still open in a new tab.
(function () {
	document.addEventListener(
		"click",
		function (e) {
			try {
				var a =
					e.target &&
					e.target.closest &&
					e.target.closest(".desktop-container a.desktop-icon[target='_blank']");
				if (a) a.removeAttribute("target");
			} catch (err) {
				/* never let this break a click */
			}
		},
		true
	);
})();

// Nexum Air chart palette — frappe-charts ships a default colour sequence with a
// pink/red, seen on report charts (Balance Sheet / P&L) AND dashboard charts
// (AR/AP Ageing donuts). Force the brand slate/teal palette on every chart by
// wrapping the global frappe.Chart (frappe/ui/chart.js does `frappe.Chart = Chart`
// from frappe-charts). Two subtleties this handles:
//   1. FORCE (not "when absent") — the dashboard widget passes its own colour
//      array, so an "only if missing" check would skip it. We overwrite colors
//      for every chart EXCEPT heatmaps (which need their own gradient).
//   2. TIMING — dashboard charts render on page load and can beat a polling
//      patch. So instead of polling, we intercept the assignment: install a
//      property setter on `frappe.Chart` that wraps the class the instant
//      frappe-charts assigns it, before any chart is constructed.
(function () {
	// Ordered for ADJACENT contrast: warm (gold/terracotta) interleaved early so
	// neighbouring series never sit as two near-identical blues (the teal/slate
	// pair was hard to tell apart). All on-brand, none pink.
	var PALETTE = ["#2E5562", "#E0A24B", "#C2603E", "#4FA88B", "#557E94", "#9DBEC8"];
	function wrap(Orig) {
		if (typeof Orig !== "function" || Orig.__nexumPatched) return Orig;
		function NexumChart(element, options) {
			try {
				if (options && options.type !== "heatmap") {
					options.colors = PALETTE.slice();
				}
			} catch (e) {
				/* never block a chart from rendering */
			}
			return new Orig(element, options);
		}
		NexumChart.prototype = Orig.prototype;
		try {
			Object.keys(Orig).forEach(function (k) {
				NexumChart[k] = Orig[k];
			});
		} catch (e) {}
		NexumChart.__nexumPatched = true;
		return NexumChart;
	}
	function install() {
		if (!window.frappe) return false;
		if (frappe.Chart) {
			// already loaded — wrap in place
			if (!frappe.Chart.__nexumPatched) frappe.Chart = wrap(frappe.Chart);
			return true;
		}
		// interceptor already installed (repeated poll, or a second injection of this
		// script) — don't redefine the accessor, which would drop the already-wrapped class
		if (frappe.__nexumChartHook) return true;
		// not assigned yet — intercept the assignment so we wrap before any render
		try {
			var stored;
			Object.defineProperty(frappe, "Chart", {
				configurable: true,
				enumerable: true,
				get: function () {
					return stored;
				},
				set: function (v) {
					stored = wrap(v);
				},
			});
			frappe.__nexumChartHook = true;
			return true;
		} catch (e) {
			return false;
		}
	}
	if (!install()) {
		var n = 0;
		var t = setInterval(function () {
			if (install() || ++n > 100) clearInterval(t);
		}, 50);
	}
})();

// EAM/Maintenance breadcrumb: our Maintenance doctypes are surfaced inside the Assets
// workspace but belong to the "EAM" module, which Frappe doesn't map to a workspace — so
// opening one from Assets drops the "Assets" breadcrumb (leaving only the Home icon).
// Map EAM -> Assets in module_wise_workspaces so the clickable "Assets" crumb stays, like
// native Asset doctypes. (Lives here because my_branding's brand.js is the app-wide desk
// script that's reliably served; eam has no /assets symlink.)
(function () {
	function mapEamToAssets() {
		try {
			var m = frappe.boot && frappe.boot.module_wise_workspaces;
			if (!m) return false;
			m["EAM"] = m["EAM"] || [];
			if (m["EAM"].indexOf("Assets") === -1) m["EAM"].push("Assets");
			return true;
		} catch (e) {
			return false;
		}
	}
	if (!mapEamToAssets()) {
		var n = 0;
		var t = setInterval(function () {
			if (mapEamToAssets() || ++n > 100) clearInterval(t);
		}, 50);
	}
})();

// --- Desk-home glass/aurora scope + greeting -------------------------------
// The post-login home is the legacy /desk Desktop-Icon grid (.desktop-container,
// inside the .desktop-wrapper flex column). Toggle body.nx-desk-home so brand.css
// can scope the aurora + frosted tiles to ONLY this screen, and inject a
// time-aware greeting above the grid. Idempotent + self-healing across SPA route
// changes via a MutationObserver, coalesced to one reconcile per frame.
(function () {
	function salutation(h) {
		return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
	}
	function firstName() {
		try {
			var u = (frappe.boot && frappe.boot.user) || {};
			// Prefer the real first name; else take the FIRST token of a full name
			// (split before falling back to the whole-name string, so we never
			// greet "Good morning, Ericson Rubio Julio").
			var full = u.full_name || (frappe.session && frappe.session.user_fullname) || "";
			return u.first_name || full.split(" ")[0] || "there";
		} catch (e) { return "there"; }
	}
	function dateStr() {
		try {
			return new Date().toLocaleDateString(undefined,
				{ weekday: "long", day: "numeric", month: "long" });
		} catch (e) { return ""; }
	}
	function ensureGreeting(grid) {
		if (document.getElementById("nx-greeting")) return;
		var parent = grid.parentElement;
		if (!parent) return;
		var wrap = document.createElement("div");
		wrap.id = "nx-greeting";
		var hi = document.createElement("div");
		hi.className = "nx-greeting-hi";
		// textContent (not innerHTML): the first name comes from user-editable
		// User fields, so it must never be interpolated into markup.
		hi.textContent = salutation(new Date().getHours()) + ", " + firstName();
		var sub = document.createElement("div");
		sub.className = "nx-greeting-sub";
		var d = dateStr();
		sub.textContent = d ? d + " · your workspace is ready" : "Your workspace is ready";
		wrap.appendChild(hi);
		wrap.appendChild(sub);
		parent.insertBefore(wrap, grid);
	}
	// Frappe's classic desk HIDES the previous page (display:none) instead of
	// removing it from the DOM, so .desktop-container lingers after you navigate
	// away from the home grid. Gate on actual visibility (getClientRects is empty
	// for a display:none element) — otherwise the class stays ON and the fixed
	// aurora + greeting leak onto every subsequent list/form for the session.
	function isVisible(el) { return !!(el && el.getClientRects().length); }
	function sync() {
		var grid = document.querySelector(".desktop-container");
		if (isVisible(grid)) {
			document.body.classList.add("nx-desk-home");
			ensureGreeting(grid);
		} else {
			document.body.classList.remove("nx-desk-home");
			var g = document.getElementById("nx-greeting");
			if (g) g.remove();
		}
	}
	// Coalesce observer callbacks to one reconcile per animation frame (mirrors
	// the splash IIFE above) so heavy desk DOM churn — and the childList mutation
	// our own insert/remove itself triggers — can't thrash sync().
	var scheduled = false;
	function schedule() {
		if (scheduled) return;
		scheduled = true;
		var raf = window.requestAnimationFrame || function (cb) { return setTimeout(cb, 16); };
		raf(function () { scheduled = false; sync(); });
	}
	function start() {
		// nx-desk marks EVERY desk page (this script loads only in the desk via
		// app_include_js) so brand.css can paint the aurora background across the
		// whole interface. Persists across in-SPA nav — never removed. The
		// home-only extras (frosted tiles + greeting) stay gated on nx-desk-home.
		document.body.classList.add("nx-desk");
		sync();
		try {
			new MutationObserver(schedule)
				.observe(document.body, { childList: true, subtree: true });
		} catch (e) {}
	}
	if (document.readyState !== "loading") start();
	else document.addEventListener("DOMContentLoaded", start);
})();
