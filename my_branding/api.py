"""Public (guest) API for the nexumair.com marketing site.

Replaces the old ``signup-api`` Server Script on hq: Server Scripts run inside
safe_exec and cannot make the outbound HTTP call that Cloudflare Turnstile
verification needs, so the signup endpoint lives here instead.

Endpoints (called cross-origin from the landing page; hq's ``allow_cors``
site_config covers them):

- ``my_branding.api.signup`` — landing-form submit. Layers: honeypot field,
  Turnstile token verification (only when ``turnstile_secret`` is set in
  site_config, so the feature is config-toggled), e-mail de-dupe, then a CRM
  Lead the provisioning worker picks up.
- ``my_branding.api.check_subdomain`` — live availability check while the
  customer types their subdomain. Mirrors provision-tenant.sh's validation
  (same regex + reserved list) so the form can't submit a name provisioning
  would reject anyway.
- ``my_branding.api.capture_partial`` — fallback that records a prospect whose
  signup could not complete (e.g. the Turnstile widget was blocked by an
  in-app browser). Creates a *Pending* CRM Lead (never auto-provisions) and
  alerts the owner so the lead gets a human follow-up instead of being lost.
"""

import os
import re

import frappe
from frappe.utils import get_bench_path

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
BASE_DOMAIN = "nexumair.com"

# keep in sync with provision-tenant.sh (validate subdomain + reserved case list)
SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])$")
# strict charset, same as provision-tenant.sh: no quotes/spaces/tabs/backslashes,
# so a signup can never queue an email that breaks the provisioning JSON or the
# tab-separated tenants.tsv downstream
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
RESERVED_SUBDOMAINS = {
	"www", "hq", "api", "admin", "app", "mail", "smtp", "imap", "pop", "ftp",
	"ns1", "ns2", "dns", "demo", "test", "staging", "stage", "status", "help",
	"support", "billing", "dashboard", "portal", "cdn", "static", "assets",
	"blog", "docs", "store", "shop", "pay", "secure", "root", "nexumair",
}


def _verify_turnstile(token):
	secret = frappe.conf.get("turnstile_secret")
	if not secret:
		return True  # Turnstile not configured on this site — feature off
	if not token:
		return False
	try:
		import requests

		# no remoteip: behind Cloudflare + Traefik the backend sees a proxy IP,
		# not the visitor's, and a mismatched remoteip fails valid tokens
		resp = requests.post(
			TURNSTILE_VERIFY_URL,
			data={"secret": secret, "response": token},
			timeout=5,
		)
		return bool(resp.json().get("success"))
	except Exception:
		# Cloudflare unreachable must not silently lose real signups — the
		# honeypot + de-dupe layers still apply. Log and let it through.
		frappe.log_error(
			title="my_branding turnstile verify failed (fail-open)",
			message=frappe.get_traceback(),
		)
		return True


