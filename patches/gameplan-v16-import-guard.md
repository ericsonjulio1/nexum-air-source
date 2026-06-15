# Patch: gameplan — guard a Frappe v16-removed import

**App:** `gameplan` (AGPLv3) · **File:** `gameplan/gameplan/api.py` ·
**Function:** `can_access_gameplan`

This is the only modification we make to an AGPL application's source. It is
applied at image-build time by `build/Containerfile` (search for "gameplan v16").

## Why

Gameplan's `can_access_gameplan` imports
`from frappe.config import get_modules_from_all_apps_for_user`, which was removed
in Frappe v16. The import sits at the top of the function, so the uncaught
`ImportError` propagates through `frappe.boot.load_desktop_data` and returns
HTTP 500 for the desk app launcher for every logged-in user. We guard the import
and fall through to the existing role check. No feature or permission behaviour
changes. It becomes a no-op once upstream removes the import.

## Change

```python
# BEFORE
def can_access_gameplan():
	from frappe.config import get_modules_from_all_apps_for_user

	if frappe.session.user == "Administrator":
		return True

	allowed_modules = [x["module_name"] for x in get_modules_from_all_apps_for_user()]
	if "Gameplan" not in allowed_modules:
		return False
	...

# AFTER
def can_access_gameplan():
	if frappe.session.user == "Administrator":
		return True

	try:
		from frappe.config import get_modules_from_all_apps_for_user

		allowed_modules = [x["module_name"] for x in get_modules_from_all_apps_for_user()]
		if "Gameplan" not in allowed_modules:
			return False
	except ImportError:  # removed in frappe v16 - rely on the role check
		pass
	...
```

The exact upstream commit we patch is pinned in `build/apps.pinned.json`.
