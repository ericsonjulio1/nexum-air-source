"""Migration branding must distinguish shipped content from tenant content."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import frappe

from my_branding import branding


class TestWorkspaceContentPreservation(unittest.TestCase):
	def setUp(self):
		self.old_user = frappe.session.user
		frappe.set_user("Administrator")
		self.savepoint = "workspace_preservation_" + uuid.uuid4().hex
		frappe.db.savepoint(self.savepoint)

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)
		frappe.set_user(self.old_user)

	def _paragraph(self):
		return {
			"id": "tenant-procedure",
			"type": "paragraph",
			"data": {
				"text": 'Our procedure: <a href="https://docs.frappe.io/erpnext">reference</a>',
				"col": 12,
			},
		}

	def test_custom_workspaces_keep_paragraphs_and_shortcuts(self):
		for public in (0, 1):
			with self.subTest(public=public):
				label = "Tenant procedure " + uuid.uuid4().hex[:12]
				doc = frappe.get_doc(
					{
						"doctype": "Workspace",
						"label": label,
						"title": label,
						"module": "CRM",
						"public": public,
						"standard": 0,
						"for_user": "" if public else "Administrator",
						"type": "Workspace",
						"content": json.dumps(
							[
								self._paragraph(),
								{
									"id": "tenant-link",
									"type": "shortcut",
									"data": {
										"shortcut_name": "Our Frappe Builder reference",
										"col": 3,
									},
								},
							]
						),
						"shortcuts": [
							{
								"type": "URL",
								"url": "https://example.invalid/reference",
								"label": "Our Frappe Builder reference",
							}
						],
					}
				).insert()
				before = frappe.db.get_value("Workspace", doc.name, "content")
				branding.reconcile_content_leaks()
				self.assertEqual(frappe.db.get_value("Workspace", doc.name, "content"), before)
				self.assertEqual(
					frappe.get_doc("Workspace", doc.name).shortcuts[0].label, "Our Frappe Builder reference"
				)

	def test_tenant_paragraph_added_to_shipped_workspace_survives(self):
		doc = frappe.get_doc("Workspace", "CRM")
		blocks = json.loads(doc.content)
		blocks.append(self._paragraph())
		frappe.db.set_value("Workspace", doc.name, "content", json.dumps(blocks))
		branding.reconcile_content_leaks()
		self.assertIn(self._paragraph(), json.loads(frappe.db.get_value("Workspace", doc.name, "content")))

	def test_shipped_block_is_reconciled_without_removing_tenant_addition(self):
		from frappe.desk.doctype.workspace.workspace import sanitize_content

		doc = frappe.get_doc("Workspace", "CRM")
		shipped = {
			"id": "shipped-banner",
			"type": "paragraph",
			"data": {
				"text": 'Deprecated: use Frappe CRM at <a href="https://frappe.io/crm">Frappe</a>',
				"col": 12,
			},
		}
		definition = {
			"name": "CRM",
			"module": "CRM",
			"standard": 1,
			"public": 1,
			"content": json.dumps([shipped]),
			"shortcuts": [],
		}
		content = sanitize_content(json.dumps([shipped, self._paragraph()]))
		frappe.db.set_value("Workspace", doc.name, "content", content)
		with tempfile.TemporaryDirectory() as root:
			path = Path(root, "crm.json")
			path.write_text(json.dumps(definition))
			real_path = frappe.get_module_path

			def source_path(module, *parts):
				if module == "CRM" and parts == ("workspace", "crm", "crm.json"):
					return str(path)
				return real_path(module, *parts)

			with patch.object(frappe, "get_module_path", side_effect=source_path):
				branding.reconcile_content_leaks()
				after = frappe.db.get_value("Workspace", doc.name, "content")
				self.assertEqual(json.loads(after), json.loads(content)[1:])
				branding.reconcile_content_leaks()
				self.assertEqual(frappe.db.get_value("Workspace", doc.name, "content"), after)

	def test_shortcut_label_and_content_reference_share_ownership(self):
		for width, target, renamed, fail_write in (
			(4, "shipped", True, False),
			(6, "shipped", False, False),
			(4, "tenant", False, False),
			(4, "shipped", False, True),
		):
			with self.subTest(width=width, target=target, fail_write=fail_write):
				frappe.db.savepoint("shortcut_ownership_case")
				try:
					row = frappe.get_doc(
						{
							"doctype": "Workspace Shortcut",
							"parent": "CRM",
							"parenttype": "Workspace",
							"parentfield": "shortcuts",
							"idx": 999,
							"type": "URL",
							"url": "https://example.invalid/" + target,
							"label": "Open <strong>Frappe Builder</strong>",
						}
					)
					row.db_insert()
					shipped = {
						"id": "shipped-shortcut",
						"type": "shortcut",
						"data": {"shortcut_name": "Open <strong>Frappe Builder</strong>", "col": 4},
					}
					content = json.loads(json.dumps([shipped]))
					content[0]["data"]["col"] = width
					frappe.db.set_value("Workspace", "CRM", "content", json.dumps(content))
					shortcut = {
						key: row.get(key) or "" for key in ("label", "type", "link_to", "url", "doc_view")
					}
					shortcut["url"] = "https://example.invalid/shipped"
					definition = {
						"name": "CRM",
						"module": "CRM",
						"standard": 1,
						"public": 1,
						"content": json.dumps([shipped]),
						"shortcuts": [shortcut],
					}
					with tempfile.TemporaryDirectory() as root:
						path = Path(root, "crm.json")
						path.write_text(json.dumps(definition))
						real_path = frappe.get_module_path

						def source_path(module, *parts):
							if module == "CRM" and parts == ("workspace", "crm", "crm.json"):
								return str(path)
							return real_path(module, *parts)

						real_write = frappe.db.set_value

						def write(doctype, *args, **kwargs):
							if fail_write and doctype == "Workspace Shortcut":
								raise RuntimeError("Synthetic child update failure")
							return real_write(doctype, *args, **kwargs)

						with (
							patch.object(frappe, "get_module_path", side_effect=source_path),
							patch.object(frappe.db, "set_value", side_effect=write),
							patch.object(frappe, "log_error") as errors,
						):
							branding.reconcile_content_leaks()
							self.assertEqual(errors.call_count, int(fail_write))
						after = json.loads(frappe.db.get_value("Workspace", "CRM", "content"))
						expected = (
							"Open <strong>Builder</strong>"
							if renamed
							else "Open <strong>Frappe Builder</strong>"
						)
						self.assertEqual(after[0]["data"]["shortcut_name"], expected)
						self.assertEqual(
							frappe.db.get_value("Workspace Shortcut", row.name, "label"), expected
						)
				finally:
					frappe.db.rollback(save_point="shortcut_ownership_case")
