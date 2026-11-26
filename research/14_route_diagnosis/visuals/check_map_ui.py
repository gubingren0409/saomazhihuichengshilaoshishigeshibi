"""Author UI verification only. This client has no routing endpoint."""
from pathlib import Path
import os,json,hashlib,datetime
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
temp=ROOT/'runs/ui_temp';temp.mkdir(parents=True,exist_ok=True);os.environ['TEMP']=str(temp);os.environ['TMP']=str(temp)
errors=[];requests=[];checks=[];layout=[]
with sync_playwright()as p:
 browser=p.chromium.launch(channel='msedge',headless=True)
 page=browser.new_page(viewport={'width':1520,'height':1050},device_scale_factor=1)
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:requests.append({'method':r.method,'url':r.url}))
 page.goto('http://127.0.0.1:53451/',wait_until='networkidle',timeout=90000)
 page.wait_for_function('window.R2_VIEW_DATA && window.R2_VIEW_DATA.strict_diagnosis_ready===true',timeout=90000)
 assert page.locator('.card').count()==4
 for i in range(4):
  page.locator('.card').nth(i).click()
  for mode in ['B0','B1','B2','B3']:
   for method in ['F0','F1']:
    page.select_option('#mode',mode);page.select_option('#method',method)
    assert page.locator('#map path').count()>0
    assert page.locator('#interfaceTable tbody tr').count()>0;assert page.locator('#counterfactual tbody tr').count()==4
    checks.append({'case_index':i,'mode':mode,'method':method,'map_paths':page.locator('#map path').count(),'interface_rows':page.locator('#interfaceTable tbody tr').count(),'status':'PASS'})
  for w in ['5','10','20','0']:page.select_option('#corridor',w)
  page.select_option('#corridor','10')
  for layer in ['sourceP','omega','newfaces','native','restrictions','interfaces','alternatives']:
   control=page.locator('#'+layer);initial=control.is_checked();control.set_checked(not initial);control.set_checked(initial)
  page.locator('#fit').click();page.locator('.mapgrid').screenshot(path=str(ROOT/f'audits/map_layout_fixed_case_{i}.png'))
  page.locator('#door').click();page.locator('.mapgrid').screenshot(path=str(ROOT/f'audits/map_layout_fixed_near_{i}.png'))
  if page.locator('#facesTable tbody tr').count():
   page.locator('#facesTable tbody tr').first.click();assert 'source' in page.locator('#selected').inner_text().lower() or 'id' in page.locator('#selected').inner_text().lower()
  page.locator('#interfaceTable tbody tr').first.click();selected=json.loads(page.locator('#selected').inner_text());assert 'current_mode_membership' in selected;assert 'ui_record_key' in selected
  geo=page.evaluate('({scrollX:window.scrollX,documentWidth:document.documentElement.scrollWidth,viewportWidth:window.innerWidth})');assert geo['scrollX']==0 and geo['documentWidth']<=geo['viewportWidth'],geo;layout.append({'case':i,**geo})
  with page.expect_download()as info:page.locator('#save').click()
  dl=info.value;target=ROOT/f'audits/map_export_case_{i}.json';dl.save_as(str(target));export=json.loads(target.read_text(encoding='utf-8'));assert export['not_new_solver_request'] is True
 page.locator('.card').first.click();page.select_option('#mode','B3');page.select_option('#method','F0');page.locator('#fit').click()
 data=page.evaluate('({cases:R2_VIEW_DATA.diagnosis.cases.map(c=>({id:c.id,metrics:c.interface_metrics.length,faces:c.faces.length})),pool:R2_VIEW_DATA.diagnosis.interface_definitions.length,shared:R2_VIEW_DATA.diagnosis.shared_evidence_values.length,overview:R2_VIEW_DATA.diagnosis.overview})')
 page.locator('#overview').screenshot(path=str(ROOT/'audits/map_layout_fixed_overview.png'))
 browser.close()
assert not errors,errors
assert not [r for r in requests if r['method']!='GET'],requests
assert not [r for r in requests if not r['url'].startswith('http://127.0.0.1:53451/')],requests
out={'role':'AUTHOR_BROWSER_CHECK','time':datetime.datetime.now().astimezone().isoformat(),'url':'http://127.0.0.1:53451/','html_sha256':hashlib.sha256((ROOT/'visuals/index.html').read_bytes()).hexdigest(),'ui_data_sha256':hashlib.sha256((ROOT/'results/map_ui.json').read_bytes()).hexdigest(),'checks':checks,'page_errors':errors,'HTTP_requests':requests,'external_requests':0,'solver_calls':0,'exports':4,'layout_checks':layout,'data_counts':data,'status':'PASS'}
(ROOT/'audits/map_final_ui_check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','combinations':len(checks),'page_errors':len(errors),'solver_calls':0,'sha256':out['html_sha256']},ensure_ascii=False))
