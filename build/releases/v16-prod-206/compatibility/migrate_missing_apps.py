"""Migrate archived custom sidebars without docking apps absent from this tenant.

Keep the archived sidebar and converted module; only skip an impossible dock edit.
The native dock validator stays unchanged for actual API writes.
"""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'apps/frappe/frappe/patches/v16_0/convert_custom_sidebars.py'
s=p.read_text()
old='\tapp = mounted_apps().get(app, app)\n\trail = resolve_app_dock(app, upto="site", gated=False)'
new='\tapp = mounted_apps().get(app, app)\n\t# Nexum: template sites can retain archived sidebars for an uninstalled app.\n\tif app not in frappe.get_installed_apps():\n\t\treturn\n\trail = resolve_app_dock(app, upto="site", gated=False)'
if new not in s:
 assert s.count(old)==1,'Upstream migration drift'
 s=s.replace(old,new)
compile(s,str(p),'exec');p.write_text(s)
print('Absent-app sidebar migration compatibility verified')
