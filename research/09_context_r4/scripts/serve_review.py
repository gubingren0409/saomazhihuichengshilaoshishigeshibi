"""Serve the completed R4-CONTEXT review on an available loopback port."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
from secrets import compare_digest, token_urlsafe
from threading import Thread
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime/context_review_service.json"
ROOT_PAGES = {"README.md", "RESULTS.md", "SCOPE_AND_METHOD.md", "USER_REVIEW_NOTES.md", "STATUS.json"}
SUBTREES = {"visuals", "delivery", "audits"}


class ReviewHandler(SimpleHTTPRequestHandler):
    def admitted(self):
        parsed = urlparse(self.path)
        path = PurePosixPath(unquote(parsed.path))
        if path == PurePosixPath("/"):
            self.send_response(302)
            self.send_header("Location", "/visuals/index.html")
            self.end_headers()
            return False
        rel = path.parts[1:]
        target = Path(self.directory).joinpath(*rel)
        allowed = bool(rel) and ((len(rel) == 1 and rel[0] in ROOT_PAGES) or rel[0] in SUBTREES)
        if (not path.is_absolute() or not allowed or ".." in rel or
                any(p.startswith(".") or "\\" in p or ":" in p for p in rel) or
                not target.resolve().is_relative_to(Path(self.directory).resolve())):
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
        if (self.path != "/_shutdown" or not hasattr(self.server, "stop_token") or
                not compare_digest(self.headers.get("X-Review-Token", ""), self.server.stop_token)):
            self.send_error(404)
            return
        self.send_response(204)
        self.end_headers()
        Thread(target=self.server.shutdown, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        if not STATE.is_file():
            print("当前目录无已登记的 R4-CONTEXT 审查服务。")
            return
        info = json.loads(STATE.read_text(encoding="utf-8"))
        target = Request(f"http://127.0.0.1:{int(info['port'])}/_shutdown", method="POST",
                         headers={"X-Review-Token": info["token"]})
        with urlopen(target, timeout=5) as response:
            print(f"已停止本目录审查服务（HTTP {response.status}）。")
        return
    if not (ROOT/"visuals/index.html").is_file():
        raise SystemExit("缺少已生成的 visuals/index.html。")
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(ReviewHandler,directory=ROOT)) as server:
        server.stop_token = token_urlsafe(30)
        STATE.parent.mkdir(exist_ok=True)
        try:
            with STATE.open("x", encoding="utf-8") as stream:
                json.dump({"port": server.server_port,"pid": os.getpid(),"token": server.stop_token}, stream)
        except FileExistsError as exc:
            raise SystemExit("本目录已有服务记录。使用 --stop 停止该服务或核对失效记录。") from exc
        try:
            print(f"http://127.0.0.1:{server.server_port}/visuals/index.html", flush=True)
            print("停止方式：Ctrl+C 或使用相同脚本的 --stop。", flush=True)
            server.serve_forever()
        finally:
            STATE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
