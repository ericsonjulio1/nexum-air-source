# v16-prod-229

Deployed and verified on 17 November 2026 (Pacific/Port_Moresby; 16 November
22:28 UTC). Framework update built on the exact v228 image
(`sha256:aefceb2e19e8f100f0b1f93a1fe10019b8f3ef09d4b69e7a82dbeb2f92358e5b`):
Frappe 16.56.0, ERPNext 16.55.0, HRMS 16.53.2 and CRM 16.0.3 (CRM's
version-16 line). Helpdesk stays at 16.1.0 and Drive at v0.4.4, both
re-extracted and re-verified unchanged. Insights, Telephony, Print Designer,
Payments and Gameplan keep their v225 sources. No app is added or renamed.
The release carries nine new upstream migration patches (Frappe 1, ERPNext 7,
CRM 1).

Branding is `8cf99edd4da1a666f74de1f1cccedaf9533d2527`, unchanged since v228.
Private EAM is `97ebff6032d6f39500149233771e32377c31df6c` (v228's
`3146e4f...` plus a change to one test file only).

The deployed image is `ericsonjulio/erpnext:v16-prod-229`,
`sha256:fe553f13107d4209c8c6d157f3fc3a203e7f535eb4a901e6db795bf90e5ecbaa`.

## Python dependencies

v229 changes exactly two of the 243 pinned PyPI distributions; everything else
stays byte-identical to v228 (the v228 changes filelock 4.2.4, fonttools
4.68.0, oauthlib 4.0.1 and plutoprint 0.22.0 remain in place):

- **soupsieve 2.9.2 -> 4.1.1**, fixing GHSA-4j63-6c4x-wfg4, GHSA-6655-6qjp-jx7x,
  GHSA-7g44-g9rc-x53w and GHSA-mmhr-3c5m-f64f.
- **tornado 6.6 -> 6.6.1**, fixing GHSA-5cjw-f85j-cv6r.

The build installs these two wheels offline, hash-verified
(`uv pip install --require-hashes --no-index --find-links`), in the same
layer as the editable app installs, and `context/v229-tools/verify-dependencies.py`
proves before/after that this is the *entire* delta: the same 243
distributions, identical bytes on every untouched package, faithful
file-for-file installs of the two wheels, and nothing left over from the
replaced versions. A native import gate in the build then checks the six
delta distributions at their exact versions, that tornado's extension module
loads, and that a BeautifulSoup selector runs through soupsieve 4.1.1.

These two wheels are ordinary public PyPI packages. **They are not vendored in
this repository.** `prepare.py` downloads them from `files.pythonhosted.org`
using the exact URLs and SHA-256 hashes recorded in
`context/v229-tools/python-delta-wheels.json`, the same way it downloads the six
upstream application archives from GitHub's codeload. Unlike a GitHub source
archive, a PyPI file's bytes at a given URL never change, so a hash mismatch
here is fatal, not merely a note.

## Modifications

`context/v229-tools/source-overlays.json` lists all 49 modified files with
the SHA-256 of the pinned upstream file and of our version; the patched files
are in `context/v229-tools/source-overlay/`.

- **39 entries** are byte-identical to v228 (and, before that, to v225/v227).
- **10 entries were rebased** onto the new upstream bytes: 5 Frappe entries
  three-way merged onto Frappe 16.56.0 (`frappe/cache_manager.py`,
  `system_settings.json`, `patches.txt`, `web_form.py`, `pyproject.toml`) and
  5 ERPNext verify-only guards re-hashed because the upstream bytes moved under
  ERPNext 16.55.0 (`accounts/custom/address.py`, `payment_request.py`,
  `process_statement_of_accounts.py`, `request_for_quotation.py`,
  `stock/get_item_details.py`).
- **0 entries are new or removed.**

They carry forward the v225/v227/v228 modifications (security backports, chart
and sidebar fixes, migration cache, MCP default, Drive menu, PDF option
validation, frozen frontend locks and CRM's exact Pulse import map).
`apply-source.py` still refuses to run unless every target is exactly the
upstream file or exactly our version, and verifies the result again inside the
image. The two branding-layer guards added in v228 (the SPA Pulse import-map
guard and the PlutoPrint PDF guard) live in `my_branding` and are unchanged.

`my_branding`'s `docs/` and `ops/` directories (design notes; host deploy,
backup and firewall scripts) are never read inside the image, so the build
context leaves them out. `prepare.py` archives the branding commit without
them (`excluded_paths` in `manifest.json`).

## Image form

The Dockerfile in `context/` builds a *stacked* image on the v228 runtime
(`docker build --platform linux/amd64` on the prepared context, tagged locally
as `nexum-stacked:v16-prod-229-rc2`, never pushed). The deployed image is that
stacked image flattened into one layer: a second build,
`FROM scratch` + `COPY --from=<stacked image> / /`, that restates the stacked
image's configuration (environment, labels, volumes, work directory, user,
entrypoint and command), run with `--network none --pull=false`. A proof
compared the two: the flat image holds exactly the stacked image's filesystem
(441,341 entries, 6.90 GB of regular files; only four directory modification
times differ, and hardlink grouping is identical) with an identical
configuration. One Dockerfile step before the final checks removes three
dead build caches (`/home/frappe/.cache/yarn`, `/home/frappe/.cache/uv`,
`/home/frappe/.local/share/pnpm/store`).

## Reproducing the build context

```sh
python3 prepare.py NEW_DIRECTORY --branding PATH_TO_Nexum-Air [--eam PATH]
docker build --platform linux/amd64 NEW_DIRECTORY
```

Python 3.12+ and Git are required. The helper downloads the six pinned
upstream archives from GitHub, extracts the exact branding commit (without
`docs/` and `ops/`), downloads and hash-verifies the two pinned dependency
wheels from PyPI, applies the source overlays and compares every file, Git
blob, SHA-256 and permission with `context-files.json`. It refuses on any
difference. GitHub may recompress archives, so archive checksums there are
informational; the extracted files are what is verified. A PyPI wheel hash
mismatch is always fatal.

EAM is private. Without `--eam` the helper verifies the public context files
(15,010) but cannot produce a buildable context; `manifest.json` records EAM's
commit and Git tree. With both repositories the result was checked byte for
byte and mode for mode against the exact context that built the deployed
image: 15,011 public files verified by `prepare.py`, and all 19,200 files,
directories and links (EAM included) compared by a separate script. The check used fresh
downloads and ran with Python 3.14 and Python 3.12. A run without `--eam`
verified the 15,010 public files and reported the context as not buildable, as
expected. All runs found zero differences.

The final image is not claimed to be bit-for-bit reproducible: frontend
package downloads and file timestamps vary between builds.
