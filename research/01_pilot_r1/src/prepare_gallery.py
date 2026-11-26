"""Bridge verified local render receipts and hosted artifacts to the blind gallery."""
from hashlib import sha256
import json
from math import isfinite

from .gallery import build
from .route_viewer import write_viewer
from .scene import ROOT, dump


HOSTED_ATTRIBUTION = "© OpenStreetMap contributors · © OpenMapTiles · Powered by Geoapify"
METRICS = ("pixel_size", "target_pixel_size", "actual_bounds", "meters_per_pixel", "target_area_ratio")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hosted_view(view, record):
    bounds = record.get("actual_bounds")
    bounded = (
        isinstance(bounds, list) and len(bounds) == 4
        and all(type(v) in (int, float) and isfinite(v) for v in bounds)
    )
    exact = bounded and all(abs(a - b) <= 1e-9 for a, b in zip(bounds, view["bounds"]))
    corner_error = record.get("max_corner_error_css_px")
    verified = exact or (
        bounded and record.get("bounds_match") is True
        and type(corner_error) in (int, float) and 0 <= corner_error <= 1
    )
    status = record.get("status", "NOT_RUN")
    if record.get("base") and status not in {"VIEWPORT_MISMATCH", "VIEWPORT_NOT_VERIFIED"}:
        status = "LIVE" if verified else "VIEWPORT_MISMATCH" if bounded else "VIEWPORT_NOT_VERIFIED"
    return {
        "status": status,
        "base": record.get("base"),
        "route": record.get("route"),
        "route_identity": record.get("route_identity") or ("HOSTED_WALK_ROUTE" if record.get("route") else None),
        "route_target_offset_m": record.get("route_target_offset_m"),
        "route_control_points": record.get("route_control_points"),
        "qa": {key: record[key] for key in METRICS if key in record},
        "human_display_verified": record.get("human_display_verified") is True,
        "local_retention_verified": record.get("local_retention_verified") is True,
        "attribution_burned_in": record.get("attribution_burned_in") is True,
        "attribution": record.get("attribution", HOSTED_ATTRIBUTION),
    }


def completed_viewer(root, scene_id, reference):
    if isinstance(reference, str):
        reference = {"path": reference}
    source = (root / reference["path"]).resolve()
    if not source.is_relative_to(root) or source.suffix.lower() != ".geojson":
        raise ValueError("Hosted route must be a retained GeoJSON artifact in the pilot.")
    data = source.read_bytes()
    if reference.get("sha256") and sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError("Hosted route receipt and GeoJSON SHA256 differ.")
    route = json.loads(data)
    if route.get("type") == "FeatureCollection":
        features = route.get("features", [])
        if len(features) != 1:
            raise ValueError("Multiple hosted route segments require an explicit multi-segment viewer.")
        route = features[0]
    geometry = route.get("geometry", route)
    if geometry.get("type") != "LineString":
        raise ValueError("Hosted route requires a verified WGS84 LineString.")

    cases = read_json(root / "runs/maplibre_viewer_input.json")
    [case] = [item for item in cases if item["scene_id"] == scene_id]
    case["routes"]["geoapify"] = geometry
    dump(root / "runs/maplibre_viewer_input_completed.json", cases)
    return write_viewer(cases, root / "visuals/route_comparisons/index.html", root)


def main(root=ROOT):
    root = root.resolve()
    scene = read_json(root / "runs/scene_contract.json")
    local = read_json(root / "runs/local_viewports.json")
    remote = read_json(root / "runs/geoapify_first.json")
    completion_path = root / "runs/geoapify_static_completion.json"
    completion = read_json(completion_path) if completion_path.is_file() else {}
    if completion and completion["scene_id"] != scene["scene_id"]:
        raise ValueError("Hosted completion is for a different frozen scene.")

    route_probe_path = root / "runs/geoapify_walk_probe_proxy.json"
    probe = read_json(route_probe_path) if completion and route_probe_path.is_file() else {}
    offset = probe.get("route", {}).get("target_offset_m") if probe.get("scene_id") == scene["scene_id"] else None
    available = {entry["operation"]: entry for entry in remote["requests"]
                 if entry.get("state") == "LIVE_SAVED" and "asset" in entry}
    result = {"scene_id": scene["scene_id"], "label": scene["label"], "views": {}}
    for name, view in scene["views"].items():
        info = local["views"][name]
        current = completion.get("views", {}).get(name)
        if current:
            geo = hosted_view(view, {"route_target_offset_m": offset, **current})
        elif name in available:
            receipt = available[name]["receipt"]
            geo = hosted_view(view, {
                "base": available[name]["asset"]["path"],
                "pixel_size": [view["width"], view["height"]],
                "actual_bounds": receipt.get("actual_bounds"),
                "human_display_verified": True,
                "local_retention_verified": True,
            })
        else:
            geo = {"status": remote["branch_status"], "base": None, "route": None}
        result["views"][name] = {"center": view["center"], "bounds": view["bounds"], "assets": {
            "osm": {"status": "LOCAL_REAL", "base": info["base"], "route": info["route"],
                    "route_identity": info.get("overlay_identity"), "attribution_burned_in": True,
                    "qa": {key: info[key] for key in METRICS}},
            "geoapify": geo}}
    path = root / "runs/gallery_input.json"
    dump(path, {"scenes": [result]})
    summary = build(root, path)
    reference = completion.get("route_geojson")
    if reference and completion.get("route_display_verified") is True:
        viewer = completed_viewer(root, scene["scene_id"], reference)
        summary["route_viewer"] = viewer.relative_to(root).as_posix()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
