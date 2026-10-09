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

import json
import os
import re
from datetime import datetime, timedelta
from html import escape

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

# Auto-approval (unattended provisioning) risk inputs -------------------------
# A signup from a free/throwaway provider is HELD for manual review rather than
# auto-approved — real businesses use gmail/outlook/yahoo/company mail.
DISPOSABLE_EMAIL_DOMAINS = {
	"mailinator.com", "guerrillamail.com", "guerrillamail.info", "sharklasers.com",
	"10minutemail.com", "10minutemail.net", "tempmail.com", "temp-mail.org",
	"tempmail.net", "tempmailo.com", "yopmail.com", "trashmail.com", "getnada.com",
	"dispostable.com", "maildrop.cc", "throwawaymail.com", "fakeinbox.com",
	"mailnesia.com", "mintemail.com", "mohmal.com", "spam4.me", "emailondeck.com",
	"moakt.com", "discard.email", "getairmail.com",
}
# plan labels we know how to provision (mirror provision-worker.py PLAN_MAP keys).
KNOWN_PLANS = {"free", "essentials", "starter", "business", "enterprise"}
# Plans eligible for UNATTENDED auto-approval. Enterprise is deliberately excluded:
# those are higher-value, higher-touch prospects worth a human qualification, so an
# Enterprise signup is HELD for manual review even when everything else looks low-risk.
# Free is the lowest-touch, instant-by-design tier (also gated by the global free cap).
AUTO_APPROVE_PLANS = {"free", "essentials", "starter", "business"}
# ceilings on UNATTENDED auto-approvals; a clean-looking burst beyond EITHER holds
# for manual review, so abuse/runaway cost can never auto-spin an unbounded number
# of tenants. Both are enforced with an atomic Redis counter (see _bump_window).
AUTO_APPROVE_CAP_PER_HOUR = 8
AUTO_APPROVE_CAP_PER_DAY = 25


def _require_signup_host():
	"""Guard: these guest endpoints (signup / capture_partial / check_subdomain) are
	the public nexumair.com marketing API and must run ONLY on the central signup host.
	``my_branding`` is installed on EVERY tenant, so without this guard the same
	``allow_guest`` endpoints are reachable unauthenticated on every customer subdomain —
	letting a guest inject CRM Leads into a tenant's own data, multiplying the owner-alert
	mailbomb by the live-tenant count, and exposing the subdomain-enumeration oracle on
	every domain. Set ``is_signup_host=1`` in the signup host's site_config (hq) only;
	everywhere else this raises and the endpoint is a no-op."""
	if not frappe.conf.get("is_signup_host"):
		raise frappe.PermissionError("This endpoint is not available on this site.")


def _accepted():
	"""Uniform guest 'signup accepted' response. Every success path — a brand-new lead,
	a waitlisted one, or a duplicate of an existing lead — returns exactly this, so an
	unauthenticated caller can't use the payload to tell whether an email is already a
	NexumAir prospect/customer (the email-enumeration oracle). The landing page only reads
	`.ok`; the real lead record lives in CRM. (A residual timing side-channel remains —
	dedup returns before the ~5s Turnstile call — best bounded by a per-IP edge rate rule.)"""
	return {"ok": True}


def _clean_subdomain(raw):
	"""Normalise + validate a client-supplied subdomain at the WRITE layer.

	check_subdomain() only validates the live as-you-type field; a direct POST to
	signup()/capture_partial() bypasses it, so both write paths must re-apply the
	same rules (charset regex + reserved list — the authoritative checks shared with
	provision-tenant.sh). Returns ``(sub, ok)``: ``sub`` is the lower-cased value,
	``ok`` is False when it fails the charset regex or is reserved. Uniqueness is
	NOT checked here (a separate query); callers decide how to treat ``ok``."""
	sub = (raw or "").strip().lower()[:60]
	if not sub:
		return "", True  # blank is allowed (subdomain is optional on a lead)
	ok = bool(SUBDOMAIN_RE.match(sub)) and sub not in RESERVED_SUBDOMAINS
	return sub, ok


def _verify_turnstile(token):
	"""Tri-state Turnstile result: ``"pass"`` (Cloudflare confirmed a human),
	``"fail"`` (Cloudflare rejected the token), or ``"skip"`` (we couldn't verify —
	no secret configured, or Cloudflare unreachable).

	The signup gate fails OPEN on ``"skip"`` (a CF outage must never lose real
	signups), but auto-approval treats ``"skip"`` as NOT good enough — only a
	strict ``"pass"`` is allowed to provision unattended."""
	secret = frappe.conf.get("turnstile_secret")
	if not secret:
		return "skip"  # Turnstile not configured on this site — feature off
	if not token:
		return "fail"
	try:
		import requests

		# no remoteip: behind Cloudflare + Traefik the backend sees a proxy IP,
		# not the visitor's, and a mismatched remoteip fails valid tokens
		resp = requests.post(
			TURNSTILE_VERIFY_URL,
			data={"secret": secret, "response": token},
			timeout=5,
		)
		return "pass" if bool(resp.json().get("success")) else "fail"
	except Exception:
		# Cloudflare unreachable must not silently lose real signups — the
		# honeypot + de-dupe layers still apply. Log and let it through (skip).
		frappe.log_error(
			title="my_branding turnstile verify failed (fail-open)",
			message=frappe.get_traceback(),
		)
		return "skip"


