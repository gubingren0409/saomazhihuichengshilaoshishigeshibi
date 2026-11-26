"""Build the self-contained R3 map gallery from frozen and saved results."""
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path

from shapely.geometry import LineString, Point, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
MUSEUM = "sh-huangpu-01"
VARIANTS = ("B0", "S1", "I-LINE", "I-REGION", "I-REGION-ABL", "I-REGION-NET-ABL")
STATE_LAYER = {"NATIVE_WALKABLE": "state-native", "INFERRED_WALKABLE": "state-inferred",
               "RESTRICTED": "state-restricted", "UNKNOWN": "state-unknown"}
BASE_ORDER = ("park", "plaza", "grass", "water", "building", "road", "walk", "fence", "gate", "crossing", "label")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def collection(path):
    return load(path)["features"]


def r3_base(root):
    path = root / "inputs/rev1/src/build_visuals.py"
    spec = importlib.util.spec_from_file_location("frozen_rev1_plot_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def convert(base, entries, layer_by):
    for feature in entries:
        if not feature.get("geometry"):
            continue
        props = dict(feature["properties"])
        geometry = base.metric(feature["geometry"])
        layer = layer_by(props)
        if not layer:
            continue
        if geometry.geom_type == "Point":
            props.setdefault("wgs84", feature["geometry"]["coordinates"])
        yield layer, geometry, props


def payload(base, entries, anchor, extent):
    rows = []
    for layer, geom, props in entries:
        if not geom.is_empty and geom.intersects(extent):
            # Clip only map drawing; evidence remains exactly as exported.
            geometry = geom.intersection(extent)
            if parts := base.normalize(geometry, anchor):
                rows.append({"layer": layer, "shape": parts, "props": props})
    return rows


def frame(base, near_objects, full_objects):
    near = base.fit_bounds(near_objects, 10, minimum=60)
    full = base.fit_bounds(full_objects or near_objects, 24, minimum=100)
    clip = box(min(near.bounds[0], full.bounds[0]), min(near.bounds[1], full.bounds[1]),
               max(near.bounds[2], full.bounds[2]), max(near.bounds[3], full.bounds[3]))
    anchor = near.centroid.coords[0]
    return clip, anchor, {"near": base.camera_bounds(near, anchor), "full": base.camera_bounds(full, anchor)}


def area_rows(base, features, scene_id):
    for row in features:
        if row["scene_id"] != scene_id or not row.get("geometry"):
            continue
        category = row["category"]
        if category == "PARK_GARDEN_OR_RECREATION":
            layer = "park"
        elif category == "PEDESTRIAN_AREA":
            layer = "plaza"
        else:
            continue
        geom = base.metric(row["geometry"])
        yield layer, geom, base.area_properties(row)
        if name := row["tags"].get("name"):
            yield "label", geom.representative_point(), {"label": name, "source_id": row["native_id"]}


def basemap(base, frozen, scene, areas, clip):
    source = load(frozen / scene["osm_clip"])
    objects = [("label" if layer == "road_label" else layer, geom, props)
               for layer, geom, props in base.basemap(source, clip)]
    objects.extend(area_rows(base, areas, scene["scene_id"]))
    footprint = base.metric(scene["building_footprint"])
    objects.append(("label", footprint.representative_point(),
                    {"label": scene["label"], "source_id": scene["building_native_id"]}))
    return sorted(objects, key=lambda obj: BASE_ORDER.index(obj[0]) if obj[0] in BASE_ORDER else len(BASE_ORDER))


def save_groups(rows, base, anchor, clip, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[2].get(k) for k in keys)].append(row)
    return {"|".join(str(v) for v in key): payload(base, members, anchor, clip)
            for key, members in sorted(groups.items(), key=lambda row: str(row[0]))}


def semantic_maps(root, base, frozen, scene, areas):
    source = collection(root / "data/semantics_routes.geojson")
    study = load(root / "runs/semantics.json")
    grass = next(f for f in source if f["properties"]["role"] == "source_grass")
    nearby = base.metric(grass["geometry"])
    route = [f for f in source if f["properties"]["role"] == "route" and
             f["properties"]["target"] == "north_fixed"]
    clip, anchor, views = frame(base, [nearby], [nearby, *(base.metric(f["geometry"]) for f in route)])
    restored = [f for f in source if f["properties"]["role"] == "restored_edge"]
    raw_ways = [f for f in source if f["properties"]["role"] == "source_walkway"]
    common = basemap(base, frozen, scene, areas, clip)
    common.extend(convert(base, [grass], lambda _: "grass"))
    common.extend(convert(base, raw_ways, lambda _: "walk"))
    p = route[0]["properties"]
    common.extend([
        ("start", base.metric({"type": "Point", "coordinates": p["start_wgs84"]}),
         {"label": "固定起点", "source_id": scene["start_native_id"], "wgs84": p["start_wgs84"]}),
        ("interface", base.metric({"type": "Point", "coordinates": p["end_wgs84"]}),
         {"label": "旧实验固定北侧接点", "wgs84": p["end_wgs84"]}),
    ])
    panels = []
    for variant, label, edge_layer in (("S0", "旧规则 · 排除草地相交", "rejected"),
                                       ("S1", "语义修复 · 保留原生步道", "restored")):
        selected = [f for f in route if f["properties"]["variant"] == variant]
        rows = list(convert(base, selected, lambda _: "route-native"))
        rows.extend(convert(base, restored, lambda _: edge_layer))
        panels.append({"title": label, "features": payload(base, rows, anchor, clip),
                       "note": f"同一固定接点 · {study['variants'][variant]['north_fixed']['length_m']:.2f} m"})
    return {"base": payload(base, common, anchor, clip), "views": views, "anchor_xy": anchor, "panels": panels,
            "lengths": {v: study["variants"][v]["north_fixed"]["length_m"] for v in ("S0", "S1")},
            "restored_count": study["spatial_geometry_policy_dedup"]["restored_segments"]}


