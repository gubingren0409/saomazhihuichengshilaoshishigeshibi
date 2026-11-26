"""Replay the fixed OSM scene, local route, and directly georeferenced PNGs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from shapely import LineString, Polygon, box

from .local_route import route_osm
from .render_osm import base_map, pixel, prepare, route_overlay
from .scene import FORWARD, HEIGHT, ROOT, WIDTH, dump


def feature(result, purpose):
    return {"type": "Feature", "geometry": result.get("geometry"),
            "properties": {"purpose": purpose, "status": result["status"],
                           "failure_reason": result.get("failure_reason"),
                           "length_m": result.get("length_m"), "end": result.get("route_end"),
                           "way_ids": result.get("way_ids", [])}}


def main(root=ROOT, output=None):
    output = root if output is None else output
    snapshot_path = root / "data/sh-huangpu-01.osm.json"
    scene = json.loads((root / "runs/scene_contract.json").read_text(encoding="utf-8"))
    if sha256(snapshot_path.read_bytes()).hexdigest() != scene["snapshot_sha256"]:
        raise ValueError("FROZEN_SNAPSHOT_MISMATCH")
    if (output / "runs/local_route.json").exists():
        raise FileExistsError("LOCAL_RUN_EXISTS_USE_FRESH_OUTPUT")
    osm = json.loads(snapshot_path.read_text(encoding="utf-8"))
    result = route_osm(osm, scene["start"], scene["target"], scene["path_snap_max_m"])
    result["scene_id"] = scene["scene_id"]
    result["identity"] = "LIVE_OSM_VECTOR_OFFLINE_ROUTING"
    result["target_identity"] = scene["target_role"]
    result["snapshot_sha256"] = scene["snapshot_sha256"]
    dump(output / "runs/local_route.json", result)
    dump(output / "runs/local_route.geojson", feature(result, "FROZEN_ENTRANCE_REQUEST"))

    overlay = result
    diagnostic = None
    if result["failure_reason"] == "TARGET_SNAP_OUTSIDE_LIMIT" and result.get("snap_end"):
        diagnostic = route_osm(osm, scene["start"], result["snap_end"]["position"], scene["path_snap_max_m"])
        diagnostic["identity"] = "PARTIAL_DIAGNOSTIC_TO_NEAREST_MAPPED_SEGMENT"
        diagnostic["parent_failure"] = result["failure_reason"]
        diagnostic["remaining_gap_to_original_target_m"] = result["snap_end_m"]
        diagnostic["missing_segment_drawn"] = False
        dump(output / "runs/local_approach_diagnostic.json", diagnostic)
        dump(output / "runs/local_approach_diagnostic.geojson", feature(diagnostic, diagnostic["identity"]))
        if diagnostic["status"] == "PASS":
            overlay = diagnostic

    features, points, missed = prepare(osm)
    polygon = Polygon([FORWARD(*p) for p in scene["building_footprint"]["coordinates"][0]])
    out_views = {}
    for name, view in scene["views"].items():
        base, extras = base_map(features, points, scene, view)
        route_picture, line_shown = route_overlay(base, scene, view, overlay)
        base_path = Path(f"visuals/osm/{scene['scene_id']}_{name}_base.png")
        route_path = Path(f"visuals/osm/{scene['scene_id']}_{name}_route.png")
        (output/base_path).parent.mkdir(parents=True, exist_ok=True)
        base.save(output/base_path, compress_level=6)
        route_picture.save(output/route_path, compress_level=6)
        extent = box(*view["extent_3857"])
        coords = [pixel(x,y,view) for x,y in polygon.exterior.coords]
        target_px = [max(p[k] for p in coords)-min(p[k] for p in coords) for k in (0,1)]
        target_area = polygon.intersection(extent).area / extent.area
        start_px = pixel(*FORWARD(*scene["start"]), view)
        target_px_point = pixel(*FORWARD(*scene["target"]), view)
        end = overlay.get("route_end")
        end_px = None if not end else pixel(*FORWARD(*end),view)
        shades = base.getcolors(WIDTH*HEIGHT)
        out_views[name] = {
            **view, **extras, "status": "PASS_LOCAL_GEOMETRY_RENDER",
            "actual_bounds": view["bounds"], "pixel_size": [WIDTH, HEIGHT],
            "target_pixel_size": target_px, "target_area_ratio": target_area,
            "building_fully_inside": extent.covers(polygon),
            "distinct_pixel_colors": len(shades) if shades else None,
            "label_visibility_assessment": "AUTOMATED_COUNTS_ONLY_HUMAN_PENDING",
            "coverage_assessment": "OSM_MAPPED_FEATURES_ONLY",
            "context_route_shown": line_shown, "requested_start_pixel": start_px,
            "requested_target_pixel": target_px_point, "rendered_route_end_pixel": end_px,
            "overlay_identity": overlay["identity"], "base": base_path.as_posix(), "route": route_path.as_posix(),
            "base_sha256": sha256((output/base_path).read_bytes()).hexdigest(),
            "route_sha256": sha256((output/route_path).read_bytes()).hexdigest(),
        }
    geometry = overlay.get("geometry")
    lengths = None
    if geometry:
        line = LineString([FORWARD(*p) for p in geometry["coordinates"]])
        lengths = {"target_building_interior_m_approx": line.intersection(polygon.buffer(-.5)).length*0.855,
                   "basis": "Projected intersection excluding the 0.5m outline buffer, approximate ground scale; not accessibility truth."}
    status = {"scene_id": scene["scene_id"], "source_snapshot_utc": osm["osm3s"]["timestamp_osm_base"],
              "attribution": "© OpenStreetMap contributors (ODbL-1.0)",
              "unmatched_renderable_relations": missed, "local_route_status": result["status"],
              "local_route_failure": result["failure_reason"], "overlay_geometry_check": lengths,
              "diagnostic_status": diagnostic["status"] if diagnostic else "NOT_NEEDED",
              "views": out_views}
    dump(output / "runs/local_viewports.json", status)
    print(json.dumps({"route_status": result["status"], "target_snap_m": result["snap_end_m"],
                      "route_length_m": result["length_m"], "diagnostic_status": status["diagnostic_status"],
                      "diagnostic_length_m": diagnostic.get("length_m") if diagnostic else None,
                      "views": list(out_views)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="write an independent replay without replacing the saved run")
    args = parser.parse_args()
    main(output=args.output)
