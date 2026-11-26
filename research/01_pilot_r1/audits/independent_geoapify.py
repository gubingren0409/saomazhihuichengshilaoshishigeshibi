"""Independently verify saved hosted maps and shared requests without provider access."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from math import atan, degrees, exp, log, pi, radians, tan
from pathlib import Path
import re

from geographiclib.geodesic import Geodesic
import numpy as np
from PIL import Image
from shapely.geometry import LineString, Polygon

SCENE_SHA = "12f457f66fe107f44c47fd57bf884087562d3aef5d30278a65b0d2e8b2cba01b"
BLANK_CSV_SHA = "17a0f3e44b8d28617d7a647eb9327f99094c9653fa6ad0e5bcd045f68af397e9"
OLD_ZIP_SHA = "c717dd1958d73fb92476624640ad46f1ccca3a792e2016c849649bb0e812d870"
RADIUS = 6378137.0
GEOD = Geodesic.WGS84
DIMENSIONS = (1200, 900)
EXPECTED_STATIC = "https://maps.geoapify.com/v1/staticmap"
GEOMETRY_PATTERN = re.compile(r"circle:(-?[\d.]+),(-?[\d.]+),([\d.]+)")
HEX_PATTERN = re.compile(r"(?:fillcolor|linecolor):(?:#|%23)?([\da-f]{6})(?:[\da-f]{2})?(?=;|$)", re.I)


def get_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def local_path(root, relative):
    assert isinstance(relative, str) and "?" not in relative and "#" not in relative
    path = (root / relative).resolve()
    assert path.is_relative_to(root) and path.is_file()
    return path


def distance(a, b):
    return GEOD.Inverse(a[1], a[0], b[1], b[0])["s12"]


def mercator(pair):
    lon, lat = pair
    return RADIUS * radians(lon), RADIUS * log(tan(pi / 4 + radians(lat) / 2))


def inverse(x, y):
    return degrees(x / RADIUS), degrees(2 * atan(exp(y / RADIUS)) - pi / 2)


def require_no_auth_fields(receipt):
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = key.lower().replace("-", "").replace("_", "")
                assert normalized not in {"apikey", "xapikey", "cookie"}
                if normalized == "authorization":
                    assert isinstance(item, str) and re.fullmatch(r"USER_(?:AUTHORIZED|REQUESTED)_[A-Z0-9_]+", item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            assert not re.search(r"(?i)(?:[?&]apiKey=|x-api-key\s*:|Cookie\s*:)", value)
    walk(receipt)


def audit_walk(root, scene):
    route_receipt_path = root / "runs/geoapify_walk_probe_proxy.json"
    record = get_json(route_receipt_path)
    require_no_auth_fields(record)
    receipt, route = record["receipt"], record["route"]
    assert receipt["endpoint"] == "https://api.geoapify.com/v1/routing"
    assert receipt["execution"] == "LIVE" and receipt["status_code"] == 200
    assert route["mode"] == "walk" and route["crs"] == "EPSG:4326"
    assert route["requested_start_wgs84"] == scene["start"] and route["requested_target_wgs84"] == scene["target"]
    query_waypoints = "|".join(f"lonlat:{lon:.9f},{lat:.9f}" for lon, lat in (scene["start"], scene["target"]))
    assert receipt["parameters"]["waypoints"] == query_waypoints and receipt["parameters"]["mode"] == "walk"
    ref = record["geojson"]
    path = local_path(root, ref["path"])
    assert hash_file(path) == ref["sha256"]
    geometry = get_json(path)
    assert geometry["type"] == "FeatureCollection" and geometry["features"]
    coords = []
    for feature in geometry["features"]:
        item = feature["geometry"]
        assert item["type"] == "LineString"
        line = item["coordinates"]
        assert len(line) >= 2 and all(len(p) == 2 and abs(p[0]) <= 180 and abs(p[1]) <= 90 for p in line)
        coords.append(line)
    assert coords[0][0] == route["route_start_wgs84"] and coords[-1][-1] == route["route_endpoint_wgs84"]
    outline = Polygon([mercator(p) for p in scene["building_footprint"]["coordinates"][0]])
    local = get_json(root / "runs/local_approach_diagnostic.json")
    local_main = get_json(root / "runs/local_route.json")
    assert local_main["status"] == "NO_ROUTE" and local_main["geometry"] is None
    assert local["parent_failure"] == local_main["failure_reason"] and local["missing_segment_drawn"] is False
    return {
        "live_receipt_sha256": hash_file(route_receipt_path), "geojson_sha256": hash_file(path),
        "provider_declared_length_m": route["provider_distance_m"],
        "provider_duration_s": route["provider_duration_s"],
        "independent_wgs84_geometry_m": sum(distance(a, b) for line in coords for a, b in zip(line, line[1:])),
        "segment_count": len(coords), "vertex_count": sum(map(len, coords)),
        "origin_offset_m": distance(coords[0][0], scene["start"]),
        "frozen_entrance_offset_m": distance(coords[-1][-1], scene["target"]),
        "offset_from_local_diagnostic_endpoint_m": distance(coords[-1][-1], local["route_end"]),
        "planar_target_interior_intersection_mercator_m": sum(LineString([mercator(p) for p in line])
            .intersection(outline.buffer(-.5)).length for line in coords),
        "source_entrance_identity": route["entrance_identity"],
        "credits_observed": receipt["actual_credits"], "route_is_complete_to_entrance": False,
    }


def png_metadata(path, expected_sha=None):
    value = hash_file(path)
    if expected_sha is not None:
        assert value == expected_sha
    with Image.open(path) as image:
        assert image.format == "PNG" and image.size == DIMENSIONS
        image.verify()
    return {"sha256": value, "bytes": path.stat().st_size, "size": list(DIMENSIONS)}


def independent_camera_fit(path, request, reference, controls):
    values = request["parameters"]["geometry"]
    commands = values if isinstance(values, list) else values.split("|")
    left, bottom, right, top = reference["extent_3857"]
    width, height = DIMENSIONS
    with Image.open(path) as im:
        image = np.asarray(im.convert("RGB"))
    expected = {row["color"].lstrip("#").lower(): row["wgs84"] for row in controls}
    assert len(expected) == 4
    found = []
    used_colors = set()
    for command in commands:
        match = GEOMETRY_PATTERN.match(command)
        shades = HEX_PATTERN.findall(command)
        if not match or not shades:
            continue
        lon, lat, radius = map(float, match.groups())
        # Restrict extraction to explicitly submitted color pixels near this control.
        x, y = mercator((lon, lat))
        px = (x - left) * width / (right - left)
        py = (top - y) * height / (top - bottom)
        x0, x1 = max(0, int(px - 85)), min(width, int(px + 86))
        y0, y1 = max(0, int(py - 85)), min(height, int(py + 86))
        if x1 <= x0 or y1 <= y0:
            continue
        for color in dict.fromkeys(reversed(shades)):
            if color.lower() in used_colors or color.lower() not in expected:
                continue
            assert all(abs(a-b) <= 1e-9 for a,b in zip((lon,lat),expected[color.lower()]))
            rgb = np.array(list(bytes.fromhex(color)), dtype=np.uint8)
            ys, xs = np.nonzero(np.all(image[y0:y1, x0:x1] == rgb, axis=2))
            if len(xs) < 3:
                continue
            observed = (float(xs.mean() + x0 + .5), float(ys.mean() + y0 + .5))
            found.append((x, y, *observed, color.lower(), len(xs)))
            used_colors.add(color.lower())
            break
    assert len(found) == 4, f"Expected 4 synthetic controls, got {len(found)}"
    control = np.array([row[:4] for row in found])
    center_x, center_y = (left + right) / 2, (bottom + top) / 2
    dx, dy = control[:, 0] - center_x, control[:, 1] - center_y
    # Fit independent east and north axes, with mean-centered metre coordinates.
    px_coef = np.linalg.lstsq(np.column_stack((dx, np.ones(len(found)))), control[:, 2], rcond=None)[0]
    py_coef = np.linalg.lstsq(np.column_stack((dy, np.ones(len(found)))), control[:, 3], rcond=None)[0]
    residual = np.hypot(control[:, 2] - (dx * px_coef[0] + px_coef[1]),
                        control[:, 3] - (dy * py_coef[0] + py_coef[1]))
    assert px_coef[0] > 0 and py_coef[0] < 0
    w = center_x - px_coef[1] / px_coef[0]
    e = center_x + (width - px_coef[1]) / px_coef[0]
    n = center_y - py_coef[1] / py_coef[0]
    s = center_y + (height - py_coef[1]) / py_coef[0]
    return {"control_count": len(found), "fit_max_residual_px": float(residual.max()),
            "reference_center_mercator": [center_x,center_y], "px_coef": px_coef.tolist(), "py_coef": py_coef.tolist(),
            "rendered_control_centers_px": [[row[2], row[3]] for row in found],
            "extent_wsen": [*inverse(w, s), *inverse(e, n)],
            "ground_m_per_px_at_center": distance(inverse(center_x, center_y), inverse(center_x + 1/px_coef[0], center_y)),
            "abs_bbox_offsets_in_reference_pixels": [abs(w-left)*width/(right-left), abs(s-bottom)*height/(top-bottom),
                                                     abs(e-right)*width/(right-left), abs(n-top)*height/(top-bottom)]}



def decode_polyline(token, precision=6):
    stream = iter(token)
    lng, lat = 0, 0
    result = []
    factor = 10 ** precision
    while True:
        head = next(stream, None)
        if head is None:
            break
        numbers = []
        for index in range(2):
            first = head if index == 0 else next(stream, None)
            assert first is not None
            value, shift = 0, 0
            current = first
            while True:
                bits = ord(current) - 63
                assert 0 <= bits < 64 and shift < 40
                value += (bits & 31) << shift
                shift += 5
                if bits < 32:
                    break
                current = next(stream)
            numbers.append(~(value >> 1) if value & 1 else value >> 1)
        lat, lng = lat + numbers[0], lng + numbers[1]
        result.append([lng / factor, lat / factor])
    return result


def route_color_support(base_path, overlay_path, line, camera, rgb):
    def project(value):
        x, y = mercator(value)
        cx, cy = camera["reference_center_mercator"]
        a, c = camera["px_coef"]
        b, d = camera["py_coef"]
        return (a*(x-cx)+c,b*(y-cy)+d)
    with Image.open(base_path) as base_image, Image.open(overlay_path) as route_image:
        base = np.asarray(base_image.convert("RGB"))
        overlay = np.asarray(route_image.convert("RGB"))
    rgb_array = np.asarray(list(bytes.fromhex(rgb)),dtype=np.uint8)
    changed = np.any(base != overlay,axis=2)
    known_ink = np.all(overlay == rgb_array,axis=2) & changed
    from shapely.geometry import box
    frame = box(8,8,DIMENSIONS[0]-8,DIMENSIONS[1]-8)
    tested, hits = 0, 0
    for trace in line:
        support = LineString([project(p) for p in trace]).intersection(frame)
        if support.is_empty or support.length <= 0:
            continue
        for fraction in np.linspace(.04,.96,32):
            sample = support.interpolate(float(fraction),normalized=True)
            x,y = int(sample.x),int(sample.y)
            tested += 1
            hits += bool(known_ink[y-4:y+5,x-4:x+5].any())
    return {"tested_visible_samples": tested, "samples_supported_by_overlay_line_color": hits,
            "matching_fraction": hits/tested if tested else None, "exact_route_color_changed_pixels": int(known_ink.sum()),
            "base_and_overlay_equal_pixel_fraction": 1-float(changed.mean())}


def audit_static(root, scene):
    receipt_path = root / "runs/geoapify_static_requests.json"
    document = get_json(receipt_path)
    require_no_auth_fields(document)
    assert document["scene_contract_sha256"] == SCENE_SHA
    assert document["status"] == "FOUR_LIVE_STATIC_IMAGES" and document["route_requests"] == 0
    route_path = local_path(root,document["route_geojson"]["path"])
    assert hash_file(route_path) == document["route_geojson"]["sha256"]
    lines = [feature["geometry"]["coordinates"] for feature in get_json(route_path)["features"]]
    assert len(document["requests"]) == 4
    by_slot = {(row["view"], row["kind"]):row for row in document["requests"]}
    assert set(by_slot) == {(key,layer) for key in ("detail","context") for layer in ("base","route")}
    completed = get_json(root / "runs/geoapify_static_completion.json")
    assert completed["scene_id"] == scene["scene_id"]
    assert completed["real_static_requests"] == 4 and completed["new_route_requests"] == 0
    assert completed["route_geojson"] == document["route_geojson"]
    root_result = {"receipt_sha256": hash_file(receipt_path),
                   "completion_qa_sha256": hash_file(root / "runs/geoapify_static_completion.json"),
                   "live_static_calls": 4, "route_reruns": 0, "views": {}}
    for name, reference in scene["views"].items():
        paths = {}
        details = {}
        for layer in ("base", "route"):
            row = by_slot[(name,layer)]
            assert row["status"] == "LIVE_SAVED"
            receipt = row["receipt"]
            assert receipt["execution"] == "LIVE" and receipt["status_code"] == 200
            assert receipt["endpoint"] == EXPECTED_STATIC and receipt["content_type"] == "image/png"
            params = receipt["parameters"]
            assert params["attribution"] == "default" and params["style"] == "osm-bright-smooth"
            assert params["format"] == "png" and params["scaleFactor"] == 1
            assert params["bearing"] == params["pitch"] == 0
            assert (params["width"],params["height"]) == DIMENSIONS
            assert params["area"] == "rect:" + ",".join(f"{num:.9f}" for num in reference["bounds"])
            assets = row["asset"]
            path = local_path(root,assets["path"])
            assert path.parent == root / "visuals/geoapify"
            assert path.name == f"{scene['scene_id']}_{name}_{layer}.png"
            paths[layer] = path
            details[layer] = png_metadata(path,assets["sha256"])
            assert details[layer]["bytes"] == assets["bytes"] == receipt["response_bytes"]
        bare, overlaid = by_slot[(name,"base")]["receipt"], by_slot[(name,"route")]["receipt"]
        assert not by_slot[(name,"base")]["controls"] and "geometry" not in bare["parameters"]
        assert bare["parameters"] == {k:v for k,v in overlaid["parameters"].items() if k != "geometry"}
        geometries = overlaid["parameters"]["geometry"]
        polylines = re.findall(r"(?:^|\|)polyline6:([^;]+);linecolor:#([\da-f]{6});", geometries)
        assert len(polylines) == len(lines)
        assert [decode_polyline(item[0]) for item in polylines] == lines
        camera = independent_camera_fit(paths["route"],overlaid,reference,by_slot[(name,"route")]["controls"])
        color = route_color_support(paths["base"],paths["route"],lines,camera,polylines[0][1])
        reported = completed["views"][name]
        assert reported["bounds_match"] is True and reported["actual_bounds"] == reference["bounds"]
        assert reported["pixel_size"] == list(DIMENSIONS)
        assert all(reported[layer] == by_slot[(name,layer)]["asset"]["path"]
                   and reported[layer+"_sha256"] == details[layer]["sha256"] for layer in ("base","route"))
        assert all(term in reported["attribution"] for term in ("OpenStreetMap", "OpenMapTiles", "Geoapify"))
        assert abs(reported["meters_per_pixel"] - camera["ground_m_per_px_at_center"]) < .0001
        assert abs(reported["alignment"]["base_overlay_identical_pixel_fraction"] -
                   color["base_and_overlay_equal_pixel_fraction"]) < 1e-12
        assert camera["fit_max_residual_px"] <= 1 and max(camera["abs_bbox_offsets_in_reference_pixels"]) <= 2
        assert color["tested_visible_samples"] and color["matching_fraction"] >= .90
        assert color["base_and_overlay_equal_pixel_fraction"] >= .96
        root_result["views"][name] = {"images": details, "independent_camera_fit": camera, "route_color_validation": color,
                                      "attribution_request": "default", "actual_credits_observed": None}
    return root_result


def local_image_hashes(root):
    names = [f"sh-huangpu-01_{view}_{layer}.png" for view in ("detail","context") for layer in ("base","route")]
    return [png_metadata(root/"visuals/osm"/name)["sha256"] for name in names]


def audit_blind_csv(root):
    path = root / "06_USER_SCORE_SHEET.csv"
    data = hash_file(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    filled = sum(bool(value) for value in list(rows[0].values())[3:])
    if data == BLANK_CSV_SHA:
        assert filled == 0
    return {"sha256": data, "same_as_initial_blank_template": data == BLANK_CSV_SHA,
            "filled_items_observed": filled, "reviewer_edited_scores": False}


def audit(root, browser=False, viewer=False):
    scene_path = root / "runs/scene_contract.json"
    assert hash_file(scene_path) == SCENE_SHA
    scene = get_json(scene_path)
    assert scene["scene_id"] == "sh-huangpu-01" and scene["frozen_before_route"]
    summary = {"reviewer": "/root/osm_review", "provider_calls": 0, "scene_contract_sha256": SCENE_SHA,
               "route": audit_walk(root, scene), "score": audit_blind_csv(root)}
    original = root / "delivery/OPEN_REVIEW.zip"
    if original.exists():
        assert hash_file(original) == OLD_ZIP_SHA
        summary["original_sealed_zip_sha256"] = OLD_ZIP_SHA
    summary["static"] = audit_static(root,scene)
    if browser:
        from independent_ab_browser import verify_browser
        hashes = local_image_hashes(root) + [item["sha256"] for view in summary["static"]["views"].values()
                 for item in view["images"].values()]
        summary["browser"] = verify_browser(root,hashes,check_viewer=viewer)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--browser",action="store_true")
    parser.add_argument("--viewer",action="store_true")
    args = parser.parse_args()
    result = audit(args.root.resolve(),args.browser,args.viewer)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Independent hosted artifact checks completed.")
