"""Read-only, loopback-only R2 diagnosis viewer. Never invokes routing."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import argparse,json,os
ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**k):super().__init__(*a,directory=str(ROOT),**k)
 def log_message(self,*a):pass
 def do_GET(self):
  if self.path in('/','/index.html'):self.path='/visuals/index.html'
  if self.path=='/api/health':
   body=json.dumps({'service':'PED_AREA_CONNECTIVITY_R2_DIAGNOSIS','pid':os.getpid(),'read_only':True,'solver_endpoint':False}).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body);return
  super().do_GET()
 def end_headers(self):self.send_header('Cache-Control','no-store');super().end_headers()
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=53451);a=p.parse_args();s=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);print('http://127.0.0.1:'+str(s.server_port)+'/',flush=True);s.serve_forever()
if __name__=='__main__':main()
