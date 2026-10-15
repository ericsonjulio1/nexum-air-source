// Keep the ratified home/workspace trail on Framework's page-scoped breadcrumbs.
// Older Framework versions render that trail themselves and need no adapter.
(function () {
	if (frappe.__nexumMaintenanceEntry) return;
	frappe.__nexumMaintenanceEntry = true;
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
		if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
		if (frappe.app?.sidebar?.current_module !== "Assets") return;
		const card = event.target.closest?.('[shortcut_name="Maintenance"] .widget');
		if (!card || card.closest(".edit-mode")) return;
		event.preventDefault();
		event.stopImmediatePropagation();
		frappe.set_route("maintenance");
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
