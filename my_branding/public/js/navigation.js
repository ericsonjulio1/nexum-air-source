// Keep the ratified home/workspace trail on Framework's page-scoped breadcrumbs.
// Older Framework versions render that trail themselves and need no adapter.
(function () {
	if (frappe.__nexumMaintenanceEntry) return;
	frappe.__nexumMaintenanceEntry = true;
	const sections = {
		"work-orders": "Work Orders",
		"pm-planning": "PM Planning",
		reports: "Reports",
		"spare-parts": "Spare Parts",
	};
	// Keep the persisted, editable workspace shortcut. Its rendered body provides
	// section links using the same markup as native link cards, without inventing
	// Page records or adding a second inventory/navigation model.
	const shortcutBlock = frappe.workspace_block?.blocks?.shortcut?.prototype;
	if (shortcutBlock?.render) {
		const render = shortcutBlock.render;
		shortcutBlock.render = function () {
			const wrapper = render.apply(this, arguments);
			if (!this.readOnly || this.data?.shortcut_name !== "Maintenance"
				|| frappe.workspace?._page?.name !== "Assets") return wrapper;
			const card = wrapper.querySelector(".widget");
			if (!card) return wrapper;
			card.classList.add("links-widget-box", "nx-maintenance-entry");
			card.setAttribute("role", "group");
			card.removeAttribute("tabindex");
			const title = card.querySelector(".widget-title");
			const home = document.createElement("a");
			home.href = "/desk/maintenance";
			home.textContent = title.textContent;
			home.className = "nx-maintenance-home";
			title.replaceChildren(home);
			const body = card.querySelector(".widget-body");
			body.replaceChildren();
			for (const [section, label] of Object.entries(sections)) {
				const link = document.createElement("a");
				link.href = "/desk/maintenance?section=" + section;
				link.className = "link-item";
				link.dataset.nexumMaintenanceSection = section;
				const content = document.createElement("span");
				content.className = "link-content";
				const text = document.createElement("span");
				text.className = "link-text";
				text.textContent = __(label);
				content.append(text);
				link.append(content);
				body.append(link);
			}
			return wrapper;
		};
	}

	// Scroll only when the requested card has actually rendered. No persistent
	// DOM observer or retry timer is needed; cached routes use the router event.
	let scrollFrame, awaitingAjax = false;
	const scrollToSection = () => {
		const label = sections[new URLSearchParams(window.location.search).get("section")];
		if (!label || frappe.workspace?._page?.name !== "Maintenance"
			|| frappe.app?.sidebar?.current_module !== "Maintenance") return;
		const card = [...frappe.workspace.wrapper[0].querySelectorAll("[card_name]")]
			.find(element => element.getAttribute("card_name") === label);
		const heading = card?.querySelector(".widget-title");
		if (!heading || card.closest(".edit-mode")) return;
		const header = frappe.workspace.wrapper[0].querySelector(".page-head");
		card.style.scrollMarginTop = ((header?.getBoundingClientRect().height || 0) + 16) + "px";
		card.scrollIntoView({ block: "start", behavior: "instant" });
		heading.setAttribute("tabindex", "-1");
		heading.focus({ preventScroll: true });
	};
	const scheduleSection = () => {
		if (scrollFrame) cancelAnimationFrame(scrollFrame);
		if (!sections[new URLSearchParams(window.location.search).get("section")] || awaitingAjax) return;
		// Number-card results can change the rows above the target. Wait for native
		// requests and their render microtasks before measuring the final layout.
		awaitingAjax = true;
		frappe.after_ajax(() => {
			awaitingAjax = false;
			scrollFrame = requestAnimationFrame(() => { scrollFrame = null; scrollToSection(); });
		});
	};
	const cardBlock = frappe.workspace_block?.blocks?.card?.prototype;
	if (cardBlock?.rendered) {
		const rendered = cardBlock.rendered;
		cardBlock.rendered = function () {
			const result = rendered.apply(this, arguments);
			if (frappe.workspace?._page?.name === "Maintenance") scheduleSection();
			return result;
		};
		frappe.router.on("change", scheduleSection);
	}
	// Framework injects Custom Documents / Reports after the last link card,
	// including empty placeholders. Keep the Assets doorway beside its two cards
	// after that injection; retain every custom card and tenant block.
	const workspace = frappe.views?.Workspace?.prototype;
	if (workspace?.add_custom_cards_in_content) {
		const addCustomCards = workspace.add_custom_cards_in_content;
		workspace.add_custom_cards_in_content = function () {
			const result = addCustomCards.apply(this, arguments);
			if (this._page?.name !== "Assets") return result;
			const index = this.content.findIndex(b => b.id === "eam-maintenance-entry");
			if (index < 0) return result;
			const [entry] = this.content.splice(index, 1);
			let anchor = -1;
			this.content.forEach((b, i) => {
				if (b.type === "card" && ["Asset Reports", "Setup"].includes(b.data?.card_name)) anchor = i;
			});
			this.content.splice(anchor < 0 ? index : anchor + 1, 0, entry);
			return result;
		};
	}
	// Native URL shortcuts always open a new window. This internal workspace
	// doorway follows the same in-place navigation as its sidebar counterpart.
	if (document.addEventListener) document.addEventListener("click", function (event) {
		if (frappe.app?.sidebar?.current_module !== "Assets") return;
		const card = event.target.closest?.('[shortcut_name="Maintenance"] .widget');
		if (!card || card.closest(".edit-mode")) return;
		const link = event.target.closest("a");
		// Let genuine anchors keep browser open-in-new-tab behavior, without the
		// parent URL shortcut also opening its generic destination.
		if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
			if (link) event.stopImmediatePropagation();
			return;
		}
		event.preventDefault();
		event.stopImmediatePropagation();
		frappe.set_route(link?.getAttribute("href") || "maintenance");
	}, true);

	const sidebarItem = frappe.ui.sidebar_item;
	if (!sidebarItem?.get_route) return;
	const getRoute = sidebarItem.get_route;
	sidebarItem.get_route = function (item, editMode, shell) {
		// This is an entry into the Maintenance module, not an Assets-owned page.
		// Keep the native Workspace link so server permission filtering still applies.
		if (!editMode && shell === "Assets" && item.type === "Link"
			&& item.link_type === "Workspace" && item.link_to === "Maintenance") {
			return "/desk/maintenance";
		}
		return getRoute.apply(this, arguments);
	};
})();

