#!/usr/bin/env python3
"""Prepare the exact v16-prod-227 build context and verify it file by file.

Usage: python3 prepare.py NEW_DIRECTORY --branding PATH [--eam PATH] [--archives DIR]

Downloads the six pinned upstream application archives from GitHub (or reads
them from --archives), extracts the exact branding commit from a clone of the
public Nexum-Air repository, applies the published source overlays and
compares every resulting file and mode with context-files.json. EAM is private:
without --eam the context is verified but not buildable.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "context" / "v227-tools"
UPSTREAM = ("frappe", "erpnext", "hrms", "crm", "helpdesk", "drive")
CUSTOM = ("eam", "my_branding")


def require(ok, message):
    if not ok:
        raise SystemExit("REFUSED: " + message)


def inventory(root):
    """Git blob id, SHA-256 and Git mode of every file and symlink (links are not followed)."""
    result = {}
    for directory, folders, names in os.walk(root, followlinks=False):
        for name in folders + names:
            path = Path(directory, name)
            if path.is_symlink():
                raw, mode = os.readlink(path).encode(), "120000"
            elif path.is_file():
                raw = path.read_bytes()
                mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            else:
                continue
            result[path.relative_to(root).as_posix()] = {
                "mode": mode, "blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def permissions(root, normalize=False):
    """Directories 0755, files 0755 when any execute bit is set, otherwise 0644."""
    records = {}
    paths = [root]
    for directory, folders, names in os.walk(root, followlinks=False):
        paths += [Path(directory, name) for name in folders + names]
    for path in paths:
        name = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            records[name] = {"kind": "symlink"}
            continue
        require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), "unexpected member type: " + name)
        directory = stat.S_ISDIR(mode)
        if normalize:
            path.chmod(0o755 if directory or mode & 0o111 else 0o644)
        records[name] = {"kind": "directory" if directory else "file", "mode": stat.S_IMODE(path.lstat().st_mode)}
    return records


def extract(data, target, strip):
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        members = archive.getmembers()
        for member in members:
            if strip:
                parts = Path(member.name).parts
                member.name = str(Path(*parts[1:])) if len(parts) > 1 else "."
            require(not member.islnk() and (member.isfile() or member.isdir() or member.issym()),
                    "unexpected archive member: " + member.name)
        archive.extractall(target, members=members, filter="data")


def upstream_archive(app, row, archives):
    if archives:
        data = (archives / (app + ".tar.gz")).read_bytes()
    else:
        repository = row["repository"].removeprefix("https://github.com/")
        url = "https://codeload.github.com/" + repository + "/tar.gz/" + row["commit"]
        with urllib.request.urlopen(url, timeout=600) as response:
            data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != row["archive_sha256"]:
        # GitHub may recompress an archive; the extracted files are verified below either way.
        print("NOTE: " + app + " archive bytes differ from the build's; verifying its files instead", file=sys.stderr)
    return data


def custom_archive(app, repository, row):
    def git(*args):
        return subprocess.check_output(["git", "-c", "core.attributesFile=/dev/null", "-C", str(repository), *args],
                                       env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_NOSYSTEM="1"))
    require(git("rev-parse", row["commit"] + "^{commit}").decode().strip() == row["commit"], app + " commit missing")
    require(git("rev-parse", row["commit"] + "^{tree}").decode().strip() == row["tree"], app + " tree differs")
    return git("archive", "--format=tar", row["commit"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path)
    parser.add_argument("--branding", type=Path, required=True, help="clone of github.com/ericsonjulio1/Nexum-Air")
    parser.add_argument("--eam", type=Path, help="clone of the private EAM repository")
    parser.add_argument("--archives", type=Path, help="directory holding APP.tar.gz upstream archives")
    args = parser.parse_args()
    require(sys.version_info >= (3, 12), "Python 3.12+ is required")
    manifest = json.loads((HERE / "manifest.json").read_text())
    expected = json.loads((HERE / "context-files.json").read_text())
    pins = json.loads((TOOLS / "pinned-inputs.json").read_text())
    apps = {**manifest["upstream_apps"], **manifest["custom_apps"]}
    for app in UPSTREAM + CUSTOM:
        require(apps[app]["commit"] == pins["apps"][app]["sha"], app + " pin differs from the build's")
    require(manifest["base_image"] == pins["base"], "base image differs from the build's")
    require(hashlib.sha256((HERE / "context/Dockerfile").read_bytes()).hexdigest() == manifest["dockerfile_sha256"],
            "Dockerfile differs")
    context = args.output.resolve()
    require(not context.exists(), "choose a new output directory")
    os.umask(0o022)
    context.mkdir(parents=True)

    for app in UPSTREAM:
        extract(upstream_archive(app, apps[app], args.archives), context / "apps" / app, strip=True)
    for app, repository in (("eam", args.eam), ("my_branding", args.branding)):
        if repository:
            extract(custom_archive(app, repository, apps[app]), context / "apps" / app, strip=False)
    shutil.copytree(HERE / "retained-pristine/apps", context / "apps", dirs_exist_ok=True)
    spec = importlib.util.spec_from_file_location("apply_source", TOOLS / "apply-source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(json.dumps(module.apply(context, package=TOOLS)))
    shutil.copyfile(HERE / "framework.png", context / "apps/frappe/frappe/public/images/framework.png")
    complete = args.eam is not None
    sources = {app: inventory(context / "apps" / app) for app in UPSTREAM + CUSTOM if (context / "apps" / app).exists()}
    for app in CUSTOM:
        (context / app).symlink_to("apps/" + app, target_is_directory=True)
    shutil.copytree(TOOLS, context / "v227-tools")
    if complete:
        (context / "v227-tools/source-files.json").write_text(json.dumps(sources, sort_keys=True) + "\n")
    shutil.copytree(HERE / "context/locks", context / "locks")
    shutil.copytree(HERE / "context/dependencies", context / "dependencies")
    for name in ("Dockerfile", ".dockerignore"):
        shutil.copyfile(HERE / "context" / name, context / name)
    modes = permissions(context, normalize=True)

    private = lambda path: path == "apps/eam" or path.startswith("apps/eam/")
    files = {path: row for path, row in inventory(context).items() if not private(path)}
    wanted = dict(expected["files"])
    if not complete:
        wanted.pop("v227-tools/source-files.json")
    missing, extra = sorted(set(wanted) - set(files)), sorted(set(files) - set(wanted))
    changed = sorted(path for path in set(files) & set(wanted) if files[path] != wanted[path])
    mode_drift = sorted(path for path, row in expected["permissions"].items()
                        if not private(path) and modes.get(path) != row
                        and not (path == "v227-tools/source-files.json" and not complete))
    require(not (missing or extra or changed or mode_drift),
            json.dumps({"missing": missing[:20], "extra": extra[:20], "changed": changed[:20], "modes": mode_drift[:20]}))
    print(json.dumps({"pass": True, "verified_files": len(files), "buildable": complete,
                      "context": str(context)}))
    if not complete:
        print("EAM is private: supply --eam to produce a buildable context", file=sys.stderr)


if __name__ == "__main__":
    main()
