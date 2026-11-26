"""Actual independent Edge rendering and controls, with no external/solver requests."""
from pathlib import Path
import json,hashlib,datetime,argparse
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:53451/');ap.add_argument('--output-prefix',default='independent_browser');a=ap.parse_args();outdir=ROOT/'audits'/a.output_prefix;outdir.mkdir(parents=True,exist_ok=True);errors=[];blocked=[];requests=[];rows=[];downloads=[]
    print('INDEPENDENT_BROWSER_START',datetime.datetime.now().astimezone().isoformat(),flush=True)
    with sync_playwright()as p:
        print('PLAYWRIGHT_DRIVER_READY',flush=True);browser=p.chromium.launch(channel='msedge',headless=True,timeout=30000);ctx=browser.new_context(viewport={'width':1520,'height':1100},accept_downloads=True);print('EDGE_CONTEXT_READY',flush=True)
        def route_handler(route):
            u=urlsplit(route.request.url)
            if u.scheme not in('file','data','blob')and not(u.scheme in('http','https')and u.hostname in('127.0.0.1','localhost')):blocked.append(route.request.url);route.abort()
            else:route.continue_()
        ctx.route('**/*',route_handler);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append({'method':r.method,'url':r.url}));response=page.goto(a.url,wait_until='load');page.wait_for_function('window.R2_VIEW_DATA && document.querySelectorAll(".card").length===4 && document.querySelector("#map").children.length>10',timeout=45000)
        default_interfaces=page.locator('#interfaces').is_checked()
        for i,case in enumerate(('south','north_near','north_far','library')):
            print('CASE_START',case,flush=True);page.locator('.card').nth(i).click();page.locator('#mode').select_option('B3');page.locator('#method').select_option('F0');page.locator('#fit').click();case_rows=[]
            for mode in('B0','B1','B2','B3'):
                for method in('F0','F1'):
                    page.locator('#mode').select_option(mode);page.locator('#method').select_option(method);summary=page.locator('#summary').inner_text();assert f'{mode} / {method}'in summary;assert page.locator('#map>*').count()>10
                    case_rows.append({'mode':mode,'method':method,'SVG_children':page.locator('#map>*').count(),'summary':summary})
            page.locator('#mode').select_option('B3');page.locator('#method').select_option('F0');page.locator('#corridor').select_option('20');page.locator('#door').click();assert page.locator('#map>*').count()>10;page.locator('#fit').click();page.locator('#interfaceFilter').fill('TIED_EQUIVALENT'if case!='library'else'D_EXISTING_ROUTE_STRICTLY_CHEAPER')
            page.locator('#interfaceTable tbody tr').first.click();selected=json.loads(page.locator('#selected').inner_text());assert selected.get('id')and selected.get('current_display_mode')=='B3';assert 'current_mode_membership'in selected
            page.locator('#interfaceFilter').fill('');page.locator('#interfaces').check();assert page.locator('#map>*').count()>10;page.locator('#interfaces').uncheck();page.locator('#fit').click();page.locator('#corridor').select_option('10');shot=outdir/(case+'.png');page.locator('#map').screenshot(path=str(shot))
            cf=page.locator('#counterfactual').inner_text();assert cf.strip()not in('{}','[]',''),'EMPTY_COUNTERFACTUAL_UI'
            with page.expect_download()as download:page.locator('#save').click()
            dest=outdir/(case+'_view.json');download.value.save_as(str(dest));downloadbody=json.loads(dest.read_text());assert downloadbody['case']==case and downloadbody['not_new_solver_request']is True;downloads.append({'case':case,'file':str(dest.relative_to(ROOT)),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
            rows.append({'case':case,'combinations':case_rows,'selected_interface':selected['id'],'counterfactual_text_chars':len(cf),'screenshot':str(shot.relative_to(ROOT)),'screenshot_sha256':hashlib.sha256(shot.read_bytes()).hexdigest()});print('CASE_DONE',case,flush=True)
        # Same exact self-contained page must initialize directly from disk too.
        page.goto((ROOT/'visuals/index.html').as_uri(),wait_until='load');page.wait_for_function('window.R2_VIEW_DATA && document.querySelector("#map").children.length>10',timeout=45000);offline={'url':page.url,'SVG_children':page.locator('#map>*').count(),'status':page.locator('#status').inner_text()};browser.close()
    result={'reviewer':'/root/r2_independent','actual_browser':'Microsoft Edge headless via Playwright; new separate browser context','at':datetime.datetime.now().astimezone().isoformat(),'HTML_sha256':hashlib.sha256((ROOT/'visuals/index.html').read_bytes()).hexdigest(),'status':'PASS_FOR_ACTUAL_INTERACTIVE_AND_OFFLINE_RENDER'if not errors and not blocked and all(r['method']=='GET'for r in requests)else'REQUIRES_INSPECTION','HTTP_status':response.status if response else None,'default_interfaces_checked':default_interfaces,'rows':rows,'combinations':sum(len(r['combinations'])for r in rows),'downloads':downloads,'offline_file':offline,'JS_errors':errors,'blocked_external_requests':blocked,'requests':requests,'new_solver_calls':0,'new_SSSP_calls':0,'user_observation':'PENDING_USER_OBSERVATION','scope':'32 saved-route mode/method combinations, same-data map, view buttons/corridor/layer switches, real interface selection, four actual JSON downloads, offline file load. This viewer is deliberately read-only diagnosis, not new route solver UI and not user visual acceptance.'}
    (ROOT/'audits'/(a.output_prefix+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':result['status'],'combinations':result['combinations'],'JS_errors':errors,'blocked_external_requests':blocked,'requests':len(requests)}))
if __name__=='__main__':main()
