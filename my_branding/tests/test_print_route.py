"""2026-10-21 miscased print routes answer 404, not 500 — integration tests on a bench site.

Run via:  bench --site <site> run-tests --module my_branding.tests.test_print_route
"""
import unittest
from unittest.mock import patch

import frappe
from frappe.website.page_renderers.not_found_page import NotFoundPage
from frappe.website.page_renderers.print_page import PrintPage
from frappe.website.page_renderers.template_page import TemplatePage
from frappe.website.path_resolver import PathResolver

from my_branding.print_route import MiscasedPrintRoute


class TestMiscasedPrintRoute(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")

	def renderer(self, path):
		# 200 = what frappe.website.serve.get_response passes for a normal request
		return PathResolver(path, 200).resolve()[1]

	def test_registered_ahead_of_frappe_renderers(self):
		self.assertIn(MiscasedPrintRoute, PathResolver.get_custom_page_renderers())

	def test_miscased_doctype_paths_are_not_found(self):
		for path in ("bin/x", "bin/.env", "project/.env", "sales invoice/x", "bin/x/y"):
			r = self.renderer(path)
			self.assertIsInstance(r, MiscasedPrintRoute, path)
			self.assertEqual(r.http_status_code, 404, path)

	def test_exact_case_print_route_unchanged(self):
		for path in ("Bin/x", "Sales Invoice/x"):
			self.assertIs(type(self.renderer(path)), PrintPage, path)

	def test_other_paths_untouched(self):
		# a first part that is no DocType at all, or a single part (`bin` alone raises
		# DoesNotExistError inside resolve, which Frappe already serves as a 404)
		for path in ("login", "nexum-no-such-route/x"):
			self.assertNotIsInstance(self.renderer(path), MiscasedPrintRoute, path)
		self.assertIsInstance(self.renderer("nexum-no-such-route/x"), NotFoundPage)
		for path in ("bin", "login", ""):
			self.assertFalse(MiscasedPrintRoute(path).can_render(), path)

	def test_defers_to_a_renderer_ahead_of_the_print_route(self):
		with patch.object(TemplatePage, "can_render", return_value=True):
			self.assertFalse(MiscasedPrintRoute("bin/x").can_render())
		self.assertTrue(MiscasedPrintRoute("bin/x").can_render())
