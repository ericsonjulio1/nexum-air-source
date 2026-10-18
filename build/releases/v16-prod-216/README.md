# Nexum Air v16-prod-216

Upgrades Frappe to 16.52.0, ERPNext to 16.51.1, HRMS to 16.51.0,
CRM to 1.88.0, Helpdesk to 1.31.0 and Insights to 3.15.0. The other
seven application runtimes and the v215 Nexum branding are retained. The EAM
commit changes only two tests to follow the new framework's notification body
field and to restrict a synthetic database stub to its intended work-order query.
Exact upstream commits, archive checksums and the immutable base image are in
`manifest.json`.

Recreate the build context using Python 3.12+ and git:

```sh
python3 prepare-context.py /tmp/nexum216-build --eam-repository /path/to/authorized/eam
docker build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-216 /tmp/nexum216-build
```

`upstream.patch` preserves Nexum's security and interface corrections. The
CRM chart hooks follow the new native chart components, and Helpdesk retains
its new rounding token. The absent-app sidebar migration guard is now upstream.
`patch-reconciliation.json` records how the inherited source changes were handled.
Two upstream lockfiles were resolved with the base image's pinned Yarn version,
without changing their package manifests; both are installed with frozen locks.

`patch-dependencies.py` preserves the tested chart bridge and lifecycle fixes;
its input hashes fail closed on unexpected dependency versions. `security/`
verifies the existing 17 security guards during the build.

`patch-migration-cache.py` refreshes Frappe's in-process module map after the
migration clears Redis. Without this correction, a warm cache from the previous
release omits CRM's new Domain Enrichment module during the first schema sync.
The integration regression fails on the uncorrected candidate and passes on
the corrected candidate; the full upgrade is then rehearsed from restored backups.

This directory contains build source only. Operational backups, credentials,
customer data and private release evidence are excluded. EAM remains supplied
through the pinned base image and its private source repository.
