/* Nexum Air branding for the standalone frappe-ui SPAs (Frappe HR/CRM/Helpdesk/
 * Drive/Insights/Builder/Gameplan/LMS).
 *
 * Injected into each SPA's <head> by my_branding.spa_brand (after_request hook),
 * which also sets window.__NEXUM_BRAND__ = {name, old} for the current app. The
 * colour work is pure CSS (spa-brand.css); this file handles what CSS can't:
 *   1. The in-app logo is an inline <svg> (Frappe cube, viewBox 117/118) or an
 *      <img> (builder_logo.png). CSS hides it; here we drop a Nexum Air <img>
 *      sibling beside it. Our <img> is created outside Vue's vdom, so re-renders
 *      leave it; if Vue remounts the logo we just re-add it.
 *   2. The router resets document.title to "Frappe X" on route changes — keep it
 *      branded.
 *   3. The visible "Frappe X" wordmark (headings, sidebar, login) -> "Nexum Air X".
 *
 * Everything is wrapped so a failure can never break the host app; the observer
 * is debounced and does only cheap work. */
(function () {
	// --- Stale-asset guard ---------------------------------------------------
	// Slides registers a ROOT-scope service worker (see brand.js note) that serves
	// /assets/* and frappe.client API cache-first across the whole origin, freezing
	// these SPAs' bundles/data across deploys. Unregister it here too. We SKIP the
	// Slides app's own pages (/slides) so we don't fight its registration on the
	// one surface that legitimately uses it; the desk's brand.js still clears it
	// the moment the user leaves Slides.
	try {
		if (location.pathname.indexOf("/slides") !== 0 && "serviceWorker" in navigator) {
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
		}
	} catch (e) { /* never break the host app */ }

	// AGPL source-code offer (§13): discreet, always-present link to the published
	// Corresponding Source. Mirrors the desk's brand.js; see SOURCES.md.
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

	// Builder defaults to the OS colour scheme (VueUse useDark, localStorage key
	// "vueuse-color-scheme"): on dark-mode machines it opens dark out of the box.
	// Seed the preference to LIGHT exactly once — only while the key is ABSENT
	// (i.e. the user has never chosen). Builder's own theme toggle writes this
	// same key, so an explicit choice (incl. dark) is respected forever after;
	// the desk/ERPNext theme is a separate per-user setting and is untouched.
	// This script is injected in <head> and runs before the app bundle, so
	// useDark reads the seeded value at init (no flash).
	try {
		if (location.pathname.indexOf("/builder") === 0 && !localStorage.getItem("vueuse-color-scheme")) {
			localStorage.setItem("vueuse-color-scheme", "light");
			document.documentElement.setAttribute("data-theme", "light");
		}
	} catch (e) {
		/* never break the host app */
	}

	var BRAND = window.__NEXUM_BRAND__ || { name: "Nexum Air", old: null };
	var NAME = BRAND.name || "Nexum Air";
	var OLD = BRAND.old || null;
	var MARK = "/assets/my_branding/images/nexum-mark.png";
	var FAVICON = "/assets/my_branding/images/favicon.png";
	// All text swaps to apply: the "Frappe X"->"Nexum Air X" wordmark plus any
	// per-app `extra` pairs (e.g. Insights' "ERPNext"->"Nexum Air").
	var SWAPS = [];
	if (OLD) SWAPS.push([OLD, NAME]);
	(BRAND.extra || []).forEach(function (p) {
		if (p && p.length === 2) SWAPS.push([p[0], p[1]]);
	});
	function hasSwap(s) {
		for (var k = 0; k < SWAPS.length; k++) {
			if (s.indexOf(SWAPS[k][0]) !== -1) return true;
		}
		return false;
	}
	function applySwaps(s) {
		for (var k = 0; k < SWAPS.length; k++) {
			if (s.indexOf(SWAPS[k][0]) !== -1) s = s.split(SWAPS[k][0]).join(SWAPS[k][1]);
		}
		return s;
	}
	// Each app's native logo. Add new fingerprints here, not per-app code:
	//   svg 117/118 = the Frappe cube (HR/Drive/Helpdesk/Gameplan)
	//   svg 300     = Frappe CRM's logo
	//   builder_logo.png = Builder
	//   the data: prefix = Frappe Insights' inlined (base64) logo
	var LOGO_SELECTOR =
		'svg[viewBox="0 0 117 117"],svg[viewBox="0 0 118 118"],svg[viewBox="0 0 300 300"],' +
		'img[src$="builder_logo.png"],' +
		'img[src^="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHe"]';

	function ensureLogos() {
		var marks = document.querySelectorAll(LOGO_SELECTOR);
		for (var i = 0; i < marks.length; i++) {
			var el = marks[i];
			var parent = el.parentNode;
			if (!parent || parent.getAttribute("data-nexum-logo")) continue;
			if (el.getAttribute("data-nexum-logo-img")) continue; // our own inject
			parent.setAttribute("data-nexum-logo", "1");
			var img = document.createElement("img");
			img.src = MARK;
			img.alt = "Nexum Air";
			img.className = el.getAttribute("class") || ""; // inherit sizing classes
			img.setAttribute("data-nexum-logo-img", "1");
			parent.insertBefore(img, el);
		}
	}

	function brandTitle() {
		if (SWAPS.length && hasSwap(document.title)) {
			document.title = applySwaps(document.title);
		}
	}

	// The frappe-ui SPAs (Helpdesk/Gameplan/...) set their OWN Frappe favicon at
	// RUNTIME via JS, so the server-side HTML rewrite in spa_brand.py never sees it
	// (Helpdesk's served HTML has no <link rel=icon> at all). Enforce the Nexum Air
	// favicon here and re-assert it if the app changes it. `rel~="icon"` matches the
	// "icon"/"shortcut icon" tokens used for the browser TAB favicon (NOT the
	// separate "apple-touch-icon" token).
	function ensureFavicon() {
		var links = document.querySelectorAll('link[rel~="icon"]');
		if (links.length) {
			for (var i = 0; i < links.length; i++) {
				if (links[i].href.indexOf("my_branding") === -1) links[i].href = FAVICON;
			}
		} else if (document.head) {
			var l = document.createElement("link");
			l.rel = "icon";
			l.href = FAVICON;
			document.head.appendChild(l);
		}
	}

	// Rewrite the visible "Frappe X" wordmark to "Nexum Air X" within `root`.
	// Text-nodes only — never attributes or <script>/<style> — so we can't corrupt
	// code or data. PERF: scoped to a subtree (the initial pass, then only the
	// nodes each mutation ADDS) instead of re-walking the whole document.body every
	// tick — which on a busy page (live lists, virtual scroll) was the one hot spot.
	function brandSubtree(root) {
		if (!SWAPS.length || !root) return;
		if (root.nodeType === 3) {
			// a text node was added directly
			if (hasSwap(root.nodeValue)) root.nodeValue = applySwaps(root.nodeValue);
			return;
		}
		if (root.nodeType !== 1) return; // only elements have a text subtree
		if (root.nodeName === "SCRIPT" || root.nodeName === "STYLE") return;
		var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
			acceptNode: function (node) {
				var p = node.parentNode;
				if (p && (p.nodeName === "SCRIPT" || p.nodeName === "STYLE")) {
					return NodeFilter.FILTER_REJECT;
				}
				return hasSwap(node.nodeValue)
					? NodeFilter.FILTER_ACCEPT
					: NodeFilter.FILTER_SKIP;
			},
		});
		var node;
		while ((node = walker.nextNode())) {
			node.nodeValue = applySwaps(node.nodeValue);
		}
	}

	// Some SPAs (Slides, Insights, Gameplan) ship NO app-switcher, so there's no way
	// back to the desk launcher. Inject a small floating "Apps" button that returns
	// to it. Scoped to those routes (apps like CRM/Builder already have a switcher).
	// Gameplan serves at /g.
	function ensureBackButton() {
		if (!/^\/(slides|insights|g)(\/|$)/.test(location.pathname)) return;
		if (document.getElementById("nexum-apps-btn") || !document.body) return;
		var a = document.createElement("a");
		a.id = "nexum-apps-btn";
		a.href = "/app";
		a.title = "Back to Nexum Air apps";
		a.innerHTML =
			'<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style="flex:none">' +
			'<rect x="3" y="3" width="8" height="8" rx="2"></rect><rect x="13" y="3" width="8" height="8" rx="2"></rect>' +
			'<rect x="3" y="13" width="8" height="8" rx="2"></rect><rect x="13" y="13" width="8" height="8" rx="2"></rect>' +
			"</svg><span>Apps</span>";
		a.style.cssText =
			"position:fixed;left:16px;bottom:16px;z-index:2147483000;display:inline-flex;align-items:center;" +
			"gap:7px;background:#107090;color:#fff;text-decoration:none;font:600 13px/1 -apple-system,system-ui,sans-serif;" +
			"padding:9px 13px;border-radius:999px;box-shadow:0 2px 12px rgba(0,0,0,.22);cursor:pointer;";
		document.body.appendChild(a);
	}

	function start() {
		// one full initial pass
		try {
			ensureLogos();
			brandTitle();
			ensureFavicon();
			brandSubtree(document.body);
			ensureBackButton();
		} catch (e) {
			/* never let branding break the app */
		}
		// Apps often set their favicon a beat after first paint — re-assert a few
		// times, then stop (it's stable after init).
		[800, 2500, 6000].forEach(function (t) {
			setTimeout(function () {
				try { ensureFavicon(); } catch (e) {}
			}, t);
		});
		var pending = null;
		var obs = new MutationObserver(function (mutations) {
			// Cheap per-mutation work: only rewrite the wordmark inside the subtrees
			// that were just ADDED (route changes / new components), not the whole body.
			for (var i = 0; i < mutations.length; i++) {
				var added = mutations[i].addedNodes;
				for (var j = 0; j < added.length; j++) {
					try {
						brandSubtree(added[j]);
					} catch (e) {
						/* ignore */
					}
				}
			}
			// Logos + title: a debounced light pass (cheap selector + title check).
			if (pending) return;
			pending = setTimeout(function () {
				pending = null;
				try {
					ensureLogos();
					brandTitle();
					ensureFavicon();
					ensureBackButton();
				} catch (e) {
					/* ignore */
				}
			}, 250);
		});
		obs.observe(document.documentElement, { subtree: true, childList: true });
	}

	if (document.body) start();
	else document.addEventListener("DOMContentLoaded", start);
})();
