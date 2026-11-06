"""Native v227 Helpdesk fixtures; opt-in, disposable sites only.

Run after installing/migrating the frozen cohort with Helpdesk. This module is
separate from the release harness; no production credentials or HTTP adapters.
"""
import os
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase


def require_synthetic_site():
    site = str(frappe.local.site or "")
    if (os.environ.get("NEXUM_V227_HELPDESK_FIXTURES") != "1"
            or not site.startswith("v227-") or not site.endswith(".test")
            or not frappe.conf.get("allow_tests")):
        raise RuntimeError("Requires opt-in, allow_tests and an isolated v227-*.test site")
    if "helpdesk" not in frappe.get_installed_apps():
        raise RuntimeError("Helpdesk must be installed on the synthetic site")


def seed_legacy():
    """Call on the OLD Helpdesk synthetic site before its normal bench migrate.

    Records only synthetic legacy template/permission inputs. No patch-log edits,
    DDL or commits: bench execute owns the successful transaction commit.
    """
    require_synthetic_site()
    if not frappe.db.has_column("HD Ticket Template Field", "hide_from_customer"):
        raise RuntimeError("Legacy Helpdesk schema required; do not fabricate a column on the target")
    if frappe.db.count("HD Ticket"):
        raise RuntimeError("Legacy seed requires an empty synthetic ticket table")
    frappe.set_user("Administrator")
    frappe.db.delete("Custom DocPerm", {"parent": "HD Ticket"})
    for role in ("System Manager", "Agent", "Agent Manager"):
        frappe.get_doc(doctype="Custom DocPerm", parent="HD Ticket", parenttype="DocType",
                       parentfield="permissions", role=role, permlevel=0, read=1, write=1,
                       create=1).insert(ignore_permissions=True)
    template = frappe.get_doc("HD Ticket Template", "Default")
    template.set("fields", [])
    for field, hidden in (("priority", 1), ("ticket_type", 0), ("resolution_details", 0)):
        template.append("fields", {"fieldname": field, "hide_from_customer": hidden})
    template.save(ignore_permissions=True)
    frappe.db.set_default("v227_helpdesk_legacy_seed", "1")
    frappe.clear_cache()
    return {"fixture": "v227-helpdesk-legacy", "seeded": True}


def prepare():
    """Native upstream test setup, including its commit, on an opted-in lab only."""
    require_synthetic_site()
    frappe.set_user("Administrator")
    frappe.flags.mute_emails = True
    from helpdesk.test_utils import before_tests
    before_tests()
    return {"fixture": "v227-helpdesk-native", "prepared": True}


def seed_hq_legacy():
    """Seed HQ's exact permission/template shape on an EMPTY 1.31.0 lab only.

    One synthetic ticket exercises the existing-site notice. No tenant content,
    schema fabrication, Patch Log edits or commit is performed by this helper.
    """
    require_synthetic_site()
    import helpdesk
    if helpdesk.__version__ != "1.31.0":
        raise RuntimeError("HQ legacy seed requires Helpdesk 1.31.0 before migrate")
    if not frappe.db.has_column("HD Ticket Template Field", "hide_from_customer"):
        raise RuntimeError("Actual legacy Helpdesk schema required")
    if frappe.db.count("HD Ticket"):
        raise RuntimeError("HQ lane requires an empty synthetic ticket table")
    frappe.set_user("Administrator")
    frappe.flags.mute_emails = True
    template = frappe.get_doc("HD Ticket Template", "Default")
    template.set("fields", [])
    template.save(ignore_permissions=True)
    frappe.get_doc(doctype="HD Ticket", subject="V227 synthetic idle HQ ticket",
                   description="Synthetic migration fixture", raised_by="Administrator").insert(ignore_permissions=True)
    frappe.db.delete("Custom DocPerm", {"parent": "HD Ticket"})
    for role in ("Agent", "Agent Manager", "All", "System Manager"):
        frappe.get_doc(doctype="Custom DocPerm", parent="HD Ticket", parenttype="DocType",
                       parentfield="permissions", role=role, permlevel=0, read=1,
                       write=1, create=1).insert(ignore_permissions=True)
    frappe.db.set_default("v227_helpdesk_hq_seed", "1")
    frappe.clear_cache()
    return {"fixture": "v227-helpdesk-hq-legacy", "seeded": True, "tickets": 1,
            "custom_permission_rows": 4}


