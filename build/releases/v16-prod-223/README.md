# v16-prod-223

Maintenance release: immutable tenant identity prevents delayed payment or plan jobs from changing a replacement workspace; checkout activation and deletion share a locked lifecycle; competing checkout plans retain cleanup work; financial owner alerts retry independently of payments. Welcome delivery and CRM reconciliation recover separately.

The image replaces the committed custom application trees on the pinned v222 base. Branding is `e734e49d054b611bd66e1178d75b58a8c8a5a415`; private EAM remains `9de5ada9a7e57e5fb3db91f02bb93c7c67a81881`. All 415,538 other bench paths remain identical; Frappe 16.52.0, ERPNext 16.51.1 and upstream dependencies are unchanged.

The public runtime application and package metadata match the image. Private EAM is omitted, so reproducing its layer requires repository access. With both canonical repositories, run `python3 prepare.py --branding PATH --eam PATH` and build this directory for `linux/amd64`. The helper extracts the exact pinned commits.

Host workers are a separate verified artifact. This release adds billing ownership, cleanup and alert fields/indexes plus per-site identity configuration. Schema recovery restores the verified database, full site configuration, files and host runtime before reopening. Changing only the image cannot reverse a migration. Bank connections and live billing-provider activation are separate work and are not enabled here.
