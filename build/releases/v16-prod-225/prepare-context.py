"""Materialize the exact v225 source context using Python 3.12+ and git."""
import argparse,hashlib,io,json,shutil,subprocess,tarfile,tempfile,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('destination',type=Path)
p.add_argument('--branding-repository',type=Path,required=True)
p.add_argument('--archive-cache',type=Path,help='Optional previously verified codeload archives named APP.tar.gz')
a=p.parse_args();release=Path(__file__).resolve().parent;target=a.destination.resolve()
if target.exists():raise SystemExit('Refusing to replace an existing directory')
manifest=json.loads((release/'manifest.json').read_text());target.mkdir(parents=True);(target/'apps').mkdir()
with tempfile.TemporaryDirectory(prefix='nexum225-source-') as tmp:
 staging=Path(tmp)
 for app,spec in manifest['apps'].items():
  archive=staging/(app+'.tar.gz')
  cached=a.archive_cache/(app+'.tar.gz') if a.archive_cache else None
  if cached and cached.is_file():shutil.copy2(cached,archive)
  else:urllib.request.urlretrieve(spec['repository'].replace('https://github.com/','https://codeload.github.com/')+'/tar.gz/'+spec['commit'],archive)
  if hashlib.sha256(archive.read_bytes()).hexdigest()!=spec['archive_sha256']:raise RuntimeError('Archive checksum mismatch: '+app)
  with tarfile.open(archive) as bundle:
   top=bundle.getmembers()[0].name.split('/')[0];bundle.extractall(staging,filter='data')
  shutil.move(staging/top,target/'apps'/app)
for name in ('Dockerfile','.dockerignore','patch-dependencies.py','patch-migration-cache.py','patch-mcp-migration.py','patch-drive-menu.py','upstream.patch','upstream-v216.patch','python-security.patch','python-security.lock','python-security.in','verify-python-lock.py','maintenance-python-security.in','maintenance-python-security.lock','remove-compromised-roots.py','align-pip-ca.py','make-wheel-lock.py'):
 shutil.copy2(release/name,target/name)
shutil.copytree(release/'security',target/'security')
subprocess.run(['git','apply','--check',str(target/'upstream.patch')],cwd=target,check=True)
subprocess.run(['git','apply',str(target/'upstream.patch')],cwd=target,check=True)
shutil.copy2(release/'framework.png',target/'apps/frappe/frappe/public/images/framework.png')
for app in ('frappe/ui','helpdesk/desk'):
 if (release/'locks'/app/'package.json').read_bytes()!=(target/'apps'/app/'package.json').read_bytes():raise RuntimeError('Lock manifest mismatch: '+app)
 shutil.copy2(release/'locks'/app/'yarn.lock',target/'apps'/app/'yarn.lock')
commit=manifest['custom_apps']['my_branding']['commit'];repo=a.branding_repository.resolve()
if subprocess.check_output(['git','-C',str(repo),'rev-parse',commit+'^{commit}'],text=True).strip()!=commit:raise RuntimeError('Branding commit mismatch')
archive=subprocess.check_output(['git','-C',str(repo),'archive',commit])
(target/'apps/my_branding').mkdir()
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:bundle.extractall(target/'apps/my_branding',filter='data')
subprocess.run(['python3',str(target/'security/apply.py'),'--verify',str(target)],check=True)
print('Exact candidate context prepared:',target)
