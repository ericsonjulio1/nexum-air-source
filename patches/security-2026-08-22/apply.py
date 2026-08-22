#!/usr/bin/env python3
"""NexumAir SECURITY patch set 2026-08-22 (no-version-bump backports onto
frappe v16.25.0 / erpnext v16.26.2). First shipped to prod as v16-prod-151.

Closes (all pure py / server-side jinja, NO asset build):
  erpnext GHSA-qq49-v74j-hjh7  CRITICAL SSTI  Process Statement of Accounts     5f6952b15c
  erpnext GHSA-6w83-8777-v93q  CRITICAL SSTI  RFQ / Contract Template / Email
                                               Campaign / Delivery Trip / Payment
                                               Request / Address template         6b45002abc
  frappe  GHSA-2ph8-x773-8p2x  HIGH   OAuth2 consent CSRF + auto-approve      eb9c1446ca a0b53599cc
  frappe  GHSA-cgwf-xgph-hxgm  LOW    unauthenticated workflow approval       5bf8597781
  frappe  GHSA-2c6h-wv85-fxvj  MEDIUM set_value mass assignment (develop-only) 2a04fae935
  erpnext GHSA-4j82 / m5xh / 48wc (+plant floor) / q8wq  MEDIUM perm checks   7a606ab91c
                                               c7cf9d868b 99f249b1a0 7bc04752fc (+custom guard)
Deferred (need `bench build`): erpnext GHSA-8pr6-r75h-h8xx (XSS in JS bundle),
GHSA-mvr5-2j8r-53p4 (banking React UI).

Each target in manifest.json is either COPIED from files/<app>/<path> (vetted
file = pin + exactly the security hunks, verified by diff 2026-08-22) or left
alone. Decision per file, in order:
  1. sha256(target) == patched_sha256      -> already patched, no-op
  2. every marker present, absent-strings absent -> upstream already fixed, no-op
  3. sha256(target) == pin_sha256          -> copy vetted file, py_compile, re-hash
  4. otherwise                             -> DRIFT: SystemExit(1) (review at bump)

Usage (inside an image build, bench root = dir containing apps/):
    python3 apply.py /home/frappe/frappe-bench            # apply (idempotent)
    python3 apply.py --verify /home/frappe/frappe-bench   # assert all fixed, no writes
"""
import hashlib
import json
import os
import py_compile
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def fixed_by_markers(src, entry):
    return all(m in src for m in entry["markers"]) and not any(a in src for a in entry["absent"])


def main(argv):
    verify_only = False
    args = [a for a in argv[1:]]
    if "--verify" in args:
        verify_only = True
        args.remove("--verify")
    if len(args) != 1:
        print(__doc__)
        return 2
    bench = args[0]
    manifest = json.load(open(os.path.join(HERE, "manifest.json")))
    applied = noop = 0
    failures = []
    for entry in manifest["files"]:
        target = os.path.join(bench, "apps", entry["app"], entry["path"])
        vetted = os.path.join(HERE, "files", entry["app"], entry["path"])
        label = f"{entry['app']}/{entry['path']}"
        if not os.path.exists(target):
            failures.append(f"MISSING target {label}")
            continue
        cur = sha256(target)
        src = open(target, encoding="utf-8").read()
        if cur == entry["patched_sha256"]:
            print(f"ok   already patched   {label}")
            noop += 1
            continue
        if fixed_by_markers(src, entry):
            print(f"ok   upstream-fixed    {label} (markers present; not our bytes - fine)")
            noop += 1
            continue
        if verify_only:
            failures.append(f"NOT FIXED {label} (sha {cur[:12]})")
            continue
        if cur == entry["pin_sha256"]:
            if sha256(vetted) != entry["patched_sha256"]:
                failures.append(f"VETTED FILE CORRUPT {label}")
                continue
            shutil.copyfile(vetted, target)
            if target.endswith(".py"):
                py_compile.compile(target, doraise=True)
            after = open(target, encoding="utf-8").read()
            if sha256(target) != entry["patched_sha256"] or not fixed_by_markers(after, entry):
                failures.append(f"PATCH DID NOT LAND {label}")
                continue
            print(f"APPLIED               {label}  [{entry['advisory']}]")
            applied += 1
            continue
        failures.append(
            f"DRIFT {label}: sha {cur[:12]} is neither pin {entry['pin_sha256'][:12]} nor patched "
            f"{entry['patched_sha256'][:12]} and markers absent -> REVIEW THIS PATCH at the next bump"
        )
    print(f"security-2026-08-22: applied={applied} noop={noop} failures={len(failures)}")
    if failures:
        for f in failures:
            print("ERROR:", f)
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
