v16-prod-208 layers committed branding and EAM sources over immutable v16-prod-207.
Upstream versions and dependencies are unchanged.

Maintenance now occupies the third card slot beside Asset Reports and Setup.
EAM mounts on the ERPNext navigation rail using the standard Dock model, so its
workspace, work orders, workbench and reports keep the Nexum Air module icons.
The Maintenance dock entry ships hidden because its entry point is under Assets.
A narrow workspace adapter preserves the card position after Framework inserts
its Custom Documents / Custom Reports placeholders.

Prepare source archives at the manifest commits, then build:
  python3.14 prepare.py --branding /path/to/my_branding --eam /path/to/eam
  docker buildx build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-208 .

The public mirror contains my_branding. EAM remains separately maintained at its
recorded repository and commit. No tenant data or credentials are build inputs.
Run bench migrate to import the standard EAM Dock and reconcile Assets content.
The deployment procedure refreshes asset caches and runs its financial gates.
