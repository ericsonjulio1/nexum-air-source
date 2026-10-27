"""Seal wheels built exclusively from the complete hash-verified source lock."""
from email.parser import BytesParser
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

root = Path(sys.argv[1])
source = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('lock_reader', Path(__file__).with_name('verify-python-lock.py'))
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
expected = reader.locked_packages(source)
packages = {}
for wheel in sorted(root.glob('*.whl')):
    with zipfile.ZipFile(wheel) as archive:
        metadata = [name for name in archive.namelist() if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
        if len(metadata) != 1:
            raise RuntimeError('Unexpected top-level wheel metadata inventory: ' + wheel.name)
        info = BytesParser().parsebytes(archive.read(metadata[0]))
    name, version = reader.canonical(info['Name']), info['Version']
    if name in packages or expected.get(name) != version:
        raise RuntimeError('Unexpected or duplicate built wheel: ' + name)
    packages[name] = {'version': version, 'filename': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}
if set(packages) != set(expected):
    raise RuntimeError('Built wheel inventory differs from source lock')
lock = '\n'.join(name+'=='+item['version']+' --hash=sha256:'+item['sha256'] for name,item in sorted(packages.items()))+'\n'
(root/'wheels.lock').write_text(lock)
record = {'source_lock_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'wheel_lock_sha256':hashlib.sha256(lock.encode()).hexdigest(),'packages':packages,'rustc':subprocess.check_output(['rustc','--version'],text=True).strip(),'compiler':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],'build_packages':subprocess.check_output(['dpkg-query','-W','build-essential','pkg-config','libmariadb-dev','libmariadb3'],text=True).splitlines()}
(root/'wheels.json').write_text(json.dumps(record,indent=2)+'\n')
print('Sealed',len(packages),'source-verified wheels for offline hash-enforced reinstallation')
