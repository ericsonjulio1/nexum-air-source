"""Prepare exact reviewed Git archives without reading runtime configuration."""
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
parser.add_argument('--eam', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
manifest = json.loads((root / 'manifest.json').read_text())
dockerfile = (root / 'Dockerfile').read_text()
require(re.fullmatch(r'ericsonjulio/erpnext@sha256:[0-9a-f]{64}', manifest['base_image']), 'Immutable base required')
require('FROM ' + manifest['base_image'] + '\n' in dockerfile, 'Base image differs')
sources = (('my_branding', args.branding), ('eam', args.eam))
archives = {}
for name, source in sources:
    commit = manifest['custom_apps'][name]['commit']
    require(re.fullmatch(r'[0-9a-f]{40}', commit), name + ': final commit required')
    resolved = subprocess.check_output(['git', '-C', str(source), 'rev-parse', commit + '^{commit}'], text=True).strip()
    require(resolved == commit, name + ': source differs')
    require(not (root / name).exists(), name + ': prepared archive already exists')
    label = 'branding' if name == 'my_branding' else 'eam'
    require(f'com.nexumair.{label}.commit="{commit}"' in dockerfile, name + ': label differs')
    archives[name] = subprocess.check_output(['git', '-C', str(source), 'archive', commit])
    with tarfile.open(fileobj=io.BytesIO(archives[name])) as bundle:
        require(name + '/hooks.py' in bundle.getnames(), name + ': invalid source layout')

# Both archives and all destinations are validated before either is written.
for name, source in sources:
    target = root / name
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archives[name])) as bundle:
        bundle.extractall(target, filter='data')
    print(name, manifest['custom_apps'][name]['commit'], 'ready')
