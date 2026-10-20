"""Prepare the exact reviewed my_branding Git archive without reading runtime configuration."""
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


parser = argparse.ArgumentParser()
parser.add_argument('--branding', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
manifest = json.loads((root / 'manifest.json').read_text())
dockerfile = (root / 'Dockerfile').read_text()
require(re.fullmatch(r'ericsonjulio/erpnext@sha256:[0-9a-f]{64}', manifest['base_image']), 'Immutable base required')
require('FROM ' + manifest['base_image'] + '\n' in dockerfile, 'Base image differs')
commit = manifest['custom_apps']['my_branding']['commit']
require(re.fullmatch(r'[0-9a-f]{40}', commit), 'my_branding: final commit required')
resolved = subprocess.check_output(['git', '-C', str(args.branding), 'rev-parse', commit + '^{commit}'], text=True).strip()
require(resolved == commit, 'my_branding: source differs')
require(f'com.nexumair.branding.commit="{commit}"' in dockerfile, 'my_branding: label differs')
target = root / 'my_branding'
require(not target.exists(), 'my_branding: prepared archive already exists')
archive = subprocess.check_output(['git', '-C', str(args.branding), 'archive', commit])
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    require('my_branding/hooks.py' in bundle.getnames(), 'my_branding: invalid source layout')
    # validated before anything is written
    target.mkdir()
    bundle.extractall(target, filter='data')
print('my_branding', commit, 'ready')
