#!/usr/bin/env python3
"""Guard the retained-app overlay copy before replacing any bytes.

The v228 base is the live v227 image, which already carries the v227 overlays for Insights, Telephony and
Print Designer, so every retained overlay row must be at its reviewed after state (fail closed otherwise)."""
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
        if hashlib.sha256((BENCH / row["path"]).read_bytes()).hexdigest() != row["after_sha256"]:
            raise RuntimeError("RC3 retained source differs from reviewed overlay boundary: " + row["path"])
    print("PASS: retained Insights/Telephony/Print Designer bytes equal the v227-deployed overlay")
