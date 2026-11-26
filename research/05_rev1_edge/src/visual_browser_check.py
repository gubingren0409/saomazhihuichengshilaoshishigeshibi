"""Exercise the real offline browser and export SVGs from the same viewer."""
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from playwright.sync_api import sync_playwright

EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
PANEL_ORDER = ["overview", "compare", "south-route", "south-terminal", "north", "matrix"]


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def check(visuals, export=False, preview=False):
    receipts = visuals.parent / "audits"
    receipts.mkdir(parents=True, exist_ok=True)
    figures = visuals / "figures"
    if export:
        figures.mkdir(exist_ok=True)
    requested, errors, exports = [], [], []
    html = (visuals / "index.html").as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(EDGE) if EDGE.is_file() else None,
                                    headless=True, args=["--disable-background-networking"])
        page = browser.new_page(viewport={"width": 1650, "height": 1100}, accept_downloads=True)
        page.route("https://**/*", lambda route: (requested.append(route.request.url), route.abort()))
        page.route("http://**/*", lambda route: (requested.append(route.request.url), route.abort()))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(html + "#compare", wait_until="load")
        page.wait_for_selector(".map-card svg")
        assert page.locator(".map-card svg").count() == 2
        left, right = page.locator(".map-card svg").all()
        assert left.get_attribute("viewBox") == right.get_attribute("viewBox")
        assert page.get_by_text("北侧步行面", exact=True).count()
        assert page.get_by_text("南侧步行面", exact=True).count()
        assert page.locator("[data-map-layer='plaza'] path").count() >= 4
        assert page.locator("[data-map-layer='walk'] path").count() > 0
        original = left.get_attribute("viewBox")
        page.locator("#zoom-in").click()
        assert page.locator(".map-card svg").first.get_attribute("viewBox") != original
        assert page.locator(".map-card svg").first.get_attribute("viewBox") == page.locator(".map-card svg").last.get_attribute("viewBox")
        page.locator("#zoom-reset").click()
        assert page.locator(".map-card svg").first.get_attribute("viewBox") == original
        page.locator("#variant").select_option("R1_WITHOUT_DERIVED_EDGES")
        assert page.locator(".map-card svg").last.get_attribute("data-run") == "R1_WITHOUT_DERIVED_EDGES"
        assert page.locator(".map-card svg").last.locator("[data-map-layer='derived']").count() == 0
        page.locator("#variant").select_option("R1_AREA_EDGE_MAIN")
        page.locator("#width").select_option("1")
        assert page.locator(".map-card svg").last.get_attribute("data-run") == "R1_WIDTH_1M"
        page.locator("#width").select_option("5")
        assert page.locator(".map-card svg").last.get_attribute("data-run") == "R1_WIDTH_5M"
        page.locator("#width").select_option("3")
        page.locator("input[data-layer-toggle='walk']").uncheck()
        assert page.locator("[data-map-layer='walk']").count() == 0
        page.locator("input[data-layer-toggle='walk']").check()
        for panel in PANEL_ORDER:
            page.locator("#panel-tabs [data-panel='" + panel + "']").click()
            page.wait_for_function("panel=>window.rev1Review.renderState().panel===panel", arg=panel)
            assert page.locator(".map-card svg").count() == (2 if panel == "compare" else 1)
        assert page.locator(".feedback ol li").count() == 4
        page.locator("#panel-tabs [data-panel='south-terminal']").click()
        page.wait_for_function("window.rev1Review.renderState().panel==='south-terminal'")
        south = page.locator("[data-layer='entrance']").first
        south.focus()
        south.press("Enter")
        assert "6897141353" in page.locator("#inspector").inner_text()
        assert "121.4712158" in page.locator("#inspector").inner_text()
        page.locator("#panel-tabs [data-panel='south-route']").click()
        page.wait_for_function("window.rev1Review.renderState().panel==='south-route'")
        assert page.locator("#contact option").count() == 4
        for node_id in ("1890745480", "1890935415", "1890935454"):
            page.locator("#contact").select_option(node_id)
        page.locator("#contact").select_option("")
        page.locator("#panel-tabs [data-panel='north']").click()
        page.wait_for_function("window.rev1Review.renderState().panel==='north'")
        exit_node = page.locator("[data-layer='exit']").first
        exit_node.focus()
        exit_node.press("Enter")
        assert "6897145227" in page.locator("#inspector").inner_text()
        assert "121.4706605" in page.locator("#inspector").inner_text()
        if not preview:
            assert page.locator("[data-map-layer='gap'] path").count() >= 1
            assert "西北门" in page.locator("#detail").inner_text()
            page.locator("#panel-tabs [data-panel='compare']").click()
            page.wait_for_function("window.rev1Review.renderState().panel==='compare'")
            assert page.locator(".map-card svg").last.locator("[data-map-layer='derived'] path").count() >= 1
            edge = page.locator("[data-layer='derived']").first
            edge.focus()
            edge.press("Enter")
            assert "派生边" in page.locator("#inspector").inner_text()
            assert "2385771" in page.locator("#inspector").inner_text() or "2153738" in page.locator("#inspector").inner_text()
        with page.expect_download() as download:
            page.locator("#export").click()
        parsed = ET.parse(download.value.path())
        assert parsed.getroot().tag.endswith("svg")
        for scene_id in page.locator("#scene-select option").evaluate_all("rows=>rows.map(row=>row.value)"):
            page.locator("#scene-select").select_option(scene_id)
            page.wait_for_function("sid=>window.rev1Review.renderState().scene===sid", arg=scene_id)
            assert page.locator(".map-card svg").count() == (2 if page.evaluate("window.rev1Review.renderState().panel") == "compare" else 1)
        page.locator("#scene-select").select_option("sh-huangpu-01")
        page.locator("#panel-tabs [data-panel='compare']").click()
        page.wait_for_function("window.rev1Review.renderState().panel==='compare'")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(full_page=not preview, path=str((receipts if preview else figures) / ("rev1_development_preview.png" if preview else "07_interactive_preview.png")))
        if export:
            entries = page.evaluate("Object.entries(window.REV1_DATA.figures)")
            for name, panel in entries:
                output = figures / name
                content = page.evaluate("panel=>window.rev1Review.exportPanel(panel)", panel)
                doc = ET.fromstring(content)
                assert doc.attrib["data-panel"] == panel
                if panel != "matrix":
                    ns = {"s": "http://www.w3.org/2000/svg"}
                    expected = 2 if panel == "compare" else 1
                    assert len(doc.findall("s:svg", ns)) == expected
                    if panel == "compare":
                        assert len({f.attrib["viewBox"] for f in doc.findall("s:svg", ns)}) == 1
                output.write_text(content, encoding="utf-8", newline="\n")
                exports.append(dict(path=f"figures/{name}", panel=panel, bytes=output.stat().st_size, sha256=file_sha(output)))
            if not preview:
                (visuals / "figure_manifest.json").write_text(json.dumps({"figures": exports}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        browser.close()
    assert not errors and not requested, (errors, requested)
    receipt = dict(status="PASS", browser="Microsoft Edge" if EDGE.is_file() else "Chromium",
                   phase="SOURCE_BACKDROP_DEVELOPMENT" if preview else "R4_REV1_PRODUCTION_MAP_AUTHOR_CHECK",
                   panels=PANEL_ORDER, same_viewport_compare=True, cases=6, options_tested=[1, 3, 5],
                   layer_toggle=True, exact_coordinates_from_source=True, svg_download=True, external_requests=0,
                   derived_edge_inspection=not preview, north_gap_visible=not preview,
                   source_payload_sha256=file_sha(visuals / "scene_data.js"), static_svg=exports)
    (receipts / ("visual_development_check.json" if preview else "visual_author_check.json")).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in receipt.items() if k!="static_svg"}))
    return receipt
