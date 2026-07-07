// Entry point to the visual invoice designer, right on the Sales Invoice form.
// Routes to the Print Designer editor with the branded "Invoice Design"
// format (created per-tenant by invoicing.ensure_invoice_design). Two gates:
//   - print_designer installed (Free-tier sites don't ship it);
//   - System Manager role — the print-designer desk Page and Print Format
//     write perms are SM-only, so for anyone else the button would land on
//     a "Not permitted" wall (the 2026-07-04 demo-user report).
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (!frappe.boot.versions || !frappe.boot.versions.print_designer) return;
		if (!frappe.user.has_role("System Manager")) return;
		frm.add_custom_button(__("Invoice Design"), () => {
			frappe.set_route("print-designer", "Invoice Design");
		});
	},
});
