"""Exercise the offline map with Playwright and export the actual maps as SVG."""
import argparse
import json
from pathlib import Path
import re
from xml.etree import ElementTree

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def verify(page, url):
    page.goto(url, wait_until="load", timeout=20000)
    page.locator("#map-left svg, #map-left path").first.wait_for(state="attached")
    assert page.locator("#title").inner_text()
    assert page.locator("#map-left").get_attribute("viewBox") == page.locator("#map-right").get_attribute("viewBox")
    return page.locator("#title").inner_text()


def capture(page, output, tag):
    exported = page.evaluate("window.exportPanel()")
    root = ElementTree.fromstring(exported)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert len(list(root.iter("{http://www.w3.org/2000/svg}path"))) > 2
    (output / f"{tag}.svg").write_text(exported, encoding="utf-8")


def main(args):
    args.figures.mkdir(parents=True, exist_ok=True)
    checks = []
    denied = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser, headless=True,
            args=["--disable-background-networking", "--disable-component-update", "--no-first-run",
                  "--disable-extensions", "--disable-sync", "--disable-default-apps"])
        context = browser.new_context(accept_downloads=True, viewport={"width": 1480, "height": 1000})
        def route_filter(route):
            url = route.request.url
            if url.startswith(("file:", "data:", "blob:", "http://127.0.0.1:", "http://localhost:")):
                route.continue_()
            else:
                denied.append(url.split("?", 1)[0])
                route.abort()
        context.route("**/*", route_filter)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        base = (args.root / "visuals/index.html").resolve().as_uri()
        checks.append(["file", verify(page, base + "#grass")])
        if args.http:
            for fragment in ("grass", "north", "cases"):
                checks.append(["loopback", fragment, verify(page, args.http + "#" + fragment)])
        verify(page, base + "#grass")
        original = page.locator("#map-left").get_attribute("viewBox")
        page.locator("#zoom-plus").click()
        assert page.locator("#map-left").get_attribute("viewBox") != original
        assert page.locator("#map-left").get_attribute("viewBox") == page.locator("#map-right").get_attribute("viewBox")
        page.locator("#reset").click()
        assert page.locator("#map-left").get_attribute("viewBox") == original
        page.get_by_label("原生底图").uncheck()
        assert page.locator('#map-left [data-layer="grass"]').count() == 0
        page.get_by_label("原生底图").check()
        edge = page.locator('#map-right [data-layer="restored"]').first
        edge.press("Enter")
        assert "way/" in page.locator("#inspector").inner_text()
        capture(page, args.figures, "01-grass-near")
        page.locator('button[data-view="full"]').click()
        capture(page, args.figures, "02-grass-full")
        verify(page, base + "#north")
        page.wait_for_function("document.getElementById('right-head').textContent.startsWith('I2')")
        assert page.locator('#map-right [data-layer="anchor"]').count() == 8
        door = page.locator('#map-right [data-layer="door"]').first
        door.press("Enter")
        assert "node/6897145227" in page.locator("#inspector").inner_text()
        assert "121.4706605" in page.locator("#inspector").inner_text()
        assert "exit" in page.locator("#inspector").inner_text()
        with page.expect_download() as download:
            page.locator("#export").click()
        assert download.value.suggested_filename.endswith(".svg")
        capture(page, args.figures, "03-north-near")
        page.locator('button[data-view="full"]').click()
        capture(page, args.figures, "04-north-full")
        page.get_by_label("北门右图变体").select_option("I1")
        assert page.locator('#map-right [data-layer="anchor"]').count() == 1
        assert "1,174.05" in page.locator("#right-summary").inner_text()
        verify(page, base + "#cases")
        page.get_by_label("受控案例").wait_for(state="visible")
        cases = page.get_by_label("受控案例")
        positive = cases.locator("option").filter(has_text=re.compile(r"^P-.*confirmation")).first.get_attribute("value")
        negative = cases.locator("option").filter(has_text=re.compile(r"^N-.*confirmation")).first.get_attribute("value")
        cases.select_option(positive)
        assert page.locator('#map-right [data-layer="reference"]').count() == 1
        assert page.locator('#map-left [data-layer="reference"]').count() == 0
        capture(page, args.figures, "05-controlled-recovery")
        cases.select_option(negative)
        assert page.locator('#map-right [data-layer="rejected"]').count() >= 1
        capture(page, args.figures, "06-rejected-conflict")
        if args.png:
            page.locator(".pair").screenshot(path=str(args.figures / "06-rejected-conflict.png"))
        cases.select_option("SYN-level")
        assert "EXPLICIT_LEVEL_CONFLICT" in page.locator("#right-summary").inner_text()
        assert page.locator('#map-right [data-layer="rejected"]').count() == 1
        checks.extend(["synthetic_layer_conflict", "zoom_lockstep", "layer_toggle", "keyboard_id", "north_exit_xy_and_role",
                       "variant_change", "actual_svg_download", f"case_positive:{positive}", f"case_negative:{negative}"])
        browser_version = browser.version
        browser.close()
    if denied or errors:
        raise RuntimeError(f"Unexpected network or script errors: {denied}, {errors}")
    output = dict(status="PASS", browser="Chromium", version=browser_version, checks=checks,
                  export="Six SVGs regenerated from the page", page_errors=errors, unexpected_requests=denied)
    if args.receipt:
        with args.receipt.open("x", encoding="utf-8") as stream:
            json.dump(output, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--figures", type=Path, default=ROOT / "visuals/figures")
    p.add_argument("--receipt", type=Path)
    p.add_argument("--browser")
    p.add_argument("--http")
    p.add_argument("--png", action="store_true")
    main(p.parse_args())
