"""Pulse import-map guard in my_branding.spa_brand — runs WITHOUT a bench:
    python3 -B -m unittest my_branding.tests.test_spa_pulse_guard -v     (from the repo root)

Uses a stub `frappe` when real frappe is absent; on a bench the real module is used.
"""
import json
import os
import re
import subprocess
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

P = spa_brand.PULSE_CLIENT_URL
PAGE = '<!DOCTYPE html><html><head>\n<meta charset="UTF-8"><script type="module" src="/a.js"></script></head><body></body></html>'


class FakeResponse:
	def __init__(self, html, mimetype="text/html"):
		self.html, self.mimetype = html, mimetype

	def get_data(self, as_text=False):
		return self.html

	def set_data(self, d):
		self.html = d


def run_hook(path, html, mimetype="text/html"):
	r = FakeResponse(html, mimetype)
	spa_brand.inject_brand_assets(r, types.SimpleNamespace(path=path))
	return r.html


class TestPulseGuard(unittest.TestCase):
	def test_first_child_of_head(self):
		out = spa_brand.inject_pulse_guard(PAGE)
		m = re.search(r"<head>(<script type=\"importmap\">.*?</script>)", out)
		self.assertIsNotNone(m)
		self.assertEqual(json.loads(re.search(r">(.*)<", m.group(1)).group(1)),
			{"imports": {P: spa_brand.PULSE_NOOP_URL}})
		self.assertLess(out.index("importmap"), out.index('type="module"'))

	def test_head_with_attributes_and_header_tag(self):
		out = spa_brand.inject_pulse_guard('<html><head lang="en"><title>x</title></head><body><header></header></body></html>')
		self.assertTrue(out.startswith('<html><head lang="en"><script type="importmap">'))

	def test_idempotent(self):
		once = spa_brand.inject_pulse_guard(PAGE)
		self.assertEqual(spa_brand.inject_pulse_guard(once), once)
		self.assertEqual(once.count(P), 1)

	def test_existing_crm_map_left_alone(self):
		crm = '<html><head><script type="importmap">{"imports":{"%s":"/assets/crm/frontend/nexum-pulse-client-noop.js"}}</script></head></html>' % P
		self.assertEqual(spa_brand.inject_pulse_guard(crm), crm)

	def test_existing_other_map_merged_not_duplicated(self):
		src = '<html><head><meta charset="utf-8"><script type="importmap">{"imports":{"vue":"/vue.js"}}</script><script type="module" src="/m.js"></script></head></html>'
		out = spa_brand.inject_pulse_guard(src)
		self.assertEqual(out.count("importmap"), 1)
		data = json.loads(re.search(r"importmap\">(.*?)</script>", out).group(1))
		self.assertEqual(data["imports"], {"vue": "/vue.js", P: spa_brand.PULSE_NOOP_URL})
		self.assertEqual(spa_brand.inject_pulse_guard(out), out)

	def test_unparseable_existing_map_gets_separate_first_map(self):
		src = '<html><head><script type="importmap">{oops</script></head></html>'
		out = spa_brand.inject_pulse_guard(src)
		self.assertTrue(out.startswith('<html><head><script type="importmap">{"imports"'))
		self.assertEqual(out.count(P), 1)

	def test_no_head_untouched(self):
		self.assertEqual(spa_brand.inject_pulse_guard("<html><body>x</body></html>"), "<html><body>x</body></html>")

	def test_hook_all_spa_routes(self):
		self.assertTrue(spa_brand.SPA_BRAND)
		for route in spa_brand.SPA_BRAND:
			out = run_hook(route + "/x", PAGE)
			self.assertRegex(out, r"<head><script type=\"importmap\">", route)
			self.assertEqual(out.count(P), 1, route)
			self.assertIn("nexum-spa-brand", out)
			self.assertLess(out.index("importmap"), out.index("spa-brand.js"))

	def test_hook_non_spa_untouched(self):
		self.assertEqual(run_hook("/app/home", PAGE), PAGE)
		self.assertEqual(run_hook("/crmx", PAGE), PAGE)

	def test_hook_non_html_untouched(self):
		js = '{"head":"<head></head>"}'
		self.assertEqual(run_hook("/crm", js, "application/json"), js)

	def test_hook_second_pass_no_duplicate(self):
		once = run_hook("/helpdesk", PAGE)
		self.assertEqual(run_hook("/helpdesk", once), once)


class TestNoopModule(unittest.TestCase):
	def setUp(self):
		self.src = open(os.path.join(ROOT, "my_branding/public/js/nexum-pulse-noop.js")).read()
		self.assertTrue(spa_brand.PULSE_NOOP_URL.startswith("/assets/my_branding/js/nexum-pulse-noop.js"))

	def test_exports_and_inert_shape(self):
		self.assertIn("export class PulseClient", self.src)
		for needle in ("async init() { return false; }", "stop() {}", "capture() {}", "getDistinctId() { return ''; }"):
			self.assertIn(needle, self.src)
		for banned in ("fetch(", "XMLHttpRequest", "sendBeacon", "http://", "https://", "import("):
			self.assertNotIn(banned, self.src)

	def test_behaviour_under_node(self):
		node = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
		if not node:
			self.skipTest("node not available")
		js = ("import('%s').then(async m=>{const c=new m.PulseClient({});"
			"if(await c.init()!==false||c.getDistinctId()!==''||c.stop()!==undefined||c.capture('x')!==undefined)process.exit(1)})"
			% ("file://" + os.path.join(ROOT, "my_branding/public/js/nexum-pulse-noop.js")))
		r = subprocess.run([node, "--input-type=commonjs", "-e", js], capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stderr)


class TestVerifyScript(unittest.TestCase):
	def test_check_pass_and_fail(self):
		sys.path.insert(0, os.path.join(ROOT, "saas"))
		import verify_pulse_guard as v
		self.assertEqual(v.check(spa_brand.inject_pulse_guard(PAGE))[0], "PASS")
		self.assertEqual(v.check(PAGE.replace("</head>", '<script>/*pulse*/</script></head>'))[0], "FAIL")
		late = '<html><head><script src="/a.js"></script><script type="importmap">{"imports":{"%s":"/n.js"}}</script></head></html>' % P
		self.assertEqual(v.check(late)[0], "FAIL")
		remote = '<html><head><script type="importmap">{"imports":{"%s":"https://x/n.js"}}</script></head></html>' % P
		self.assertEqual(v.check(remote)[0], "FAIL")


class TestVerifierRoutesMatchBrandConfig(unittest.TestCase):
	"""verify_pulse_guard.DEFAULT_ROUTES must track the routes spa_brand actually guards
	(every brand_config app with a route; _match() is by route prefix)."""

	def _verifier(self):
		import importlib.util
		spec = importlib.util.spec_from_file_location("verify_pulse_guard_bc", os.path.join(ROOT, "saas", "verify_pulse_guard.py"))
		m = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(m)
		return m

	def test_default_routes_match_brand_config(self):
		from my_branding import brand_config
		routes = list(self._verifier().DEFAULT_ROUTES)
		guarded = {cfg["route"] for cfg in brand_config.APPS.values() if cfg.get("route")}
		self.assertEqual(guarded, set(spa_brand.SPA_BRAND))
		for app in ("crm", "helpdesk", "insights", "drive", "gameplan", "hrms", "lms", "builder"):
			self.assertIn(brand_config.APPS[app]["route"], routes, app)
		self.assertNotIn("/gameplan", routes)
		self.assertEqual(len(routes), len(set(routes)))
		self.assertEqual(set(routes), guarded)


if __name__ == "__main__":
	unittest.main()
