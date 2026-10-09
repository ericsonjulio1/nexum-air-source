"""Owner-first Home + per-module "Getting started" panels (UX plan 2026-08-23, steps 1 + 4).

What ships
----------
* Custom HTML Blocks ("Nexum Get Set Up" on Home; "Nexum Getting Started — Accounts /
  Selling / Stock" on those workspaces). The block HTML is a placeholder `div`; the
  rendering lives in brand.js (`window.NexumChecklist`) so it is versioned + cache-busted
  with the rest of the desk JS and the DB rows never need a content bump.
* 3 Custom Number Cards on Home (Receivables / Payables / Cash & Bank) backed by the
  whitelisted methods below, formatted in the company currency.
* `reconcile_home_workspace` (after_migrate): idempotent recompute-and-diff insert of
  the block + KPI row at the TOP of the standard Home workspace (core re-syncs it on
  bumps) and of the module blocks at the top of Accounting / Selling / Stock.

Checklist steps are self-checking: `kind="exists"` steps are live DB checks;
`kind="visit"` steps (open a report / review a screen) complete when the user clicks
through (per-user default). Frappe's own Module Onboarding / form tours stay OFF
(branding.reconcile_onboarding — ratified: they read as clutter on a provisioned site);
these panels are the deliberate replacement.
"""

import json

import frappe
from frappe import _

from my_branding.plan import get_plan

HOME_BLOCK = "Nexum Get Set Up"
# checklist key -> (candidate workspaces, first existing wins; block name). erpnext 16.32
# split the old "Accounting" workspace into Invoicing / Financial Reports / … — the
# Accounts panel lives on Invoicing (the accounting landing), older cohorts on Accounting.
MODULE_BLOCKS = {
	"accounts": (("Invoicing", "Accounting"), "Nexum Getting Started — Accounts"),
	"selling": (("Selling",), "Nexum Getting Started — Selling"),
	"stock": (("Stock",), "Nexum Getting Started — Stock"),
}


def module_workspace(key):
	"""The workspace that carries the `key` checklist on this site (None if absent)."""
	for ws in MODULE_BLOCKS[key][0]:
		if frappe.db.exists("Workspace", ws):
			return ws
	return None
NUMBER_CARDS = [
	# (name/label, method, document_type that gates read permission, route, route_options)
	("Receivables", "my_branding.home.receivables", "Sales Invoice"),
	("Payables", "my_branding.home.payables", "Purchase Invoice"),
	("Cash & Bank", "my_branding.home.cash_and_bank", "Payment Entry"),
]
_VISIT_KEY = "nx_ck:{name}:{key}"
_HIDE_KEY = "nx_ck_hidden:{name}"
# who sees the panels (owner-type roles; a Sales User on a Business tenant doesn't need
# "set up your company")
_PANEL_ROLES = {"System Manager", "Accounts Manager", "Sales Manager", "Stock Manager", "Purchase Manager"}


# --------------------------------------------------------------------------- helpers
def _company():
	c = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	if c and frappe.db.exists("Company", c):
		return c
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def _exists(doctype, filters=None):
	try:
		return bool(frappe.db.exists(doctype, filters or {}))
	except Exception:
		return False


def _company_details_done(company):
	if not company:
		return False
	row = frappe.db.get_value("Company", company, ["tax_id", "company_logo", "phone_no", "email"], as_dict=True) or {}
	if row.get("tax_id") or row.get("company_logo"):
		return True
	return _exists("Dynamic Link", {"link_doctype": "Company", "link_name": company, "parenttype": "Address"})


def _sales_tax_template_done(company):
	return _exists("Sales Taxes and Charges Template", {"company": company, "disabled": 0}) or _exists(
		"Item Tax Template", {"company": company, "disabled": 0}
	)


