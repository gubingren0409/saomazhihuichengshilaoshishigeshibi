"""Offline Edge smoke check of the actual R3 package pages."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

EDGE=Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
ROOT=Path(__file__).resolve().parents[1]


def verify(root):
    cases=json.loads((root/"runs/display_cases.json").read_text(encoding="utf-8"))["scenes"]
    expected=sum(1 for c in cases for v in c["views"].values()
                 for side in v["assets"].values() for key in ("base","overlay") if side.get(key))
    requests=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=str(EDGE) if EDGE.is_file() else None,
            headless=True,args=["--disable-background-networking","--no-first-run"],timeout=18000)
        page=browser.new_page(viewport={"width":1440,"height":980},accept_downloads=True)
        page.route("http://**/*",lambda r:(requests.append("HTTP"),r.abort()))
        page.route("https://**/*",lambda r:(requests.append("HTTPS"),r.abort()))
        page.on("pageerror",lambda e:errors.append(type(e).__name__))
        page.goto((root/"visuals/blind_review/index.html").as_uri(),wait_until="load")
        assert page.locator("article").count()==len(cases)
        page.evaluate("""() => {for(const d of document.querySelectorAll('details')) d.open=true;
          for(const i of document.images) i.loading='eager';}""")
        page.wait_for_function("Array.from(document.images).every(i=>i.complete&&i.naturalWidth===1200&&i.naturalHeight===900)",timeout=25000)
        assert page.locator("img").count()==expected
        assert page.locator("table tbody tr").count()==len(cases)
        page.goto((root/"visuals/blind_review/score.html").as_uri(),wait_until="load")
        assert page.locator("fieldset").count()==sum(not c.get("historical") for c in cases)
        assert page.evaluate("Array.from(document.querySelectorAll('select,textarea')).every(x=>x.value==='')")
        with page.expect_download() as export:
            page.locator("button[type=submit]").click()
        with export.value.path().open(encoding="utf-8-sig",newline="") as handle:
            assert len(list(csv.DictReader(handle)))==sum(not c.get("historical") for c in cases)
        page.goto((root/"visuals/routes/index.html").as_uri(),wait_until="load")
        assert page.locator("article").count()==len(cases)
        page.wait_for_function("Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)")
        route_and_detail=page.locator("img").count()
        page.goto((root/"visuals/failure_cases/index.html").as_uri(),wait_until="load")
        failure_cases=page.locator("article").count()
        browser.close()
    assert not requests and not errors
    with (root/"07_USER_SCORE_SHEET.csv").open(encoding="utf-8-sig",newline="") as handle:
        rows=list(csv.DictReader(handle))
    id_fields={"blind_scene_id","detail_pair_id","context_pair_id"}
    assert all(v=="" for row in rows for k,v in row.items() if k not in id_fields)
    return {"status":"PASS","scene_cards":len(cases),"real_gallery_png_links":expected,
            "routes_and_access_figures":route_and_detail,"failure_cards":failure_cases,
            "empty_score_rows":len(rows),"off_device_requests":0,
            "score_template_sha256":sha256((root/"07_USER_SCORE_SHEET.csv").read_bytes()).hexdigest(),
            "identity":"BROWSER_STRUCTURAL_QA_NO_HUMAN_SCORING"}


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root",type=Path,default=ROOT)
    cli.add_argument("--out",type=Path)
    args=cli.parse_args()
    result=verify(args.root.resolve())
    if args.out:
        args.out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
