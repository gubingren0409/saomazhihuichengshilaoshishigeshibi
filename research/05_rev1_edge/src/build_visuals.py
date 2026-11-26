"""Build the offline REV1 review from frozen map objects and saved machine outputs."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
PROJECTOR = Transformer.from_crs(4326, 32651, always_xy=True)
INVERSE = Transformer.from_crs(32651, 4326, always_xy=True)
MUSEUM = "sh-huangpu-01"
SOUTH = "relation/2385771"
NORTH = "relation/2153738"
MAIN = "R1_AREA_EDGE_MAIN"
WALK = {"footway", "path", "pedestrian", "steps", "living_street", "corridor"}
ROAD = {"primary", "secondary", "tertiary", "residential", "service", "unclassified", "trunk"}
FENCE = {"fence", "wall", "hedge", "guard_rail", "retaining_wall", "chain"}
MAP_NAMES = {
    SOUTH: "南侧步行面", NORTH: "北侧步行面",
    "node/6897141353": "南门 main", "node/6897145227": "西北门 exit",
}
FIGURES = {
    "01_map_information.svg": "overview",
    "02_old_new_same_camera.svg": "compare",
    "03_south_full_route.svg": "south-route",
    "04_south_terminal.svg": "south-terminal",
    "05_north_unsupported_gap.svg": "north",
    "06_parameter_cases.svg": "matrix",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as handle:
        return sha256(handle.read()).hexdigest()


def metric(geometry):
    return transform(PROJECTOR.transform, shape(geometry))


def fit_bounds(geometries, padding=20, minimum=80, aspect=1.48):
    valid = [geometry.bounds for geometry in geometries if geometry and not geometry.is_empty]
    x0, y0 = min(p[0] for p in valid), min(p[1] for p in valid)
    x1, y1 = max(p[2] for p in valid), max(p[3] for p in valid)
    width = max(x1 - x0 + padding * 2, (y1 - y0 + padding * 2) * aspect, minimum)
    height = width / aspect
    return box((x0 + x1 - width) / 2, (y0 + y1 - height) / 2,
               (x0 + x1 + width) / 2, (y0 + y1 + height) / 2)


def record(layer, geometry, props):
    return layer, geometry, props


def area_properties(row):
    return dict(native_id=row["native_id"], tags=row.get("tags", {}), source="FROZEN_OSM",
                evidence_status="OBSERVED", rings=row.get("outer_way_ids"),
                inner_rings=row.get("inner_way_ids"), label=MAP_NAMES.get(row["native_id"]))


def basemap(document, selection):
    """Paint map context only. No source feature here creates a routing edge."""
    objects = document["elements"]
    nodes = {r["id"]: (r["lon"], r["lat"]) for r in objects if r["type"] == "node"}
    geographic = box(*INVERSE.transform_bounds(*selection.bounds))
    features, names = [], defaultdict(list)
    for item in objects:
        tags = item.get("tags", {})
        identifier = f"{item['type']}/{item['id']}"
        if item["type"] == "node" and (tags.get("highway") == "crossing" or tags.get("barrier") in {"gate", "lift_gate"}):
            point = Point(nodes[item["id"]])
            if geographic.covers(point):
                layer = "gate" if tags.get("barrier") else "crossing"
                features.append(record(layer, transform(PROJECTOR.transform, point),
                                       dict(native_id=identifier, tags=tags, wgs84=list(point.coords[0]), source="FROZEN_OSM")))
        if item["type"] != "way" or not tags:
            continue
        coords = [nodes.get(key) for key in item["nodes"]]
        if len(coords) < 2 or None in coords:
            continue
        line = LineString(coords)
        if not geographic.intersects(line.envelope):
            continue
        props = dict(native_id=identifier, tags=tags, source="FROZEN_OSM")
        highway = tags.get("highway")
        if highway in ROAD and tags.get("area") != "yes":
            way = transform(PROJECTOR.transform, line).intersection(selection)
            if way.is_empty:
                continue
            features.append(record("road", way, props))
            if tags.get("name"):
                names[tags["name"]].append(way)
        if (highway in WALK or tags.get("foot") in {"yes", "designated", "permissive"}) and tags.get("area") != "yes":
            features.append(record("walk", transform(PROJECTOR.transform, line), props))
        if tags.get("barrier") in FENCE:
            features.append(record("fence", transform(PROJECTOR.transform, line), props))
        if len(coords) < 4 or not line.is_ring:
            continue
        polygon = Polygon(coords)
        if not polygon.is_valid:
            continue
        layer = None
        if tags.get("building") not in {None, "no"}:
            layer = "building"
        elif tags.get("landuse") in {"grass", "flowerbed", "meadow"} or tags.get("leisure") == "garden":
            layer = "grass"
        elif tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
            layer = "water"
        if layer:
            features.append(record(layer, transform(PROJECTOR.transform, polygon), props))
    for name, lines in names.items():
        visible = max(lines, key=lambda line: line.length)
        if visible.length >= 38:
            features.append(record("road_label", visible.interpolate(.5, normalized=True),
                                   dict(label=name, source="FROZEN_OSM")))
    return features


def run_properties(feature):
    """Keep the source evidence intact while display path commands hold the geometry."""
    props = dict(feature["properties"])
    if feature["geometry"]["type"] == "Point":
        props.setdefault("wgs84", feature["geometry"]["coordinates"])
    return props


def output_layer(props, dataset):
    key = str(props.get("kind", props.get("edge_class", ""))).upper()
    if dataset == "domains":
        return "domain"
    if "GAP" in key:
        return "gap"
    if props.get("run_id") == "DIAGNOSTIC_B0_OBSTACLE_VIEW":
        return "supplement"
    if dataset == "edges":
        return "terminal_edge" if "TERMINAL" in key else "derived"
    section = str(props.get("section") or key).upper()
    if "HOSTED" in section or "GEOAPIFY" in section or "HOSTED" in str(props.get("run_id", "")).upper():
        return "hosted"
    if "TERMINAL" in section or "PORT" in section:
        return "route_terminal"
    if "DERIVED" in section or "EDGE_BAND" in section:
        return "route_derived"
    if "CONTACT" in section:
        return "contact"
    if key in {"ROUTE_ENDPOINT", "APPROACH_ENDPOINT", "ENDPOINT"}:
        return "endpoint"
    if props.get("status") == "PLANAR_CONFLICT_ROUTE_REQUIRES_REVIEW":
        return "route_conflict"
    return "route_native"


def normalize(geometry, anchor):
    def coordinate(p):
        return round(p[0] - anchor[0], 3), round(anchor[1] - p[1], 3)

    def path(coords, closed=False):
        return "M" + "L".join(f"{x},{y}" for x, y in map(coordinate, coords)) + ("Z" if closed else "")

    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [{"point": coordinate(geometry.coords[0])}]
    if geometry.geom_type == "LineString":
        return [{"d": path(geometry.coords)}]
    if geometry.geom_type == "Polygon":
        return [{"d": "".join(path(ring.coords, True) for ring in [geometry.exterior, *geometry.interiors]), "area": True}]
    return [item for child in getattr(geometry, "geoms", []) for item in normalize(child, anchor)]


def camera_bounds(polygon, anchor):
    x0, y0, x1, y1 = polygon.bounds
    return [round(x0 - anchor[0], 3), round(anchor[1] - y1, 3), round(x1 - x0, 3), round(y1 - y0, 3)]


def lookup_coordinate(scene, node_id):
    return next((entry["coordinate"] for entry in scene["r4_entrances"] if entry["native_id"] == node_id), None)


def scene_payload(scene, old, old_spaces, frozen, output_features):
    sid = scene["scene_id"]
    clip_path = frozen / scene["osm_clip"]
    clip = read_json(clip_path)
    building = metric(scene["building_footprint"])
    anchor = (building.centroid.x, building.centroid.y)
    origin = transform(PROJECTOR.transform, Point(scene["start"]))
    terminal = scene["target"]
    native_features = [record("target", building, dict(native_id=scene["building_native_id"],
                       label=scene["label"], source="FROZEN_OSM")),
                       record("origin", origin, dict(native_id=scene.get("start_native_id"), wgs84=scene["start"],
                                                      label="冻结起点", source="FROZEN_OSM"))]
    for entry in scene["r4_entrances"]:
        node_id = entry["native_id"]
        mode = "exit" if entry.get("tags", {}).get("entrance") == "exit" else "entrance"
        native_features.append(record(mode, transform(PROJECTOR.transform, Point(entry["coordinate"])),
                                      dict(entry, label=MAP_NAMES.get(node_id, "登记入口"),
                                           wgs84=entry["coordinate"], source="FROZEN_OSM")))
    if not scene["r4_entrances"]:
        native_features.append(record("proxy", transform(PROJECTOR.transform, Point(terminal)),
                                      dict(label="冻结代理目标", wgs84=terminal, status="PROXY_OR_UNCERTAIN")))
    area_focus = set(scene["r4_focus_space_ids"]) | ({SOUTH, NORTH} if sid == MUSEUM else set())
    for row in old_spaces:
        tags = row["tags"]
        if row["native_id"] in area_focus:
            layer = "plaza"
        elif row.get("category") == "CONTEXT_GRASS_FLOWERBED_WATER":
            layer = "water" if tags.get("natural") == "water" or tags.get("waterway") == "riverbank" else "grass"
        else:
            continue
        geometry = metric(row["geometry"])
        native_features.append(record(layer, geometry, area_properties(row)))


    experiment_features = []
    for dataset, feature in output_features:
        if not feature.get("geometry"):
            continue
        props = run_properties(feature)
        layer = output_layer(props, dataset)
        geometry = metric(feature["geometry"])
        if layer == "route_native" and geometry.geom_type == "Point":
            layer = "endpoint"
        experiment_features.append(record(layer, geometry, props))
        if layer == "gap" and geometry.geom_type == "LineString" and props.get("length_m") is not None:
            label = f'{props["length_m"]:.2f} m 未支持'
            experiment_features.append(record("gap_label", geometry.interpolate(.5, normalized=True), dict(props, label=label)))

    # Historical geometry and contacts come from frozen machine outputs and native IDs.
    baseline_paths = [frozen / scene["historical_local_route"], frozen / scene["historical_hosted_route"]]
    if scene.get("historical_local_diagnostic"):
        baseline_paths.append(frozen / scene["historical_local_diagnostic"])
    for index, path in enumerate(baseline_paths):
        saved = read_json(path)
        if index == 1:
            for feature in saved["features"]:
                if feature.get("geometry"):
                    native_features.append(record("hosted", metric(feature["geometry"]),
                                                  dict(source="HISTORICAL_HOSTED_BASELINE", native_id=None,
                                                       evidence_status="OBSERVED_SAVED_PROVIDER_RESULT")))
            continue
        saved = saved.get("route", saved)
        if saved.get("geometry"):
            native_features.append(record("historical", metric(saved["geometry"]),
                                          dict(status=saved.get("status"), evidence_status="HISTORICAL_B0",
                                               length_m=saved.get("length_m"), endpoint=saved.get("route_end"))))
    node_coords = {f"node/{row['id']}": [row["lon"], row["lat"]] for row in clip["elements"] if row["type"] == "node"}
    for p in old.get("boundary_contacts", []):
        if p.get("evidence") != "B0_NATIVE_NODE_ON_PERIMETER":
            continue
        node_id = next((x for x in p.get("native_ids", []) if x.startswith("node/")), None)
        if node_id not in node_coords:
            continue
        p = dict(p, native_id=node_id, wgs84=node_coords[node_id], source="FROZEN_OSM")
        native_features.append(record("contact", transform(PROJECTOR.transform, Point(p["wgs84"])), p))

    # Northern relation is large. Keep the standard comparison centred on both entrances.
    overview = fit_bounds([building], padding=80, minimum=360)
    for layer, area, props in list(native_features):
        if layer != "plaza" or props["native_id"] not in MAP_NAMES:
            continue
        visible = area.intersection(overview.buffer(-16))
        if not visible.is_empty:
            native_features.append(record("area_label", visible.representative_point(), props))
    native_features.append(record("building_label", building.representative_point(),
                                  dict(label=scene["label"].replace("人民广场馆", ""), source="FROZEN_OSM")))
    terminal_point = transform(PROJECTOR.transform, Point(terminal))
    terminal_bounds = fit_bounds([terminal_point], padding=16, minimum=62)
    north_coord = lookup_coordinate(scene, "node/6897145227")
    north_point = transform(PROJECTOR.transform, Point(north_coord)) if north_coord else terminal_point
    north_bounds = fit_bounds([north_point], padding=19, minimum=74)
    saved_routes = [g for layer, g, _ in experiment_features if layer.startswith("route") or layer in {"gap", "supplement"}]
    historical = [g for layer, g, _ in native_features if layer in {"historical", "hosted"}]
    # Fixed camera per scene and panel. Old/new/ablation never get individual fitting.
    context = fit_bounds([building, origin, *saved_routes, *historical], padding=46, minimum=420)
    map_bounds = fit_bounds([overview, terminal_bounds, north_bounds, context], padding=1)
    features = basemap(clip, map_bounds) + native_features + experiment_features
    packed = []
    for layer, geometry, props in features:
        if not geometry.intersects(map_bounds):
            continue
        clipped = geometry.intersection(map_bounds)
        parts = normalize(clipped, anchor)
        if parts:
            packed.append(dict(layer=layer, shape=parts, props=props))
    return dict(id=sid, label=scene["label"], building_id=scene["building_native_id"], features=packed,
                bounds=dict(overview=camera_bounds(overview, anchor), context=camera_bounds(context, anchor),
                            terminal=camera_bounds(terminal_bounds, anchor), north=camera_bounds(north_bounds, anchor)),
                contacts=[f["props"] for f in packed if f["layer"] == "contact"],
                source_clip=scene["osm_clip"], source_sha256=digest(clip_path), historical_geometry_sha256={path.name: digest(path) for path in baseline_paths},
                focus_ids=sorted(area_focus), old_result={k: old[k] for k in (
                    "verified_b1_edges", "verified_b2_additional_edges", "eligible_entrance_count", "local_b0_frozen_replay"
                )})


def build(input_root, run_root, output_root, backdrop_only=False):
    scene_contract = input_root / "runs/source_scene_contracts.json"
    space_doc = input_root / "runs/source_open_spaces.json"
    old_runs = input_root / "runs/experiment.json"
    scenes = read_json(scene_contract)["scenes"]
    old = {row["scene_id"]: row for row in read_json(old_runs)["scenes"]}
    spaces = defaultdict(list)
    for row in read_json(space_doc)["features"]:
        spaces[row["scene_id"]].append(row)
    data_inputs = {"derived_edges": "edges", "allowed_domains": "domains", "routes": "routes"}
    grouped = defaultdict(list)
    paths = {}
    if not backdrop_only:
        for file_name, dataset in data_inputs.items():
            path = run_root / "data" / f"{file_name}.geojson"
            paths[file_name] = digest(path)
            features = read_json(path)["features"]
            if dataset == "edges":
                # Uniform source-order display subset per face. Keep every terminal port.
                # The complete original GeoJSON remains available for download and audit.
                groups = defaultdict(list)
                for feature in features:
                    props = feature["properties"]
                    groups[(props["scene_id"], props["source_area_id"])].append(feature)
                for (scene_id, _), rows in groups.items():
                    line_edges = [row for row in rows if "CONNECTOR" not in row["properties"]["kind"]]
                    port_edges = [row for row in rows if "CONNECTOR" in row["properties"]["kind"]]
                    if len(line_edges) > 900:
                        line_edges = [line_edges[i * len(line_edges) // 900] for i in range(900)]
                    grouped[scene_id].extend((dataset, row) for row in line_edges + port_edges)
            else:
                for feature in features:
                    props = feature["properties"]
                    if props.get("run_id") == "HISTORICAL_HOSTED_BASELINE":
                        continue
                    if props.get("kind") == "HISTORICAL_LOCAL_APPROACH":
                        continue
                    grouped[props["scene_id"]].append((dataset, feature))
        evidence_file = run_root / "data/edge_evidence.jsonl"
        selected = {feature["properties"]["qualified_id"]: feature["properties"]
                    for rows in grouped.values() for dataset, feature in rows if dataset == "edges"}
        with evidence_file.open(encoding="utf-8-sig") as handle:
            for line in handle:
                row = json.loads(line)
                properties = selected.pop(row["qualified_id"], None)
                if properties is not None:
                    properties.update(row)
        if selected:
            raise ValueError("Displayed edges missing individual evidence")
        paths["edge_evidence"] = digest(evidence_file)
        experiment = read_json(run_root / "runs/experiment.json")
        outcomes = read_json(run_root / "data/entrance_approach.json")
        paths["experiment"] = digest(run_root / "runs/experiment.json")
        paths["entrance_approach"] = digest(run_root / "data/entrance_approach.json")
        diagnostic_path = run_root / "data/native_prefix_diagnostic.geojson"
        diagnostic_results = run_root / "data/native_prefix_diagnostic.json"
        if diagnostic_path.is_file() and diagnostic_results.is_file():
            paths["native_prefix_diagnostic_geometry"] = digest(diagnostic_path)
            paths["native_prefix_diagnostic"] = digest(diagnostic_results)
            for feature in read_json(diagnostic_path)["features"]:
                props = feature["properties"]
                if "GAP" not in props["kind"]:
                    grouped[props["scene_id"]].append(("routes", feature))
            outcomes["supplement"] = read_json(diagnostic_results)["records"]
        for run_id, run in experiment["runs"].items():
            for result in run["scenes"]:
                if result["scene_id"] != MUSEUM:
                    continue
                entry = (result.get("entrances") or result.get("strict_entrances") or {}).get("node/6897145227")
                if entry and entry.get("endpoint"):
                    properties = dict(entry, kind="APPROACH_ENDPOINT", run_id=run_id, scene_id=MUSEUM)
                    grouped[MUSEUM].append(("routes", {"type":"Feature", "geometry":{
                        "type":"Point", "coordinates":entry["endpoint"]}, "properties":properties}))
    else:
        experiment, outcomes = {}, {}
    payload = dict(schema="REV1_VISUAL_EVIDENCE_1", crs="EPSG:32651", coordinate_input="WGS84 lon,lat",
                   figures=FIGURES, sources=paths, preview=backdrop_only,
                   scenes=[scene_payload(scene, old[scene["scene_id"]], spaces[scene["scene_id"]],
                                         input_root, grouped[scene["scene_id"]]) for scene in scenes],
                   experiment=strip_geometry(experiment), outcomes=strip_geometry(outcomes))
    output_root.mkdir(exist_ok=True, parents=True)
    template = ROOT / "visuals"
    if output_root != template.resolve():
        for filename in ("index.html", "style.css", "review.js"):
            copyfile(template / filename, output_root / filename)
    (output_root / "scene_data.js").write_text(
        "window.REV1_DATA=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + ";\n",
        encoding="utf-8")
    print(json.dumps(dict(scenes=len(scenes), features=Counter(x["layer"] for s in payload["scenes"] for x in s["features"]),
                          sources=paths, preview=backdrop_only), ensure_ascii=False))
    return payload


def strip_geometry(value):
    if isinstance(value, list):
        return [strip_geometry(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_geometry(item) for key, item in value.items()
                if key not in {"geometry", "building_footprint", "coordinates", "views", "case_catalog"}}
    return value


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=ROOT / "frozen_r4")
    parser.add_argument("--run-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=ROOT / "visuals")
    parser.add_argument("--backdrop-only", action="store_true", help="Build source-only author preview")
    parser.add_argument("--browser-only", action="store_true", help="Open and verify existing production files")
    parser.add_argument("--browser", action="store_true", help="Export standalone SVG and verify browser")
    args = parser.parse_args()
    if not args.browser_only:
        build(args.input_root.resolve(), args.run_root.resolve(), args.output_root.resolve(), args.backdrop_only)
    if args.browser or args.browser_only:
        from .visual_browser_check import check
        check(args.output_root.resolve(), export=not args.browser_only, preview=args.backdrop_only)


if __name__ == "__main__":
    main()
