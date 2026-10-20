# v16-prod-217

The demo site's after-migrate reconciler follows the Frappe 16.50+ navigation model. It no longer
rewrites the archived Workspace Sidebar rows, which keep Frappe's Sidebar conversion re-runnable.
It checks the navigation the demo login actually resolves instead, and records a problem rather
than repairing anything. Tests cover the 16.50+ path, session-user restoration and a missing demo
user. The ops watchdog sources in the private repository changed too; they are not part of the
combined work.

The immutable v216 base retains the exact upstream framework (Frappe 16.52.0, ERPNext 16.51.1,
HRMS 16.51.0, CRM 1.88.0, Helpdesk 1.31.0, Insights 3.15.0), its security fixes, the compiled SPA
bundles and EAM `05c867e`. Only the `my_branding` tree changes, from `96c6e48` to `8fd8cc3`;
dependencies are not upgraded and no historical patcher runs.

Run `prepare.py --branding /path/to/my_branding`, then build this directory for `linux/amd64`.
Generated archives are ignored by Git. The manifest records the accepted registry digest.

The production image was produced by overlaying the files that changed between `96c6e48` and
`8fd8cc3` onto v216. It was verified against `8fd8cc3` file for file: all 384 tracked files match by
Git blob id, with no extra source files. Everything outside `apps/my_branding` is byte-identical to
v216, so this recipe's full-tree replacement yields the same application source.

This mirror's `my_branding/` directory is at `8800ef6`. That commit differs from the running
`8fd8cc3` only in test fixtures: the watchdog reset-detection test's sample process paths, which
named a host directory the mirror does not publish. No runtime file differs.

Release gates covered the provenance and scope checks above. On an isolated stack, the demo golden
database was restored and migrated on v216, which reproduces the defect, and on v217, which ran
clean with the demo user's navigation verified. The changed test modules passed under bench. The
release then took fresh production backups and ran the canonical deploy: migrate, site
verification and the financial lifecycle smoke test. The kit was independently reviewed with
OpenAI Codex. Evidence is recorded privately without credentials or business data.
