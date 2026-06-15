# Nexum Air — Corresponding Source

This repository is the **Corresponding Source** for the open-source software that
powers [Nexum Air](https://nexumair.com), published to satisfy the **GNU Affero
General Public License v3 (AGPLv3) §13** for the AGPL-licensed applications we run.

Nexum Air is a hosted (SaaS) ERP service operated by **Nordstern Engineering
Design Services** (Philippines), built on the [Frappe](https://frappeframework.com)
framework and a number of Frappe / ERPNext applications.

## What's here

| Path | Contents |
|------|----------|
| `my_branding/` | Our application — branding, naming, role profiles, storage quotas, and the runtime customisations layered on top of the apps below. This is the work that links to and modifies the AGPL apps. |
| `build/Containerfile` | The image recipe: which apps are installed, and the build-time modifications (including the one app patch). |
| `build/build.sh` | The build script. |
| `build/apps.json`, `build/apps.pinned.json` | The app manifest and the **exact upstream commit** each bundled app is pinned to. |
| `patches/` | Human-readable description of our modifications to bundled apps. |
| `SOURCES.md` | The full manifest: every bundled app, its license, and its pinned commit. |

## Bundled applications

The bundled Frappe / ERPNext apps are **not** copied here — their source is their
public upstream repository at the commit pinned in `build/apps.pinned.json`. See
`SOURCES.md` for the complete list with licenses. Ten of them are AGPLv3
(builder, crm, drive, gameplan, helpdesk, insights, lms, print_designer, slides,
telephony); the rest are GPLv3 or MIT.

## Reproducing the running image

1. Check out each app from `build/apps.json` at the commit in `build/apps.pinned.json`.
2. Place this `my_branding/` directory into the bench's `apps/`.
3. Build with `build/Containerfile` (it applies our modifications, documented in `patches/`).

## License

`my_branding`'s own files are MIT-licensed (`license.txt`). Because the
application links to and modifies AGPLv3 applications at runtime, the deployed
combination is governed by AGPLv3, and this repository is the source offer for it.

Questions: **hello@nexumair.com** · Hosted offer page: <https://nexumair.com/source.html>
