"""Author UI acceptance for actual target presence, frozen scope and exports; no solver."""
from pathlib import Path
import datetime,json
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
def main():
    scene=json.loads((ROOT/'data/scene.json').read_text());out={'role':'root author browser check','at':datetime.datetime.now().astimezone().isoformat(),'views':[],'errors':[],'external_requests':[],'solver_calls_added':0}
    with sync_playwright()as pw:
        b=pw.chromium.launch(channel='chrome',headless=True);p=b.new_page(viewport={'width':1740,'height':1240},accept_downloads=True)
        p.on('pageerror',lambda e:out['errors'].append(str(e)))
        def intercept(route):
            if route.request.url.startswith(('http://127.0.0.1:53531/','file:','blob:','data:')):route.continue_()
            else:out['external_requests'].append(route.request.url);route.abort()
        p.route('**/*',intercept);p.goto('http://127.0.0.1:53531/',wait_until='domcontentloaded');p.wait_for_selector('#map-context .target-outline')
        assert p.evaluate('window.RECON_MAP_DIAGNOSTICS.view_id')=='target_overview'
        target_box=p.locator('#map-context .target-outline').bounding_box()
        assert target_box and target_box['y']>=0 and target_box['y']+target_box['height']<=1240,target_box
        out['first_screen_target_box']=target_box
        for view in scene['views']:
            p.select_option('#view',view['id'])
            for qi in range(2):
                p.select_option('#query',index=qi);d=p.evaluate('window.RECON_MAP_DIAGNOSTICS')
                assert d['target_building_id']=='way/161090899'and d['target_visible']and d['target_fully_inside']and all(d['doors_visible'].values())
                assert d['base_sets_equal']and len({a['base_map_sha256']for a in d['panels']})==1
                assert len({a['viewport_sha256']for a in d['panels']})==1
                for panel in ['context','R0','R1','R2']:
                    assert p.locator('#map-'+panel+' .target-outline[data-source-id="way/161090899"]').count()==1
                    assert p.locator('#map-'+panel+' .target-marker[data-door-role="exit"]').count()==1
                out['views'].append(d)
        p.select_option('#view','target_overview');p.locator('#map-context .target-outline').dispatch_event('click')
        selected=p.evaluate('window.RECON_MAP_SELECTION');assert selected['OSM_type_id']=='way/161090899'
        p.locator('#map-context .target-marker[data-door-id="node/6897145227"]').dispatch_event('click')
        selected=p.evaluate('window.RECON_MAP_SELECTION');assert selected['tags']['entrance']=='exit'and selected['coordinates_moved']is False
        with p.expect_download()as x:p.click('#export-evidence')
        x.value.save_as(str(ROOT/'audits/author_exit_evidence.json'))
        with p.expect_download()as x:p.click('#export')
        x.value.save_as(str(ROOT/'audits/author_view_export.json'))
        with p.expect_download()as x:p.click('#export-svg')
        x.value.save_as(str(ROOT/'audits/author_export.svg'));ET.parse(ROOT/'audits/author_export.svg')
        p.click('#layer-controls-toggle')
        p.locator('#layers input[data-layer="R2"]').uncheck();assert p.evaluate('window.RECON_MAP_DIAGNOSTICS.target_visible')
        p.locator('#layers input[data-layer="R2"]').check()
        for value in p.locator('#history option').evaluate_all('(a)=>a.map(x=>x.value)'):
            p.select_option('#history',value);assert p.evaluate('window.RECON_MAP_DIAGNOSTICS.target_building_id')=='way/161090899'
        p.select_option('#view','target_overview');p.evaluate('window.scrollTo(0,0)');p.screenshot(path=str(ROOT/'audits/author_browser_target.png'),full_page=False)
        p.goto((ROOT/'web/index.html').as_uri(),wait_until='domcontentloaded');p.wait_for_selector('#map-context .target-outline')
        assert p.evaluate('window.RECON_MAP_DIAGNOSTICS.view_id')=='target_overview'
        out['offline_open']='PASS';b.close()
    out['status']='PASS'if not out['errors']and not out['external_requests']else'FAIL'
    (ROOT/'audits/author_browser.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':out['status'],'tested_views':len(out['views']),'errors':out['errors'],'external_requests':out['external_requests']}))
if __name__=='__main__':main()
