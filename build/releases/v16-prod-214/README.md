# v16-prod-214

Financial Overview and Maintenance Workbench now use native Frappe page actions, tabs, controls, cards, tables and theme tokens. Financial calculations and maintenance transactions remain unchanged.

The ERP application is labeled **ERP** throughout the launcher, dock and app-switcher return entries. Its new connected-modules icon matches the suite icons. Nexum Air remains the company and suite brand.

This release extends the immutable v213 image. `apply_frontend.py` validates the exact SHA-256 of seven inherited source files before applying narrowly scoped app labels/icon paths. CRM, Helpdesk, Insights (both versions), Drive, Teams and HRMS Roster are rebuilt with inherited dependencies. No upstream framework upgrade or minified output rewrite is included.

## Build

Run `prepare.py --branding /path/to/my_branding --eam /path/to/eam` to archive the manifest commits, then build this directory with Docker for `linux/amd64`. Generated source archives are ignored by Git. The manifest records the published image digest after the build passes acceptance.

## Acceptance

Required release gates include four-site staging migration and repeat migration, accounting/operational parity, financial lifecycle smoke, native page interactions in browser and the Mac app, responsive/theme checks, and suite app-switcher regressions. Production uses fresh verified backups, a maintenance barrier, the canonical deployment script and read-only post-release checks. Private configurations, sessions, backups and business data are excluded from this repository.
