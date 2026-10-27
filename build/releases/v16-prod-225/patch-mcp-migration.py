"""Keep the bundled MCP service opt-in on upgraded sites as well as new sites."""
from pathlib import Path
import hashlib
path = Path('/home/frappe/frappe-bench/apps/frappe/frappe/patches.txt')
old = 'execute:frappe.db.set_single_value("System Settings", "enable_mcp", 1)'
new = 'execute:frappe.db.set_single_value("System Settings", "enable_mcp", 0)'
source = path.read_text()
if source.count(old) != 1 or new in source:
    raise RuntimeError('MCP migration changed upstream; review before patching')
path.write_text(source.replace(old, new))
print('MCP migration is opt-in:', hashlib.sha256(path.read_bytes()).hexdigest())
