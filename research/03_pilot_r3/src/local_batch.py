"""Freeze five independently named Shanghai targets, then replay the unmodified R1 local pipeline."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest, sha256
import json
from pathlib import Path
from time import perf_counter

from shapely import LineString, Point, Polygon, box, union_all
from shapely.geometry import mapping, shape
from shapely.ops import nearest_points, polygonize, transform

from .frozen_r1.clip_pbf import SOURCE, extract
from .frozen_r1.local_route import PROFILE, route_osm
from .frozen_r1.render_osm import base_map, pixel, prepare, route_overlay
from .frozen_r1.scene import DENY, FORWARD, HEIGHT, INVERSE, WIDTH, distance, index, viewport, xy

ROOT = Path(__file__).resolve().parents[1]
R1_PBF = ROOT.parent / "OSM_GEOAPIFY_PILOT_R1/runtime/shanghai-261108.osm.pbf"
PBF_SHA = "e4b83f15cc358d347c47708239f8c556d9819a69f43ff32f42a23c405733e8f6"
ROUTER_SHA = "dfc2c42c3e4f228d11105ffbd170e5aa04c59834b977a8e7e212cf94dcb5b25f"
RENDERER_SHA = "bf1832decb3ea7716b7af4736b0643d28f4e38df353065e2ea53794f8e5ea029"
CHOICES = (
    ("sh-wukang", "武康大楼", "STREET_FRONT_RESIDENTIAL_MIXED", "way", 293434151,
     (121.4334133, 31.2059766, 121.4339882, 31.2065692), "沿街住宅/混合类型；单门属性未独立核验"),
    ("sh-tower", "上海中心大厦", "OFFICE_MIXED_HIGHRISE", "way", 165792123,
     (121.5007275, 31.235189, 121.501806, 31.2360492), "办公主导的混合用途高层；原生 building=commercial"),
    ("sh-newworld", "新世界城", "STREET_FRONT_RETAIL", "way", 51317339,
     (121.4684057, 31.2363964, 121.4697643, 31.2377346), "沿街商业；原生 building=retail、shop=mall；实体多入口状态未核验"),
    ("sh-library", "上海图书馆淮海路馆", "PUBLIC_LIBRARY", "way", 293434188,
     (121.4391702, 31.2087726, 121.4408607, 31.2101789), "公共服务；目标为淮海中路1555号原生馆舍轮廓"),
    ("sh-exhibition", "上海展览中心", "OPEN_SPACE_EXHIBITION_COMPLEX", "relation", 7469147,
     (121.4466448, 31.2248504, 121.4500003, 31.2286203), "退线场馆复合体；采用含内环的馆舍建筑关系，区别于外部场地 way/438483942"),
)
ENTRANCE_PRIORITY = {"main": 0, "public": 1, "yes": 2, "entrance": 3}
SNAP_M = 35


def save_json(path, value, *, exclusive=False, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=None if compact else 2,
                  separators=(",", ":") if compact else None, allow_nan=False)
        stream.write("\n")


def hash_file(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def bounded_bbox(source_bounds):
    w, s, e, n = source_bounds
    cx, cy = FORWARD((w + e) / 2, (s + n) / 2)
    # Same physical camera geometry as R1 plus a 520 m projected source margin.
    context = viewport(INVERSE(cx, cy), 16)["extent_3857"]
    a, b = INVERSE(context[0] - 520, context[1] - 520)
    c, d = INVERSE(context[2] + 520, context[3] + 520)
    return [a, b, c, d]


def named_footprint(native_kind, native_id, nodes, ways, relations):
    if native_kind == "way":
        way = ways[native_id]
        references = way["nodes"]
        if references[0] != references[-1]:
            raise ValueError("NAMED_WAY_NOT_CLOSED")
        footprint = Polygon([xy(nodes[n]) for n in references])
        tags = way["tags"]
    else:
        relation = relations[native_id]
        members = relation["members"]
        outer_lines = [LineString([xy(nodes[n]) for n in ways[m["ref"]]["nodes"]])
                       for m in members if m["role"] in ("outer", "")]
        inner_lines = [LineString([xy(nodes[n]) for n in ways[m["ref"]]["nodes"]])
                       for m in members if m["role"] == "inner"]
        outer = union_all(list(polygonize(outer_lines)))
        inner = union_all(list(polygonize(inner_lines)))
        footprint = outer.difference(inner)
        references = [n for m in members for n in ways[m["ref"]]["nodes"]]
        tags = relation["tags"]
    if footprint.geom_type != "Polygon" or footprint.is_empty or not footprint.is_valid:
        raise ValueError("NAMED_FOOTPRINT_NOT_VALID_SINGLE_POLYGON")
    if tags.get("building") in (None, "no") or not tags.get("name"):
        raise ValueError("BUILDING_IDENTITY_UNCONFIRMED")
    return footprint, sorted(set(references)), tags


def make_contract(candidate, snapshot, clip_path):
    scene_id, label, category, native_kind, native_id, _, caveat = candidate
    nodes, ways, relations = index(snapshot)
    footprint, references, building_tags = named_footprint(native_kind, native_id, nodes, ways, relations)
    poly = transform(FORWARD, footprint)
    west, south, east, north = poly.bounds
    cx, cy = (west + east) / 2, (south + north) / 2
    center = INVERSE(cx, cy)
    west_probe = Point(west - 330, cy)
    facade_point = nearest_points(poly.exterior, west_probe)[0]
    entr = []
    for node_id in references:
        node = nodes[node_id]
        tags = node.get("tags", {})
        if "entrance" not in tags:
            continue
        point = xy(node)
        on_external_ring = poly.exterior.distance(Point(FORWARD(*point))) <= .1
        valid = (on_external_ring and tags.get("entrance") in ENTRANCE_PRIORITY
                 and tags.get("access") not in DENY and tags.get("foot") not in DENY)
        entr.append({"native_id": f"node/{node_id}", "coordinate": list(point), "tags": tags,
                     "on_exterior_ring": on_external_ring, "request_eligible": valid,
                     "classification": "OSM_TAGGED", "physical_access": "UNKNOWN"})
    eligible = [e for e in entr if e["request_eligible"]]
    selected = min(eligible, key=lambda e: (ENTRANCE_PRIORITY[e["tags"]["entrance"]],
                                            Point(FORWARD(*e["coordinate"])).distance(facade_point),
                                            int(e["native_id"].split("/")[-1]))) if eligible else None
    target = selected["coordinate"] if selected else list(INVERSE(facade_point.x, facade_point.y))
    target_role = "OSM_TAGGED" if selected else "PROXY_OR_UNCERTAIN"
    path_nodes = set()
    for way in ways.values():
        tags = way.get("tags", {})
        if (tags.get("highway") in {"footway", "pedestrian", "path", "steps", "living_street"}
                and tags.get("area") != "yes" and tags.get("indoor") != "yes"
                and tags.get("access") not in DENY and tags.get("foot") not in DENY
                and tags.get("level") in (None, "0") and tags.get("layer") in (None, "0")):
            path_nodes.update(way["nodes"])
    probe = INVERSE(cx - 330, cy)
    starts = []
    for node_id in path_nodes:
        node = nodes.get(node_id)
        if node is None:
            continue
        tags = node.get("tags", {})
        point = xy(node)
        if (240 <= distance(center, point) <= 440
                and tags.get("access") not in DENY and tags.get("foot") not in DENY):
            starts.append((distance(probe, point), node_id))
    start_id = min(starts)[1] if starts else None
    ready = start_id is not None
    views = {k: viewport(center, z) for k, z in (("detail", 18), ("context", 16))}
    target_scope = ("OSM 原生外轮廓入口点；现实门及通行未独立核验" if selected else
                    "朝西外轮廓接近代理点，仅用于双方同坐标请求，未当作真实门或 POI")
    return {
        "scene_id": scene_id, "label": label, "category": category, "category_evidence_note": caveat,
        "role": "NEW_LOCKED_SCENE", "use": category, "group": category,
        "building_native_id": f"{native_kind}/{native_id}", "building_tags": building_tags,
        "building_source_url": f"https://www.openstreetmap.org/{native_kind}/{native_id}",
        "building_footprint": mapping(footprint),
        "start": list(xy(nodes[start_id])) if ready else None, "start_native_id": f"node/{start_id}" if ready else None,
        "start_role": "DECLARED_MAP_QUERY_ORIGIN", "target": target, "target_role": target_role,
        "entry_native_id": selected["native_id"] if selected else None, "entry_scope": target_scope,
        "entrance_references": entr, "access_reference_status": "SOURCE_REFERENCE_ONLY",
        "poi_search_location": None, "poi_search_status": "NOT_REQUESTED_FIXED_GEOMETRY",
        "path_snap_max_m": SNAP_M, "frozen_before_route": True, "contract_status": "READY" if ready else "NO_ELIGIBLE_START",
        "views": views, "osm_clip": clip_path.relative_to(ROOT).as_posix(),
        "snapshot_sha256": hash_file(clip_path), "snapshot_time": snapshot["osm3s"]["timestamp_osm_base"],
        "snapshot_bounds_wsen": snapshot["bounds_wsen"],
        "geoapify_request_contract": {
            "route": {"mode": "walk", "type": "balanced", "units": "metric", "format": "geojson"},
            "static": {"style": "osm-bright-smooth", "width": WIDTH, "height": HEIGHT,
                       "bearing": 0, "pitch": 0, "scaleFactor": 1, "format": "png"},
        },
    }


def clip_candidate(candidate, pbf):
    scene_id, label, category, native_kind, native_id, source_bounds, caveat = candidate
    start = perf_counter()
    relative = Path(f"data/{scene_id}.osm.json")
    clip_path = ROOT / relative
    try:
        snapshot = extract(pbf, bounded_bbox(source_bounds))
        save_json(clip_path, snapshot, exclusive=True, compact=True)
        result = make_contract(candidate, snapshot, clip_path)
        result["clip_elapsed_s"] = perf_counter() - start
        return result
    except (KeyError, ValueError, OSError) as exc:
        return {"scene_id": scene_id, "label": label, "category": category, "category_evidence_note": caveat,
                "building_native_id": f"{native_kind}/{native_id}", "target_role": "UNKNOWN",
                "contract_status": "SOURCE_OR_GEOMETRY_BLOCKED", "reason": type(exc).__name__ + ": " + str(exc),
                "frozen_before_route": True, "views": {}, "start": None, "target": None,
                "clip_elapsed_s": perf_counter() - start}


def freeze(pbf):
    contract_path = ROOT / "runs/scene_contracts.json"
    if contract_path.exists():
        raise SystemExit("FROZEN_SCENE_ALREADY_EXISTS")
    if hash_file(pbf) != PBF_SHA:
        raise SystemExit("SOURCE_PBF_SHA_MISMATCH")
    with ThreadPoolExecutor(max_workers=3) as executor:
        scenes = list(executor.map(lambda c: clip_candidate(c, pbf), CHOICES))
    result = {
        "execution": "LOCKED_BEFORE_LOCAL_AND_HOSTED_ROUTE",
        "snapshot": {"path": "../OSM_GEOAPIFY_PILOT_R1/runtime/shanghai-261108.osm.pbf",
                     "source": SOURCE, "sha256": PBF_SHA, "version_utc": "2026-11-08T21:21:00Z",
                     "bytes": 26079230, "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors"},
        "selection_policy": {
            "identity": "Exact native names and stable IDs confirmed from PBF before any route outcome; five predetermined categories",
            "start": "From tagged surface walking ways, choose eligible native node 240–440 m from footprint center, nearest fixed probe 330 Web Mercator metres west; tie by native ID.",
            "target": "Use exterior-ring tagged entrance (main, public, yes, entrance in that order), nearest west facade and native ID to break ties. If absent use west-facing exterior proxy, not an entrance.",
            "camera": "R1 frozen equivalent north-up WGS84 bounds derived from EPSG:3857 z18 detail and z16 context, 1200×900 DPR1",
            "failure": "Keep all five named slots and paired input coordinates; failed, unknown, and incomplete scenes are never substituted.",
            "snap": "Unchanged R1 local 35 m for both endpoints. Hosted threshold not assumed.",
        },
        "local_pipeline": {"profile": PROFILE, "router_sha256": ROUTER_SHA, "renderer_sha256": RENDERER_SHA},
        "scenes": scenes,
    }
    save_json(contract_path, result, exclusive=True)
    for scene in scenes:
        print(json.dumps({k: scene.get(k) for k in ("scene_id","contract_status","building_native_id","entry_native_id",
                                                 "target_role","start","target","reason","clip_elapsed_s")},
                         ensure_ascii=True), flush=True)


def route_feature(result, purpose):
    return {"type": "Feature", "geometry": result.get("geometry"),
            "properties": {"purpose": purpose, "status": result["status"],
                           "failure_reason": result.get("failure_reason"),
                           "length_m": result.get("length_m"), "end": result.get("route_end"),
                           "way_ids": result.get("way_ids", [])}}


def render_scene(scene, snapshot, route, overlay, output_root):
    features, points, missed = prepare(snapshot)
    polygon = transform(FORWARD, shape(scene["building_footprint"]))
    output = {}
    for name, view in scene["views"].items():
        base, extras = base_map(features, points, scene, view)
        route_picture, drawn = route_overlay(base, scene, view, overlay)
        base_path = Path(f"visuals/osm/{scene['scene_id']}_{name}_base.png")
        route_path = Path(f"visuals/osm/{scene['scene_id']}_{name}_route.png")
        (output_root / base_path).parent.mkdir(parents=True, exist_ok=True)
        base.save(ROOT / base_path, compress_level=6)
        route_picture.save(ROOT / route_path, compress_level=6)
        extent = box(*view["extent_3857"])
        coords = [pixel(x, y, view) for x, y in polygon.exterior.coords]
        target_px = [max(p[k] for p in coords) - min(p[k] for p in coords) for k in (0, 1)]
        line = overlay.get("geometry")
        length_inside = None
        if line:
            projected_line = transform(FORWARD, shape(line))
            length_inside = projected_line.intersection(polygon.buffer(-.5)).length
        output[name] = {**view, **extras, "status": "PASS_LOCAL_GEOMETRY_RENDER", "actual_bounds": view["bounds"],
                        "pixel_size": [WIDTH, HEIGHT], "target_pixel_size": target_px,
                        "target_area_ratio": polygon.intersection(extent).area / extent.area,
                        "building_fully_inside": extent.covers(polygon), "overlay_drawn": drawn,
                        "route_identity": overlay["identity"], "route_status": route["status"],
                        "route_target_offset_m": overlay.get("remaining_gap_to_original_target_m", route.get("snap_end_m")),
                        "target_building_inner_overlap_projected_m": length_inside,
                        "unmatched_renderable_relations": missed,
                        "base": base_path.as_posix(), "route": route_path.as_posix(),
                        "base_sha256": hash_file(output_root / base_path), "route_sha256": hash_file(output_root / route_path)}
    return output


def run(output_root=ROOT):
    output = output_root / "runs/local_results.json"
    if output.exists():
        raise SystemExit("LOCAL_RESULTS_ALREADY_EXIST")
    lock_path = ROOT / "runs/scene_contracts.json"
    contract = json.loads(lock_path.read_text(encoding="utf-8"))
    if hash_file(Path(__file__).with_name("frozen_r1") / "local_route.py") != ROUTER_SHA:
        raise SystemExit("FROZEN_ROUTER_SHA_MISMATCH")
    if hash_file(Path(__file__).with_name("frozen_r1") / "render_osm.py") != RENDERER_SHA:
        raise SystemExit("FROZEN_RENDERER_SHA_MISMATCH")
    results = {"scene_contracts_sha256": hash_file(lock_path), "profile": PROFILE,
               "engine_identity": "FROZEN_R1_IMPLEMENTATION", "scenes": []}
    for scene in contract["scenes"]:
        started = perf_counter()
        scene_id = scene["scene_id"]
        if scene["contract_status"] != "READY":
            results["scenes"].append({"scene_id": scene_id, "status": scene["contract_status"], "views": {},
                                      "route": None, "diagnostic": None, "elapsed_s": perf_counter() - started})
            continue
        clip_path = ROOT / scene["osm_clip"]
        if hash_file(clip_path) != scene["snapshot_sha256"]:
            raise SystemExit("FROZEN_CLIP_SHA_MISMATCH")
        snapshot = json.loads(clip_path.read_text(encoding="utf-8"))
        route_started = perf_counter()
        route = route_osm(snapshot, scene["start"], scene["target"], SNAP_M)
        route_elapsed = perf_counter() - route_started
        route.update(scene_id=scene_id, identity="LOCAL_OSM_R1_LOCKED_REQUEST",
                     target_identity=scene["target_role"], snapshot_sha256=scene["snapshot_sha256"])
        route_path = Path(f"runs/local/{scene_id}_route.geojson")
        save_json(output_root / route_path, route_feature(route, "FROZEN_REQUEST"))
        diagnostic, diagnostic_path, overlay = None, None, route
        if route["failure_reason"] == "TARGET_SNAP_OUTSIDE_LIMIT" and route.get("snap_end"):
            diagnostic = route_osm(snapshot, scene["start"], route["snap_end"]["position"], SNAP_M)
            diagnostic.update(identity="PARTIAL_DIAGNOSTIC_TO_NEAREST_MAPPED_SEGMENT",
                              parent_failure=route["failure_reason"],
                              remaining_gap_to_original_target_m=route["snap_end_m"], missing_segment_drawn=False)
            diagnostic_path = Path(f"runs/local/{scene_id}_diagnostic.geojson")
            save_json(output_root / diagnostic_path, route_feature(diagnostic, diagnostic["identity"]))
            if diagnostic["status"] == "PASS":
                overlay = diagnostic
        views = render_scene(scene, snapshot, route, overlay, output_root)
        row = {"scene_id": scene_id, "status": route["status"], "route": route, "diagnostic": diagnostic,
               "views": views, "route_artifact": route_path.as_posix(),
               "diagnostic_artifact": diagnostic_path.as_posix() if diagnostic_path else None,
               "route_elapsed_s": route_elapsed, "elapsed_s": perf_counter() - started}
        results["scenes"].append(row)
        print(json.dumps({"scene_id": scene_id, "status": route["status"], "failure": route["failure_reason"],
                          "length_m": route.get("length_m"), "end_gap_m": route.get("snap_end_m"),
                          "diagnostic_status": diagnostic["status"] if diagnostic else None,
                          "elapsed_s": row["elapsed_s"]}), flush=True)
    save_json(output, results, exclusive=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--pbf", type=Path, default=R1_PBF)
    parser.add_argument("--output", type=Path, default=ROOT, help="Run-only output root for a clean replay.")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.pbf)
    else:
        run(args.output.resolve())


if __name__ == "__main__":
    main()