# --------------------------------------------------------------------------- checklists
def _checklists(company):
	"""Step specs per checklist. route = desk route list (frappe.set_route).

	`done` is a thunk: get_checklist evaluates only the requested checklist's steps,
	not the 14-18 existence queries behind all four (perf sweep 2026-10-02)."""
	return {
		"home": {
			"title": _("Get set up"),
			"subtitle": _("Three steps and you can send your first invoice."),
			"steps": [
				{
					"key": "company",
					"label": _("Confirm your company details"),
					"help": _("Name, TIN, address and logo go on every invoice."),
					"route": ["Form", "Company", company] if company else ["List", "Company"],
					"kind": "exists",
					"done": lambda: _company_details_done(company),
				},
				{
					"key": "customer_item",
					"label": _("Add your first customer and item"),
					"help": _("What you sell, and who you sell it to."),
					"route": ["List", "Customer"],
					"actions": [
						{"label": _("New Customer"), "route": ["Form", "Customer", "new"]},
						{"label": _("New Item"), "route": ["Form", "Item", "new"]},
					],
					"kind": "exists",
					"done": lambda: _exists("Customer") and _exists("Item", {"has_variants": 0}),
				},
				{
					"key": "invoice",
					"label": _("Issue your first Sales Invoice"),
					"help": _("Pick the customer, add the item, Save and Submit."),
					"route": ["Form", "Sales Invoice", "new"],
					"kind": "exists",
					"done": lambda: _exists("Sales Invoice", {"docstatus": 1}),
				},
			],
		},
		"accounts": {
			"title": _("Getting started with Accounting"),
			"subtitle": "",
			"steps": [
				{"key": "coa", "label": _("Review your Chart of Accounts"), "route": ["Tree", "Account"], "kind": "visit"},
				{
					"key": "tax",
					"label": _("Set up your sales tax (VAT) template"),
					"route": ["List", "Sales Taxes and Charges Template"],
					"kind": "exists",
					"done": lambda: _sales_tax_template_done(company),
				},
				{
					"key": "invoice",
					"label": _("Record your first Sales Invoice"),
					"route": ["Form", "Sales Invoice", "new"],
					"kind": "exists",
					"done": lambda: _exists("Sales Invoice", {"docstatus": 1}),
				},
				{
					"key": "payment",
					"label": _("Record a payment against it"),
					"route": ["Form", "Payment Entry", "new"],
					"kind": "exists",
					"done": lambda: _exists("Payment Entry", {"docstatus": 1}),
				},
				{"key": "bs", "label": _("Open your Balance Sheet"), "route": ["query-report", "Balance Sheet"], "kind": "visit"},
			],
		},
		"selling": {
			"title": _("Getting started with Selling"),
			"subtitle": "",
			"steps": [
				{"key": "customer", "label": _("Add a customer"), "route": ["Form", "Customer", "new"], "kind": "exists", "done": lambda: _exists("Customer")},
				{"key": "item", "label": _("Add an item you sell"), "route": ["Form", "Item", "new"], "kind": "exists", "done": lambda: _exists("Item", {"is_sales_item": 1, "has_variants": 0})},
				{"key": "quotation", "label": _("Send a Quotation"), "route": ["Form", "Quotation", "new"], "kind": "exists", "done": lambda: _exists("Quotation", {"docstatus": 1})},
				{"key": "so", "label": _("Confirm a Sales Order"), "route": ["Form", "Sales Order", "new"], "kind": "exists", "done": lambda: _exists("Sales Order", {"docstatus": 1})},
				{"key": "si", "label": _("Invoice it"), "route": ["Form", "Sales Invoice", "new"], "kind": "exists", "done": lambda: _exists("Sales Invoice", {"docstatus": 1})},
				{"key": "analytics", "label": _("Open Sales Analytics"), "route": ["query-report", "Sales Analytics"], "kind": "visit"},
			],
		},
		"stock": {
			"title": _("Getting started with Stock"),
			"subtitle": "",
			"steps": [
				{"key": "warehouse", "label": _("Review your warehouses"), "route": ["Tree", "Warehouse"], "kind": "visit"},
				{"key": "item", "label": _("Add a stock item"), "route": ["Form", "Item", "new"], "kind": "exists", "done": lambda: _exists("Item", {"is_stock_item": 1, "has_variants": 0})},
				{
					"key": "receipt",
					"label": _("Receive stock (Purchase Receipt or Stock Entry)"),
					"route": ["Form", "Purchase Receipt", "new"],
					"actions": [
						{"label": _("Purchase Receipt"), "route": ["Form", "Purchase Receipt", "new"]},
						{"label": _("Stock Entry"), "route": ["Form", "Stock Entry", "new"]},
					],
					"kind": "exists",
					"done": lambda: _exists("Purchase Receipt", {"docstatus": 1}) or _exists("Stock Entry", {"docstatus": 1}),
				},
				{"key": "dn", "label": _("Deliver stock (Delivery Note)"), "route": ["Form", "Delivery Note", "new"], "kind": "exists", "done": lambda: _exists("Delivery Note", {"docstatus": 1})},
				{"key": "balance", "label": _("Open the Stock Balance report"), "route": ["query-report", "Stock Balance"], "kind": "visit"},
			],
		},
	}


