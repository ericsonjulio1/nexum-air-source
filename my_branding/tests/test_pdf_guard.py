"""PlutoPrint refusal in my_branding.pdf_guard — runs WITHOUT a bench:
    python3 -B -m unittest my_branding.tests.test_pdf_guard -v     (from the repo root)

The module's `frappe` global is replaced by a fake in every test, so the real framework
(when present) is never touched.
"""
import ast
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if "frappe" not in sys.modules:
	try:
		import frappe  # noqa: F401
	except ImportError:
		sys.modules["frappe"] = types.ModuleType("frappe")

from my_branding import pdf_guard  # noqa: E402


class Blocked(Exception):
	pass


class Doc(dict):
	pass


def fake_frappe(form=None, path="/", fields=None, singles=None, rows=None, setter=None):
	f = types.SimpleNamespace()
	f._ = lambda s: s
	f.local = types.SimpleNamespace(form_dict=dict(form or {}), request=types.SimpleNamespace(path=path))

	def throw(msg, title=None):
		raise Blocked(msg)

	f.throw = throw
	f.made, f.cleared, f.set_values, f.set_singles, f.logged = [], [], [], [], []
	f.get_traceback = lambda: "tb"
	f.log_error = lambda **kw: f.logged.append(kw)
	f.clear_cache = lambda **kw: f.cleared.append(kw)
	f.make_property_setter = lambda args, **kw: f.made.append((args, kw))

	def get_value(dt, flt, fld=None, as_dict=False):
		if dt == "DocField":
			return (fields or {}).get(flt["parent"])
		return setter

	f.db = types.SimpleNamespace(
		get_value=get_value,
		get_single_value=lambda dt, fld: (singles or {}).get(dt),
		set_single_value=lambda dt, fld, v: f.set_singles.append((dt, v)),
		set_value=lambda dt, n, fld, v, update_modified=True: f.set_values.append((dt, n, v, update_modified)),
	)
	f.get_all = lambda dt, filters=None, pluck=None: (rows or {}).get(dt, [])
	return f


def print_utils(resolved):
	m = types.ModuleType("frappe.utils.print_utils")
	m._print_format_doc_or_none = lambda name: name
	m.resolve_pdf_generator = lambda pf, explicit=None: resolved(pf, explicit)
	return m


class TestSave(unittest.TestCase):
	def run_save(self, value):
		with mock.patch.object(pdf_guard, "frappe", fake_frappe()):
			pdf_guard.refuse_plutoprint_save(Doc(pdf_generator=value))

	def test_plutoprint_refused_any_case_and_space(self):
		for v in ("PlutoPrint", "plutoprint", " PLUTOPRINT "):
			with self.assertRaises(Blocked, msg=v):
				self.run_save(v)

	def test_other_generators_and_empty_allowed(self):
		for v in ("wkhtmltopdf", "chrome", "Typst", "WeasyPrint", "", None):
			self.run_save(v)


class TestRequest(unittest.TestCase):
	def call(self, form, path, resolved=lambda pf, e: "wkhtmltopdf"):
		f = fake_frappe(form=form, path=path)
		utils = {"frappe.utils.print_utils": print_utils(resolved)}
		with mock.patch.object(pdf_guard, "frappe", f), mock.patch.dict(sys.modules, utils):
			pdf_guard.refuse_plutoprint_request()

	def test_explicit_argument_refused_on_any_path(self):
		for path in ("/api/method/frappe.utils.print_format.download_pdf", "/printview", "/api/method/ping"):
			with self.assertRaises(Blocked, msg=path):
				self.call({"pdf_generator": "PlutoPrint"}, path)

	def test_stored_choice_resolving_to_plutoprint_refused_on_print_paths(self):
		for path in ("/api/method/frappe.utils.print_format.download_pdf", "/printview"):
			with self.assertRaises(Blocked, msg=path):
				self.call({"format": "X"}, path, resolved=lambda pf, e: "PlutoPrint")

	def test_resolution_not_probed_off_print_paths(self):
		def boom(pf, e):
			raise AssertionError("must not resolve")

		self.call({"format": "X"}, "/api/method/ping", resolved=boom)

	def test_safe_generators_pass(self):
		for g in ("wkhtmltopdf", "chrome", "Typst"):
			self.call({"format": "X", "pdf_generator": g}, "/printview", resolved=lambda pf, e, g=g: g)

	def test_probe_failure_does_not_block_printing(self):
		def boom(pf, e):
			raise RuntimeError("db down")

		self.call({"format": "X"}, "/printview", resolved=boom)

	def test_resolver_receives_explicit_and_format(self):
		seen = []
		self.call(
			{"format": "F", "pdf_generator": "chrome"},
			"/printview",
			resolved=lambda pf, e: seen.append((pf, e)) or "chrome",
		)
		self.assertEqual(seen, [("F", "chrome")])


