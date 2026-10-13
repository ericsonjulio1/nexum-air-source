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
				if (hadController) {
					// A SW controlled this page and may have already served stale
					// bundles/API data — reload ONCE to discard them. The latch is
					// per (re)appearance of a controller: cleared below whenever no SW
					// controls the page, so a SW that RE-registers later (e.g. a second
					// visit to Slides) still gets its own one-shot reload instead of
					// being permanently suppressed by a stale latch.
					if (!sessionStorage.getItem("nx_sw_cleared")) {
						try { sessionStorage.setItem("nx_sw_cleared", "1"); } catch (e) {}
						location.reload();
					}
				} else {
					try { sessionStorage.removeItem("nx_sw_cleared"); } catch (e) {}
				}
			});
		}).catch(function () {});
	} catch (e) {}
})();

// --- Home KPI widgets: docs from boot ------------------------------------------
// NumberCardWidget and CustomBlockWidget call frappe.model.with_doc() once per render,
// which sends a getdoc unless the doc AND its docinfo are already loaded, so every KPI
// value and the checklist waited a full round trip after the workspace (batch 205 idx
// 94). Boot carries the docs this user may read (my_branding.home.boot_widget_docs):
// a widget's FIRST with_doc for each is answered from them. Only a widget's: the
// widgets call with_doc with no callback, while the form view always passes one, and
// no docinfo is faked, so a form opened on a card (even as the first page loaded)
// fetches as usual. A form must never open on an empty docinfo: its timeline,
// assignments and @mentions need one.
(function () {
	try {
		var docs = window.frappe && frappe.boot && frappe.boot.nx_widget_docs;
		if (!docs || !docs.length || !frappe.model || !frappe.model.sync || !frappe.model.with_doc) return;
		frappe.model.sync(docs);
		var pending = {};
		docs.forEach(function (d) {
			pending[d.doctype + "\u0000" + d.name] = true;
		});
		var with_doc = frappe.model.with_doc;
		frappe.model.with_doc = function (doctype, name, callback) {
			var key = doctype + "\u0000" + (name || doctype);
			var route = (frappe.get_route && frappe.get_route()) || [];
			if (pending[key] && !callback && route[0] !== "Form" && locals[doctype] && locals[doctype][name]) {
				delete pending[key];
				return Promise.resolve(frappe.get_doc(doctype, name));
			}
			return with_doc.apply(this, arguments);
		};
	} catch (e) {
		/* the widgets fetch their docs themselves, as before */
	}
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
	// 2026-08-29 professional restyle (owner: charts read "elementary" — wants a
	// restrained, monotone-leaning look). Slate-teal leads and slot 2 stays in the
	// blue family, so the 1-2-series charts that dominate the desk read monotone;
	// warm accents only appear from slot 3 (donuts / multi-series). Both lists are
	// VALIDATED with the dataviz six-checks script (OKLCH lightness band, chroma
	// floor >= 0.10, adjacent-pair CVD + normal-vision separation, contrast) — the
	// old #2E5562 brand slate FAILS the chroma floor (C 0.049 reads gray), which
	// is why slot 1 is a chroma-corrected slate-teal, not the raw brand hex. Dark
	// is its own selected list (dark band L 0.48-0.67), not a flip. Change these
	// only with a re-run of the validator.
	var PALETTE_LIGHT = ["#007096", "#67b5e1", "#bf9840", "#20947d", "#375998", "#af6340"];
	var PALETTE_DARK = ["#006f96", "#4b9ad0", "#af892e", "#20947d", "#4567a8", "#af6340"];
	function palette() {
		var dark = false;
		try {
			dark = document.documentElement.getAttribute("data-theme") === "dark";
		} catch (e) {
			/* never block a chart from rendering */
		}
		return (dark ? PALETTE_DARK : PALETTE_LIGHT).slice();
	}
	function wrap(Orig) {
		if (typeof Orig !== "function" || Orig.__nexumPatched) return Orig;
		function NexumChart(element, options) {
			try {
				if (options && options.type !== "heatmap") {
					options.colors = palette();
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
//
// The same prototype patch also re-fits the table body on container WIDTH changes
// (v16-prod-199). frappe-datatable binds its own window-resize handler only for
// layout:'fluid' (style.js bindResizeWindow) and every desk report is
// layout:'fixed', so a table rendered on the MacBook screen and then dragged to a
// wider external display kept its .dt-scrollable at the old pixel width: the
// header and the newly exposed month columns filled the extra space while the
// body — and its vertical scrollbar — stopped mid-page until a reload (owner
// screenshot, P&L Monthly, 2026-09-16). A ResizeObserver on the wrapper catches
// display moves, sidebar toggles and full-width toggles alike. It reacts to width
// only (setBodyStyle itself changes the wrapper's HEIGHT, which must not re-fire
// it) and never runs while the page is hidden (a display:none wrapper measures 0
// and would pin the body to 0px). Hooked at setDimensions, which runs at the end
// of the constructor and on every refresh(), so late-constructed tables get it.
(function () {
	function observeWidth(inst) {
		if (inst.__nxWidthObs || !inst.style || !inst.datatableWrapper) return;
		if (inst.options && inst.options.layout === "fluid") return; // library handles fluid
		var el = inst.datatableWrapper;
		var lastWidth = el.clientWidth;
		var timer = null;
		var obs = new ResizeObserver(function () {
			var w = el.clientWidth;
			if (!w || w === lastWidth) return;
			lastWidth = w;
			clearTimeout(timer);
			timer = setTimeout(function () {
				try {
					if (!el.isConnected || !el.clientWidth) return;
					inst.style.setBodyStyle();
				} catch (e) {
					/* a failed re-fit must never break the table */
				}
			}, 120);
		});
		obs.observe(el);
		inst.__nxWidthObs = obs;
		var destroy = inst.destroy;
		if (typeof destroy === "function") {
			inst.destroy = function () {
				try {
					obs.disconnect();
				} catch (e) {}
				return destroy.apply(this, arguments);
			};
		}
	}
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
		var setDimensions = Cls.prototype.setDimensions;
		if (setDimensions && typeof ResizeObserver === "function") {
			Cls.prototype.setDimensions = function () {
				var r = setDimensions.apply(this, arguments);
				try {
					observeWidth(this);
				} catch (e) {}
				return r;
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
		// v184 (owner videos 2026-08-25 + 2026-08-26): INSIDE the Maintenance
		// workspace world, home = Maintenance home, not the launcher — a
		// technician working the CMMS expects the house to stay in the CMMS
		// (report pages carry no workspace crumb, so the house was their only
		// way "up" and it ejected them to the app grid). Detection is the
		// CURRENT sidebar title — live context at click time, deliberately NOT
		// the stale localStorage memory that v136 removed (owner video
		// 2026-07-24: home resurrected a weeks-old HR workspace). Already ON
		// the Maintenance home, the house stays the escape hatch to the
		// launcher.
		try {
			var sidebarTitle = (frappe.app && frappe.app.sidebar
				&& (frappe.app.sidebar.current_module || frappe.app.sidebar.sidebar_title)) || "";
			var onMaintenanceHome = /^\/desk\/maintenance\/?$/.test(
				window.location.pathname);
			if (/^maintenance$/i.test(String(sidebarTitle).trim()) && !onMaintenanceHome) {
				if (frappe.router && frappe.router.push_state) {
					frappe.router.push_state("/desk/maintenance");
				} else {
					window.location.assign("/desk/maintenance");
				}
				return;
			}
		} catch (err) {
			/* fall through to the launcher on any detection failure */
		}
		// v136+: everywhere else, home goes to the BRANDED LAUNCHER,
		// deterministically. The previous behavior (restore
		// localStorage.current_page via the Workspaces page — v117/v118) could
		// resurrect a workspace the user last touched weeks ago: owner video
		// 2026-07-24 showed home landing on a stale HR "Expense Claims"
		// workspace under a "Setup" sidebar — chaos for tenants. When v117
		// shipped, the alternative was the ugly legacy grid; since the
		// v128-131 sectioned launcher, the grid IS the product's curated home,
		// so send home there. The empty route resolves through
		// bootinfo.home_page ("desktop") -> the launcher grid, same as every
		// other back-to-apps affordance.
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
			if (!sb || (sb.current_module || sb.sidebar_title) === want) return;
			// only when that sidebar actually exists in this site's boot payload
			if (!(frappe.boot.module_sidebars?.[want] || frappe.boot.workspace_sidebar_item?.[want.toLowerCase()])) return;
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
		// Modern Framework owns a separate trail per page; navigation.js decorates it.
		if (frappe.boot?.module_sidebars) return;
		try {
			var sb = frappe.app && frappe.app.sidebar;
			var title = sb && (sb.current_module || sb.sidebar_title);
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

	// 2026-08-29 professional mark treatment (rides the same settled-frame pass as
	// the label fix): translucent fills with a solid same-hue edge on bars, a 2px
	// surface gap between donut/pie slices, 2px line weight, whisper-light area
	// fills. Style/attribute writes ONLY — the shared MutationObserver watches
	// childList, so these mutations can never re-trigger it (no loop). Heatmaps
	// keep their gradient (untouched: their cells are rect.day, not rect.bar).
	// Charts with only 1-3 categories (e.g. an annual roll-up) get slab-wide bars
	// from frappe-charts' fill-the-space sizing — owner: "very unprofessional".
	// Cap the mark width and re-center it in its slot; the slot center is what
	// tooltips key on, so hover is unaffected. Idempotent: a capped bar is under
	// the cap on the next pass and is left alone.
	var MAX_BAR_WIDTH = 56;
	function restyleMarks(container) {
		try {
			var i, el, fill, w;
			var bars = container.querySelectorAll("svg rect.bar");
			for (i = 0; i < bars.length; i++) {
				el = bars[i];
				fill = el.style.fill || el.getAttribute("fill");
				if (!fill || fill === "none") continue;
				el.style.fillOpacity = "0.55";
				el.style.stroke = fill;
				el.style.strokeWidth = "1.25px";
				el.setAttribute("rx", "2");
				w = parseFloat(el.getAttribute("width"));
				if (w > MAX_BAR_WIDTH) {
					el.setAttribute("x", String(
						parseFloat(el.getAttribute("x") || "0") + (w - MAX_BAR_WIDTH) / 2));
					el.setAttribute("width", String(MAX_BAR_WIDTH));
				}
			}
			var pies = container.querySelectorAll(
				"svg path[class*='pie'], svg .dataset-pies path");
			for (i = 0; i < pies.length; i++) {
				el = pies[i];
				fill = el.style.fill || el.getAttribute("fill");
				if (!fill || fill === "none") continue;
				el.style.fillOpacity = "0.8";
				el.style.stroke = "var(--card-bg, var(--bg-color, #ffffff))";
				el.style.strokeWidth = "2px";
			}
			var lines = container.querySelectorAll("svg path.line-graph-path");
			for (i = 0; i < lines.length; i++) {
				lines[i].style.strokeWidth = "2px";
			}
			var regions = container.querySelectorAll("svg .region-fill");
			for (i = 0; i < regions.length; i++) {
				regions[i].style.fillOpacity = "0.12";
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
					// On a page Frappe has hidden (display:none) every label measures as a
					// zero rect, so the pass would only hide them all, once per resize per
					// hidden chart. Skip it, as frappe-charts skips its own hidden redraws;
					// its redraw on show re-runs this pass through the observer.
					if (container.offsetParent === null) return;
					fixLabels(container);
					restyleMarks(container);
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

			// frappe-charts mounts its hover tooltip (.graph-svg-tip) inside this same
			// container and rewrites it on every mousemove, which re-ran the whole pass
			// (a forced layout plus every mark) each frame while hovering. Labels and
			// marks only change when the svg is redrawn: ignore tooltip-only batches.
			observer = new MutationObserver(function (records) {
				try {
					for (var r = 0; r < records.length; r++) {
						var target = records[r].target;
						if (!(target && target.closest && target.closest(".graph-svg-tip"))) {
							schedule();
							return;
						}
					}
				} catch (e) {
					schedule();
				}
			});
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

// -----------------------------------------------------------------------------
// Balance Sheet chart: composition columns instead of three unrelated lines.
// erpnext's Balance Sheet report ships a chart of three independent series
// (Assets / Liabilities / Equity as lines when "Accumulated Values" is on) — trend
// only, and the accounting identity is invisible. Re-shape it client-side (wrap of
// QueryReport.get_chart_options, Balance Sheet only) into ONE stacked column per
// period: Liabilities + Equity + Provisional P/L (= Assets − L − E, the unclosed
// period result erpnext leaves out of the Equity row), so the column height IS
// Total Assets and the composition is readable. Note: frappe-charts 2.0.0-rc27 sums
// every dataset (a line included) for the stacked y-range, so a "bars + assets
// line" mixed chart cannot share one correct scale — hence the derived 3rd segment
// rather than an overlay line. Any other report / unexpected shape passes through.
// -----------------------------------------------------------------------------
(function () {
	var SERIES = { assets: /^assets?$/i, liabilities: /^liabilit/i, equity: /^equity$/i };

	function pick(datasets, re) {
		for (var i = 0; i < datasets.length; i++) {
			if (re.test(String(datasets[i].name || "").trim())) return datasets[i];
		}
		return null;
	}

	function reshape(opts) {
		if (!opts || !opts.data || !Array.isArray(opts.data.datasets) || opts.data.datasets.length !== 3) return opts;
		var ds = opts.data.datasets;
		var a = pick(ds, SERIES.assets), l = pick(ds, SERIES.liabilities), e = pick(ds, SERIES.equity);
		if (!a || !l || !e) return opts;
		// bars first (stack order: liabilities at the base, equity on top), line last
		// frappe-charts (rc27) sums EVERY dataset — a line included — for the stacked
		// y-range, so "stacked bars + assets line" cannot share one correct scale. Use the
		// accounting identity instead: Liabilities + Equity + Provisional P/L (the unclosed
		// period result erpnext leaves out of the Equity row) stacks to EXACTLY Total Assets,
		// so the column height IS the asset total and the composition is readable.
		var pl = a.values.map(function (v, k) {
			return Math.round(((+v || 0) - (+l.values[k] || 0) - (+e.values[k] || 0)) * 100) / 100;
		});
		opts.data.datasets = [
			{ name: l.name, values: l.values },
			{ name: e.name, values: e.values },
			{ name: __("Provisional P/L"), values: pl },
		];
		opts.type = "bar";
		opts.title = __("Column height = Total Assets");
		opts.barOptions = Object.assign({}, opts.barOptions || {}, { stacked: 1, spaceRatio: 0.5 });
		return opts;
	}

	function install() {
		var QR = frappe.views && frappe.views.QueryReport;
		if (!QR || !QR.prototype || QR.prototype.__nxBsChart) return !!(QR && QR.prototype && QR.prototype.__nxBsChart);
		var orig = QR.prototype.get_chart_options;
		if (typeof orig !== "function") return false;
		QR.prototype.get_chart_options = function (data) {
			var opts = orig.apply(this, arguments);
			try {
				if (this.report_name === "Balance Sheet") return reshape(opts);
			} catch (err) {
				/* never block a report from rendering */
			}
			return opts;
		};
		QR.prototype.__nxBsChart = true;
		return true;
	}

	if (!install()) {
		var n = 0;
		var t = setInterval(function () {
			if (install() || ++n > 100) clearInterval(t);
		}, 50);
	}
})();

// -----------------------------------------------------------------------------
// Launcher grid: full-width, fluid tiles (match the desktop app).
// frappe's /desk launcher renders `.icons` with hard-coded pixel columns
// (e.g. "127px 127px 127px 127px 127px 127px") computed in JS at load, inside a
// fixed ~880px `.icons-container` CENTERED in the full-width `.desktop-container`
// — so in a browser the tiles sit in a narrow centred block with a big empty
// left/right gutter. The macOS desktop app already fixes this with an injected
// stylesheet; this brings the SAME full-width fluid grid to the web desk (and
// makes the desktop inject redundant). Scoped to the MAIN launcher via the
// `>` direct-child chain so folder pop-ups / nested app launchers (which reuse
// `.icons` inside their own narrow modal) keep their native multi-column layout.
(function () {
	if (document.getElementById("nx-launcher-layout")) return;
	var css =
		".layout-main:has(.desktop-wrapper)," +
		".layout-main-section:has(.desktop-wrapper){max-width:none !important}" +
		".desktop-wrapper,.desktop-container,.desktop-container > .icons-container{" +
		"width:100% !important;max-width:none !important}" +
		".desktop-container > .icons-container > .icons{" +
		"width:100% !important;display:grid !important;gap:15px !important;" +
		"justify-content:stretch !important;" +
		"grid-template-columns:repeat(auto-fill,minmax(150px,1fr)) !important}";
	function add() {
		if (document.getElementById("nx-launcher-layout")) return;
		var s = document.createElement("style");
		s.id = "nx-launcher-layout";
		s.textContent = css;
		(document.head || document.documentElement).appendChild(s);
	}
	if (document.head) add();
	else document.addEventListener("DOMContentLoaded", add);
})();

// -----------------------------------------------------------------------------
// Owner-first Home / Getting-started checklists (UX plan 2026-08-23, steps 1 + 4).
// The Custom HTML Blocks my_branding.home reconciles into Home / Accounting / Selling /
// Stock are a bare `<div class="nx-checklist" data-checklist="…">` inside a shadow
// root; their tiny inline script calls window.NexumChecklist.mount(el). All rendering
// lives here so it ships versioned with brand.js. Data: my_branding.home.get_checklist.
// -----------------------------------------------------------------------------
(function () {
	var CSS =
		".nx-ck{font-family:inherit;border:1px solid var(--border-color,#dce7eb);border-radius:14px;" +
		"background:var(--card-bg,#fff);padding:16px 18px;margin:0 0 6px}" +
		".nx-ck-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}" +
		".nx-ck-title{font-size:15px;font-weight:700;color:var(--text-color,#1c2b30);margin:0}" +
		".nx-ck-sub{font-size:12.5px;color:var(--text-muted,#5c7079);margin:2px 0 0}" +
		".nx-ck-count{font-size:12px;font-weight:600;color:var(--text-color,#2E5562);white-space:nowrap}" +
		".nx-ck-bar{height:6px;border-radius:999px;background:var(--control-bg,#edf3f5);margin:12px 0 14px;overflow:hidden}" +
		".nx-ck-bar>span{display:block;height:100%;border-radius:999px;" +
		"background:linear-gradient(90deg,#557E94,#2E5562);transition:width .3s}" +
		".nx-ck-steps{list-style:none;margin:0;padding:0;display:grid;gap:8px;" +
		"grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}" +
		".nx-ck-step{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:10px;" +
		"border:1px solid var(--border-color,#dce7eb);background:var(--fg-color,#fff);cursor:pointer;" +
		"transition:border-color .15s,transform .15s}" +
		".nx-ck-step:hover{border-color:#557E94;transform:translateY(-1px)}" +
		".nx-ck-step.done{opacity:.72;cursor:default}.nx-ck-step.done:hover{transform:none;border-color:var(--border-color,#dce7eb)}" +
		".nx-ck-dot{flex:0 0 22px;width:22px;height:22px;border-radius:50%;border:2px solid #9DBEC8;display:grid;" +
		"place-items:center;font-size:12px;font-weight:700;color:var(--text-color,#2E5562);margin-top:1px}" +
		".nx-ck-step.done .nx-ck-dot{background:#2E5562;border-color:#2E5562;color:#fff}" +
		".nx-ck-lbl{font-size:13px;font-weight:600;color:var(--text-color,#1c2b30);line-height:1.3}" +
		".nx-ck-step.done .nx-ck-lbl{text-decoration:line-through;font-weight:500}" +
		".nx-ck-help{font-size:12px;color:var(--text-muted,#5c7079);margin-top:2px;line-height:1.35}" +
		".nx-ck-acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}" +
		".nx-ck-acts a{font-size:11.5px;font-weight:600;color:#2E5562;text-decoration:none;border:1px solid #9DBEC8;" +
		"border-radius:999px;padding:2px 9px}.nx-ck-acts a:hover{background:#2E5562;color:#fff;border-color:#2E5562}" +
		".nx-ck-foot{display:flex;justify-content:flex-end;margin-top:10px}" +
		".nx-ck-hide{font-size:12px;color:var(--text-muted,#5c7079);background:none;border:0;cursor:pointer;padding:0}" +
		".nx-ck-hide:hover{color:#2E5562;text-decoration:underline}" +
		".nx-ck.complete{padding:12px 18px}.nx-ck.complete .nx-ck-title{font-size:14px}";
	// Theme: the panel uses frappe's own tokens (--card-bg/--text-color/--border-color/
	// --control-bg) which inherit INTO the shadow root and already flip with the desk
	// theme, so no data-theme sniffing/snapshot class is needed (that went stale when the
	// user switched theme after mount).

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	function go(route) {
		if (!route) return;
		if (Array.isArray(route)) return frappe.set_route.apply(frappe, route);
		if (typeof route === "string" && route.charAt(0) === "/") window.location.href = route;
		else frappe.set_route(route);
	}

	function render(el, data) {
		var root = el.getRootNode && el.getRootNode();
		var isShadow = root && root.host;
		if (isShadow && !root.querySelector("style[data-nx-ck]")) {
			var st = document.createElement("style");
			st.setAttribute("data-nx-ck", "1");
			st.textContent = CSS;
			root.appendChild(st);
		} else if (!isShadow && !document.getElementById("nx-ck-style")) {
			var st2 = document.createElement("style");
			st2.id = "nx-ck-style";
			st2.textContent = CSS;
			document.head.appendChild(st2);
		}
		if (!data || data.hidden) {
			el.innerHTML = "";
			el.closest && (function () {
				// collapse the widget box entirely when hidden for this user
				try {
					var host = root && root.host;
					var widget = host && host.closest(".widget");
					if (widget) widget.style.display = "none";
				} catch (e) {}
			})();
			return;
		}
		var pct = data.total ? Math.round((data.done / data.total) * 100) : 0;
		var h = '<div class="nx-ck' + (data.complete ? " complete" : "") + '">';
		h += '<div class="nx-ck-head"><div><p class="nx-ck-title">' + esc(data.title) + "</p>";
		if (data.subtitle && !data.complete) h += '<p class="nx-ck-sub">' + esc(data.subtitle) + "</p>";
		if (data.complete) h += '<p class="nx-ck-sub">' + esc(__("All done — you're set up.")) + "</p>";
		h += '</div><span class="nx-ck-count">' + data.done + " / " + data.total + "</span></div>";
		if (!data.complete) {
			h += '<div class="nx-ck-bar"><span style="width:' + pct + '%"></span></div>';
			h += '<ul class="nx-ck-steps">';
			data.steps.forEach(function (s, i) {
				h += '<li class="nx-ck-step' + (s.done ? " done" : "") + '" data-key="' + esc(s.key) + '">';
				h += '<span class="nx-ck-dot">' + (s.done ? "✓" : i + 1) + "</span><div>";
				h += '<div class="nx-ck-lbl">' + esc(s.label) + "</div>";
				if (s.help) h += '<div class="nx-ck-help">' + esc(s.help) + "</div>";
				if (!s.done && s.actions && s.actions.length) {
					h += '<div class="nx-ck-acts">';
					s.actions.forEach(function (a, j) {
						h += '<a href="#" data-act="' + j + '">' + esc(a.label) + "</a>";
					});
					h += "</div>";
				}
				h += "</div></li>";
			});
			h += "</ul>";
		}
		h += '<div class="nx-ck-foot"><button type="button" class="nx-ck-hide">' +
			esc(data.complete ? __("Hide") : __("Hide this panel")) + "</button></div></div>";
		el.innerHTML = h;

		function visit(step) {
			if (step.kind === "visit" && !step.done) {
				frappe.xcall("my_branding.home.mark_visited", { name: data.name, key: step.key }).catch(function () {});
			}
		}
		el.querySelectorAll(".nx-ck-step").forEach(function (li) {
			var step = data.steps.filter(function (s) { return s.key === li.getAttribute("data-key"); })[0];
			if (!step) return;
			li.querySelectorAll("a[data-act]").forEach(function (a) {
				a.addEventListener("click", function (ev) {
					ev.preventDefault();
					ev.stopPropagation();
					visit(step);
					go(step.actions[+a.getAttribute("data-act")].route);
				});
			});
			li.addEventListener("click", function () {
				if (step.done && step.kind !== "visit") return;
				visit(step);
				go(step.route);
			});
		});
		var hide = el.querySelector(".nx-ck-hide");
		hide && hide.addEventListener("click", function () {
			frappe.xcall("my_branding.home.hide_checklist", { name: data.name }).then(function () {
				var boot = frappe.boot && frappe.boot.nx_checklists;
				if (boot && Array.isArray(boot.hidden) && boot.hidden.indexOf(data.name) < 0) boot.hidden.push(data.name);
				render(el, { hidden: 1 });
			});
		});
	}

	// Boot already knows when the server could only answer "hidden" (no panel role,
	// mature Enterprise site, or hidden by this user): skip that round trip.
	function hiddenAtBoot(name) {
		var boot = frappe.boot && frappe.boot.nx_checklists;
		if (!boot) return false;
		return !!boot.off || (Array.isArray(boot.hidden) && boot.hidden.indexOf(name) >= 0);
	}

	function mount(el) {
		if (!el || !window.frappe || !frappe.xcall) return;
		var name = el.getAttribute("data-checklist");
		if (!name) return;
		if (hiddenAtBoot(name)) {
			render(el, { hidden: 1, name: name });
			return;
		}
		frappe
			.xcall("my_branding.home.get_checklist", { name: name })
			.then(function (data) { render(el, data); })
			.catch(function () { el.innerHTML = ""; });
	}

	window.NexumChecklist = { mount: mount, render: render };
})();

// -----------------------------------------------------------------------------
// Report presets for simple mode (UX plan 2026-08-23, step 3). On Free/Essentials
// (frappe.boot.nx_simple_mode) the financial statements default to the current fiscal
// year by MONTH, and the power-user filters (Finance Book, Cost Center, Project, Report
// Template, presentation currency…) sit behind a "More filters" link instead of walling
// the report. Wraps QueryReport.setup_filters; Business/Enterprise and "Show advanced
// fields" users get the stock bar. Auto-expands when a hidden filter has a value,
// including one a drill-down sets through route_options after the bar is built
// (QueryReport.set_route_filters is wrapped to look again).
// -----------------------------------------------------------------------------
(function () {
	var PRESET_REPORTS = {
		"Profit and Loss Statement": { periodicity: "Monthly" },
		"Balance Sheet": { periodicity: "Monthly" },
		"Cash Flow": { periodicity: "Monthly" },
		"Trial Balance": {},
		"General Ledger": {},
		"Accounts Receivable": {},
		"Accounts Payable": {},
		"Accounts Receivable Summary": {},
		"Accounts Payable Summary": {},
		"Gross Profit": {},
		"Sales Register": {},
		"Purchase Register": {},
	};
	var ADVANCED = [
		"finance_book", "cost_center", "project", "selected_view", "report_template",
		"presentation_currency", "include_default_book_entries", "show_zero_values",
		"include_dimensions", "show_net_values_in_party_account", "add_values_in_transaction_currency",
		"ignore_err", "ignore_cr_dr_notes", "show_cancelled_entries", "show_opening_entries",
		"categorize_by", "group_by", "show_remarks", "based_on_payment_terms", "show_future_payments",
		"show_delivery_notes", "show_sales_person", "show_gl_balance", "in_party_currency",
		"handle_employee_advances", "territory", "sales_partner", "sales_person", "payment_terms_template",
		"customer_group", "supplier_group", "include_uom", "brand", "branch", "department",
		"against_voucher_no",
	];
	var ESSENTIAL_KEEP = ["company", "from_date", "to_date", "period_start_date", "period_end_date",
		"from_fiscal_year", "to_fiscal_year", "filter_based_on", "periodicity", "accumulated_values",
		"report_date", "ageing_based_on", "range", "range1", "range2", "range3", "range4", "item_code"];

	function simple() {
		return !!(window.frappe && frappe.boot && cint(frappe.boot.nx_simple_mode));
	}

	function install() {
		var QR = frappe.views && frappe.views.QueryReport;
		if (!QR || !QR.prototype || QR.prototype.__nxPresets) return !!(QR && QR.prototype && QR.prototype.__nxPresets);
		var orig = QR.prototype.setup_filters;
		if (typeof orig !== "function") return false;
		QR.prototype.setup_filters = function () {
			var me = this;
			var preset = simple() ? PRESET_REPORTS[this.report_name] : null;
			try {
				if (preset && this.report_settings && Array.isArray(this.report_settings.filters)) {
					this.report_settings.filters.forEach(function (df) {
						if (df && preset[df.fieldname] !== undefined && !df.__nxOrigDefault) {
							df.__nxOrigDefault = df.default === undefined ? null : df.default;
							df.default = preset[df.fieldname];
						}
					});
				}
			} catch (e) { /* presets are best-effort */ }
			me.__nxAdvRecheck = null; // set again by applyMoreFilters for this filter bar
			var out = orig.apply(this, arguments);
			try {
				if (preset) applyMoreFilters(me);
			} catch (e2) { /* never break a report */ }
			return out;
		};
		// refresh_report runs setup_filters FIRST and set_route_filters after it, so a
		// drill-down's values (cost_center, project, finance_book, …) land after the row
		// decided to stay collapsed: applied, yet hidden. Look again once they are set.
		var origRoute = QR.prototype.set_route_filters;
		if (typeof origRoute === "function") {
			QR.prototype.set_route_filters = function () {
				var me = this;
				var out = origRoute.apply(this, arguments);
				try {
					Promise.resolve(out).then(function () {
						if (typeof me.__nxAdvRecheck === "function") me.__nxAdvRecheck();
					}).catch(function () { /* the report handles its own errors */ });
				} catch (e) { /* never break a report */ }
				return out;
			};
		}
		QR.prototype.__nxPresets = true;
		return true;
	}

	function norm(v) {
		if (Array.isArray(v)) return v.length ? JSON.stringify(v) : "";
		if (v === undefined || v === null || v === false || v === 0 || v === "0") return "";
		return String(v);
	}

	// "has a value" = differs from the filter's own default (a checked-by-default box or
	// a default Select option must not pop the advanced row open)
	function hasValue(f) {
		try {
			return norm(f.get_value()) !== norm(f.df && f.df.default);
		} catch (e) { return false; }
	}

	function applyMoreFilters(report) {
		var filters = report.filters || [];
		var adv = filters.filter(function (f) {
			var fn = f.df && f.df.fieldname;
			if (!fn || ESSENTIAL_KEEP.indexOf(fn) !== -1) return false;
			return ADVANCED.indexOf(fn) !== -1;
		});
		if (!adv.length) return;
		var $form = report.page.page_form;
		$form.find(".nx-more-filters").remove();
		var open = adv.some(hasValue);
		var $btn = $('<button type="button" class="btn btn-xs nx-more-filters" style="margin:auto 0 6px 4px;white-space:nowrap;' +
			'color:#2E5562;background:transparent;border:1px dashed #9DBEC8;border-radius:999px;padding:2px 10px;font-weight:600"></button>');
		function paint() {
			adv.forEach(function (f) { $(f.wrapper).toggleClass("nx-adv-hidden", !open); });
			// a collapsed row still says when hidden filters are narrowing the report
			var active = adv.filter(hasValue).length;
			$btn.text(open ? __("Fewer filters") : __("More filters") + " (" + adv.length + ")" +
				(active ? " · " + __("{0} active", [active]) : ""));
		}
		$btn.on("click", function () { open = !open; paint(); });
		paint();
		$form.append($btn);
		// called after route filters land (see set_route_filters above): open the row
		// when one of them set a hidden filter; never collapse what the user opened
		report.__nxAdvRecheck = function () {
			try {
				if (!open && adv.some(hasValue)) open = true;
				paint();
			} catch (e) { /* never break a report */ }
		};
		if (!document.getElementById("nx-adv-filter-css")) {
			var st = document.createElement("style");
			st.id = "nx-adv-filter-css";
			st.textContent = ".page-form .nx-adv-hidden{display:none !important}";
			document.head.appendChild(st);
		}
	}

	if (!install()) {
		var n = 0;
		var t = setInterval(function () {
			if (install() || ++n > 100) clearInterval(t);
		}, 50);
	}
})();

// -----------------------------------------------------------------------------
// Bare-root landing (2026-08-23 follow-up). The desktop app (and anyone typing the
// domain) opens the bare `/`. For a logged-in system user frappe renders the DESK at
// `/` without redirecting, and the desk router treats "/" as the launcher — so the
// owner-first Home workspace (User.default_workspace=Home, set by
// branding.ensure_owner_landing) only applied to the post-login redirect. Route the
// bare root to the user's default workspace once, client-side. `/desk` typed
// explicitly is left alone (that IS the launcher).
// -----------------------------------------------------------------------------
(function () {
	function go() {
		try {
			if (location.pathname !== "/" || !window.frappe || !frappe.boot || !frappe.boot.user) return false;
			var ws = frappe.boot.user.default_workspace;
			if (!ws) return true; // nothing to do, stop polling
			var name = typeof ws === "string" ? ws : ws.name || ws.title;
			if (!name || !frappe.router || !frappe.set_route) return false;
			var slug = frappe.router.slug(name);
			frappe.set_route(ws.public === 0 || ws.public === false ? "private/" + slug : slug);
			return true;
		} catch (e) {
			return true;
		}
	}
	if (!go()) {
		var n = 0;
		var t = setInterval(function () {
			if (go() || ++n > 100) clearInterval(t);
		}, 50);
	}
})();
