#!/usr/bin/env python3
"""Stage fix: Insights data-source connections fail during SSL negotiation.

Symptom (prod, 2026-06-17):
    Connecting an Insights "Site DB" data source returned HTTP 500 with
    CERTIFICATE_VERIFY_FAILED against the self-signed MariaDB certificate.
    An external Frappe-site source with SSL disabled could fail the same way.

Cause:
    SiteDB hardcoded ssl=False together with ssl_verify_cert=True, causing
    PyMySQL to verify the local self-signed certificate. FrappeDB passed the
    user's use_ssl choice to ssl but hardcoded ssl_verify_cert=True.

Fix:
    Remove SiteDB's two SSL keyword arguments so it uses the trusted private
    Docker-network connection, and make FrappeDB certificate verification
    follow use_ssl. These are the same two replacements used by the original
    NexumAir Containerfile heredoc.

Usage (run inside the image build, against the fetched Insights app):
    python3 apply.py \
      apps/insights/insights/insights/doctype/insights_data_source/sources/frappe_db.py

Idempotent (re-running is a no-op), drift-guarded, and verifies the result
compiles after writing.
"""
import sys
import py_compile

SITE_OLD = "            ssl=False,\n            ssl_verify_cert=True,\n"
EXT_OLD = "            ssl=use_ssl,\n            ssl_verify_cert=True,"
EXT_NEW = "            ssl=use_ssl,\n            ssl_verify_cert=use_ssl,"
MARKER = EXT_NEW


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 apply.py <path-to-frappe_db.py>")
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        src = fh.read()

    changed = False
    if SITE_OLD in src:
        src = src.replace(SITE_OLD, "", 1)
        changed = True
    if EXT_OLD in src:
        src = src.replace(EXT_OLD, EXT_NEW, 1)
        changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        py_compile.compile(path, doraise=True)
        print("insights ssl patch applied (SiteDB + FrappeDB), compiles OK:", path)
        return 0

    if MARKER in src:
        print("already patched, nothing to do:", path)
        return 0
    if "ssl_verify_cert" not in src:
        print("no patch needed (upstream changed ssl handling - verify):", path)
        return 0

    print("ERROR: insights ssl code changed upstream - REVIEW THIS PATCH")
    return 1


if __name__ == "__main__":
    sys.exit(main())
