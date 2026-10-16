"""Archive only the final manifest pins; do not read runtime configuration."""
import argparse
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--branding', type=Path, required=True)
parser.add_argument('--eam', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
manifest = json.loads((root / 'manifest.json').read_text())
dockerfile = (root / 'Dockerfile').read_text()
assert 'FROM ' + manifest['base_image'] in dockerfile
sources = (('my_branding', args.branding), ('eam', args.eam))

# Validate BOTH pins and destinations before writing either source tree.
for name, source in sources:
    commit = manifest['custom_apps'][name]['commit']
    assert re.fullmatch(r'[0-9a-f]{40}', commit), name + ': replace placeholder with final commit'
    resolved = subprocess.check_output(['git', '-C', str(source), 'rev-parse', commit + '^{commit}'], text=True).strip()
    assert resolved == commit
    assert not (root / name).exists(), name + ': remove only the prior prepared archive before retrying'
    label = 'branding' if name == 'my_branding' else 'eam'
    assert f'com.nexumair.{label}.commit="{commit}"' in dockerfile, name + ': Dockerfile label and manifest differ'

for name, source in sources:
    commit = manifest['custom_apps'][name]['commit']
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', commit])
    target = root / name
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(target, filter='data')
    assert (target / name / 'hooks.py').exists(), name
    print(name, commit, 'ready')
