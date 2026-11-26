"""Actual Edge/Playwright APP interaction audit, no route-result substitution.

Default is GET/loading checks only. --solve issues two compare POSTs, one fresh
single and one delayed-result POST, pre-authorized in the solver budget.
The controlled HTTP503 is a UI transport fault only. No simulated solver or
historical route response is supplied to the page.
"""
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import argparse,asyncio,json,time
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]

def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

async def audit(url,solve):
    checks=[];responses=[];errors=[];capture=[];first=asyncio.Event();first_release=asyncio.Event();scene_fetches=0;fail_next=False
    delay_scene=None;scene_held=asyncio.Event();scene_release=asyncio.Event()
    delay_plan=False;plan_held=asyncio.Event();plan_release=asyncio.Event()
    def record(name,passed,detail=None):checks.append({'name':name,'passed':bool(passed),'detail':detail})
    async with async_playwright()as pw:
        browser=await pw.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True,
            args=['--disable-gpu','--disable-extensions','--renderer-process-limit=1'])
        context=await browser.new_context(viewport={'width':1480,'height':1040},accept_downloads=True)
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        async def scene_handler(route):
            nonlocal scene_fetches,fail_next
            scene_fetches+=1
            if fail_next:
                fail_next=False;await route.fulfill(status=503,content_type='application/json',body='{"error":"INDEPENDENT_CONTROLLED_TRANSPORT_FAULT"}');return
            r=await route.fetch(timeout=120000)
            if scene_fetches==1:first.set();await first_release.wait()
            scene_id=parse_qs(urlparse(route.request.url).query).get('scene_id',[''])[0]
            if scene_id==delay_scene:scene_held.set();await scene_release.wait()
            await route.fulfill(response=r)
        await page.route('**/api/scene?**',scene_handler)
        async def plan_handler(route):
            nonlocal delay_plan
            if not delay_plan:await route.continue_();return
            delay_plan=False;r=await route.fetch(timeout=240000);plan_held.set();await plan_release.wait();await route.fulfill(response=r)
        await page.route('**/api/plan',plan_handler)
        async def plan_response(response):
            if response.url.endswith('/api/plan')and response.request.method=='POST':
                body=await response.json();responses.append({'request':response.request.post_data_json,'body':body})
        page.on('response',plan_response)
        await page.goto(url,wait_until='domcontentloaded',timeout=60000)
        await asyncio.wait_for(first.wait(),120)
        await page.select_option('#method','F0');await page.select_option('#purpose','ENTER_BUILDING');await page.select_option('#area-mode','FULL_FACE')
        first_release.set()
        await page.wait_for_function('mapReady && !mapLoading',timeout=120000)
        loaded=await page.evaluate('({paths:document.querySelectorAll("#svg path").length, starts:document.querySelectorAll("#start option").length,start:document.querySelector("#start").value,ready:mapReady,loading:mapLoading})')
        record('COLD_LOADING_METHOD_PURPOSE_AREA_CHANGE_KEEP_MAP_AND_START',loaded['ready']and not loaded['loading']and loaded['paths']>20 and bool(loaded['start']),loaded)
        await page.select_option('#purpose','APPROACH_OUTSIDE')
        fail_next=True
        await page.evaluate('loadScene()')
        failed=await page.evaluate('({ready:mapReady,loading:mapLoading,notice:document.querySelector("#map-notice-text").textContent,retryVisible:!document.querySelector("#retry-map").hidden})')
        record('HTTP503_NOT_STUCK_LOADING_RETRY_VISIBLE',not failed['ready']and not failed['loading']and failed['retryVisible'],failed)
        await page.click('#retry-map');await page.wait_for_function('mapReady && !mapLoading',timeout=120000)
        record('HTTP503_RETRY_FETCHES_REAL_MAP',await page.locator('#svg path').count()>20)
        original=await page.locator('#scene').input_value()
        alternatives=await page.locator('#scene option').evaluate_all('(xs)=>xs.map(x=>x.value)')
        other='sh-library'if'sh-library'in alternatives and original!='sh-library'else next(s for s in alternatives if s!=original)
        delay_scene=other
        await page.select_option('#scene',other);await asyncio.wait_for(scene_held.wait(),120)
        await page.select_option('#scene',original)
        await page.wait_for_function('(id)=>mapReady && !mapLoading && data.scene_id===id',arg=original,timeout=120000)
        scene_release.set();await asyncio.sleep(.5)
        race=await page.evaluate('({selected:document.querySelector("#scene").value,loaded:data.scene_id,paths:document.querySelectorAll("#svg path").length,start:document.querySelector("#start").value})')
        record('REAL_OUT_OF_ORDER_SCENE_RESPONSE_CANNOT_OVERWRITE_NEW_SCENE',race['selected']==original and race['loaded']==original and race['paths']>20 and bool(race['start']),race)
        delay_scene=None
        await page.screenshot(path=str(ROOT/'audits/independent_ui_map_ready.png'),full_page=True)
        if solve:
            initial=json.loads((ROOT/'runs/initial_app_pair/EDGE_BAND.json').read_text(encoding='utf-8'))['input']
            if await page.locator('#scene').input_value()!=initial['scene_id']:
                await page.select_option('#scene',initial['scene_id']);await page.wait_for_function('mapReady && !mapLoading',timeout=120000)
            if await page.locator('#door').input_value()!=initial['door_id']:
                await page.select_option('#door',initial['door_id']);await page.wait_for_function('mapReady && !mapLoading',timeout=120000)
            await page.select_option('#start',initial['start_id']);await page.select_option('#purpose','APPROACH_OUTSIDE')
            await page.select_option('#method','F0');await page.select_option('#area-mode','FULL_FACE')
            await page.click('#compare');await page.wait_for_function('!planning && comparison && comparison.results.length===2',timeout=240000)
            await asyncio.sleep(.1)
            compared=await page.evaluate('({results:comparison.results.map(r=>({mode:r.area_routing,run_id:r.run_id,solver:r.solver,request:r.input,status:r.status,length:r.route?.length_m})),faceCount:faceLayers.length,portals:portals.length,paths:document.querySelectorAll("#svg path").length,holes:faceLayers.map(f=>f.omega.coordinates?.length),evenodd:Array.from(document.querySelectorAll("#svg path")).filter(x=>x.getAttribute("fill-rule")==="evenodd").length})')
            rs=compared['results'];record('COMPARE_SENDS_TWO_NEW_ACTUAL_SOLVER_REQUESTS',len(rs)==2 and all(r['solver'].get('invoked')for r in rs)and len({r['run_id']for r in rs})==2 and{r['mode']for r in rs}=={'EDGE_BAND','FULL_FACE'},compared)
            record('REAL_FACE_AND_PORTAL_LAYERS_POPULATED',compared['faceCount']>=2 and compared['portals']>2 and compared['evenodd']>2)
            await page.check('#show-band');await page.check('#show-portals');await page.click('#face-view')
            await page.screenshot(path=str(ROOT/'audits/independent_ui_compare_face.png'),full_page=True)
            portal=page.locator('#svg circle[fill="#376d4e"]').first
            await portal.click(force=True)
            record('ACTUAL_PORTAL_CLICK_SHOWS_SOURCE_EVIDENCE','source_area_id'in await page.locator('#evidence').inner_text())
            for button,filename in[('#json','independent_ui_comparison.json'),('#geojson','independent_ui_comparison.geojson')]:
                async with page.expect_download()as info:await page.click(button)
                download=await info.value;destination=ROOT/'audits'/filename;await download.save_as(str(destination))
                saved=json.loads(destination.read_text(encoding='utf-8'));record('ACTUAL_EXPORT_'+filename,bool(saved))
            options=await page.locator('#start option').evaluate_all('(xs)=>xs.map(x=>x.value).filter(Boolean)')
            another=next((s for s in options if s!=initial['start_id']),initial['start_id'])
            await page.select_option('#start',another);await page.select_option('#method','F1');await page.select_option('#area-mode','FULL_FACE')
            await page.click('#compute');await page.wait_for_function('!planning && last && !comparison',timeout=240000)
            single=await page.evaluate('({run_id:last.run_id,solver:last.solver,request:last.input,status:last.status,request_id:last.request_id})')
            record('FRESH_SINGLE_REQUEST_USES_CURRENT_CONTROLS',single['solver'].get('invoked')and single['request']['start_id']==another and single['request']['method']=='F1'and single['request']['area_routing']=='FULL_FACE',single)
            delay_plan=True
            await page.click('#compute');await asyncio.wait_for(plan_held.wait(),240)
            await page.select_option('#method','F0');await page.select_option('#area-mode','EDGE_BAND')
            plan_release.set();await page.wait_for_function('!planning',timeout=30000);await asyncio.sleep(.1)
            late=await page.evaluate('({last:last,comparison:comparison,routeCount:route.length,method:document.querySelector("#method").value,mode:document.querySelector("#area-mode").value,status:document.querySelector("#status").textContent})')
            record('REAL_OLD_SOLVER_RESPONSE_CANNOT_OVERWRITE_CHANGED_METHOD_AND_AREA',late['last']is None and late['comparison']is None and late['routeCount']==0 and late['method']=='F0'and late['mode']=='EDGE_BAND',late)
        record('NO_BROWSER_PAGE_ERRORS',not errors,errors)
        await context.close();await browser.close()
    result={'reviewer':'/root/face_review','role':'ACTUAL_EDGE_UI_INTERACTION','url':url,'checks':checks,'page_errors':errors,
        'actual_plan_POST_count':len(responses),'actual_solver_invocations':sum(r['body'].get('solver',{}).get('invoked',False)for r in responses),
        'actual_solver_records':[{'request':r['request'],'run_id':r['body'].get('run_id'),'solver':r['body'].get('solver'),'status':r['body'].get('status')}for r in responses],
        'transport_fault':'One injected HTTP503 for map GET only; delayed old scene and old solver responses passed through byte-for-byte from real backend',
        'status':'PASS'if all(c['passed']for c in checks)else'REQUIRES_INSPECTION',
        'limitations':['Technical UI interaction, not user aesthetic judgment or field passage verification']}
    write(ROOT/'audits/independent_ui_interaction.json',result)
    print(json.dumps({'status':result['status'],'checks':len(checks),'solver_calls':result['actual_solver_invocations']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--solve',action='store_true');a=p.parse_args();asyncio.run(audit(a.url,a.solve))
