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

	def test_raw_shipped_content_is_reconciled_without_removing_tenant_addition(self):
		definition = json.loads(
			Path(frappe.get_module_path("CRM", "workspace", "crm", "crm.json")).read_text()
		)
		definition["content"] = json.dumps(
			[
				{
					"id": "raw-banner",
					"type": "paragraph",
					"data": {
						"text": '<a class="legacy" href="https://frappe.io/crm">Deprecated: use Frappe CRM</a>',
						"col": 12,
					},
				}
			]
		)
		with tempfile.TemporaryDirectory() as root:
			path = Path(root, "crm.json")
			path.write_text(json.dumps(definition))
			# Raw content can predate the current importer or arrive via db_set.
			# The real importer and current shipped definitions are tested below.
			frappe.db.set_value(
				"Workspace",
				"CRM",
				"content",
				json.dumps(json.loads(definition["content"]) + [self._paragraph()]),
			)
			real_path = frappe.get_module_path
			with patch.object(
				frappe,
				"get_module_path",
				side_effect=lambda module, *parts: (
					str(path)
					if module == "CRM" and parts == ("workspace", "crm", "crm.json")
					else real_path(module, *parts)
				),
			):
				branding.reconcile_content_leaks()
			self.assertEqual(
				json.loads(frappe.db.get_value("Workspace", "CRM", "content")), [self._paragraph()]
			)

	def test_real_installed_standard_workspaces_keep_content_and_tenant_additions(self):
		"""Exercise actual shipped JSON through the same native importer as migrate."""
		from frappe.modules.import_file import import_doc

		for module, name in (("CRM", "crm"), ("Support", "support")):
			with self.subTest(workspace=module):
				path = Path(frappe.get_module_path(module, "workspace", name, name + ".json"))
				definition = json.loads(path.read_text())
				import_doc(dict(definition))
				before = json.loads(frappe.db.get_value("Workspace", module, "content"))
				self.assertEqual(before, json.loads(definition["content"]))
				frappe.db.set_value("Workspace", module, "content", json.dumps(before + [self._paragraph()]))
				branding.reconcile_content_leaks()
				after = json.loads(frappe.db.get_value("Workspace", module, "content"))
				self.assertIn(self._paragraph(), after)
				# Current ERPNext ships chart/card blocks here. They must survive.
				for block in before:
					if block["type"] != "paragraph":
						self.assertIn(block, after)
				for block in after:
					if block == self._paragraph():
						continue
					text = (block.get("data") or {}).get("text", "").lower()
					self.assertFalse("frappe.io" in text and "deprecated" in text)

	def test_orphaned_workspace_does_not_prevent_later_standard_reconciliation(self):
		self._assert_workspace_failure_isolated("orphan")

	def test_failed_workspace_write_does_not_prevent_later_standard_reconciliation(self):
		self._assert_workspace_failure_isolated("write")

	def _assert_workspace_failure_isolated(self, failure):
		crm = frappe.get_doc("Workspace", "CRM")
		support = frappe.get_doc("Workspace", "Support")
		banner = {
			"id": "banner",
			"type": "paragraph",
			"data": {"text": "Deprecated: use Frappe at https://frappe.io/crm", "col": 12},
		}
		for doc in (crm, support):
			frappe.db.set_value("Workspace", doc.name, "content", json.dumps([banner]))
		with tempfile.TemporaryDirectory() as root:
			for module in ("CRM", "Support"):
				definition = {
					"name": module,
					"module": module,
					"public": 1,
					"standard": 1,
					"content": json.dumps([banner]),
					"shortcuts": [],
				}
				Path(root, module + ".json").write_text(json.dumps(definition))
			real_path, real_get, real_write = frappe.get_module_path, frappe.get_all, frappe.db.set_value

			def source_path(module, *parts):
				if failure == "orphan" and module == "CRM":
					raise frappe.DoesNotExistError("Synthetic orphaned module")
				if module in ("CRM", "Support") and parts == (
					"workspace",
					module.lower(),
					module.lower() + ".json",
				):
					return str(Path(root, module + ".json"))
				return real_path(module, *parts)

			def ordered(doctype, *args, **kwargs):
				rows = real_get(doctype, *args, **kwargs)
				return sorted(rows, key=lambda row: row.name != "CRM") if doctype == "Workspace" else rows

			def write(doctype, name, *args, **kwargs):
				if failure == "write" and doctype == "Workspace" and name == "CRM":
					raise RuntimeError("Synthetic content write failure")
				return real_write(doctype, name, *args, **kwargs)

			with (
				patch.object(frappe, "get_module_path", side_effect=source_path),
				patch.object(frappe, "get_all", side_effect=ordered),
				patch.object(frappe.db, "set_value", side_effect=write),
				patch.object(frappe, "log_error") as errors,
			):
				branding.reconcile_content_leaks()
				self.assertEqual(errors.call_count, int(failure == "write"))
			self.assertEqual(json.loads(frappe.db.get_value("Workspace", "CRM", "content")), [banner])
			self.assertEqual(json.loads(frappe.db.get_value("Workspace", "Support", "content")), [])

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
