"""Per-tenant file storage quota enforcement.

Each tenant's plan sets ``storage_quota_gb`` in ``site_config.json``
(0 / unset = unlimited, used for the owner ``hq`` site). When a new File would
push the site's total stored bytes over that quota, the upload is blocked with a
friendly "upgrade your plan" message. Wired via ``doc_events`` in hooks.py.
"""

import frappe
from frappe import _


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


def _used_bytes(exact=False):
	"""Total bytes already stored in this site, across classic File attachments
	and Drive uploads (Drive keeps its own ``Drive File`` doctype — both count
	against the one plan quota).

	This ran a full ``SUM(file_size)`` table scan on EVERY upload. The result is now
	cached per-site for a few seconds to spare that scan on routine uploads; pass
	``exact=True`` to bypass the cache and recompute. The caller forces an exact
	recompute once an upload is near the limit, so the quota boundary stays precise
	while far-from-limit uploads stay cheap. (frappe.cache is per-site namespaced,
	so one tenant's total can't leak into another's.)"""
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


def invalidate_used_cache(doc, method=None):
	"""Drop the cached usage total when a File/Drive File is deleted.

	Without this, the cached SUM only expired on its 30s TTL, so a tenant AT quota
	who deleted files to free space could stay blocked for up to 30s (the next
	upload read the stale-high cached total). Deleting a File is the one event that
	*lowers* usage, so bust the cache here — the next ``_used_bytes`` call recomputes
	exactly. Best-effort: a cache hiccup must never block a delete."""
	try:
		frappe.cache.delete_value(_USED_CACHE_KEY)
	except Exception:
		frappe.log_error(
			title="my_branding invalidate_used_cache failed",
			message=frappe.get_traceback(),
		)


def _bust_used_cache_on_rollback():
	"""Register a rollback callback that drops the usage-cache reservation, so a
	rolled-back upload's projected total can't linger and over-block the next one.
	No-op on frappe builds without the after_rollback CallbackManager."""
	cb = getattr(frappe.db, "after_rollback", None)
	if cb is not None and hasattr(cb, "add"):
		cb.add(lambda: frappe.cache.delete_value(_USED_CACHE_KEY))


def enforce_file_quota(doc, method=None):
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

		used = _used_bytes()
		# cheap cached read above; if it puts us anywhere near the limit, recompute
		# exactly so the cache's few-second lag can never wave an upload past quota.
		if (used + incoming) > quota * 0.9:
			used = _used_bytes(exact=True)
		projected = used + incoming
		over_limit = projected > quota
		# Keep the cached total in step with THIS upload. The cache is otherwise only
		# refreshed on a 30s miss or on delete, so without this a burst of uploads inside
		# the TTL window would each read the pre-burst total and could slip past quota
		# (the near-limit exact recompute above can't catch it when the STALE `used` is
		# itself low). Best-effort: a cache hiccup must never block a legitimate upload.
		if not over_limit:
			try:
				frappe.cache.set_value(_USED_CACHE_KEY, projected, expires_in_sec=_USED_CACHE_TTL)
				# If this insert is later rolled back (a downstream validation/permission
				# failure, etc.), the projected reservation would linger for up to the TTL
				# and wrongly block the tenant's NEXT small upload. Drop it on rollback so
				# the next read recomputes exactly. On COMMIT the reservation stands — that
				# is the burst-bypass guard. Guarded for older frappe without the hook.
				_bust_used_cache_on_rollback()
			except Exception:
				pass
	except Exception:
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
