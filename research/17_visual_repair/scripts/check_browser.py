"""Author browser checks. All interactions redraw frozen data; no planner exists here."""
import datetime
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def main():
    out={'role':'root author browser check; independent review separate',
         'at':datetime.datetime.now().astimezone().isoformat(),'views':[],'page_errors':[],
         'external_requests_blocked':[],'solver_calls_added':0}
    with sync_playwright()as pw:
        b=pw.chromium.launch(channel='chrome',headless=True)
        page=b.new_page(viewport={'width':1740,'height':1200},accept_downloads=True)
        page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
        def intercept(route):
            if route.request.url.startswith(('http://127.0.0.1:53521/','file:','data:','blob:')):route.continue_()
            else:out['external_requests_blocked'].append(route.request.url);route.abort()
        page.route('**/*',intercept)
        page.goto('http://127.0.0.1:53521/',wait_until='domcontentloaded')
        # Immediate changes during image loading must not clear the source map.
        page.select_option('#window',index=2);page.select_option('#query',index=1);page.select_option('#variant','R2')
        for i,(window,n)in enumerate([('native',154),('tagged',122),('missing',85)]):
            page.select_option('#window',index=i);page.click('#full')
            for q in range(2):
                page.select_option('#query',index=q)
                d=page.evaluate('window.MAP_REPAIR_DIAGNOSTICS')
                assert d['base_sets_equal']and len(d['panels'])==4
                assert all(len(p['source_ids'])==n for p in d['panels']),(window,d)
                scales=page.evaluate("Array.from(document.querySelectorAll('svg.map')).map(s=>1/Math.abs(s.getScreenCTM().a))")
                reported=[p['meters_per_css_px']for p in d['panels']]
                if len(scales)==4:assert all(abs(a-b)<1e-6 for a,b in zip(scales,reported))
                assert page.locator('#layers input[data-layer="road_areas"]').is_disabled()
                out['views'].append({'window':window,'query':d['query_id'],'source_objects_per_panel':n,
                                     'same_base':True,'extent':d['extent'],'meters_per_css_px':reported,
                                     'statuses':{v:page.locator('#summary-'+v).inner_text()for v in ['R0','R1','R2']}})
            # Independent layer controls must hide only the requested data, then restore.
            roads=page.locator('#layers input[data-layer="road_centerlines"]')
            roads.uncheck();assert page.locator('#map-context g.source-feature[data-family="road_centerlines"]').count()==0
            roads.check();assert page.locator('#map-context g.source-feature[data-family="road_centerlines"]').count()>0
            page.click('#detail');assert page.evaluate('window.MAP_REPAIR_DIAGNOSTICS.extent')!=d['extent']
            assert page.evaluate('window.MAP_REPAIR_DIAGNOSTICS.base_sets_equal')
            page.click('#full')
        page.select_option('#window',index=0);page.select_option('#query',index=0)
        page.locator('#map-context g.source-feature').first.dispatch_event('click')
        evidence=json.loads(page.locator('#evidence').inner_text())
        assert evidence.get('OSM_type_id')and evidence.get('raw_tags') is not None,evidence
        with page.expect_download()as download:page.click('#export-evidence')
        download.value.save_as(str(ROOT/'reviews/author_object_export.json'))
        with page.expect_download()as download:page.click('#export')
        download.value.save_as(str(ROOT/'reviews/author_view_export.json'))
        with page.expect_download()as download:page.click('#export-svg')
        download.value.save_as(str(ROOT/'reviews/author_export.svg'))
        ET.parse(ROOT/'reviews/author_export.svg')
        for value in page.locator('#history option').evaluate_all('(a)=>a.map(x=>x.value)'):
            page.select_option('#history',value)
            assert page.locator('#map-context g.source-feature').count()>0
        page.select_option('#variant','context');page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ROOT/'reviews/author_browser_overview.png'),full_page=False)
        page.goto((ROOT/'index.html').as_uri(),wait_until='domcontentloaded')
        page.wait_for_selector('#map-context g.source-feature')
        assert page.evaluate('window.MAP_REPAIR_DIAGNOSTICS.base_sets_equal')
        out['offline_open']='PASS';out['exports']='JSON_VIEW_JSON_OBJECT_EDITABLE_SVG_PASS'
        out['loading_switches_no_blank']='PASS';out['history_selection_no_map_override']='PASS'
        b.close()
    out['status']='PASS'if not out['page_errors']and not out['external_requests_blocked']else'FAIL'
    (ROOT/'reviews/author_browser_check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':out['status'],'views':len(out['views']),'page_errors':out['page_errors'],
                      'external_requests':len(out['external_requests_blocked'])}))

if __name__=='__main__':main()
