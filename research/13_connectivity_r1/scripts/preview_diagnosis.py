"""Source-only preview server; no planner imports or solver endpoint."""
from pathlib import Path
import json,threading,os,sys
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.connectivity_view import diagnosis_data
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def send(self,b,m='application/json'):
        b=json.dumps(b,ensure_ascii=False).encode()if not isinstance(b,bytes)else b
        self.send_response(200);self.send_header('Content-Type',m+'; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/api/health':return self.send({'pid':os.getpid(),'status':'UP','service':'CONNECTIVITY_SOURCE_PREVIEW','solver_available':False})
        if path=='/api/diagnosis':return self.send(diagnosis_data('sh-huangpu-01'))
        if path in('/','/diagnosis'):return self.send((ROOT/'app/diagnosis.html').read_bytes(),'text/html')
        if path=='/diagnosis.js':return self.send((ROOT/'app/diagnosis.js').read_bytes(),'application/javascript')
        self.send_error(404)
    def do_POST(self):
        if self.path!='/api/stop':return self.send_error(404)
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        if body.get('pid')!=os.getpid():return self.send_error(409)
        self.send({'stopping':os.getpid()});threading.Thread(target=self.server.shutdown,daemon=True).start()
server=ThreadingHTTPServer(('127.0.0.1',53441),Handler)
(ROOT/'runs').mkdir(exist_ok=True);(ROOT/'runs/diagnosis_service.json').write_text(json.dumps({'pid':os.getpid(),'url':'http://127.0.0.1:53441/','service':'CONNECTIVITY_SOURCE_PREVIEW'}),encoding='utf-8')
server.serve_forever(.2);server.server_close()
