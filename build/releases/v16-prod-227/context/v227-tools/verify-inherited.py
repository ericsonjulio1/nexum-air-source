#!/usr/bin/env python3
"""Read-only RC3 dependency/trust guards; no advisory package remediation."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import ssl
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BENCH = Path("/home/frappe/frappe-bench")


def main():
    pins = json.loads((HERE / "pinned-inputs.json").read_text())
    replacement = {name for name, row in pins["apps"].items() if row["action"] == "replace"}
    inventory = {d.metadata["Name"].lower().replace("_", "-"): d.version for d in metadata.distributions()
                 if d.metadata["Name"].lower().replace("-", "_") not in replacement}
    record = HERE / "nonapp-before.json"
    if sys.argv[1] == "before":
        if record.exists():
            raise RuntimeError("Preserve prior dependency inventory")
        record.write_text(json.dumps(inventory, sort_keys=True) + "\n")
    elif json.loads(record.read_text()) != inventory:
        raise RuntimeError("Non-app Python package changed; v227 excludes advisory remediation")
    for interpreter, lock, maintenance in ((str(BENCH / "env/bin/python"), "/tmp/upgrade-226/python-security.lock", False),
                                           ("/usr/local/bin/python", "/tmp/upgrade-225/maintenance-python-security.lock", True)):
        subprocess.run([interpreter, "-I", "-B", "/tmp/upgrade-225/verify-python-lock.py", lock,
                        *(["--maintenance"] if maintenance else [])], check=True)
        code = "import certifi,pip._vendor.certifi,pathlib,hashlib; print(hashlib.sha256(pathlib.Path(certifi.where()).read_bytes()).hexdigest()); print(hashlib.sha256(pathlib.Path(pip._vendor.certifi.where()).read_bytes()).hexdigest())"
        hashes = subprocess.check_output([interpreter, "-I", "-B", "-c", code], text=True).splitlines()
        if hashes != ["2ef52ad56b4803e264045c915e55c236cbfa045b84b81efefc218a19eb44bd2b"] * 2:
            raise RuntimeError("Inherited pip/certifi CA alignment changed")
    removed = {"bc4d809b15189d78db3e1d8cf4f9726a795da1643ca5f1358e1ddb0edc0d7eb3",
               "125609aa301da0a249b97a8239cb6a34216f44dcac9f3954b14292f2e8c8608f",
               "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"}
    trusted = {hashlib.sha256(c).hexdigest() for c in ssl.create_default_context().get_ca_certs(binary_form=True)}
    if len(trusted) < 100 or trusted & removed:
        raise RuntimeError("Inherited system CA distrust changed")
    print(json.dumps({"pass": True, "phase": sys.argv[1], "non_replaced_distributions": len(inventory)}))


if __name__ == "__main__":
    main()