def _subdomain_taken(sub, include_pipeline=True):
	"""True if ``sub`` is already provisioned on this bench or held by a CRM Lead.
	Assumes ``sub`` already passed the charset/reserved checks.

	``include_pipeline`` controls which lead statuses count as taken:
	* True (default, used by signup's risk assessment): the full in-flight set
	  Pending/Approved/Provisioning/Active — so two signups for the same name are
	  caught and held for review.
	* False (used by the PUBLIC check_subdomain availability oracle): only live /
	  actively-provisioning sites (Provisioning/Active). This keeps the as-you-type
	  checker from leaking not-yet-live signups (Pending/Approved company names =
	  sales-pipeline intel) to unauthenticated guests; a rare Pending collision is
	  resolved by the operator at Approve time, not hard-rejected."""
	site_config = os.path.join(get_bench_path(), "sites", f"{sub}.{BASE_DOMAIN}", "site_config.json")
	if os.path.exists(site_config):
		return True
	statuses = ["Pending", "Approved", "Provisioning", "Active"] if include_pipeline else ["Provisioning", "Active"]
	return bool(
		frappe.db.exists("DocType", "CRM Lead")
		and frappe.db.exists(
			"CRM Lead",
			{
				"custom_subdomain": sub,
				"custom_provision_status": ("in", statuses),
			},
		)
	)


def _bump_window(name, fmt, ttl):
	"""Atomically increment a time-bucketed counter (Redis INCR) and return the new
	count. INCR is atomic, so a burst of concurrent requests can't undercount the
	cap the way a get-then-set would (the exact race a flood would exploit). Key is
	site-namespaced; raises on a cache outage so callers choose fail-open/closed."""
	bucket = "%s:%s:%s" % (name, getattr(frappe.local, "site", "") or "", frappe.utils.now_datetime().strftime(fmt))
	n = frappe.cache.incr(bucket)
	if n == 1:
		frappe.cache.expire(bucket, ttl)
	return n


def _is_disposable_email(email):
	"""True if the email's domain OR any parent suffix is a known throwaway domain,
	so a subdomain of a disposable host (e.g. ``x.mailinator.com``) can't slip past
	an exact-match check."""
	dom = email.rsplit("@", 1)[-1].lower().strip(".")
	parts = dom.split(".")
	# test the full domain and each registrable parent suffix (need >=2 labels)
	for i in range(len(parts) - 1):
		if ".".join(parts[i:]) in DISPOSABLE_EMAIL_DOMAINS:
			return True
	return False


def _assess_trial_risk(email, subdomain, plan, ts):
	"""Decide whether a signup is safe to provision UNATTENDED. Returns
	``(approve: bool, reason: str)``. Deliberately conservative — ANY doubt holds
	the lead at Pending for a human to review (the owner is alerted)."""
	holds = []
	if ts != "pass":
		holds.append("security check not strictly verified")
	if _is_disposable_email(email):
		holds.append("disposable/throwaway email domain")
	if not subdomain:
		holds.append("no subdomain chosen")
	elif _subdomain_taken(subdomain):
		holds.append("subdomain unavailable")
	plan_norm = (plan or "").strip().lower()
	if plan_norm not in KNOWN_PLANS:
		holds.append("unrecognized plan")
	elif plan_norm not in AUTO_APPROVE_PLANS:
		holds.append("Enterprise plan — manual qualification")
	if holds:
		return False, "; ".join(holds)
	# everything looks clean — enforce hourly AND daily ceilings so even a clean-
	# looking burst can't auto-provision an unbounded number of tenants. Atomic
	# (Redis INCR) so concurrent requests can't race past the cap. Overflow — and a
	# cache outage — HOLDS for manual review rather than failing open.
	try:
		if _bump_window("nexum_autoapprove_h", "%Y%m%d%H", 3700) > AUTO_APPROVE_CAP_PER_HOUR:
			return False, "hourly auto-approval limit reached — held for review"
		if _bump_window("nexum_autoapprove_d", "%Y%m%d", 90000) > AUTO_APPROVE_CAP_PER_DAY:
			return False, "daily auto-approval limit reached — held for review"
	except Exception:
		return False, "rate state unavailable — held for review"
	return True, "low risk (human-verified, business email, subdomain free, known plan)"


def _is_free(plan):
	"""True when the form/CRM plan label refers to the perpetual Free tier."""
	return (plan or "").strip().lower() in ("free", "free tier", "free plan")


def _free_cap():
	"""Max concurrent Free-tier sites the shared server will provision (0 / unset =
	unlimited). A capacity backstop so unbounded free signups can't exhaust the box —
	set ``free_tier_cap`` in hq site_config; raise it as capacity grows or when Free
	moves to its own server."""
	try:
		return int(frappe.conf.get("free_tier_cap") or 0)
	except (TypeError, ValueError):
		return 0


