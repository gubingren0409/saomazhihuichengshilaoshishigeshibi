"""Actual read-only browser check of the final G0 exact inventory overview."""
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Thread
import argparse,csv,hashlib,json
from playwright.sync_api import sync_playwright
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--out',type=Path);args=ap.parse_args();root=args.root;out=args.out or root/'reviews/browser';out.mkdir(parents=True,exist_ok=True)
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)));thread=Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
binding=json.loads((root/'audit/ROUND_BINDING.json').read_text(encoding='utf8'));files=list(csv.DictReader((root/'audit/PUBLIC_FILE_INVENTORY.csv').open(encoding='utf-8-sig',newline='')));requests=[]
try:
    with sync_playwright()as p:
        browser=p.chromium.launch(channel='msedge',headless=True,timeout=30000);ctx=browser.new_context(viewport={'width':1520,'height':1100})
        def route(r):
            good=r.request.method=='GET'and r.request.url.startswith(base+'/');requests.append({'method':r.request.method,'url':r.request.url,'allowed':good});r.continue_()if good else r.abort()
        ctx.route('**/*',route);page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/',wait_until='networkidle',timeout=60000)
        body=page.locator('body').inner_text();assert binding['final_commit']in body
        assert all(r['path']in body for r in files)
        assert page.locator('a[href="#history"]').count()>0 and page.locator('a[href="#publication"]').count()>0
        page.screenshot(path=str(out/'foundation-overview-final.png'),full_page=True)
        page.locator('a[href="#publication"]').first.click();page.screenshot(path=str(out/'foundation-publication-final.png'))
        assert not errors and all(r['allowed']for r in requests);browser.close()
finally:server.shutdown();server.server_close();thread.join(timeout=5)
receipt={'status':'PASS_FINAL_OVERVIEW_RENDER_EXACT_INVENTORY','HTML_sha256':hashlib.sha256((root/'index.html').read_bytes()).hexdigest(),'final_commit':binding['final_commit'],'file_inventory_rows_present':len(files),'requests':requests,'browser_stopped':True,'temporary_server_stopped':not thread.is_alive(),'new_solver_calls':0}
(out/'overview_final_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'status':receipt['status'],'files':len(files),'stopped':receipt['temporary_server_stopped']}))
