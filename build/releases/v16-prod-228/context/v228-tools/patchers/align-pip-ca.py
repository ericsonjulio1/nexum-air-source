"""Align pip 26.2.2's vendored CA data with the pinned certifi 2026.10.23 store.

pip ships certifi 2026.10.19: it already removes the advisory's G3 root but
retains C1/C3 removed by certifi's October 23 update. This explicit data-only
patch keeps both installers aligned with the reviewed current trust store.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SOURCE_SHA = '2ef52ad56b4803e264045c915e55c236cbfa045b84b81efefc218a19eb44bd2b'
VENDORED_SHA = '50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785'


def main():
    results = {}
    for interpreter in ['/usr/local/bin/python', '/home/frappe/frappe-bench/env/bin/python']:
        code = 'import json,certifi,pip,pip._vendor.certifi; print(json.dumps([certifi.__version__,pip.__version__,certifi.where(),pip._vendor.certifi.where()]))'
        version, pip_version, source, destination = json.loads(subprocess.check_output([interpreter, '-I', '-B', '-c', code]))
        source, destination = Path(source), Path(destination)
        if version != '2026.10.23' or pip_version != '26.2.2' or source.is_symlink() or destination.is_symlink():
            raise RuntimeError('Unexpected pinned trust-store package or layout')
        if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA or hashlib.sha256(destination.read_bytes()).hexdigest() != VENDORED_SHA:
            raise RuntimeError('CA bundle content drift')
        shutil.copyfile(source, destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != SOURCE_SHA:
            raise RuntimeError('Trust-store alignment failed')
        results[interpreter] = {'source_sha256': SOURCE_SHA, 'previous_vendored_sha256': VENDORED_SHA}
    print(json.dumps({'pass': True, 'data_patch': results}))


if __name__ == '__main__':
    main()
