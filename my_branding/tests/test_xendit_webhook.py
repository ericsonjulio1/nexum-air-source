"""Stub-based tests for the Xendit webhook receiver (XENDIT-SPEC section 3).

No DB fixtures: frappe supplies the exception types; conf/request/db calls are
patched. Run via:
  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_xendit_webhook
"""
import json
import unittest

import frappe

import my_branding.api as api
from my_branding.api import XENDIT_EVENT_TYPES, _xendit_event_identity, xendit_webhook


class _Patched:
    def __init__(self, *triples):
        self.triples = triples

    def __enter__(self):
        self.saved = [(o, n, getattr(o, n)) for o, n, _v in self.triples]
        for o, n, v in self.triples:
            setattr(o, n, v)

    def __exit__(self, *exc):
        for o, n, v in reversed(self.saved):
            setattr(o, n, v)


class _Req:
    def __init__(self, body):
        self._body = body

    def get_data(self, as_text=False):
        return self._body


def _run(body, token="tok-1", configured="tok-1", existing=False):
    """Drive xendit_webhook with everything stubbed; returns (result, inserts)."""
    inserts = []

    class _Doc(dict):
        def insert(self, ignore_permissions=False):
            inserts.append(dict(self))
            return self

    conf = {"xendit_webhook_token": configured} if configured else {}
    with _Patched(
        (frappe, "conf", frappe._dict(conf)),
        (frappe, "get_request_header", lambda name: token),
        (frappe, "request", _Req(json.dumps(body) if isinstance(body, dict) else body)),
        (frappe.db, "exists", lambda *a, **k: existing),
        (frappe, "get_doc", lambda d: _Doc(d)),
    ):
        return xendit_webhook(), inserts


class TestWebhookGate(unittest.TestCase):
    def test_dead_without_site_config_token(self):
        with self.assertRaises(frappe.PermissionError):
            _run({"event": "recurring.cycle.succeeded"}, configured=None)

    def test_wrong_token_rejected(self):
        with self.assertRaises(frappe.PermissionError):
            _run({"event": "recurring.cycle.succeeded"}, token="wrong")

    def test_malformed_payload_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            _run("this is not json")
        with self.assertRaises(frappe.ValidationError):
            _run("[1,2,3]")  # JSON but not an object


class TestWebhookInbox(unittest.TestCase):
    def test_known_event_queued_unprocessed(self):
        body = {"event": "recurring.cycle.succeeded", "id": "evt_1",
                "data": {"id": "cycle_1", "plan_id": "plan_9"}}
        result, inserts = _run(body)
        self.assertTrue(result["ok"])
        self.assertEqual(len(inserts), 1)
        row = inserts[0]
        self.assertEqual(row["doctype"], "Billing Event")
        self.assertEqual(row["event_id"], "evt_1")
        self.assertEqual(row["reference_id"], "plan_9")
        self.assertEqual(row["processed"], 0)

    def test_unknown_event_acked_but_preprocessed(self):
        # a 4xx would make Xendit retry six times for a type we never handle —
        # ack it, store it processed=1 with the note
        result, inserts = _run({"event": "totally.new.event", "id": "evt_2"})
        self.assertTrue(result["ok"])
        self.assertEqual(inserts[0]["processed"], 1)
        self.assertIn("whitelist", inserts[0]["processing_error"])

    def test_duplicate_delivery_inserts_nothing(self):
        result, inserts = _run(
            {"event": "recurring.cycle.succeeded", "id": "evt_1"}, existing=True)
        self.assertTrue(result["duplicate"])
        self.assertEqual(inserts, [])

    def test_never_processes_in_request(self):
        # the receiver must ONLY insert — any lifecycle side effect in-request
        # violates the queue-then-process design (spec section 3)
        src = open(api.__file__.rstrip("c")).read()
        webhook_src = src.split("def xendit_webhook")[1]
        for forbidden in ("subprocess", "set_value(", "sendmail", "requests."):
            self.assertNotIn(forbidden, webhook_src.split("\ndef ")[0])


class TestEventIdentity(unittest.TestCase):
    def test_prefers_delivery_id(self):
        self.assertEqual(
            _xendit_event_identity({"id": "evt_9", "event": "x", "data": {"id": "c"}}),
            "evt_9")

    def test_derived_identity_is_stable_and_distinct(self):
        a = {"event": "recurring.cycle.succeeded",
             "data": {"id": "cycle_1", "updated": "T1"}}
        b = dict(a, event="recurring.cycle.failed")
        self.assertEqual(_xendit_event_identity(a), _xendit_event_identity(dict(a)))
        self.assertNotEqual(_xendit_event_identity(a), _xendit_event_identity(b))

    def test_whitelist_covers_spec_lifecycle(self):
        # "recurring.plan.activated" (dots) is what Xendit's dashboard test
        # delivery actually sent (v1, live-verified 2026-08-30); the underscore
        # form stays accepted for API-version drift.
        for must in ("recurring.cycle.succeeded", "recurring.cycle.failed",
                     "recurring.plan.inactivated", "recurring_plan.activated",
                     "recurring.plan.activated"):
            self.assertIn(must, XENDIT_EVENT_TYPES)


