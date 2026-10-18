"""Materialize the pinned v216 build context (Python 3.12+ and git required)."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='New, empty build-context directory')
parser.add_argument('--eam-repository', type=Path, required=True, help='Authorized local EAM git repository')
args = parser.parse_args()
release = Path(__file__).resolve().parent
target = args.destination.resolve()
if target.exists():
    raise SystemExit('Use a new directory; existing contexts are never overwritten')
target.mkdir(parents=True)
manifest = json.loads((release / 'manifest.json').read_text())
(target / 'apps').mkdir()
with tempfile.TemporaryDirectory(prefix='nexum216-source-') as temporary:
    staging = Path(temporary)
    for app, info in manifest['apps'].items():
        archive = staging / (app + '.tar.gz')
        url = f"https://codeload.github.com/frappe/{app}/tar.gz/{info['commit']}"
        urllib.request.urlretrieve(url, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != info['archive_sha256']:
            raise RuntimeError('Pinned source checksum mismatch: ' + app)
        with tarfile.open(archive) as bundle:
            top = bundle.getmembers()[0].name.split('/')[0]
            bundle.extractall(staging, filter='data')
        shutil.move(staging / top, target / 'apps' / app)
for name in ('Dockerfile', '.dockerignore', 'patch-dependencies.py', 'patch-migration-cache.py', 'upstream.patch'):
    shutil.copy2(release / name, target / name)
shutil.copytree(release / 'security', target / 'security')
(target / 'eam-tests').mkdir()
for name in ('test_batch205_workorders.py', 'test_notifications.py'):
    source = subprocess.check_output(['git', '-C', str(args.eam_repository.resolve()), 'show',
        manifest['custom_apps']['eam']['commit'] + ':eam/tests/' + name])
    (target / 'eam-tests' / name).write_bytes(source)
subprocess.run(['git', 'apply', '--check', str(target / 'upstream.patch')], cwd=target, check=True)
subprocess.run(['git', 'apply', str(target / 'upstream.patch')], cwd=target, check=True)
shutil.copy2(release / 'framework.png', target / 'apps/frappe/frappe/public/images/framework.png')
for path in ('frappe/ui', 'helpdesk/desk'):
    expected = release / 'locks' / path
    actual = target / 'apps' / path
    if (expected / 'package.json').read_bytes() != (actual / 'package.json').read_bytes():
        raise RuntimeError('Lockfile dependency manifest mismatch: ' + path)
    shutil.copy2(expected / 'yarn.lock', actual / 'yarn.lock')
print('Pinned build context ready:', target)