def _can_see_panels():
	return bool(_PANEL_ROLES & set(frappe.get_roles()))


_MATURE_DAYS = 45


def panels_enabled_for_site():
	"""Getting-started panels are for NEW tenants. Enterprise tenants are onboarded
	done-for-you (SBL, hq): once their site is older than _MATURE_DAYS the panels would
	only nag about things that don't apply (e.g. "issue your first invoice" on an EAM
	tenant), so they stay off there. site_config `nx_setup_panels` (1/0) overrides."""
	try:
		override = frappe.conf.get("nx_setup_panels")
		if override is not None and override != "":
			return bool(frappe.cint(override))
		if get_plan() != "enterprise":
			return True
		created = frappe.db.get_value("Company", {}, "creation", order_by="creation asc")
		if not created:
			return True
		from frappe.utils import date_diff, nowdate

		return date_diff(nowdate(), created) <= _MATURE_DAYS
	except Exception:
		return True


@frappe.whitelist()
def get_checklist(name):
	"""Steps + done flags for one checklist (rendered by brand.js NexumChecklist)."""
	name = (name or "").strip()
	if not _can_see_panels() or not panels_enabled_for_site():
		return {"hidden": 1, "name": name}
	if frappe.cint(frappe.defaults.get_user_default(_HIDE_KEY.format(name=name))):
		return {"hidden": 1, "name": name}
	company = _company()
	spec = _checklists(company).get(name)
	if not spec:
		frappe.throw(_("Unknown checklist {0}").format(name))
	steps = []
	for s in spec["steps"]:
		done = bool(s["done"]()) if s["kind"] == "exists" else bool(
			frappe.cint(frappe.defaults.get_user_default(_VISIT_KEY.format(name=name, key=s["key"])))
		)
		steps.append(
			{
				"key": s["key"],
				"label": s["label"],
				"help": s.get("help") or "",
				"route": s["route"],
				"actions": s.get("actions") or [],
				"kind": s["kind"],
				"done": done,
			}
		)
	done_count = sum(1 for s in steps if s["done"])
	return {
		"name": name,
		"title": spec["title"],
		"subtitle": spec["subtitle"],
		"steps": steps,
		"done": done_count,
		"total": len(steps),
		"complete": done_count == len(steps),
		"plan": get_plan(),
		"hidden": 0,
	}


CHECKLIST_NAMES = ("home", "accounts", "selling", "stock")


def checklist_boot():
	"""Desk boot flags for brand.js NexumChecklist.mount: when get_checklist could only
	answer {"hidden": 1} (no panel role, a mature Enterprise site, or the user hid that
	checklist), the client renders hidden without the round trip — 0.4–1 s per workspace
	visit from the Philippines. Mirrors get_checklist's first two gates exactly."""
	if not _can_see_panels() or not panels_enabled_for_site():
		return {"off": 1, "hidden": list(CHECKLIST_NAMES)}
	return {
		"off": 0,
		"hidden": [
			n for n in CHECKLIST_NAMES if frappe.cint(frappe.defaults.get_user_default(_HIDE_KEY.format(name=n)))
		],
	}


@frappe.whitelist()
def mark_visited(name, key):
	"""A "visit" step is done once the user clicks through (per user)."""
	frappe.defaults.set_user_default(_VISIT_KEY.format(name=name, key=key), 1)
	return {"ok": 1}


@frappe.whitelist()
def hide_checklist(name):
	frappe.defaults.set_user_default(_HIDE_KEY.format(name=name), 1)
	return {"ok": 1}


