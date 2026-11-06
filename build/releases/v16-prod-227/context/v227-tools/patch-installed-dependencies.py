#!/usr/bin/env python3
"""Reapply the retained chart patch with all-file preflight and idempotent guards."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ANCHOR = "  ECharts.prototype.setOption = function (option, notMerge, lazyUpdate) {"
BLOCK = ANCHOR + """
    // Nexum Air: shared presentation before ECharts consumes the original data.
    if (typeof window !== 'undefined' && window.NexumCharts) {
      option = window.NexumCharts.echartsOptions(option, this);
    }"""


def run(root, verify=False):
    root = Path(root)
    paths = {}
    for frontend, version in (("crm/frontend", "6.1.0"), ("helpdesk/desk", "6.1.0"), ("insights/frontend", "5.6.0")):
        base = Path("apps") / frontend / "node_modules/echarts"
        if json.loads((root / base / "package.json").read_text())["version"] != version:
            raise ValueError("ECharts locked version drift: " + frontend)
        path = base / "lib/core/echarts.js"
        text = (root / path).read_text()
        if text.count(ANCHOR) != 1 or ("window.NexumCharts" in text and text.count(BLOCK) != 1):
            raise ValueError("ECharts wrapper drift: " + frontend)
        paths[path] = text.replace(BLOCK, ANCHOR)
    base = Path("apps/frappe/node_modules/frappe-charts")
    path = base / "src/js/objects/ChartComponents.js"
    paths[path] = (root / path).read_text().replace("\tlet config = { ...componentConfigs[keys[0]] };", "\tlet config = componentConfigs[keys[0]];")
    for name, variable in (("esm", "Ct"), ("umd", "Ct"), ("cjs", "Tt")):
        path = base / "dist" / f"frappe-charts.{name}.js"
        old = f"a={variable}[i[0]];return Object.assign(a,{{constants:e,getData:n}})"
        new = f"a=Object.assign({{}},{variable}[i[0]]);return Object.assign(a,{{constants:e,getData:n}})"
        paths[path] = (root / path).read_text().replace(new, old)
    # The original patcher still verifies all four exact frappe-charts input hashes.
    # It runs on seven normalized copies, so one bad target cannot partially alter
    # the image. The inherited Insights wrapper is recognized rather than doubled.
    with tempfile.TemporaryDirectory(prefix="v227-chart-guards-") as folder:
        temp = Path(folder)
        for path, content in paths.items():
            target = temp / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        subprocess.run([sys.executable, "-B", str(HERE / "patchers/patch-dependencies.py"), str(temp)], check=True)
        for path, old in paths.items():
            patched = (temp / path).read_bytes()
            if patched == old.encode():
                raise ValueError("Old dependency code remains: " + str(path))
            if verify and (root / path).read_bytes() != patched:
                raise ValueError("Dependency patch absent/drifted: " + str(path))
        if not verify:
            for path in paths:
                (root / path).write_bytes((temp / path).read_bytes())
        result = {str(p): hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    return {"pass": True, "files": result}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    print(json.dumps(run(args.root, args.verify), sort_keys=True))
