"""Rename only native ERP launcher fallbacks in the immutable v213 sources.

Rebuild the six affected frontends with their inherited locked dependencies.
Never rewrite minified output or user-authored content.
"""
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
sources = {
    "apps/crm/frontend/src/components/UserDropdown.vue": "96402c1785e2396de4ab072798740d615a875a77d5052d376fcd4c70abe8de5f",
    "apps/helpdesk/desk/src/composables/useApps.ts": "9bf63abd2c9e1669d6db3a01d93a3e9ebaea8504667ff64104f9a79060967233",
    "apps/drive/frontend/src/resources/permissions.js": "a8c666121a2ba25adc3e7137199b850fc1ffa9f33b98a139185ab3d3aa6496fc",
    "apps/insights/frontend/src2/components/UserDropdown.vue": "1559490959c4d4928602fee173c08b1399bd66f16e200dca77773ff0c12ca81f",
    "apps/insights/frontend/src/components/Sidebar.vue": "f7f48d9a9ca268272e5e9a129df479042d5a045b7b79033611011a0e2f794dda",
    "apps/gameplan/frontend/src/components/UserDropdown.vue": "a8d7b5d5e3a4751789eb9286e0e4f3bf40e315a44faa8279605aea128222670b",
    "apps/hrms/roster/src/components/NavBar.vue": "c89240635c0a732704e00ea233f4f4e282600c6f0cedb6c9d38a96e7444b6c1f",
}
prepared = {}
for relative, expected in sources.items():
    path = root / relative
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"Unexpected v213 source: {relative}"
    text = path.read_text()
    if relative == "apps/hrms/roster/src/components/NavBar.vue":
        assert text.count("label: 'Switch to Desk'") == 1, relative
        prepared[path] = text.replace("label: 'Switch to Desk'", "label: 'Switch to ERP'")
        continue
    assert text.count("Nexum Air") == 1, relative
    text = text.replace("Nexum Air", "ERP")
    if relative.endswith("apps/insights/frontend/src/components/Sidebar.vue"):
        assert text.count("label: 'Switch to Desk'") == 1, relative
        text = text.replace("label: 'Switch to Desk'", "label: 'Switch to ERP'")
    expected_icons = 0 if relative.endswith("src/components/Sidebar.vue") else 1
    assert text.count("erpnext_app.svg") == expected_icons, relative
    prepared[path] = text.replace("erpnext_app.svg", "erp_app.svg")
for path, text in prepared.items():
    path.write_text(text)
print("ERP fallback labels and icon paths updated in seven pinned source files")
