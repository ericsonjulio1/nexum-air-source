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
_VER = "20260615b"

_FAVICON = "/assets/my_branding/images/favicon.png"
# Swap the href of any <link rel="icon"|"shortcut icon"> to the Nexum Air favicon.
_FAVICON_RE = re.compile(r'(<link\b[^>]*\brel="(?:shortcut )?icon"[^>]*\bhref=")[^"]*"', re.I)
_TITLE_RE = re.compile(r"<title>.*?</title>", re.I | re.S)
_MARKER = "nexum-spa-brand"


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

		# tab title + favicon for the initial paint (spa-brand.js keeps the title
		# branded across client-side route changes)
		html = _TITLE_RE.sub("<title>%s</title>" % cfg["name"], html, count=1)
		html = _FAVICON_RE.sub(r"\1%s\"" % _FAVICON, html)

		# Per-app brand config for spa-brand.js (which wordmark to swap, etc.).
		brand = json.dumps({"name": cfg["name"], "old": cfg["old"], "extra": cfg.get("extra") or []})
		inject = (
			'<!-- %s -->'
			'<link rel="stylesheet" href="/assets/my_branding/css/spa-brand.css?v=%s">'
			"<script>window.__NEXUM_BRAND__=%s;</script>"
			'<script src="/assets/my_branding/js/spa-brand.js?v=%s"></script>'
		) % (_MARKER, _VER, brand, _VER)
		html = html.replace("</head>", inject + "</head>", 1)
		response.set_data(html)
	except Exception:
		frappe.log_error(
			title="my_branding spa_brand injection failed",
			message=frappe.get_traceback(),
		)