def north_maps(root, base, frozen, scene, areas):
    routes = collection(root / "data/north_routes.geojson")
    domains = collection(root / "data/north_domain.geojson")
    surfaces = collection(root / "data/north_regions.geojson")
    interfaces = collection(root / "data/north_interfaces.geojson")
    info = load(root / "runs/north.json")
    domain_rows = list(convert(base, domains, lambda _: "domain"))
    rows = list(convert(base, surfaces, lambda p: STATE_LAYER[p["walkability_state"]]))
    for _, _, p in rows:
        p["variant"] = "I-REGION"
    ablation = root / "data/north_regions_I-REGION-ABL.geojson"
    if ablation.is_file():
        extras = list(convert(base, collection(ablation), lambda p: STATE_LAYER[p["walkability_state"]]))
        for _, _, p in extras:
            p["variant"] = "I-REGION-ABL"
        rows.extend(extras)
    points = list(convert(base, interfaces, lambda p: {"registered_exit": "exit", "start": "start",
                                                       "query_endpoint": "endpoint"}.get(p.get("role"), "interface")))
    for layer, _, p in points:
        if layer == "exit" and info["target"].get("wgs84"):
            p["wgs84"] = info["target"]["wgs84"]

    def route_layer(p):
        if p.get("role") in {"gap", "route_gap", "residual_gap"}:
            return "gap"
        if not p.get("layer") and p.get("role") not in {None, "route_segment"}:
            return None
        layer = p.get("layer", "native").lower().replace("_", "-")
        kind = p.get("geometry_kind")
        if kind == "R2_SINGLE_LINE_BASELINE":
            return "route-line"
        if kind == "NEW_GRID_WITHIN_MAPPED_FACE":
            return "route-derived-new"
        if layer in {"native", "derived", "inferred", "unknown"}:
            return f"route-{layer}"
        if p.get("role") == "route_segment":
            raise ValueError(f"Unexpected route layer {layer}")
        return "gap" if p.get("role") in {"gap", "route_gap", "residual_gap"} else None

    route_rows = list(convert(base, routes, route_layer))
    for query in info["queries"]:
        ident = query["query_id"]
        if ident == "NORTH-DOOR":
            for name, variant in info["variants"].items():
                result = variant["routes"][ident]
                if result.get("end_xy") and (result.get("residual_m") or 0) > .005:
                    route_rows.append(("gap", LineString([result["end_xy"], query["target"]["xy"]]),
                                       {"variant": name, "query_id": ident, "role": "DISTANCE_ONLY_GAP",
                                        "length_m": result["residual_m"], "status": "无通路的测距线"}))
            continue
        for side in ("source", "target"):
            qpoint = query[side]
            points.append(("endpoint", Point(qpoint["xy"]), {"id": qpoint["id"], "query_id": ident,
                           "role": side, "wgs84": list(base.INVERSE.transform(*qpoint["xy"]))}))
    clip, anchor, views = frame(base, [g for _, g, _ in domain_rows],
                               [g for _, g, _ in [*domain_rows, *route_rows, *points]])
    background = basemap(base, frozen, scene, areas, clip)
    domain = unary_union([g for _, g, _ in domain_rows])
    label_specs = [("上海博物馆", scene["building_native_id"], base.metric(scene["building_footprint"]))]
    label_specs.extend(("北侧登记步行面", row["native_id"], base.metric(row["geometry"]))
                       for row in areas if row["scene_id"] == scene["scene_id"] and row["native_id"] == "relation/2153738")
    for name, source_id, geometry in label_specs:
        within = geometry.intersection(domain)
        if not within.is_empty:
            background.append(("label", within.representative_point(), {"label": name, "source_id": source_id, "near_only": True}))
    visual_sources = root / "data/north_sources.geojson"
    if visual_sources.is_file():
        def source_layer(p):
            state = str(p.get("kind", "")).upper()
            return ("fence" if "WALL" in state or "BARRIER" in state or "FENCE" in state else
                    "building" if "BUILDING" in state else "water" if "WATER" in state else
                    "grass" if "GRASS" in state or "FLOWERBED" in state else None)
        background.extend(convert(base, collection(visual_sources), source_layer))
    areas_m2 = defaultdict(float)
    for _, geom, props in rows:
        variant = props.get("variant", "I-REGION")
        if variant in {"I-REGION", None}:
            areas_m2[props["walkability_state"]] += props.get("area_m2", geom.area)
    rows.sort(key=lambda row: (row[2].get("walkability_state"), row[2].get("region_id")))
    light_info = {"surface": info["surface"], "queries": [q["query_id"] for q in info["queries"]],
                  "variants": {name: {"routes": {q: {k:v for k,v in row.items()
                    if k in {"status", "length_m", "residual_m", "cost_m", "reached", "condition_graph_failure", "surface_sha256"}}
                    for q,row in val["routes"].items()}} for name,val in info["variants"].items()}}
    return {"base": payload(base, background, anchor, clip), "views": views, "anchor_xy": anchor,
            "domain": payload(base, domain_rows, anchor, clip), "points": payload(base, points, anchor, clip),
            "regions": save_groups(rows, base, anchor, clip, ("variant",)), "areas_m2": dict(areas_m2),
            "routes": save_groups(route_rows, base, anchor, clip, ("variant", "query_id")),
            "variants": [v for v in VARIANTS if v in info["variants"]],
            "summary": light_info, "window_area_m2": unary_union([g for _, g, _ in domain_rows]).area}