@frappe.whitelist(allow_guest=True, methods=["POST"])
def signup():
	d = frappe.form_dict

	# honeypot: hidden field a human never fills
	if d.get("website") or d.get("hp_url"):
		return {"ok": True}

	email = (d.get("email") or "").strip()
	if not email or len(email) > 120 or not EMAIL_RE.match(email):
		return {"ok": False, "error": "valid email required"}

	if not _verify_turnstile(d.get("cf-turnstile-response") or d.get("cf_turnstile_response")):
		return {"ok": False, "error": "captcha verification failed"}

	if frappe.db.exists("CRM Lead", {"email": email}):
		return {"ok": True, "dedup": 1}

	# cap free-text lengths so a bot can't stuff megabytes into a lead
	company = (d.get("company") or "").strip()[:140]
	lead = frappe.new_doc("CRM Lead")
	lead.first_name = company or email
	lead.organization = company
	lead.email = email
	lead.status = "New"
	lead.custom_plan = (d.get("plan") or "").strip()[:40]
	lead.custom_subdomain = (d.get("subdomain") or "").strip().lower()[:60]
	lead.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "lead": lead.name}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def capture_partial():
	"""Record a signup that could not complete so a real prospect isn't lost.

	Fired by the landing page when the Turnstile challenge can't run (commonly an
	in-app browser such as Facebook/Instagram/Gmail blocking the widget). The lead
	is left at the default ``Pending`` provision status — the worker only ever acts
	on ``Approved`` leads, so this NEVER auto-provisions; it's a follow-up record
	plus an owner alert. The strict signup() path is unchanged.

	Anti-spam: honeypot + email-format + e-mail de-dupe. The only cost of abuse is
	inbox/CRM noise, not bot tenants — manual Approve still gates provisioning.
	"""
	d = frappe.form_dict

	# honeypot: hidden field a human never fills
	if d.get("website") or d.get("hp_url"):
		return {"ok": True}

	email = (d.get("email") or "").strip()
	if not email or len(email) > 120 or not EMAIL_RE.match(email):
		return {"ok": False, "error": "valid email required"}

	# don't duplicate an existing lead (a completed signup, or an earlier capture)
	if frappe.db.exists("CRM Lead", {"email": email}):
		return {"ok": True, "dedup": 1}

	company = (d.get("company") or "").strip()[:140]
	plan = (d.get("plan") or "").strip()[:40]
	subdomain = (d.get("subdomain") or "").strip().lower()[:60]
	reason = (d.get("reason") or "unknown").strip()[:60]

	lead = frappe.new_doc("CRM Lead")
	lead.first_name = company or email
	lead.organization = company
	lead.email = email
	lead.status = "New"
	lead.custom_plan = plan
	lead.custom_subdomain = subdomain
	lead.custom_provision_status = "Pending"
	lead.custom_provision_log = (
		"BLOCKED SIGNUP (reason=%s): the visitor filled the form but the security "
		"check could not complete in their browser (commonly an in-app browser such "
		"as Facebook/Instagram/Gmail). Verify this is a real prospect, then set the "
		"provision status to Approved to provision." % reason
	)
	lead.insert(ignore_permissions=True)
	frappe.db.commit()

	# alert the owner so a blocked prospect gets a human follow-up
	try:
		owner = frappe.conf.get("owner_notify_email") or "admin@nexumair.com"
		frappe.sendmail(
			recipients=[owner],
			subject="⚠️ Blocked Nexum Air signup — needs follow-up (%s)" % (company or email),
			message=(
				"A prospect tried to sign up but the security check was blocked in "
				"their browser, so the form could not complete on its own.<br><br>"
				"<b>Company:</b> %s<br><b>Email:</b> %s<br>"
				"<b>Subdomain:</b> %s<br><b>Plan:</b> %s<br><b>Reason:</b> %s<br><br>"
				"A Pending CRM Lead (<b>%s</b>) was created. Reach out, and if it's "
				"genuine set its provision status to Approved.<br>"
				'<a href="https://hq.nexumair.com/crm/leads/%s">Open in CRM</a>'
				% (company, email, subdomain, plan, reason, lead.name, lead.name)
			),
			now=True,
		)
	except Exception:
		frappe.log_error(
			title="my_branding capture_partial owner alert failed",
			message=frappe.get_traceback(),
		)

	return {"ok": True, "lead": lead.name, "captured": 1}


@frappe.whitelist(allow_guest=True)
def check_subdomain(subdomain=None):
	sub = (subdomain or "").strip().lower()

	if not SUBDOMAIN_RE.match(sub):
		return {"available": False, "reason": "invalid"}
	if sub in RESERVED_SUBDOMAINS:
		return {"available": False, "reason": "reserved"}

	# a site already provisioned on this bench
	site_config = os.path.join(get_bench_path(), "sites", f"{sub}.{BASE_DOMAIN}", "site_config.json")
	if os.path.exists(site_config):
		return {"available": False, "reason": "taken"}

	# a signup already queued for the same name (anything not Failed holds it)
	if frappe.db.exists("DocType", "CRM Lead") and frappe.db.exists(
		"CRM Lead",
		{
			"custom_subdomain": sub,
			"custom_provision_status": ("in", ["Pending", "Approved", "Provisioning", "Active"]),
		},
	):
		return {"available": False, "reason": "taken"}

	return {"available": True}
