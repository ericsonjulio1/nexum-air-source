v16-prod-207 layers the committed branding and EAM sources over the immutable
v16-prod-206 image. Upstream app versions and dependencies are unchanged.

Changes: restore Apps-mode Nexum Air logos; render duotone module icons on the
installed Electron 25 Mac client; place Maintenance under Assets; return Helpdesk
Nexum Air and Desk shortcuts to the Business Application Suite launcher.

Prepare source archives at the manifest commits, then build:
  python3.14 prepare.py --branding /path/to/my_branding --eam /path/to/eam
  docker buildx build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-207 .

The source mirror contains the public my_branding package. EAM remains separately
maintained at its recorded repository and commit. The build needs no tenant data
or credentials. Run bench migrate after deployment so Assets links are applied.
The existing deployment procedure also refreshes asset caches and runs its gates.
