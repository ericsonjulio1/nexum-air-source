"""Versioned NexumAir plan policy shared by Frappe and host adapters.

No Frappe dependency. The operations bundle materializes the same source file;
host scripts must never maintain their own prices, limits or membership maps.
Existing checkout amounts and unattended-approval eligibility are preserved.
"""
import argparse
import json

POLICY_VERSION = 1
_FREE_CAPS = {"Customer": 10, "Supplier": 10, "Item": 25, "Sales Invoice": 50,
	"Purchase Order": 25, "Purchase Invoice": 25, "Journal Entry": 50,
	"Stock Entry": 50, "Payment Entry": 50}
_BASE_APPS = ("erpnext", "my_branding")
_STARTER_APPS = (*_BASE_APPS, "print_designer")
_BUSINESS_APPS = (*_STARTER_APPS, "hrms", "crm", "payments")
_POLICY = {
	"free": dict(label="Free", aliases=("free", "free tier", "free plan"),
		apps=_BASE_APPS, quota_gb=1, doc_caps=_FREE_CAPS, price_php=None,
		simple=True, auto_approve=True, signup_aliases=("free",), indicators=()),
	"starter": dict(label="Essentials", aliases=("essentials", "starter"),
		apps=_STARTER_APPS, quota_gb=5, doc_caps={}, price_php=2790,
		simple=True, auto_approve=True, signup_aliases=("essentials", "starter"), indicators=("print_designer",)),
	"business": dict(label="Business", aliases=("business",),
		apps=_BUSINESS_APPS, quota_gb=25, doc_caps={}, price_php=8490,
		simple=False, auto_approve=True, signup_aliases=("business",), indicators=("hrms", "crm", "helpdesk", "insights")),
	"enterprise": dict(label="Enterprise", aliases=("enterprise",),
		apps=(*_BUSINESS_APPS, "eam"), quota_gb=100, doc_caps={}, price_php=22740,
		simple=False, auto_approve=False, signup_aliases=("enterprise",), indicators=("eam", "lms", "drive")),
}
PLAN_IDS = tuple(_POLICY)
PLAN_ALIASES = {alias: slug for slug, p in _POLICY.items() for alias in p["aliases"]}
SIGNUP_PLANS = frozenset(alias for p in _POLICY.values() for alias in p["signup_aliases"])
AUTO_APPROVE_PLANS = frozenset(alias for p in _POLICY.values() if p["auto_approve"] for alias in p["signup_aliases"])
SIMPLE_PLANS = tuple(slug for slug, p in _POLICY.items() if p["simple"])
CHECKOUT_PRICES_PHP = {p["label"]: p["price_php"] for p in _POLICY.values() if p["price_php"] is not None}
PAID_LABELS = {p["label"]: slug for slug, p in _POLICY.items() if p["price_php"] is not None}
CAPPED_DOCTYPES = tuple(dict.fromkeys(dt for p in _POLICY.values() for dt in p["doc_caps"]))


def canonical_plan(value):
	return PLAN_ALIASES.get(str(value or "").strip().lower())


def policy(plan):
	"""A caller-owned policy snapshot; unknown plans fail explicitly."""
	slug = canonical_plan(plan)
	if slug is None:
		raise ValueError("Unknown NexumAir plan")
	return dict(_POLICY[slug], slug=slug, version=POLICY_VERSION, doc_caps=dict(_POLICY[slug]["doc_caps"]))


def infer_plan(apps):
	"""Legacy sites without nexum_plan keep their existing inference semantics."""
	installed = set(apps)
	for slug in reversed(PLAN_IDS):
		if installed.intersection(_POLICY[slug]["indicators"]):
			return slug
	return "free"


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("field", choices=("apps", "quota_gb", "doc_caps", "policy"))
	parser.add_argument("plan")
	parser.add_argument("--strict-id", action="store_true", help="Accept canonical host plan IDs only")
	args = parser.parse_args()
	if args.strict_id and args.plan not in PLAN_IDS:
		parser.error("Host operations require a canonical plan ID")
	try:
		value = policy(args.plan)
	except ValueError as exc:
		parser.error(str(exc))
	if args.field == "apps":
		print(" ".join(value["apps"]))
	elif args.field == "quota_gb":
		print(value["quota_gb"])
	else:
		print(json.dumps(value if args.field == "policy" else value[args.field], separators=(",", ":")))


if __name__ == "__main__":
	main()
