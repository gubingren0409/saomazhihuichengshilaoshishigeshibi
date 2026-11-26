"""Verify the actual offline and loopback pages in Edge and export four review figures."""
import argparse
from functools import partial
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse
from xml.etree import ElementTree

from playwright.sync_api import sync_playwright

from serve_review import ReviewHandler

ROOT = Path(__file__).resolve().parents[1]
TABS = ("context", "mask", "method", "business")
FILENAMES = ("01-context-and-local", "02-masking-comparison", "03-m0-m1-comparison", "04-business-and-failures")


def open_page(page, url, tab):
    page.goto(f"{url}#{tab}", wait_until="load", timeout=40000)
    page.wait_for_function("tab=>window.contextReview?.tab===tab",arg=tab,timeout=30000)
    assert page.locator("#left-map path").count() and page.locator("#right-map path").count()
    assert page.locator("#left-map [data-layer=score-domain] path").first.get_attribute("fill") == "none"
    assert not page.locator("#ref-toggle").is_checked()


def viewport(page, side):
    return page.locator(f"#{side}-map").get_attribute("viewBox")


PREFERRED = ("Wc4183046a70", "W6daddd19fdb", "W745941f0f92")


def task_ids(page):
    available=page.locator("#case option").evaluate_all("xs=>xs.map(x=>x.value)")
    return list(dict.fromkeys([*(p for p in PREFERRED if p in available),*available]))


def option_ids(page, selector):
    return page.locator(f"#{selector} option").evaluate_all("xs=>xs.map(x=>x.value)")


def case_with(page, key, value):
    identifiers = task_ids(page)
    for ident in identifiers:
        page.locator("#case").select_option(ident)
        if value in page.locator(f"#{key} option").evaluate_all("xs=>xs.map(x=>x.value)"):
            return ident
    return None


def comparable_method_case(page):
    """Prefer a real witness for explaining the feature, irrespective of its score."""
    pairs=page.evaluate("window.contextReviewPairs")
    if not pairs:
        return None
    order={name:i for i,name in enumerate(PREFERRED)}
    item=min(pairs,key=lambda x:(x["changed"]==0,not x["beyond40"],x["mode"]!="G",x["radius"]!="80",
                                order.get(x["id"],len(order)),x["id"],x["mode"],x["radius"]))
    ident,mode,radius=(item[k] for k in ("id","mode","radius"))
    page.locator("#case").select_option(ident)
    page.locator("#mode").select_option(mode)
    page.locator("#radius").select_option(radius)
    return ident,mode,radius


def interactive(page, url):
    checks=[]
    open_page(page,url,"context")
    case_with(page,"radius","160")
    left=page.locator("#left-map")
    right=page.locator("#right-map")
    assert left.get_attribute("data-extent")=="context-160m" and right.get_attribute("data-extent")=="local-30m"
    original_view=viewport(page,"right")
    original_outline=right.locator("[data-layer=score-domain] path").first.get_attribute("d")
    hashes=[]
    radii=page.locator("#radius option").evaluate_all("xs=>xs.map(x=>x.value)")
    for value in ("40","80","160"):
        if value not in radii:
            continue
        page.locator("#radius").select_option(value)
        assert left.locator("[data-layer=context-circle]").get_attribute("data-radius")==value
        assert viewport(page,"right")==original_view
        assert right.locator("[data-layer=score-domain] path").first.get_attribute("d")==original_outline
        hashes.append(left.get_attribute("data-observed"))
    assert len(set(hashes))==len(hashes)
    if "40" in radii and "160" in radii:
        page.locator("#radius").select_option("40")
        assert left.locator("[data-layer=unobserved-context]").count()==1
        page.locator("#gray-toggle").uncheck()
        assert left.locator("[data-layer=unobserved-context]").count()==0
        page.locator("#gray-toggle").check()
    checks.append("radius_changes_observed_receipt_but_not_score_domain")
    point=left.bounding_box()
    page.mouse.click(point["x"]+point["width"]/2,point["y"]+point["height"]/2)
    assert left.locator(".link-crosshair").count() and right.locator(".link-crosshair").count()
    page.locator("#zoom-in").click()
    assert viewport(page,"right")!=original_view
    page.locator("#reset").click()
    assert viewport(page,"right")==original_view
    checks.append("linked_point_and_reset")
    if page.locator("#ref-toggle").is_enabled():
        assert not page.locator("[data-layer=reference]").count()
        page.locator("#ref-toggle").check()
        assert page.locator("[data-layer=reference][data-visibility=evaluation-only]").count()==2
        page.locator("#ref-toggle").uncheck()
        assert not page.locator("[data-layer=reference]").count()
        checks.append("reference_opt_in_only")
    open_page(page,url,"mask")
    if case_with(page,"mode","G"):
        page.locator("#mode").select_option("G")
        if "80" in page.locator("#radius option").evaluate_all("xs=>xs.map(x=>x.value)"):
            page.locator("#radius").select_option("80")
        page.locator("#other").select_option("H")
        assert left.get_attribute("data-observed")!=right.get_attribute("data-observed")
        assert viewport(page,"right")==viewport(page,"left")
        checks.append("same_extent_h_g")
    open_page(page,url,"method")
    selected=comparable_method_case(page)
    if selected:
        assert left.get_attribute("data-observed")==right.get_attribute("data-observed")
        assert left.get_attribute("data-state-sha256") and right.get_attribute("data-state-sha256")
        outer=page.locator('#right-map [data-outer-witness=true]').first
        cell=outer if outer.count() else page.locator('#right-map [data-layer="cell"]').first
        if cell.count():
            cell.press("Enter")
            actual=page.locator("#inspect").inner_text()
            assert "evidence_sources" in actual or "decision_reason" in actual or "context_witnesses" in actual
            checks.append("region_cell_evidence")
            if outer.count():
                assert "actual_outer_witnesses" in actual and "radius_band" in actual
                checks.append("real_outer_witness_details")
        else:
            candidate=page.locator('#right-map [data-layer^="state-"]').first
            candidate.press("Enter")
            assert "walkability_state" in page.locator("#inspect").inner_text()
            checks.append("region_state_evidence_in_selected_case")
        checks.append("m0_m1_identical_observation")
    open_page(page,url,"business")
    if "NORTH" in task_ids(page):
        page.locator("#case").select_option("NORTH")
        door=page.locator("#right-map [data-layer=exit]").first
        door.press("Enter")
        text=page.locator("#inspect").inner_text()
        assert "6897145227" in text and "121.4706605" in text and "31.2305674" in text and "exit" in text
        if page.locator("#left-map [data-layer^=route-]").count():
            page.locator("#full-route").click()
            assert page.locator("#left-map").get_attribute("data-extent")=="full-route"
            assert page.locator("#right-map").get_attribute("data-extent")=="local-30m"
        checks.append("original_north_exit")
    return checks