class TestWebhookDuplicateRace(unittest.TestCase):
    def test_duplicate_insert_race_is_acked_not_500(self):
        """Two concurrent deliveries race past exists(); the unique event_id
        makes the loser's insert throw — it must be ACKed as duplicate so
        Xendit does not retry a stored event (review-gate LOW)."""
        class _RacingDoc(dict):
            def insert(self, ignore_permissions=False):
                raise frappe.DuplicateEntryError("Billing Event", self["event_id"])

        with _Patched(
            (frappe, "conf", frappe._dict({"xendit_webhook_token": "tok-1"})),
            (frappe, "get_request_header", lambda name: "tok-1"),
            (frappe, "request", _Req(json.dumps(
                {"event": "recurring.cycle.succeeded", "id": "evt_race"}))),
            (frappe.db, "exists", lambda *a, **k: False),
            (frappe, "get_doc", lambda d: _RacingDoc(d)),
        ):
            out = xendit_webhook()
        self.assertEqual(out, {"ok": True, "duplicate": True})


class TestCheckoutMirrorSafety(unittest.TestCase):
    """Review-gate findings 2/6: guest checkout must write ONLY pending_*
    fields (never the live plan/xendit_plan_id/status mapping), and an
    unexpired session must be reused instead of minting a new one."""

    _SESSION = {"payment_link_url": "https://dev.xen.to/abc",
                "recurring_plan_id": "repl_new",
                "payment_session_id": "ps_new"}

    def test_existing_row_gets_only_pending_fields(self):
        writes = []
        with _Patched(
            (api, "_xendit_customer_id", lambda sub, email: "cust_1"),
            (api, "_xendit_api", lambda m, p, payload=None: (200, dict(self._SESSION))),
            (frappe.db, "exists", lambda *a, **k: True),
            (frappe.db, "set_value", lambda dt, name, fields: writes.append((dt, name, fields))),
        ):
            out = api._create_checkout_session("acme", "Business", "a@b.co")
        self.assertEqual(out["checkout_url"], "https://dev.xen.to/abc")
        self.assertEqual(len(writes), 1)
        fields = writes[0][2]
        forbidden = {"plan", "status", "xendit_plan_id"}
        self.assertFalse(forbidden & set(fields),
                         "checkout must not touch the live mapping: %s" % fields)
        self.assertEqual(fields["pending_plan_id"], "repl_new")
        self.assertEqual(fields["pending_plan"], "Business")

    def test_new_row_created_pending_without_live_plan_id(self):
        docs = []

        class _Doc(dict):
            def insert(self, ignore_permissions=False):
                docs.append(dict(self))
                return self

        with _Patched(
            (api, "_xendit_customer_id", lambda sub, email: "cust_1"),
            (api, "_xendit_api", lambda m, p, payload=None: (200, dict(self._SESSION))),
            (frappe.db, "exists", lambda *a, **k: False),
            (frappe, "get_doc", lambda d: _Doc(d)),
        ):
            api._create_checkout_session("acme", "Business", "a@b.co")
        subs = [d for d in docs if d.get("doctype") == "Nexum Subscription"]
        attempts = [d for d in docs if d.get("doctype") == "Billing Checkout Attempt"]
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].get("status"), "Pending")
        self.assertNotIn("xendit_plan_id", subs[0])
        self.assertEqual(subs[0]["pending_plan_id"], "repl_new")
        # the durable attempt record carries plan_id -> tenant + priced tier
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["plan_id"], "repl_new")
        self.assertEqual(attempts[0]["subdomain"], "acme")
        self.assertEqual(attempts[0]["tier"], "Business")

    def test_unexpired_pending_session_is_reused(self):
        from datetime import datetime as _dt, timedelta as _td

        row = frappe._dict(pending_plan="Business",
                           checkout_url="https://dev.xen.to/keep",
                           checkout_expires_on=(_dt.now() + _td(minutes=10)))
        calls = []

        def _boom(*a, **k):
            calls.append(a)
            raise AssertionError("must not mint a second session")

        import contextlib

        @contextlib.contextmanager
        def _no_lock(*a, **k):
            yield

        import frappe.utils.synchronization as sync
        with _Patched(
            (api, "_require_signup_host", lambda: None),
            (api, "_bump_window", lambda *a, **k: 1),
            (api, "_subdomain_taken", lambda *a, **k: True),
            (api, "_create_checkout_session", _boom),
            (sync, "filelock", _no_lock),
            (frappe, "conf", frappe._dict({"xendit_secret_key": "xnd_test"})),
            (frappe, "form_dict", frappe._dict(
                subdomain="acme", plan="Business", email="a@b.co")),
            (frappe.db, "exists", lambda *a, **k: True),
            (frappe.db, "get_value", lambda *a, **k: row),
            (frappe.db, "commit", lambda: None),
        ):
            out = api.xendit_checkout()
        self.assertEqual(out["checkout_url"], "https://dev.xen.to/keep")
        self.assertEqual(calls, [])


