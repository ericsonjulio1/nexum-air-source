"""Offline transaction-adapter checks; real MariaDB concurrency is a release gate."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from my_branding.storage_quota import QuotaBusy, check_and_hold


class Callbacks:
	def __init__(self):
		self.items = []

	def add(self, fn):
		self.items.append(fn)

	def run(self):
		for fn in self.items:
			fn()
		self.items.clear()


class Database:
	"""A committed store with connection-local inserts and transaction callbacks."""
	def __init__(self, store):
		self.store = store
		self.pending = 0
		self.after_commit, self.after_rollback = Callbacks(), Callbacks()
		self.waiting = threading.Event()
		self.force_busy = False

	def sql(self, query, values=None):
		if query == "SELECT DATABASE()":
			return [("test-site",)]
		if "GET_LOCK" in query:
			self.waiting.set()
			return [(0 if self.force_busy else int(self.store["lock"].acquire(timeout=2)),)]
		if "RELEASE_LOCK" in query:
			self.store["lock"].release()
			return [(1,)]
		assert query.endswith("FOR UPDATE"), "Quota reads must bypass old snapshots"
		return [(self.store["used"] + self.pending,)]

	def table_exists(self, name):
		return False

	def finish(self, commit):
		if commit:
			self.store["used"] += self.pending
		self.pending = 0
		(self.after_commit if commit else self.after_rollback).run()
		self.after_commit.items.clear()
		self.after_rollback.items.clear()


class TestStorageCoordination(unittest.TestCase):
	def setUp(self):
		self.store = {"used": 80, "lock": threading.Lock()}
		self.first, self.second = Database(self.store), Database(self.store)

	def test_overlapping_uploads_count_the_first_commit(self):
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.pending = 15
		with ThreadPoolExecutor(1) as pool:
			other = pool.submit(check_and_hold, self.second, 15, 100)
			self.assertTrue(self.second.waiting.wait(1))
			self.assertFalse(other.done())
			self.first.finish(commit=True)
			self.assertFalse(other.result(timeout=2))
		self.second.finish(commit=False)
		self.assertEqual(self.store["used"], 95)

	def test_rollback_releases_capacity_and_coordination(self):
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.pending = 15
		self.first.finish(commit=False)
		self.assertTrue(check_and_hold(self.second, 15, 100))
		self.second.finish(commit=False)

	def test_multiple_uploads_in_one_transaction_count_own_inserts(self):
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.pending = 15
		self.assertFalse(check_and_hold(self.first, 15, 100))
		self.assertEqual(len(self.first.after_commit.items), 1)
		self.first.finish(commit=False)

	def test_busy_is_not_permission_to_skip_quota(self):
		self.first.force_busy = True
		with self.assertRaises(QuotaBusy):
			check_and_hold(self.first, 15, 100)
		self.assertEqual(self.first.after_commit.items, [])

	def test_exact_limit_and_over_limit(self):
		self.assertTrue(check_and_hold(self.first, 20, 100))
		self.assertFalse(check_and_hold(self.first, 21, 100))
		self.first.finish(commit=False)

	def test_release_error_closes_connection_and_does_not_fail_a_committed_upload(self):
		from unittest.mock import Mock, patch
		self.assertTrue(check_and_hold(self.first, 15, 100))
		self.first.pending = 15
		closed = Mock(side_effect=self.store["lock"].release)
		later = Mock()
		self.first.after_commit.add(later)
		with patch.object(self.first, "sql", side_effect=ConnectionError("lost response")), patch.object(self.first, "close", closed, create=True):
			self.first.finish(commit=True)
		closed.assert_called_once()
		later.assert_called_once()
		self.assertFalse(check_and_hold(self.second, 15, 100))
		self.second.finish(commit=False)
