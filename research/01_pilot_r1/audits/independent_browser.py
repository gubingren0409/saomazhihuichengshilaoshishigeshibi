"""Independent technical checks for the actual blind gallery and offline route viewer."""
import argparse
import csv
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def verify(root):
    calls = []
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(EDGE), headless=True,
                                    timeout=15000, args=["--disable-background-networking", "--no-first-run"])
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.set_default_timeout(12000)
        def forbid(route):
            calls.append("EXTERNAL_REQUEST")
            route.abort()
        page.route("http://**/*", forbid)
        page.route("https://**/*", forbid)
        page.on("pageerror", lambda _: errors.append("PAGE_SCRIPT_ERROR"))
        blind = root / "visuals/blind_review"
        page.goto((blind / "index.html").as_uri(), wait_until="load")
        assert page.locator("section.view").count() == 2
        assert page.get_by_text("0 / 2 组双侧底图", exact=True).is_visible()
        for item in page.get_by_text("展开同视野路线叠加", exact=True).all():
            item.click()
        page.locator("img").evaluate_all("xs=>xs.forEach(x=>x.loading='eager')")
        page.wait_for_function("Array.from(document.images).every(i=>i.complete&&i.naturalWidth===1200)")
        gallery_dimensions = page.locator("img").evaluate_all("xs=>xs.map(x=>[x.naturalWidth,x.naturalHeight])")
        assert gallery_dimensions == [[1200, 900]] * 4
        attributed = json.loads((root / "runs/local_viewports.json").read_text(encoding="utf-8"))["views"]
        assert all("OpenStreetMap contributors" in view["attribution"] for view in attributed.values())
        for alias in page.locator("img").evaluate_all("xs=>xs.map(x=>x.getAttribute('src'))"):
            with Image.open(blind / alias) as image:
                credit_panel = image.convert("RGB").crop((820, 855, 1190, 888))
                assert len(credit_panel.getcolors(10000)) > 15
        assert all("geoapify" not in path for path in page.locator("img").evaluate_all("xs=>xs.map(x=>x.getAttribute('src'))"))
        page.goto((blind / "score.html").as_uri(), wait_until="load")
        counts = {tag: page.locator(tag).count() for tag in ("select", "textarea")}
        assert counts["select"] == 21 and counts["textarea"] == 2
        assert page.locator("select,textarea").evaluate_all("xs=>xs.every(x=>x.value==='')")
        with (root / "06_USER_SCORE_SHEET.csv").open(encoding="utf-8-sig", newline="") as f:
            csv_rows = list(csv.DictReader(f))
        assert len(csv_rows) == 1 and list(csv_rows[0].values())[3:] == [""] * (len(csv_rows[0]) - 3)
        page.goto((root / "visuals/route_comparisons/index.html").as_uri(), wait_until="load")
        page.wait_for_function("window.PilotRouteViewer.summary()?.loaded", timeout=12000)
        detail = page.evaluate("window.PilotRouteViewer.summary()")
        page.locator("#view").select_option("context")
        page.wait_for_function("window.PilotRouteViewer.summary()?.view==='context' && window.PilotRouteViewer.summary()?.loaded",
                               timeout=12000)
        context = page.evaluate("window.PilotRouteViewer.summary()")
        browser.close()
    for view in (detail, context):
        assert view["bounds_match"] and view["max_corner_error_css_px"] <= 1
        assert view["bearing"] == view["pitch"] == 0 and view["image_present"]
        assert view["route_counts"] == {"local":0,"geoapify":0,"diagnostic":90}
        assert view["visible_layers"] == {"local":False,"geoapify":False,"diagnostic":True}
    assert calls == errors == []
    return {"status": "PASS", "identity": "ACTUAL_LOCAL_PILOT_ARTIFACTS", "provider_calls": 0,
            "gallery_dimensions": gallery_dimensions, "scored_items": 0,
            "score_controls": counts, "views": [detail,context]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root.resolve())
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Independent Edge artifact check passed.")
