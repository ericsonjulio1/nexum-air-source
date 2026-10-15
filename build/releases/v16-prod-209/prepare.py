"""Assemble the pinned custom sources without reading runtime configuration."""
import argparse
import io
import json
import subprocess
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--branding', type=Path, required=True)
parser.add_argument('--eam', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
manifest = json.loads((root / 'manifest.json').read_text())

for name, source in (('my_branding', args.branding), ('eam', args.eam)):
    commit = manifest['custom_apps'][name]['commit']
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', commit])
    target = root / name
    target.mkdir()  # fail rather than mixing a new archive with existing files
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(target, filter='data')
    assert (target / name / 'hooks.py').exists(), name
    print(name, commit, 'ready')
