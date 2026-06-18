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

	return stock_setup_complete(json.dumps(data))
