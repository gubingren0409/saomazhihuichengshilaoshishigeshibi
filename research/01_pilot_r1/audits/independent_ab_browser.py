"""Check the final local A/B gallery without submitting any human scores."""
from pathlib import Path
from playwright.sync_api import sync_playwright

from independent_geoapify import hash_file, local_path

EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def verify_browser(root, expected_hashes, check_viewer=False):
    root = root.resolve()
    calls, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(EDGE), headless=True,
                                     timeout=15000, args=["--disable-background-networking", "--no-first-run"])
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
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
        assert page.get_by_text("2 / 2 组双侧底图", exact=True).is_visible()
        for item in page.get_by_text("展开同视野路线叠加", exact=True).all():
            item.click()
        page.locator("img").evaluate_all("xs=>xs.forEach(x=>x.loading='eager')")
        page.wait_for_function("document.images.length===8 && Array.from(document.images).every(i=>i.complete&&i.naturalWidth===1200&&i.naturalHeight===900)")
        alias_paths = page.locator("img").evaluate_all("xs=>xs.map(x=>x.getAttribute('src'))")
        assert len(set(alias_paths)) == len(alias_paths) == 8
        assert all("geoapify" not in p.lower() and "osm" not in p.lower() for p in alias_paths)
        assert {hash_file(local_path(blind, alias)) for alias in alias_paths} == set(expected_hashes)
        assert page.locator("body").inner_text().count("Powered by Geoapify") >= 4
        assert page.locator("body").inner_text().count("OpenMapTiles") >= 4
        page.goto((blind / "score.html").as_uri(), wait_until="load")
        counts = {tag: page.locator(tag).count() for tag in ("select", "textarea")}
        assert counts == {"select": 21, "textarea": 2}
        assert page.locator("select,textarea").evaluate_all("xs=>xs.every(x=>x.value==='')")
        views = []
        if check_viewer:
            page.goto((root / "visuals/route_comparisons/index.html").as_uri(), wait_until="load")
            page.wait_for_function("window.PilotRouteViewer.summary()?.loaded", timeout=14000)
            views.append(page.evaluate("window.PilotRouteViewer.summary()"))
            page.locator("#view").select_option("context")
            page.wait_for_function("window.PilotRouteViewer.summary()?.view==='context' && window.PilotRouteViewer.summary()?.loaded",
                                   timeout=14000)
            views.append(page.evaluate("window.PilotRouteViewer.summary()"))
        browser.close()
    for view in views:
        assert view["bounds_match"] and view["max_corner_error_css_px"] <= 1
        assert view["bearing"] == view["pitch"] == 0 and view["image_present"]
        assert view["route_counts"] == {"local": 0, "geoapify": 80, "diagnostic": 90}
    assert calls == errors == []
    return {"status": "PASS", "paired_base_views": 2, "images_loaded": 8, "score_controls": counts,
            "score_values_default_empty": True, "submitted_scores": 0, "external_requests": 0, "viewer": views}
