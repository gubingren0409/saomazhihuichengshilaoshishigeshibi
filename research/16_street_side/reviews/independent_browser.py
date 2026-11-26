"""Independent real browser check; local read-only viewer, no route requests."""
import datetime, hashlib, json, pathlib
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
errors=[];external=[];requests=[];checked=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1500,'height':1100},accept_downloads=True)
    context.route('**/*',lambda route:route.continue_()if route.request.url.startswith(('http://127.0.0.1:53511/','data:','blob:'))else(external.append(route.request.url),route.abort())[-1])
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append({'method':r.method,'url':r.url}))
    response=page.goto('http://127.0.0.1:53511/',wait_until='networkidle',timeout=30000)
    if response.status!=200:errors.append('HTTP:'+str(response.status))
    page.wait_for_function('window.STREET_VIEWER && document.querySelector("#map-R0 path")')
    for w in range(3):
        page.select_option('#window',str(w))
        for q in range(2):
            page.select_option('#query',str(q))
            item=page.evaluate('''() => ({state:window.STREET_VIEWER.getState(), error:document.querySelector('#error').textContent, svgPaths:['R0','R1','R2'].map(x=>document.querySelectorAll('#map-'+x+' path').length), result:document.querySelector('#request').textContent})''')
            checked.append(item)
            if item['error']or any(n==0 for n in item['svgPaths']):errors.append('empty/error view:'+str((w,q)))
    page.select_option('#window','2');page.select_option('#query','0')
    # Actual pointer click on visible source geometry, rather than direct handler calls.
    selected=False
    rect=page.locator('#map-R0').bounding_box()
    for locator in page.locator('#map-R0 path').all():
        box=locator.bounding_box()
        if not box:continue
        x=box['x']+box['width']/2;y=box['y']+box['height']/2
        if rect['x']+2<x<rect['x']+rect['width']-2 and rect['y']+2<y<rect['y']+rect['height']-2:
            page.mouse.click(x,y)
            try:
                value=json.loads(page.locator('#evidence').inner_text())
                if value.get('source_id')or value.get('identity')not in {None}:selected=True;break
            except json.JSONDecodeError:pass
    if not selected:errors.append('source object actual pointer click not verified')
    with page.expect_download() as download:
        page.locator('#export').click()
    downloaded=ROOT/'reviews/independent_browser_export.json';download.value.save_as(downloaded)
    export=json.loads(downloaded.read_text(encoding='utf-8'))
    if export.get('identity')!='SAVED_FORMAL_QUERY_DISPLAY_NO_NEW_SOLVER_CALL'or not export.get('source_sha256'):errors.append('request/view export identity missing')
    page.screenshot(path=str(ROOT/'reviews/independent_browser.png'),full_page=True)
    title=page.title();body=page.locator('body').inner_text()
    browser.close()
report={'reviewer':'/root/resume_review','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS_LOCAL_READONLY_INTERACTIVE_VIEWER'if not errors else'FAIL','page_title':title,'six_saved_query_views_checked':len(checked),'checks':checked,'source_object_pointer_click_verified':selected,'actual_export_path':str(downloaded),'actual_export_sha256':hashlib.sha256(downloaded.read_bytes()).hexdigest(),'page_bindings':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ['index.html','maps/viewer.js','maps/viewer.css','maps/trial_map_data.json']},'requests':requests,'external_requests_attempted_and_blocked':external,'errors':errors,'new_solver_calls':0,'new_network_map_api_requests':0,'browser_closed':True,'scope':'Separate actual headless installedChrome browser, six saved-query views, real object pointer click, actual JSON download. GET local assets only; does not verify real-world geometry or new interactive route calculation.'}
(ROOT/'reviews/independent_browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'views':len(checked),'requests':len(requests),'errors':errors,'external':external},ensure_ascii=False))
raise SystemExit(0 if not errors else 1)
