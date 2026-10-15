Nexum Air v16-prod-212 — empty chart lifecycle completion

This release extends the v211 chart cleanup to the native "No data yet"
placeholder. Repeated redraws previously retained each placeholder's chart and
resize listener after its DOM was removed. Widgets now own and destroy their
empty chart when redrawn, replaced by actual data, refreshed, or removed. A late
empty response cannot recreate a chart after its widget has been deleted.
The native chart component factory also copies its shared defaults before adding
an instance's bound data callback. It previously retained the last chart through
those shared defaults even after the owner correctly destroyed it.

The immutable v211 base retains the Teams resource/fetch fixes, suite navigation,
branding, shared theme and financial UI. No schemas or accounting logic change.
The adapter checks both exact v211 source SHA-256 values and all three published
chart entrypoints before editing. The npm package's prebuilt ESM, UMD and CommonJS
entrypoints receive the identical source fix; Framework imports those entrypoints.
The Framework bundle is rebuilt; the runtime asset manifest is copied into assets.

Build
docker build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-212 .

Validation
- empty_chart.test.cjs runs in the image build and covers repeated redraw,
  deletion, repeated cleanup, the transition from a placeholder to real data,
  an empty response arriving after widget deletion, and native component isolation
  in both source and the three published entrypoints.
- browser_empty_chart.py exercises the installed ChartWidget with a disposable
  DOM-only fixture. Ten redraws must retain one connected chart after animation
  timers settle and GC; the owner's cleanup must leave none. It holds only WeakRefs.
- Re-run v211/lifecycle.test.cjs and v211/browser_performance.py to check the
  inherited Teams resource, single-fetch, tab freshness and populated-chart fixes.
- Run the existing navigation/theme/financial smoke checks, native Mac checks,
  and migrations on all restored staging sites before deployment.

Browser environment: BASE_URL, OUTPUT_DIR, CHROMIUM_PATH, SID_FILE (temporary
JSON containing sid), and optional CHROMIUM_HOST_RULES for an origin tunnel.
Output contains only aggregate lifecycle evidence, never session credentials.
