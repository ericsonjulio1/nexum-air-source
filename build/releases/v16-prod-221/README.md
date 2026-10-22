# v16-prod-221

This release consolidates plan policy, upload coordination and browser compatibility
into dedicated modules. Concurrent uploads read current storage usage while preserving
the request's normal business snapshot and uncommitted work. EAM financial views now
share their source-query helpers; the financial calculations are unchanged.

`manifest.json` pins the v220 base and both exact custom-app Git trees. The Dockerfile
replaces only `apps/my_branding` and `apps/eam`, parses their Python files without
creating bytecode, and records their commits. All 415,538 bench paths outside those
two app trees are byte-identical to the base. No upstream application or dependency
changes; the framework remains v216 (Frappe16.52.0, ERPNext16.51.1).

The published `my_branding/`, `pyproject.toml` and `license.txt` match the runtime
application at `d3aab28c735ad0d42fcc0b01104af3b8ec20a1aa`. The complete canonical Git
archive also includes host tooling and repository documentation. EAM remains private;
its required commit is `50725b23392fd42aab0947eafe2d765e7331d0f0`. A public reader
cannot rebuild the private EAM layer from this mirror. With access to both canonical
repositories, run `python3 prepare.py --branding /path/to/Nexum-Air --eam /path/to/eam`,
then build this directory for `linux/amd64`. The helper extracts only the committed
archives, validates the labels and pinned base, and refuses existing destinations.

Host operations have a separate reviewed bundle and deployment lifecycle; the image
recipe does not install host scripts or contain live tenant credentials/state.
