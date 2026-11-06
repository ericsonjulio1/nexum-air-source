"""Preserve the v210/v214 native Drive menu correction when replacing Drive."""
from pathlib import Path
import hashlib
path=Path('/home/frappe/frappe-bench/apps/drive/frontend/src/resources/permissions.js')
old='''    let apps = [
      {
        name: "frappe",
        logo: "/assets/frappe/images/framework.png",
        title: "Desk",
        route: "/app",
      },
    ]'''
new='''    let apps = data.some(app => app.name === "erpnext") ? [] : [
      {
        name: "erpnext",
        logo: "/assets/my_branding/images/icons/erp_app.svg",
        title: "ERP",
        route: "/desk",
      },
    ]'''
source=path.read_text()
if source.count(old)!=1:
    raise RuntimeError('Drive app switcher changed; review the native menu patch')
path.write_text(source.replace(old,new))
print('Drive native menu patch:',hashlib.sha256(path.read_bytes()).hexdigest())
