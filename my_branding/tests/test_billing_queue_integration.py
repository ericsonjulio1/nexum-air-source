"""Real Frappe/MariaDB queue selection and writes on an isolated test site.

The HQ transport dispatches to the actual Frappe endpoint functions; authentication,
HTTP serving, provider delivery and host financial scripts are outside this suite.
"""
import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import unquote
import uuid

import frappe
from frappe.api.v1 import update_doc
from frappe.client import get_list


_spec = importlib.util.spec_from_file_location(
    "billing_queue_integration_worker", Path(__file__).parents[2] / "saas" / "billing-worker.py")
_worker = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(Path(__file__).parents[2] / "saas"))
try:
    _spec.loader.exec_module(_worker)
finally:
    sys.path.pop(0)


class NativeHQ(_worker.HQ):
    """Replace only HTTP transport, retaining native query and write permissions."""
    def _call(self, method, path, payload=None):
        if method == "POST" and path == "/api/method/frappe.client.get_list":
            return {"message": get_list(**payload)}
        prefix = "/api/resource/Billing%20Event/"
        if method == "GET" and path.startswith(prefix):
            doc = frappe.get_doc("Billing Event", unquote(path[len(prefix):]))
            doc.check_permission("read")
            return {"data": doc.as_dict()}
        if method == "PUT" and path.startswith(prefix):
            previous = frappe.local.form_dict
            try:
                frappe.local.form_dict = frappe._dict(data=json.dumps(payload))
                return {"data": update_doc("Billing Event", unquote(path[len(prefix):])).as_dict()}
            finally:
                frappe.local.form_dict = previous
        raise AssertionError(f"Unexpected transport call: {method} {path}")


