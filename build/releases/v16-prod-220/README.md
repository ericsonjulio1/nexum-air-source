# v16-prod-220

Start Work now requires recorded isolation (lockout/tagout) when a job needs it.
The new Schedule Conformance measure tracks whether work finishes by the end of
its planned day. Next week's plan is frozen automatically every Friday at 17:00
site time. Moving a job's Scheduled Date preserves the original date, requires a
reason and records the change. Maintenance permissions are set up as soon as the
app is installed.

The image `ericsonjulio/erpnext:v16-prod-220` has registry digest
`sha256:a601fe57c981461d2c4c4d29d6a2bc2bd81b5c22d7d49d5a2ff6cb005aba5a41`.
It inherits v219 at the immutable digest recorded in `manifest.json` and replaces
only `apps/eam`, from `05c867e650eadb181cf379ac88a75c555a1d2c0f` to
`f806e3d7ccaea10f31b0d4bc8a91aa8d5cb7df5d`. The release comparison proved all
416,034 entries outside `apps/eam` byte-identical to v219. `my_branding` is retained
at `16fae11ed4ba5a6e90f10b9c7ba533688ae35012`.

The framework release remains v16-prod-216: Frappe 16.52.0, ERPNext 16.51.1 and
HRMS 16.51.0. Upstream applications, dependencies, security fixes and compiled
standalone apps are unchanged. No upstream dependency is upgraded and no
historical patcher runs.

EAM is MIT-licensed and maintained in a private repository. It is not part of the
AGPL Corresponding Source offer. The AGPL-covered sources and every published
modification are those of [v219](../v16-prod-219/README.md), unchanged. Follow the
inherited release manifests for their sources and build instructions.

A public reader cannot rebuild the private EAM layer from this mirror: the
required EAM source is not published here. `prepare.py` is included to follow the
existing convention of preparing the exact Git archive for the app tree being
replaced. It prepares only EAM; the unchanged `my_branding` tree is inherited
from the base image. With access to the private repository and the pinned commit,
run `python3 prepare.py --eam /path/to/eam`, then build this directory for
`linux/amd64`. The helper validates the immutable base, source commit, image label
and app layout before extracting the archive. Generated archives are ignored by
Git. The Dockerfile replaces the complete EAM tree, including removals, without
changing other application sources or dependencies.
