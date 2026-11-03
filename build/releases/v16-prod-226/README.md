# v16-prod-226

Deployed and verified on 3 November 2026 (Pacific/Port_Moresby). Maintenance release built on the exact v225 image: the committed custom application trees are replaced and their frontend assets rebuilt; Frappe 16.53.0, ERPNext 16.52.1, every other bundled upstream application, the hashed Python locks and the retained v225 patches are inherited unchanged.

Branding is `d45d82c0cc3092dcaa5ced95b4f7eeae4a470d63` (host-operations reliability and Settings workspace fixes; the Settings workspace now ships as a seed instead of a fixture). Private EAM is `da5720a43ef8e8d7971ac4ba6e3c417760c345bc` (migration isolation, lifecycle, stock and report fixes).

The public runtime application and package metadata match the image. Private EAM is omitted, so reproducing its layer requires repository access. With both canonical repositories, run `python3 prepare.py --branding PATH --eam PATH` and build this directory for `linux/amd64` on the pinned base. The helper extracts the exact pinned commits. The Dockerfile re-verifies both inherited Python security locks and `uv pip check` in the final image.
