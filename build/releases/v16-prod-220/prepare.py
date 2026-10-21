"""Prepare the exact reviewed eam Git archive; private repository access is required."""
import argparse
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path


def require(value, message):
    if not value:
        raise RuntimeError(message)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--eam', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
manifest = json.loads((root / 'manifest.json').read_text())
dockerfile = (root / 'Dockerfile').read_text()
require(re.fullmatch(r'ericsonjulio/erpnext@sha256:[0-9a-f]{64}', manifest['base_image']), 'Immutable base required')
require('FROM ' + manifest['base_image'] + '\n' in dockerfile, 'Base image differs')
commit = manifest['custom_apps']['eam']['commit']
require(re.fullmatch(r'[0-9a-f]{40}', commit), 'eam: final commit required')
resolved = subprocess.check_output(['git', '-C', str(args.eam), 'rev-parse', commit + '^{commit}'], text=True).strip()
require(resolved == commit, 'eam: source differs')
require(f'com.nexumair.eam.commit="{commit}"' in dockerfile, 'eam: label differs')
target = root / 'eam'
require(not target.exists(), 'eam: prepared archive already exists')
archive = subprocess.check_output(['git', '-C', str(args.eam), 'archive', commit])
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    require('eam/hooks.py' in bundle.getnames(), 'eam: invalid source layout')
    # validated before anything is written
    target.mkdir()
    bundle.extractall(target, filter='data')
print('eam', commit, 'ready')
