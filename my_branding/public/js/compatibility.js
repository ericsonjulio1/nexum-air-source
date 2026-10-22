// Frappe compatibility adapters. Presentation code stays in brand.js.
// One idempotent interface installs all adapters in dependency order; a named
// adapter can also be installed independently by a page or behavior test.
// Do not copy these patches into callers. Preserve scripts/UX-CONTRACT.md.
(function () {
    if (window.NexumCompatibility) return;
    var installed = new Set();
    var adapters = {
        bootDocuments: function () {
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
        },
        sidebar: function () {
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
        },
        chartPalette: function () {
// Shared report palette, installed before the chart bundle assigns its class.

	function wrap(Orig) {
		if (typeof Orig !== "function" || Orig.__nexumPatched) return Orig;
		function NexumChart(element, options) {
			try {
				if (options && options.type !== "heatmap") {
					options = window.NexumCharts?.frappeOptions(options) || options;
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
        },
        tables: function () {
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
        },
        maintenanceBreadcrumb: function () {
// EAM/Maintenance breadcrumb: our Maintenance doctypes are surfaced inside the Assets
// workspace but belong to the "EAM" module, which Frappe doesn't map to a workspace — so
// opening one from Assets drops the "Assets" breadcrumb (leaving only the Home icon).
// Map EAM -> Assets in module_wise_workspaces so the clickable "Assets" crumb stays, like
// native Asset doctypes. (Lives here because my_branding's brand.js is the app-wide desk
// script that's reliably served; eam has no /assets symlink.)

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
        },
        accountSidebar: function () {
// Page-type routes (Chart of Accounts / Chart of Cost Centers) carry no sidebar
// context of their own: the "Accounts Setup" sidebar they render under is passed
// by the LINK that opens them (frappe.route_options.sidebar). A naked arrival —
// deep link, awesomebar, set_route — leaves the WHOLE sidebar (and therefore the
// crumb) stuck on whatever workspace the user came from (2026-07-25 nav sweep:
// from Website you get a Website sidebar on the Chart of Accounts). Claim the
// proper sidebar for these routes whenever it didn't come along.

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
        },
        breadcrumbSync: function () {
// The breadcrumb's workspace crumb can freeze on the PREVIOUS context: core
// appends it from `frappe.app.sidebar.sidebar_title` at breadcrumb-update time,
// which runs BEFORE the sidebar's own route handler has switched — so landing on
// the Company list from the launcher showed crumb "Stock" beside a correctly
// switched "Organization" sidebar (owner video, 2026-07-24). Re-sync the crumb
// to the settled sidebar title on a rAF-coalesced observer tick; strict no-op
// when they already agree. (Upstream class name really is "worksapce-breadcrumb".)

	// Modern Framework owns page-scoped trails through navigation.js. Do not
	// register a whole-body observer whose every scheduled pass would be a no-op.
	if (frappe.boot?.module_sidebars) return;
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
        },
        chartSizing: function () {
// Frappe chart terminal x-axis label overlap — frappe-charts 2.0.0-rc27's
// src/js/utils/axis-chart-utils.js:100-134 getShortenedLabels blanks interior
// labels on a stride, but line 124 force-draws the FINAL label without checking
// its proximity to the last kept stride label; line 128's guard only covers
// stride-skipped labels, not that forced terminal one. With 31 daily points at
// about 800px chart width and a stride of 4, index 28 is kept and index 30 is
// force-drawn only ~52px later even though the label is ~70px wide, so they
// overlap. Every workspace, dashboard, and query-report chart rendered through
// frappe.Chart shares this path. Fix rendered x-axis text after render/resize,
// and size bars before animation: no chart data, tooltip, legend, or y-axis changes.
// This wrapper composes with the Nexum Air palette wrap above.

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
	// the label fix): solid report fills with rounded bars, a 2px
	// surface gap between donut/pie slices, 3px line weight, subtle area
	// fills. Style/attribute writes ONLY — the shared MutationObserver watches
	// childList, so these mutations can never re-trigger it (no loop). Heatmaps
	// keep their gradient (untouched: their cells are rect.day, not rect.bar).
	// Charts with only 1-3 categories (e.g. an annual roll-up) get slab-wide bars
	// from frappe-charts' fill-the-space sizing — owner: "very unprofessional".
	// Native sizing below handles AxisChart before animation. Keep this DOM cap
	// as a backstop for the first chart's zero-data draw and non-AxisChart bars;
	// re-centering preserves the tooltip's slot center, and capped bars are a no-op.
	var MAX_BAR_WIDTH = 56;
	function capBarWidth(chart) {
		try {
			var proto = chart && Object.getPrototypeOf(chart);
			if (!proto || proto.__nxBarWidthPatched || typeof proto.calcXPositions !== "function") return;
			var calc = proto.calcXPositions;
			proto.calcXPositions = function () {
				var result = calc.apply(this, arguments);
				try {
					var s = this.state, options = this.barOptions;
					if (!s || !isFinite(s.unitWidth) || s.unitWidth <= 0 || !options) return result;
					// Keep the author's floor once per options object, not our last computed
					// ratio: a narrower container must be able to return to native spacing.
					if (!Object.prototype.hasOwnProperty.call(options, "__nxSpaceRatio")) {
						Object.defineProperty(options, "__nxSpaceRatio", { value: options.spaceRatio });
					}
					var datasets = (this.data && this.data.datasets) || [], bars = 0;
					for (var i = 0; i < datasets.length; i++) {
						if (datasets[i] && datasets[i].chartType === "bar") bars++;
					}
					bars = options.stacked ? 1 : Math.max(1, bars);
					// rc27 reads this before every draw/update, including the animated SVG.
					// A .95 ceiling still exceeds 56px in a stacked slot wider than 1120px;
					// allow the computed ratio up to 1, retaining narrower author settings.
					options.spaceRatio = Math.min(1, Math.max(
						options.__nxSpaceRatio || 0.5, 1 - MAX_BAR_WIDTH * bars / s.unitWidth));
				} catch (e) {
					/* never block a chart from rendering */
				}
				return result;
			};
			proto.__nxBarWidthPatched = true;
		} catch (e) {
			/* never block a chart from rendering */
		}
	}

	function restyleMarks(container) {
		try {
			var i, el, fill, w;
			var bars = container.querySelectorAll("svg rect.bar");
			for (i = 0; i < bars.length; i++) {
				el = bars[i];
				fill = el.style.fill || el.getAttribute("fill");
				if (!fill || fill === "none") continue;
				el.style.fillOpacity = "1";
				el.style.stroke = fill;
				el.style.strokeWidth = "0px";
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
				el.style.fillOpacity = "1";
				el.style.stroke = "var(--card-bg, var(--bg-color, #ffffff))";
				el.style.strokeWidth = "2px";
			}
			var lines = container.querySelectorAll("svg path.line-graph-path");
			for (i = 0; i < lines.length; i++) {
				lines[i].style.strokeWidth = "3px";
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
				chart.__nxLabelObserver = null;
				chart.__nxLabelResizeListener = null;
			};

			var run = function () {
				if (stopped) return;
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
			// Widget refresh/replacement calls the native chart lifecycle. Release our
			// own observers there too, without waiting for a later window resize.
			var destroy = chart.destroy;
			chart.destroy = function () {
				stop();
				if (typeof destroy === "function") return destroy.apply(this, arguments);
			};
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
			capBarWidth(chart);
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
			// desk.bundle defines this subclass before app_include_js, capturing the
			// old constructor. Its first chart must not depend on another chart's patch.
			if (frappe.ui && frappe.ui.RealtimeChart) {
				frappe.ui.RealtimeChart = wrap(frappe.ui.RealtimeChart);
			}
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
        },
        balanceSheet: function () {
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
        },
        reportFilters: function () {
// Report presets for simple mode (UX plan 2026-08-23, step 3). On Free/Essentials
// (frappe.boot.nx_simple_mode) the financial statements default to the current fiscal
// year by MONTH, and the power-user filters (Finance Book, Cost Center, Project, Report
// Template, presentation currency…) sit behind a "More filters" link instead of walling
// the report. Wraps QueryReport.setup_filters; Business/Enterprise and "Show advanced
// fields" users get the stock bar. Auto-expands when a hidden filter has a value,
// including one a drill-down sets through route_options after the bar is built
// (QueryReport.set_route_filters is wrapped to look again).
// -----------------------------------------------------------------------------

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
        },
    };
    window.NexumCompatibility = Object.freeze({
        install: function (name) {
            var names = name ? [name] : Object.keys(adapters);
            names.forEach(function (key) {
                if (!Object.prototype.hasOwnProperty.call(adapters, key)) throw new Error("Unknown Nexum compatibility adapter: " + key);
                if (installed.has(key)) return;
                adapters[key]();
                installed.add(key);
            });
        }
    });
})();
