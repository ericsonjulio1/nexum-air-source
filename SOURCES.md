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

- **Upstream apps** (the 17 Frappe/ERPNext apps below): the exact source we run is
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
| frappe (framework) | MIT | https://github.com/frappe/frappe | `567c05b6b7b7` |
| erpnext | GPLv3 | https://github.com/frappe/erpnext | `054b20a2ae1b` |
| hrms | GPLv3 | https://github.com/frappe/hrms | `576d99135cd0` |
| payments | MIT | https://github.com/frappe/payments | `cca07d9f9392` |
| lending | GPLv3 | https://github.com/frappe/lending | `6c6d4988c79f` |
| webshop | GPLv3 | https://github.com/frappe/webshop | `1a5239d44828` |
| ecommerce_integrations | GPLv3 | https://github.com/frappe/ecommerce_integrations | `ba8ac5055fd6` |
| **print_designer** | **AGPLv3** | https://github.com/frappe/print_designer | `9d62227e20d1` |
| **insights** | **AGPLv3** | https://github.com/frappe/insights | `57d1d053b91d` |
| **helpdesk** | **AGPLv3** | https://github.com/frappe/helpdesk | `f4cba24df6af` |
| **crm** | **AGPLv3** | https://github.com/frappe/crm | `9b0aa041d734` |
| **gameplan** | **AGPLv3** | https://github.com/frappe/gameplan | `6af88020e7cf` |
| **lms** | **AGPLv3** | https://github.com/frappe/lms | `cea72f8b668a` |
| **drive** | **AGPLv3** | https://github.com/frappe/drive | `6355907291bc` |
| **builder** | **AGPLv3** | https://github.com/frappe/builder | `54e2561f7846` |
| **slides** | **AGPLv3** | https://github.com/frappe/slides | `162973a4acc9` |
| **telephony** | **AGPLv3** | https://github.com/frappe/telephony | `58d32184e44b` |
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
2. **Branding / runtime relabeling** — the `my_branding` app relabels app titles,
   workspace labels, icons, and post-processes the served HTML of the standalone
   frappe-ui SPAs (CRM, Helpdesk, Insights, Drive, Builder, Gameplan, LMS) to
   apply Nexum Air branding. It also overrides `builder.api.get_apps`. No business
   logic of the AGPL apps is changed.
3. **Static asset overrides** — Nexum Air logos replace `lending`'s logo file and
   Frappe's `framework.png` (these two are GPLv3/MIT respectively).
4. **Service-worker neutralizer** — `my_branding` unregisters the Slides
   root-scope service worker on the desk/SPAs (a stale-asset fix); it does not
   alter Slides' own functionality.

## Reproducing the build

Exact app commits are pinned in `saas/image/apps.pinned.json`; the image is built
by `saas/image/Containerfile` + `build.sh`. Checking out each app at its pinned
commit, applying the modifications above, and building reproduces the running
service.
