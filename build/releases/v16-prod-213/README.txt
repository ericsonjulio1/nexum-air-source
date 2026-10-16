Nexum Air v16-prod-213 — Maintenance navigation refinement

Release source pins and immutable registry digest are recorded in manifest.json.

This incremental image inherits immutable v212, including its chart/resource
lifecycle fixes. It overlays only committed my_branding and eam sources.
No framework/SPA bundle rebuild, upstream version bump, database schema change,
or accounting calculation change is intended. The underlying native Maintenance
shortcut and document permissions stay intact; its four section links are
rendered by the branding adapter. Maintenance Workbench remains in the sidebar.
The native full-width invisible row break remains between KPI and transaction
cards; only its visible separator border and the duplicated Workbench links retire.

Reproduce this build
1. Check out the exact custom-app commits in manifest.json. The Dockerfile labels
   must match those pins. Keep the v212 base digest unchanged.
2. Confirm all changed browser assets are served directly and the branding asset
   version has changed. If changes require compiled bundles, revise this recipe
   and validate the rebuild rather than assuming an overlay is enough.
3. python3.14 prepare.py --branding /path/to/my_branding --eam /path/to/eam
   This archives only the pinned commits, not working-tree changes or credentials.
4. docker build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-213 .

Validation and publication
- Run focused branding client tests and EAM workspace/sidebar regression tests.
- Use isolated production-copy staging; migrate all four sites and repeat
  migration to verify the reconciler is idempotent.
- Browser and native Mac checks: Assets Maintenance card has Work Orders,
  PM Planning, Reports and Spare Parts links; links open their matching section
  without losing the dock/sidebar; native group guides render correctly; the
  workspace Workbench banner and duplicate body link are gone; sidebar Workbench
  still opens; Accounts Home and Financial Overview remain available; existing
  shared themes, chart style and cross-app navigation remain intact.
- Run the normal financial smoke and compare the business/accounting baseline.
- Push the tested immutable image, record its registry digest in manifest.json,
  and verify the deployed tag resolves to that exact digest before cutover.
- Keep prepared my_branding/ and eam/ directories out of the public Git commit;
  the referenced repositories and pins are the corresponding-source record.

Production deployment uses the separately reviewed local coordinator and its
explicit staging gates. It is not part of this public build context. Never copy
site configuration, authentication/session files, backups or private QA evidence
into this directory.
