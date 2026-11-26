"""Isolated ZIP, rendered-file, score, geometry and browser audit for R2."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image

from independent_r2 import verify

SCORE = "user_scores_20261109T110307129Z.csv"
FIGURES = ("figure01_global.png", "figure02_origin.png", "figure03_plaza.png",
           "figure04_endpoint.png", "figure05_visual_comparison.png", "figure06_layers.png")
BLOCKED_COMPONENTS = {".git", "private_local", "__pycache__", ".pytest_cache", ".venv", "node_modules",
                      "07_blind_reveal_map_private.csv"}
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def checksum(data):
    return sha256(data).hexdigest()


def safe_member(info):
    raw = info.filename
    path = PurePosixPath(raw)
    if not raw or raw != path.as_posix() or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("ARCHIVE_UNSAFE_PATH")
    for token in path.parts:
        low = token.lower()
        if (chr(92) in token or ":" in token or token.rstrip(". ") != token
                or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", token.split(".", 1)[0].upper())
                or low in BLOCKED_COMPONENTS or (low.startswith(".env") and low != ".env.example")):
            raise ValueError("ARCHIVE_PRIVATE_OR_UNSAFE_MEMBER")
    if stat.S_ISLNK(info.external_attr >> 16) or info.is_dir() or path.suffix.lower() in {".har", ".sqlite", ".pyc", ".pbf"}:
        raise ValueError("ARCHIVE_LINK_OR_UNEXPECTED_FORMAT")
    return path


def unpack(archive, root):
    with ZipFile(archive) as book:
        assert book.testzip() is None
        member_names, members = set(), {}
        for row in book.infolist():
            path = safe_member(row)
            name = path.as_posix()
            assert name.casefold() not in member_names and row.file_size < 30 * 1024 * 1024
            member_names.add(name.casefold())
            members[name] = path
        assert sum(info.file_size for info in book.infolist()) < 100 * 1024 * 1024
        manifest = json.loads(book.read("MANIFEST.json"))["entries"]
        assert len(manifest) == len(members)-1
        assert {row["path"] for row in manifest} == set(members)-{"MANIFEST.json"}
        for row in manifest:
            data = book.read(row["path"])
            assert len(data) == row["bytes"] and checksum(data) == row["sha256"]
        for name, path in members.items():
            destination = root.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(book.read(name))
    return {"members": len(members), "manifest_entries": len(manifest), "crc": "PASS",
            "sha256": checksum(archive.read_bytes()), "bytes": archive.stat().st_size,
            "forbidden_private_members": 0}


def indexed_copies(root):
    matched = 0
    with (root / "source_evidence_index.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if not row["copy_path"]:
                continue
            path = (root / row["copy_path"]).resolve()
            assert path.is_relative_to(root) and path.is_file(), row["copy_path"]
            assert path.stat().st_size == int(row["bytes"]) and checksum(path.read_bytes()) == row["sha256"]
            matched += 1
    return matched


def figure_checks(root):
    with (root / "figure_manifest.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 6, "Six figure provenance rows required"
    result = {}
    for name in FIGURES:
        path = root / "figures" / name
        candidates = [row for row in rows if any(name in str(v) for v in row.values())]
        assert len(candidates) == 1, name
        manifest_hash = candidates[0].get("sha256") or candidates[0].get("image_sha256")
        digest = checksum(path.read_bytes())
        if manifest_hash:
            assert digest == manifest_hash
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            assert image.format == "PNG" and min(image.size) >= 500
            summary = image.convert("RGB").getcolors(maxcolors=100)
            assert summary is None or len(summary) >= 10
            result[name] = {"size": list(image.size), "sha256": digest}
    return result


def browser_checks(root):
    from playwright.sync_api import sync_playwright
    calls, errors = [], []
    with (root / "inputs" / SCORE).open(encoding="utf-8-sig", newline="") as file:
        [score] = list(csv.DictReader(file))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(EDGE), headless=True, timeout=15000,
                                     args=["--disable-background-networking", "--no-first-run"])
        page = browser.new_page(viewport={"width":1440, "height":1024}, accept_downloads=True)
        page.set_default_timeout(12000)

        def no_http(route):
            calls.append("EXTERNAL")
            route.abort()

        page.route("http://**/*", no_http)
        page.route("https://**/*", no_http)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((root / "web/index.html").as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('#figure-list a').length===6")
        assert page.locator("#score-body blockquote").first.text_content() == score["failure_reason"]
        assert "合计 A 42/45 · B 43/45" in page.locator("#score-body").inner_text()
        assert "37/40" in page.locator("#score-body").inner_text() and "38/40" in page.locator("#score-body").inner_text()

        for preset in ("overview", "origin", "plaza", "endpoint"):
            view = page.locator(f'[data-view="{preset}"]')
            view.click()
            assert view.get_attribute("aria-pressed") == "true"
            assert page.locator("#map-geometries .geom").count() > 0
        page.locator('[data-view="origin"]').click()
        page.locator("#route-side").select_option("geoapify")
        assert page.locator('[data-layer="route_geoapify"] .geom').count() > 0
        assert page.locator('[data-layer="route_local"] .geom').count() == 0
        page.locator("#route-side").select_option("local")
        assert page.locator('[data-layer="route_local"] .geom').count() > 0
        assert page.locator('[data-layer="route_geoapify"] .geom').count() == 0
        page.locator("#route-side").select_option("both")
        page.locator("#layer-buildings").uncheck()
        assert page.locator('[data-layer="buildings"] .geom').count() == 0
        page.locator("#layer-buildings").check()
        candidates = page.locator('[data-feature-id^="way/"]')
        assert candidates.count() > 0
        first = candidates.first
        chosen = first.get_attribute("data-feature-id")
        first.press("Enter")
        assert chosen in page.locator("#selection").inner_text()
        with page.expect_download() as exported:
            page.locator("#download").click()
        data = exported.value.path().read_text(encoding="utf-8")
        assert "<svg " in data and "OpenStreetMap contributors" in data and "Geoapify" in data
        assert "http://127.0.0.1" not in data
        page.locator("#base-detail summary").click()
        for side in ("A","B"):
            page.locator("#base-side").select_option(side)
            for view in ("detail","context"):
                page.locator("#base-view").select_option(view)
                page.wait_for_function("(() => {const img=document.querySelector('#base-image');return img.complete&&img.naturalWidth===1200&&img.naturalHeight===900;})()")
        browser.close()
    assert calls == errors == []
    return {"status":"PASS","six_figure_links":6,"viewport_presets":4,"route_switch":True,
            "layer_toggle":True,"way_inspector":True,"svg_export":True,"source_maps_loaded":4,
            "exact_original_score_comment":True,"external_requests":0}


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("archive", type=Path)
    args.add_argument("--scratch", type=Path, required=True)
    args.add_argument("--out", type=Path, required=True)
    args.add_argument("--browser", action="store_true")
    parsed = args.parse_args()
    parsed.scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=parsed.scratch) as tmp:
        root = Path(tmp).resolve()
        report = unpack(parsed.archive, root)
        report["source_copies_sha_verified"] = indexed_copies(root)
        report["independent_geography_and_scores"] = verify(root / "inputs/r1", root / "inputs" / SCORE)
        report["figure_images"] = figure_checks(root)
        if parsed.browser:
            report["offline_browser"] = browser_checks(root)
        report["status"] = "PASS"
    parsed.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in {"independent_geography_and_scores","figure_images"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

