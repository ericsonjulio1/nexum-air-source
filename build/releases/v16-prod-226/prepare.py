"""Prepare exact reviewed app archives; private EAM repository access is required."""
import argparse,io,json,re,subprocess,tarfile
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
prepared=[]
for name,repo in [('my_branding',args.branding),('eam',args.eam)]:
    commit=manifest['custom_apps'][name]['commit'];target=root/name
    require(not target.exists(),'Prepared archive already exists: '+name)
    require(subprocess.check_output(['git','-C',str(repo),'rev-parse',commit+'^{commit}'],text=True).strip()==commit,'Source commit differs')
    require('com.nexumair.'+name+'.commit="'+commit+'"' in dockerfile,'Source label differs')
    archive=subprocess.check_output(['git','-C',str(repo),'archive',commit])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(name+'/hooks.py' in tar.getnames(),'Wrong source layout')
    prepared.append((target,archive))
for target,archive in prepared:
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(target,filter='data')
print('Exact committed application archives prepared')
