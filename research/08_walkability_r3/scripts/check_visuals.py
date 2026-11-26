"""Open the actual map in Edge, verify interactions and render six review figures."""
import argparse
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from serve_review import ReviewHandler

ROOT = Path(__file__).resolve().parents[1]
FIGURES = {"grass": "01-grass-native-walkways.png", "region": "02-north-walkability-states.png",
           "pairs": "03-shared-region-multiple-queries.png", "mask": "04-controlled-masking.png",
           "limits": "05-obstacles-and-unknown.png", "route": "06-route-layer-contribution.png"}


def visible_heading(page, heading):
    page.wait_for_function("text => document.getElementById('title').textContent.includes(text)", arg=heading)
    assert page.locator("#left-map").get_attribute("viewBox") == page.locator("#right-map").get_attribute("viewBox")
    assert page.locator("#left-map path").count() > 1 and page.locator("#right-map path").count() > 1


def browse(page, url, name, index):
    page.goto(f"{url}#{name}", wait_until="load", timeout=30000)
    visible_heading(page, f"0{index} ·")


def checks(page, url):
    browse(page, url, "region", 2)
    same = page.locator("#right-map").get_attribute("viewBox")
    page.get_by_role("button", name="同步放大").click()
    assert page.locator("#left-map").get_attribute("viewBox") != same
    assert page.locator("#left-map").get_attribute("viewBox") == page.locator("#right-map").get_attribute("viewBox")
    page.get_by_role("button", name="重置", exact=True).click()
    assert page.locator("#left-map").get_attribute("viewBox") == same
    domain = page.locator('#right-map [data-layer="domain"] path').first
    assert domain.get_attribute("fill") == "none"
    exact_exit = page.locator('#right-map [data-layer="exit"]').first
    exact_exit.press("Enter")
    inspect = page.locator("#inspect").inner_text()
    assert "6897145227" in inspect and "121.4706605" in inspect and "31.2305674" in inspect and "exit" in inspect
    status = page.locator('#right-map [data-layer^="state-"]').first
    status.press("Enter")
    inspect = page.locator("#inspect").inner_text()
    assert "walkability_state" in inspect and "evidence_sources" in inspect
    page.get_by_label("区域与搜索域").uncheck()
    assert page.locator('#right-map [data-layer^="state-"]').count() == 0
    page.get_by_label("区域与搜索域").check()
    browse(page, url, "pairs", 3)
    left = page.get_by_label("左图端点对").locator("option").count()
    assert left >= 2
    assert page.locator("#left-title").inner_text() != page.locator("#right-title").inner_text()
    left_states = page.locator('#left-map [data-layer^="state-"]').evaluate_all("els => els.map(el=>el.dataset.name)")
    right_states = page.locator('#right-map [data-layer^="state-"]').evaluate_all("els => els.map(el=>el.dataset.name)")
    assert left_states == right_states and left_states
    assert page.locator('#right-map [data-layer="route-inferred"]').count() > 0
    assert page.locator('#left-map [data-layer="route-inferred"]').count() == 0
    browse(page, url, "mask", 4)
    assert page.locator('#left-map [data-layer^="reference"]').count() == 0
    assert page.locator('#right-map [data-layer^="reference"]').count() >= 1
    browse(page, url, "limits", 5)
    assert page.locator('#right-map [data-layer="state-restricted"]').count() >= 1
    browse(page, url, "route", 6)
    methods = ["B0", "S1", "I-LINE", "I-REGION", "I-REGION-ABL", "I-REGION-NET-ABL"]
    right = page.get_by_label("右图方法")
    assert right.locator("option").all_text_contents() == methods
    for value in methods:
        right.select_option(value)
        assert page.locator("#right-title").inner_text() == value
    return ["zoom_reset_synchronized", "region_evidence", "search_window_unfilled", "north_raw_exit",
            "toggle_layers", f"{left}_query_pairs_with_identical_regions", "reference_right_only",
            "restricted_negative_visible", "six_route_variants"]


def main(args):
    page_path = args.root / "visuals/index.html"
    args.figures.mkdir(parents=True, exist_ok=True)
    page_errors, denied, openings = [], [], []
    with ThreadingHTTPServer(("127.0.0.1",0), partial(ReviewHandler, directory=args.root)) as server:
        runner = Thread(target=server.serve_forever, daemon=True)
        runner.start()
        url = f"http://127.0.0.1:{server.server_port}/visuals/index.html"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=args.browser, headless=True,
                    args=["--disable-background-networking", "--disable-component-update",
                          "--no-first-run", "--disable-extensions", "--disable-sync", "--disable-default-apps"])
                ctx = browser.new_context(viewport={"width": 1440, "height": 1040}, device_scale_factor=1)
                def local_only(route):
                    u = urlparse(route.request.url)
                    if u.scheme in {"file", "data", "blob"} or (u.scheme == "http" and
                        u.hostname == "127.0.0.1" and u.port == server.server_port):
                        route.continue_()
                    else:
                        denied.append(route.request.url)
                        route.abort()
                ctx.route("**/*", local_only)
                file_page = ctx.new_page()
                file_page.on("pageerror", lambda err: page_errors.append(str(err)))
                for idx, name in enumerate(FIGURES, 1):
                    browse(file_page, page_path.resolve().as_uri(), name, idx)
                    openings.append(f"file:{name}")
                http_page = ctx.new_page()
                http_page.on("pageerror", lambda err: page_errors.append(str(err)))
                interaction_checks = checks(http_page, url)
                # Capture from a fresh context state so defaults remain evident in the figures.
                render_page = ctx.new_page()
                render_page.on("pageerror", lambda err: page_errors.append(str(err)))
                for idx, (name, filename) in enumerate(FIGURES.items(), 1):
                    browse(render_page, url, name, idx)
                    openings.append(f"loopback:{name}")
                    render_page.evaluate("document.body.classList.add('capture')")
                    if name == "route":
                        render_page.locator("#detail details").evaluate("el => el.open = true")
                        render_page.evaluate("document.body.classList.add('capture-route')")
                    else:
                        render_page.evaluate("document.body.classList.remove('capture-route')")
                    output = args.figures / filename
                    render_page.locator("#figure").screenshot(path=str(output), animations="disabled", timeout=60000)
                browser_version = browser.version
                browser.close()
        finally:
            server.shutdown()
            runner.join(timeout=5)
    if page_errors or denied:
        raise AssertionError({"page_errors": page_errors, "unexpected_requests": denied})
    result = {"status": "PASS", "browser": browser_version, "views": openings, "interactions": interaction_checks,
              "figures": list(FIGURES.values()), "requests_denied": denied, "page_errors": page_errors}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--browser")
    p.add_argument("--figures", type=Path, default=ROOT / "visuals/figures")
    p.add_argument("--receipt", type=Path)
    main(p.parse_args())
