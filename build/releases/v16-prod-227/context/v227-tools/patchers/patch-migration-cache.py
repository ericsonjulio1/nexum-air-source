"""Refresh the in-process module map after migration clears its backing cache."""
import hashlib
from pathlib import Path

path = Path('/home/frappe/frappe-bench/apps/frappe/frappe/migrate.py')
source = path.read_text()
before = '\t\tfrappe.clear_cache()\n\n\t\tif os.path.exists(self.touched_tables_file):'
after = (
    '\t\tfrappe.clear_cache()\n'
    '\t\t# init may have read the previous release\'s cached module list.\n'
    '\t\t# New modules must participate in the first schema sync.\n'
    '\t\tfrappe.setup_module_map()\n\n'
    '\t\tif os.path.exists(self.touched_tables_file):'
)
if source.count(before) != 1:
    raise RuntimeError('Unexpected migration setup source; review the cache fix')
path.write_text(source.replace(before, after))
print('Migration module-map refresh applied:', hashlib.sha256(path.read_bytes()).hexdigest())
