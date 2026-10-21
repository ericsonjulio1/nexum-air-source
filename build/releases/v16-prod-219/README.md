# v16-prod-219

Charts with only a few columns, such as a yearly Profit and Loss, no longer show wide bars that
snap narrower a moment after the page opens. `my_branding` keeps chart bars at most 56 px wide.
It used to narrow them after frappe-charts had drawn, so the library's entry animation still ran
at its own width for about 400 ms. It now sets frappe-charts' bar spacing for each draw, so every
draw, animation, update and resize is sized correctly from the first frame. An author's own
spacing stays the minimum, and frappe's realtime chart is covered too. Tests cover the width
calculation and a browser run of the shipped code.

The immutable v218 base retains the exact upstream framework (Frappe 16.52.0, ERPNext 16.51.1,
HRMS 16.51.0, CRM 1.88.0, Helpdesk 1.31.0, Insights 3.15.0), its security fixes, the compiled SPA
bundles and EAM `05c867e`. Only the `my_branding` tree changes, from `636bb1a` to `16fae11`;
dependencies are not upgraded and no historical patcher runs.

Run `prepare.py --branding /path/to/my_branding`, then build this directory for `linux/amd64`.
Generated archives are ignored by Git. The manifest records the accepted registry digest. This
mirror's `my_branding/` directory is at `16fae11`, the commit production runs.

The production image was produced by overlaying the files that changed between `636bb1a` and
`16fae11` onto v218. It was verified against `16fae11` file for file: all 389 tracked files match by
Git blob id, with no extra source files. Everything outside `apps/my_branding` is byte-identical to
v218, so this recipe's full-tree replacement yields the same application source.

Release gates covered the provenance and scope checks above, and checked that the served
`brand.js` is the reviewed file. In a headless browser with the production frappe-charts build,
v218's code drew bars wider than 56 px for 34 to 36 frames in each few-column scenario; v219's
drew none in any scenario, including stacked, mixed and mid-animation resize. On an isolated
stack the demo golden database was restored and migrated on v218 and v219, with the demo
navigation and route checks clean on both and the changed test modules passing under bench. The
release then took fresh production backups and ran the canonical deploy: migrate, site
verification and the financial lifecycle smoke test. OpenAI Codex implemented the change and the
release kit, and Claude reviewed both. Evidence is recorded privately without credentials or
business data.
