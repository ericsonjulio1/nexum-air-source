"""Native MariaDB/permission checks with real temporary tenant identity files.

Provider transport alone is simulated. Checkout commits are real; fixtures have
unique names and explicit cleanup because a savepoint cannot span those commits.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import traceback
import unittest
from unittest.mock import patch
import uuid

import frappe

from my_branding import api, billing_lifecycle as billing


class TestBillingLifecycleIntegration(unittest.TestCase):
    def setUp(self):
        self.assertTrue(str(frappe.local.site).endswith(".localhost") and frappe.conf.get("allow_tests"),
                        "Requires an isolated localhost test site")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, self.previous_user)
        self.sub = "identity-" + uuid.uuid4().hex[:12]
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.directory = self.root / "sites" / (self.sub + ".nexumair.com")
        self.directory.mkdir(parents=True)
        self.config = self.directory / "site_config.json"
        self.generation("a" * 32)
        self.stack.enter_context(patch.object(billing, "get_bench_path", return_value=str(self.root)))
        self.stack.enter_context(patch.object(api, "get_bench_path", return_value=str(self.root)))
        self.stack.enter_context(patch.dict(frappe.conf, is_signup_host=1, xendit_secret_key="synthetic-disabled"))
        self.addCleanup(self.cleanup_records)

    def generation(self, value, **values):
        self.config.write_text(json.dumps(dict(nexum_tenant_generation=value, **values)))

    def cleanup_records(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for doctype in ("Billing Paid Cycle", "Billing Checkout Attempt", "Nexum Subscription"):
            frappe.db.delete(doctype, {"subdomain": self.sub})
        frappe.db.commit()

    def mirror(self, **fields):
        row = billing.prepare_checkout(self.sub)
        if fields:
            frappe.db.set_value("Nexum Subscription", self.sub, fields)
            row.update(fields)
        return row

    def attempt(self, label, **fields):
        plan = self.sub + "-" + label
        frappe.get_doc(dict(doctype="Billing Checkout Attempt", plan_id=plan, subdomain=self.sub,
                            tenant_generation="a" * 32, state="Pending", **fields)).insert()
        return plan

    def test_reused_name_archives_old_mirror_and_rejects_old_generation_writes(self):
        old_plan = self.sub + "-old"
        self.mirror(plan="Enterprise", status="Active", paid_until="2030-01-01", xendit_plan_id=old_plan)
        self.generation("b" * 32)
        replacement = billing.prepare_checkout(self.sub)
        self.assertEqual(replacement.tenant_generation, "b" * 32)
        self.assertFalse(replacement.paid_until)
        self.assertFalse(replacement.xendit_plan_id)
        history = json.loads(replacement.previous_generations)
        self.assertEqual(history[-1]["tenant_generation"], "a" * 32)
        self.assertEqual(history[-1]["paid_until"], "2030-01-01")
        self.assertTrue(frappe.db.get_value("Billing Checkout Attempt", old_plan, "needs_deactivation"))
        with self.assertRaises(frappe.ValidationError):
            billing.update_subscription(self.sub, "a" * 32, {"status": "Active", "paid_until": "2031-01-01"})
        self.assertEqual(frappe.db.get_value("Nexum Subscription", self.sub, "status"), "Pending")

    def test_closure_tracks_all_pending_plans_and_blocks_checkout_and_activation(self):
        self.mirror()
        one, two = self.attempt("one"), self.attempt("two")
        closed = billing.close_checkout(self.sub, "a" * 32)
        self.assertEqual({p.plan_id for p in closed["plans"]}, {one, two})
        for plan in (one, two):
            self.assertTrue(frappe.db.get_value("Billing Checkout Attempt", plan, "needs_deactivation"))
        with self.assertRaises(frappe.ValidationError):
            billing.prepare_checkout(self.sub)
        with self.assertRaises(frappe.ValidationError):
            billing.update_subscription(self.sub, "a" * 32, {"status": "Active"})
        with self.assertRaises(frappe.ValidationError):
            billing.activate_subscription(self.sub, "a" * 32, one, "",
                                           {"status": "Active", "xendit_plan_id": one})
        self.assertTrue(frappe.db.get_value("Billing Checkout Attempt", one, "needs_deactivation"))
        billing.update_subscription(self.sub, "a" * 32, {"status": "Cancelled"})
        self.generation("b" * 32)
        billing.prepare_checkout(self.sub)
        with self.assertRaises(frappe.ValidationError):
            billing.update_subscription(self.sub, "a" * 32, {"status": "Cancelled"})
        self.assertEqual(frappe.db.get_value("Nexum Subscription", self.sub, "status"), "Pending")

    def test_never_subscribed_tenant_closes_and_cancels_without_provider_work(self):
        self.assertFalse(frappe.db.exists("Nexum Subscription", self.sub))
        closed = billing.close_checkout(self.sub, "a" * 32)
        self.assertEqual(closed["plans"], [])
        billing.update_subscription(self.sub, "a" * 32, {"status": "Cancelled", "last_event": "tenant-deleted"})
        frappe.db.commit()
        row = frappe.get_doc("Nexum Subscription", self.sub)
        self.assertEqual(row.status, "Cancelled")
        self.assertTrue(row.billing_closed)
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": "Nexum Subscription", "docname": self.sub}))

    def test_activation_retires_all_other_same_generation_attempts(self):
        old, abandoned, chosen = self.attempt("old"), self.attempt("abandoned"), self.attempt("chosen")
        foreign = self.attempt("prior-generation")
        frappe.db.set_value("Billing Checkout Attempt", foreign, "tenant_generation", "b" * 32)
        self.mirror(xendit_plan_id=old)
        result = billing.activate_subscription(self.sub, "a" * 32, chosen, old,
                                               {"status": "Active", "xendit_plan_id": chosen})
        self.assertEqual(set(result["deactivate"]), {old, abandoned})
        self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", abandoned, "state"), "Superseded")
        self.assertTrue(frappe.db.get_value("Billing Checkout Attempt", abandoned, "needs_deactivation"))
        self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", foreign, "state"), "Pending")
        with self.assertRaises(frappe.ValidationError):
            billing.activate_subscription(self.sub, "a" * 32, abandoned, chosen,
                                           {"status": "Active", "xendit_plan_id": abandoned})
        later = self.attempt("later-checkout")
        repeated = billing.activate_subscription(self.sub, "a" * 32, chosen, chosen,
                                                 {"status": "Active", "xendit_plan_id": chosen})
        self.assertEqual(repeated["deactivate"], [])
        self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", later, "state"), "Pending")

    def test_native_cleanup_query_selects_untouched_attempts_before_failed_retries(self):
        from my_branding.tests.test_billing_queue_integration import NativeHQ
        hq = NativeHQ(dict(HQ_URL="https://fixture.example.invalid", API_KEY="synthetic", API_SECRET="synthetic"))
        self.assertFalse(hq.attempts_needing_deactivation(), "Requires isolated cleanup queue")
        plans = [self.attempt("cleanup-%02d" % index, needs_deactivation=1) for index in range(25)]
        first = hq.attempts_needing_deactivation()
        self.assertEqual(len(first), 20)
        for row in first:
            frappe.db.set_value("Billing Checkout Attempt", row.name, "deactivation_attempted_on", "2030-01-01")
        untouched = set(plans) - {row.name for row in first}
        self.assertEqual({row.name for row in hq.attempts_needing_deactivation()[:5]}, untouched)
        index = frappe.db.sql("SHOW INDEX FROM `tabBilling Checkout Attempt` "
                               "WHERE Key_name='billing_attempt_cleanup_order'", as_dict=True)
        self.assertEqual([row.Column_name for row in sorted(index, key=lambda row: row.Seq_in_index)],
                          ["needs_deactivation", "deactivation_attempted_on", "creation"])

    def test_legacy_financial_ownership_is_not_automatically_bound(self):
        frappe.get_doc(dict(doctype="Nexum Subscription", subdomain=self.sub,
                            xendit_plan_id=self.sub + "-legacy", status="Cancelled")).insert()
        with self.assertRaises(frappe.ValidationError):
            billing.prepare_checkout(self.sub)
        self.assertFalse(frappe.db.get_value("Nexum Subscription", self.sub, "tenant_generation"))

    def test_missing_site_can_be_cancelled_but_not_activated(self):
        self.mirror()
        self.config.unlink()
        self.directory.rmdir()
        self.assertEqual(billing.tenant_context(self.sub)["state"], "missing")
        with self.assertRaises(frappe.ValidationError):
            billing.update_subscription(self.sub, "a" * 32, {"status": "Active"})
        billing.update_subscription(self.sub, "a" * 32, {"status": "Cancelled"})

    def test_provisioning_site_cannot_open_checkout(self):
        self.generation("a" * 32, nexum_billing_ready=0)
        self.assertEqual(billing.tenant_context(self.sub)["state"], "unbound")
        with self.assertRaises(frappe.ValidationError):
            billing.prepare_checkout(self.sub)

    def test_migration_assigns_identity_once_and_never_rebinds_invalid_identity(self):
        from my_branding.tenant_identity import ensure_current_generation, UnboundGeneration, valid_generation

        def write_config(key, value):
            self.config.write_text(json.dumps({key: value}))

        with patch.dict(frappe.conf, nexum_tenant_generation=None), \
                patch("frappe.installer.update_site_config", side_effect=write_config) as write:
            ensure_current_generation()
            first = json.loads(self.config.read_text())["nexum_tenant_generation"]
            self.assertTrue(valid_generation(first))
            ensure_current_generation()
            write.assert_called_once()
            frappe.conf.nexum_tenant_generation = "invalid-existing-identity"
            with self.assertRaises(UnboundGeneration):
                ensure_current_generation()
            self.assertEqual(json.loads(self.config.read_text())["nexum_tenant_generation"], first)

    def test_guest_cannot_use_worker_mutation_or_identity_endpoints(self):
        self.mirror()
        frappe.set_user("Guest")
        for operation in (lambda: billing.tenant_context(self.sub),
                          lambda: billing.close_checkout(self.sub, "a" * 32),
                          lambda: billing.activate_subscription(self.sub, "a" * 32, "plan", "",
                                                                 {"status": "Active", "xendit_plan_id": "plan"}),
                          lambda: billing.update_subscription(self.sub, "a" * 32, {"status": "Active"})):
            with self.assertRaises(frappe.PermissionError):
                operation()

    def test_http_worker_updates_commit_before_response_and_reject_guests(self):
        """Exercise token auth, HTTP dispatch and Frappe's actual commit boundary."""
        from frappe.app import application
        from werkzeug.test import Client
        from werkzeug.wrappers import Response

        self.mirror()
        plan = self.attempt("http")
        user_name = self.sub + "@example.invalid"
        key, secret = uuid.uuid4().hex, uuid.uuid4().hex
        user = frappe.get_doc(dict(doctype="User", email=user_name, first_name="HTTP fixture",
                                   send_welcome_email=0, user_type="System User",
                                   roles=[{"role": "System Manager"}], api_key=key, api_secret=secret)).insert()
        self.addCleanup(lambda: (frappe.delete_doc("User", user.name, force=True), frappe.db.commit()))
        frappe.db.commit()
        site = frappe.local.site

        def post(method, fields, authenticated=True):
            responses, errors = [], []

            def request():
                try:
                    client = Client(application, Response)
                    headers = {"Authorization": "token " + key + ":" + secret} if authenticated else {}
                    # Request-local config is initialized by the WSGI stack.
                    responses.append(client.post("/api/method/my_branding.billing_lifecycle." + method,
                                                 base_url="http://" + site, json=fields, headers=headers))
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    frappe.destroy()

            thread = threading.Thread(target=request)
            thread.start()
            thread.join(20)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            frappe.db.rollback()  # Observe from a new database snapshot.
            return responses[0]

        identity = dict(subdomain=self.sub, tenant_generation="a" * 32)
        # Persist the HQ flag in the disposable site's config only for this request
        # via init hooks; no production config or provider settings are changed.
        original_init = frappe.init

        def init(*args, **kwargs):
            result = original_init(*args, **kwargs)
            frappe.conf.is_signup_host = 1
            return result

        with patch.object(frappe, "init", side_effect=init):
            response = post("update_subscription", dict(identity, fields={"paid_until": "2031-02-03"}))
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(str(frappe.db.get_value("Nexum Subscription", self.sub, "paid_until")), "2031-02-03")
            response = post("activate_subscription", dict(identity, plan_id=plan, expected_plan_id="",
                            fields={"status": "Active", "xendit_plan_id": plan}))
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", plan, "state"), "Activated")
            response = post("close_checkout", identity)
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertTrue(frappe.db.get_value("Nexum Subscription", self.sub, "billing_closed"))
            self.assertTrue(frappe.db.get_value("Billing Checkout Attempt", plan, "needs_deactivation"))
            response = post("update_subscription", dict(identity, fields={"status": "Cancelled"}), False)
            self.assertIn(response.status_code, (401, 403))
            self.assertEqual(frappe.db.get_value("Nexum Subscription", self.sub, "status"), "Active")

    def test_guarded_updates_validate_fields_and_preserve_financial_audit_history(self):
        self.mirror()
        for fields in ({"status": "Imaginary"}, {"plan": "Unpriced"}, {"paid_until": "invalid-date"},
                       {"xendit_plan_id": "bypassed-activation"}, {"xendit_customer_id": "foreign-customer"}):
            with self.subTest(fields=fields), self.assertRaises((frappe.ValidationError, ValueError)):
                billing.update_subscription(self.sub, "a" * 32, fields)
        billing.update_subscription(self.sub, "a" * 32, {"status": "Active", "paid_until": "2030-03-04"})
        versions = frappe.get_all("Version", filters={"ref_doctype": "Nexum Subscription", "docname": self.sub},
                                  fields=["data"])
        changed = [change for version in versions for change in json.loads(version.data).get("changed", [])]
        self.assertIn(["status", "Pending", "Active"], changed)
        self.assertTrue(any(change[0] == "paid_until" and change[2] == "2030-03-04" for change in changed))

    def test_confirmed_inactive_live_plan_is_not_requeued_during_activation(self):
        old = self.sub + "-inactive"
        self.mirror(status="Inactive", xendit_plan_id=old)
        new = self.attempt("new")
        result = billing.activate_subscription(self.sub, "a" * 32, new, old,
                                               {"status": "Active", "xendit_plan_id": new})
        self.assertEqual(result["deactivate"], [])
        self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", old, "state"), "Inactive")

    def test_checkout_persists_distinct_customer_and_plan_ownership_for_reused_name(self):
        calls = []

        def provider(method, path, payload=None):
            calls.append((method, path, payload))
            generation = "a" if len(calls) <= 2 else "b"
            if path == "/customers":
                return 200, {"id": self.sub + "-customer-" + generation}
            return 200, {"recurring_plan_id": self.sub + "-plan-" + generation,
                         "payment_link_url": "https://checkout.example.invalid/" + generation}

        with patch.object(api, "_xendit_api", side_effect=provider), \
                patch.object(frappe.local, "form_dict", frappe._dict(subdomain=self.sub, plan="Business",
                                                                   email="fixture@example.invalid")):
            first = api.xendit_checkout()
            self.generation("b" * 32)
            second = api.xendit_checkout()
        self.assertNotEqual(first["checkout_url"], second["checkout_url"])
        self.assertNotEqual(calls[0][2]["reference_id"], calls[2][2]["reference_id"])
        for generation in ("a", "b"):
            self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", self.sub + "-plan-" + generation,
                                                 "tenant_generation"), generation * 32)

    def test_deletion_waits_for_inflight_checkout_and_includes_its_committed_plan(self):
        self.mirror()
        frappe.db.commit()
        site, sites_path = frappe.local.site, str(Path(frappe.local.sites_path).resolve())
        inside, release, closing, closed = (threading.Event() for _ in range(4))
        errors, result = [], []
        plan = self.sub + "-concurrent"

        def provider(method, path, payload=None):
            if path == "/customers":
                return 200, {"id": self.sub + "-customer"}
            inside.set()
            if not release.wait(15):
                raise AssertionError("Checkout release signal was not received")
            return 200, {"recurring_plan_id": plan, "payment_link_url": "https://checkout.example.invalid"}

        def session(operation):
            try:
                frappe.init(site=site, sites_path=sites_path)
                frappe.connect()
                frappe.set_user("Administrator")
                frappe.conf.is_signup_host = 1
                frappe.conf.xendit_secret_key = "synthetic-disabled"
                operation()
                frappe.db.commit()
            except BaseException as exc:
                print(traceback.format_exc())  # isolated synthetic fixture; exposes the failed SQL boundary
                errors.append(exc)
                if getattr(frappe.local, "db", None):
                    frappe.db.rollback()
            finally:
                frappe.destroy()

        def checkout():
            frappe.local.form_dict = frappe._dict(subdomain=self.sub, plan="Business", email="fixture@example.invalid")
            api.xendit_checkout()

        def close():
            closing.set()
            result.append(billing.close_checkout(self.sub, "a" * 32))
            closed.set()

        first = threading.Thread(target=session, args=(checkout,))
        second = threading.Thread(target=session, args=(close,))
        with patch.object(api, "_xendit_api", side_effect=provider):
            first.start()
            try:
                self.assertTrue(inside.wait(10), str(errors))
                second.start()
                self.assertTrue(closing.wait(10))
                self.assertFalse(closed.wait(0.2), "Deletion must wait for checkout's transaction")
            finally:
                release.set()
                first.join(20)
                if second.ident:
                    second.join(20)
        self.assertFalse(first.is_alive() or second.is_alive(), "Concurrent native sessions must finish")
        self.assertEqual(errors, [])
        self.assertEqual({p.plan_id for p in result[0]["plans"]}, {plan})

    def test_activation_cannot_clear_cleanup_from_concurrent_deletion(self):
        self.mirror()
        plan = self.attempt("activate")
        frappe.db.commit()
        site, sites_path = frappe.local.site, str(Path(frappe.local.sites_path).resolve())
        inside, release, closing, closed = (threading.Event() for _ in range(4))
        errors, results = [], []
        real_write = billing._set_locked

        def pause_after_mirror_write(doctype, name, fields):
            real_write(doctype, name, fields)
            if doctype == "Nexum Subscription" and fields.get("status") == "Active":
                inside.set()
                if not release.wait(15):
                    raise AssertionError("Activation release signal was not received")

        def session(operation):
            try:
                frappe.init(site=site, sites_path=sites_path)
                frappe.connect()
                frappe.set_user("Administrator")
                frappe.conf.is_signup_host = 1
                operation()
                frappe.db.commit()
            except BaseException as exc:
                print(traceback.format_exc())
                errors.append(exc)
                if getattr(frappe.local, "db", None):
                    frappe.db.rollback()
            finally:
                frappe.destroy()

        def activate():
            billing.activate_subscription(self.sub, "a" * 32, plan, "",
                                           {"status": "Active", "plan": "Business", "xendit_plan_id": plan})

        def close():
            closing.set()
            results.append(billing.close_checkout(self.sub, "a" * 32))
            closed.set()

        first = threading.Thread(target=session, args=(activate,))
        second = threading.Thread(target=session, args=(close,))
        # Timing instrumentation pauses after the real SQL write; it does not
        # replace the native transaction, row locks or business behavior.
        with patch.object(billing, "_set_locked", side_effect=pause_after_mirror_write):
            first.start()
            try:
                self.assertTrue(inside.wait(10), str(errors))
                second.start()
                self.assertTrue(closing.wait(10))
                self.assertFalse(closed.wait(0.2), "Closure must not interleave mirror and attempt activation")
            finally:
                release.set()
                first.join(20)
                if second.ident:
                    second.join(20)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        frappe.db.rollback()  # Drop the main session's earlier read snapshot.
        attempt = frappe.get_doc("Billing Checkout Attempt", plan)
        self.assertEqual(attempt.state, "Superseded")
        self.assertTrue(attempt.needs_deactivation)
        self.assertEqual({p.plan_id for p in results[0]["plans"]}, {plan})

    def test_activation_rejects_changed_pointer_and_foreign_attempt_before_writes(self):
        self.mirror(xendit_plan_id=self.sub + "-current")
        plan = self.attempt("new")
        fields = {"status": "Active", "xendit_plan_id": plan}
        with self.assertRaises(frappe.ValidationError):
            billing.activate_subscription(self.sub, "a" * 32, plan, self.sub + "-outdated", fields)
        frappe.db.set_value("Billing Checkout Attempt", plan, "tenant_generation", "b" * 32)
        with self.assertRaises(frappe.ValidationError):
            billing.activate_subscription(self.sub, "a" * 32, plan, self.sub + "-current", fields)
        self.assertEqual(frappe.db.get_value("Nexum Subscription", self.sub, "xendit_plan_id"), self.sub + "-current")

    def test_activation_failure_rolls_back_mirror_and_attempts_as_one_transaction(self):
        old = self.attempt("old")
        new = self.attempt("new")
        self.mirror(xendit_plan_id=old)
        savepoint = "activation_atomicity"
        frappe.db.savepoint(savepoint)
        real_write = billing._set_locked

        def fail_last_write(doctype, name, fields):
            if doctype == "Billing Checkout Attempt" and name == new and fields.get("state") == "Activated":
                raise OSError("Synthetic final write failure")
            real_write(doctype, name, fields)

        with patch.object(billing, "_set_locked", side_effect=fail_last_write), self.assertRaises(OSError):
            billing.activate_subscription(self.sub, "a" * 32, new, old,
                                           {"status": "Active", "xendit_plan_id": new})
        frappe.db.rollback(save_point=savepoint)
        self.assertEqual(frappe.db.get_value("Nexum Subscription", self.sub, "xendit_plan_id"), old)
        self.assertFalse(frappe.db.get_value("Billing Checkout Attempt", old, "needs_deactivation"))
        self.assertEqual(frappe.db.get_value("Billing Checkout Attempt", new, "state"), "Pending")
