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

// Desk-launcher tiles swallow "jittery" clicks: each tile is an `<a draggable>`
// anchor managed by the grid's drag-to-reorder (SortableJS, native HTML5 mode),
// and the browser starts a drag — cancelling the click outright — once the
// pointer travels ~4px between mousedown and mouseup. Wireless/Bluetooth mice
// routinely drift that much during a normal click, so tiles intermittently
// "do nothing". A timed guard (drags allowed only after a 300ms hold) still
// swallowed slow drifting clicks — a press held past the window with ≥4px of
// drift died exactly like before. Since the launcher order is centrally
// reconciled (LAUNCHER_SECTIONS + reconcile_desktop_icon_order re-stamp idx on
// every migrate), a user drag-reorder is overwritten on the next deploy anyway,
// so drag-to-reorder is disabled on tiles outright: every press releases as an
// ordinary click.
(function () {
	document.addEventListener(
		"dragstart",
		function (e) {
			try {
				if (e.target && e.target.closest && e.target.closest(".desktop-container .desktop-icon")) {
					e.preventDefault();
				}
			} catch (err) {
				/* never let this break a drag */
			}
		},
		true
	);
})();

// Desk sidebar opens the wrong workspace (e.g. a report under Assets showing the
// Website/Framework sidebar): frappe v16 Sidebar.resolve_sidebar() rule 2 trusts
// localStorage.sidebar_item_map[entity][0] — a per-browser remembered choice —
// UNCONDITIONALLY, without checking that the remembered sidebar still links the
// entity at all; and store_last_show_sidebar_for_item() only ever appends, so
// the oldest (possibly stale/corrupt) entry wins forever. Sanitize on every
// resolve: keep only remembered sidebars that are real candidates for the
// entity (per get_workspace_sidebars), dedupe, and write the pruned map back —
// this also self-heals browsers already carrying a poisoned entry. When the
// entity has no candidates at all, stock behavior is left untouched.
(function () {
	function wrap() {
		var S = frappe.ui && frappe.ui.Sidebar;
		if (!S || !S.prototype || !S.prototype.resolve_sidebar || S.prototype.__nxSidebarSanitized) {
			return !!(S && S.prototype && S.prototype.__nxSidebarSanitized);
		}
		var orig = S.prototype.resolve_sidebar;
		S.prototype.resolve_sidebar = function (entity, module) {
			try {
				var raw = JSON.parse(localStorage.getItem("sidebar_item_map") || "{}");
				var entry = raw[entity];
				if (entry && entry.length) {
					var candidates = this.get_workspace_sidebars(entity) || [];
					if (candidates.length) {
						var valid = [];
						entry.forEach(function (s) {
							if (candidates.indexOf(s) !== -1 && valid.indexOf(s) === -1) valid.push(s);
						});
						if (valid.length !== entry.length) {
							if (valid.length) raw[entity] = valid;
							else delete raw[entity];
							localStorage.setItem("sidebar_item_map", JSON.stringify(raw));
						}
					}
				}
			} catch (err) {
				/* sanitizing is best-effort; never block sidebar resolution */
			}
			return orig.call(this, entity, module);
		};
		S.prototype.__nxSidebarSanitized = true;
		return true;
	}
	if (!wrap()) {
		var tries = 0;
		var t = setInterval(function () {
			if (wrap() || ++tries > 50) clearInterval(t);
		}, 200);
	}
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

// Frozen first column on wide report tables — Balance Sheet / P&L / GL and every
// other datatable-backed grid scrolls horizontally, and the row's identity (the
// Account / ID column) scrolls away with it, so users lose track of which row a
// number belongs to. frappe-datatable 1.20.4 already ships full sticky-column
// machinery (column.sticky -> .dt-cell--sticky, position:sticky + cumulative left
// offsets recomputed on resize in setStickyColumnStyle) — it's just only applied
// to the internal checkbox/serial columns by default. We turn it on for the FIRST
// visible data column of every table.
//
// Hook point: every desk grid is constructed from a class that some bundle assigns
// to `window.DataTable` (query_report.js, report_view.js) or `frappe.DataTable`
// (ui/datatable.js) — patching that CLASS's prototype covers even call sites that
// hold the module-scope binding (report_view's `new DataTable(...)` is the same
// class object it assigns to window). Two prototype methods need the mark:
//   - buildOptions(options): runs inside the constructor with the raw options
//   - refresh(data, columns): query_report re-runs pass freshly built column
//     objects here on every filter change, which would otherwise drop the flag
// Same intercept-the-assignment pattern as the frappe.Chart palette wrap above,
// because these bundles load lazily (report bundle only on first report route).
// Respect an explicit author choice: if any column is already marked sticky we
// leave the table alone.
(function () {
	function markSticky(columns) {
		if (!Array.isArray(columns) || columns.length < 2) return;
		for (var i = 0; i < columns.length; i++) {
			if (columns[i] && columns[i].sticky) return; // report author already chose
		}
		for (var j = 0; j < columns.length; j++) {
			var c = columns[j];
			if (c && !c.hidden) {
				c.sticky = true;
				return;
			}
		}
	}
	function patch(Cls) {
		if (typeof Cls !== "function" || !Cls.prototype || Cls.__nxStickyPatched) return Cls;
		var buildOptions = Cls.prototype.buildOptions;
		if (buildOptions) {
			Cls.prototype.buildOptions = function (options) {
				try {
					// 'fluid' layout hides horizontal overflow entirely — sticky
					// could never engage, so don't add the pinned-edge shadow there.
					if (options && options.layout !== "fluid") markSticky(options.columns);
				} catch (e) {
					/* never block a table from rendering */
				}
				return buildOptions.apply(this, arguments);
			};
		}
		var refresh = Cls.prototype.refresh;
		if (refresh) {
			Cls.prototype.refresh = function (data, columns) {
				try {
					if (!this.options || this.options.layout !== "fluid") markSticky(columns);
				} catch (e) {}
				return refresh.apply(this, arguments);
			};
		}
		Cls.__nxStickyPatched = true;
		return Cls;
	}
	function hook(obj, prop) {
		try {
			var stored = obj[prop];
			if (stored) patch(stored);
			Object.defineProperty(obj, prop, {
				configurable: true,
				enumerable: true,
				get: function () {
					return stored;
				},
				set: function (v) {
					stored = patch(v);
				},
			});
		} catch (e) {}
	}
	hook(window, "DataTable");
	if (window.frappe) hook(window.frappe, "DataTable");
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

// Desk breadcrumb "home" icon -> last-viewed workspace.
// frappe.breadcrumbs.clear() (frappe/public/js/frappe/views/breadcrumbs.js) always
// re-renders the crumb bar with a bare `<a href="/desk">` (the home icon) as its
// FIRST element, on every route change. A plain click on that anchor is caught by
// the global delegated click-handler in router.js (`$("body").on("click", "a", ...)`),
// which sees `is_app_route("/desk")` === true (router.js `is_app_route`: path
// segment "desk") and calls `frappe.set_route("/desk")`. `get_route_from_arguments`
// strips the leading "desk" segment, leaving an EMPTY route, so `router.render()`
// falls to `frappe.views.pageview.show("")` -> `name = frappe.boot.home_page`
// (pageview.js ~line 52). Site default `desktop:home_page` is "workspace", which
// `frappe/boot.py::add_home_page` can't resolve (no Page doc named "workspace" /
// "Workspaces" exists), so core's fallback lands `bootinfo.home_page = "desktop"`
// — the legacy app-icon grid, not the last-viewed workspace.
//
// We used to fix this by force-overriding `bootinfo.home_page = "Workspaces"`
// server-side (my_branding/boot.py, commit 019ea2b). That's a GLOBAL override:
// every other "back to app grid" affordance also resolves through the same empty
// route + bootinfo.home_page fallback (the workspace sidebar's "Desktop" dropdown
// item, every frappe-ui SPA's "Desk" switcher, spa-brand.js ensureBackButton(),
// fixLmsDeskLink()) — so it silently hijacked ALL of them into the Workspaces UI
// too. Reverted; fixed instead with a scoped client-side intercept, ONLY on this
// one anchor, that skips the empty-route/home_page fallback entirely:
// `frappe.set_route("Workspaces")` builds the URL "/desk/Workspaces" (router.js
// `convert_from_standard_route` leaves an unrecognised first segment like
// "Workspaces" untouched, since it only special-cases List/Form/Tree views), which
// `convert_to_standard_route` also leaves unrecognised (frappe.workspaces keys are
// always lowercase-slugged by `frappe.router.slug()`, so it can never collide with
// the literal "Workspaces"), so `render_page()` calls
// `pageview.show("Workspaces")` -> `frappe.standard_pages["Workspaces"]` (registered
// unconditionally by frappe/public/js/frappe/views/workspace/workspace.js:4,
// regardless of bootinfo.home_page) -> its `get_page_to_show()` (~line 137)
// restores `localStorage.current_page`, the user's last-viewed workspace. Same
// desired destination, without touching bootinfo or any other back-to-grid path.
(function () {
	function onBreadcrumbHomeClick(e) {
		// Respect modified clicks / non-primary buttons (open-in-new-tab etc.) —
		// let the browser's native handling take over, same as router.js's own
		// delegated click-handler does for ctrlKey/metaKey.
		if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) {
			return;
		}
		var a = e.target && e.target.closest && e.target.closest('.navbar-breadcrumbs a[href="/desk"]');
		if (!a) return;
		e.preventDefault();
		e.stopPropagation();
		// v136+: home goes to the BRANDED LAUNCHER, deterministically. The previous
		// behavior (restore localStorage.current_page via the Workspaces page —
		// v117/v118) could resurrect a workspace the user last touched weeks ago:
		// owner video 2026-07-24 showed home landing on a stale HR "Expense Claims"
		// workspace under a "Setup" sidebar — chaos for tenants. When v117 shipped,
		// the alternative was the ugly legacy grid; since the v128-131 sectioned
		// launcher, the grid IS the product's curated home, so send home there.
		// The empty route resolves through bootinfo.home_page ("desktop") -> the
		// launcher grid, same as every other back-to-apps affordance.
		frappe.set_route("");
	}
	// Delegated on document (breadcrumbs.clear() empties + re-appends the anchor
	// on every route change, so a direct listener on the element would be lost;
	// capture phase so we run before router.js's own delegated "a" click-handler
	// on `body`, which would otherwise treat this as a plain "/desk" navigation).
	document.addEventListener("click", onBreadcrumbHomeClick, true);
})();

// Page-type routes (Chart of Accounts / Chart of Cost Centers) carry no sidebar
// context of their own: the "Accounts Setup" sidebar they render under is passed
// by the LINK that opens them (frappe.route_options.sidebar). A naked arrival —
// deep link, awesomebar, set_route — leaves the WHOLE sidebar (and therefore the
// crumb) stuck on whatever workspace the user came from (2026-07-25 nav sweep:
// from Website you get a Website sidebar on the Chart of Accounts). Claim the
// proper sidebar for these routes whenever it didn't come along.
(function () {
	var PAGE_SIDEBARS = {
		"chart-of-accounts": "Accounts Setup",
		"chart-of-cost-centers": "Accounts Setup",
	};
	function fix() {
		try {
			var r = frappe.get_route ? frappe.get_route() : null;
			var want = r && r.length === 1 && PAGE_SIDEBARS[r[0]];
			if (!want) return;
			var sb = frappe.app && frappe.app.sidebar;
			if (!sb || sb.sidebar_title === want) return;
			// only when that sidebar actually exists in this site's boot payload
			if (!frappe.boot.workspace_sidebar_item || !frappe.boot.workspace_sidebar_item[want.toLowerCase()]) return;
			sb.setup(want);
		} catch (e) {
			/* cosmetic — never break navigation */
		}
	}
	function arm() {
		try {
			frappe.router.on("change", function () {
				setTimeout(fix, 300);
			});
			fix();
		} catch (e) {
			setTimeout(arm, 500);
		}
	}
	arm();
})();

// The breadcrumb's workspace crumb can freeze on the PREVIOUS context: core
// appends it from `frappe.app.sidebar.sidebar_title` at breadcrumb-update time,
// which runs BEFORE the sidebar's own route handler has switched — so landing on
// the Company list from the launcher showed crumb "Stock" beside a correctly
// switched "Organization" sidebar (owner video, 2026-07-24). Re-sync the crumb
// to the settled sidebar title on a rAF-coalesced observer tick; strict no-op
// when they already agree. (Upstream class name really is "worksapce-breadcrumb".)
(function () {
	var pending = null;
	function syncCrumb() {
		pending = null;
		try {
			var sb = frappe.app && frappe.app.sidebar;
			var title = sb && sb.sidebar_title;
			if (!title) return;
			// The workspace crumb is built by DIFFERENT code paths per view type:
			// list/form views tag it `worksapce-breadcrumb` (upstream typo), but
			// page-type views (Chart of Accounts / Accounts Setup, ...) append a
			// bare classless <a href="#"> — so select by POSITION: the first
			// crumb anchor that isn't the home icon (href="/desk").
			var crumb = document.querySelector(".navbar-breadcrumbs a.worksapce-breadcrumb");
			if (!crumb) {
				var anchors = document.querySelectorAll(".navbar-breadcrumbs a");
				for (var i = 0; i < anchors.length; i++) {
					if (anchors[i].getAttribute("href") !== "/desk") {
						crumb = anchors[i];
						break;
					}
				}
				// only treat the positional match as a workspace crumb when its
				// text IS a known launcher-tile label — never rewrite a doctype
				// or record crumb that merely sits first.
				if (crumb && !frappe.utils.get_desktop_icon_by_label(crumb.textContent.trim())) return;
			}
			if (!crumb) return;
			var icon = frappe.utils.get_desktop_icon_by_label(title);
			var label = (icon && icon.label) || title;
			if (crumb.textContent.trim() !== label) {
				crumb.textContent = label;
				var url = icon && frappe.utils.get_route_for_icon(icon);
				if (url) crumb.setAttribute("href", url);
			}
		} catch (e) {
			/* cosmetic — never break navigation */
		}
	}
	function schedule() {
		if (!pending) pending = requestAnimationFrame(syncCrumb);
	}
	function arm() {
		try {
			new MutationObserver(schedule).observe(document.body, { subtree: true, childList: true });
		} catch (e) {
			/* ignore */
		}
	}
	if (document.body) arm();
	else document.addEventListener("DOMContentLoaded", arm);
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
	// The LMS ships two launcher tiles that both read "Learning": the app tile
	// "Frappe Learning" (-> /lms, the learner app, open-book icon) and its desk
	// WORKSPACE tile (-> /desk/lms-course, the course-admin/records view, given a
	// distinct records icon in brand.css). Their Desktop Icon label must stay
	// "Learning" for frappe's launcher to render the workspace tile at all, so we
	// relabel ONLY its visible caption here to "Learning Admin" to tell them apart.
	// Re-applied each sync so it survives the grid's re-renders.
	function relabelLearningAdminTile() {
		var el = document.querySelector('.desktop-container .desktop-icon[data-id="Learning"]');
		if (!el) return;
		// Target .icon-title specifically: in frappe's desktop-icon DOM it is the
		// INNER text node (child of the .icon-caption wrapper) that carries the
		// caption typography (weight/size/line-height + our gradient-clip color).
		// A comma-selector querySelector would return .icon-caption first (tree
		// order, ancestor first), and writing textContent on it would DESTROY the
		// inner .icon-title, orphaning a bare text node with none of that styling.
		var caption = el.querySelector(".icon-caption");
		var c = caption && caption.querySelector(".icon-title");
		if (!c) return;
		if (c.textContent.trim() !== "Learning Admin") {
			c.textContent = "Learning Admin";
			c.setAttribute("data-original-title", "Learning Admin");
		}
	}
	// The custom EAM app (meter-based preventive maintenance + spare parts, the
	// product differentiator) lives under the "Assets" workspace/tile. Its Desktop
	// Icon label must stay "Assets" — it's the ordering/linkage key read by
	// DESKTOP_ICON_ORDER in branding.py and by Frappe's own launcher-tile render
	// gating — so we relabel ONLY its visible caption here to "Assets &
	// Maintenance", same pattern as the Learning Admin tile above. Re-applied
	// each sync so it survives the grid's re-renders.
	function relabelAssetsTile() {
		var el = document.querySelector('.desktop-container .desktop-icon[data-id="Assets"]');
		if (!el) return;
		// Same .icon-caption > .icon-title targeting as relabelLearningAdminTile
		// above — never write textContent on the outer wrapper.
		var caption = el.querySelector(".icon-caption");
		var c = caption && caption.querySelector(".icon-title");
		if (!c) return;
		if (c.textContent.trim() !== "Assets & Maintenance") {
			c.textContent = "Assets & Maintenance";
			c.setAttribute("data-original-title", "Assets & Maintenance");
		}
	}
	// Section headers above the ratified 5-group launcher layout (Sales & Money,
	// Operations, Customers & Team, Files & Office, Administration). The backend
	// publishes the groupings as frappe.boot.nexumair_launcher_sections — an
	// ordered array of {title, labels:[...]} where each label is a Desktop Icon
	// label == the tile's data-id. Attribute-only: no nodes are ever inserted
	// into the sortable grid; we just tag tiles and let brand.css do the visuals
	// (SortableJS + the tile hit-targets stay untouched):
	//   - .nx-section-start + data-nx-section-title on the first tile of EVERY
	//     section -> grid-column:1 + a ::before floating label (lone-tile
	//     sections are labeled too — no tile-count gate);
	//   - .nx-row-head on a section-start's row-mates -> same margin-top, so
	//     the whole row shifts down uniformly instead of the marked tile
	//     drooping below its stretched row siblings.
	// Fail-open: a missing/empty boot key leaves the grid completely unmarked.
	function applyLauncherSectionHeaders() {
		// Idempotency: tiles get re-rendered and pager pages flipped between
		// syncs, so ALWAYS clear stale marks first — even when we end up not
		// re-marking below (boot key absent, grid gone, customized layout).
		// .nx-row-head is class-only (no attributes), so a plain
		// classList.remove clears it fully.
		var marked = document.querySelectorAll(".nx-section-start");
		for (var i = 0; i < marked.length; i++) {
			marked[i].classList.remove("nx-section-start");
			marked[i].removeAttribute("data-nx-section-title");
		}
		var rowMarked = document.querySelectorAll(".nx-row-head");
		for (var rm = 0; rm < rowMarked.length; rm++) {
			rowMarked[rm].classList.remove("nx-row-head");
		}
		var sections = null;
		try {
			sections = frappe.boot && frappe.boot.nexumair_launcher_sections;
		} catch (e) { sections = null; }
		if (!Array.isArray(sections) || !sections.length) return;
		// Anchor on the TOP-LEVEL launcher grid only: folder tiles render their
		// own nested .icons-container > .icons INSIDE a .desktop-icon, and folder
		// pop-ups reuse the same class names in a modal — the direct-child chain
		// structurally excludes both.
		var grid = document.querySelector(".desktop-container > .icons-container > .icons");
		if (!grid) return;
		// label -> its section's index (first occurrence wins), plus the
		// flattened canonical tile order — both derived fresh from the boot data
		// every call (no separate hardcoded copy to drift out of sync).
		var labelToSectionIndex = {};
		var canonicalOrder = [];
		for (var s = 0; s < sections.length; s++) {
			var labels = Array.isArray(sections[s] && sections[s].labels) ? sections[s].labels : [];
			for (var l = 0; l < labels.length; l++) {
				var label = labels[l];
				if (typeof label !== "string" || !label) continue;
				if (!Object.prototype.hasOwnProperty.call(labelToSectionIndex, label)) {
					labelToSectionIndex[label] = s;
					canonicalOrder.push(label);
				}
			}
		}
		// Only this grid's DIRECT-CHILD tiles, in DOM order, and only those on
		// the currently visible pager page — recomputed from the DOM every sync,
		// so paging needs no persisted state.
		var tiles = grid.querySelectorAll(":scope > .desktop-icon[data-id]");
		var visible = [];
		for (var t = 0; t < tiles.length; t++) {
			if (isVisible(tiles[t])) visible.push(tiles[t]);
		}
		// Canonical-order guard: if the known tiles' positions in the ratified
		// order are not strictly increasing in DOM order, the user has
		// drag-customized their layout and headers would lie — leave everything
		// unmarked (already cleared above, the correct no-headers state). Tiles
		// with unknown data-ids (custom/unlisted apps) are skipped, not breaks.
		var lastCanonical = -1;
		var qualifying = [];
		for (var v = 0; v < visible.length; v++) {
			var id = visible[v].getAttribute("data-id");
			if (!Object.prototype.hasOwnProperty.call(labelToSectionIndex, id)) continue;
			var ci = canonicalOrder.indexOf(id);
			if (ci <= lastCanonical) return;
			lastCanonical = ci;
			qualifying.push(visible[v]);
		}
		// Group by section preserving DOM order; mark the FIRST visible tile of
		// every section on this page with .nx-section-start +
		// data-nx-section-title (a labeled row header, ::before in CSS) —
		// lone-tile sections are labeled exactly like multi-tile ones.
		var seen = {};
		for (var q2 = 0; q2 < qualifying.length; q2++) {
			var si2 = labelToSectionIndex[qualifying[q2].getAttribute("data-id")];
			if (seen[si2]) continue;
			seen[si2] = true;
			qualifying[q2].classList.add("nx-section-start");
			qualifying[q2].setAttribute("data-nx-section-title", sections[si2].title || "");
		}
		// Row-mate pass: tag the tiles sharing a labeled section-start's grid
		// ROW with .nx-row-head so CSS gives them the same margin-top — the
		// whole row shifts down uniformly instead of the section-start tile
		// drooping 48px below its row siblings (grid align-items:stretch
		// stretches every tile in the row to the now-taller row track).
		// Column count comes from the RESOLVED gridTemplateColumns (a
		// space-separated list of track sizes) — one computed-style read, no
		// offsetTop/getBoundingClientRect layout probes and no class toggling
		// to measure. Walk the FULL visible array (not just `qualifying`):
		// unknown/custom tiles still occupy real grid cells and count as
		// row-mates. Stop the walk at any tile that itself forces a new row
		// (.nx-section-start sets grid-column:1) — it can never share the
		// earlier tile's row. Runs AFTER the marking loop above so the walk
		// sees the freshly applied classes.
		var columnCount = 0;
		try {
			var tracks = (window.getComputedStyle(grid).gridTemplateColumns || "").split(/\s+/);
			for (var tc = 0; tc < tracks.length; tc++) {
				if (tracks[tc]) columnCount++;
			}
		} catch (e) { columnCount = 0; }
		if (columnCount > 1) {
			for (var m = 0; m < visible.length; m++) {
				if (!visible[m].classList.contains("nx-section-start")) continue;
				var mates = 0;
				for (var k = m + 1; k < visible.length && mates < columnCount - 1; k++) {
					var mate = visible[k];
					if (mate.classList.contains("nx-section-start")) break;
					mate.classList.add("nx-row-head");
					mates++;
				}
			}
		}
	}
	// Same tile opened inside the desk: its workspace sidebar header renders the
	// workspace LABEL ("Learning"), which must stay "Learning" for the launcher to
	// keep showing the tile (see reconcile_lms_admin_workspace). So relabel just the
	// visible header text to "Learning Admin" too. Only the LMS module workspace is
	// named "Learning", so a text match is safe + self-scoping (fires only when
	// that workspace is the current one).
	function relabelLearningWorkspaceHeader() {
		var h = document.querySelector(".sidebar-header .header-title");
		if (h && h.textContent.trim() === "Learning") h.textContent = "Learning Admin";
	}
	function sync() {
		relabelLearningWorkspaceHeader(); // runs on every desk page (header is app-wide)
		var grid = document.querySelector(".desktop-container");
		if (isVisible(grid)) {
			document.body.classList.add("nx-desk-home");
			ensureGreeting(grid);
			relabelLearningAdminTile();
			relabelAssetsTile();
			applyLauncherSectionHeaders();
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
		// The launcher grid's columns are fluid (repeat(auto-fill, minmax(150px,1fr))),
		// so a pure window resize changes the column count — and therefore which
		// tiles are row-mates of a section header — WITHOUT any DOM mutation the
		// observer above would see. Re-run the SAME rAF-coalesced schedule() on
		// resize so .nx-row-head tags shrink/grow to match the new column count.
		// Safe: schedule() is single-flight (one sync per frame), so even a
		// resize-event storm coalesces — no layout thrash, and the marking pass
		// only toggles classes/attributes, which can trigger the MutationObserver
		// but converges immediately (same marks re-applied = no further change
		// beyond one extra no-op sync, and childList-only observation ignores
		// attribute changes anyway). No new observer/scheduler needed.
		window.addEventListener("resize", schedule, { passive: true });
	}
	if (document.readyState !== "loading") start();
	else document.addEventListener("DOMContentLoaded", start);
})();

// Frappe chart terminal x-axis label overlap — frappe-charts 2.0.0-rc27's
// src/js/utils/axis-chart-utils.js:100-134 getShortenedLabels blanks interior
// labels on a stride, but line 124 force-draws the FINAL label without checking
// its proximity to the last kept stride label; line 128's guard only covers
// stride-skipped labels, not that forced terminal one. With 31 daily points at
// about 800px chart width and a stride of 4, index 28 is kept and index 30 is
// force-drawn only ~52px later even though the label is ~70px wide, so they
// overlap. Every workspace, dashboard, and query-report chart rendered through
// frappe.Chart shares this path. Fix only the rendered x-axis text after render
// (and after resize): no chart data, tooltip, legend, or y-axis changes. This
// wrapper composes with, rather than replaces, the Nexum Air palette wrap above.
(function () {
	function fixLabels(container) {
		try {
			if (!container) return;
			// Restore our previous choices before measuring the freshly rendered
			// labels, so a resize can reveal labels that no longer collide.
			var hidden = container.querySelectorAll("[data-nx-label-hidden]");
			for (var h = 0; h < hidden.length; h++) {
				hidden[h].style.visibility = "";
				hidden[h].removeAttribute("data-nx-label-hidden");
			}

			var nodes = container.querySelectorAll(".x.axis > g > text");
			var labels = [];
			var rects = [];
			for (var i = 0; i < nodes.length; i++) {
				if ((nodes[i].textContent || "").trim()) {
					labels.push(nodes[i]);
					rects.push(nodes[i].getBoundingClientRect());
				}
			}
			if (labels.length < 2) return;

			// Walk from the forced terminal label towards the first label. The
			// terminal label is always kept; each earlier label is compared with
			// the nearest label already kept to its right.
			var lastKeptRect = rects[rects.length - 1];
			for (var j = labels.length - 2; j >= 1; j--) {
				var thisRect = rects[j];
				if (thisRect.right + 4 > lastKeptRect.left) {
					labels[j].style.visibility = "hidden";
					labels[j].setAttribute("data-nx-label-hidden", "1");
				} else {
					lastKeptRect = thisRect;
				}
			}
		} catch (e) {
			/* never block a chart from rendering */
		}
	}

	function attachLabelFix(chart) {
		var observer;
		var schedule;
		try {
			if (!chart || chart.__nxLabelObserver || !chart.container) return;
			var container = chart.container;
			var stopped = false;
			var scheduled = false;

			var stop = function () {
				if (stopped) return;
				stopped = true;
				try {
					if (observer) observer.disconnect();
				} catch (e) {
					/* never block a chart from rendering */
				}
				try {
					window.removeEventListener("resize", schedule);
				} catch (e) {
					/* never block a chart from rendering */
				}
			};

			var run = function () {
				try {
					if (
						!chart.container ||
						chart.container !== container ||
						!document.documentElement ||
						!document.documentElement.contains(container)
					) {
						stop();
						return;
					}
					fixLabels(container);
				} catch (e) {
					/* never block a chart from rendering */
				}
			};

			// Mutation churn and resize events share one settled-frame scheduler,
			// so at most one measurement/fix pass is pending at a time.
			schedule = function () {
				try {
					if (stopped || scheduled) return;
					scheduled = true;
					var raf = window.requestAnimationFrame || function (cb) { return setTimeout(cb, 16); };
					raf(function () {
						scheduled = false;
						run();
					});
				} catch (e) {
					scheduled = false;
					/* never block a chart from rendering */
				}
			};

			observer = new MutationObserver(schedule);
			observer.observe(container, { childList: true, subtree: true });
			window.addEventListener("resize", schedule);
			chart.__nxLabelObserver = observer;
			chart.__nxLabelResizeListener = schedule;
			schedule();
		} catch (e) {
			try {
				if (observer) observer.disconnect();
			} catch (ignored) {
				/* never block a chart from rendering */
			}
			try {
				window.removeEventListener("resize", schedule);
			} catch (ignored) {
				/* never block a chart from rendering */
			}
			/* never block a chart from rendering */
		}
	}

	function wrap(Orig) {
		if (typeof Orig !== "function" || Orig.__nxChartLabelPatched) return Orig;
		function NexumChartLabels() {
			// Function#bind is ES5's constructor-safe way to forward every argument
			// while preserving the inner constructor's normal `new` behaviour.
			var args = [null].concat(Array.prototype.slice.call(arguments));
			var Bound = Function.prototype.bind.apply(Orig, args);
			var chart = new Bound();
			try {
				attachLabelFix(chart);
			} catch (e) {
				/* never block a chart from rendering */
			}
			return chart;
		}
		NexumChartLabels.prototype = Orig.prototype;
		try {
			Object.keys(Orig).forEach(function (k) {
				NexumChartLabels[k] = Orig[k];
			});
		} catch (e) {
			/* never block a chart from rendering */
		}
		NexumChartLabels.__nxChartLabelPatched = true;
		return NexumChartLabels;
	}

	function install() {
		try {
			if (!window.frappe) return false;
			if (frappe.__nxChartLabelHook) return true;
			// The palette IIFE is earlier in this file. If neither its accessor nor
			// a loaded Chart exists yet, let the shared 50ms poll try again.
			if (!frappe.Chart && !frappe.__nexumChartHook) return false;

			var prior = Object.getOwnPropertyDescriptor(frappe, "Chart");
			var current = frappe.Chart;
			var stored = current;
			var usePriorGetter = !!(prior && prior.get);
			Object.defineProperty(frappe, "Chart", {
				configurable: true,
				enumerable: true,
				get: function () {
					try {
						return usePriorGetter ? prior.get.call(frappe) : stored;
					} catch (e) {
						/* never block a chart from rendering */
						return stored;
					}
				},
				set: function (v) {
					try {
						if (prior && prior.set) {
							// Let the palette accessor wrap first, then make its stored
							// constructor the inner constructor for this visual patch.
							prior.set.call(frappe, v);
							stored = wrap(prior.get ? prior.get.call(frappe) : v);
							prior.set.call(frappe, stored);
						} else {
							stored = wrap(v);
							usePriorGetter = false;
						}
					} catch (e) {
						/* never block a chart from rendering */
					}
				},
			});
			frappe.__nxChartLabelHook = true;
			// Feed an already-loaded constructor through the new outer accessor;
			// its setter then calls the palette accessor's setter, preserving both.
			if (current) frappe.Chart = current;
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
