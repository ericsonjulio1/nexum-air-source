"""Prepare exact reviewed app archives; private EAM repository access is required."""
import argparse,io,json,os,re,subprocess,tarfile
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--branding',type=Path,required=True)
parser.add_argument('--eam',type=Path,required=True)
args=parser.parse_args();root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text());dockerfile=(root/'Dockerfile').read_text()
def require(ok,message):
    if not ok:raise RuntimeError(message)
require(re.fullmatch(r'ericsonjulio/erpnext@sha256:[0-9a-f]{64}',manifest['base_image']),'Immutable base required')
require('FROM '+manifest['base_image']+'\n' in dockerfile,'Base image differs')
env={k:v for k,v in os.environ.items() if k not in ('GIT_ICASE_PATHSPECS','GIT_GLOB_PATHSPECS','GIT_NOGLOB_PATHSPECS','GIT_LITERAL_PATHSPECS')}
env.update(GIT_NO_REPLACE_OBJECTS='1',GIT_CONFIG_NOSYSTEM='1')
def git(repo,*a):return subprocess.check_output(['git','-c','core.attributesFile=/dev/null','-C',str(repo),*a],env=env)
prepared=[]
for name,repo in [('my_branding',args.branding),('eam',args.eam)]:
    row=manifest['custom_apps'][name];commit=row['commit'];target=root/name
    require(not target.exists(),'Prepared archive already exists: '+name)
    require(git(repo,'rev-parse',commit+'^{commit}').decode().strip()==commit,'Source commit differs')
    require(git(repo,'rev-parse',commit+'^{tree}').decode().strip()==row['tree'],'Source tree differs')
    require('com.nexumair.'+name+'.commit="'+commit+'"' in dockerfile,'Source label differs')
    excluded=row.get('excluded_paths',[])
    require(excluded==sorted(set(excluded)) and all(p.endswith('/') and not p.startswith('/') and '..' not in p.split('/') for p in excluded),'Excluded paths are not reviewed directory prefixes')
    archive=git(repo,'archive','--format=tar',commit,*(['--','.']+[':(exclude,literal,top)'+p[:-1] for p in excluded] if excluded else []))
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        names=tar.getnames()
        require(name+'/hooks.py' in names,'Wrong source layout')
        require(not any(n==p[:-1] or n.startswith(p) for n in names for p in excluded),'Excluded path present')
    prepared.append((target,archive))
for target,archive in prepared:
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(target,filter='data')
print('Exact committed application archives prepared')
