"""Use v16 structured aggregate fields; retain the Framework's SQL validation."""
from pathlib import Path
import sys
root=Path(sys.argv[1])/'apps/gameplan/gameplan'
patches={
 'api.py': [('"count(name) as count",', '[{"COUNT": "name", "as": "count"}],')],
 'gameplan/doctype/gp_project/gp_project.py': [('fields=["sum(is_completed) as completed", "count(name) as total"]', 'fields=[{"SUM": "is_completed", "as": "completed"}, {"COUNT": "name", "as": "total"}]')],
 'patches/rename_doctypes_with_gp_prefix.py': [('fields=["max(name) as last"]','fields=[{"MAX": "name", "as": "last"}]')],
}
for name,changes in patches.items():
 p=root/name;s=p.read_text()
 for old,new in changes:
  if new not in s:
   assert s.count(old)==1,f'Gameplan query drift: {name}'
   s=s.replace(old,new)
 compile(s,str(p),'exec');p.write_text(s)
print('Gameplan structured aggregate fields verified')
