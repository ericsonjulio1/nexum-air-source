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
	// The injected header logo should match the app's own launcher tile (owner
	// request, v16-prod-133) — one generic N for every SPA read as unbranded.
	// Keyed by the SPA's first path segment; anything unmapped keeps the N mark.
	// These are the same squircle assets the desk launcher + apps switcher use.
	var APP_ICONS = {
		crm: "crm_app2.svg",
		helpdesk: "helpdesk_app.svg",
		drive: "drive_app.svg",
		lms: "lms_app2.svg",
		builder: "builder_app.svg",
		g: "gameplan_app2.svg", // Gameplan ("Teams") serves at /g
		slides: "slides_app.svg",
		insights: "insights_app.svg",
		hr: "hrms_app.svg",
	};
	var APP_MARK = (function () {
		try {
			var seg = (location.pathname.split("/")[1] || "").toLowerCase();
			if (APP_ICONS[seg]) return "/assets/my_branding/images/icons/" + APP_ICONS[seg];
		} catch (e) {
			/* fall back to the generic mark */
		}
		return MARK;
	})();
	var FAVICON = "/assets/my_branding/images/favicon.png";
	// Two tiers of text swap:
	//  * SWAPS — the specific "Frappe X" -> "Nexum Air X" wordmark. "Frappe X" is
	//    distinctive enough to substring-replace anywhere in the DOM safely.
	//  * EXACT_SWAPS — the per-app `extra` pairs (e.g. Insights "ERPNext"->"Nexum Air",
	//    Gameplan "Gameplan"->"Teams"). These are BARE tokens common enough to appear in
	//    real user/business data (an Insights query-result cell containing "ERPNext", a
	//    project literally named "Gameplan"), so substring-replacing them across the whole
	//    subtree silently rewrote data values. Apply them ONLY to a text node whose TRIMMED
	//    value IS exactly the token — i.e. a standalone chrome label (wordmark / data-source
	//    name) — never a substring inside a larger data string.
	var SWAPS = [];
	if (OLD) SWAPS.push([OLD, NAME]);
	var EXACT_SWAPS = [];
	(BRAND.extra || []).forEach(function (p) {
		if (p && p.length === 2) EXACT_SWAPS.push([p[0], p[1]]);
	});
	function _trim(s) { return s.replace(/^\s+|\s+$/g, ""); }
	function hasSwap(s) {
		for (var k = 0; k < SWAPS.length; k++) {
			if (s.indexOf(SWAPS[k][0]) !== -1) return true;
		}
		var t = _trim(s);
		for (var j = 0; j < EXACT_SWAPS.length; j++) {
			if (t === EXACT_SWAPS[j][0]) return true;
		}
		return false;
	}
	function applySwaps(s) {
		for (var k = 0; k < SWAPS.length; k++) {
			if (s.indexOf(SWAPS[k][0]) !== -1) s = s.split(SWAPS[k][0]).join(SWAPS[k][1]);
		}
		// exact-only: replace just when the trimmed text node equals the token, so a
		// standalone chrome label is branded but a substring of real data is left intact.
		var t = _trim(s);
		for (var j = 0; j < EXACT_SWAPS.length; j++) {
			if (t === EXACT_SWAPS[j][0]) { s = s.split(EXACT_SWAPS[j][0]).join(EXACT_SWAPS[j][1]); break; }
		}
		return s;
	}
	// Each app's native logo. Add new fingerprints here, not per-app code:
	//   svg 117/118 = the Frappe cube (HR/Drive/Helpdesk/Gameplan)
	//   svg 300     = Frappe CRM's logo
	//   svg 80 79   = Frappe LMS (Learning) book logo
	//   builder_logo.png = Builder
	var LOGO_SELECTOR =
		'svg[viewBox="0 0 117 117"],svg[viewBox="0 0 118 118"],svg[viewBox="0 0 300 300"],' +
		'svg[viewBox="0 0 80 79"],' +
		'img[src$="builder_logo.png"]';

	function ensureLogos() {
		var marks = document.querySelectorAll(LOGO_SELECTOR);
		for (var i = 0; i < marks.length; i++) {
			var el = marks[i];
			var parent = el.parentNode;
			if (!parent || parent.getAttribute("data-nexum-logo")) continue;
			if (el.getAttribute("data-nexum-logo-img")) continue; // our own inject
			parent.setAttribute("data-nexum-logo", "1");
			var img = document.createElement("img");
			img.src = APP_MARK;
			img.alt = "Nexum Air";
			img.className = el.getAttribute("class") || ""; // inherit sizing classes
			img.setAttribute("data-nexum-logo-img", "1");
			parent.insertBefore(img, el);
		}
	}

	// Frappe Insights (<v2.2) inlined its logo as a base64 PNG whose header bytes
	// are just the generic "64x64 RGBA PNG" signature — NOT unique to that logo
	// file — so matching it globally (as LOGO_SELECTOR used to) risked hiding/
	// mislabeling any ordinary base64-embedded image (an avatar, a report
	// thumbnail, ...) on ANY of the frappe-ui SPAs this script runs in. Scope it
	// back to the one route it was written for (same pathname-gate pattern as
	// ensureBackButton() above), and tag matches with a class so spa-brand.css
	// only ever hides elements THIS check has approved — instead of matching the
	// base64 header on its own in CSS (which can't check the route).
	function ensureLegacyInsightsLogo() {
		if (location.pathname.indexOf("/insights") !== 0) return;
		var marks = document.querySelectorAll(
			'img[src^="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHe"]'
		);
		for (var i = 0; i < marks.length; i++) {
			var el = marks[i];
			if (el.getAttribute("data-nexum-logo-img")) continue; // our own inject
			el.classList.add("nx-legacy-logo-hidden");
			var parent = el.parentNode;
			if (!parent || parent.getAttribute("data-nexum-logo")) continue;
			parent.setAttribute("data-nexum-logo", "1");
			var img = document.createElement("img");
			img.src = APP_MARK;
			img.alt = "Nexum Air";
			img.className = el.getAttribute("class") || "";
			img.setAttribute("data-nexum-logo-img", "1");
			parent.insertBefore(img, el);
		}
	}

	function brandTitle() {
		if ((SWAPS.length || EXACT_SWAPS.length) && hasSwap(document.title)) {
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
		if ((!SWAPS.length && !EXACT_SWAPS.length) || !root) return;
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
			"gap:7px;background:#2E5562;color:#fff;text-decoration:none;font:600 13px/1 -apple-system,system-ui,sans-serif;" +
			"padding:9px 13px;border-radius:999px;box-shadow:0 2px 12px rgba(0,0,0,.22);cursor:pointer;";
		document.body.appendChild(a);
	}

	// The SPA sidebar "Apps" switcher (crm Apps.vue, and the same component in
	// helpdesk/lms) is a frappe-ui <Popover trigger="hover"> nested in a reka
	// dropdown. Its flyout is portaled to <body> as [data-slot="content"]. In this
	// nested context the Popover's CONTENT-side mouseover never fires, so once the
	// cursor leaves the "Apps" trigger a 100ms leave timer (leaveDelay=0.1) closes
	// the flyout before you can reach it — and even landing on it closes it, so the
	// switcher is effectively unusable by hover (frappe-ui has since DEPRECATED
	// this hover path). Verified on live prod: a content-side hover-bridge does NOT
	// help (content mouseover is dead); but the Popover keeps open while its
	// `pointerOverTargetOrPopup` flag is true, and that flag CAN be re-asserted
	// from the TRIGGER side (a plain element whose mouseover is reliable). So while
	// an Apps flyout is open we re-dispatch a bubbling `mouseover` on the trigger on
	// a short timer to hold it open, and stop (dispatching `mouseleave` so it closes
	// normally) only after the cursor has stayed clearly away from the trigger and
	// flyout for a grace window. Re-asserting per-tick UNCONDITIONALLY-while-near
	// (not gated frame-by-frame, which dropped frames mid-move) is what makes it
	// survive the reach. Purely additive, scoped to the Apps flyout, no app source.
	var _nxApps = null;
	function nxAppsFlyoutKeepAlive() {
		if (_nxApps) { _nxApps.start(); return; } // set up once; (re)start on later opens
		var STEP = 30, GRACE = 250;
		var S = { x: -1, y: -1, timer: null, outMs: 0 };
		document.addEventListener("mousemove", function (e) { S.x = e.clientX; S.y = e.clientY; }, true);
		function flyout() {
			var p = document.querySelectorAll('[data-slot="content"]');
			for (var i = 0; i < p.length; i++)
				if (p[i].querySelectorAll("a img").length >= 2) return p[i]; // app links = the Apps flyout
			return null;
		}
		function trigger() {
			var b = document.querySelectorAll("button");
			for (var i = 0; i < b.length; i++) {
				var t = (b[i].textContent || "").replace(/\s+/g, " ").trim();
				if (t === "Apps" || t.indexOf("Apps") === 0) return b[i];
			}
			return null;
		}
		function isNear(tr, fr) {
			var x = S.x, y = S.y;
			var inTrig = x >= tr.left - 24 && x <= tr.right + 28 && y >= tr.top - 24 && y <= tr.bottom + 24;
			var inFly = fr && x >= fr.left - 14 && x <= fr.right + 40 && y >= fr.top - 40 && y <= fr.bottom + 40;
			return inTrig || inFly;
		}
		function fire(el, type) {
			if (!el) return;
			el.dispatchEvent(new MouseEvent(type, { bubbles: true }));
			if (el.parentElement) el.parentElement.dispatchEvent(new MouseEvent(type, { bubbles: true }));
		}
		function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } S.outMs = 0; }
		function tick() {
			var trig = trigger();
			if (!trig) {
				// No "Apps" trigger in the DOM: the dropdown closed, a switcher-less SPA
				// armed us via an unrelated popover, or a non-English tenant. Tolerate a
				// TRANSIENT miss (mid reka re-render) but guarantee the timer STOPS
				// instead of polling forever — advance the exit counter, tear down after
				// the grace. (Without this the 30ms interval leaks for the whole session.)
				S.outMs += STEP;
				if (S.outMs >= GRACE) stop();
				return;
			}
			var fly = flyout();
			var tr = trig.getBoundingClientRect();
			var fr = fly ? fly.getBoundingClientRect() : null;
			if (isNear(tr, fr)) {
				S.outMs = 0;
				fire(trig, "mouseover"); // hold it open
			} else {
				S.outMs += STEP;
				// Stop only after a sustained exit — never on one transient miss (that's
				// what let dropped frames mid-move close it). mouseleave lets it close.
				if (S.outMs >= GRACE) { fire(trig, "mouseleave"); stop(); }
			}
		}
		function start() { if (!S.timer) { S.outMs = 0; S.timer = setInterval(tick, STEP); } }
		_nxApps = { start: start };
		start();
	}

	// The SPA app-switcher flyout shows BOTH frappe-ui's hard-coded "Desk" entry
	// AND the erpnext app's own get_apps entry (branded "Nexum Air", route /desk).
	// Both land on the same desk launcher — a genuine duplicate (owner-flagged,
	// v16-prod-134). Hide the hard-coded "Desk" one and keep the branded entry.
	// FAIL-SAFE: only hide when the same flyout ALSO contains another desk-routing
	// link with a different label (the Nexum Air entry) — never remove the only
	// path back to the desk (e.g. a user whose permissions hide the erpnext entry).
	// NOTE: the flyout container varies per frappe-ui version — some SPAs portal it
	// as [data-slot="content"], Drive's portals a bare <div> — so detection is
	// anchor-first: find the "Desk" link, then walk up to the switcher list around
	// it (an ancestor holding >=2 icon links) and look for the branded entry there.
	function _path(a) {
		return (a.getAttribute("href") || "").split("?")[0].replace(/\/+$/, "");
	}
	// The hard-coded "Desk" entry's route varies per app/frappe-ui version:
	// /app, /desk, or /desk/<its-own-workspace> (lms -> /desk/learning,
	// helpdesk -> /desk/helpdesk). Accept the whole family for the Desk link…
	function _deskRoute(a) {
		var path = _path(a);
		return path === "/app" || path === "/desk" || path.indexOf("/desk/") === 0;
	}
	// …but the branded entry that justifies hiding it must be the erpnext
	// get_apps entry itself (launcher route exactly), not another /desk/* link.
	function _launcherRoute(a) {
		var path = _path(a);
		return path === "/app" || path === "/desk";
	}
	function hideDuplicateDeskEntry() {
		var anchors = document.querySelectorAll("a[href]");
		for (var i = 0; i < anchors.length; i++) {
			var a = anchors[i];
			if (a.getAttribute("data-nx-desk-hidden")) continue;
			if ((a.textContent || "").replace(/\s+/g, " ").trim() !== "Desk") continue;
			if (!_deskRoute(a)) continue;
			// find the surrounding switcher list: nearest ancestor with >=2 icon links
			var box = a.parentElement;
			var depth = 0;
			while (box && depth < 5 && box.querySelectorAll("a img").length < 2) {
				box = box.parentElement;
				depth++;
			}
			if (!box || box === document.body || box === document.documentElement) continue;
			var links = box.querySelectorAll("a[href]");
			var brandLink = null;
			for (var j = 0; j < links.length; j++) {
				var other = links[j];
				if (other === a || !_launcherRoute(other)) continue;
				if ((other.textContent || "").replace(/\s+/g, " ").trim() !== "Desk") {
					brandLink = other;
					break;
				}
			}
			if (brandLink) {
				a.setAttribute("data-nx-desk-hidden", "1");
				// Hide the switcher CELL, not just the anchor: grid-style flyouts (LMS)
				// wrap each tile, so display:none on the inner <a> leaves an empty
				// grid slot and the first row renders with a hole. Walk up to the
				// direct child of the switcher container and hide that — but only
				// when it wraps this link alone (list-style flyouts where the anchor
				// IS the direct child keep the old behavior).
				var cell = a;
				while (cell.parentElement && cell.parentElement !== box) cell = cell.parentElement;
				var target = cell !== a && cell.querySelectorAll("a[href]").length === 1 ? cell : a;
				target.style.display = "none";
			}
		}
	}

	// frappe/lms hard-codes its app-switcher "Desk" link to `/desk/learning` (its
	// OWN desk workspace — the tile the desk launcher labels "Learning Admin"),
	// unlike every other app whose "Desk" goes to `/app` (the Nexum Air home grid).
	// So from the Learning app, "Desk" drops you into Learning Admin instead of the
	// home launcher. Repoint it to /app to match the other apps. Scoped naturally —
	// only LMS emits a /desk/learning link.
	function fixLmsDeskLink() {
		var links = document.querySelectorAll('a[href="/desk/learning"]');
		for (var i = 0; i < links.length; i++) links[i].setAttribute("href", "/app");
	}

	function start() {
		// one full initial pass
		try {
			ensureLogos();
			ensureLegacyInsightsLogo();
			brandTitle();
			ensureFavicon();
			brandSubtree(document.body);
			ensureBackButton();
			fixLmsDeskLink();
			hideDuplicateDeskEntry();
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
			var sawPopover = false;
			for (var i = 0; i < mutations.length; i++) {
				var added = mutations[i].addedNodes;
				for (var j = 0; j < added.length; j++) {
					try {
						brandSubtree(added[j]);
						// A popover/dropdown just mounted — the Apps switcher lives in one.
						// Arm the keep-alive THIS tick (not on the 250ms debounce) so it's
						// holding the flyout before the cursor starts to cross.
						var n = added[j];
						if (
							n.nodeType === 1 &&
							(n.matches && n.matches('[data-slot="content"]')
								? true
								: n.querySelector && n.querySelector('[data-slot="content"]'))
						) {
							sawPopover = true;
						}
					} catch (e) {
						/* ignore */
					}
				}
			}
			if (sawPopover) {
				try { nxAppsFlyoutKeepAlive(); } catch (e) { /* ignore */ }
				try { fixLmsDeskLink(); } catch (e) { /* ignore */ }
				try { hideDuplicateDeskEntry(); } catch (e) { /* ignore */ }
			}
			// Logos + title: a debounced light pass (cheap selector + title check).
			if (pending) return;
			pending = setTimeout(function () {
				pending = null;
				try {
					ensureLogos();
					ensureLegacyInsightsLogo();
					brandTitle();
					ensureFavicon();
					ensureBackButton();
					fixLmsDeskLink();
					hideDuplicateDeskEntry();
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
