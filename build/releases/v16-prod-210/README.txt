Nexum Air v16-prod-210 — navigation follow-up

Build from the immutable v209 image using the custom revisions in manifest.json:
  python prepare.py --branding /path/to/Nexum-Air --eam /path/to/eam
  docker buildx build --platform linux/amd64 --load -t ericsonjulio/erpnext:v16-prod-210 .

The source adapter removes Drive's hard-coded Desk entry before rendering. Teams
gets a top-left Apps submenu with permission-filtered sibling apps, pointer and
keyboard navigation, focus restoration and lifecycle cleanup. TeamsUserDropdown.vue
is the full corresponding source for the modified Gameplan component; the upstream
Gameplan license applies. Both frontends rebuild with the dependencies already
present in the pinned image, without resolving or updating packages.

Branding removes Teams' floating Apps fallback. EAM removes the Financial Overview,
Maintenance Costs and Financial Overview Sources links from Maintenance, preserving
tenant links and operational cost reports. All financial views and old bookmarked
URLs use Accounts. Calculations and stored financial transactions are unchanged.

Run navigation_followup_smoke.py for first-frame Drive and Teams keyboard coverage,
plus suite_consistency_smoke.py, maintenance_navigation_smoke.py and
apps_navigation_smoke.py. Run ux_contract_smoke.py last: it ends its own session.
