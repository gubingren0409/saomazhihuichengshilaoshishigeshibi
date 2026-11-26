"""Actual APP whole/near controls, no injected route and no solver request."""
from pathlib import Path
import argparse,asyncio,hashlib,json,time
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]

async def audit(url):
    posts=[];errors=[];tick=time.perf_counter()
    async with async_playwright()as pw:
        browser=await pw.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True,
            args=['--disable-gpu','--disable-extensions','--renderer-process-limit=1'])
        try:
            page=await browser.new_page(viewport={'width':1480,'height':1040})
            page.on('request',lambda r:posts.append(r.post_data_json)if r.url.endswith('/api/plan')else None)
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(url,wait_until='domcontentloaded',timeout=60000)
            await page.wait_for_function('mapReady && !mapLoading && !!document.querySelector("#start").value',timeout=180000)
            print('REAL_MAP_READY',flush=True)
            ready=await page.evaluate('({scene:data.scene_id,source:data.source_info,paths:document.querySelectorAll("#svg path").length,start:document.querySelector("#start").value,door:document.querySelector("#door").value,routeCount:route.length,last:last})')
            await page.click('#full');whole=await page.locator('#svg').get_attribute('viewBox')
            await page.click('#close');near=await page.locator('#svg').get_attribute('viewBox')
            await page.screenshot(path=str(ROOT/'audits/independent_ui_close_view.png'),full_page=True)
            await page.click('#full');again=await page.locator('#svg').get_attribute('viewBox')
            a,b=[float(x)for x in whole.split()],[float(x)for x in near.split()]
            checks={'genuine_map_and_start_loaded':ready['paths']>20 and bool(ready['start']),
                'no_route_answer_injected':ready['last']is None and ready['routeCount']==0,
                'whole_to_near_changes_viewbox':whole!=near,'near_has_smaller_extent':b[2]<a[2]and b[3]<a[3],
                'whole_restores_previous_viewbox':whole==again,'zero_solver_POSTs':not posts,'no_page_errors':not errors}
        finally:await browser.close()
    result={'reviewer':'/root/face_review','role':'ACTUAL_APP_WHOLE_NEAR_VIEW_BUTTONS','url':url,'ready':ready,
        'whole_viewBox':whole,'near_viewBox':near,'whole_again_viewBox':again,'checks':checks,'APP_solver_calls':0,
        'API_plan_POST_count':len(posts),'page_errors':errors,'elapsed_s':time.perf_counter()-tick,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'status':'PASS'if all(checks.values())else'REQUIRES_INSPECTION'}
    (ROOT/'audits/independent_view_controls.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'APP_solver_calls':0,'elapsed_s':result['elapsed_s']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);a=p.parse_args();asyncio.run(audit(a.url))
