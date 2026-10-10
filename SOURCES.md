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
| frappe (framework) | MIT | https://github.com/frappe/frappe | `97a5dd93ca58` |
| erpnext | GPLv3 | https://github.com/frappe/erpnext | `af63cde49415` |
| hrms | GPLv3 | https://github.com/frappe/hrms | `f281e8b172ac` |
| payments | MIT | https://github.com/frappe/payments | `cca07d9f9392` |
| **print_designer** | **AGPLv3** | https://github.com/frappe/print_designer | `9d62227e20d1` |
| **insights** | **AGPLv3** | https://github.com/frappe/insights | `c9af45de73b3` |
| **helpdesk** | **AGPLv3** | https://github.com/frappe/helpdesk | `480486287b2b` |
| **crm** | **AGPLv3** | https://github.com/frappe/crm | `49d98d61e7d4` |
| **gameplan** | **AGPLv3** | https://github.com/frappe/gameplan | `30d4f16f9f2c` |
| **drive** | **AGPLv3** | https://github.com/frappe/drive | `0bd11d8f4124` |
| **telephony** | **AGPLv3** | https://github.com/frappe/telephony | `039cf39f245d` |
| my_branding | MIT* | https://github.com/ericsonjulio1/nexum-air-source | main |

\* `my_branding` files are MIT-licensed, but because the application links to and
modifies AGPLv3 apps at runtime, the deployed combination is governed by AGPLv3
and `my_branding`'s source is offered accordingly.

## Modifications we make to bundled apps

These are applied at image-build time (see `saas/image/Containerfile`) and are part
of the Corresponding Source:

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
