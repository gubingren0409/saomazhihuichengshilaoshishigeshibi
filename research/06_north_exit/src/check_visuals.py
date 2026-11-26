"""Exercise the rendered maps in local Edge with external requests blocked."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def check(url, screenshot):
    errors, foreign = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=EDGE, headless=True,
                                     args=["--disable-background-networking", "--no-first-run"], timeout=20000)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        def gate(req):
            if req.request.url.startswith(("file:", "http://127.0.0.1:8776/")):
                req.continue_()
            else:
                foreign.append(req.request.url)
                req.abort()

        page.route("**/*", gate)
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(url, wait_until="load")
        assert response is None or response.ok
        assert page.get_by_role("heading", name="门前接入的三种对照").is_visible()
        left, right = page.locator("#map-left"), page.locator("#map-right")
        near = left.get_attribute("viewBox")
        assert near == right.get_attribute("viewBox")
        assert left.locator('[data-feature="connector"]').count() == 0
        assert right.locator('[data-feature="connector"][data-variant="N2"]').count() == 1
        assert right.locator('[data-feature="corridor"]').count() == 1
        for name, expected in [("connector", "假设"), ("grade_point", "level")]:
            feature = right.locator(f'[data-feature="{name}"]')
            feature.focus()
            feature.press("Enter")
            assert expected in page.locator("#inspector").inner_text()
        page.get_by_role("button", name="N0 对 N1").click()
        assert right.locator('[data-feature="connector"][data-variant="N1"]').count() == 1
        assert right.locator('[data-feature="corridor"]').count() == 0
        assert left.get_attribute("viewBox") == right.get_attribute("viewBox") == near
        page.get_by_role("button", name="路线全程").click()
        full = left.get_attribute("viewBox")
        assert full != near and full == right.get_attribute("viewBox")
        page.get_by_role("button", name="同步放大").click()
        assert left.get_attribute("viewBox") == right.get_attribute("viewBox") != full
        page.get_by_role("checkbox", name="障碍与内环").uncheck()
        for target in (left, right):
            assert target.locator('[data-layer="obstacle"]').evaluate("(x)=>getComputedStyle(x).display") == "none"
        page.get_by_role("checkbox", name="障碍与内环").check()
        page.get_by_role("button", name="N0 对 N2").click()
        page.get_by_role("button", name="门前近景").click()
        assert left.get_attribute("viewBox") == right.get_attribute("viewBox") == near
        assert page.locator("#sensitivity-rows tbody tr").count() == 5
        embedded = json.loads(page.locator("#payload").text_content())
        for relative, key in [("data/route_variants.geojson", "route"), ("data/constraints.geojson", "constraints")]:
            assert sha256((ROOT / relative).read_bytes()).hexdigest() == embedded["sha256"][key]
        if screenshot:
            page.screenshot(path=screenshot)
        browser.close()
    assert not errors and not foreign, (errors, foreign)
    return {"status": "PASS", "renderer": "local Microsoft Edge", "entry": url,
            "near_and_full_views_match": True, "toggle_n1_n2": True, "zoom_and_layers": True,
            "keyboard_source_inspection": True, "explicit_nearby_level_point": True, "sensitivity_rows": 5,
            "verified_geometry_sha256": embedded["sha256"], "external_requests": 0}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--url", default=(ROOT / "visuals/index.html").as_uri())
    cli.add_argument("--receipt", type=Path)
    cli.add_argument("--screenshot", type=Path)
    args = cli.parse_args()
    result = json.dumps(check(args.url, args.screenshot), ensure_ascii=False, indent=2) + "\n"
    if args.receipt:
        args.receipt.write_text(result, encoding="utf8")
    print(result)
