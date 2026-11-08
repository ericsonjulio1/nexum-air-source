import frappe
from frappe.utils.data import cint

from print_designer.pdf import measure_time
from print_designer.pdf_generator.browser import Browser
from print_designer.pdf_generator.generator import FrappePDFGenerator
from print_designer.pdf_generator.pdf_merge import PDFTransformer


def before_request():
	if frappe.request.path not in (
		"/api/method/frappe.utils.print_format.download_pdf", "/printview"
	):
		return
	from frappe.utils.print_utils import _print_format_doc_or_none, resolve_pdf_generator

	# Use the same format/builder/site precedence as Frappe 16.54. form_dict
	# includes POST parameters; request.args alone silently ignores those choices.
	form = frappe.local.form_dict
	form.pdf_generator = resolve_pdf_generator(
		_print_format_doc_or_none(form.get("format")), form.get("pdf_generator") or None
	)
	if (
		frappe.request.path == "/api/method/frappe.utils.print_format.download_pdf"
		and form.pdf_generator == "chrome"
	):
		# Preserve Print Designer's existing browser lifecycle.
		FrappePDFGenerator()


def after_request():
	if (
		frappe.request.path == "/api/method/frappe.utils.print_format.download_pdf"
		and FrappePDFGenerator._instance
	):
		# Not Heavy operation as if proccess is not available it returns
		if not FrappePDFGenerator().USE_PERSISTENT_CHROMIUM:
			FrappePDFGenerator()._close_browser()


@measure_time
def get_pdf(print_format, html, options, output, pdf_generator=None):
	if pdf_generator != "chrome":
		# Use the default pdf generator
		return
	# scrubbing url to expand url is not required as we have set url.
	# also, planning to remove network requests anyway 🤞
	generator = FrappePDFGenerator()
	browser = None
	try:
		browser = Browser(generator, print_format, html, options)
		transformer = PDFTransformer(browser)
		# transforms and merges header, footer into body pdf and returns merged pdf
		return transformer.transform_pdf(output=output)
	finally:
		if browser is not None:
			generator.remove_browser(browser.browserID)