def benchmark_maps(root, base):
    source = collection(root / "data/benchmark_review.geojson")
    by_case = defaultdict(list)
    for feature in source:
        by_case[feature["properties"]["task_id"]].append(feature)

    def style(p):
        role = p["role"]
        if role == "predicted_region":
            return STATE_LAYER[p["walkability_state"]]
        if role == "observed_obstacle":
            kind = str(p.get("kind", "")).upper()
            return "water" if "WATER" in kind else "fence" if "BARRIER" in kind or "WALL" in kind else "building"
        if role == "observed_support":
            return "park" if p.get("kind") == "PARK" else "plaza"
        if role == "route":
            return "route-" + p.get("layer", "inferred")
        tags = p.get("tags") or {}
        if role == "observed_network" and (tags.get("level") not in {None, "0"} or tags.get("layer") not in {None, "0"}):
            return "walk-grade"
        return {"observed_network": "walk", "observed_background": "grass", "domain": "domain",
                "reference_area": "reference", "reference_line": "reference-line", "obstacle_reference": "reference",
                "query_endpoint": "endpoint", "origin": "start", "target": "endpoint", "interface": "interface",
                "registered_exit": "exit", "route_gap": "gap"}.get(role)

    review_index = root / "runs/benchmark_review.json"
    meta = load(review_index) if review_index.is_file() else {}
    data = {}
    for ident, features in sorted(by_case.items()):
        rows = list(convert(base, features, style))
        if not rows:
            continue
        reference = [g for layer, g, _ in rows if layer in {"reference", "reference-line"}]
        domain = [g for layer, g, _ in rows if layer == "domain"]
        clip, anchor, views = frame(base, reference or domain or [rows[0][1]], domain or reference or [rows[0][1]])
        left, right = [], []
        for row in rows:
            if row[2]["role"].startswith("observed_") or row[2]["role"] in {"domain", "origin", "target", "query_endpoint", "registered_exit"}:
                left.append(row)
            else:
                right.append(row)
        left.sort(key=lambda row: BASE_ORDER.index(row[0]) if row[0] in BASE_ORDER else len(BASE_ORDER))
        right.sort(key=lambda row: (row[0] in {"reference", "reference-line"}, row[0].startswith("route-")))
        attributes = meta.get(ident, {})
        if not attributes:
            attributes = next((row[2] for row in rows if "case_type" in row[2]), {})
        data[ident] = {"base": payload(base, left, anchor, clip), "right": payload(base, right, anchor, clip),
                       "views": views, "anchor_xy": anchor, "summary": attributes}
    return data


def main(root, output):
    base = r3_base(root)
    frozen = root / "inputs/rev1/frozen_r4"
    scenes = load(frozen / "runs/source_scene_contracts.json")["scenes"]
    scene = next(s for s in scenes if s["scene_id"] == MUSEUM)
    areas = collection(frozen / "runs/source_open_spaces.json")
    data = {"semantics": semantic_maps(root, base, frozen, scene, areas),
            "north": north_maps(root, base, frozen, scene, areas),
            "benchmark": benchmark_maps(root, base), "snapshot_time": scene.get("snapshot_time")}
    template = (ROOT / "src/review_template.html").read_text(encoding="utf-8")
    script = (ROOT / "src/review_map.js").read_text(encoding="utf-8")
    serial = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__PAYLOAD__", serial).replace("__SCRIPT__", script), encoding="utf-8")
    print(json.dumps({"html": str(output), "benchmark_cases": len(data["benchmark"]),
                      "variants": data["north"]["variants"]}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    main(a.root, a.output or a.root / "visuals/index.html")
