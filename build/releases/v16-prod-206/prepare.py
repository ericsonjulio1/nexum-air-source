"""Fetch immutable upstream sources and assemble the release's Docker build context.

Supply the release's custom-app checkouts with --branding and --eam. This program
never reads a site, database backup, credential file, or Docker credential store.
"""
import argparse,concurrent.futures,hashlib,json,shutil,subprocess,tarfile,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--branding',type=Path,required=True);p.add_argument('--eam',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parent;m=json.loads((r/'manifest.json').read_text());(r/'apps').mkdir(exist_ok=True)
def fetch(pair):
 name,info=pair; archive=r/(name+'.tar.gz')
 request=urllib.request.Request(info['repository'].replace('https://github.com/','https://codeload.github.com/')+'/tar.gz/'+info['commit'],headers={'User-Agent':'Nexum-release-source'})
 if not archive.exists():
  with urllib.request.urlopen(request) as response,archive.open('wb') as out:shutil.copyfileobj(response,out)
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==info['archive_sha256'],name
 dest=r/'apps'/name;dest.mkdir(exist_ok=True)
 with tarfile.open(archive) as tf:
  prefix=tf.getmembers()[0].name.split('/')[0]+'/'
  members=[]
  for member in tf.getmembers():
   if not member.name.startswith(prefix):continue
   member.name=member.name[len(prefix):]
   if member.name:members.append(member)
  tf.extractall(dest,members=members,filter='data')
 return name
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for name in pool.map(fetch,m['apps'].items()):print(name,'verified')
subprocess.run(['patch','-p1','-i',str(r/'upstream.patch')],cwd=r,check=True)
shutil.copy2(r/'framework.png',r/'apps/frappe/frappe/public/images/framework.png')
for name,source in [('my_branding',a.branding),('eam',a.eam)]:
 assert (source/name/'hooks.py').exists(),source
 shutil.copytree(source,r/'custom'/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__','*.pyc'))
print('Context ready. Build with docker buildx build --platform linux/amd64 -t ericsonjulio/erpnext:v16-prod-206 .')
