"""Local-only dynamic service; the same src.planner.plan powers CLI and HTTP."""
import argparse,json,os,sys,time,threading,urllib.request
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.planner import ROOT,plan,scene_list,scene_view,put

STATE=ROOT/'runs/service.json'
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,value,status=200,ctype='application/json; charset=utf-8'):
        body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        try:
            if u.path=='/api/health':return self.send({'status':'UP','pid':os.getpid(),'route_answer_cache':False,'service':'PEDESTRIAN_AREA_SHORTEST_R1'})
            if u.path=='/api/scenes':return self.send(scene_list())
            if u.path=='/api/scene':return self.send(scene_view(qs['scene_id'][0],qs.get('door_id',[None])[0]))
            if u.path in ('/api/diagnostics','/api/diagnostics-support'):
                name='diagnostics.json' if u.path=='/api/diagnostics' else 'diagnostics_support.json'
                return self.send(json.loads((ROOT/'visuals'/name).read_text(encoding='utf-8')))
            if u.path.startswith('/api/runs/'):
                name=u.path.rsplit('/',1)[-1]
                if not name.startswith('RUN-') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in name):return self.send({'error':'INVALID_RUN_ID'},400)
                p=ROOT/'runs/app'/f'{name}.json'
                return self.send(json.loads(p.read_text(encoding='utf-8'))) if p.exists() else self.send({'error':'RUN_NOT_FOUND'},404)
            assets={'/':('app/index.html','text/html; charset=utf-8'),'/index.html':('app/index.html','text/html; charset=utf-8'),'/app.js':('app/app.js','application/javascript; charset=utf-8'),'/app.css':('app/app.css','text/css; charset=utf-8'),'/diagnostics':('app/diagnostics.html','text/html; charset=utf-8'),'/diagnostics.js':('app/diagnostics.js','application/javascript; charset=utf-8')}
            assets['/review']=('index.html','text/html; charset=utf-8')
            for doc in ('README.md','RESULTS.md','SCOPE_AND_METHOD.md'):
                assets['/'+doc]=(doc,'text/plain; charset=utf-8')
            if u.path.startswith('/visuals/'):
                name=u.path.rsplit('/',1)[-1]
                if u.path=='/visuals/'+name and '\\'not in name and ':'not in name and name not in('.','..'):
                    visual=ROOT/'visuals'/name
                    if visual.is_file()and not visual.is_symlink()and visual.suffix in('.svg','.png'):
                        return self.send(visual.read_bytes(),ctype='image/svg+xml'if visual.suffix=='.svg'else'image/png')
            if u.path in assets:
                f,mime=assets[u.path];return self.send((ROOT/f).read_bytes(),ctype=mime)
            return self.send({'error':'NOT_FOUND'},404)
        except (ValueError,KeyError,FileNotFoundError) as e:return self.send({'error':str(e)},400)
    def do_POST(self):
        if self.headers.get('Origin') and self.headers['Origin'] not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            return self.send({'error':'LOCAL_SAME_ORIGIN_REQUIRED'},403)
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=10000:return self.send({'error':'INVALID_BODY_SIZE'},400)
        try:body=json.loads(self.rfile.read(size))
        except (ValueError,UnicodeError):return self.send({'error':'INVALID_JSON'},400)
        if not isinstance(body,dict):return self.send({'error':'JSON_OBJECT_REQUIRED'},400)
        if self.path=='/api/plan':
            try:return self.send(plan(body))
            except Exception as e:
                put(ROOT/'runs/server_error.json',{'error':str(e),'type':type(e).__name__,'timestamp':time.time()})
                return self.send({'error':'PLANNING_ENGINE_ERROR','detail':str(e)},500)
        if self.path=='/api/stop':
            if body.get('pid')!=os.getpid():return self.send({'error':'PID_MISMATCH'},409)
            self.send({'status':'STOPPING','pid':os.getpid()});threading.Thread(target=self.server.shutdown,daemon=True).start();return
        self.send({'error':'NOT_FOUND'},404)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=53431);ap.add_argument('--stop',action='store_true');a=ap.parse_args()
    if a.stop:
        s=json.loads(STATE.read_text(encoding='utf-8'))
        if not s.get('running'):print('Already stopped');return
        req=urllib.request.Request(s['url']+'api/stop',data=json.dumps({'pid':s['pid']}).encode(),headers={'Content-Type':'application/json'},method='POST')
        print(urllib.request.urlopen(req,timeout=10).read().decode());return
    if STATE.exists():
        try:
            existing=json.loads(STATE.read_text(encoding='utf-8'))
            if existing.get('running') and urlparse(existing.get('url','')).hostname=='127.0.0.1':
                health=json.loads(urllib.request.urlopen(existing['url']+'api/health',timeout=2).read())
                if health.get('pid')==existing.get('pid') and health.get('service')=='PEDESTRIAN_AREA_SHORTEST_R1':
                    print(existing['url']+' (already running; use --stop to restart)',flush=True);return
        except (OSError,ValueError,KeyError):pass
    try:server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    except OSError:server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}/'
    put(STATE,{'pid':os.getpid(),'url':url,'running':True,'started_at':time.time()})
    print(url,flush=True)
    try:server.serve_forever(poll_interval=.2)
    finally:server.server_close();put(STATE,{'pid':os.getpid(),'url':url,'running':False,'stopped_at':time.time()})
if __name__=='__main__':main()
