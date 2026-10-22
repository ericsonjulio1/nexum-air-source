"""Real MariaDB coordination proof, restricted to isolated *.localhost test sites.

The adapter changes only table names to disposable fixtures; the quota module's
advisory-lock, current-read, commit and rollback SQL runs unchanged on MariaDB.
"""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
import uuid

import frappe
import pymysql

from my_branding.storage_quota import check_and_hold


class Callbacks:
	def __init__(self):
		self.items = []

	def add(self, callback):
		self.items.append(callback)


class Connection:
	def __init__(self, settings, tables):
		self.connection = pymysql.connect(**settings)
		self.tables = tables
		self.after_commit, self.after_rollback = Callbacks(), Callbacks()
		self.waiting = threading.Event()

	def sql(self, query, values=None):
		for source, target in self.tables.items():
			query = query.replace("`" + source + "`", "`" + target + "`")
		if "GET_LOCK" in query:
			self.waiting.set()
		with self.connection.cursor() as cursor:
			cursor.execute(query, values)
			return cursor.fetchall()

	def table_exists(self, name):
		return "tab" + name in self.tables

	def finish(self, commit):
		callbacks = (self.after_commit if commit else self.after_rollback).items[:]
		(self.connection.commit if commit else self.connection.rollback)()
		self.after_commit.items.clear(); self.after_rollback.items.clear()
		for callback in callbacks:
			callback()

	def close(self):
		try:
			self.finish(False)
		finally:
			self.connection.close()


class TestStorageTransactions(unittest.TestCase):
	def setUp(self):
		if not str(frappe.local.site).endswith(".localhost") or not frappe.conf.get("allow_tests"):
			raise unittest.SkipTest("Requires an isolated *.localhost site with allow_tests")
		self.settings = frappe.db.get_connection_settings()
		# Frappe may use mysqlclient. PyMySQL owns its conversion map and disables
		# multi-statements by default; mysqlclient's keyword is not accepted here.
		self.settings.pop("conv", None)
		self.assertFalse(self.settings.pop("multi_statements", False))
		prefix = "nx_quota_" + uuid.uuid4().hex[:12]
		self.tables = {"tabFile": prefix + "_file", "tabDrive File": prefix + "_drive"}
		self.first = Connection(self.settings, self.tables)
		self.second = Connection(self.settings, self.tables)
		for table in self.tables.values():
			self.first.sql(f"CREATE TABLE `{table}` (name VARCHAR(32) PRIMARY KEY, file_size BIGINT NOT NULL) ENGINE=InnoDB")
		self.first.sql("INSERT INTO `tabFile` VALUES ('initial', 80)")
		self.first.connection.commit()

	def tearDown(self):
		if not hasattr(self, "first"):
			return
		self.second.close()
		self.first.finish(False)
		try:
			for table in self.tables.values():
				self.first.sql(f"DROP TABLE IF EXISTS `{table}`")
		finally:
			self.first.close()

	def overlapping_upload(self, snapshot_isolation):
		self.second.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
		self.second.sql("SET SESSION innodb_snapshot_isolation = %s", (snapshot_isolation,))
		self.assertEqual(self.second.sql("SELECT SUM(file_size) FROM `tabFile`")[0][0], 80)
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.sql("INSERT INTO `tabFile` VALUES ('first', 15)")
		with ThreadPoolExecutor(1) as pool:
			future = pool.submit(check_and_hold, self.second, 15, 100)
			self.assertTrue(self.second.waiting.wait(2))
			self.assertFalse(future.done())
			self.first.finish(True)
			self.assertFalse(future.result(timeout=20))
			self.assertEqual(self.second.sql("SELECT @@innodb_snapshot_isolation")[0][0], snapshot_isolation)

	def test_current_read_sees_other_commit_with_legacy_snapshot_setting(self):
		self.overlapping_upload(snapshot_isolation=0)

	def test_current_read_sees_other_commit_with_snapshot_conflict_detection(self):
		self.overlapping_upload(snapshot_isolation=1)

	def test_quota_counts_fresh_usage_without_aborting_the_business_snapshot(self):
		self.second.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
		self.second.sql("SET SESSION innodb_snapshot_isolation = 1")
		self.assertEqual(self.second.sql("SELECT SUM(file_size) FROM `tabFile`")[0][0], 80)
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.sql("INSERT INTO `tabFile` VALUES ('committed', 15)")
		self.first.finish(True)
		self.second.sql("INSERT INTO `tabFile` VALUES ('own', 2)")
		# Quota sees 95 committed + 2 own bytes, without discarding any prior work.
		self.assertFalse(check_and_hold(self.second, 4, 100))
		self.assertEqual(self.second.sql("SELECT @@innodb_snapshot_isolation, @@transaction_isolation")[0],
			(1, "REPEATABLE-READ"))
		# Ordinary business reads retain their original view plus this transaction's write.
		self.assertEqual(self.second.sql("SELECT SUM(file_size) FROM `tabFile`")[0][0], 82)
		self.second.finish(False)

	def test_rollback_frees_the_next_upload_and_drive_shares_the_total(self):
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.sql("INSERT INTO `tabDrive File` VALUES ('rolled-back', 15)")
		self.first.finish(False)
		self.assertTrue(check_and_hold(self.second, 15, 100))
		self.second.sql("INSERT INTO `tabDrive File` VALUES ('drive', 15)")
		self.second.finish(True)
		self.assertFalse(check_and_hold(self.first, 6, 100))

	def test_connection_loss_releases_coordination(self):
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.connection.close()
		self.first.after_commit.items.clear(); self.first.after_rollback.items.clear()
		self.first._nexum_storage_lock = None
		try:
			self.assertTrue(check_and_hold(self.second, 15, 100))
		finally:
			self.first.connection = pymysql.connect(**self.settings)

	def test_connection_loss_after_commit_does_not_fail_release_callbacks(self):
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.sql("INSERT INTO `tabFile` VALUES ('committed', 15)")
		self.first.connection.commit()
		self.first.connection.close()
		callbacks = self.first.after_commit.items[:]
		self.first.after_commit.items.clear(); self.first.after_rollback.items.clear()
		try:
			for callback in callbacks:
				callback()
			self.assertFalse(check_and_hold(self.second, 15, 100))
		finally:
			self.first.connection = pymysql.connect(**self.settings)
