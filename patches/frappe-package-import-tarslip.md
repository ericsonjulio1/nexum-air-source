# Patch: frappe Package Import — TarSlip path-traversal / RCE fix

**App:** frappe (AGPLv3) · **File:** `frappe/core/doctype/package_import/package_import.py`
**Advisory:** GHSA-58w2-4cjg-hvp6 / CVE-2026-55852 (HIGH) · **Fixed upstream in:** frappe ≥ 16.23.0
**We pin:** frappe 16.22.0 · **First shipped:** image `v16-prod-106` (2026-07-07)

## What upstream did wrong (in 16.22.0)
`PackageImport.import_package()` extracted an uploaded `<name>-x.y.z.tar.gz` by
shelling out to `subprocess.check_output(["tar", "xzf", <archive>, "-C", <packages>])`
with no validation of the archive members. A crafted tar containing `../`
traversal paths or symlink/hardlink members could therefore write files outside
the intended `packages/` directory — an arbitrary file write that leads to remote
code execution. The endpoint requires the **System Manager** role, which on our
platform every tenant owner holds on their own site, so on a shared bench this is
a cross-tenant risk.

## Our modification
We replace the file with the exact upstream-fixed version (frappe ≥ 16.23.0). The
patched `import_package()`:
- extracts with Python's `tarfile` instead of a shell `tar`,
- rejects any symlink or hardlink member,
- validates every member path with `check_path_safety(extract_path, member_path)`
  (this helper already exists in our pinned 16.22.0 `frappe/core/doctype/file/utils.py`),
- sanitizes the derived package name, and
- calls `tar.extractall(path=..., filter="data")`.

Our pinned 16.22.0 file differs from the upstream-fixed file **only** by this
security diff (verified byte-for-byte on 2026-07-07).

## How it is applied
`frappe_package_import_tarslip.py` in this directory is the idempotent,
drift-guarded patcher (it embeds the full patched file; it is a no-op if the file
is already fixed and fails the build loudly if the upstream file shape has moved).
The image build runs it against the baked frappe app. Drop this patch once we bump
frappe to ≥ 16.23.0.
