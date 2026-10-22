"""Coordinate quota checks for the lifetime of a MariaDB upload transaction.

Call ``check_and_hold(db, incoming, limit)`` before inserting a File or Drive File.
The site's connection-owned advisory lock is released after commit/rollback (or
by MariaDB if the connection dies). Repeated calls in one transaction reuse it.
Quota-only locking reads count current rows, including our own inserts, without
changing the transaction's isolation level or ordinary repeatable-read snapshot.
Neither a Redis snapshot nor an older repeatable-read snapshot grants capacity.
No schema, quota ledger, reservation TTL, or customer-data migration is required.
"""

import hashlib


class QuotaBusy(RuntimeError):
	"""Another upload still owns the site's quota transaction; retry is required."""


class QuotaTransactionConflict(RuntimeError):
	"""MariaDB rolled back a stale snapshot; the entire request must roll back."""


def check_and_hold(db, incoming, limit):
	"""Return whether incoming bytes fit; retain coordination until transaction end.

	``db`` is the Frappe MariaDB adapter, including transaction callbacks. A lock
	timeout is an expected contention outcome, never permission to skip the check.
	Callers retain their policy for unexpected infrastructure failures.
	"""
	if not getattr(db, "_nexum_storage_lock", None):
		# Validate callback support before acquiring a connection-owned lock.
		commit, rollback = db.after_commit, db.after_rollback
		database = db.sql("SELECT DATABASE()")[0][0]
		key = "nexum-storage:" + hashlib.sha256(str(database).encode()).hexdigest()[:40]
		acquired = db.sql("SELECT GET_LOCK(%s, %s)", (key, 15))[0][0]
		if acquired == 0:
			raise QuotaBusy("Another upload is still completing")
		if acquired != 1:
			raise RuntimeError("Could not acquire the storage quota lock")
		db._nexum_storage_lock = key

		def release():
			try:
				db.sql("SELECT RELEASE_LOCK(%s)", (key,))
			except Exception:
				# The commit may already have succeeded. Closing the connection is
				# the fallback release and must not stop later transaction callbacks.
				try:
					db.close()
				except Exception:
					pass
			finally:
				db._nexum_storage_lock = None

		commit.add(release)
		rollback.add(release)

	try:
		# MariaDB 11.8 otherwise aborts a locking read outside the request's old
		# snapshot (1020), making concurrent valid uploads fail. Only these quota
		# aggregates need current committed rows; SET STATEMENT restores the
		# snapshot-conflict setting before the next business query, even on error.
		current_read = "SET STATEMENT innodb_snapshot_isolation=OFF FOR "
		used = int(db.sql(current_read + "SELECT COALESCE(SUM(file_size), 0) FROM `tabFile` FOR UPDATE")[0][0] or 0)
		if db.table_exists("Drive File"):
			used += int(db.sql(current_read + "SELECT COALESCE(SUM(file_size), 0) FROM `tabDrive File` FOR UPDATE")[0][0] or 0)
	except Exception as exc:
		# Any residual snapshot conflict must still abort the request, never
		# fall through to the hook's unexpected-infrastructure fail-open policy.
		if exc.args and exc.args[0] == 1020:
			raise QuotaTransactionConflict("Upload snapshot changed; retry the whole request") from exc
		raise
	return used + incoming <= limit
