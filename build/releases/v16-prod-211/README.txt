Nexum Air v16-prod-211 — resource and chart lifecycle fixes

This incremental release uses the immutable v210 image in manifest.json. It
retains that release's navigation, branding, shared theme and financial UI.
No upstream version, database schema or accounting calculation changes.

Changes
- Teams' uncached list resources unregister from row-update fanout and remove
  their own realtime callback when their owning component unmounts or replaces
  its resource options. Shared cached resources remain available to other users
  of that cache within the same page. Submitted writes are not cancelled.
- Discussion lists use auto-fetch on their first activation. Revisiting a
  kept-alive feed still refreshes; it does not duplicate an already active fetch.
- Dashboard widgets destroy old native charts before refreshing, replacing or
  deleting them. Removed widgets cannot render after a pending settings load.
- Chart destruction also disconnects Nexum label observers and resize listeners;
  an already queued animation frame cannot measure the destroyed chart.

apply_runtime.py checks all five v210 source hashes before writing any file. It
contains the complete upstream changes (including the Teams frappe-ui dependency).
The build reuses pinned dependencies and rebuilds Teams and Framework assets.
The runtime asset manifest is preserved in the image's assets directory.

Build
1. python3.14 prepare.py --branding /path/to/my_branding --eam /path/to/eam
2. docker build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-211 .
The preparation step archives only the Git commits pinned in manifest.json.

Validation
- lifecycle.test.cjs runs in the build against the patched implementation and
  actual Vue reactive proxies. It covers uncached cleanup, shared cache ownership,
  options replacement, realtime listener removal, activation, and chart deletion.
- Run the branding repository's Node client tests (including chart destruction).
- browser_performance.py uses an isolated authenticated browser to check twenty
  route cycles, one request per feed visit, fresh kept-alive tabs/sort changes,
  and ten real dashboard Refresh actions followed by forced garbage collection.
  It holds only WeakRefs to charts and never disposes them itself.
- Run the existing navigation/theme/financial UI smoke checks and all-site
  migrations on an isolated restored staging clone before production deployment.

Browser check environment: BASE_URL, OUTPUT_DIR, CHROMIUM_PATH and either
SID_FILE (a temporary JSON session file) or USER_ID/PASSWORD. Optional
CHROMIUM_HOST_RULES supports an origin tunnel. Evidence contains aggregate
counts and request filters; it does not contain session credentials or heap dumps.
