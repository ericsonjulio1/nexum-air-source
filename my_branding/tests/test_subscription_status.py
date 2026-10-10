"""Nexum Subscription status 'Cancelled' (v204, host fix M25).

When a deleted tenant's billing mirror is retired, the host billing worker and
trial-lifecycle write status=Cancelled; hq rejected that value until it was a Select
option. A Cancelled mirror must never block the subdomain's next checkout (a
returning customer re-provisioned on the same name).

Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_subscription_status
"""
import json
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import frappe
import frappe.utils.synchronization as sync

from my_branding import api

ORIGINAL_OPTIONS = ["Pending", "Active", "Retrying", "Failed", "Inactive", "Suspended"]
SAVEPOINT = "nx_subscription_status_test"


def _json_options():
	path = frappe.get_app_path(
		"my_branding", "my_branding", "doctype", "nexum_subscription", "nexum_subscription.json"
	)
	with open(path) as f:
		fields = json.load(f)["fields"]
	return next(df for df in fields if df["fieldname"] == "status")["options"].split("\n")


@contextmanager
def _no_lock(*args, **kwargs):
	yield


class TestCancelledOption(unittest.TestCase):
	def test_cancelled_is_appended_after_the_original_options(self):
		# append-only: stored rows and the host writers rely on the existing values
		self.assertEqual(_json_options(), [*ORIGINAL_OPTIONS, "Cancelled"])

	def test_migrated_doctype_accepts_cancelled(self):
		"""What hq's REST write runs: a full save, select options validated."""
		frappe.db.savepoint(SAVEPOINT)
		try:
			doc = frappe.get_doc(
				{"doctype": "Nexum Subscription", "subdomain": "_nx-cancelled-probe", "status": "Cancelled"}
			).insert(ignore_permissions=True)
			self.assertEqual(frappe.db.get_value("Nexum Subscription", doc.name, "status"), "Cancelled")
		finally:
			frappe.db.rollback(save_point=SAVEPOINT)


class TestCheckoutAfterCancellation(unittest.TestCase):
	def _mirror(self, status, plan_id):
		"""The tenant's existing Nexum Subscription row, with no open checkout session."""
		return frappe._dict(
			status=status, xendit_plan_id=plan_id, pending_plan="", checkout_url="", checkout_expires_on=None
		)

	def _checkout(self, row):
		"""Drive xendit_checkout for an existing mirror row; returns (result, sessions)."""
		sessions = []

		def _create(sub, plan, email):
			sessions.append((sub, plan, email))
			return {"ok": True, "checkout_url": "https://checkout.example/new"}

		with ExitStack() as stack:
			for target, name, value in (
				(api, "_require_signup_host", lambda: None),
				(api, "_bump_window", lambda *a, **k: 1),
				(api, "_subdomain_taken", lambda *a, **k: True),  # the re-provisioned live site
				(api, "_create_checkout_session", _create),
				(sync, "filelock", _no_lock),
				(frappe, "conf", frappe._dict(xendit_secret_key="xnd_test")),
				(frappe, "form_dict", frappe._dict(subdomain="acme", plan="Business", email="a@b.co")),
				(frappe.db, "exists", lambda *a, **k: True),
				(frappe.db, "get_value", lambda *a, **k: row),
				(frappe.db, "commit", lambda *a, **k: None),
			):
				stack.enter_context(patch.object(target, name, value))
			return api.xendit_checkout(), sessions

	def test_cancelled_mirror_does_not_block_a_new_checkout(self):
		# the deleted tenant's mirror keeps its old (deactivated) plan id
		result, sessions = self._checkout(self._mirror("Cancelled", "repl_old"))
		self.assertEqual(result, {"ok": True, "checkout_url": "https://checkout.example/new"})
		self.assertEqual(sessions, [("acme", "Business", "a@b.co")])

	def test_retrying_subscription_still_blocks(self):
		with self.assertRaises(frappe.ValidationError):
			self._checkout(self._mirror("Retrying", "repl_live"))