class TestBillingQueueIntegration(unittest.TestCase):
    def setUp(self):
        self.assertTrue(str(frappe.local.site).endswith(".localhost") and frappe.conf.get("allow_tests"),
                        "Requires an isolated *.localhost site with allow_tests; this required gate cannot skip")
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self.prefix = "queue-" + uuid.uuid4().hex
        self.savepoint = "queue_" + uuid.uuid4().hex
        frappe.db.savepoint(self.savepoint)
        self.addCleanup(self.cleanup)
        self.assertFalse(frappe.db.count("Billing Event", {"processed": 0}),
                         "Queue integration tests require a dedicated site with no foreign pending Billing Events")
        self.manager = self.create_user("manager", "System Manager")
        self.restricted = self.create_user("restricted", "Employee")
        self.hq = NativeHQ(dict(HQ_URL="https://fixture.example.invalid", API_KEY="synthetic", API_SECRET="synthetic"))

    def cleanup(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point=self.savepoint)
        frappe.set_user(self.previous_user)

    def create_user(self, label, role):
        return frappe.get_doc(dict(doctype="User", email=f"{self.prefix}-{label}@example.invalid",
                                   first_name="Queue Fixture", user_type="System User", send_welcome_email=0,
                                   roles=[dict(role=role)])).insert().name

    def row(self, suffix, *, attempted=None, processed=0, payload='{"data": {}}'):
        doc = frappe.get_doc(dict(doctype="Billing Event", event_id=f"{self.prefix}-{suffix}",
                                  event_type="recurring.cycle.succeeded", processed=processed,
                                  last_attempted_on=attempted, payload=payload)).insert()
        # Equal creation times exercise the stable name tie-break, independent of insertion order.
        frappe.db.set_value("Billing Event", doc.name, "creation", "2026-01-01 00:00:00", update_modified=False)
        return doc.name

    def test_native_query_prioritizes_untouched_then_oldest_attempt_and_excludes_visits(self):
        recent = self.row("recent", attempted="2026-02-02 00:00:00")
        older = self.row("older", attempted="2026-02-01 00:00:00")
        second = self.row("untouched-b")
        first = self.row("untouched-a")
        self.row("completed", processed=1)
        frappe.set_user(self.manager)
        self.assertEqual([row.name for row in self.hq.pending_events(limit=2)], [first, second])
        self.assertEqual([row.name for row in self.hq.pending_events(exclude=[first, second])], [older, recent])

    def test_native_attempt_write_reorders_without_completing_or_changing_payload(self):
        first, second = self.row("a"), self.row("b")
        frappe.set_user(self.manager)
        self.hq.mark_attempted(first)
        doc = frappe.get_doc("Billing Event", first)
        self.assertIsNotNone(doc.last_attempted_on)
        self.assertFalse(doc.processed)
        self.assertIsNone(doc.processed_on)
        self.assertEqual(doc.payload, '{"data": {}}')
        self.assertEqual([row.name for row in self.hq.pending_events()], [second, first])
        self.hq.mark_processed(second)
        self.assertEqual([row.name for row in self.hq.pending_events()], [first])

    def test_terminal_alert_is_durable_after_payment_completion_and_has_separate_acknowledgement(self):
        name = self.row("terminal")
        frappe.set_user(self.manager)
        self.hq.queue_owner_alert(name, "Synthetic refund", "Synthetic financial reconciliation")
        self.hq.mark_processed(name, err="Payment not applied; refund required")
        self.assertEqual([row.name for row in self.hq.pending_owner_alerts()], [name])
        self.hq.mark_owner_alert_attempted(name)
        self.hq.mark_owner_alert_sent(name)
        self.hq.queue_owner_alert(name, "Replay must not reset Sent", "Replay")
        self.assertEqual(self.hq.pending_owner_alerts(), [])
        row = frappe.get_doc("Billing Event", name)
        self.assertTrue(row.processed)
        self.assertIn("refund required", row.processing_error)
        self.assertEqual(row.owner_alert_subject, "Synthetic refund")
        self.assertIsNotNone(row.owner_alert_sent_on)

    def test_native_permissions_reject_guest_and_unprivileged_queue_read_and_write(self):
        name = self.row("protected")
        for user in ("Guest", self.restricted):
            with self.subTest(user=user):
                frappe.set_user(user)
                with self.assertRaises(frappe.PermissionError):
                    self.hq.pending_events()
                with self.assertRaises(frappe.PermissionError):
                    self.hq.mark_attempted(name)
        frappe.set_user("Administrator")
        self.assertIsNone(frappe.db.get_value("Billing Event", name, "last_attempted_on"))

    def test_installed_schema_has_nullable_attempt_and_pending_index(self):
        columns = {row.Field: row for row in frappe.db.sql("SHOW COLUMNS FROM `tabBilling Event`", as_dict=True)}
        self.assertTrue(columns["last_attempted_on"].Type.startswith("datetime"))
        self.assertEqual(columns["last_attempted_on"].Null, "YES")
        indexes = frappe.db.sql("SHOW INDEX FROM `tabBilling Event`", as_dict=True)
        fields = [row.Column_name for row in sorted(indexes, key=lambda row: row.Seq_in_index)
                  if row.Key_name == "billing_event_pending_attempt"]
        self.assertEqual(fields, ["processed", "last_attempted_on", "creation"])

    def test_payload_above_text_limit_survives_database_roundtrip(self):
        payload = json.dumps({"data": {"metadata": "é" * 40000}}, ensure_ascii=False)
        self.assertGreater(len(payload.encode("utf-8")), 65535)
        self.assertLess(len(payload.encode("utf-8")), 100000)
        name = self.row("payload", payload=payload)
        frappe.set_user(self.manager)
        self.hq.mark_attempted(name)
        self.assertEqual(self.hq.pending_events()[0].payload, payload)

    def test_watchdog_probe_keeps_old_pending_event_after_fresh_attempt_writes(self):
        from my_branding.tests.test_watchdog_jobs import _load_watchdog
        from types import SimpleNamespace

        self.assertTrue((Path(__file__).parents[2] / "saas" / "nexum-watchdog.py").is_file(),
                        "Required watchdog source is missing from the candidate")
        name = self.row("old-retried")
        frappe.set_user(self.manager)
        for _ in range(2):
            self.hq.mark_attempted(name)

        class SiteProbe:
            # Label the synthetic connection as HQ for the host probe dispatch;
            # all actual database calls still use this isolated test site.
            local = SimpleNamespace(site="hq.nexumair.com")

            def __getattr__(self, key):
                return getattr(frappe, key)

        output = io.StringIO()
        with redirect_stdout(output):
            exec(_load_watchdog().PROBE_SRC, {"frappe": SiteProbe()})
        line = next(line for line in output.getvalue().splitlines() if line.startswith("WDPROBE "))
        probe = json.loads(line[len("WDPROBE "):])
        self.assertIn([name, "recurring.cycle.succeeded"], probe["billing"])