@unittest.skipUnless(os.environ.get("NEXUM_V227_HELPDESK_FIXTURES") == "1",
                     "Explicit v227 synthetic Helpdesk fixture gate only")
class TestV227Helpdesk(FrappeTestCase):
    CUSTOMER = "v227-customer@example.invalid"
    OTHER = "v227-other@example.invalid"
    MANAGER = "v227-manager@example.invalid"
    AGENT = "v227-agent@example.invalid"
    AGENT_MANAGER = "v227-agent-manager@example.invalid"

    @classmethod
    def setUpClass(cls):
        require_synthetic_site()
        super().setUpClass()

    def setUp(self):
        require_synthetic_site()
        super().setUp()
        frappe.set_user("Administrator")
        self.previous_mute = frappe.flags.mute_emails
        frappe.flags.mute_emails = True
        frappe.db.savepoint("v227_helpdesk_case")
        self.addCleanup(self.restore_context)
        # All mutations below are DML in the testcase transaction. No custom-field
        # creation/DDL, external requests, permission mocks or ignore flags on reads.
        from helpdesk.test_utils import create_agent, create_contact
        for label, email, role in (("V227 Customer", self.CUSTOMER, "HD Customer"),
                                   ("V227 Other", self.OTHER, "HD Customer"),
                                   ("V227 Manager", self.MANAGER, "HD Customer Manager")):
            create_contact(label, email, role=role)
        create_agent(self.AGENT)
        create_agent(self.AGENT_MANAGER)
        # HD Agent's insert saves User; the helper's returned User is stale.
        frappe.get_doc("User", self.AGENT_MANAGER).add_roles("Agent Manager")
        self.assertNotIn("Agent", frappe.get_roles(self.CUSTOMER))
        self.assertNotIn("System Manager", frappe.get_roles(self.CUSTOMER))

    def restore_context(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="v227_helpdesk_case")
        frappe.db.value_cache.clear()
        frappe.flags.mute_emails = self.previous_mute
        frappe.clear_cache()

    def template(self, visible="Everyone", editable=1):
        frappe.set_user("Administrator")
        template = frappe.get_doc("HD Ticket Template", "Default")
        template.set("fields", [])
        template.append("fields", {"fieldname": "priority", "visible_to": visible,
                                    "editable_after_creation": editable})
        template.save(ignore_permissions=True)
        frappe.clear_cache()

    def ticket(self, user=None):
        from helpdesk.test_utils import make_ticket
        frappe.set_user("Administrator")
        return make_ticket(subject="V227 synthetic permission ticket", raised_by=user or self.CUSTOMER)

    def other_priority(self, current):
        from helpdesk.test_utils import make_priority
        frappe.set_user("Administrator")
        for priority in ("V227 Priority A", "V227 Priority B"):
            make_priority(priority)
        return "V227 Priority B" if current == "V227 Priority A" else "V227 Priority A"

    def test_customer_agent_manager_and_guest_native_read_boundaries(self):
        from frappe.client import get
        self.template()
        ticket = self.ticket()
        frappe.db.set_value("HD Ticket", ticket.name, "resolution_details", "V227 internal only")
        for user in (self.CUSTOMER,):
            frappe.set_user(user)
            seen = get("HD Ticket", ticket.name)
            self.assertEqual(seen["name"], ticket.name)
            self.assertFalse(seen.get("resolution_details"))
        for user in (self.AGENT, self.AGENT_MANAGER):
            frappe.set_user(user)
            self.assertIn("V227 internal only", get("HD Ticket", ticket.name)["resolution_details"])
        for user in (self.OTHER, "Guest"):
            frappe.set_user(user)
            with self.assertRaises(frappe.PermissionError):
                get("HD Ticket", ticket.name)
        manager_ticket = self.ticket(self.MANAGER)
        frappe.set_user(self.MANAGER)
        self.assertEqual(get("HD Ticket", manager_ticket.name)["name"], manager_ticket.name)
        self.assertFalse(get("HD Ticket", manager_ticket.name).get("resolution_details"))

    def test_visible_to_is_narrower_than_framework_field_permission(self):
        from frappe.client import get
        from helpdesk.helpdesk.doctype.hd_ticket.api import get_one
        self.template("Agents", editable=1)
        ticket = self.ticket()
        frappe.set_user(self.CUSTOMER)
        self.assertFalse(get_one(ticket.name).get("priority"))
        self.assertEqual(get("HD Ticket", ticket.name).get("priority"), ticket.priority)
        frappe.set_user(self.AGENT)
        self.assertEqual(get_one(ticket.name).get("priority"), ticket.priority)

    def test_editable_after_creation_and_agent_only_rows(self):
        from frappe.client import set_value
        for visible, editable, allowed in (("Everyone", 1, True), ("Everyone", 0, False), ("Agents", 1, False)):
            with self.subTest(visible=visible, editable=editable):
                self.template(visible, editable)
                ticket = self.ticket()
                value = self.other_priority(ticket.priority)
                frappe.set_user(self.CUSTOMER)
                if allowed:
                    set_value("HD Ticket", ticket.name, "priority", value)
                    self.assertEqual(frappe.db.get_value("HD Ticket", ticket.name, "priority"), value)
                else:
                    with self.assertRaises(frappe.PermissionError):
                        set_value("HD Ticket", ticket.name, "priority", value)

    def test_customer_whole_document_save_preserves_unreadable_fields(self):
        from frappe.client import get, save
        self.template()
        ticket = self.ticket()
        frappe.db.set_value("HD Ticket", ticket.name, "resolution_details", "V227 retained secret")
        frappe.set_user(self.CUSTOMER)
        seen = get("HD Ticket", ticket.name)
        self.assertFalse(seen.get("resolution_details"))
        save(seen)
        self.assertIn("V227 retained secret", frappe.db.get_value("HD Ticket", ticket.name, "resolution_details"))

    def test_customer_native_create_then_read_only_template_field(self):
        from frappe.client import set_value
        from helpdesk.helpdesk.doctype.hd_ticket.api import new
        self.template("Everyone", editable=0)
        priority = self.other_priority(None)
        frappe.set_user(self.CUSTOMER)
        ticket = new({"subject": "V227 customer native creation", "description": "Synthetic fixture",
                      "priority": priority}, attachments=[])
        self.assertEqual(ticket["raised_by"], self.CUSTOMER)
        self.assertEqual(ticket["priority"], priority)
        self.assertNotIn("via_customer_portal", ticket)
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("HD Ticket", ticket["name"], "via_customer_portal"), 1)
        replacement = self.other_priority(priority)
        frappe.set_user(self.CUSTOMER)
        with self.assertRaises(frappe.PermissionError):
            set_value("HD Ticket", ticket["name"], "priority", replacement)

    def custom_base(self, roles):
        frappe.set_user("Administrator")
        frappe.db.delete("Custom DocPerm", {"parent": "HD Ticket"})
        for role in roles:
            frappe.get_doc(doctype="Custom DocPerm", parent="HD Ticket", parenttype="DocType",
                           parentfield="permissions", role=role, permlevel=0, read=1, write=1,
                           create=1).insert(ignore_permissions=True)
        frappe.clear_cache()

    def grants(self):
        return {(row.role, row.permlevel): (row.read, row.write) for row in frappe.get_all(
            "Custom DocPerm", filters={"parent": "HD Ticket"}, fields=["role", "permlevel", "read", "write"])}

    def test_native_migration_grants_zero_seven_eight_and_is_idempotent(self):
        from helpdesk.patches.harden_hd_ticket_field_permissions import execute
        self.custom_base(("System Manager", "Agent", "Agent Manager", "Guest"))
        execute()
        got = self.grants()
        for role in ("HD Customer", "HD Customer Manager"):
            self.assertEqual(got[(role, 0)], (1, 1))
            self.assertEqual(got[(role, 7)], (1, 0))
            self.assertNotIn((role, 8), got)
        for role in ("Agent", "Agent Manager", "System Manager"):
            self.assertEqual(got[(role, 7)], (1, 1))
            self.assertEqual(got[(role, 8)], (1, 1))
        self.assertNotIn(("Guest", 7), got)
        self.assertNotIn(("Guest", 8), got)
        execute()
        self.assertEqual(self.grants(), got)

    def test_partial_customer_and_existing_level_grants_are_preserved(self):
        from helpdesk.patches.harden_hd_ticket_field_permissions import execute
        self.custom_base(("System Manager", "Agent", "HD Customer"))
        frappe.get_doc(doctype="Custom DocPerm", parent="HD Ticket", parenttype="DocType",
                       parentfield="permissions", role="Agent", permlevel=8, read=0, write=0).insert(ignore_permissions=True)
        execute()
        got = self.grants()
        self.assertNotIn(("HD Customer Manager", 0), got)
        self.assertEqual(got[("Agent", 8)], (0, 0))
        self.assertEqual(got[("HD Customer", 7)], (1, 0))

    def test_real_upgrade_seed_backfill_and_patch_log(self):
        if frappe.db.get_default("v227_helpdesk_legacy_seed") != "1":
            self.skipTest("Requires seed_legacy on the old Helpdesk site before normal migrate")
        rows = frappe.get_all("HD Ticket Template Field", filters={"parent": "Default"}, fields=["fieldname", "visible_to"])
        values = {row.fieldname: row.visible_to for row in rows}
        self.assertEqual(values["priority"], "Agents")
        self.assertEqual(values["ticket_type"], "Everyone")
        self.assertEqual(values["resolution_details"], "Agents")
        for patch in ("helpdesk.patches.harden_hd_ticket_field_permissions", "helpdesk.patches.backfill_template_field_visible_to"):
            self.assertTrue(frappe.db.exists("Patch Log", {"patch": patch}))

    def test_real_hq_custom_permissions_upgrade(self):
        if frappe.db.get_default("v227_helpdesk_hq_seed") != "1":
            self.skipTest("Requires seed_hq_legacy on 1.31.0 before ordinary migrate")
        expected = {}
        for role in ("Agent", "Agent Manager", "All", "System Manager", "HD Customer", "HD Customer Manager"):
            expected[(role, 0)] = (1, 1)
            expected[(role, 7)] = (1, int(role in ("Agent", "Agent Manager", "System Manager")))
        for role in ("Agent", "Agent Manager", "System Manager"):
            expected[(role, 8)] = (1, 1)
        rows = frappe.get_all("Custom DocPerm", filters={"parent": "HD Ticket"}, fields=["role", "permlevel", "read", "write", "create"])
        self.assertEqual(len(rows), 15)
        self.assertEqual(self.grants(), expected)
        self.assertTrue(all(row.create for row in rows if row.permlevel == 0))
        self.assertEqual(frappe.db.count("HD Ticket Template Field", {"parent": "Default"}), 0)
        self.assertEqual(int(frappe.db.get_single_value("HD Settings", "show_ticket_field_permission_notice")), 1)
        for patch in ("harden_hd_ticket_field_permissions", "backfill_template_field_visible_to", "show_ticket_field_permission_notice"):
            self.assertTrue(frappe.db.exists("Patch Log", {"patch": "helpdesk.patches." + patch}))
        frappe.clear_cache()
        meta = frappe.get_meta("HD Ticket")
        self.assertEqual(len(meta.permissions), 15)
        for user, read, write in ((self.AGENT, {0, 7, 8}, {0, 7, 8}),
                                  (self.AGENT_MANAGER, {0, 7, 8}, {0, 7, 8}),
                                  (self.CUSTOMER, {0, 7}, {0}),
                                  (self.MANAGER, {0, 7}, {0}),
                                  ("Guest", set(), set())):
            self.assertEqual(set(meta.get_permlevel_access("read", user=user)), read)
            self.assertEqual(set(meta.get_permlevel_access("write", user=user)), write)
        # The same real read/write guards are exercised with the migrated custom
        # rows, including another customer's ticket and unreadable level 8.
        self.test_customer_agent_manager_and_guest_native_read_boundaries()
        self.test_customer_whole_document_save_preserves_unreadable_fields()
        from helpdesk.patches.harden_hd_ticket_field_permissions import execute
        frappe.set_user("Administrator")
        execute()
        self.assertEqual(self.grants(), expected)
        self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "HD Ticket"}), 15)
