# v16-prod-224

Data-protection release: migration branding now changes only Workspace content that still matches an installed public standard definition, so tenant-edited workspaces, shortcuts and links are preserved; shortcut references are updated together or not at all. Tenant deletion is held by the host operations released alongside it.

The image replaces the committed custom application trees on the pinned v223 base. Branding is `206eb4b4835de66507459c9f8296e898bc22bc86`; private EAM remains `9de5ada9a7e57e5fb3db91f02bb93c7c67a81881`. All 415,538 other bench paths remain identical; Frappe 16.52.0, ERPNext 16.51.1 and upstream dependencies are unchanged.

The public runtime application and package metadata match the image. Private EAM is omitted, so reproducing its layer requires repository access. With both canonical repositories, run `python3 prepare.py --branding PATH --eam PATH` and build this directory for `linux/amd64`. The helper extracts the exact pinned commits.

Host workers are a separate verified artifact: deletion preview has no side effects, every actual tenant deletion is refused before side effects, and deletion backups are verified by encrypted offsite read-back. No columns, indexes, providers, billing activation, framework or EAM changes are included. Schema recovery still restores the verified database, full site configuration, files and host runtime before reopening.
