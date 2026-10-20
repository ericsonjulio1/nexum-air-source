"""A 404, not a 500, for /<doctype>/<name> paths whose doctype has the wrong letter case.

Frappe's print route (website/page_renderers/print_page.py) claims any two-part path whose
first part names a DocType, but frappe.db.exists matches case-insensitively, so /bin/x,
/project/.env and /sales invoice/x reach the print view, which can't import the lowercase
controller: "500 : There was an error building this page" (Frappe 16.52, every site; seen
from scanners probing /bin/.env, /dashboard/.env, ...). The exact-case route (/Bin/x) is
untouched and still answers 403/404 itself.

Registered as a page_renderer, which Frappe tries before its own renderers, so it claims a
path only when no renderer ahead of the print route would serve it.
"""

import frappe
from frappe.website.page_renderers.document_page import DocumentPage
from frappe.website.page_renderers.not_found_page import NotFoundPage
from frappe.website.page_renderers.static_page import StaticPage
from frappe.website.page_renderers.template_page import TemplatePage
from frappe.website.page_renderers.web_form import WebFormPage
from frappe.website.path_resolver import PathResolver

# Frappe's renderers that come before PrintPage in PathResolver.resolve
_AHEAD_OF_PRINT = (StaticPage, WebFormPage, DocumentPage, TemplatePage)


class MiscasedPrintRoute(NotFoundPage):
	def __init__(self, path, http_status_code=None):
		# resolve() hands every renderer the request's status (200 from get_response); built
		# with it, the 404 page answered 200 once served from the page cache, which skips the
		# context that sets 404. Frappe's own fallback, NotFoundPage(endpoint), takes the default.
		super().__init__(path)

	def can_render(self):
		parts = self.request_path.split("/", 1)
		if len(parts) != 2 or not parts[0]:
			return False
		canonical = frappe.db.get_value("DocType", parts[0], "name")  # case-insensitive, like PrintPage
		if not canonical or canonical == parts[0]:
			return False
		others = [r for r in PathResolver.get_custom_page_renderers() if r is not MiscasedPrintRoute]
		return not any(r(self.request_path).can_render() for r in (*others, *_AHEAD_OF_PRINT))
