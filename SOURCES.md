# Nexum Air — Source Code & Licensing

Nexum Air is a hosted (SaaS) service operated by **Nordstern Engineering Design
Services** (Philippines). It is built on the [Frappe](https://frappeframework.com)
framework and a number of Frappe/ERPNext applications, several of which are
licensed under the **GNU Affero General Public License v3 (AGPLv3)**.

AGPLv3 §13 requires that anyone interacting with these programs over a network be
offered the **Corresponding Source** of the version running, at no charge. This
file is that offer. It lists every bundled application, its license, the exact
upstream commit we run, and our modifications.

> This is a developer/compliance document, not legal advice.

## How to obtain the Corresponding Source

- **Upstream apps** (the 11 Frappe/ERPNext apps below): the exact source we run is
  the upstream repository at the pinned commit listed in the table. These are
  public.
- **Our modifications** — the `my_branding` application (this repository) and the
  patches we apply to bundled apps at build time (see *Modifications* below). The
  complete buildable source corresponding to the running service is published at
  **<https://github.com/ericsonjulio1/nexum-air-source>** (also available at no charge
  by emailing **hello@nexumair.com**; offer page: <https://nexumair.com/source.html>).

## Bundled applications, licenses, and pinned commits

| App | License | Upstream | Pinned commit |
|-----|---------|----------|---------------|
| frappe (framework) | MIT | https://github.com/frappe/frappe | `2871914b69b6` |
| erpnext | GPLv3 | https://github.com/frappe/erpnext | `7474d9e78627` |
| hrms | GPLv3 | https://github.com/frappe/hrms | `7c037698ce57` |
| payments | MIT | https://github.com/frappe/payments | `cca07d9f9392` |
| **print_designer** | **AGPLv3** | https://github.com/frappe/print_designer | `7beaad298dd6` |
| **insights** | **AGPLv3** | https://github.com/frappe/insights | `5447f1621c0e` |
| **helpdesk** | **AGPLv3** | https://github.com/frappe/helpdesk | `78722c2b3643` |
| **crm** | **AGPLv3** | https://github.com/frappe/crm | `0d3910b456ef` |
| **gameplan** | **AGPLv3** | https://github.com/frappe/gameplan | `30d4f16f9f2c` |
| **drive** | **AGPLv3** | https://github.com/frappe/drive | `0bd11d8f4124` |
| **telephony** | **AGPLv3** | https://github.com/frappe/telephony | `039cf39f245d` |
| my_branding | MIT* | https://github.com/ericsonjulio1/nexum-air-source | main |

\* `my_branding` files are MIT-licensed, but because the application links to and
modifies AGPLv3 apps at runtime, the deployed combination is governed by AGPLv3
and `my_branding`'s source is offered accordingly.

## Current release: v16-prod-207

The [v207 recipe and immutable manifest](build/releases/v16-prod-207/README.txt)
layer the committed branding and Maintenance navigation changes over v206.
It restores Apps-mode brand icons, supplies icon colors for the existing Mac
client, moves Maintenance access under Assets, and routes Helpdesk's Nexum Air
and Desk shortcuts to the suite launcher. Upstream versions are unchanged.

## Base release: v16-prod-206

The exact incremental build recipe and immutable source manifest are in
[`build/releases/v16-prod-206`](build/releases/v16-prod-206/README.txt) in the public
source mirror. It updates Framework to 16.51.1, ERPNext and HRMS to 16.50.0, CRM to 1.87.0,
Helpdesk to 1.30.2, Insights to 3.14.2, and Print Designer to the pinned v16-compatible
main commit. Insights preserves its v2 interface and existing queries alongside v3.

That recipe retains Payments, Telephony, Drive and Gameplan from the immutable205
base image. Drive-to-Suite is a separate product/data migration and is not included.
The release compatibility scripts cover the new Sidebar model, archived sidebars
for absent apps, authorized Web Form attachments, Gameplan's structured SQL aggregates,
and concurrent service startup. The Framework standard-field and domain-cache
protections remain; the old Workspace Sidebar return patch and Insights SSL patch
are superseded by the new upstream implementations. HRMS's security fix is native.

EAM is a separately maintained custom application, pinned in the release manifest.
Its private repository is not copied into this public mirror.

## Modifications we make to bundled apps

The following describes the205 base modifications. The206 recipe above identifies
retained and superseded patches; both sets of build scripts are included:

1. **gameplan** (AGPLv3) — `gameplan/api.py`: guard a `from frappe.config import
   get_modules_from_all_apps_for_user` import that was removed in Frappe v16, so
   the uncaught `ImportError` no longer 500s the desk launcher. Falls through to
   the existing role check.
2. **Branding / runtime relabeling** — the `my_branding` application relabels app titles,
   workspace labels, icons, and post-processes the served HTML of the standalone
   frappe-ui SPAs (CRM, Helpdesk, Insights, Drive, Gameplan) to apply Nexum Air
   branding. No business logic of the AGPL apps is changed.
3. **Static asset override** — a Nexum Air image replaces Frappe's `framework.png` (MIT).
4. **Service-worker neutralizer** — `my_branding` unregisters any root-scope service
   worker left in a browser (Slides, bundled until August 2026, registered one) on the
   desk/SPAs; a stale-asset fix.
5. **insights** (AGPLv3) — `insights/.../sources/frappe_db.py`: drop the
   hardcoded `ssl_verify_cert=True` (SiteDB) / make it follow `use_ssl` (external
   FrappeDB), so connecting to the trusted local MariaDB over the private Docker
   network no longer fails cert verification against our self-signed cert.
   See `patches/insights_ssl_patch.py`.
6. **frappe** (MIT) — `frappe/cache_manager.py` and
   `frappe/desk/doctype/workspace_sidebar/workspace_sidebar.py`: two upstream bugs hid
   every DocType/Page link in the workspace sidebars from non-Administrator users
   (untagged doctypes missing from the domain cache; a missing `return`). See
   `patches/frappe_sidebar_visibility.py`.
7. **Security backports** — upstream security fixes applied to the pinned versions
   before a release that includes them:
   - **frappe** (MIT) `frappe/client.py`: the `set_value` standard-field guard
     (GHSA-2c6h-wv85-fxvj).
   - **hrms** (GPLv3) `hrms/payroll/doctype/salary_structure/salary_structure.py`: the
     sanitised salary-component search (GHSA-jfmr-9jv9-mrw4).

   Each patched file is the pinned upstream file plus exactly the upstream security
   hunks. See `patches/security-2026-08-22.md` and `patches/security-2026-08-22/`.

Earlier modifications that are now part of the pinned upstream versions (the patch
scripts in `patches/` detect this and change nothing): the erpnext Growth-view fix for
columnar financial reports, the frappe Package Import TarSlip fix (GHSA-58w2-4cjg-hvp6),
and the other 2026-08-22 frappe/erpnext security backports.

## Reproducing the build

Exact app commits are pinned in `saas/image/apps.pinned.json`; the image is built
by `saas/image/Containerfile` + `build.sh`. Checking out each app at its pinned
commit, applying the modifications above, and building reproduces the running
service.
