"""Loopback-only static map review. No solver or external map backend."""
import argparse
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path=unquote(urlsplit(self.path).path)
        if path=='/health':
            data=json.dumps({'task':'PG1-MAP-CONTEXT-VISUAL-REPAIR-R1','mode':'FROZEN_RENDER_ONLY',
                             'solver_calls_added':0,'external_map_requests':0}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if any(p.startswith('.')or p in{'repository','delivery'}for p in PurePosixPath(path).parts):
            self.send_error(403);return
        super().do_GET()
    def do_POST(self):self.send_error(405,'This review page cannot run a solver')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=53521);args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),functools.partial(Handler,directory=str(ROOT)))
    print(f'http://127.0.0.1:{args.port}/ frozen-render-only=True',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
