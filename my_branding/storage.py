"""Per-tenant file storage quota enforcement.

Each tenant's plan sets ``storage_quota_gb`` in ``site_config.json``
(0 / unset = unlimited, used for the owner ``hq`` site). When a new File would
push the site's total stored bytes over that quota, the upload is blocked with a
friendly "upgrade your plan" message. Wired via ``doc_events`` in hooks.py.

Usage is the SUM of the stored ``file_size`` values, so those values must be the size
the server measured, never one the client sent (``pin_true_file_size``).
"""

import os

import frappe
from frappe import _
from frappe.utils import cint

from my_branding.storage_quota import QuotaBusy, QuotaTransactionConflict, check_and_hold


def _quota_bytes():
	"""Quota in bytes from site_config; 0 (or unset/invalid) means unlimited."""
	gb = frappe.conf.get("storage_quota_gb")
	try:
		gb = float(gb)
	except (TypeError, ValueError):
		return 0
	return int(gb * 1024 * 1024 * 1024)


_USED_CACHE_KEY = "nexum_storage_used_bytes"
_USED_CACHE_TTL = 30  # seconds — short enough that deletes free space quickly
# doc.flags key: the size File.before_insert measured, for pin_true_file_size
_TRUE_SIZE_FLAG = "nx_true_file_size"


def _used_bytes(exact=False):
	"""Total bytes already stored in this site, across classic File attachments
	and Drive uploads (Drive keeps its own ``Drive File`` doctype — both count
	against the one plan quota).

	This display cache expires after 30 seconds; ``exact=True`` recomputes it.
	Quota decisions use the transaction-coordinated storage_quota module instead.
	Frappe namespaces this cache by site."""
	if not exact:
		cached = frappe.cache.get_value(_USED_CACHE_KEY)
		if cached is not None:
			return int(cached)
	used = int(frappe.db.sql("SELECT COALESCE(SUM(file_size), 0) FROM `tabFile`")[0][0] or 0)
	if frappe.db.table_exists("Drive File"):
		used += int(
			frappe.db.sql("SELECT COALESCE(SUM(file_size), 0) FROM `tabDrive File`")[0][0] or 0
		)
	frappe.cache.set_value(_USED_CACHE_KEY, used, expires_in_sec=_USED_CACHE_TTL)
	return used


def invalidate_used_cache(doc=None, method=None):
	"""Best-effort display refresh after a file change or transaction completion."""
	try:
		frappe.cache.delete_value(_USED_CACHE_KEY)
	except Exception:
		# Even logging may depend on the unavailable service. Transaction callbacks
		# must continue: the upload can already be committed at this point.
		try:
			frappe.log_error(
				title="my_branding invalidate_used_cache failed",
				message=frappe.get_traceback(),
			)
		except Exception:
			pass


def _bust_used_cache_on_rollback():
	"""Register a rollback callback that drops any display total read mid-transaction.
	No-op on frappe builds without the after_rollback CallbackManager."""
	cb = getattr(frappe.db, "after_rollback", None)
	if cb is not None and hasattr(cb, "add"):
		cb.add(invalidate_used_cache)


def enforce_file_quota(doc, method=None):
	# Remember the size File.before_insert just measured from the uploaded content
	# (save_file sets file_size = len(content), then flags.new_file) so the validate pin
	# below can restore it. Done before the unlimited-site early return: the stored size
	# must be honest on every site, not only on capped ones (a plan can change later).
	if doc.doctype == "File" and doc.flags.get("new_file"):
		doc.flags[_TRUE_SIZE_FLAG] = cint(doc.get("file_size"))

	# Compute the over-quota decision defensively. This runs on EVERY file insert,
	# so an unexpected internal error (e.g. a transient DB hiccup in the usage sum)
	# must NOT block a legitimate upload — fail OPEN (log + allow). The quota block
	# itself is raised OUTSIDE the try so frappe.throw still propagates normally.
	try:
		quota = _quota_bytes()
		if quota <= 0:
			return  # unlimited (owner site / unset)

		if getattr(doc, "is_group", 0):
			return  # Drive folder, takes no space

		incoming = int(getattr(doc, "file_size", 0) or 0)
		if incoming <= 0:
			return  # nothing to count yet (e.g. folder, or size set later)

		over_limit = not check_and_hold(frappe.db, incoming, quota)
		# Display-only usage cache must not retain values from an earlier transaction.
		frappe.db.after_commit.add(invalidate_used_cache)
		_bust_used_cache_on_rollback()
	except QuotaBusy:
		frappe.throw(_("Another upload is completing. Please retry in a moment."), title=_("Upload Busy"))
	except QuotaTransactionConflict as exc:
		raise frappe.QueryDeadlockError(str(exc)) from exc
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
		# Frappe wraps driver errors; errno predicates do not recognize wrappers.
		raise
	except Exception as exc:
		# A database transaction conflict must roll back, never continue partially.
		if frappe.db.is_deadlocked(exc) or frappe.db.is_timedout(exc):
			raise
		frappe.log_error(
			title="my_branding enforce_file_quota failed (fail-open)",
			message=frappe.get_traceback(),
		)
		return

	if over_limit:
		limit_gb = int(quota / (1024 ** 3))
		frappe.throw(
			_(
				"You've reached your plan's storage limit of {0} GB. "
				"Please upgrade your plan to upload more files."
			).format(limit_gb),
			title=_("Storage Full"),
		)


def pin_true_file_size(doc, method=None):
	"""File ``validate``: store the size the server measured, never the client's (H3, v204).

	Upstream File.validate ends with ``self.file_size = frappe.form_dict.file_size or
	self.file_size`` (frappe 16.36.1 file.py:190), so any request field named
	``file_size`` (an extra multipart field on /api/method/upload_file, or a REST PUT on
	an existing File) overwrote the real size. The quota check saw the true size at
	before_insert, but the row was stored with the forged one, so SUM(file_size) — the
	usage figure — undercounted without bound and a Free tenant could fill the shared
	tenant-files volume. doc_events run after the controller method (Document.hook runs
	the controller first), so this hook has the last word:

	* new upload: the size File.before_insert measured from the content, stashed by
	  enforce_file_quota — exactly the figure the quota check used;
	* any other save of a local file (REST update, private/public toggle, re-optimise,
	  copied attachment): the size of the blob on disk, which File.validate has just
	  confirmed exists (validate_file_on_disk).

	Folders and remote URLs store no bytes here and are left alone. If the disk read
	fails, keep the size already in the database rather than the client's."""
	if doc.get("is_folder") or doc.is_remote_file:
		return
	# consumed here: a later save of the same object in this request (e.g. a re-optimise)
	# must measure the blob again, not reuse the size from the insert
	measured = doc.flags.pop(_TRUE_SIZE_FLAG, None)
	true_size = measured if doc.is_new() else None
	if true_size is None:
		try:
			true_size = os.path.getsize(doc.get_full_path())
		except Exception:
			before = doc.get_doc_before_save()
			true_size = cint(before.file_size) if before else None
	if true_size is not None and cint(doc.get("file_size")) != true_size:
		doc.file_size = true_size
