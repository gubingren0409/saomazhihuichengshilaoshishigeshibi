"""Actual file/HTTP Edge interaction tests and six small real-map exports."""
import argparse
from functools import partial
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse
from xml.etree import ElementTree

from playwright.sync_api import sync_playwright

from serve_review import ReviewHandler

ROOT=Path(__file__).resolve().parents[1]
TABS=('north','compare','risk')


def open_page(page,url,tab):
    target=url+'#'+tab
    if page.url==target:
        # A same-URL goto is not a fresh document; deliberately reload when
        # asserting the initial opt-in reference state between captures.
        page.reload(wait_until='load',timeout=60000)
    else:
        page.goto(target,wait_until='load',timeout=60000)
    page.wait_for_function('t=>window.freeReview?.tab===t',arg=tab,timeout=60000)
    assert page.locator('#right-map path').count()>0
    assert not page.locator('#ref-toggle').is_checked()
    assert page.locator('#right-map [data-layer=score-domain] path').get_attribute('fill')=='none'


def ids(page,selector):
    return page.locator(selector+' option').evaluate_all('xs=>xs.map(x=>x.value)')


def interactive(page,url):
    checks=[]
    open_page(page,url,'north')
    before=page.locator('#right-map').get_attribute('viewBox')
    for m in ids(page,'#method'):
        page.locator('#method').select_option(m)
        assert page.locator('#right-map').get_attribute('viewBox')==before
    checks.append('method_switch_preserves_fixed_local_view')
    page.locator('#zoom-in').click()
    assert page.locator('#right-map').get_attribute('viewBox')!=before
    page.locator('#reset').click()
    assert page.locator('#right-map').get_attribute('viewBox')==before
    page.locator('#right-map').click(position={'x':180,'y':180})
    assert page.locator('#left-map .link-crosshair').count() and page.locator('#right-map .link-crosshair').count()
    checks.append('linked_focus_zoom_and_reset')
    open_page(page,url,'compare')
    views=[page.locator('#'+s+'-map').get_attribute('viewBox') for s in ('left','right','third')]
    assert len(set(views))==1
    observed=[page.locator('#'+s+'-map').get_attribute('data-observed') for s in ('left','right','third')]
    assert len(set(observed))==1
    hashes=[page.locator('#'+s+'-map').get_attribute('data-state-sha256') for s in ('right','third')]
    assert hashes[0] and len(set(hashes))==1
    checks.append('three_same_view_same_input_f0_f1_same_surface')
    cell=page.locator('#right-map [data-layer=cell]').first
    if cell.count():
        cell.press('Enter')
        text=page.locator('#inspect').inner_text()
        assert 'source_evidence_state' in text and 'planning_state' in text and 'policy_id' in text
        checks.append('cell_factual_and_planning_axes')
    if not page.locator('#ref-toggle').is_disabled():
        assert not page.locator('[data-layer=reference]').count()
        page.locator('#ref-toggle').check()
        assert page.locator('[data-layer=reference][data-visibility=evaluation-only]').count()==3
        page.locator('#ref-toggle').uncheck()
        checks.append('reference_opt_in_only')
    page.locator('#region-toggle').uncheck()
    assert not page.locator('[data-layer=state-inferred]').count()
    page.locator('#region-toggle').check()
    page.locator('#interface-toggle').check()
    checks.append('region_and_interface_layer_toggles')
    if 'NORTH' in ids(page,'#case'):
        page.goto(url+'#north')
        page.locator('#case').select_option('NORTH')
        door=page.locator('#right-map [data-layer=exit]').first
        assert door.count()
        door.press('Enter')
        text=page.locator('#inspect').inner_text()
        assert '6897145227' in text and 'exit' in text and '121.4706605' in text and '31.2305674' in text
        page.locator('#full-route').click()
        assert page.locator('#left-map').get_attribute('data-extent')=='full-route'
        assert page.locator('#right-map').get_attribute('data-extent')=='local-30m'
        checks.append('original_exit_identity_and_full_route')
    open_page(page,url,'risk')
    if page.locator('#source-gap').is_visible():
        assert page.locator('#case').input_value()=='W7a6b5a10076'
        assert '128.39' in page.locator('#case-gap').inner_text()
        fixed=page.evaluate('window.freeReview.privateFixed')
        assert ('R0' if fixed else '1/25') in page.locator('#source-gap').inner_text()
        if fixed:
            assert 'V3已导入' in page.locator('#legend').inner_text()
            assert '非算法输入' not in page.locator('#legend').inner_text()
        overlay=page.locator('[data-layer=post-audit-restriction]')
        assert overlay.count()==3
        assert overlay.first.get_attribute('data-visibility')==('current-source-constraint-review' if fixed else 'post-audit-review-only')
        overlay.first.press('Enter')
        info=page.locator('#inspect').inner_text()
        assert ('SOURCE_RESTRICTION_V3_PARITY_REVIEW' if fixed else 'POST_AUDIT_SOURCE_RESTRICTION') in info and 'private' in info and 'predictor_input' in info
        old=page.locator('#right-map').get_attribute('data-state-sha256')
        page.locator('#post-audit-toggle').uncheck()
        assert page.locator('[data-layer=post-audit-restriction]').count()==0
        assert page.locator('#right-map').get_attribute('data-state-sha256')==old
        page.locator('#post-audit-toggle').check()
        checks.append('post_audit_restriction_separate_from_predictor_and_toggle_keeps_surface')
        if fixed:
            page.locator('#stage').select_option('R0')
            assert page.evaluate('window.freeReview.stage')=='R0_HISTORICAL'
            assert page.locator('#right-map').get_attribute('data-state-sha256')!=old
            assert page.locator('#right-map [data-layer=post-audit-restriction]').get_attribute('data-visibility')=='post-audit-review-only'
            page.locator('#stage').select_option('CURRENT')
            assert page.locator('#right-map').get_attribute('data-state-sha256')==old
            open_page(page,url,'privatefix')
            assert page.locator('#maps article.map:not([hidden])').count()==4
            assert page.locator('#left-map').get_attribute('data-stage')=='R0_HISTORICAL'
            assert page.locator('#third-map').get_attribute('data-state-sha256')==page.locator('#fourth-map').get_attribute('data-state-sha256')
            assert len({page.locator('#'+side+'-map').get_attribute('viewBox') for side in ('left','right','third','fourth')})==1
            checks.append('sealed_r0_switch_and_four_panel_current_fix_same_view')
    return checks


