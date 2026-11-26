"""Exercise the real R2 artifacts in a network-denied Edge session."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
SCORE_FILE = "user_scores_20261109T110307129Z.csv"


def checked_viewer(root):
    external = []
    errors = []
    svg_metadata = {}
    with (root/"inputs"/SCORE_FILE).open(encoding="utf-8-sig",newline="") as stream:
        [score] = list(csv.DictReader(stream))
    figure5=root/"figures/figure05_visual_comparison.png"
    with Image.open(figure5) as montage:
        for view,y in (("detail",256),("context",1260)):
            for kind,x in (("geoapify",36),("osm",1300)):
                source=root/"inputs"/"r1"/"visuals"/kind/f"sh-huangpu-01_{view}_base.png"
                with Image.open(source) as raw:
                    assert raw.size==(1200,900)
                    crop=montage.crop((x,y,x+1200,y+900)).convert("RGB")
                    assert ImageChops.difference(crop,raw.convert("RGB")).getbbox() is None
    with TemporaryDirectory(prefix="r2_browser_") as tmp, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(EDGE), headless=True,
            args=["--disable-background-networking","--no-first-run","--disable-component-update"])
        context = browser.new_context(accept_downloads=True, viewport={"width":1440,"height":1000},
                                      service_workers="block")
        def deny(route):
            external.append("BLOCKED_EXTERNAL")
            route.abort()
        context.route("http://**/*", deny)
        context.route("https://**/*", deny)
        page = context.new_page()
        page.on("pageerror",lambda error: errors.append(type(error).__name__))
        page.goto((root/"web/index.html").as_uri(), wait_until="domcontentloaded", timeout=14000)
        page.locator("#map-geometries [data-feature-id]").first.wait_for(timeout=10000)
        assert page.locator("#figure-list a").count()==6
        for item in page.locator("#figure-list a").all():
            relative=item.get_attribute("href")
            assert (root/"web"/relative).resolve().is_file()
        assert page.locator("#score-body blockquote").first.text_content()==score["failure_reason"]
        score_summary=page.locator(".score-summary").first.text_content()
        assert "42/45" in score_summary and "43/45" in score_summary and score["overall_preference"] in score_summary
        assert page.locator("#map [data-layer=route_local] [data-feature-id]").count()>0
        assert page.locator("#map [data-layer=route_geoapify] [data-feature-id]").count()>0
        page.locator("#route-side").select_option("geoapify")
        assert page.locator("#map [data-layer=route_local] [data-feature-id]").count()==0
        page.locator("#route-side").select_option("local")
        assert page.locator("#map [data-layer=route_geoapify] [data-feature-id]").count()==0
        page.locator("#route-side").select_option("both")
        page.locator("[data-view=plaza]").click()
        plaza_count=page.locator("#map [data-layer=plaza] [data-feature-id]").count()
        assert plaza_count>0
        page.locator("#layer-plaza").uncheck()
        assert page.locator("#map [data-layer=plaza] [data-feature-id]").count()==0
        page.locator("#layer-plaza").check()
        page.locator("[data-view=origin]").click()
        point=page.locator("#map [data-layer=crossing] [data-feature-id]").first
        point.focus()
        item=point.get_attribute("data-feature-id")
        point.press("Enter")
        assert item in page.locator("#selection").inner_text()
        page.locator("[data-view=endpoint]").click()
        assert page.locator("[data-view=endpoint]").get_attribute("aria-pressed")=="true"
        assert page.locator("#map [data-layer=reference] [data-feature-id]").count()>0
        page.locator("#zoom-in").click()
        page.locator("#zoom-out").click()
        page.locator("#download").scroll_into_view_if_needed()
        with page.expect_download() as delivery:
            page.locator("#download").click()
        exported=Path(tmp)/delivery.value.suggested_filename
        delivery.value.save_as(exported)
        xml=ElementTree.fromstring(exported.read_bytes())
        assert xml.tag.endswith("}svg") and xml.attrib["viewBox"]=="0 0 1040 660"
        assert len([e for e in xml.iter() if "data-feature-id" in e.attrib])>0
        assert not any(e.tag.endswith("}image") for e in xml.iter())
        assert "Powered by Geoapify" in exported.read_text(encoding="utf-8")
        svg_metadata={"filename":exported.name,"contains_native_feature_ids":True,"contains_original_map_images":False}
        page.locator("#base-title").click()
        for side in ("A","B"):
            page.locator("#base-side").select_option(side)
            for view in ("detail","context"):
                page.locator("#base-view").select_option(view)
                page.wait_for_function("""() => {const img=document.querySelector('#base-image');
                    const link=document.querySelector('#base-original');
                    return img.complete&&img.naturalWidth===1200&&img.currentSrc===link.href; }""")
                assert page.locator("#base-image").evaluate("(img) => img.naturalHeight")==900
        browser.close()
    assert not errors and not external
    return {
        "status":"PASS","engine":"Microsoft Edge via Playwright",
        "entry":"web/index.html","figure_links":6,"presets_and_zoom":True,"both_routes_and_plaza_toggle":True,
        "native_id_inspector":True,"score_text_exact":True,"original_base_assets":4,"figure05_raw_pixel_identity":4,"external_requests":len(external),
        "page_errors":len(errors),"svg_export":svg_metadata,
        "viewer_html_sha256":hashlib.sha256((root/"web/index.html").read_bytes()).hexdigest(),
        "viewer_data_sha256":hashlib.sha256((root/"web/data.js").read_bytes()).hexdigest(),
    }


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path)
    opts=parser.parse_args()
    result=checked_viewer(opts.root.resolve())
    formatted=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if opts.out:
        opts.out.write_text(formatted,encoding="utf-8")
    print(formatted,end="")
