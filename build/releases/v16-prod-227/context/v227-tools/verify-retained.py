#!/usr/bin/env python3
"""Guard the small retained-app overlay copy before replacing any bytes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = Path("/home/frappe/frappe-bench")

if __name__ == "__main__":
    rows = json.loads((HERE / "source-overlays.json").read_text())["files"]
    for row in rows:
        app = Path(row["path"]).parts[1]
        if app not in ("insights", "telephony", "print_designer"):
            continue
        expected = row["before_sha256"] if app == "print_designer" else row["after_sha256"]
        if hashlib.sha256((BENCH / row["path"]).read_bytes()).hexdigest() != expected:
            raise RuntimeError("RC3 retained source differs from reviewed overlay boundary: " + row["path"])
    print("PASS: retained Insights/Telephony bytes and original Print Designer hook")
