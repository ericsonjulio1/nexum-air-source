"""Storage quota: the stored File.file_size is the size the server measured (H3, v204).

frappe's File.validate copies a request field named file_size over the measured size
(frappe 16.36.1 file.py:190), so a forged form field shrank the stored size and the
quota's SUM(file_size) undercounted without bound. storage.pin_true_file_size restores
the real size after File.validate.

Run via:  bench --site <site> run-tests --app my_branding --module my_branding.tests.test_storage_quota
"""
import os
import unittest
from contextlib import contextmanager

import frappe
from frappe.utils import cint

from my_branding import storage


@contextmanager
def _form_dict(**values):
	"""Pretend the current request carried these form fields (None = absent)."""
	old = frappe.local.form_dict
	frappe.local.form_dict = frappe._dict({k: v for k, v in values.items() if v is not None})
	try:
		yield
	finally:
		frappe.local.form_dict = old


@contextmanager
def _quota_bytes(n):
	old = frappe.conf.get("storage_quota_gb")
	frappe.conf.storage_quota_gb = n / (1024**3)
	try:
		yield
	finally:
		if old is None:
			frappe.conf.pop("storage_quota_gb", None)
		else:
			frappe.conf.storage_quota_gb = old


def _content(size):
	"""`size` bytes with a unique head, so save_file never dedups onto an older blob."""
	head = frappe.generate_hash(length=20).encode()
	return head + b"x" * (size - len(head))


def _stored_size(name):
	return cint(frappe.db.get_value("File", name, "file_size"))


class TestTrueFileSize(unittest.TestCase):
	def setUp(self):
		self.made = []
		frappe.cache.delete_value(storage._USED_CACHE_KEY)

	def tearDown(self):
		for name in self.made:
			if frappe.db.exists("File", name):
				frappe.delete_doc("File", name, ignore_permissions=True, force=True)
		frappe.cache.delete_value(storage._USED_CACHE_KEY)
		frappe.db.commit()

	def _upload(self, size, forged_size=None):
		"""What /api/method/upload_file does, with an optional forged file_size field."""
		with _form_dict(file_size=forged_size):
			doc = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "nx-h3-%s.txt" % frappe.generate_hash(length=8),
					"content": _content(size),
					"is_private": 1,
				}
			).insert(ignore_permissions=True)
		self.made.append(doc.name)
		return doc

	def test_forged_form_size_cannot_shrink_the_stored_size(self):
		doc = self._upload(5000, forged_size=1)
		self.assertEqual(os.path.getsize(doc.get_full_path()), 5000)
		self.assertEqual(_stored_size(doc.name), 5000)

	def test_forged_size_on_update_is_replaced_by_the_size_on_disk(self):
		doc = self._upload(4000)
		self.assertEqual(_stored_size(doc.name), 4000)
		# a REST PUT {"file_size": 1}: doc.update() sets the field AND form_dict carries it
		with _form_dict(file_size=1):
			doc = frappe.get_doc("File", doc.name)
			doc.file_size = 1
			doc.save(ignore_permissions=True)
		self.assertEqual(_stored_size(doc.name), 4000)

	def test_quota_holds_against_forged_sizes(self):
		size = 6000
		used = storage._used_bytes(exact=True)
		# room for ONE more upload of `size`, not two
		with _quota_bytes(used + size + size // 2):
			self._upload(size, forged_size=1)
			frappe.db.commit()  # keep it; drops the first upload's rollback hooks
			frappe.cache.delete_value(storage._USED_CACHE_KEY)
			# the stored usage must count the first upload's real 6000 bytes, not 1
			with self.assertRaises(frappe.ValidationError):
				self._upload(size, forged_size=1)
		# the refused upload's blob was already written by save_file; rolling back runs
		# File.on_rollback, which deletes it (only the refused insert is uncommitted)
		frappe.db.rollback()