(function () {
	if (!frappe.boot?.module_sidebars || !frappe.ui.Page?.prototype.get_breadcrumbs) return;
	const Page = frappe.ui.Page.prototype;
	if (Page.__nexumNavigation) return;
	Page.__nexumNavigation = true;
	const getBreadcrumbs = Page.get_breadcrumbs;
	Page.get_breadcrumbs = function () {
		const items = getBreadcrumbs.call(this);
		if (this !== frappe.get_current_page() || this.show_breadcrumbs === false) return items;
		const shell = frappe.app?.sidebar?.current_module;
		const sidebar = frappe.boot.module_sidebars[shell];
		const title = sidebar?.label || __(shell || "");
		const prefix = [{ href: "/desk", prefix: "house", title: __("Home") }];
		if (shell === "Maintenance" && !items.some((item) => item.label === title)) {
			prefix.push({ label: title, href: "/desk/maintenance" });
		}
		return prefix.concat(items);
	};
	// Sidebar setup fires before it assigns current_module. Repaint after that assignment,
	// only on the visible page, so navigating cannot leave the previous module in the trail.
	const repaint = () => queueMicrotask(() => frappe.get_current_page()?.render_breadcrumbs());
	$(document).on("sidebar_setup", repaint);
	frappe.router.on("change", repaint);
	repaint();
})();