def figures(page,url,out,audit_only=False,fix_only=False):
    open_page(page,url,'north')
    available=ids(page,'#case')
    preferred=[('north','NORTH','01-north-full-route'),('compare','NORTH','02-north-three-methods'),
               ('compare','Wc4183046a70','03-library-expansion'),('compare','W2b809bbe6b8','04-new-reachability'),
               ('compare','W0caca58bc41','05-still-no-path'),('risk','W0440b97497a','06-water-and-policy')]
    audit=[('risk','W7a6b5a10076','07-private-parking-gap')]
    preferred=audit if audit_only else preferred+audit
    if fix_only:preferred=[('privatefix','W7a6b5a10076','08-private-before-after')]
    actual=[]
    for tab,task,name in preferred:
        if task not in available:
            continue
        open_page(page,url,tab)
        if page.locator('#case').input_value()!=task:
            page.locator('#case').select_option(task)
        if name=='01-north-full-route':
            page.locator('#full-route').click()
        if tab=='compare' and task!='NORTH':
            page.locator('#ref-toggle').check()
            page.locator('#expansion-toggle').check()
        page.locator('#interface-toggle').check()
        page.evaluate("document.body.classList.add('capture')")
        png=out/(name+'.png')
        page.locator('#figure').screenshot(path=png,animations='disabled',timeout=60000)
        page.evaluate("document.body.classList.remove('capture')")
        svg=out/(name+'.svg')
        with page.expect_download(timeout=30000) as ev:
            page.locator('#download').click()
        ev.value.save_as(svg)
        tree=ElementTree.parse(svg).getroot();ns={'s':'http://www.w3.org/2000/svg'}
        panes=tree.findall('s:svg',ns)
        assert len(panes)==(2 if tab=='north' else 4 if tab=='privatefix' else 3)
        assert not tree.findall('.//s:script',ns)
        if name in {'01-north-full-route','08-private-before-after'}:
            with page.expect_download(timeout=30000) as ev:
                page.locator('#download-png').click()
            exported=out/('user-export-private-fix.png' if name=='08-private-before-after' else 'user-export-north.png')
            ev.value.save_as(exported)
            assert exported.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
        actual.append({'png':png.name,'svg':svg.name,**page.evaluate('window.freeReview')})
    return actual


def main(args):
    html=args.root/'visuals/index.html';out=args.figure_output or args.root/'visuals/figures';out.mkdir(exist_ok=True,parents=True)
    errors=[];blocked=[];views=[]
    with ThreadingHTTPServer(('127.0.0.1',0),partial(ReviewHandler,directory=args.root)) as server:
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{server.server_port}/visuals/index.html'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.browser,headless=True,args=[
                    '--disable-background-networking','--disable-component-update','--no-first-run',
                    '--disable-extensions','--disable-sync','--disable-default-apps'])
                ctx=browser.new_context(viewport={'width':1560,'height':1160},device_scale_factor=1,accept_downloads=True)
                def local_only(route):
                    u=urlparse(route.request.url)
                    if u.scheme in {'file','data','blob'} or (u.scheme=='http' and u.hostname=='127.0.0.1' and u.port==server.server_port):
                        route.continue_()
                    else:
                        blocked.append(route.request.url);route.abort()
                ctx.route('**/*',local_only)
                page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                for tab in TABS:
                    open_page(page,html.resolve().as_uri(),tab);views.append('file:'+tab)
                if page.locator('#fix-nav').is_visible():
                    open_page(page,html.resolve().as_uri(),'privatefix');views.append('file:privatefix')
                checks=interactive(page,url)
                for tab in TABS:
                    open_page(page,url,tab);views.append('http:'+tab)
                if page.locator('#fix-nav').is_visible():
                    open_page(page,url,'privatefix');views.append('http:privatefix')
                exports=figures(page,url,out,args.audit_only,args.fix_only)
                version=browser.version;browser.close()
        finally:
            server.shutdown();worker.join(timeout=5)
    assert not errors and not blocked,{'errors':errors,'blocked':blocked}
    result={'status':'PASS','browser':version,'page_sha256':sha256(html.read_bytes()).hexdigest(),
            'views':views,'checks':checks,'figures':exports,'blocked_external':blocked,'page_errors':errors}
    path=args.receipt or args.root/'audits/visual_browser_check.json'
    path.parent.mkdir(exist_ok=True,parents=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--browser',default='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--audit-only',action='store_true',help='Only export the incremental post-audit seventh map; preserve six earlier verified figures')
    parser.add_argument('--fix-only',action='store_true',help='Only export the eighth R0/current repair comparison; preserve seven previous figures')
    parser.add_argument('--figure-output',type=Path,help='Separate replay exports; preserve immutable unpacked package members')
    main(parser.parse_args())
