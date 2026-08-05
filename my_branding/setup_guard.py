"""Guard ERPNext's setup wizard against a missing Country.

ERPNext's setup-wizard fixtures step does ``country.replace(...)`` and raises a
raw 500 (``'NoneType' object has no attribute 'replace'``) when the wizard is
submitted with no Country. That rolls the whole setup back and strands the
customer on the "Setup your organization" screen forever — exactly what hit
curiosity.nexumair.com on 2026-06-17 (the Country field sat behind a mobile
overlay and was left blank).

This wrapper is registered over the stock ``setup_complete`` whitelisted method
(see ``override_whitelisted_methods`` in hooks.py). It backfills the Country —
and its currency — from the global default we pre-seed at provision time, and if
there is genuinely no Country to use it raises a clean validation error instead
of a 500.
"""

import json

import frappe
from frappe import _


@frappe.whitelist()
def setup_complete(args):
	# Imported lazily so the override map resolves the *stock* function (not us),
	# avoiding any recursion through the whitelisted-method dispatch.
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete as stock_setup_complete

	# Authorization: the legitimate caller is the setup wizard, always run by
	# Administrator / the first System Manager on a fresh site. This is registered as a
	# GLOBAL override_whitelisted_methods entry, so without this guard ANY logged-in
	# tenant user could POST to my_branding.setup_guard.setup_complete and reach the
	# System Settings write below — overwriting the tenant's global country/currency.
	# (Mirrors the guard already on autocomplete_setup.)
	frappe.only_for("System Manager")

	data = json.loads(args) if isinstance(args, str) else dict(args or {})

	country = (data.get("country") or "").strip()
	if not country:
		# fall back to the Country pre-seeded as the site's global default
		country = (frappe.db.get_default("country") or "").strip()

	if not country:
		frappe.throw(
			_("Please go back and select a Country before completing setup."),
			title=_("Country Required"),
		)

	data["country"] = country

	# Backfill currency too — the same blank-form path leaves it null, and the
	# stock flow is happier with an explicit value.
	if not (data.get("currency") or "").strip():
		try:
			from frappe.geo.country_info import get_country_info

			currency = (get_country_info(country) or {}).get("currency")
			if currency:
				data["currency"] = currency
		except Exception:
			pass

	# Persist country/currency on System Settings too. ERPNext's RESUMED-setup path
	# (set_missing_values) reads these from System Settings, NOT from these args — so if a
	# first attempt ever marks the 'frappe' stage complete with a blank country, every
	# retry reads None and re-fails forever (this is exactly what stranded
	# curiosity.nexumair.com, 2026-06-20). Writing them here makes a retry resume-safe.
	# Gate on NOT-yet-complete: once setup is done the stock function no-ops, so this
	# write would otherwise be the only effect of a re-call — never mutate an already-
	# configured tenant's country/currency.
	if not frappe.is_setup_complete():
		try:
			# only write currency when we actually have one — `or None` would otherwise
			# clobber a pre-seeded System Settings currency with NULL when the form was
			# blank AND get_country_info() yielded no currency, defeating the resume-safe
			# backfill this block exists for.
			vals = {"country": country}
			if (data.get("currency") or "").strip():
				vals["currency"] = data["currency"]
			frappe.db.set_value("System Settings", "System Settings", vals)
			frappe.db.commit()
		except Exception:
			pass

	return stock_setup_complete(json.dumps(data))


@frappe.whitelist()
def autocomplete_setup(company_name=None, country="Philippines", currency="PHP"):
	"""Provision-time onboarding: complete the setup wizard programmatically so a NEW
	tenant never lands on the (fragile) wizard at all — they log straight into a ready
	desk with their own company. Called by provision-tenant.sh after app install.

	Uses the client's signup company name; safe market defaults (Philippines/PHP, which
	the client can change later) and a standard calendar fiscal year. Idempotent: a no-op
	if setup is already complete, so re-running provisioning can't double-create anything.
	Hardened: persists country/currency on System Settings first (resume-safe, see above)
	and finalizes the per-app + global setup-complete flags so is_setup_complete() is True.
	"""
	import json as _json

	from frappe.utils import nowdate

	# State-mutating + @whitelist'd: restrict to admins. In normal operation this is
	# called by provision-tenant.sh via `bench execute` (Administrator context, which
	# passes only_for) — the guard just stops a logged-in low-privilege tenant user
	# from POSTing to a raw setup-completing endpoint.
	frappe.only_for("System Manager")

	if frappe.is_setup_complete():
		return {"status": "already complete"}

	company_name = (str(company_name or "").strip()) or "My Company"
	abbr = ("".join(w[0] for w in company_name.split() if w)[:5] or "C").upper()
	year = int(nowdate()[:4])

	# resume-safe: the wizard's set_missing_values reads these from System Settings
	frappe.db.set_value(
		"System Settings",
		"System Settings",
		{
			"country": country,
			"currency": currency,
			"language": "en",
			"time_zone": "Asia/Manila",
			"time_format": "HH:mm:ss",
		},
	)
	frappe.db.commit()

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete as stock_setup_complete

	args = {
		"language": "English",
		"country": country,
		"currency": currency,
		"timezone": "Asia/Manila",
		"time_zone": "Asia/Manila",
		"time_format": "HH:mm:ss",
		"company_name": company_name,
		"company_abbr": abbr,
		"chart_of_accounts": "Standard",
		"fy_start_date": "%d-01-01" % year,
		"fy_end_date": "%d-12-31" % year,
		"setup_demo": 0,
	}

	# Frappe CRM's setup_wizard_complete hook (crm.demo.api.create_demo_data) ignores
	# setup_demo and seeds demo users/leads/deals on every wizard completion — its only
	# guard is this default. Pre-set it so real tenants never get @example.com demo
	# users (whose assignment emails hard-bounce at Resend).
	if "crm" in frappe.get_installed_apps():
		frappe.db.set_default("crm_demo_data_created", "1")

	stock_setup_complete(_json.dumps(args))

	# Finalize: only frappe+erpnext have setup stages, so mark every installed app +
	# the global flag so is_setup_complete() is True and the wizard never shows again.
	frappe.db.sql("update `tabInstalled Application` set is_setup_complete=1")
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	frappe.db.commit()
	return {"status": "completed", "company": company_name}
