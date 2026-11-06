"""Apply the emSign distrust from certifi's October 2026 advisory to system TLS.

Hash-pinned public root certificates remain on disk for audit but are disabled
in Debian's trust inventory. Node uses this same OpenSSL store at runtime.
"""
import hashlib
import json
from pathlib import Path
import ssl
import subprocess

REMOVED = {
    'emSign_ECC_Root_CA_-_C3.crt': 'bc4d809b15189d78db3e1d8cf4f9726a795da1643ca5f1358e1ddb0edc0d7eb3',
    'emSign_Root_CA_-_C1.crt': '125609aa301da0a249b97a8239cb6a34216f44dcac9f3954b14292f2e8c8608f',
    'emSign_ECC_Root_CA_-_G3.crt': '86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    config = Path('/etc/ca-certificates.conf')
    lines = config.read_text().splitlines()
    for name, digest in REMOVED.items():
        certificate = Path('/usr/share/ca-certificates/mozilla') / name
        require(hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.read_text())).hexdigest() == digest, 'Unexpected root certificate: ' + name)
        entry = 'mozilla/' + name
        require(lines.count(entry) == 1, 'Expected enabled root is missing or duplicated')
        lines[lines.index(entry)] = '!' + entry
    config.write_text('\n'.join(lines) + '\n')
    subprocess.run(['update-ca-certificates', '--fresh'], check=True)
    trusted = {hashlib.sha256(cert).hexdigest() for cert in ssl.create_default_context().get_ca_certs(binary_form=True)}
    require(len(trusted) >= 100 and trusted.isdisjoint(REMOVED.values()), 'System distrust did not take effect')
    print(json.dumps({'pass': True, 'removed_sha256': REMOVED, 'system_trusted_roots': len(trusted)}))


if __name__ == '__main__':
    main()
