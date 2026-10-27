#!/usr/bin/env python3
"""NexumAir SECURITY patch set 2026-08-22 (no-version-bump backports onto
frappe v16.25.0 / erpnext v16.26.2). First shipped to prod as v16-prod-151.
Re-based 2026-08-22 for the frappe v16.31.0 / erpnext v16.32.3 bump: every entry
except frappe/client.py is upstream-fixed there (10 targets byte-identical to our
vetted files, 5 marker-fixed); client.py (GHSA-2c6h, still unpatched on
version-16) gets a new vetted file = v16.31.0 client.py + the develop hunk 2a04fae935.

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
  hrms    GHSA-jfmr-9jv9-mrw4  HIGH   SQLi in get_salary_component search    f176a319dd  (added 2026-10-09)
Deferred (need `bench build`): erpnext GHSA-8pr6-r75h-h8xx (XSS in JS bundle),
GHSA-mvr5-2j8r-53p4 (banking React UI).

Each target in manifest.json is either COPIED from files/<app>/<path> (vetted
file = pin + exactly the security hunks, verified by diff 2026-08-22) or left
alone. `pin_sha256` and `patched_sha256` may each be a string OR a list of
acceptable sha256s (list = several vetted bytes / bases accepted; the single
vetted file in files/ must hash to one of patched_sha256). Decision per file:
  1. sha256(target) in patched_sha256      -> already patched, no-op
  2. every marker present, absent-strings absent -> upstream already fixed, no-op
  3. sha256(target) in pin_sha256          -> copy vetted file, py_compile, re-hash
  4. otherwise                             -> DRIFT: SystemExit(1) (review at bump)
Bump rule: when a target lands in (1) or (2) on the NEW base, keep the entry (it
costs nothing and --verify keeps asserting the fix); when it lands in (4), rebase
the vetted file onto the new upstream bytes, diff-verify the hunk, and add the
new pin / patched shas to the lists (old patched sha may stay so benches built
from the previous image still verify as "already patched").

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


def as_list(v):
    """pin_sha256 / patched_sha256 may be a single sha (str) or a list of acceptable shas."""
    return [v] if isinstance(v, str) else list(v)


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
        pins = as_list(entry["pin_sha256"])
        patched = as_list(entry["patched_sha256"])
        if cur in patched:
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
        if cur in pins:
            if sha256(vetted) not in patched:
                failures.append(f"VETTED FILE CORRUPT {label}")
                continue
            shutil.copyfile(vetted, target)
            if target.endswith(".py"):
                py_compile.compile(target, doraise=True)
            after = open(target, encoding="utf-8").read()
            if sha256(target) not in patched or not fixed_by_markers(after, entry):
                failures.append(f"PATCH DID NOT LAND {label}")
                continue
            print(f"APPLIED               {label}  [{entry['advisory']}]")
            applied += 1
            continue
        failures.append(
            f"DRIFT {label}: sha {cur[:12]} is neither pin {[p[:12] for p in pins]} nor patched "
            f"{[p[:12] for p in patched]} and markers absent -> REVIEW THIS PATCH at the next bump"
        )
    print(f"security-2026-08-22: applied={applied} noop={noop} failures={len(failures)}")
    if failures:
        for f in failures:
            print("ERROR:", f)
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
