#!/usr/bin/env python3
"""Regression: first painted frames, native Teams menu, and finance ownership."""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
password=os.environ.get('PASSWORD')
base=os.environ['BASE_URL'].rstrip('/')
failures=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'))
 ctx=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
 if os.environ.get('SID'):
  ctx.add_cookies([{'name':'sid','value':os.environ['SID'],'url':base}])
 else:
  assert ctx.request.post(base+'/api/method/login',form={'usr':os.environ.get('USER_ID','Administrator'),'pwd':password}).ok
 page=ctx.new_page();page.goto(base+'/drive');page.wait_for_load_state('networkidle')
 page.evaluate('''() => {
 window.__deskFrames=[];window.__trackDesk=true;
 const frame=()=>{if(!window.__trackDesk)return;
 const visible=[...document.querySelectorAll('[role="menuitem"]')].filter(e=>e.getBoundingClientRect().width && getComputedStyle(e).visibility!=='hidden' && Number(getComputedStyle(e).opacity)>0);
 if(visible.some(e=>e.textContent.trim()==='Desk'))window.__deskFrames.push(performance.now());
 requestAnimationFrame(frame)};requestAnimationFrame(frame);
 }''')
 counts=[]
 for _ in range(3):
  page.get_by_role('button',name='Drive',exact=False).first.click()
  page.get_by_role('menuitem',name='Apps',exact=True).hover()
  page.get_by_role('menuitem',name='Nexum Air',exact=True).wait_for()
  page.wait_for_timeout(500)
  counts.append(page.evaluate('window.__deskFrames.length'))
  page.keyboard.press('Escape');page.keyboard.press('Escape');page.wait_for_timeout(100)
 page.evaluate('window.__trackDesk=false')
 print('Drive painted Desk frames over three menu openings:',counts,flush=True)
 if counts[-1]:failures.append('Drive paints a duplicate Desk entry before removing it')
 page.goto(base+'/g');page.wait_for_load_state('networkidle')
 page.get_by_role('button',name='Teams',exact=False).first.click()
 native=page.get_by_role('menuitem',name='Apps',exact=True).count()
 floating=page.locator('#nexum-apps-btn').count()
 if os.environ.get('OUTPUT_DIR'):
  output=Path(os.environ['OUTPUT_DIR']);output.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(output/'teams-menu.png'))
 print('Teams top-left Apps items:',native,'floating bottom Apps:',floating,flush=True)
 if native!=1 or floating:failures.append('Teams is missing the native top-left Apps menu')
 if native == 1:
  apps=page.get_by_role('menuitem',name='Apps',exact=True)
  apps.hover()
  launcher=page.get_by_role('menuitem',name='Nexum Air',exact=True)
  launcher.wait_for(state='visible')
  assert launcher.count()==1
  assert page.get_by_role('menuitem',name='Desk',exact=True).count()==0
  launcher.focus();page.keyboard.press('Escape')
  assert apps.evaluate('e=>e===document.activeElement')
  apps.press('ArrowRight')
  assert launcher.evaluate('e=>e===document.activeElement')
  page.keyboard.press('ArrowDown');page.keyboard.press('Home')
  assert launcher.evaluate('e=>e===document.activeElement')
  page.keyboard.press('Enter')
  page.locator('.desktop-icon img[alt="Nexum Air"]').wait_for()
  print('PASS Teams mouse and keyboard submenu, Escape focus return, and launcher destination',flush=True)

 page.goto(base+'/desk/maintenance');page.wait_for_load_state('networkidle')
 financial=page.locator('.sidebar-items a').filter(has_text='Maintenance Costs').count()
 financial+=page.locator('.sidebar-items a').filter(has_text='Financial Overview').count()
 print('Maintenance financial overview sidebar entries:',financial,flush=True)
 if financial:failures.append('Maintenance still exposes the duplicated financial doorway')
 browser.close()
assert not failures, '; '.join(failures)
