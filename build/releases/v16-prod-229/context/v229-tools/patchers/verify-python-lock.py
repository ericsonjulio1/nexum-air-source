"""Fail the build unless its final Python environment exactly matches reviewed pins."""
import importlib.metadata
import json
from pathlib import Path
import re
import sys

APPS = {'frappe','erpnext','hrms','crm','helpdesk','insights','drive','telephony','payments','print-designer','gameplan','my-branding','eam'}
GIT = {'gunicorn': ('https://github.com/frappe/gunicorn', '54b59ca884c79dcf04d4882658a32bbaf17e999f'), 'pypika': ('https://github.com/frappe/pypika', '7ef6e40215d46cd531e8c4e58650b84c11abbd04')}

def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()

def locked_packages(path):
    locked = {}
    current = None
    hashed = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?', line)
        if match:
            current = canonical(match[1])
            if current in locked:
                raise RuntimeError('Duplicate package in lock')
            locked[current] = match[2]
        elif re.fullmatch(r'--hash=sha256:[0-9a-f]{64}\s*\\?', line) and current:
            hashed.add(current)
        else:
            raise RuntimeError('Unsupported lock syntax')
    if not locked or set(locked) != hashed:
        raise RuntimeError('Missing package hashes')
    return locked

def verify(path, maintenance=False):
    locked = locked_packages(path)
    expected_apps = set() if maintenance else APPS
    expected_git = {} if maintenance else GIT
    pypi, apps, git, seen = {}, set(), set(), set()
    for dist in importlib.metadata.distributions():
        name = canonical(dist.metadata['Name'])
        if name in seen:
            raise RuntimeError('Duplicate installed distribution: ' + name)
        seen.add(name)
        direct = dist.read_text('direct_url.json')
        if not direct:
            pypi[name] = dist.version
            continue
        direct = json.loads(direct)
        if name in expected_apps and direct == {'url': 'file:///home/frappe/frappe-bench/apps/' + name.replace('-', '_'), 'dir_info': {'editable': True}}:
            apps.add(name)
        elif name in expected_git and direct.get('url') == GIT[name][0] and direct.get('vcs_info', {}).get('commit_id') == GIT[name][1] and direct['vcs_info'].get('vcs') == 'git':
            git.add(name)
        else:
            raise RuntimeError('Unexpected direct distribution: ' + name)
    if pypi != locked or apps != expected_apps or git != set(expected_git):
        raise RuntimeError('Final environment differs from the complete lock and immutable app/Git inventory')
    return {'pass': True, 'pypi': pypi, 'editable_apps': sorted(apps), 'git': {name: GIT[name][1] for name in sorted(git)}}

if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1]), maintenance=sys.argv[2:] == ["--maintenance"]), sort_keys=True))
