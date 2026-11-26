"""Loopback-only PG1 review viewer; no route, download or push endpoint."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import argparse,json,os
ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**k):super().__init__(*a,directory=str(ROOT),**k)
 def log_message(self,*a):pass
 def do_GET(self):
  if any(part in('.git','.env')for part in self.path.split('/')):self.send_error(403);return
  if self.path=='/api/health':
   b=json.dumps({'service':'SMART_CITY_PG1_FOUNDATION_REVIEW','pid':os.getpid(),'read_only':True,'solver_endpoint':False,'push_endpoint':False}).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b);return
  super().do_GET()
 def end_headers(self):self.send_header('Cache-Control','no-store');super().end_headers()
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=53501);a=p.parse_args();s=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);print('http://127.0.0.1:'+str(a.port)+'/',flush=True);s.serve_forever()
if __name__=='__main__':main()
