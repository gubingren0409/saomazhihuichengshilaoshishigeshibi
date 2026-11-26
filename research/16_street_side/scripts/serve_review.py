"""Loopback-only, GET/HEAD review service. No route execution or external requests."""
import argparse
import functools
import json
import mimetypes
from pathlib import Path, PurePosixPath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT.parent / 'SMART_CITY_WALKABILITY_FOUNDATION_PG1/delivery/PG1_FOUNDATION_REVIEW.zip'

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.serve(False)

    def do_HEAD(self):
        self.serve(True)

    def serve(self, head):
        path = unquote(urlsplit(self.path).path)
        if path == '/health':
            data = json.dumps({'round':'PG1-RESUME-STREET-SIDE-R1', 'mode':'READ_ONLY_REVIEW',
                               'external_requests':False}).encode()
            kind = 'application/json; charset=utf-8'
        elif path.startswith('/foundation/'):
            name = path.removeprefix('/foundation/') or 'index.html'
            if any(p in {'.','..'} for p in PurePosixPath(name).parts) or '\\' in name:
                self.send_error(400); return
            # Always read the sealed copy, not mutable files in the old workspace.
            name = 'phase1/' + name
            try:
                with zipfile.ZipFile(FOUNDATION) as z:
                    data = z.read(name)
            except (KeyError, FileNotFoundError):
                self.send_error(404); return
            kind = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        else:
            parts = PurePosixPath(path).parts
            if any(part.startswith('.') or part in {'repository','inputs','delivery'} for part in parts):
                self.send_error(403); return
            if head:
                super().do_HEAD()
            else:
                super().do_GET()
            return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if not head:
            self.wfile.write(data)

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=53511)
    args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),functools.partial(Handler,directory=str(ROOT)))
    print(f'http://127.0.0.1:{args.port}/ round=PG1-RESUME-STREET-SIDE-R1 readonly=True',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
