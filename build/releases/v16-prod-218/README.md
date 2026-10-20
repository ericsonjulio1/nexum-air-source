# v16-prod-218

A request for `/<doctype>/<name>` whose doctype matches a DocType only without regard to letter
case, such as `/bin/.env` or `/project/x`, now receives the 404 page. Frappe's print route accepted
those paths and its print view then failed to load the lowercase controller, answering 500. A
`my_branding` page renderer claims only those paths, and only when no renderer ahead of the print
route serves them; exact-case print routes and every other route are unchanged. Tests cover the
miscased, exact-case and unrelated paths. The ops scripts in the private repository changed too;
they are not part of the combined work.

The immutable v217 base retains the exact upstream framework (Frappe 16.52.0, ERPNext 16.51.1,
HRMS 16.51.0, CRM 1.88.0, Helpdesk 1.31.0, Insights 3.15.0), its security fixes, the compiled SPA
bundles and EAM `05c867e`. Only the `my_branding` tree changes, from `8fd8cc3` to `636bb1a`;
dependencies are not upgraded and no historical patcher runs.

Run `prepare.py --branding /path/to/my_branding`, then build this directory for `linux/amd64`.
Generated archives are ignored by Git. The manifest records the accepted registry digest. This
mirror's `my_branding/` directory is at `636bb1a`, the commit production runs.

The production image was produced by overlaying the files that changed between `8fd8cc3` and
`636bb1a` onto v217. It was verified against `636bb1a` file for file: all 387 tracked files match by
Git blob id, with no extra source files. Everything outside `apps/my_branding` is byte-identical to
v217, so this recipe's full-tree replacement yields the same application source.

Release gates covered the provenance and scope checks above. On an isolated stack, the demo golden
database was restored and migrated on v217 and on v218, and the same Guest requests were sent
through the application on both: v217 answered 500 for the miscased routes, v218 answered 404,
including when the 404 page was served from the page cache, and every other route answered the
same. The changed test modules passed under bench. The release then took fresh production backups
and ran the canonical deploy: migrate, site verification and the financial lifecycle smoke test.
The kit was independently reviewed with OpenAI Codex. Evidence is recorded privately without
credentials or business data.
