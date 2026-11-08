# v16-prod-228

Deployed and verified on 9 November 2026 (Pacific/Port_Moresby; 8 November
21:45 UTC). Framework update built on the exact v227 image: Frappe 16.55.2,
ERPNext 16.54.0, HRMS 16.53.1, CRM 16.0.2 (CRM's version-16 renumbering of the
1.91.x line, not an unrelated rewrite) and Helpdesk 16.1.0. Drive stays at
v0.4.4, re-extracted and re-verified unchanged. Insights, Telephony, Print
Designer, Payments and Gameplan keep their v225 sources. No app is added or
renamed.

Branding is `8cf99edd4da1a666f74de1f1cccedaf9533d2527` (v227's
`66897f3a9...` plus release records and the two guards below). Private EAM is
`3146e4f524df673c49524248e9518f495b2fd31b` (ERPNext 16.54 compatibility
fixes).

## Python dependencies (first change since v225)

v228 changes exactly four of the 242 pinned PyPI distributions; everything
else stays byte-identical to v225/v226/v227:

- **filelock 3.20.4 -> 4.2.4**, fixing six filelock advisories.
- **fonttools 4.63.0 -> 4.68.0.**
- **oauthlib 4.0.0 -> 4.0.1**, fixing GHSA-3jp2-3mrg-2vxc.
- **plutoprint 0.22.0**, new (see the PDF guard below for why it is present
  but blocked).

The build installs these four wheels offline, hash-verified
(`uv pip install --require-hashes --no-index --find-links`), in the same
layer as the editable app installs, and `context/v228-tools/verify-dependencies.py`
proves before/after that this is the *entire* delta: same 242-to-243
distribution count change, identical bytes on every untouched package,
faithful file-for-file installs of the four wheels, and nothing left over
from the replaced versions.

These four wheels are ordinary public PyPI packages. **They are not vendored
in this repository.** `prepare.py` downloads them from
`files.pythonhosted.org` using the exact URLs and SHA-256 hashes recorded in
`context/v228-tools/python-delta-wheels.json`, the same way it already
downloads the six upstream application archives from GitHub's codeload. This
keeps the source mirror free of ~25 MB of compiled binary wheels (most of it
the PlutoPrint wheel, which bundles its own native libraries) while still
reproducing byte-identical input to the build. Unlike a GitHub source
archive, a PyPI file's bytes at a given URL never change, so a hash mismatch
here is fatal, not merely a note.

## Modifications

`context/v228-tools/source-overlays.json` lists all 49 modified files with
the SHA-256 of the pinned upstream file and of our version; the patched files
are in `context/v228-tools/source-overlay/`. 35 entries are byte-identical to
v227 (and, before that, to v225). 8 entries that only *verify* an
already-upstream-fixed file were re-hashed because the upstream bytes moved
under Frappe 16.55.2 / Helpdesk 16.1.0; 6 entries were three-way merged onto
the new upstream so the carried fix still applies. They carry forward the
v225/v227 modifications (security backports, chart and sidebar fixes,
migration cache, MCP default, Drive menu, PDF option validation, frozen
frontend locks, and v227's CRM-only Frappe Pulse import map) onto the new
upstream versions. No source-overlay entry changed in this release beyond
that rebase; `apply-source.py` still refuses to run unless every target is
exactly the upstream file or exactly our version, and verifies the result
again inside the image.

Two further changes are **in `my_branding`, not in the source-overlay
upstream patch set**, because they are branding-layer hooks rather than
edits to vendored upstream files:

- **SPA Pulse import-map guard (all frappe-ui apps).** v227 only rewrote
  CRM's own `frontend/index.html`. v228 adds a guard inside
  `my_branding`'s existing SPA-branding response hook
  (`spa_brand.inject_brand_assets`) that injects or merges an import map
  resolving `https://pulse.m.frappe.cloud/assets/pulse/js/pulse_client.js`
  to a local no-op module (`my_branding/public/js/nexum-pulse-noop.js`) on
  **every** branded SPA route (Helpdesk, Insights, CRM, Drive, Gameplan, and
  any other app in `brand_config.spa_brand()`), not just CRM. CRM's own
  v227 overlay import map is left as-is (recognized as an equivalent
  mapping, so the guard does not double it). The browser therefore never
  requests the remote Pulse telemetry host from any of these apps.
- **PlutoPrint PDF guard.** PlutoPrint vendors its own bundled, older
  libcurl/openssl, so `my_branding` refuses to let it actually generate a
  PDF even though the dependency is now installed (ERPNext/Frappe's own
  `pyproject.toml` requires it). The guard validates Print Settings and
  Print Format (no document may select PlutoPrint), refuses any request
  that resolves to PlutoPrint at render time (including the Print Designer
  overlay's own resolution path and the `pdf_generator` request
  parameter), and heals stored PlutoPrint values back to the default on
  migrate. wkhtmltopdf, Chrome and Typst are unaffected.

## Reproducing the build context

```sh
python3 prepare.py NEW_DIRECTORY --branding PATH_TO_Nexum-Air [--eam PATH]
docker build --platform linux/amd64 NEW_DIRECTORY
```

Python 3.12+ and Git are required. The helper downloads the six pinned
upstream archives from GitHub, extracts the exact branding commit, downloads
and hash-verifies the four pinned dependency wheels from PyPI, applies the
source overlays and compares every file, Git blob, SHA-256 and permission
with `context-files.json`. It refuses on any difference. GitHub may
recompress archives, so archive checksums there are informational; the
extracted files are what is verified. A PyPI wheel hash mismatch is always
fatal.

EAM is private. Without `--eam` the helper verifies the 15,010 public context
files but cannot produce a buildable context; `manifest.json` records EAM's
commit and Git tree. With both repositories the result was checked byte for byte and mode for mode
against the exact context that built the deployed image: 15,011 public files
verified by `prepare.py`, and all 19,206 files, directories and links (EAM
included) compared by a separate script. The check used fresh downloads and
ran with Python 3.14 and Python 3.12. A run without `--eam` verified the
15,010 public files and reported the context as not buildable, as expected.
All runs found zero differences.

The Dockerfile starts from the pinned v227 image and rebuilds the frontend
assets of the replaced applications with frozen lockfiles. Like earlier
releases, the final image is not claimed to be bit-for-bit reproducible:
frontend package downloads and file timestamps vary between builds.
