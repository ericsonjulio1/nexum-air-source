// Install the version-sensitive framework adapters before presentation behavior.
try {
	if (window.NexumCompatibility) window.NexumCompatibility.install();
} catch (error) {
	// Keep presentation available if a framework adapter or its asset fails.
	console.warn("Nexum compatibility initialization failed", error);
}

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

// -----------------------------------------------------------------------------


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
