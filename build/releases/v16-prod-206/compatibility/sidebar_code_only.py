"""Preserve an authored sidebar whose title names a module with no navigation.

ERPNext now declares its native Maintenance module code-only. EAM's Maintenance
sidebar remains the only navigable shell of that name; routing and validation
must agree with the boot payload. Do not relax collisions with navigable modules.
"""
from pathlib import Path
import sys

p=Path(sys.argv[1])/'apps/frappe/frappe/desk/doctype/sidebar/sidebar.py'
s=p.read_text()
changes=[
('from frappe.utils.modules import get_code_only_module_heirs, get_module_placement',
 'from frappe.utils.modules import get_code_only_module_heirs, get_code_only_modules, get_module_placement'),
('\ttaken += [other for other in frappe.get_all("Module Def", pluck="name") if other != module]',
 '\t# Nexum: code-only modules have no computed shell or URL to collide with.\n\ttaken += [other for other in frappe.get_all("Module Def", pluck="name")\n\t\tif other != module and other not in get_code_only_modules()]'),
('\t\tif self.title == self.module:\n\t\t\treturn',
 '\t\tif self.title == self.module or self.title in get_code_only_modules():\n\t\t\treturn'),
('\tif frappe.db.exists("Module Def", shell, cache=True):\n\t\treturn shell',
 '\t# Nexum: an authored shell may reuse a code-only module name.\n\tif shell in get_code_only_modules():\n\t\tif row := frappe.db.get_value("Sidebar", shell, ["module"], as_dict=True, cache=True):\n\t\t\treturn row.module or None\n\tif frappe.db.exists("Module Def", shell, cache=True):\n\t\treturn shell'),
]
for old,new in changes:
    if new in s: continue
    assert s.count(old)==1, f'Upstream drift: {old[:80]}'
    s=s.replace(old,new)
compile(s,str(p),'exec')
p.write_text(s)
print('Code-only module sidebar compatibility verified')
