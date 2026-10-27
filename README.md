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
| `build/releases/` | Release-specific image recipes, exact source manifests, frontend locks and retained patches. |
| `build/Containerfile`, `build/build.sh` | Historical build tooling; use the relevant release capsule for current images. |
| `build/apps.json`, `build/apps.pinned.json` | Historical manifests; current source identities are in `SOURCES.md` and the release capsule. |
| `patches/` | Human-readable description of our modifications to bundled apps. |
| `SOURCES.md` | The full manifest: every bundled app, its license, and its pinned commit. |

## Bundled applications

The bundled Frappe / ERPNext apps are **not** copied here — their source is their
public upstream repository at the commit pinned in the release manifest. See
`SOURCES.md` for the complete list of eleven upstream apps and licenses. Seven
are AGPLv3 (crm, drive, gameplan, helpdesk, insights, print_designer, telephony);
the rest are GPLv3 or MIT. Historical manifests also include apps no longer installed.

## Reproducing the running image

Use the [v224 release recipe](build/releases/v16-prod-224/README.md) and its immutable
manifest. It pins the v223 base and exact custom application commits; follow its
inherited manifests for upstream source and retained patches. Historical
`build/Containerfile` tooling alone does not reproduce the current service.
Private EAM repository access is required to rebuild its layer.

The [v225 candidate recipe](build/releases/v16-prod-225/README.md) is prepared
for the next framework upgrade; its publication alone does not mean production
has switched versions.

## License

`my_branding`'s own files are MIT-licensed (`license.txt`). Because the
application links to and modifies AGPLv3 applications at runtime, the deployed
combination is governed by AGPLv3, and this repository is the source offer for it.

Questions: **hello@nexumair.com** · Hosted offer page: <https://nexumair.com/source.html>
