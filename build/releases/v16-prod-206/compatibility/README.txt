Release 206 compatibility changes:
- sidebar_code_only.py permits authored shells to reuse only code-only module names,
  including EAM's Maintenance shell, and keeps resolver identity consistent.
- Framework UI's upstream yarn.lock was inconsistent with package.json. The lock
  was regenerated with Yarn 1.22.22; the image uses frozen-lockfile thereafter.
- cache_manager.py retains the existing domain cache patch for untagged entities.
  The old Workspace Sidebar missing-return patch is retired: its replacement
  Sidebar inherits the corrected DeskViews implementation.
- client.py retains the vetted mass-assignment field guard. All 17 security
  checks pass; HRMS's former SQLi backport is now present upstream.
- New Insights connectors contain the local no-SSL behavior upstream.
