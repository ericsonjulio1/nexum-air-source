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
		a.style.cssText = "position:fixed;left:10px;bottom:6px;z-index:2000000;font-size:11px;line-height:1;color:#8a99a3;opacity:.5;text-decoration:none;background:rgba(255,255,255,.65);padding:2px 6px;border-radius:4px;font-family:inherit;";
		a.addEventListener("mouseover", function () { a.style.opacity = "1"; });
		a.addEventListener("mouseout", function () { a.style.opacity = ".5"; });
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