@frappe.whitelist()
def show_checklist(name):
	frappe.defaults.clear_user_default(_HIDE_KEY.format(name=name))
	return {"ok": 1}


# --------------------------------------------------------------------------- number cards
def _company_currency(company):
	# tolerate an unconfigured site (Gemini review of batch-183): _company() can be
	# None before any Company exists — the cards must render 0, not 500
	if not company:
		return ""
	try:
		return frappe.get_cached_value("Company", company, "default_currency") or ""
	except Exception:
		return ""


def _card(value, route, route_options=None):
	return {"value": float(value or 0), "fieldtype": "Currency", "route": route, "route_options": route_options or {}}


def _require_read(doctype):
	"""These are plain whitelisted RPCs — enforce the same read permission the card's
	drill-down target needs, server-side (the Number Card widget does no client gating)."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def receivables(filters=None):
	_require_read("Sales Invoice")
	company = _company()
	# outstanding_amount is stored in the PARTY ACCOUNT currency (batch-183, sweep
	# C32): multiplying by conversion_rate is right only when that account is in a
	# foreign currency — for the common company-currency receivable account the old
	# blanket multiply double-converted (a USD invoice at rate 56 reported 56x).
	val = frappe.db.sql(
		"""select coalesce(sum(outstanding_amount *
			if(ifnull(party_account_currency, '') in ('', %(cur)s), 1,
			   ifnull(conversion_rate, 1))), 0)
		from `tabSales Invoice`
		where docstatus = 1 and outstanding_amount > 0 and company = %(company)s""",
		{"company": company, "cur": _company_currency(company)},
	)[0][0]
	return _card(val, ["query-report", "Accounts Receivable"], {"company": company})


@frappe.whitelist()
def payables(filters=None):
	_require_read("Purchase Invoice")
	company = _company()
	# same party-account-currency rule as receivables (sweep C32)
	val = frappe.db.sql(
		"""select coalesce(sum(outstanding_amount *
			if(ifnull(party_account_currency, '') in ('', %(cur)s), 1,
			   ifnull(conversion_rate, 1))), 0)
		from `tabPurchase Invoice`
		where docstatus = 1 and outstanding_amount > 0 and company = %(company)s""",
		{"company": company, "cur": _company_currency(company)},
	)[0][0]
	return _card(val, ["query-report", "Accounts Payable"], {"company": company})


@frappe.whitelist()
def cash_and_bank(filters=None):
	from erpnext.accounts.utils import get_balance_on

	_require_read("Payment Entry")
	company = _company()
	total = 0.0
	for acc in frappe.get_all(
		"Account", filters={"company": company, "is_group": 0, "account_type": ["in", ["Cash", "Bank"]], "disabled": 0}, pluck="name"
	):
		try:
			# company-currency balances (batch-183, sweep C33): the default returns
			# each account's balance in its OWN currency, silently adding USD to PHP
			total += float(get_balance_on(acc, company=company,
			                              in_account_currency=False) or 0)
		except Exception:
			pass
	return _card(total, ["query-report", "Account Balance"], {"company": company, "root_type": "Asset"})


# --------------------------------------------------------------------------- reconcilers
def _block_html(name):
	return f'<div class="nx-checklist" data-checklist="{name}"></div>'


_BLOCK_SCRIPT = """
(function mount(tries){
  var el = root_element && root_element.querySelector('.nx-checklist');
  if (!el) return;
  if (window.NexumChecklist && window.NexumChecklist.mount) { window.NexumChecklist.mount(el); return; }
  if (tries < 40) setTimeout(function(){ mount(tries + 1); }, 150);
})(0);
"""


def _ensure_block(name, checklist):
	"""Create/refresh the Custom HTML Block (public, all roles)."""
	html = _block_html(checklist)
	if frappe.db.exists("Custom HTML Block", name):
		doc = frappe.get_doc("Custom HTML Block", name)
		if doc.html != html or (doc.script or "").strip() != _BLOCK_SCRIPT.strip() or doc.private:
			doc.html = html
			doc.script = _BLOCK_SCRIPT
			doc.style = ""
			doc.private = 0
			doc.flags.ignore_permissions = True
			doc.save()
		return
	doc = frappe.get_doc(
		{"doctype": "Custom HTML Block", "name": name, "html": html, "script": _BLOCK_SCRIPT, "style": "", "private": 0}
	)
	doc.flags.ignore_permissions = True
	doc.insert(set_name=name)


def _ensure_number_cards():
	company = _company()
	currency = _company_currency(company)
	for label, method, doctype in NUMBER_CARDS:
		want = {
			"label": label,
			"type": "Custom",
			"method": method,
			"document_type": doctype,
			"is_public": 1,
			"is_standard": 0,
			"show_full_number": 1,  # frappe shortens 0 to "" -> NaN with a currency card
			"currency": currency,
			"color": "#2E5562",
		}
		if frappe.db.exists("Number Card", label):
			doc = frappe.get_doc("Number Card", label)
			if any(doc.get(k) != v for k, v in want.items()):
				doc.update(want)
				doc.flags.ignore_permissions = True
				doc.save()
		else:
			doc = frappe.get_doc(dict(doctype="Number Card", **want))
			doc.flags.ignore_permissions = True
			doc.insert(set_name=label)


def _our_block(b, names):
	d = b.get("data", {}) if isinstance(b, dict) else {}
	return (b.get("type") == "custom_block" and d.get("custom_block_name") in names) or (
		b.get("type") == "number_card" and d.get("number_card_name") in names
	)


def _place_at_top(workspace, block_names, number_card_names=()):
	"""Ensure our custom_block (+ number-card row) are the first content blocks and the
	child-table rows exist. No-op when already in steady state."""
	ws = frappe.get_doc("Workspace", workspace)
	content = json.loads(ws.content or "[]")
	ours = set(block_names) | set(number_card_names)
	wanted = [{"type": "custom_block", "data": {"custom_block_name": n, "col": 12}} for n in block_names] + [
		{"type": "number_card", "data": {"number_card_name": n, "col": 4}} for n in number_card_names
	]
	head = content[: len(wanted)]
	steady = len(head) == len(wanted) and all(
		h.get("type") == w["type"] and h.get("data", {}).get(next(iter(w["data"]))) == next(iter(w["data"].values()))
		for h, w in zip(head, wanted)
	)
	cb_rows = {r.custom_block_name for r in (ws.custom_blocks or [])}
	nc_rows = {r.number_card_name for r in (ws.number_cards or [])}
	rows_ok = set(block_names) <= cb_rows and set(number_card_names) <= nc_rows
	if steady and rows_ok:
		return False
	rest = [b for b in content if not _our_block(b, ours)]
	new = [dict(id=frappe.generate_hash(length=10), **w) for w in wanted] + rest
	ws.content = json.dumps(new)
	for n in block_names:
		if n not in cb_rows:
			ws.append("custom_blocks", {"custom_block_name": n, "label": n})
	for n in number_card_names:
		if n not in nc_rows:
			ws.append("number_cards", {"number_card_name": n, "label": n})
	ws.flags.ignore_permissions = True
	ws.save()
	return True


def reconcile_home_workspace():
	"""after_migrate: owner-first Home (Get-set-up panel + Receivables/Payables/Cash row) and
	Getting-started panels on Accounting / Selling / Stock. Idempotent + hardened."""
	if not frappe.db.table_exists("Workspace") or not frappe.db.table_exists("Custom HTML Block"):
		return
	try:
		_ensure_block(HOME_BLOCK, "home")
		_ensure_number_cards()
		if frappe.db.exists("Workspace", "Home"):
			_place_at_top("Home", [HOME_BLOCK], [n for n, _m, _d in NUMBER_CARDS])
	except Exception:
		frappe.log_error(title="my_branding reconcile_home_workspace (home) failed", message=frappe.get_traceback())
	for key, (_candidates, block) in MODULE_BLOCKS.items():
		try:
			workspace = module_workspace(key)
			if not workspace:
				continue
			_ensure_block(block, key)
			_place_at_top(workspace, [block])
		except Exception:
			frappe.log_error(title=f"my_branding reconcile_home_workspace ({key}) failed", message=frappe.get_traceback())
	try:
		frappe.cache.delete_key("bootinfo")
	except Exception:
		pass
