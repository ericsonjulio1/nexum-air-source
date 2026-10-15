Nexum Air v16-prod-209 — suite consistency

Derived from the immutable v208 image. Upstream app versions remain pinned to
v206. Custom app revisions are recorded in manifest.json. EAM remains private;
obtain its pinned source from the licensed repository when rebuilding.

Run prepare.py --branding /path/to/Nexum-Air --eam /path/to/eam, then:
  docker buildx build --platform linux/amd64 --load -t ericsonjulio/erpnext:v16-prod-209 .

apply_frontend.py modifies source (not minified assets) before rebuilding CRM,
Helpdesk and Insights with their existing locked dependencies. It removes the
hard-coded duplicate Desk entry, retains a branded fallback, gives Insights a
native accessible Apps submenu, adds report-card styling hooks, and connects
all three apps' ECharts setOption entry points to the shared report presentation.
Explicit data-point colours, visual maps and saved series colours are retained.
The corresponding ECharts dependency changes are fully described in that script;
its existing Apache-2.0 license and source remain in the image dependency tree.

The my_branding package supplies the shared chart style and the per-user Desk
theme bridge. EAM moves the full overview to Accounts, keeps a permission-checked
Maintenance Costs doorway, and avoids colliding final chart date labels. These
changes alter presentation and navigation; accounting calculations are unchanged.

Run the published suite_consistency_smoke.py, apps_navigation_smoke.py,
maintenance_navigation_smoke.py and ux_contract_smoke.py against a migrated site.
The UX smoke ends its own session and must run last when sharing a session.