class TestWorkerPureHelpers(unittest.TestCase):
    """The host worker is stdlib-only; its money math is importable by path."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(frappe.get_app_path("my_branding")),
                            "saas", "billing-worker.py")
        if not os.path.exists(path):
            raise unittest.SkipTest("saas/billing-worker.py not present")
        spec = importlib.util.spec_from_file_location("billing_worker", path)
        cls.bw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bw)

    def test_add_one_month_caps_day_at_28(self):
        from datetime import date as _d
        self.assertEqual(self.bw._add_one_month(_d(2026, 1, 31)), _d(2026, 2, 28))
        self.assertEqual(self.bw._add_one_month(_d(2026, 12, 15)), _d(2027, 1, 15))
        # 12 payments from an anchor-day date advance exactly 12 months
        d = _d(2026, 2, 28)
        for _ in range(12):
            d = self.bw._add_one_month(d)
        self.assertEqual(d, _d(2027, 2, 28))

    def test_stale_fence_across_mixed_timestamp_formats(self):
        """Frappe REST hands back '2026-08-30 10:00:00'; Xendit sends
        '...T09:00:00Z'. Raw string comparison calls the OLDER event newer
        ('T' > ' ') — round-2 finding 6. The normalizer must fix that."""
        norm = self.bw._norm_ts
        self.assertEqual(norm("2026-08-30T09:00:00.123Z"), "2026-08-30 09:00:00.123000")
        self.assertEqual(norm("2026-08-30 09:00:00.500000"), "2026-08-30 09:00:00.500000")
        self.assertEqual(norm("2026-08-30T17:00:00+08:00"), "2026-08-30 09:00:00.000000")
        self.assertEqual(norm("garbage"), "")
        # sub-second ordering survives (round-3 #5): a delayed .100 failure is
        # STALE next to an applied .900 success in the same second
        self.assertTrue(self.bw._is_stale(
            {"last_event_at": norm("2026-08-30T10:00:00.900Z")},
            norm("2026-08-30T10:00:00.100Z")))
        # frappe-format watermark vs older Xendit-format event
        sub = {"last_event_at": "2026-08-30 10:00:00"}
        self.assertTrue(self.bw._is_stale(sub, self.bw._norm_ts("2026-08-30T09:00:00Z")))
        self.assertFalse(self.bw._is_stale(sub, self.bw._norm_ts("2026-08-30T11:00:00Z")))
        self.assertFalse(self.bw._is_stale({}, "2026-08-30 04:00:00"))
        self.assertFalse(self.bw._is_stale(sub, ""))

    def test_watermark_is_monotonic(self):
        sub = {"last_event_at": "2026-08-30 10:00:00"}
        self.assertEqual(self.bw._watermark(sub, "2026-08-30 09:00:00"),
                         "2026-08-30 10:00:00.000000")
        self.assertEqual(self.bw._watermark(sub, "2026-08-30 11:00:00"),
                         "2026-08-30 11:00:00.000000")
        self.assertEqual(self.bw._watermark({}, ""), None)
        # an event with no timestamp must never erase the watermark
        self.assertEqual(self.bw._watermark(sub, ""), "2026-08-30 10:00:00.000000")

    def test_plan_map_matches_mark_paid_vocabulary(self):
        self.assertEqual(self.bw.PLAN_TO_HOST,
                         {"Essentials": "starter", "Business": "business",
                          "Enterprise": "enterprise"})


class TestCheckoutActiveBlock(unittest.TestCase):
    def test_active_subscription_blocks_new_checkout(self):
        """Round-2 finding 3: the public pricing page must not open a SECOND
        recurring plan for an already-billing tenant."""
        import contextlib

        @contextlib.contextmanager
        def _no_lock(*a, **k):
            yield

        import frappe.utils.synchronization as sync
        row = frappe._dict(status="Active", xendit_plan_id="repl_live",
                           pending_plan="", checkout_url="",
                           checkout_expires_on=None)
        with _Patched(
            (api, "_require_signup_host", lambda: None),
            (api, "_bump_window", lambda *a, **k: 1),
            (api, "_subdomain_taken", lambda *a, **k: True),
            (sync, "filelock", _no_lock),
            (frappe, "conf", frappe._dict({"xendit_secret_key": "xnd_test"})),
            (frappe, "form_dict", frappe._dict(
                subdomain="acme", plan="Business", email="a@b.co")),
            (frappe.db, "exists", lambda *a, **k: True),
            (frappe.db, "get_value", lambda *a, **k: row),
            (frappe.db, "commit", lambda: None),
        ):
            with self.assertRaises(frappe.ValidationError):
                api.xendit_checkout()


class TestCheckoutEndpoint(unittest.TestCase):
    def _run(self, form=None, secret="sk-test", taken=True, api_script=None,
             exists=False):
        """Drive xendit_checkout with stubs; returns (result, api_calls, writes)."""
        api_calls, writes = [], []
        script = list(api_script or [])

        def fake_api(method, path, payload=None):
            api_calls.append((method, path, payload))
            return script.pop(0)

        class _Doc(dict):
            def insert(self, ignore_permissions=False):
                writes.append(("insert", dict(self)))
                return self

        conf = {"is_signup_host": 1}
        if secret:
            conf["xendit_secret_key"] = secret
        form_dict = frappe._dict(form or {
            "subdomain": "acme", "plan": "essentials", "email": "own@acme.ph"})
        with _Patched(
            (frappe, "conf", frappe._dict(conf)),
            (frappe, "form_dict", form_dict),
            (api, "_bump_window", lambda *a, **k: 1),
            (api, "_subdomain_taken", lambda s, include_pipeline=True: taken),
            (api, "_xendit_api", fake_api),
            (frappe.db, "exists", lambda *a, **k: exists),
            (frappe.db, "set_value",
             lambda dt, name, values: writes.append(("update", name, values))),
            (frappe.db, "commit", lambda: None),
            (frappe, "get_doc", lambda d: _Doc(d)),
        ):
            return api.xendit_checkout(), api_calls, writes

    _HAPPY = [
        (200, {"id": "cust-1"}),                      # customer create
        (200, {"payment_link_url": "https://dev.xen.to/abc",
               "recurring_plan_id": "repl_1"}),        # session create
    ]

    def test_dead_without_secret_key(self):
        with self.assertRaises(frappe.PermissionError):
            self._run(secret=None)

    def test_unknown_tenant_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._run(taken=False, api_script=self._HAPPY)

    def test_unknown_plan_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._run(form={"subdomain": "acme", "plan": "mega",
                            "email": "own@acme.ph"}, api_script=self._HAPPY)

    def test_happy_path_returns_link_and_mirrors_plan(self):
        result, api_calls, writes = self._run(api_script=list(self._HAPPY))
        self.assertEqual(result["checkout_url"], "https://dev.xen.to/abc")
        # session call carries immediate first charge + PHP + the plan price
        session_payload = api_calls[1][2]
        self.assertEqual(session_payload["amount"], 2790)
        self.assertEqual(session_payload["currency"], "PHP")
        self.assertTrue(session_payload["subscription"]["immediate_payment"])
        self.assertLessEqual(
            int(session_payload["subscription"]["schedule"]["anchor_date"][8:10]), 28)
        # mirror row created BEFORE any webhook arrives — but only as a
        # PENDING mapping: the live xendit_plan_id is promoted by the worker
        # on plan activation (guest checkout can't clobber a live mapping);
        # the durable attempt row records plan_id -> tenant + priced tier
        inserts = {w[1].get("doctype"): w[1] for w in writes if w[0] == "insert"}
        attempt = inserts["Billing Checkout Attempt"]
        self.assertEqual(attempt["plan_id"], "repl_1")
        self.assertEqual(attempt["subdomain"], "acme")
        row = inserts["Nexum Subscription"]
        self.assertEqual(row["pending_plan_id"], "repl_1")
        self.assertNotIn("xendit_plan_id", row)
        self.assertEqual(row["status"], "Pending")

    def test_duplicate_customer_falls_back_to_fetch(self):
        script = [
            (409, {"error_code": "DUPLICATE_ERROR"}),          # create rejected
            (200, {"data": [{"id": "cust-old"}]}),             # fetch by reference
            (200, {"payment_link_url": "https://dev.xen.to/x",
                   "recurring_plan_id": "repl_2"}),
        ]
        result, api_calls, _w = self._run(api_script=script)
        self.assertTrue(result["ok"])
        self.assertIn("reference_id=tenant-acme", api_calls[1][1])
        self.assertEqual(api_calls[2][2]["customer_id"], "cust-old")

    def test_session_failure_throws_without_mirror_write(self):
        script = [(200, {"id": "cust-1"}), (500, {"message": "boom"})]
        with _Patched((frappe, "log_error", lambda **kw: None)):
            with self.assertRaises(frappe.ValidationError):
                self._run(api_script=script)
