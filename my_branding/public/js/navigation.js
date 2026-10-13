// Keep the ratified home/workspace trail on Framework's page-scoped breadcrumbs.
// Older Framework versions render that trail themselves and need no adapter.
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
