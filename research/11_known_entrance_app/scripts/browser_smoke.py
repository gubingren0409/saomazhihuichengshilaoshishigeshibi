"""Genuine UI -> HTTP -> solver -> export, with no remote browser requests."""
from pathlib import Path
import json,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'AUDIT/browser';out.mkdir(exist_ok=True,parents=True)
    errors=[];responses=[];requests=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-background-networking','--disable-sync','--no-first-run'])
        context=browser.new_context(viewport={'width':1500,'height':1080},accept_downloads=True)
        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:53421/') else route.abort())
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append({'url':r.url,'method':r.method,'body':r.post_data}) if '/api/plan' in r.url else None)
        page.goto('http://127.0.0.1:53421/',wait_until='domcontentloaded',timeout=60000)
        page.wait_for_function("document.querySelector('#start').options.length>0",timeout=120000)
        page.select_option('#door','node/6897145227')
        page.wait_for_function("document.querySelector('#status').textContent.includes('地图就绪')",timeout=120000)
        page.select_option('#start','node/10073042336');page.select_option('#method','F0')
        for method,case in [('F0','APP-03'),('F1','APP-04')]:
            if method=='F1':
                page.select_option('#method',method)
                assert '输入已变化' in page.locator('#status').inner_text()
                assert page.locator('#json').is_disabled()
            with page.expect_response(lambda r:r.url.endswith('/api/plan') and r.request.method=='POST',timeout=300000) as awaited:
                page.click('#compute')
            response=awaited.value;result=response.json();responses.append({'registered_case':case,'http_status':response.status,'result':result})
            page.wait_for_function("!document.querySelector('#json').disabled",timeout=30000)
            page.screenshot(path=str(out/f'{method}-full.png'),full_page=True)
            page.click('#close');page.screenshot(path=str(out/f'{method}-door.png'),full_page=True)
            with page.expect_download() as downloaded:page.click('#json')
            downloaded.value.save_as(str(out/f'{method}-export.json'))
            assert json.loads((out/f'{method}-export.json').read_text(encoding='utf-8'))['run_id']==result['run_id']
        marker=page.locator('svg text').filter(has_text='★').first
        marker.click();assert '6897145227' in page.locator('#evidence').inner_text()
        report={'actual_browser':'Microsoft Edge via Playwright','responses':responses,'requests':requests,'page_errors':errors,
                'stale_result_cleared':True,'json_download_verified':True,'map_object_evidence_clicked':True,
                'remote_requests_allowed':False,'claims':'Actual browser requests; user and field acceptance pending'}
        (out/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()
    print(json.dumps({'cases':[r['registered_case'] for r in responses],'statuses':[r['result']['status'] for r in responses],'page_errors':errors},ensure_ascii=False))
if __name__=='__main__':main()
