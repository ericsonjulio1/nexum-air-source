"""SPA favicon rewrite emits the exact _FAVICON href (no stray backslash). No bench needed."""
import sys
import types
import unittest

if "frappe" not in sys.modules:
	try:
		import frappe  # noqa: F401
	except ImportError:
		stub = types.ModuleType("frappe")
		stub.conf = {}
		stub.session = types.SimpleNamespace(user="Guest")
		stub.log_error = lambda **kw: None
		stub.get_traceback = lambda: ""
		sys.modules["frappe"] = stub

from my_branding import spa_brand  # noqa: E402
from my_branding.tests.test_spa_pulse_guard import run_hook  # noqa: E402

PAGE = (
	'<!DOCTYPE html><html><head><title>CRM</title>'
	'<link rel="icon" type="image/png" href="/assets/crm/favicon.png">'
	'<link rel="shortcut icon" href="/x.ico"></head><body></body></html>'
)


class TestSpaFavicon(unittest.TestCase):
	def test_rewritten_href_equals_favicon_exactly(self):
		out = run_hook("/crm", PAGE)
		self.assertNotIn("\\", out)
		self.assertIn('href="%s"' % spa_brand._FAVICON, out)
		self.assertEqual(out.count('href="%s"' % spa_brand._FAVICON), 2)
		self.assertTrue(spa_brand._FAVICON.endswith("?v=20261117-perf"))


if __name__ == "__main__":
	unittest.main()