class TestReconcile(unittest.TestCase):
	OPT = {"Print Settings": "wkhtmltopdf\nchrome\nPlutoPrint", "Print Format": "\nwkhtmltopdf\nchrome\nPlutoPrint\nTypst\nWeasyPrint"}

	def test_options_without_blocked_keeps_order_and_blank(self):
		self.assertEqual(pdf_guard.options_without_blocked(self.OPT["Print Format"]), "\nwkhtmltopdf\nchrome\nTypst\nWeasyPrint")
		self.assertEqual(pdf_guard.options_without_blocked(self.OPT["Print Settings"]), "wkhtmltopdf\nchrome")
		self.assertEqual(pdf_guard.options_without_blocked(None), "")

	def run_rec(self, **kw):
		f = fake_frappe(fields=self.OPT, **kw)
		with mock.patch.object(pdf_guard, "frappe", f):
			pdf_guard.reconcile_pdf_generators()
		return f

	def test_creates_system_setters_and_heals(self):
		f = self.run_rec(singles={"Print Settings": "PlutoPrint"}, rows={"Print Format": ["A", "B"]})
		self.assertEqual({a["doctype"] for a, _ in f.made}, {"Print Settings", "Print Format"})
		for args, kw in f.made:
			self.assertEqual((args["fieldname"], args["property"]), ("pdf_generator", "options"))
			self.assertNotIn("PlutoPrint", args["value"])
			self.assertTrue(kw["is_system_generated"])
		self.assertEqual(f.set_singles, [("Print Settings", "wkhtmltopdf")])
		self.assertEqual(f.set_values, [("Print Format", "A", "", False), ("Print Format", "B", "", False)])

	def test_idempotent_when_setter_already_current(self):
		for dt, opt in self.OPT.items():
			wanted = pdf_guard.options_without_blocked(opt)
			f = fake_frappe(fields={dt: opt}, setter=types.SimpleNamespace(value=wanted, is_system_generated=1))
			with mock.patch.object(pdf_guard, "frappe", f):
				pdf_guard.reconcile_pdf_generators()
			self.assertEqual([a for a, _ in f.made if a["doctype"] == dt], [], dt)

	def test_human_setter_not_overwritten(self):
		human = types.SimpleNamespace(value="chrome", is_system_generated=0)
		f = self.run_rec(setter=human)
		self.assertEqual(f.made, [])

	def test_clean_site_no_heal(self):
		f = self.run_rec(singles={"Print Settings": "wkhtmltopdf"})
		self.assertEqual((f.set_singles, f.set_values), ([], []))

	def test_never_raises(self):
		f = fake_frappe(fields=self.OPT)
		f.db.get_value = mock.Mock(side_effect=RuntimeError("x"))
		with mock.patch.object(pdf_guard, "frappe", f):
			pdf_guard.reconcile_pdf_generators()
		self.assertEqual(len(f.logged), 1)


class TestHooks(unittest.TestCase):
	def hooks(self):
		with open(os.path.join(ROOT, "my_branding", "hooks.py")) as fh:
			src = fh.read()
		return src, ast.parse(src)

	def test_hooks_registered(self):
		src, _ = self.hooks()
		for needle in (
			'"Print Settings": {\n\t\t"validate": "my_branding.pdf_guard.refuse_plutoprint_save"',
			'"Print Format": {\n\t\t"validate": "my_branding.pdf_guard.refuse_plutoprint_save"',
			'"my_branding.pdf_guard.refuse_plutoprint_request"',
			'"my_branding.pdf_guard.reconcile_pdf_generators"',
		):
			self.assertIn(needle, src)
		self.assertIn("my_branding.idle_lock.enforce", src)  # existing before_request kept

	def test_every_hook_target_exists(self):
		src, _ = self.hooks()
		for name in ("refuse_plutoprint_save", "refuse_plutoprint_request", "reconcile_pdf_generators"):
			self.assertTrue(callable(getattr(pdf_guard, name)))
			self.assertIn(f"my_branding.pdf_guard.{name}", src)


if __name__ == "__main__":
	unittest.main()
