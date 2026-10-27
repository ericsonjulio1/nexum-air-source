# v16-prod-225 candidate

Not deployed. Prepared from v224 with Frappe 16.53.0, ERPNext 16.52.1,
HRMS 16.52.0, CRM 1.89.2, Insights 3.15.1, Drive 0.4.3 and the pinned
Telephony signature fix. Helpdesk 1.31.0 and the other app source pins remain
unchanged. Bench maintenance tooling advances to 5.31.1. The manifest records
source identities and archive checksums. No app is added or renamed.

The Dockerfile preserves the reviewed security, chart, sidebar, dependency and
module-cache patches. MCP's new-site default and migration are both off; it can
be enabled separately. The retained Drive menu patch prevents duplicate Desk
entries. Frontend locks are frozen; Drive's pnpm build runs explicitly because
Frappe's dispatcher assumes Yarn.

Run `python3 prepare-context.py NEW_DIRECTORY --branding-repository PATH` with
Python 3.12+ and Git, then build that directory for `linux/amd64`. The helper
verifies downloaded archives and the exact branding commit. Reproducing the
complete image needs authorized access to the canonical private repository,
as in v224; private host operations are not published here. The pinned base
retains EAM and the other unchanged applications.

`python-security.lock` pins and hashes all 242 application PyPI distributions.
`maintenance-python-security.lock` does the same for all 20 distributions in
Bench's separate interpreter. Installs force reinstallation with the cache
disabled, so a preinstalled matching version cannot bypass archive verification.
A separate build stage compiles native source packages with a digest-pinned Rust
1.92.0 toolchain and Debian build tools. It seals all 242 wheels in a second hash
lock, then the runtime installs them offline from a read-only build mount. The
wheel manifest and lock remain in the image for release verification; compiler
tools and the wheelhouse are not copied into the runtime. The build verifies each complete installed
inventory, the 13 editable app origins and the two immutable Git distributions,
and runs dependency compatibility checks. Any extra, missing or mismatched
package fails the build. `python-security.patch` explicitly records the Pillow,
pypdf, GitPython and Bleach constraint changes, public bulk-PDF option validation
and its upstream regression expectation. Unused LiteLLM is removed from the
final environment.

The trust policy follows certifi 2026.10.23. `remove-compromised-roots.py` disables
three hash-pinned emSign roots in Debian's trust store, and Node uses that
OpenSSL store. `align-pip-ca.py` applies a recorded data-only patch to both pip
26.2.2 CA bundles. Pip already removes the advisory's G3 root; the alignment
also incorporates the C1/C3 removals in certifi's October 23 update. Native
checks cover both Python interpreters, OpenSSL and Node's acceptance/rejection
of a disposable test certificate.

The earlier dependency-install layer retains the framework build sequence and
can resolve dependencies. The final locks and inventory checks constrain the
shipped runtime; they do not make every intermediate layer or the complete
image byte-for-byte reproducible. Debian builder packages and temporary PEP517
build dependencies are fetched online; their full dependency graph is not
hermetically locked. The wheel record captures compiler and Debian library
versions, and native database/CRDT tests exercise compatibility in the final image. Source reproduction and full installed-file
inventories are verified separately. Native release tests, fresh advisory
scans, recovery rehearsals, independent review and production preflight remain
required before deployment.
