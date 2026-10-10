"""Signup de-dup and the subdomain check ignore released CRM Leads (host fix M25, v204).

The host lifecycle moves a deleted tenant's lead to custom_provision_status 'Deleted'.
Like 'Failed', that lead must no longer swallow a new signup for the email or keep the
subdomain taken, so a returning customer can sign up again.

Stub-based: the CRM Lead provisioning fields exist on hq only, so frappe.db.exists
answers from an in-memory lead list and inserts are captured; nothing touches the DB.
Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_signup_dedup
"""
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import frappe

from my_branding import api

EMAIL = "owner@returning-customer.example"


def _matches(value, cond):
	"""One frappe filter condition. Like frappe, a nullable field compares as IFNULL(field, '')."""
	if isinstance(cond, list | tuple) and len(cond) == 2 and cond[0] in ("in", "not in", "!=", "="):
		op, arg = cond
		value = value or ""
		return {
			"in": lambda: value in arg,
			"not in": lambda: value not in arg,
			"!=": lambda: value != arg,
			"=": lambda: value == arg,
		}[op]()
	return value == cond


class _FakeCRM:
	"""Just enough of frappe.db.exists / frappe.new_doc for the signup paths."""

	def __init__(self, *leads):
		self.leads = [dict(lead) for lead in leads]
		self.inserted = []

	def exists(self, doctype, filters=None, *args, **kwargs):
		if doctype == "DocType":
			return filters == "CRM Lead"
		if doctype != "CRM Lead" or not isinstance(filters, dict):
			return None
		for lead in self.leads:
			if all(_matches(lead.get(field), cond) for field, cond in filters.items()):
				return lead.get("name") or "CRM-LEAD-TEST"
		return None

	def new_doc(self, doctype):
		crm = self

		class _Lead(frappe._dict):
			def insert(self, ignore_permissions=False):
				crm.inserted.append(frappe._dict(self))
				crm.leads.append(dict(self))
				return self

		return _Lead(doctype=doctype)


@contextmanager
def _signup_host(crm, **form):
	"""Run as the signup host (hq) with the fake CRM, no Turnstile secret, no rate state."""
	old_form = frappe.local.form_dict
	frappe.local.form_dict = frappe._dict(form)
	with ExitStack() as stack:
		for target, name, value in (
			(frappe, "conf", frappe._dict(is_signup_host=1)),
			(frappe.db, "exists", crm.exists),
			(frappe.db, "commit", lambda *a, **k: None),
			(frappe, "new_doc", crm.new_doc),
			(frappe, "sendmail", lambda *a, **k: None),
			(api, "_bump_window", lambda *a, **k: 1),
			(api, "get_bench_path", lambda: "/nonexistent-nx-test-bench"),
		):
			stack.enter_context(patch.object(target, name, value))
		try:
			yield
		finally:
			frappe.local.form_dict = old_form


def _lead(status, **fields):
	return {"email": EMAIL, "custom_subdomain": "acme", "custom_provision_status": status, **fields}


class TestReleasedStatuses(unittest.TestCase):
	def test_shared_constant(self):
		self.assertEqual(set(api.RELEASED_LEAD_STATUSES), {"Failed", "Deleted"})
		self.assertFalse(set(api.RELEASED_LEAD_STATUSES) & set(api.PIPELINE_LEAD_STATUSES))
		self.assertTrue(set(api.LIVE_LEAD_STATUSES) <= set(api.PIPELINE_LEAD_STATUSES))

	def test_released_leads_no_longer_hold_the_email(self):
		for status, holds in (
			("Deleted", False),
			("Failed", False),
			("Pending", True),
			("Approved", True),
			("Provisioning", True),
			("Active", True),
			(None, True),  # never released by accident: a status-less lead still holds it
		):
			with self.subTest(status=status), _signup_host(_FakeCRM(_lead(status))):
				self.assertEqual(api._lead_holds_email(EMAIL), holds)

	def test_deleted_lead_frees_the_subdomain(self):
		for status, in_pipeline, live in (
			("Deleted", False, False),
			("Failed", False, False),
			("Pending", True, False),
			("Active", True, True),
		):
			with self.subTest(status=status), _signup_host(_FakeCRM(_lead(status))):
				self.assertEqual(api._subdomain_taken("acme"), in_pipeline)
				self.assertEqual(api._subdomain_taken("acme", include_pipeline=False), live)


class TestReturningCustomer(unittest.TestCase):
	def _signup(self, crm, plan):
		with _signup_host(crm, email=EMAIL, subdomain="acme", plan=plan, company="Acme"):
			return api.signup()

	def test_signup_after_tenant_deleted_creates_a_new_lead(self):
		for plan in ("free", "starter"):  # _stage_free_lead and the paid-trial path
			crm = _FakeCRM(_lead("Deleted"), _lead("Failed"))
			with self.subTest(plan=plan):
				self.assertEqual(self._signup(crm, plan), {"ok": True})
				self.assertEqual(len(crm.inserted), 1)
				new = crm.inserted[0]
				self.assertEqual((new.email, new.custom_subdomain, new.custom_plan), (EMAIL, "acme", plan))
				# the deleted tenant's lead does not make its own subdomain a collision
				self.assertNotIn("collision", new.get("custom_provision_log") or "")

	def test_live_lead_still_swallows_a_repeat_signup(self):
		crm = _FakeCRM(_lead("Active"))
		self.assertEqual(self._signup(crm, "free"), {"ok": True})
		self.assertEqual(crm.inserted, [])

	def test_post_lock_recheck_still_catches_a_racer(self):
		"""A Deleted lead passes the early check; a concurrent signup for the same email
		commits while this one verifies Turnstile: the re-check under the lock must see it."""
		for plan in ("free", "starter"):
			crm = _FakeCRM(_lead("Deleted"))

			def racer_commits(token, crm=crm):
				crm.leads.append(_lead("Pending", name="CRM-LEAD-RACER"))
				return "skip"

			with self.subTest(plan=plan), patch.object(api, "_verify_turnstile", racer_commits):
				self.assertEqual(self._signup(crm, plan), {"ok": True})
				self.assertEqual(crm.inserted, [])

	def test_capture_after_tenant_deleted_records_the_prospect(self):
		crm = _FakeCRM(_lead("Deleted"))
		with _signup_host(crm, email=EMAIL, subdomain="acme", plan="free", reason="widget-blocked"):
			self.assertEqual(api.capture_partial(), {"ok": True})
		self.assertEqual(len(crm.inserted), 1)
		self.assertEqual(crm.inserted[0].custom_provision_status, "Pending")
