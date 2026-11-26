"""Own temporary server + actual Edge. Local GET only; no author browser code."""
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Thread
from datetime import datetime,timezone
import argparse,hashlib,json,sys
from playwright.sync_api import sync_playwright

DEFAULT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=DEFAULT);ap.add_argument('--output',type=Path,default=DEFAULT/'reviews/browser');args=ap.parse_args()
ROOT=args.root;OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
receipt={'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'actual Edge browser, all six map scenes, local GET-only server; source-code-independent UI checks','phase1':[],'phase2':[],'requests':[],'page_errors':[],'server_stopped':False,'browser_stopped':False,'new_solver_calls':0}
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
thread=Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
receipt['temporary_local_port']=server.server_port
try:
    with sync_playwright() as p:
        print('PLAYWRIGHT_READY',flush=True)
        browser=p.chromium.launch(channel='msedge',headless=True,timeout=30000)
        ctx=browser.new_context(viewport={'width':1520,'height':1100},accept_downloads=True)
        def network(route):
            request=route.request;good=request.method=='GET' and request.url.startswith(base+'/')
            receipt['requests'].append({'method':request.method,'url':request.url,'allowed':good})
            if good:route.continue_()
            else:route.abort()
        ctx.route('**/*',network);page=ctx.new_page();page.on('pageerror',lambda e:receipt['page_errors'].append(str(e)))
        page.goto(base+'/index.html',wait_until='networkidle',timeout=60000)
        assert page.locator('a[href*="phase1"]').count()>0 and page.locator('a[href*="phase2"]').count()>0
        page.screenshot(path=str(OUT/'foundation-overview.png'),full_page=True)
        receipt['overview_html_sha256']=hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest()
        page.goto(base+'/phase1/index.html',wait_until='networkidle',timeout=60000)
        page.wait_for_function("document.querySelectorAll('#scene option').length===6 && window.__PG1MapReviewState?.().features>0",timeout=60000)
        scenes=page.locator('#scene option').evaluate_all('(els)=>els.map(x=>x.value)')
        for sid in scenes:
            page.select_option('#scene',sid)
            page.wait_for_function('(sid)=>window.__PG1MapReviewState?.().scene_id===sid && !document.querySelector("#scene-note").textContent.includes("加载")',arg=sid,timeout=60000)
            page.wait_for_timeout(400)
            counts={name:page.locator('#'+name+' .feature').count()for name in ['raw','import','graph','legacy']}
            assert all(n>0 for n in counts.values())
            illegal_line_fills=page.locator('svg path.feature').evaluate_all("els=>els.filter(e=>!/[Zz]/.test(e.getAttribute('d')||'') && e.getAttribute('fill')!=='none').length")
            assert illegal_line_fills==0,'LINESTRING_IMPLICIT_POLYGON_FILL'
            assert len({page.locator('#'+name).get_attribute('viewBox')for name in counts})==1
            state=page.evaluate('window.__PG1MapReviewState()');assert state['solver_invoked_this_audit']is False
            # Drawn objects may extend beyond the SVG viewBox; select an actual
            # visible road-name label rather than an offscreen object's bbox.
            page.locator('#raw').evaluate("svg=>{const n=[...svg.querySelectorAll('text')].find(n=>typeof n.onclick==='function');if(!n)throw Error('NO_CLICKABLE_ROAD_LABEL');n.setAttribute('data-independent-click','true')}")
            page.locator('#raw [data-independent-click]').click(force=True)
            assert page.locator('#object').inner_text().find('source_id')>=0
            state=page.evaluate('window.__PG1MapReviewState()')
            before=page.locator('#raw .feature').count();toggle=page.locator('#layers label').filter(has_text='建筑').locator('input');toggle.uncheck();page.wait_for_timeout(200);after=page.locator('#raw .feature').count();assert after<before;toggle.check();page.wait_for_timeout(200)
            page.screenshot(path=str(OUT/(sid+'-block.png')),full_page=True)
            blockbox=page.locator('#raw').get_attribute('viewBox');page.click('#detail');page.wait_for_timeout(200);assert page.locator('#raw').get_attribute('viewBox')!=blockbox
            page.screenshot(path=str(OUT/(sid+'-detail.png')),full_page=True)
            page.click('#full');page.wait_for_timeout(200);assert page.locator('#raw .feature').count()>=before
            graph=json.loads((ROOT/'phase1/data'/sid/'current_graph.json').read_text(encoding='utf8'))
            graph_clicks=[]
            graph_click_attempts=[]
            page.locator('#graph').scroll_into_view_if_needed()
            for key in ['interfaces','seams']:
                candidates=[]
                for record in graph[key]:
                    geom=record.get('geometry',{})
                    if geom.get('type')=='Point':xy=geom['coordinates']
                    elif geom.get('type')=='LineString':
                        a,b=geom['coordinates'][0],geom['coordinates'][-1]
                        if a==b:continue
                        xy=[(a[0]+b[0])/2,(a[1]+b[1])/2]
                    else:continue
                    candidates.append({'id':record['id'],'xy':xy})
                if not candidates:continue
                points=page.locator('#graph').evaluate("(svg,items)=>{const b=svg.getBoundingClientRect();return items.map(r=>{const p=svg.createSVGPoint();p.x=r.xy[0];p.y=-r.xy[1];const q=p.matrixTransform(svg.getScreenCTM());return {id:r.id,x:q.x,y:q.y}}).filter(q=>q.x>b.left+10&&q.x<b.right-10&&q.y>b.top+10&&q.y<b.bottom-10)}",candidates)
                for point in points[:30]:
                    page.mouse.click(point['x'],point['y']);page.wait_for_timeout(30)
                    selected=page.evaluate('window.__PG1MapReviewState().selected_id')
                    graph_click_attempts.append({'layer':key,'target':point['id'],'selected':selected})
                    # Several source-supported interfaces can occupy one exact
                    # point; accept the actually selected member of this layer.
                    if selected in {r['id']for r in graph[key]}:graph_clicks.append({'layer':key,'id':selected});break
                if points:assert any(r['layer']==key for r in graph_clicks),'CURRENT_GRAPH_OBJECT_CLICK_FAILED'
            page.fill('#review-text','Independent browser mechanics check; user visual acceptance remains pending.')
            with page.expect_download() as event:page.click('#export-review')
            download=event.value;dest=OUT/(sid+'-request.json');download.save_as(str(dest));record=json.loads(dest.read_text(encoding='utf8'))
            assert record['scene_id']==sid and record['solver_invoked_this_audit']is False and record['acceptance']=='PENDING_USER_DECISION'
            receipt['phase1'].append({'scene_id':sid,'render_primitive_counts_block':counts,'primitive_count_is_not_source_object_denominator':True,'illegal_line_fills':illegal_line_fills,'layer_toggle_removed_primitives':before-after,'clicked_source_object':state.get('selected_id'),'clicked_current_graph_objects':graph_clicks,'graph_click_attempts':graph_click_attempts,'export_source_sha256':record['source_sha256'],'html_sha256':hashlib.sha256((ROOT/'phase1/index.html').read_bytes()).hexdigest(),'renderer_sha256':hashlib.sha256((ROOT/'phase1/src/map.js').read_bytes()).hexdigest()})
        page.goto(base+'/phase2/index.html',wait_until='networkidle',timeout=60000)
        receipt['candidate_html_sha256']=hashlib.sha256((ROOT/'phase2/index.html').read_bytes()).hexdigest()
        config=json.loads((ROOT/'phase2/scene_config.json').read_text(encoding='utf8'))
        for candidate in config:
            sid=candidate['scene_id'];section=page.locator('section#'+sid);assert section.count()==1
            paths=section.locator('svg path[d]').count();realpaths=section.locator('g[class^="layer-"] path').count()
            if sid=='hel_kallio':assert realpaths==0 and 'NO VERIFIED GEOMETRY'in section.inner_text()
            else:assert realpaths>0
            controls=section.locator('input[type=checkbox]')
            if controls.count() and realpaths:
                controls.first.uncheck();assert section.locator('g[class^="layer-"]').first.evaluate('(x)=>getComputedStyle(x).display')=='none';controls.first.check()
            section.screenshot(path=str(OUT/(sid+'-atlas.png')))
            receipt['phase2'].append({'scene_id':sid,'svg_paths':paths,'real_geometry_paths':realpaths,'metadata_only':sid=='hel_kallio'})
        assert not receipt['page_errors']
        assert all(r['allowed']for r in receipt['requests'])
        browser.close();receipt['browser_stopped']=True
    receipt['status']='PASS_FOR_REAL_BROWSER_GET_RENDER_INTERACTION_SCOPE'
except Exception as e:
    receipt['status']='REQUIRES_FIX';receipt['error']=repr(e)
    if 'graph_click_attempts'in locals():receipt['failed_graph_click_attempts']=graph_click_attempts
    raise
finally:
    server.shutdown();server.server_close();thread.join(timeout=5);receipt['server_stopped']=not thread.is_alive()
    (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'status':receipt['status'],'scenes':len(receipt['phase1']),'candidates':len(receipt['phase2']),'requests':len(receipt['requests']),'local_only':all(r['allowed']for r in receipt['requests']),'stopped':receipt['server_stopped']and receipt['browser_stopped']}))
