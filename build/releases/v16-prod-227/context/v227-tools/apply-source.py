#!/usr/bin/env python3
"""Apply the frozen, offline-composed source overlays after a complete preflight."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or path.is_symlink():
        raise ValueError("Unsafe overlay path: " + relative)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Overlay escapes root: " + relative)
    return path


def apply(root, verify=False, package=HERE):
    root = Path(root).resolve()
    entries = json.loads((package / "source-overlays.json").read_text())["files"]
    states = set()
    pending = []
    for row in entries:
        path = checked(root, row["path"])
        before, after = row["before_sha256"], row["after_sha256"]
        # A null before hash authorizes creation, never replacement. Verification
        # is the only operation allowed once the new file exists, even if exact.
        if before is None:
            if not verify and path.exists():
                raise ValueError("New overlay file already exists: " + row["path"])
            actual = sha(path) if path.is_file() else None
        else:
            actual = sha(path)
        if actual not in (before, after):
            raise ValueError("Source drift: " + row["path"])
        if before != after:
            artifact = checked(package / "source-overlay", row["path"])
            if sha(artifact) != after:
                raise ValueError("Overlay artifact drift: " + row["path"])
            states.add("patched" if actual == after else "original")
            pending.append((path, artifact, before is None))
        if verify and actual != after:
            raise ValueError("Old code remains: " + row["path"])
    if len(states) > 1:
        raise ValueError("Partial application: prepare a fresh source context")
    if not verify and states == {"original"}:
        for path, artifact, create in pending:
            if create:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    output.write(artifact.read_bytes())
            else:
                path.write_bytes(artifact.read_bytes())
    for row in entries:
        actual = sha(checked(root, row["path"]))
        if actual != row["after_sha256"] or (row["assert_old_gone"] and actual == row["before_sha256"]):
            raise ValueError("Postcondition / old-code guard failed: " + row["path"])
    return {"pass": True, "guarded_files": len(entries), "mode": "verify" if verify else "apply"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(args.root, args.verify)))