def _free_active_count():
	"""Count Free-tier leads that are live or in-flight (Approved/Provisioning/Active).
	Conservative by design: a deleted-but-still-Active lead keeps counting, so the cap
	errs toward holding new free signups rather than over-filling the server."""
	return frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabCRM Lead`
		 WHERE LOWER(TRIM(custom_plan)) IN ('free', 'free tier', 'free plan')
		   AND custom_provision_status IN ('Approved', 'Provisioning', 'Active')
		"""
	)[0][0]


def _stage_free_lead(lead, cap, email, subdomain, plan, ts, subdomain_locked=True):
	"""Capacity-gate + auto-approve a free-tier lead, insert it, and return the signup()
	response dict. Call under the nexum_free_cap lock so the count check and the 'Approved'
	insert commit atomically against concurrent free signups (otherwise two racers both
	read count<cap and both auto-approve, overshooting free_tier_cap)."""
	waitlist = cap > 0 and _free_active_count() >= cap
	if waitlist:
		# free capacity reached — hold (don't reject the prospect), alert via the worker
		lead.custom_provision_status = "Pending"
		lead.custom_provision_log = (
			"FREE WAITLIST: free-tier capacity (%d) reached — review or raise free_tier_cap "
			"before provisioning" % cap
		)
	else:
		approve, reason = _assess_trial_risk(email, subdomain, plan, ts)
		if approve:
			lead.custom_provision_status = "Approved"
			lead.custom_provision_log = "auto-approved (free): " + reason
			auto = 1
		else:
			lead.custom_provision_status = "Pending"
			lead.custom_provision_log = "HELD for review (free): " + reason
			auto = 0

	# Re-check identity and subdomain at the insertion boundary while signup() holds
	# the identity lock. The early checks remain useful fast paths, but are stale by now
	# if another request inserted while this one was verifying Turnstile.
	if frappe.db.exists("CRM Lead", {"email": email, "custom_provision_status": ["!=", "Failed"]}):
		return _accepted()
	if subdomain and not subdomain_locked:
		lead.custom_provision_status = "Pending"
		lead.custom_provision_log += "; HELD for review: subdomain lock unavailable at insert time"
		if not waitlist:
			auto = 0
	if subdomain and _subdomain_taken(subdomain):
		lead.custom_provision_status = "Pending"
		lead.custom_provision_log += "; HELD for review: subdomain collision detected at insert time"
		if not waitlist:
			auto = 0

	lead.insert(ignore_permissions=True)
	frappe.db.commit()
	# ALWAYS the uniform shape (batch-183, sweep C31): returning {ok, lead, auto} for
	# a new lead while duplicates got a bare {ok} let a guest distinguish known from
	# unknown emails — the exact oracle _accepted() exists to close. Nothing
	# client-side reads lead/auto.
	return _accepted()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def signup():
	_require_signup_host()  # hq only — never run on a tenant site
	d = frappe.form_dict

	# honeypot: hidden field a human never fills
	if d.get("website") or d.get("hp_url"):
		return {"ok": True}

	email = (d.get("email") or "").strip()
	if not email or len(email) > 120 or not EMAIL_RE.match(email):
		return {"ok": False, "error": "valid email required"}

	# Dedup excludes FAILED leads (here and at every re-check): the retry email we
	# send on a subdomain clash tells the customer to sign up again with another
	# name — an email-only dedup returned {ok} while silently doing nothing, so the
	# advertised retry flow never worked. A Failed lead's email may try again.
	# Dedup + flood cap run BEFORE the (up to ~5s, outbound) Turnstile verification.
	# Otherwise every request OVER the cap still pays a blocking Cloudflare round-trip
	# before being rejected, so a bot flood pins a gunicorn worker ~5s each — exactly what
	# the cap exists to prevent. check_subdomain()/capture_partial() already rate-limit
	# first. Dedup runs first (cheap, indexed on email) so a benign double-submit / browser
	# retry returns early and does NOT consume the global hourly budget.
	if frappe.db.exists("CRM Lead", {"email": email, "custom_provision_status": ["!=", "Failed"]}):
		return _accepted()

	# rate-limit backstop: signup() trusts Turnstile, but _verify_turnstile is FAIL-OPEN
	# (it passes when Cloudflare is unreachable or no turnstile_secret is set), so on a
	# bad-CF day or a misconfigured site a bot could flood CRM Leads with no throttle.
	# Mirror capture_partial's global hourly cap. Fail-open: a cache hiccup must never
	# drop a genuine signup.
	try:
		if _bump_window("nexum_signup", "%Y%m%d%H", 3700) > 60:
			return {"ok": False, "error": "too many signups right now, please try again shortly"}
	except Exception:
		pass

	ts = _verify_turnstile(d.get("cf-turnstile-response") or d.get("cf_turnstile_response"))
	if ts == "fail":
		return {"ok": False, "error": "captcha verification failed"}
	# ts is "pass" (verified) or "skip" (CF unverifiable — allowed in, but not auto-approved)

	# Re-validate the subdomain server-side: check_subdomain() only guards the live
	# form field, so a direct POST could otherwise queue a Lead with a reserved/
	# malformed name. Reject it here — a real form submit always sends a clean value.
	subdomain, sub_ok = _clean_subdomain(d.get("subdomain"))
	if not sub_ok:
		return {"ok": False, "error": "invalid subdomain"}

	# Serialize each email's final re-check + insert. Fail-open: a lock hiccup falls
	# back to the same insertion path rather than dropping a genuine prospect.
	identity_lock_cm = None
	got_identity_lock = False
	try:
		from frappe.utils.synchronization import filelock
		identity_lock_cm = filelock("nexum_signup_identity:" + email.lower(), timeout=15)
		identity_lock_cm.__enter__()
		got_identity_lock = True
	except Exception:
		got_identity_lock = False

	# Different emails may still race for the same subdomain, so serialize only
	# competing claims for that subdomain. Keep the same fail-open behavior.
	subdomain_lock_cm = None
	got_subdomain_lock = False
	if subdomain:
		try:
			from frappe.utils.synchronization import filelock
			subdomain_lock_cm = filelock("nexum_signup_subdomain:" + subdomain, timeout=15)
			subdomain_lock_cm.__enter__()
			got_subdomain_lock = True
		except Exception:
			got_subdomain_lock = False
	# FRESH SNAPSHOT (batch-183, sweep C29): the pre-lock dedup read established this
	# transaction's REPEATABLE READ snapshot, so the insert-boundary re-checks below —
	# though they run under the locks — would replay that stale snapshot and miss a
	# racer's committed insert (the racer commits before releasing its lock). Ending
	# the transaction here starts a fresh read view; nothing meaningful has been
	# written yet in this guest request.
	try:
		frappe.db.commit()
	except Exception:
		pass
	try:
		# cap free-text lengths so a bot can't stuff megabytes into a lead
		company = " ".join((d.get("company") or "").split())[:140]
		plan = (d.get("plan") or "").strip()[:40]
		lead = frappe.new_doc("CRM Lead")
		lead.first_name = company or email
		lead.organization = company
		lead.email = email
		lead.status = "New"
		lead.custom_plan = plan
		lead.custom_subdomain = subdomain
		# Marketing attribution (custom_utm_*/custom_referrer) is stamped from the request
		# form params (utm_source/medium/campaign/content/term, ref) by the "lead-attribution"
		# Before-Insert Server Script — see saas/hq-lead-capture-setup.py. The landing form
		# forwards those params on this POST (index.html NX.append).

		# Auto-approval. Free tier is instant BY DESIGN (no manual review, independent of the
		# auto_approve_trials flag) — that frictionless path is the whole point of freemium —
		# but still gated by Turnstile (above), the per-tenant risk backstop, AND a global cap
		# that protects the shared server from unbounded free sites. Paid trials keep the
		# original behaviour: instant only when auto_approve_trials is on and the signup is
		# low-risk; otherwise Pending for human review.
		auto = 0
		if _is_free(plan):
			cap = _free_cap()
			# Serialize the capacity check with the 'Approved' insert so concurrent free signups
			# can't each read count<cap and each auto-approve past free_tier_cap (overshooting the
			# shared box by racers-1). The hourly/daily auto-approve caps are atomic via Redis INCR;
			# the free cap needs count+insert atomic, so we take a short cross-worker lock. Fail-open:
			# a lock hiccup falls back to the unlocked path rather than dropping a genuine prospect.
			lock_cm = None
			got_lock = False
			try:
				from frappe.utils.synchronization import filelock
				lock_cm = filelock("nexum_free_cap", timeout=15)
				lock_cm.__enter__()
				got_lock = True
			except Exception:
				got_lock = False
			try:
				# fresh snapshot under the free-cap lock (sweep C29): the capacity
				# count + dedup re-check must see inserts committed by the previous
				# lock holder, not this transaction's pre-lock read view
				if got_lock:
					try:
						frappe.db.commit()
					except Exception:
						pass
				return _stage_free_lead(
					lead, cap, email, subdomain, plan, ts,
					subdomain_locked=got_subdomain_lock,
				)
			finally:
				if got_lock:
					try:
						lock_cm.__exit__(None, None, None)
					except Exception:
						pass
		elif frappe.cint(frappe.conf.get("auto_approve_trials")):
			approve, reason = _assess_trial_risk(email, subdomain, plan, ts)
			if approve:
				lead.custom_provision_status = "Approved"
				lead.custom_provision_log = "auto-approved: " + reason
				auto = 1
			else:
				lead.custom_provision_status = "Pending"
				lead.custom_provision_log = "HELD for review: " + reason

		# Repeat the early checks at the insertion boundary while the identity lock is
		# held, closing the check-then-insert window for concurrent same-email signups.
		if frappe.db.exists("CRM Lead", {"email": email, "custom_provision_status": ["!=", "Failed"]}):
			return _accepted()
		if subdomain and not got_subdomain_lock:
			lead.custom_provision_status = "Pending"
			lead.custom_provision_log = "HELD for review: subdomain lock unavailable at insert time"
			auto = 0
		if subdomain and _subdomain_taken(subdomain):
			lead.custom_provision_status = "Pending"
			collision_log = "HELD for review: subdomain collision detected at insert time"
			if not got_subdomain_lock:
				lead.custom_provision_log += "; " + collision_log
			else:
				lead.custom_provision_log = collision_log
			auto = 0

		lead.insert(ignore_permissions=True)
		frappe.db.commit()
		return _accepted()
	finally:
		if got_subdomain_lock:
			try:
				subdomain_lock_cm.__exit__(None, None, None)
			except Exception:
				pass
		if got_identity_lock:
			try:
				identity_lock_cm.__exit__(None, None, None)
			except Exception:
				pass


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
	_require_signup_host()  # hq only — never run on a tenant site
	d = frappe.form_dict

	# honeypot: hidden field a human never fills
	if d.get("website") or d.get("hp_url"):
		return {"ok": True}

	email = (d.get("email") or "").strip()
	if not email or len(email) > 120 or not EMAIL_RE.match(email):
		return {"ok": False, "error": "valid email required"}

	# global hourly cap: this endpoint is guest-accessible with NO Turnstile (by design —
	# a blocked visitor must still be capturable), and behind Cloudflare the backend can't
	# see per-client IPs, so cap total captures/hour to stop a bot flooding Pending leads +
	# owner emails. Fail-open: a cache hiccup must never drop a genuine lead.
	try:
		over_cap = _bump_window("nexum_capture", "%Y%m%d%H", 3700) > 40
	except Exception:
		over_cap = False
	if over_cap:
		# lead-table + owner-mailbox flood protection stands, but a REAL prospect
		# past the cap must not vanish (bots eating the first 40 slots used to
		# silently discard customer #41). Known emails just dedup; new ones spill
		# to a durable file the daily signup-funnel digest surfaces for follow-up.
		if frappe.db.exists("CRM Lead", {"email": email, "custom_provision_status": ["!=", "Failed"]}):
			return _accepted()
		return _spill_overflow(d, email)

	# don't duplicate an existing lead (a completed signup, or an earlier capture)
	if frappe.db.exists("CRM Lead", {"email": email, "custom_provision_status": ["!=", "Failed"]}):
		return _accepted()

	company = " ".join((d.get("company") or "").split())[:140]
	plan = (d.get("plan") or "").strip()[:40]
	# This is the "don't lose the prospect" path, so DON'T reject on a bad subdomain —
	# just drop an invalid/reserved one to blank (the owner picks the real name at
	# Approve time anyway). A clean value is still stored verbatim.
	subdomain, sub_ok = _clean_subdomain(d.get("subdomain"))
	if not sub_ok:
		subdomain = ""
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

	# alert the owner so a blocked prospect gets a human follow-up.
	# The lead is already saved above; the email is a best-effort side-channel, so it
	# must NOT be allowed to mailbomb the owner or block a web worker:
	#  * gate it behind a SEPARATE, fail-CLOSED hourly budget (distinct from the
	#    lead-insert cap, which is intentionally fail-open). If the counter can't be
	#    read or the budget is exhausted, skip the email but still keep the lead.
	#  * enqueue it (default now=False) instead of a synchronous SMTP round-trip, so a
	#    guest request never blocks a gunicorn worker for the SMTP latency.
	try:
		alert_ok = _bump_window("nexum_capture_alert", "%Y%m%d%H", 3700) <= 20
	except Exception:
		alert_ok = False  # fail CLOSED: no rate state -> no alert (lead is still recorded)
	if alert_ok:
		try:
			owner = frappe.conf.get("owner_notify_email") or "admin@nexumair.com"
			frappe.sendmail(
				recipients=[owner],
				subject="⚠️ Blocked Nexum Air signup — needs follow-up (%s)" % " ".join((company or email).splitlines()),
				message=(
					"A prospect tried to sign up but the security check was blocked in "
					"their browser, so the form could not complete on its own.<br><br>"
					"<b>Company:</b> %s<br><b>Email:</b> %s<br>"
					"<b>Subdomain:</b> %s<br><b>Plan:</b> %s<br><b>Reason:</b> %s<br><br>"
					"A Pending CRM Lead (<b>%s</b>) was created. Reach out, and if it's "
					"genuine set its provision status to Approved.<br>"
					'<a href="https://hq.nexumair.com/crm/leads/%s">Open in CRM</a>'
					% (escape(company), escape(email), escape(subdomain), escape(plan), escape(reason), lead.name, lead.name)
				),
			)
		except Exception:
			frappe.log_error(
				title="my_branding capture_partial owner alert failed",
				message=frappe.get_traceback(),
			)

	# uniform guest shape (sweep C31) — the landing page only reads .ok
	return _accepted()


OVERFLOW_MAX_BYTES = 1_000_000  # ~4k entries; a sustained bot flood hits this lid, not the disk


def _spill_overflow(d, email):
	"""Durably queue an over-cap capture beacon instead of dropping it.

	Appends a JSON line to sites/<site>/private/capture-overflow.jsonl —
	``private/`` is never web-served and lives on the sites volume, so entries
	survive deploys. signup-funnel.py folds them into the daily digest (escaped
	there — every field here is attacker-controlled) and archives the file.

	EVERY guest outcome returns the uniform _accepted() shape (Codex gate round 2):
	a truthful "throttled" error on the full-file/write-failure paths let an
	attacker fill the file and then enumerate CRM emails — a known email short-
	circuits at the dedup with {ok} while an unknown one reached the error. The
	failure is still loud server-side (Error Log + the file itself in the daily
	digest); the beacon is best-effort by nature and the lead was lost either way."""
	try:
		path = frappe.get_site_path("private", "capture-overflow.jsonl")
		if os.path.exists(path) and os.path.getsize(path) > OVERFLOW_MAX_BYTES:
			# ONE alert per hour (Codex gate round 3): unthrottled, an attacker who
			# filled the bounded file could then mint unlimited Error Log rows —
			# trading a disk cap for a database flood. frappe.cache get/set_value
			# go through make_key, so the latch is site-scoped.
			try:
				if not frappe.cache().get_value("nx_overflow_full_alerted"):
					frappe.cache().set_value("nx_overflow_full_alerted", 1,
					                         expires_in_sec=3600)
					frappe.log_error(
						title="capture overflow file full",
						message="capture-overflow.jsonl over %d bytes — beacons are "
						        "being dropped (latest: %s). Archive the file via the "
						        "funnel digest to resume capture." % (OVERFLOW_MAX_BYTES, email))
			except Exception:
				pass  # alerting must never break the uniform guest response
			return _accepted()
		entry = {
			"ts": str(frappe.utils.now_datetime()),
			"email": email,
			"company": " ".join((d.get("company") or "").split())[:140],
			"plan": (d.get("plan") or "").strip()[:40],
			"subdomain": (d.get("subdomain") or "").strip()[:60],
			"reason": (d.get("reason") or "unknown").strip()[:60],
		}
		with open(path, "a") as fh:
			fh.write(json.dumps(entry) + "\n")
		# uniform guest shape (Codex gate, finding 8): {"ok", "overflow"} vs bare
		# {"ok"} for known emails was the last remaining enumeration oracle
		return _accepted()
	except Exception:
		frappe.log_error(title="capture overflow spill failed", message=frappe.get_traceback())
		return _accepted()


@frappe.whitelist(allow_guest=True)
def check_subdomain(subdomain=None):
	_require_signup_host()  # hq only — never run on a tenant site
	sub = (subdomain or "").strip().lower()

	# Throttle: this is the one guest endpoint without a rate cap, so an
	# unauthenticated dictionary sweep could enumerate tenant existence. Cap
	# checks/hour and return a benign 'busy' instead of an availability verdict once
	# over budget. Fail-open (a cache hiccup must not break the live as-you-type
	# check) — consistent with the other guest endpoints.
	try:
		if _bump_window("nexum_checksub", "%Y%m%d%H", 3700) > 600:
			return {"available": False, "reason": "busy"}
	except Exception:
		pass

	if not SUBDOMAIN_RE.match(sub):
		return {"available": False, "reason": "invalid"}
	if sub in RESERVED_SUBDOMAINS:
		return {"available": False, "reason": "reserved"}

	# Taken = a live/provisioning site only (NOT Pending/Approved pipeline leads), so
	# this public checker can't leak not-yet-live signups' company names.
	if _subdomain_taken(sub, include_pipeline=False):
		return {"available": False, "reason": "taken"}

	return {"available": True}


# ------------------------------------------------------------------ billing ---
# XENDIT-SPEC section 3: the webhook inbox. Xendit POSTs every event here with a
# static shared secret in the x-callback-token header (their scheme — no HMAC).
# The endpoint is DEAD everywhere until ``xendit_webhook_token`` is set in
# site_config, which only ever happens on hq (the Turnstile/is_signup_host
# precedent) — my_branding is installed on every tenant, so an unguarded guest
# endpoint would otherwise listen on every customer subdomain.
#
# In-request work is verification + one Billing Event insert + fast 200. All
# money/lifecycle action happens in the host billing worker (saas/
# billing-worker.py) consuming unprocessed rows — Xendit's own docs recommend
# exactly this queue-then-process split, and it keeps a webhook storm from
# doing anything worse than inserting rows.

# Event types the pipeline understands. Anything else is acknowledged (200 —
# a non-2xx would make Xendit retry an event we will never handle, 6 times)
# but recorded with processed=1 + a note, so it is visible without being work.
XENDIT_EVENT_TYPES = frozenset({
	"payment_session.completed",
	"payment_token.activation",
	# Xendit's dashboard test delivery sends "recurring.plan.activated" (dots,
	# api-version v1, verified live 2026-08-30); docs also show the underscore
	# form — accept both so an API-version drift can't shelve activations.
	"recurring_plan.activated",
	"recurring.plan.activated",
	"recurring.plan.inactivated",
	"recurring.cycle.created",
	"recurring.cycle.succeeded",
	"recurring.cycle.retrying",
	"recurring.cycle.failed",
	"payment.succeeded",
	"payment.failure",
	"payment.capture",
})


def _xendit_event_identity(body):
	"""Stable dedupe key for one Xendit event. Prefer the delivery/event id when
	present; otherwise derive from (event, data.id, data.updated) — Xendit
	re-deliveries carry the same triple, while distinct lifecycle events on the
	same object differ in event or updated."""
	data = body.get("data") or {}
	event_id = body.get("id") or body.get("event_id")
	if event_id:
		return str(event_id)
	return "{0}:{1}:{2}".format(
		body.get("event") or "unknown",
		data.get("id") or "no-object",
		data.get("updated") or body.get("created") or "no-ts",
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def xendit_webhook():
	"""Xendit webhook receiver (hq-only, config-gated). Verify token, dedupe,
	whitelist, insert Billing Event, return fast. NEVER act on money here."""
	import hmac

	configured = frappe.conf.get("xendit_webhook_token")
	if not configured:
		raise frappe.PermissionError("This endpoint is not available on this site.")
	presented = frappe.get_request_header("x-callback-token") or ""
	if not hmac.compare_digest(str(presented), str(configured)):
		frappe.throw("Invalid webhook token.", frappe.PermissionError)

	try:
		body = json.loads(frappe.request.get_data(as_text=True) or "{}")
	except Exception:
		frappe.throw("Malformed payload.", frappe.ValidationError)
	if not isinstance(body, dict):
		frappe.throw("Malformed payload.", frappe.ValidationError)

	event_type = str(body.get("event") or "unknown")[:140]
	event_id = _xendit_event_identity(body)[:140]
	data = body.get("data") or {}
	known = event_type in XENDIT_EVENT_TYPES

	if frappe.db.exists("Billing Event", {"event_id": event_id}):
		return {"ok": True, "duplicate": True}

	doc = frappe.get_doc({
		"doctype": "Billing Event",
		"event_id": event_id,
		"event_type": event_type,
		"reference_id": str(data.get("plan_id") or data.get("reference_id")
			or data.get("id") or "")[:140],
		"payload": json.dumps(body, ensure_ascii=False)[:100000],
		# unknown types are stored pre-processed so the worker never sees them
		"processed": 0 if known else 1,
		"processing_error": None if known else "event type not in pipeline whitelist",
	})
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# two concurrent deliveries of the same event raced past the exists()
		# check — the unique event_id index is the authority; ack the loser so
		# Xendit does not retry a stored event
		return {"ok": True, "duplicate": True}
	return {"ok": True}


# ---------------------------------------------------------- billing: checkout ---
# XENDIT-SPEC sections 3-4 (F1): the pricing page's Subscribe button posts here;
# we create a Xendit SUBSCRIPTION payment session server-side (the secret key
# never reaches the browser) and hand back the hosted checkout URL. Config-gated
# like the webhook: requires BOTH is_signup_host and xendit_secret_key in
# site_config, so the endpoint exists only on hq and only once billing is wired.

XENDIT_API_BASE = "https://api.xendit.co"

# Peso price points per XENDIT-SPEC section 2 — PENDING OWNER/ACCOUNTANT
# CONFIRMATION (flat, VAT stance undecided). One edit point.
XENDIT_PLAN_PRICES_PHP = {
	"Essentials": 2790,
	"Business": 8490,
	"Enterprise": 22740,
}


def _xendit_api(method, path, payload=None):
	"""Minimal Xendit REST call (Basic auth, secret as username). Raises on
	transport errors; returns (status_code, parsed_json)."""
	import requests

	secret = frappe.conf.get("xendit_secret_key")
	resp = requests.request(
		method, XENDIT_API_BASE + path, auth=(secret, ""),
		json=payload, timeout=15,
	)
	try:
		body = resp.json()
	except ValueError:
		body = {}
	return resp.status_code, body


def _xendit_customer_id(subdomain, email):
	"""Create-or-fetch the Xendit customer for a tenant. reference_id is the
	stable identity ``tenant-<subdomain>`` — Xendit rejects reuse on create, so
	a resubscribing tenant is fetched instead (probe-verified 2026-08-30)."""
	ref = "tenant-" + subdomain
	status, body = _xendit_api("POST", "/customers", {
		"reference_id": ref,
		"type": "INDIVIDUAL",
		"email": email,
		"individual_detail": {"given_names": subdomain, "surname": "Nexum Air"},
	})
	if status < 300 and body.get("id"):
		return body["id"]
	# duplicate (or races): fetch by reference
	status, body = _xendit_api("GET", "/customers?reference_id=" + ref)
	rows = body.get("data") or []
	if rows and rows[0].get("id"):
		return rows[0]["id"]
	frappe.throw("Could not establish billing customer.", frappe.ValidationError)


def _next_anchor_date():
	"""First renewal date: one month out, day capped at 28 (Xendit schedule
	limit) — with immediate_payment=true the first charge happens at checkout
	and cycles then run monthly from the anchor."""
	from datetime import date, timedelta

	today = date.today()
	month = today.month % 12 + 1
	year = today.year + (1 if month == 1 else 0)
	return date(year, month, min(today.day, 28)).isoformat() + "T00:00:00Z"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def xendit_checkout():
	"""Create a hosted SUBSCRIPTION checkout for a LIVE tenant and return its
	payment_link_url. Guest-facing (the trial-warning email button / pricing
	page has no session), so: signup-host + secret-key gates, rate limit,
	strict input validation, and the only thing it leaks is a checkout URL."""
	_require_signup_host()
	if not frappe.conf.get("xendit_secret_key"):
		raise frappe.PermissionError("Billing is not enabled on this site.")

	# checkout sessions create real Xendit objects — cap the rate hard
	if _bump_window("nexum_checkout", "%Y%m%d%H", 3700) > 120:
		frappe.throw("Busy — please try again shortly.", frappe.ValidationError)

	d = frappe.form_dict
	sub, sub_ok = _clean_subdomain(d.get("subdomain") or "")
	plan = (d.get("plan") or "").strip().title()
	email = (d.get("email") or "").strip()[:140]
	if not sub or not sub_ok:
		frappe.throw("Invalid subdomain.", frappe.ValidationError)
	if plan not in XENDIT_PLAN_PRICES_PHP:
		frappe.throw("Unknown plan.", frappe.ValidationError)
	if "@" not in email or len(email) < 6:
		frappe.throw("A billing email is required.", frappe.ValidationError)
	# only an already-provisioned, live tenant can subscribe (F1 trial->paid);
	# pay-at-signup (F6) intentionally comes later
	if not _subdomain_taken(sub, include_pipeline=False):
		frappe.throw("Unknown tenant.", frappe.ValidationError)

	# One checkout at a time per tenant, and reuse an unexpired session for the
	# same plan (double-click / two-tab guard): every extra session is another
	# completable payment link at Xendit. Guest checkout also must NEVER touch
	# the live billing mapping (plan/xendit_plan_id/status) — it writes only
	# pending_* fields, and the worker promotes them when Xendit confirms the
	# plan activated. Otherwise anyone who knows a public subdomain could
	# re-point a paying tenant's mapping at an unpaid pending plan and strand
	# its real renewal webhooks.
	from frappe.utils.synchronization import filelock

	with filelock("nexum_checkout:" + sub, timeout=15):
		# banked lock recipe (batch-183): commit right after acquiring so this
		# transaction's snapshot SEES the previous lock holder's committed
		# pending fields, and commit again before release so the next holder
		# sees ours — without this the filelock guards nothing (frappe commits
		# at request end, after the lock is gone)
		frappe.db.commit()
		if frappe.db.exists("Nexum Subscription", sub):
			row = frappe.db.get_value(
				"Nexum Subscription", sub,
				["status", "xendit_plan_id", "pending_plan", "checkout_url",
				 "checkout_expires_on"],
				as_dict=True) or frappe._dict()
			# an already-billing tenant must not be able to open a SECOND
			# recurring plan from the public pricing page — Xendit would
			# happily charge both. Plan changes are a support flow until a
			# real switchover (deactivate-old) UX exists.
			if (row.get("xendit_plan_id")
					and row.get("status") in ("Active", "Retrying")):
				frappe.throw("This tenant already has an active subscription — "
				             "contact support to change plans.",
				             frappe.ValidationError)
			expires = _as_naive_dt(row.get("checkout_expires_on"))
			if (row.get("pending_plan") == plan and row.get("checkout_url")
					and expires and expires > datetime.now()):
				return {"ok": True, "checkout_url": row.checkout_url}
		result = _create_checkout_session(sub, plan, email)
		frappe.db.commit()
		return result


def _as_naive_dt(v):
	"""Datetime column value (datetime from the ORM, string from REST) → naive
	datetime, same server clock the writer used. None when absent/unparsable."""
	if not v:
		return None
	if isinstance(v, datetime):
		return v
	try:
		return datetime.fromisoformat(str(v)[:19])
	except ValueError:
		return None


def _create_checkout_session(sub, plan, email):
	"""Create the Xendit session + persist the pending-checkout mirror fields.
	Caller holds the per-subdomain checkout filelock."""
	customer_id = _xendit_customer_id(sub, email)
	status, session = _xendit_api("POST", "/sessions", {
		"reference_id": "nexum-{0}-{1}".format(sub, frappe.generate_hash(length=8)),
		"session_type": "SUBSCRIPTION",
		"mode": "PAYMENT_LINK",
		"amount": XENDIT_PLAN_PRICES_PHP[plan],
		"currency": "PHP",
		"country": "PH",
		"customer_id": customer_id,
		"subscription": {
			"schedule": {
				"interval": "MONTH",
				"interval_count": 1,
				"anchor_date": _next_anchor_date(),
				"total_retry": 3,
				"retry_interval": "DAY",
				"retry_interval_count": 1,
			},
			"failed_cycle_action": "RESUME",
			"immediate_payment": True,
		},
		"success_return_url": "https://{0}.{1}?subscribed=1".format(sub, BASE_DOMAIN),
		"cancel_return_url": "https://{0}/pricing".format(BASE_DOMAIN),
	})
	if status >= 300 or not session.get("payment_link_url"):
		frappe.log_error(title="my_branding xendit_checkout session failed",
		                 message=json.dumps(session)[:2000])
		frappe.throw("Could not start checkout — please try again.",
		             frappe.ValidationError)

	# mirror the plan->tenant mapping NOW (the session response already carries
	# recurring_plan_id) — but only into the pending_* fields. The live mapping
	# (plan/xendit_plan_id/status) is promoted by the billing worker when the
	# recurring plan actually ACTIVATES, so an unpaid checkout can never
	# displace a paying tenant's mapping (review-gate findings 2/6).
	plan_id = session.get("recurring_plan_id") or ""
	# durable attempt record: the worker resolves EVERY webhook through
	# plan_id -> (tenant, priced tier) here, so an overwritten pending slot,
	# an early paid event, or a superseded plan can always be attributed to
	# the right tenant AND the tier that was actually priced (review-gate
	# round-3 findings 1-3)
	if plan_id and not frappe.db.exists("Billing Checkout Attempt", plan_id):
		frappe.get_doc({
			"doctype": "Billing Checkout Attempt", "plan_id": plan_id,
			"subdomain": sub, "tier": plan,
			"session_id": session.get("payment_session_id") or "",
			"state": "Pending",
		}).insert(ignore_permissions=True)
	pending = {
		"pending_plan": plan,
		"pending_plan_id": plan_id,
		"checkout_session_id": session.get("payment_session_id") or "",
		"checkout_url": session["payment_link_url"],
		# Xendit sessions live ~30 min; refuse to reuse ours a little earlier
		"checkout_expires_on": datetime.now() + timedelta(minutes=25),
		"xendit_customer_id": customer_id,
	}
	if frappe.db.exists("Nexum Subscription", sub):
		frappe.db.set_value("Nexum Subscription", sub, pending)
	else:
		frappe.get_doc(dict(pending, doctype="Nexum Subscription",
		                    subdomain=sub, status="Pending",
		                    )).insert(ignore_permissions=True)

	return {"ok": True, "checkout_url": session["payment_link_url"]}
