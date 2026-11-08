import json
import re

import frappe

from my_branding import brand_config

# The standalone frappe-ui SPAs (Frappe HR/CRM/Helpdesk/Drive/Insights/Builder/
# Gameplan/LMS) each serve their OWN full HTML document that does NOT extend
# Frappe's web.html, so `web_include_css` / brand.css never reaches them and
# everything inside reverts to the native Frappe look. We can't fix that from
# inside those apps without editing their source (un-maintainable across
# updates), so instead we post-process their rendered HTML in the after_request
# hook: inject a Nexum Air brand stylesheet + script, and rewrite the tab title
# and favicon. This touches ZERO app source, so it survives every app update.
#
#   name = the brand tab title + the wordmark text we paint in
#   old  = the native string ("Frappe X") to replace in title + body text
# Derived from brand_config (one source of truth): route -> {name, old}.
SPA_BRAND = brand_config.spa_brand()

# Bump when editing spa-brand.css / spa-brand.js (the SPA service worker + HTTP
# layer cache them aggressively).
_VER = "20261024-maintenance222"  # Refresh cached SPA branding after the maintenance fixes.

_FAVICON = "/assets/my_branding/images/favicon.png"
# Swap the href of any <link rel="icon"|"shortcut icon"> to the Nexum Air favicon.
_FAVICON_RE = re.compile(r'(<link\b[^>]*\brel="(?:shortcut )?icon"[^>]*\bhref=")[^"]*"', re.I)
_TITLE_RE = re.compile(r"<title>.*?</title>", re.I | re.S)
_MARKER = "nexum-spa-brand"
_DEMO_THEME_RESET = '<script>try{localStorage.setItem("theme","light")}catch(e){}</script>'


# Owner rule (2026-11-04): Nexum Air must not load remote telemetry. The frappe-ui
# telemetry plugin bundled into the SPAs does `await import(<pulse client url>)` on
# every load, before any enabled check. Remap that remote URL to an inert same-origin
# module with an import map placed as the FIRST child of <head> (import maps only
# affect module scripts that run after them). Needs no rebuild of any SPA.
PULSE_CLIENT_URL = "https://pulse.m.frappe.cloud/assets/pulse/js/pulse_client.js"
PULSE_NOOP_URL = "/assets/my_branding/js/nexum-pulse-noop.js?v=20261107"
_HEAD_OPEN_RE = re.compile(r"<head(?=[\s>])[^>]*>", re.I)
_IMPORTMAP_RE = re.compile(
	r"(<script\b[^>]*\btype=[\"']?importmap[\"']?[^>]*>)(.*?)(</script>)", re.I | re.S
)


def inject_pulse_guard(html):
	"""Return `html` with the Pulse client import map guaranteed (idempotent).

	- An existing import map already mapping PULSE_CLIENT_URL is left as is (CRM's
	  build-time one).
	- Else an existing parseable import map in <head> gets the entry merged in.
	- Else a new import map is inserted right after the opening <head> tag.
	"""
	head = _HEAD_OPEN_RE.search(html)
	if not head:
		return html
	end = html.find("</head>", head.end())
	scope = html[head.end(): end if end != -1 else len(html)]
	for m in _IMPORTMAP_RE.finditer(scope):
		if PULSE_CLIENT_URL in m.group(2):
			return html
	for m in _IMPORTMAP_RE.finditer(scope):
		try:
			data = json.loads(m.group(2))
			if not isinstance(data, dict) or not isinstance(data.get("imports", {}), dict):
				continue
		except ValueError:
			continue
		data.setdefault("imports", {})[PULSE_CLIENT_URL] = PULSE_NOOP_URL
		merged = m.group(1) + json.dumps(data, separators=(",", ":")) + m.group(3)
		a = head.end() + m.start()
		return html[:a] + merged + html[head.end() + m.end():]
	tag = '<script type="importmap">%s</script>' % json.dumps(
		{"imports": {PULSE_CLIENT_URL: PULSE_NOOP_URL}}, separators=(",", ":")
	)
	return html[: head.end()] + tag + html[head.end():]


def _match(path):
	for prefix, cfg in SPA_BRAND.items():
		if path == prefix or path.startswith(prefix + "/"):
			return cfg
	return None


def inject_brand_assets(response, request):
	"""after_request hook — paint Nexum Air branding onto the standalone frappe-ui
	SPAs by rewriting their server-rendered HTML.

	Hardened: matches fast, bails on anything unexpected; any exception leaves the
	original response untouched (worst case the SPA looks native for that one
	request). It can never 500 a page load.
	"""
	try:
		path = getattr(request, "path", "") or ""
		cfg = _match(path)
		if not cfg:
			return
		if (getattr(response, "mimetype", "") or "") != "text/html":
			return

		html = response.get_data(as_text=True)
		if not html or _MARKER in html or "</head>" not in html:
			return

		try:
			html = inject_pulse_guard(html)
		except Exception:
			frappe.log_error(title="my_branding pulse guard failed", message=frappe.get_traceback())

		# tab title + favicon for the initial paint (spa-brand.js keeps the title
		# branded across client-side route changes)
		html = _TITLE_RE.sub("<title>%s</title>" % cfg["name"], html, count=1)
		html = _FAVICON_RE.sub(r"\1%s\"" % _FAVICON, html)

		# Per-app brand config for spa-brand.js (which wordmark to swap, etc.).
		theme, csrf = "Light", None
		if frappe.session.user != "Guest":
			theme = frappe.db.get_value("User", frappe.session.user, "desk_theme") or "Light"
			csrf = frappe.sessions.get_csrf_token()
		if frappe.conf.get("is_demo_site"):
			theme, csrf = "Light", None
		brand = json.dumps({"name": cfg["name"], "old": cfg["old"], "extra": cfg.get("extra") or [],
			"theme": theme, "theme_csrf": csrf})
		inject = (
			'<!-- %s -->'
			'<link rel="stylesheet" href="/assets/my_branding/css/spa-brand.css?v=%s">'
			"<script>window.__NEXUM_BRAND__=%s;</script>"
			'<link rel="stylesheet" href="/assets/my_branding/css/report-theme.css?v=20261016d">'
			'<script src="/assets/my_branding/js/suite-theme.js?v=20261016-audit215r2"></script>'
			'<script src="/assets/my_branding/js/report-theme.js?v=20261016b"></script>'
			'<script src="/assets/my_branding/js/spa-brand.js?v=%s"></script>'
		) % (_MARKER, _VER, brand, _VER)
		if frappe.conf.get("is_demo_site"):
			# the public demo must always show the branded LIGHT look: frappe-ui apps
			# (CRM/HR/Helpdesk/…) read `localStorage.theme`, so a visitor who once flipped
			# the in-app toggle (or a shared browser) would see a dark CRM next to the
			# light desk. Reset it before the app bundle reads it; real tenants keep
			# their own choice.
			inject = _DEMO_THEME_RESET + inject
		html = html.replace("</head>", inject + "</head>", 1)
		response.set_data(html)
	except Exception:
		frappe.log_error(
			title="my_branding spa_brand injection failed",
			message=frappe.get_traceback(),
		)
