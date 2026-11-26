"""Independently verify R3 original receipts, images, geometry and request identities.

No import of the R3 adapters, routing engines, renderers or hosted request code.
"""
import argparse
from collections import Counter
import csv
from hashlib import file_digest
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from geographiclib.geodesic import Geodesic
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def need(condition, code):
    if not condition:
        raise ValueError(code)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hash_file(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def relative(root, value):
    path = (root / value).resolve()
    need(path.is_relative_to(root.resolve()), "ARTIFACT_OUTSIDE_ROOT")
    return path


def index(payload):
    rows = payload["scenes"]
    indexed = {r["scene_id"]: r for r in rows}
    need(len(rows) == len(indexed), "DUPLICATE_RECEIPT_SCENE_ID")
    return indexed


def line_parts(geometry):
    if not geometry:
        return []
    type_ = geometry["type"]
    if type_ == "Feature":
        return line_parts(geometry.get("geometry"))
    if type_ == "FeatureCollection":
        return [line for feature in geometry["features"] for line in line_parts(feature)]
    if type_ == "LineString":
        return [geometry["coordinates"]]
    if type_ == "MultiLineString":
        return geometry["coordinates"]
    raise ValueError("UNEXPECTED_ROUTE_GEOMETRY")


def measure(a, b):
    if a is None or b is None:
        return None
    x1, y1 = a
    x2, y2 = b
    need(abs(x1) <= 180 and abs(x2) <= 180 and abs(y1) <= 90 and abs(y2) <= 90, "NON_WGS84_VERTEX")
    return Geodesic.WGS84.Inverse(y1, x1, y2, x2)["s12"]


def route_measure(lines, scene):
    if not lines:
        return None
    need(all(len(line) >= 2 for line in lines), "EMPTY_SOURCE_LINE")
    return {
        "parts": len(lines),
        "length_m": math.fsum(measure(a, b) for line in lines for a, b in zip(line, line[1:])),
        "start_wgs84": lines[0][0],
        "end_wgs84": lines[-1][-1],
        "start_offset_m": measure(lines[0][0], scene.get("start")),
        "target_gap_m": measure(lines[-1][-1], scene.get("target")),
        "between_parts_gap_m": [measure(a[-1], b[0]) for a, b in zip(lines, lines[1:])],
    }


def explicit_request(waypoints):
    result = []
    for s in waypoints.split("|"):
        prefix, coord = s.split(":", 1)
        need(prefix == "lonlat", "HOSTED_REQUEST_AXIS_ORDER")
        result.append([float(x) for x in coord.split(",")])
    return result


def verify_png(root, view, field, dimensions):
    value = view.get(field)
    if not value:
        return False
    path = relative(root, value)
    need(hash_file(path) == view.get(field + "_sha256"), "PNG_SHA_MISMATCH")
    with Image.open(path) as image:
        need(image.format == "PNG" and image.size == dimensions, "PNG_GEOMETRY_MISMATCH")
        image.verify()
    return True



def source_nodes(clip, scene):
    native = {f"{row['type']}/{row['id']}": row for row in clip["elements"]}
    need(clip["osm3s"]["timestamp_osm_base"] == scene["snapshot_time"] and
         clip["bounds_wsen"] == scene["snapshot_bounds_wsen"], "FROZEN_OSM_CLIP_METADATA_MISMATCH")
    building = native[scene["building_native_id"]]
    need(building["tags"].get("building") not in (None, "no") and building["tags"] == scene["building_tags"],
         "FROZEN_NATIVE_BUILDING_ID_MISMATCH")
    origin = native[scene["start_native_id"]]
    need([origin["lon"], origin["lat"]] == scene["start"], "FROZEN_NATIVE_ORIGIN_MISMATCH")
    if scene["target_role"] == "OSM_TAGGED":
        entry = native[scene["entry_native_id"]]
        need("entrance" in entry["tags"] and [entry["lon"], entry["lat"]] == scene["target"],
             "FROZEN_NATIVE_ENTRANCE_ID_MISMATCH")
    else:
        need(not scene.get("entry_native_id"), "PROXY_MISIDENTIFIED_AS_NATIVE_ENTRANCE")
    return native


def verify_local_segments(native, route, parts):
    if not parts:
        need(not route.get("segments"), "NO_GEOMETRY_BUT_SEGMENTS_PRESENT")
        return {}
    points, evidence = [], Counter()
    for edge in route["segments"]:
        a, b = edge["start"], edge["end"]
        if points:
            need(a == points[-1], "LOCAL_NATIVE_SEGMENT_DISCONTINUITY")
        else:
            points.append(a)
        if b != a:
            points.append(b)
        length = measure(a,b)
        need(abs(length - edge["length_m"]) < .001, "LOCAL_NATIVE_SEGMENT_DISTANCE_MISMATCH")
        if edge["osm_way_id"] is None:
            node = native[f"node/{edge['source_node_transition']}"]
            need(a == b == [node["lon"], node["lat"]], "LOCAL_SOURCE_TRANSITION_MISMATCH")
        else:
            way = native[f"way/{edge['osm_way_id']}"]
            idx = edge["segment_index"]
            nodes = way["nodes"][idx:idx+2]
            need(nodes == edge["osm_source_node_ids"], "LOCAL_SOURCE_WAY_NODE_MISMATCH")
            u, v = [native[f"node/{id_}"] for id_ in nodes]
            p, q = [u["lon"], u["lat"]], [v["lon"], v["lat"]]
            full_length = measure(p, q)
            for x in (a,b):
                need(abs(measure(p,x) + measure(x,q) - full_length) < .1, "LOCAL_SEGMENT_OUTSIDE_NATIVE_WAY")
            tags = way.get("tags", {})
            oneway = tags.get("oneway:foot")
            if oneway is None and tags.get("highway") in {"footway","path","steps"}:
                oneway = tags.get("oneway")
            forward = measure(p,a) < measure(p,b)
            need(not ((forward and oneway in {"-1", "reverse"}) or
                      (not forward and oneway in {"yes", "true", "1"})), "LOCAL_EXPLICIT_FOOT_DIRECTION_VIOLATED")
        evidence[edge["evidence"]] += 1
    need(parts == [points] and bool(points), "LOCAL_GEOMETRY_DIFFERS_FROM_EDGE_SEQUENCE")
    return dict(evidence)


def verify_static_requests(scene, hosted):
    total = 0
    for row in hosted.get("requests", []):
        receipt = row.get("receipt") or {}
        if receipt.get("status_code") != 200 or row["operation"] == "route":
            continue
        kind, _ = row["operation"].split("_", 1)
        view = scene["views"][kind]
        params = receipt["parameters"]
        prefix, coordinates = params["area"].split(":",1)
        bounds = [float(x) for x in coordinates.split(",")]
        need(prefix == "rect" and len(bounds) == 4 and
             all(abs(a-b)<1e-8 for a,b in zip(bounds,view["bounds"])), "HOSTED_STATIC_REQUEST_BOUNDS_CHANGED")
        spec = scene["geoapify_request_contract"]["static"]
        need(all(params.get(key) == val for key,val in spec.items()) and
             params["attribution"] == "default", "HOSTED_STATIC_STYLE_SIZE_OR_ATTRIBUTION_CHANGED")
        total += 1
    return total


def verify_scene(root, scene, local, hosted):
    ready = scene.get("contract_status") == "READY"
    rows = {
        "scene_id": scene["scene_id"], "contract_status": scene.get("contract_status"),
        "target_grade": scene.get("target_role"), "local_status": local.get("status", "NOT_RUN"),
        "hosted_status": hosted.get("status", "NOT_RUN"),
    }
    native = {}
    if ready:
        clip = relative(root, scene["osm_clip"])
        need(hash_file(clip) == scene["snapshot_sha256"], "FROZEN_OSM_CLIP_SHA_MISMATCH")
        native = source_nodes(read(clip), scene)
    local_route, hosted_route = local.get("route") or {}, hosted.get("route") or {}
    local_parts = line_parts(local_route.get("geometry"))
    rows["local_failure_reason"] = local_route.get("failure_reason")
    rows["hosted_raw_features"] = None
    if local_route:
        need(local_route["requested_start"] == scene["start"] and local_route["requested_target"] == scene["target"],
             "LOCAL_REQUEST_CHANGED")
        need(local_route["max_snap_m"] == scene["path_snap_max_m"], "LOCAL_SNAP_LIMIT_CHANGED")
        if local.get("route_artifact"):
            need(line_parts(read(relative(root, local["route_artifact"]))) == local_parts, "LOCAL_ROUTE_ARTIFACT_MISMATCH")
        if local_route["status"] != "PASS":
            need(not local_parts, "LOCAL_FAILURE_PRESENTED_AS_ROUTE")
    rows["local_target_route"] = route_measure(local_parts, scene)
    rows["local_native_edge_evidence_counts"] = verify_local_segments(native, local_route, local_parts)
    if rows["local_target_route"]:
        need(abs(rows["local_target_route"]["length_m"] - local_route["length_m"]) < .1, "LOCAL_LENGTH_MISMATCH")
    diag = local.get("diagnostic") or {}
    rows["local_approach_diagnostic"] = route_measure(line_parts(diag.get("geometry")), scene)
    if diag:
        artifact = local.get("diagnostic_artifact")
        if artifact:
            need(line_parts(read(relative(root, artifact))) == line_parts(diag.get("geometry")),
                 "LOCAL_DIAGNOSTIC_ARTIFACT_MISMATCH")
        need(local_route["status"] != "PASS" and diag["requested_target"] == local_route["snap_end"]["position"],
             "DIAGNOSTIC_IDENTITY_LOST")
    hosted_parts = []
    if hosted_route.get("geometry_path"):
        path = relative(root, hosted_route["geometry_path"])
        need(hash_file(path) == hosted_route["geometry_sha256"], "HOSTED_GEOMETRY_SHA_MISMATCH")
        hosted_parts = line_parts(read(path))
        receipt = hosted_route["receipt"]
        params = receipt["parameters"]
        waypoints = explicit_request(params["waypoints"])
        need(len(waypoints) == 2 and all(measure(a, b) < .001 for a, b in
                                         zip(waypoints, [scene["start"], scene["target"]])), "HOSTED_REQUEST_CHANGED")
        need(params["mode"] == "walk" and params["type"] == "balanced", "HOSTED_PROFILE_CHANGED")
        need(hosted_parts and hosted_parts[-1][-1] == hosted_route["route_endpoint_wgs84"],
             "HOSTED_RETURNED_ENDPOINT_MISMATCH")
        if hosted_route.get("raw_response_path"):
            path = relative(root, hosted_route["raw_response_path"])
            need(hash_file(path) == hosted_route["raw_response_sha256"], "HOSTED_RAW_SHA_MISMATCH")
            raw = read(path)
            need(raw.get("features") and line_parts(raw["features"][0]) == hosted_parts,
                 "HOSTED_NORMALIZED_GEOMETRY_DIFFERS_FROM_RAW")
            rows["hosted_raw_features"] = len(raw["features"])
            feature_waypoints = raw["features"][0]["properties"].get("waypoints") or []
            if feature_waypoints and all("location" in w for w in feature_waypoints):
                rows["hosted_feature_waypoint_offset_to_request_m"] = [
                    measure(w["location"], target) for w,target in zip(feature_waypoints, [scene["start"],scene["target"]])]
            rows["hosted_explicit_snap_available"] = bool(hosted_route.get("snap_start") or hosted_route.get("snap_end"))
    rows["hosted_verified_static_requests"] = verify_static_requests(scene, hosted)
    rows["hosted_returned_route"] = route_measure(hosted_parts, scene)
    if rows["hosted_returned_route"] and hosted_route.get("geometry_length_m_wgs84") is not None:
        need(abs(rows["hosted_returned_route"]["length_m"] - hosted_route["geometry_length_m_wgs84"]) < .1,
             "HOSTED_RECOMPUTED_LENGTH_MISMATCH")
    for side, record, overlay in (("local", local, "route"), ("hosted", hosted, "overlay")):
        views = record.get("views") or {}
        rows[side+"_verified_png"] = sum(
            verify_png(root, v, field, (scene["views"][kind]["width"], scene["views"][kind]["height"]))
            for kind, v in views.items() for field in ("base", overlay)
        )
    return rows


def verify(root):
    contract_path = root/"runs/scene_contracts.json"
    contracts = index(read(contract_path))
    local_path, hosted_path = root/"runs/local_results.json", root/"runs/hosted_results.json"
    local = read(local_path) if local_path.exists() else {"scenes":[]}
    hosted = read(hosted_path) if hosted_path.exists() else {"scenes":[]}
    contract_sha = hash_file(contract_path)
    for raw in (local,hosted):
        if raw["scenes"]:
            need(raw.get("scene_contract_sha256", raw.get("scene_contracts_sha256")) == contract_sha,
                 "RESULT_FREEZE_SHA_MISMATCH")
            need(set(index(raw)) == set(contracts), "FROZEN_SCENE_MISSING_FROM_RESULTS")
    index_a, index_b = index(local), index(hosted)
    for scene in hosted["scenes"]:
        attempted = [row["operation"] for row in scene.get("requests", []) if row.get("execution") == "LIVE"]
        need(len(attempted) == len(set(attempted)) and len(attempted) <= 5,
             "HOSTED_DUPLICATE_OR_OVER_BUDGET_SCENE_OPERATION")
    statuses = Counter((row.get("receipt") or {}).get("status_code") for scene in hosted["scenes"]
                       for row in scene.get("requests", []) if row.get("execution") == "LIVE")
    total = sum(statuses.values())
    need(total == hosted.get("requests_attempted", 0) and total <= 25, "HOSTED_REQUEST_COUNT_MISMATCH")
    result = {
        "audit_scope": "R3 artifact hash, request identity, WGS84 geodesic and PNG shape",
        "r3_scene_contract_sha256": contract_sha,
        "scenes": [verify_scene(root, c, index_a.get(id_, {}), index_b.get(id_, {})) for id_,c in contracts.items()],
        "hosted_attempt_count": total, "hosted_http_status_counts": {str(k):v for k,v in statuses.items()},
        "local_results_retained": bool(local["scenes"]), "hosted_results_retained": bool(hosted["scenes"]),
        "visual_ratings_filled": 0, "site_validations": 0,
        "review_context": "Adapter author independently verified local and hosted evidence; does not audit own CIR.",
    }
    return result



ORIGINAL_SCORE = "user_scores_20261109T110307129Z.csv"
SCORE_SHA256 = "bf9031591b4d67be39ec7e0239432116a01f3197b414e88d3e8a682a68db108a"
BLOCKED = {".git", "runtime", "private_local", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def check_summary(root, receipts):
    summary = read(root / "runs/summary.json")
    rows = receipts["scenes"]
    need(summary["new_frozen_buildings"] == len(rows) and
         summary["local_request_routes_returned"] == sum(bool(r["local_target_route"]) for r in rows) and
         summary["hosted_routes_returned"] == sum(bool(r["hosted_returned_route"]) for r in rows) and
         summary["osm_tagged_target_references"] == sum(r["target_grade"] == "OSM_TAGGED" for r in rows) and
         summary["hosted_requests_attempted"] == receipts["hosted_attempt_count"] and
         summary["http_200_count"] == receipts["hosted_http_status_counts"].get("200", 0), "SUMMARY_COUNT_MISMATCH")
    need(summary["new_field_checks"] == 0 and summary["human_visual"] == "PENDING_USER_REVIEW" and
         summary["gpt_acceptance"] == "PENDING_GPT_REVIEW", "SUMMARY_MISSTATES_HUMAN_VALIDATION")
    with (root/"runs/comparison.csv").open(encoding="utf-8-sig", newline="") as stream:
        compare = list(csv.DictReader(stream))
    historical = [row for row in compare if row["historical"] == "True"]
    fresh = {row["scene_id"]: row for row in compare if row["historical"] == "False"}
    need(len(historical) == summary["historical_buildings"] and len(fresh) == len(rows) and
         len(compare) == len(fresh)+len(historical), "COMPARISON_FROZEN_DENOMINATOR_CHANGED")
    for r in rows:
        row = fresh[r["scene_id"]]
        local = r["local_target_route"]
        hosted = r["hosted_returned_route"]
        need(row["target_role"] == r["target_grade"] and row["local_status"] == r["local_status"] and
             (row["local_failure"] or None) == r["local_failure_reason"], "COMPARISON_CASE_IDENTITY_CHANGED")
        if local:
            need(abs(float(row["local_length_m"]) - local["length_m"]) < .1 and
                 abs(float(row["local_snap_m"]) - local["target_gap_m"]) < .1, "COMPARISON_LOCAL_METRIC_MISMATCH")
        if hosted:
            need(abs(float(row["hosted_route_m"]) - hosted["length_m"]) < .1 and
                 abs(float(row["hosted_target_gap_m"]) - hosted["target_gap_m"]) < .1, "COMPARISON_HOSTED_METRIC_MISMATCH")
    status = read(root/"STATUS.json")
    need(all(status.get(key) == value for key,value in summary.items()), "STATUS_SUMMARY_DISAGREE")
    need(status["status"] == "READY_FOR_USER_VISUAL_REVIEW" and status["judgment"] == "INCONCLUSIVE" and
         status["dual_paths"] == "RETAIN", "STATUS_CONFUSES_TECHNICAL_DELIVERY_AND_SELECTION")
    decision = (root/"05_DECISION_ON_TWO_PATHS.md").read_text(encoding="utf-8")
    need(all(token in decision for token in ("INCONCLUSIVE", "保留本地 OSM 与 Geoapify 两条数据路径",
                                               "没有独立路径真值", "用户盲评仍待填写", "拓扑机制")),
         "DECISION_DOES_NOT_DISCLOSE_EVIDENCE_BOUNDARY")
    return {"frozen_rows": len(fresh), "historical_rows": len(historical), "selected_counts": "PASS",
            "technical_delivery": status["status"], "evidence_verdict": status["judgment"],
            "decision": status["dual_paths"], "human_review_pending": True, "gpt_review_pending": True}


def check_scores(root):
    originals = sorted((root / "inputs").rglob(ORIGINAL_SCORE))
    need(bool(originals), "MISSING_ORIGINAL_USER_SCORE")
    for path in originals:
        need(hash_file(path) == SCORE_SHA256, "ORIGINAL_USER_SCORE_CHANGED")
    with (root / "07_USER_SCORE_SHEET.csv").open(encoding="utf-8-sig", newline="") as stream:
        scores = csv.DictReader(stream)
        identity = ("blind_scene_id", "detail_pair_id", "context_pair_id")
        need(tuple(scores.fieldnames[:3]) == identity, "BLIND_SCORE_IDENTITY_CHANGED")
        rows = list(scores)
    need(len(rows) == len({row["blind_scene_id"] for row in rows}), "BLIND_SCORE_IDS_NOT_UNIQUE")
    need(all(all(row[key] for key in identity) and not any(value for key, value in row.items() if key not in identity)
             for row in rows), "R3_HUMAN_SCORES_MUST_BE_BLANK")
    return {"original_score_copies_verified": len(originals), "empty_r3_rows": len(rows)}


def check_indexes(root):
    count = {}
    for label, index_path, col in (("historical_copies", "audits/historical_sources.csv", "relative_copy"),
                                   ("data_artifacts", "data/manifest.csv", "path")):
        checked = 0
        with (root/index_path).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row[col]:
                    path = relative(root,row[col])
                    need(path.stat().st_size == int(row["bytes"]) and hash_file(path) == row["sha256"],
                         "INDEX_ARTIFACT_DIGEST_MISMATCH")
                    checked += 1
        count[label] = checked
    return count


def safe_zip_member(info):
    raw = info.filename
    path = PurePosixPath(raw)
    need(bool(raw) and raw == path.as_posix() and not path.is_absolute() and ".." not in path.parts,
         "ARCHIVE_UNSAFE_MEMBER_PATH")
    for token in path.parts:
        folded = token.casefold()
        need(chr(92) not in token and ":" not in token and token.rstrip(". ") == token and
             not re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", token.split(".", 1)[0].upper()) and
             folded not in BLOCKED and
             not (folded.startswith(".env") and folded != ".env.example") and
             not any(mark in folded for mark in ("blind_mapping", "blind_reveal_map_private")), "ARCHIVE_PRIVATE_OR_UNSAFE_MEMBER")
    need(not stat.S_ISLNK(info.external_attr >> 16) and not info.is_dir() and
         path.suffix.casefold() not in {".har", ".sqlite", ".pyc", ".pbf"}, "ARCHIVE_UNEXPECTED_FORMAT")
    return path


def unpack(archive, root):
    with ZipFile(archive) as book:
        members, folded_names = {}, set()
        infos = book.infolist()
        need(sum(info.file_size for info in infos) < 200 * 1024**2, "ARCHIVE_REVIEW_SIZE_LIMIT")
        for info in infos:
            path = safe_zip_member(info)
            name = path.as_posix()
            need(name.casefold() not in folded_names and info.file_size < 30 * 1024**2,
                 "ARCHIVE_DUPLICATE_OR_OVERSIZED_MEMBER")
            folded_names.add(name.casefold())
            members[name] = path
        need(book.testzip() is None, "ARCHIVE_BAD_CRC")
        entries = json.loads(book.read("MANIFEST.json"))["entries"]
        need(len(entries) == len(members) - 1 and
             {entry["path"] for entry in entries} == set(members) - {"MANIFEST.json"}, "ARCHIVE_MANIFEST_COVERAGE")
        for name, member in members.items():
            destination = root.joinpath(*member.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(book.read(name))
        for entry in entries:
            path = root / entry["path"]
            need(path.stat().st_size == entry["bytes"] and hash_file(path) == entry["sha256"],
                 "ARCHIVE_MEMBER_MANIFEST_MISMATCH")
    return {"archive_sha256": hash_file(archive), "archive_bytes": archive.stat().st_size,
            "archive_members": len(members), "manifest_entries": len(entries),
            "crc": "PASS", "private_or_unsafe_members": 0}


def check_browser(root, score_count):
    from playwright.sync_api import sync_playwright
    calls, errors = [], []
    image_count = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(EDGE), headless=True, timeout=15000,
                                     args=["--disable-background-networking", "--no-first-run"])
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        page.set_default_timeout(12000)

        def no_http(route):
            calls.append("EXTERNAL")
            route.abort()

        page.route("http://**/*", no_http)
        page.route("https://**/*", no_http)
        page.on("pageerror", lambda error: errors.append(str(error)))
        for document in ("visuals/blind_review/index.html", "visuals/routes/index.html",
                         "visuals/failure_cases/index.html"):
            page.goto((root / document).as_uri(), wait_until="load")
            need(bool(page.locator("h1").first.text_content()), "BROWSER_MISSING_PAGE")
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open=true);")
            page.evaluate("document.querySelectorAll('img').forEach(i => i.loading='eager');")
            page.wait_for_function("Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)")
            image_count += page.locator("img").count()

        page.goto((root / "visuals/blind_review/score.html").as_uri(), wait_until="load")
        need(page.locator("#scores fieldset").count() == score_count, "BROWSER_BLIND_SCORE_ROW_COUNT")
        need(page.evaluate("Array.from(document.querySelectorAll('#scores select, #scores textarea'))"
                           ".every(el => el.value === '')"), "BROWSER_PREFILLED_HUMAN_SCORES")
        if score_count:
            first = page.locator("#scores select").first
            first.select_option("3")
            with page.expect_download() as exported:
                page.locator("#scores button[type=submit]").click()
            with exported.value.path().open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            need(len(rows) == score_count and rows[0][first.get_attribute("name")] == "3",
                 "BROWSER_SCORE_CSV_EXPORT_MISMATCH")
        browser.close()
    need(not calls and not errors, "BROWSER_NETWORK_OR_JS_ERRORS")
    return {"status": "PASS", "offline_gallery_pages": 3, "decoded_image_occurrences": image_count,
            "blank_score_fields": True, "test_csv_export": bool(score_count),
            "test_score_is_browser_only": True, "external_requests": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    if args.archive:
        need(args.scratch is not None, "ARCHIVE_NEEDS_ISOLATED_SCRATCH")
        args.scratch.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.scratch) as tmp:
            root = Path(tmp).resolve()
            result = unpack(args.archive, root)
            result["source_and_geometry"] = verify(root)
            result["comparison_summary"] = check_summary(root, result["source_and_geometry"])
            result["score_sheets"] = check_scores(root)
            result["artifact_indexes"] = check_indexes(root)
            if args.browser:
                result["offline_browser"] = check_browser(root, result["score_sheets"]["empty_r3_rows"])
    else:
        result = verify(args.root)
        if args.browser:
            result["comparison_summary"] = check_summary(args.root, result)
            result["score_sheets"] = check_scores(args.root)
            result["offline_browser"] = check_browser(args.root, result["score_sheets"]["empty_r3_rows"])
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