def check_svg(path):
    svg=ElementTree.parse(path).getroot()
    ns={"s":"http://www.w3.org/2000/svg"}
    panes=svg.findall("s:svg",ns)
    assert len(panes)==2 and all(p.get("data-extent") for p in panes)
    assert not svg.findall(".//s:script",ns)


def prepare_figure(page, url, tab):
    open_page(page,url,tab)
    if tab=="context":
        case_with(page,"radius","160")
        if "H" in option_ids(page,"mode"):
            page.locator("#mode").select_option("H")
        page.locator("#radius").select_option("160")
    elif tab=="mask" and case_with(page,"mode","G"):
        page.locator("#mode").select_option("G")
        if "80" in page.locator("#radius option").evaluate_all("xs=>xs.map(x=>x.value)"):
            page.locator("#radius").select_option("80")
        page.locator("#other").select_option("H")
    elif tab=="method":
        comparable_method_case(page)
    elif tab=="business" and "NORTH" in task_ids(page):
        page.locator("#case").select_option("NORTH")
    page.evaluate("document.body.classList.add('capture')")


def main(args):
    path=args.root/"visuals/index.html"
    args.figures.mkdir(parents=True,exist_ok=True)
    blocked,errors,openings,figures=[],[],[],[]
    with ThreadingHTTPServer(("127.0.0.1",0),partial(ReviewHandler,directory=args.root)) as server:
        worker=Thread(target=server.serve_forever,daemon=True)
        worker.start()
        url=f"http://127.0.0.1:{server.server_port}/visuals/index.html"
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.browser,headless=True,
                    args=["--disable-background-networking","--disable-component-update","--no-first-run",
                          "--disable-extensions","--disable-sync","--disable-default-apps"])
                ctx=browser.new_context(viewport={"width":1460,"height":1100},device_scale_factor=1,
                                        accept_downloads=True)
                def local_only(route):
                    u=urlparse(route.request.url)
                    if u.scheme in {"file","data","blob"} or (u.scheme=="http" and u.hostname=="127.0.0.1" and u.port==server.server_port):
                        route.continue_()
                    else:
                        blocked.append(route.request.url)
                        route.abort()
                ctx.route("**/*",local_only)
                file=ctx.new_page()
                file.on("pageerror",lambda error:errors.append(str(error)))
                for tab in TABS:
                    open_page(file,path.resolve().as_uri(),tab)
                    openings.append("file:"+tab)
                page=ctx.new_page()
                page.on("pageerror",lambda error:errors.append(str(error)))
                checks=interactive(page,url)
                for tab,name in zip(TABS,FILENAMES):
                    prepare_figure(page,url,tab)
                    openings.append("http:"+tab)
                    png=args.figures/(name+".png")
                    page.locator("#figure").screenshot(path=png,animations="disabled",timeout=60000)
                    svg=args.figures/(name+".svg")
                    page.evaluate("document.body.classList.remove('capture')")
                    with page.expect_download(timeout=30000) as ev:
                        page.locator("#download").click()
                    ev.value.save_as(svg)
                    check_svg(svg)
                    figures.append({"png":png.name,"svg":svg.name,**page.evaluate("window.contextReview")})
                version=browser.version
                browser.close()
        finally:
            server.shutdown()
            worker.join(timeout=5)
    assert not blocked and not errors, {"blocked":blocked,"errors":errors}
    result={"status":"PASS","browser":version,"page_sha256":sha256(path.read_bytes()).hexdigest(),
            "views":openings,"checks":checks,"figures":figures,"blocked_external":blocked,"page_errors":errors}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True,exist_ok=True)
        args.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--browser")
    parser.add_argument("--figures",type=Path)
    parser.add_argument("--receipt",type=Path)
    args=parser.parse_args()
    args.figures=args.figures or args.root/"visuals/figures"
    main(args)
