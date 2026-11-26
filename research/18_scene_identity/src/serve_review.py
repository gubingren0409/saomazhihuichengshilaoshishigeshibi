"""Loopback static review only. No route/planner endpoint."""
import argparse
import functools
import json
from pathlib import Path, PurePosixPath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path=unquote(urlsplit(self.path).path)
        if path=='/':
            self.send_response(302);self.send_header('Location','/web/index.html');self.end_headers();return
        if path=='/health':
            b=json.dumps({'task':'PG1-MAP-CONTEXT-RECONSTRUCTION-R2','target':'way/161090899',
                          'mode':'SOURCE_AND_FROZEN_RESULTS_DISPLAY_ONLY','solver_calls_added':0}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        if any(p.startswith('.')or p in{'repository','delivery'}for p in PurePosixPath(path).parts):self.send_error(403);return
        super().do_GET()
    def do_POST(self):self.send_error(405,'No route calculation in this task')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=53531);a=p.parse_args()
    s=ThreadingHTTPServer(('127.0.0.1',a.port),functools.partial(Handler,directory=str(ROOT)))
    print(f'http://127.0.0.1:{a.port}/ target=way/161090899 readonly=True',flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.server_close()
