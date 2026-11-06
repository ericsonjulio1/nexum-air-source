#!/usr/bin/env python3
"""Verify CRM's exact import-map mitigation in built output; never edits files."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

PULSE_URL = 'https://pulse.m.frappe.cloud/assets/pulse/js/pulse_client.js'
STUB_URL = '/assets/crm/frontend/nexum-pulse-client-noop.js'
STUB_SHA256 = 'ea7fd1f4d72aee3a4d94dc544bebad525723f0a769d9c3369b9c1a919fe5deb3'
MAPPING = {'imports': {PULSE_URL: STUB_URL}}
HTML_PATH = 'apps/crm/crm/www/crm.html'
STUB_PATH = 'apps/crm/crm/public/frontend/nexum-pulse-client-noop.js'
FRONTEND = 'apps/crm/crm/public/frontend'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate import-map key')
        result[key] = value
    return result


class ImportMapHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.index = 0
        self.in_head = False
        self.scripts, self.modules, self.preloads, self.maps = [], [], [], []
        self.current = None

    def handle_starttag(self, tag, attrs):
        self.index += 1
        attrs = unique_object(attrs)
        if tag == 'head':
            self.in_head = True
        if tag == 'script':
            self.scripts.append(self.index)
            kind = (attrs.get('type') or '').lower()
            if kind == 'module':
                self.modules.append(self.index)
            if kind == 'importmap':
                require(attrs == {'type': 'importmap'}, 'Unexpected import-map attributes')
                self.current = {'index': self.index, 'head': self.in_head, 'text': ''}
                self.maps.append(self.current)
        if tag == 'link' and 'modulepreload' in (attrs.get('rel') or '').lower().split():
            self.preloads.append(self.index)

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.current = None
        elif tag == 'head':
            self.in_head = False


def verify_html(text, *, built=True):
    parser = ImportMapHTML()
    parser.feed(text); parser.close()
    require(len(parser.maps) == 1, 'Exactly one CRM import map required')
    mapping = parser.maps[0]
    require(mapping['head'] and mapping['index'] == min(parser.scripts),
            'Import map must be the first script in head')
    require(json.loads(mapping['text'], object_pairs_hook=unique_object) == MAPPING,
            'CRM import map must contain only the exact Pulse mapping')
    require(parser.modules, 'CRM module entry point missing')
    require(not built or parser.preloads, 'CRM modulepreload missing')
    require(all(mapping['index'] < position for position in parser.modules + parser.preloads),
            'CRM import map must precede modules and modulepreloads')


def verify_contents(html, stub, chunks):
    """Shared by the build step and source-bound image-audit replay."""
    verify_html(html)
    require(digest(stub) == STUB_SHA256, 'CRM Pulse stub hash differs')
    require(chunks, 'CRM built chunks missing')
    telemetry = []
    hashes = {}
    for name, text in sorted(chunks.items()):
        require(name.startswith(FRONTEND + '/') and name.endswith('.js')
                and '..' not in Path(name).parts, 'Unexpected CRM built chunk path')
        hashes[name] = digest(text.encode())
        urls = re.findall(r'(?:https?:)?//[^\s\"\'`<>\\()]+', text)
        pulse_clients = [url for url in urls if 'pulse' in url.lower()
                         and ('client' in url.lower() or '.js' in url.lower())]
        require(all(url == PULSE_URL for url in pulse_clients),
                'Different Pulse client URL in CRM chunk: ' + name)
        if PULSE_URL in text:
            require(Path(name).name.startswith('telemetry-'), 'Pulse import escaped the telemetry chunk')
            telemetry.append({'path': name, 'sha256': hashes[name]})
    require(len(telemetry) == 1, 'Exactly one telemetry chunk with the exact Pulse default URL required')
    return {'pass': True, 'html_sha256': digest(html.encode()), 'stub_sha256': digest(stub),
            'telemetry_chunks': telemetry, 'scanned_chunks': len(hashes),
            'chunk_inventory_sha256': digest(json.dumps(hashes, sort_keys=True).encode()),
            'mapping': MAPPING}


def regular(root, relative):
    path = root / relative
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            'Missing or unsafe CRM built file: ' + str(relative))
    return path


def verify(root):
    root = Path(root)
    chunks = {p.relative_to(root).as_posix(): regular(root, p.relative_to(root)).read_text()
              for p in sorted((root / FRONTEND).rglob('*.js'))}
    return verify_contents(regular(root, HTML_PATH).read_text(), regular(root, STUB_PATH).read_bytes(), chunks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', required=True)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), sort_keys=True))
