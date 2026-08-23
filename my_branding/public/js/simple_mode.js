// Simple-mode toggle for Sales Invoice / Purchase Invoice / Payment Entry
// (UX plan 2026-08-23, step 2). On Free/Essentials the advanced header fields are gated
// by property setters `depends_on = eval:(!frappe.boot.nx_simple_mode || doc.<f>) && …`
// (see my_branding/simple_mode.py). This adds the per-user escape hatch to the form
// menu: "Show advanced fields" / "Use simple form". Business/Enterprise (nx_simple_plan
// = 0) get nothing — their form is the full ERPNext form already.
(function () {
	if (!window.frappe) return;

	function isSimplePlan() {
		return !!(frappe.boot && cint(frappe.boot.nx_simple_plan));
	}

	function simpleOn() {
		return !!(frappe.boot && cint(frappe.boot.nx_simple_mode));
	}

	function addToggle(frm) {
		if (!isSimplePlan()) return;
		const label = simpleOn() ? __("Show advanced fields") : __("Use simple form");
		// idempotent across refreshes: drop both variants before adding
		const both = [__("Show advanced fields"), __("Use simple form")];
		frm.page.menu
			.find("li")
			.filter((i, el) => both.includes($(el).text().trim()))
			.remove();
		frm.page.add_menu_item(label, () => {
			const on = simpleOn() ? 1 : 0; // currently simple -> turn advanced ON
			frappe
				.xcall("my_branding.plan.set_advanced_fields", { on })
				.then((r) => {
					frappe.boot.nx_simple_mode = r && r.nx_simple_mode ? 1 : 0;
					frm.refresh();
					frappe.show_alert({
						message: on ? __("Advanced fields shown") : __("Simple form restored"),
						indicator: "green",
					});
				})
				.catch(() => {});
		});
	}

	["Sales Invoice", "Purchase Invoice", "Payment Entry"].forEach((dt) => {
		frappe.ui.form.on(dt, {
			refresh(frm) {
				addToggle(frm);
			},
		});
	});
})();
