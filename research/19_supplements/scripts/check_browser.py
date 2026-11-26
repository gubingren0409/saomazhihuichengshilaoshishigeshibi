"""Actual local Chromium interaction and offline resource check; same author context."""
from pathlib import Path
import json,datetime,hashlib
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];errors=[];requests=[];cases=[]
with sync_playwright()as p:
 browser=p.chromium.launch(channel='chrome',headless=True);browser_version=browser.version
 page=browser.new_page(viewport={'width':1500,'height':1150},device_scale_factor=1)
 page.on('pageerror',lambda e:errors.append(str(e)))
 def intercept(route):
  url=route.request.url;requests.append(url)
  if url.startswith(('file:','data:','about:')):route.continue_()
  else:errors.append('UNEXPECTED_EXTERNAL_RESOURCE:'+url.split('?')[0]);route.abort()
 page.route('**/*',intercept);page.goto((ROOT/'index.html').as_uri(),wait_until='load');page.wait_for_function('window.VIEWER_READY === true')
 for scene in range(3):
  page.locator('#scene').select_option(str(scene));count=page.locator('#variant option').count()
  for v in range(count):
   page.locator('#variant').select_option(str(v));status=page.locator('#status').inner_text();pixels=page.locator('#map').evaluate('(c)=>{let a=c.getContext("2d").getImageData(0,0,c.width,c.height).data,n=0;for(let i=3;i<a.length;i+=4)if(a[i])n++;return n}');assert pixels>1000
   cases.append({'scene_index':scene,'variant_index':v,'status_text':status,'nontransparent_pixels':pixels})
  page.locator('#near').click();page.locator('#full').click();page.locator('#labels').uncheck();page.locator('#labels').check();page.locator('#route').uncheck();page.locator('#route').check();page.locator('#base').uncheck();page.locator('#base').check()
 page.locator('#scene').select_option('0');page.locator('#variant').select_option('0');page.screenshot(path=str(ROOT/'figures/browser_review.png'),full_page=False)
 assert not errors,errors
 browser.close()
receipt={'timestamp':datetime.datetime.now().astimezone().isoformat(),'identity':'AUTHOR_BROWSER_CHECK_SEPARATE_CHROMIUM_PROCESS_NOT_INDEPENDENT_REVIEWER','page':'index.html','html_sha256':hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),'actual_browser':'Installed Chrome via Playwright','browser_version':browser_version,'checks':cases,'javascript_errors':errors,'attempted_external_resources':[],'external_requests_sent':0,'offline_inline_data':True,'screenshot':'figures/browser_review.png','scope':'Result replay viewer only, not a live HTTP route computation','status':'PASS'}
(ROOT/'audit/browser_check.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print('BROWSER_CHECK_PASS',len(cases))
