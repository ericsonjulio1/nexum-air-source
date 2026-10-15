"""Fail-closed adapters for the pinned v209 Drive and Teams sources."""
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
source = Path(__file__).resolve().parent

def replace(relative, old, new):
    path = root / relative
    content = path.read_text()
    assert content.count(old) == 1, (relative, content.count(old))
    path.write_text(content.replace(old, new))

# Do not render a duplicate and hide it later: it flashes on every hover.
replace('apps/drive/frontend/src/resources/permissions.js', '''    let apps = [
      {
        name: "frappe",
        logo: "/assets/frappe/images/framework.png",
        title: "Desk",
        route: "/app",
      },
    ]''', '''    let apps = data.some(app => app.name === "erpnext") ? [] : [
      {
        name: "erpnext",
        logo: "/assets/my_branding/images/icons/erpnext_app.svg",
        title: "Nexum Air",
        route: "/desk",
      },
    ]''')
path = root / 'apps/gameplan/frontend/src/components/UserDropdown.vue'
assert hashlib.sha256(path.read_bytes()).hexdigest() == '959f2eeea3e29e9d5c7120ce4a3ec14f0c6fe041aadf62d03d2e82d6f6a5386d', 'Unexpected Teams menu source'
path.write_bytes((source / 'TeamsUserDropdown.vue').read_bytes())
print('Applied v210 source adapters: Drive and Teams native menus')
