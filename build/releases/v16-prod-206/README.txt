The v16-prod-206 recipe uses the immutable v16-prod-205 runtime image as its base.
manifest.json identifies every replaced upstream tree and the two custom-app
commits. Existing Payments, Telephony, Drive and Gameplan are retained from that
base. Frappe Suite is not included: it is a separate product migration.

Use Python 3.14 and pass the release's my_branding and EAM source checkouts:
  python3.14 prepare.py --branding /path/to/my_branding --eam /path/to/eam
  docker buildx build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-206 .

The public my_branding package in this source repository is the corresponding
branding source. EAM is maintained separately at the repository/commit recorded
in manifest.json. No tenant data or credentials are needed for the image build.

upstream.patch preserves the standard-field security guard and domain cache fix,
and reconciles Framework UI's inconsistent yarn lockfile. Helpdesk's resolved
lockfile is in locks/helpdesk. compatibility/sidebar_code_only.py keeps EAM's
Maintenance sidebar route valid after native Maintenance became code-only.
security/apply.py verifies the 17 existing security checks.

Additional compatibility patches preserve authorized Web Form attachment submission,
use structured aggregate fields in Gameplan, skip impossible absent-app dock entries,
and serialize/atomically replace the asset link when services start together.
Print Designer reuses the maintained system Chromium through its expected bench path.
