"""Serve only review deliverables on loopback. Use Ctrl+C or --stop."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import threading
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime/review_service.json"
PUBLIC = {"visuals", "audits", "delivery", "data", "runs", "README.md", "RESULTS.md",
          "SCOPE_AND_METHOD.md", "USER_REVIEW_NOTES.md", "STATUS.json"}


class ReviewHandler(SimpleHTTPRequestHandler):
    def admitted(self):
        path = PurePosixPath(unquote(urlparse(self.path).path))
        if path == PurePosixPath("/"):
            self.send_response(302)
            self.send_header("Location", "/visuals/index.html")
            self.end_headers()
            return False
        if len(path.parts) < 2 or path.parts[1] not in PUBLIC or ".." in path.parts or any(
                part.startswith(".") or ":" in part or "\\" in part for part in path.parts[1:]):
            self.send_error(404)
            return False
        return True

    def do_GET(self):
        if self.admitted():
            super().do_GET()

    def do_HEAD(self):
        if self.admitted():
            super().do_HEAD()

    def list_directory(self, path):
        self.send_error(404)

    def do_POST(self):
        if self.path != "/_shutdown" or not secrets.compare_digest(
                self.headers.get("X-Review-Token", ""), self.server.token):
            self.send_error(404)
            return
        self.send_response(204)
        self.end_headers()
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        if not STATE.exists():
            print("No current review server.")
            return
        state = json.loads(STATE.read_text(encoding="utf-8"))
        req = Request(f"http://127.0.0.1:{int(state['port'])}/_shutdown", method="POST",
                      headers={"X-Review-Token": state["token"]})
        try:
            with urlopen(req, timeout=5) as response:
                print(f"Review server stopped (HTTP {response.status}).")
        except URLError as error:
            raise SystemExit(f"Recorded review service could not be stopped: {error}") from error
        return
    if not (ROOT / "visuals/index.html").is_file():
        raise SystemExit("visuals/index.html was not found.")
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(ReviewHandler, directory=ROOT)) as server:
        server.token = secrets.token_urlsafe(32)
        STATE.parent.mkdir(exist_ok=True)
        with STATE.open("x", encoding="utf-8") as stream:
            json.dump({"port": server.server_port, "pid": os.getpid(), "token": server.token}, stream)
        try:
            print(f"http://127.0.0.1:{server.server_port}/visuals/index.html", flush=True)
            server.serve_forever()
        finally:
            STATE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
