# v16-prod-227

Deployed and verified on 7 November 2026 (Pacific/Port_Moresby; 6 November
19:30 UTC). Framework update built on the exact v226 image: Frappe 16.54.0,
ERPNext 16.53.0, HRMS 16.53.0, CRM 1.91.1, Helpdesk 1.31.1 and Drive 0.4.4.
Insights, Telephony, Print Designer, Payments and Gameplan keep their v225
sources. No app is added or renamed, and no Python dependency changes: the
hashed v225 package locks and every non-application distribution in the v226
image are verified unchanged during the build.

Branding is `66897f3a946e5a8034720d000313bc874c19291c` (empty watchdog lead
results and Helpdesk 1.31.1 upgrade fixtures). Private EAM is
`c65980f7fbd995759982952e2bf564a20038279a` (current locking reads for Start
Work, job plans and workbench receipts).

## Modifications

`context/v227-tools/source-overlays.json` lists all 49 modified files with the
SHA-256 of the pinned upstream file and of our version; the patched files are
in `context/v227-tools/source-overlay/`. They carry the v225 modifications
forward (security backports, chart and sidebar fixes, migration cache, MCP
default, Drive menu, PDF option validation and frozen frontend locks) onto the
new upstream versions, and add one:

- **CRM (AGPLv3), Frappe Pulse telemetry removed.** CRM 1.91.1 loads a remote
  analytics client from `pulse.m.frappe.cloud`. `frontend/index.html` gains an
  import map that resolves that URL to `nexum-pulse-client-noop.js`, a local
  module whose methods do nothing, so the browser makes no request to the
  telemetry host. `patchers/crm-pulse/verify.py` checks the built output.

`apply-source.py` refuses to run unless every target is exactly the upstream
file or exactly our version, and verifies the result again inside the image.

## Reproducing the build context

```sh
python3 prepare.py NEW_DIRECTORY --branding PATH_TO_Nexum-Air [--eam PATH]
docker build --platform linux/amd64 NEW_DIRECTORY
```

Python 3.12+ and Git are required. The helper downloads the six pinned upstream
archives from GitHub, extracts the exact branding commit, applies the source
overlays and compares every file, Git blob, SHA-256 and permission with
`context-files.json`. It refuses on any difference. GitHub may recompress
archives, so archive checksums are informational; the extracted files are what
is verified.

EAM is private. Without `--eam` the helper verifies the 14,917 public context
files but cannot produce a buildable context; `manifest.json` records EAM's
commit and Git tree. With both repositories the result was checked
byte-for-byte against the context that built the deployed image (15,674 files,
all permissions), with fresh downloads and with Python 3.12 and 3.15.

The Dockerfile starts from the pinned v226 image and rebuilds the frontend
assets of the replaced applications with frozen lockfiles. Like earlier
releases, the final image is not claimed to be bit-for-bit reproducible:
frontend package downloads and file timestamps vary between builds.
