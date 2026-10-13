"""Keep Web Form attachment authorization aligned with its authorized parent save."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'apps/frappe/frappe/website/doctype/web_form/web_form.py'
s=p.read_text()
old='\t\t\t_file.save()\n\n\t\t\t# update values'
new='\t\t\t# Nexum: the form and parent document were authorized and saved above.\n\t\t\t_file.save(ignore_permissions=True)\n\n\t\t\t# update values'
if new not in s:
 assert s.count(old)==1,'Upstream Web Form attachment drift'
 s=s.replace(old,new)
compile(s,str(p),'exec');p.write_text(s)
print('Authorized Web Form attachment compatibility verified')
