# v16-prod-222

Maintenance release: payment entitlement protection, bounded webhook input,
retry scheduling for the durable billing inbox, reliable welcome-message outbox,
SPA branding corrections, and calendar bounds that preserve legacy EAM history.
The billing schema adds a nullable attempt timestamp and a queue-selection index.

The image replaces only the committed `my_branding` and `eam` trees on the pinned
v221 base. All 415,538 other bench paths remain identical; Frappe 16.52.0,
ERPNext 16.51.1 and upstream dependencies are unchanged.

Runtime branding: `1f76ae4154ebb35266b5e7795544f8a156b986b7`.
Private EAM: `9de5ada9a7e57e5fb3db91f02bb93c7c67a81881`.
The public application and package metadata match the image. This mirror does not
include private EAM, so public readers cannot reproduce that layer without access.
With both canonical repositories, run `python3 prepare.py --branding PATH --eam PATH`
and build this directory for `linux/amd64`. The helper extracts the pinned commits.

Host workers are a separate verified release artifact. Their installation requires
schema readiness. Schema releases require database-and-files backup and recovery;
changing the image alone cannot undo a migration. No bank-provider integration is
included in this release.
