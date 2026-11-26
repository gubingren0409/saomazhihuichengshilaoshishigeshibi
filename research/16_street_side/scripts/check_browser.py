"""Author UI checks against actual local page; never calls any route solver."""
import datetime
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def main():
    out={'role':'root author UI check; separate from independent technical review',
         'at':datetime.datetime.now().astimezone().isoformat(),'checks':[],
         'page_errors':[],'external_requests_blocked':[],'new_solver_calls':0}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True, channel='chrome')
        page=browser.new_page(viewport={'width':1700,'height':1120},accept_downloads=True)
        page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
        def route(req):
            if req.request.url.startswith(('http://127.0.0.1:53511/','file:','blob:','data:')):
                req.continue_()
            else:
                out['external_requests_blocked'].append(req.request.url)
                req.abort()
        page.route('**/*',route)
        page.goto('http://127.0.0.1:53511/',wait_until='networkidle')
        page.wait_for_selector('#map-R0 path')
        for index,window in enumerate(['native','tagged','missing']):
            page.select_option('#window',index=index)
            values=page.locator('#query option').evaluate_all('(a)=>a.map(x=>x.value)')
            assert len(values)==2
            for value in values:
                page.select_option('#query',value)
                counts={v:page.locator('#map-'+v+' path').count() for v in ['R0','R1','R2']}
                assert all(n>0 for n in counts.values()),counts
                out['checks'].append({'window':window,'query':value,'svg_paths':counts,
                                      'summaries':{v:page.locator('#summary-'+v).inner_text() for v in counts}})
        # Repeated interaction must retain source maps, queries and real result objects.
        page.locator('#layers input').first.uncheck()
        page.locator('#layers input').first.check()
        page.locator('#show-route').uncheck();page.locator('#show-route').check()
        page.locator('#map-R2 path[opacity=".85"]').first.dispatch_event('click')
        evidence=json.loads(page.locator('#evidence').inner_text())
        assert evidence.get('source_id') or evidence.get('edge_id'),evidence
        out['object_click']=evidence
        oldview=page.locator('#map-R0').get_attribute('viewBox')
        page.locator('#map-R0').hover();page.mouse.wheel(0,-250)
        assert page.locator('#map-R0').get_attribute('viewBox')!=oldview
        assert len({page.locator('#map-'+v).get_attribute('viewBox') for v in ['R0','R1','R2']})==1
        page.click('#reset')
        with page.expect_download() as d:
            page.click('#export')
        target=ROOT/'audit/browser_export_request.json';d.value.save_as(str(target))
        out['request_export_fields']=list(json.loads(target.read_text()))
        with page.expect_download() as d:
            page.click('#evidence-export')
        d.value.save_as(str(ROOT/'audit/browser_export_evidence.json'))
        page.screenshot(path=str(ROOT/'reviews/author_browser_actual.png'),full_page=False)
        # File-open path must work offline, including SVG initialization.
        page.goto((ROOT/'index.html').as_uri(),wait_until='load')
        page.wait_for_selector('#map-R2 path')
        out['offline_file_open']='PASS'
        out['all_six_query_switches']='PASS'
        out['layers_pan_zoom_object_export']='PASS'
        browser.close()
    out['status']='PASS' if not out['page_errors'] else 'FAIL'
    (ROOT/'reviews/author_browser_check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':out['status'],'checks':len(out['checks']),
                      'page_errors':out['page_errors'],'external_requests_blocked':len(out['external_requests_blocked'])}))

if __name__=='__main__':main()
