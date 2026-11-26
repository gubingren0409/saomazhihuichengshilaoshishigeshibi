"""Independent spatial and route checks for the R3 natural case, without its method code."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from hashlib import file_digest
from itertools import combinations, pairwise
import json
import math
from pathlib import Path
import re
import sys

from pyproj import Transformer
from shapely import make_valid, union_all
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
POS = "INFERRED_WALKABLE"
NATIVE = "NATIVE_WALKABLE"
REST = "RESTRICTED"
UNKNOWN = "UNKNOWN"
STATES = (NATIVE, POS, REST, UNKNOWN)
REGIONS = ("I-REGION", "I-REGION-ABL", "I-REGION-NET-ABL")
EPS = 1e-5
AREA_EPS = 2e-4
AREA_SOURCE = "relation/2153738"
EXIT_ID = "node/6897145227"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def close(a, b, description, tolerance=EPS):
    if abs(a-b) > tolerance:
        raise ValueError(f"{description}: {a} vs {b}")


def metric(geometry):
    return make_valid(transform(PROJECT, shape(geometry)))


def parts(items):
    return union_all(list(items), grid_size=1e-7)


def features(path):
    return [(metric(f["geometry"]), f["properties"]) for f in read(path)["features"]]


def covers(geometry, line, label):
    close(line.difference(geometry.buffer(EPS)).length, 0, label)


def area_check(path, record, cfg, window, native, hard, park, source):
    rows = features(path)
    masks = {s: parts(g for g, p in rows if p["walkability_state"] == s) for s in STATES}
    ids = {}
    reasons = Counter()
    for g, p in rows:
        ident = p["region_id"]
        i, j, _ = map(int, ident.split("/")[1:])
        step = cfg["cell_m"]
        grid = box(i*step, j*step, (i+1)*step, (j+1)*step)
        close(g.difference(grid).area, 0, f"grid-cell containment {ident}")
        close(g.area, p["area_m2"], f"cell area {ident}")
        if ident in ids or not g.area:
            raise ValueError("Repeated or non-area region cell")
        ids[ident] = g
        s = p["walkability_state"]
        if s == POS:
            if not p["evidence_sources"] or p["hard_conflicts"] or p["source_status"] != "inferred":
                raise ValueError("Missing evidence or wrong role on inferred cell")
            if not p["assumptions"] or p["uncertainty_level"] != "CONDITIONAL_UNCALIBRATED":
                raise ValueError("Inferred cell treated as verified")
            reason = p["decision_reason"]
            refs = p["evidence_sources"]
            for ref in refs:
                typ, n = ref.split("/")
                known = {"node": source.nodes, "way": source.ways, "relation": source.relations}
                if int(n) not in known[typ]:
                    raise ValueError(f"Missing original evidence object {ref}")
            if reason == "PARK_AND_REGISTERED_FRONTAGE_AND_WALKWAY":
                if not {EXIT_ID, "way/161090899", "way/404709025"} <= set(refs) or not g.intersects(park):
                    raise ValueError("Missing explicit park, frontage or registered exit evidence")
                if g.distance(Point(source.projected[6897145227])) > cfg["door_near_m"]+EPS:
                    raise ValueError("Inferred frontage beyond the locked door relationship")
            if reason == "MAPPED_PEDESTRIAN_FACE_AND_WALKWAY_ADJACENCY":
                if AREA_SOURCE not in refs or g.distance(native) > cfg["face_near_m"]+EPS:
                    raise ValueError("Inferred cell lacks raw pedestrian-face adjacency")
            if reason != "GEOMETRY_AND_NETWORK_ONLY_ABLATION" and reason not in {
                "PARK_AND_REGISTERED_FRONTAGE_AND_WALKWAY", "MAPPED_PEDESTRIAN_FACE_AND_WALKWAY_ADJACENCY",
                "PARK_AND_OBSERVED_WALKWAYS_ON_DISTINCT_SIDES", "PAVING_AND_OBSERVED_NETWORK_ADJACENCY",
            }:
                raise ValueError("Inferred cell without accepted contextual reason")
            roads = [source.ways[int(ref.split("/")[1])] for ref in refs if ref.startswith("way/")]
            lines = [LineString([source.projected[k] for k in r["nodes"]]) for r in roads
                     if r.get("tags", {}).get("highway") in {"path", "footway", "pedestrian", "steps", "corridor", "living_street"}]
            if not lines or min(g.distance(line) for line in lines) > cfg["network_near_m"]+EPS:
                raise ValueError("Inferred cell lacks cited mapped pedestrian line within network threshold")
            reasons[reason] += 1
        if s == UNKNOWN and p["uncertainty_level"] != "UNRESOLVED":
            raise ValueError("Unknown cell semantics were promoted")
    overlap = sum(a.intersection(b).area for a, b in combinations(masks.values(), 2))
    close(overlap, 0, "positive-area overlap across classes", AREA_EPS)
    union = parts(masks.values())
    close(sum(g.area for g, _ in rows), union.area, "fragment self-overlap", AREA_EPS)
    close(union.symmetric_difference(window).area, 0, "full four-state partition", AREA_EPS)
    close(masks[NATIVE].symmetric_difference(native.intersection(window).difference(hard)).area, 0,
          "exact raw mapped pedestrian face minus conflicts", AREA_EPS)
    close(masks[REST].symmetric_difference(hard.intersection(window)).area, 0,
          "mapped hard/background conflict partition", AREA_EPS)
    close(masks[POS].intersection(hard).area, 0, "inferred area expanded into hard source geometry", AREA_EPS)
    for state, value in masks.items():
        close(value.area, record["area_m2"][state], f"whole-class area {state}", AREA_EPS)
    return masks, ids, dict(cells=len(rows), recomputed_m2={s:g.area for s,g in masks.items()},
                            overlap_m2=overlap, inferred_reasons=dict(reasons),
                            inferred_on_park_m2=masks[POS].intersection(park).area,
                            park_in_window_m2=park.intersection(window).area,
                            inferred_known_hard_overlap_m2=masks[POS].intersection(hard).area)


def raw_way(line, edge, source):
    match = re.match(r"way/(\d+)(?:/(\d+))?$", edge["source_id"])
    if not match:
        # Frozen graph can retain real shared-node transitions with zero geometry.
        if line.length <= EPS and all(str(edge.get(k, "")).startswith("node/") for k in ("u", "v")):
            return
        raise ValueError(f"Unexpected native provenance: {edge['source_id']}")
    number, index = match.groups()
    way = source.ways[int(number)]
    xy = [source.projected[k] for k in way["nodes"]]
    if index is not None:
        xy = xy[int(index):int(index)+2]
    geometry = LineString(xy)
    covers(geometry, line, "exact original native route geometry")
    tags = way.get("tags", {})
    if edge.get("tags") is not None and tags != edge["tags"]:
        raise ValueError("Routed native source tags were modified")
    direction = geometry.project(Point(line.coords[-1])) - geometry.project(Point(line.coords[0]))
    oneway = tags.get("oneway:foot", tags.get("oneway") if tags.get("highway") in {"footway","path","steps"} else None)
    if direction > EPS and oneway in {"-1", "reverse"} or direction < -EPS and oneway in {"yes","1","true"}:
        raise ValueError("Routed native segment violates source direction")
    foot = tags.get("foot", tags.get("access"))
    if foot in {"no","private","customers","destination","delivery","permit","restricted"} or tags.get("locked") == "yes":
        raise ValueError("Routed native segment has explicit access restriction")


def frozen_geometry(rev, edge_ids, port_ids):
    evidence, ports = {}, {}
    path = rev / "data/edge_evidence.jsonl"
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            if '"scene_id":"sh-huangpu-01"' not in line:
                break
            row = json.loads(line)
            if row["edge_id"] in edge_ids:
                evidence[row["edge_id"]] = row
            for n,xy in zip((row["u"],row["v"]),row["coordinates_metric"]):
                if n in port_ids:
                    ports[n] = xy
    if evidence.keys() != edge_ids or ports.keys() != port_ids:
        raise ValueError("Missing original R4-REV1 face edges or interface nodes")
    return evidence, ports


def route_check(route, query, line_export, mask, cell_ids, source, original, cfg, hard):
    edges = route["edges"]
    if len(edges) != len(line_export):
        raise ValueError("Machine/visual GeoJSON route edge cardinality differs")
    if not edges:
        if route["reached"] and math.dist(query["source"]["xy"], query["target"]["xy"]) > EPS:
            raise ValueError("Claimed nonzero route lacks actual geometry")
        return {"status":route["status"],"length_m":route["length_m"],"inferred_m":0,"route_edges":0}
    close(math.dist(query["source"]["xy"], edges[0]["xy"][0]), 0, "fixed start")
    residual = math.dist(query["target"]["xy"], edges[-1]["xy"][-1])
    if route["reached"]:
        close(residual, 0, "unchanged reached target")
    else:
        close(residual, route["residual_m"], "explicit retained gap")
    for a, b in pairwise(edges):
        close(math.dist(a["xy"][-1], b["xy"][0]), 0, "route continuity")
    lengths = Counter()
    by_layer = Counter()
    unknown_by_edge = Counter()
    for i,e in enumerate(edges):
        geom = LineString(e["xy"])
        layer, kind = e["layer"], e["geometry_kind"]
        exported, p = line_export[i]
        if p["sequence"] != i or p["layer"] != layer or p["source_id"] != e["source_id"]:
            raise ValueError("Machine route GeoJSON attributes differ")
        close(geom.hausdorff_distance(exported), 0, "machine route GeoJSON geometry")
        close(geom.length, e["length_m"], "route edge length")
        lengths[kind] += geom.length
        by_layer[layer] += geom.length
        if layer == "native":
            raw_way(geom, e, source)
        if kind in {"DERIVED_FROM_TAGGED_PEDESTRIAN_AREA", "DERIVED_TERMINAL_CONNECTOR"}:
            old = original[e["edge_id"]]
            covers(LineString(old["coordinates_metric"]), geom, "original mapped-face derived geometry")
            directions = {(old["u"],old["v"])}
            if old["direction"] == "BIDIRECTIONAL":
                directions.add((old["v"],old["u"]))
            if (e["u"],e["v"]) not in directions:
                raise ValueError("Frozen old route source edge endpoints changed")
        if kind in {"FROZEN_INFERRED_REGION","NEW_GRID_WITHIN_MAPPED_FACE","BOUNDED_UNKNOWN_PORTAL",
                    "EXACT_REGION_PORTAL"}:
            state = {"inferred": POS, "derived": NATIVE, "unknown": UNKNOWN}[layer]
            if any(ident not in cell_ids for ident in e["source_id"].split("|")):
                raise ValueError("New region route has no frozen cell source")
            covers(mask[state], geom, "new route inside corresponding frozen state")
            close(geom.intersection(hard.buffer(-EPS)).length, 0, "new route restricted conflict")
            if layer in {"inferred","unknown"} and geom.length > EPS and e.get("level") != "UNKNOWN_LOCAL_OUTDOOR_ASSUMPTION":
                raise ValueError("No explicit unknown level assumption")
            if layer == "inferred":
                close(e["cost_m"], geom.length*cfg["inference_cost_multiplier"], "inference layer cost")
            if layer == "unknown":
                unknown_by_edge[e["u"],e["v"]] += geom.length
    if any(m > cfg["unknown_portal_budget_m"] + EPS for m in unknown_by_edge.values()):
        raise ValueError("Unbounded unknown interface crossing")
    for layer, m in route["layer_lengths"].items():
        close(by_layer[layer], m, f"route layer {layer}")
    close(sum(lengths.values()), route["length_m"], "route geometry")
    close(sum(e["cost_m"] for e in edges), route["cost_m"], "route costs")
    return {"status":route["status"],"length_m":sum(lengths.values()),"inferred_m":by_layer["inferred"],
            "route_edges":len(edges),"geometry_kind_length_m":dict(lengths),
            "endpoint_residual_m":residual}


def main(root, output):
    sys.path.insert(0, str(root))
    from inputs.rev1.src.native_adapter import Source
    rev = root / "inputs/rev1"
    raw_path = rev / "frozen_r4/data/source/sh-huangpu-01.osm.json"
    source = Source(read(raw_path))
    cfg = read(root / "config/region.json")
    north = read(root / "runs/north.json")
    gate = read(root / "audits/S_FREEZE.json")
    freeze = read(root / "data/north_surface_freeze.json")
    qdoc = read(root / "data/north_queries.json")
    assert gate["status"] == "S1_FROZEN_INDEPENDENT_CHECK_PASS"
    assert freeze["status"] == "FROZEN_BEFORE_QUERY_CONSTRUCTION"
    assert freeze["config_sha256"] == sha(root / "config/region.json")
    assert qdoc["queries"] == north["queries"]
    assert qdoc["region_sha256"] == north["surface"]["sha256"]
    assert north["target"]["id"] == EXIT_ID and north["target"]["tags"]["entrance"] == "exit"
    assert list(source.coord(EXIT_ID)) == north["target"]["wgs84"]
    assert north["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT"
    coord = source.projected[6897145227]
    close(math.dist(coord, freeze["anchor"]["anchor_xy"]), 0, "raw registered exit as search anchor")
    (window, window_props), = features(root / "data/north_domain.geojson")
    assert window_props["role"] == "SEARCH_DOMAIN_ONLY"
    expected_window = Point(coord).buffer(cfg["domain_radius_m"], quad_segs=32)
    close(window.symmetric_difference(expected_window).area, 0, "search window raw center and fixed radius", AREA_EPS)
    native, park = [source.area(ident) for ident in (AREA_SOURCE, "way/404709025")]
    source_layers = features(root / "data/north_sources.geojson")
    for geometry, properties in source_layers:
        ident = properties["source_id"]
        raw_object = source.obj(ident)
        if raw_object["tags"] != properties["tags"]:
            raise ValueError("Map source tags changed")
        raw_area = source.area(ident)
        if raw_area is not None:
            close(geometry.symmetric_difference(raw_area).area, 0, "map source area geometry", AREA_EPS)
    obstacles, _ = source.obstacles([window])
    hard_sources = [item for item in obstacles if item["geometry"].intersects(window)]
    hard = parts(obj["geometry"] if obj["geometry"].area else obj["geometry"].buffer(cfg["hard_line_clearance_m"])
                 for obj in hard_sources)
    cases = {}
    old_north = read(root / "inputs/north/runs/experiment.json")["source_geometry"]
    old_line = LineString([PROJECT(*old_north["approach_wgs84"]),coord])
    for stage in freeze["stages"]:
        name = stage["variant"]
        path = root / stage["path"]
        assert sha(path) == stage["sha256"]
        assert stage["surface_sha256"] == north["variants"][name]["surface"]["sha256"]
        cases[name] = area_check(path, north["variants"][name]["surface"], cfg, window, native, hard, park, source)
    assert set(cases) == set(REGIONS)
    assert north["variants"]["I-REGION"]["surface"]["sha256"] == north["variants"]["I-REGION-NET-ABL"]["surface"]["sha256"]
    route_features = defaultdict(list)
    for g,p in features(root / "data/north_routes.geojson"):
        if p["role"] == "route_segment":
            route_features[p["variant"],p["query_id"]].append((g,p))
    interfaces = defaultdict(dict)
    for point,p in features(root / "data/north_interfaces.geojson"):
        if p["role"] == "registered_exit":
            close(point.distance(Point(coord)),0,"map export original exit")
        if p["role"] == "network_interface":
            interfaces[p["variant"]][p["id"]] = (point,p)
    all_routes = [r for v in north["variants"].values() for r in v["routes"].values()]
    edge_ids = {e["edge_id"] for r in all_routes for e in r["edges"] if e["geometry_kind"]
                in {"DERIVED_FROM_TAGGED_PEDESTRIAN_AREA","DERIVED_TERMINAL_CONNECTOR"}}
    port_ids = {ident for rows in interfaces.values() for ident in rows if ident.startswith("grid/")}
    old, old_ports = frozen_geometry(rev, edge_ids, port_ids)
    for name, model in north["variants"].items():
        for port in model.get("interfaces", []):
            ident = port["id"]
            point, props = interfaces[name][ident]
            xy = source.projected[int(ident.split("/")[1])] if ident.startswith("node/") else old_ports[ident]
            close(point.distance(Point(xy)),0,"exact existing interface source coordinates")
            close(math.dist(port["xy"],xy),0,"route interface coordinates")
            if props["source_ids"] != port["source_ids"] or port["cell_id"] not in cases[name][1]:
                raise ValueError("Missing interface evidence or frozen area-cell linkage")
    checks = {}
    query_map = {q["query_id"]:q for q in north["queries"]}
    for name, model in north["variants"].items():
        mask, cells, _ = cases.get(name, ({},{},{}))
        checks[name] = {}
        for qid,value in model["routes"].items():
            if name in REGIONS and value["surface_sha256"] != model["surface"]["sha256"]:
                raise ValueError("Query route refers to a different frozen surface")
            checks[name][qid] = route_check(value,query_map[qid],route_features[name,qid],
                                           mask,cells,source,old,cfg,hard)
    main_checks = checks["I-REGION"]
    local = {qid:c for qid,c in main_checks.items() if qid != "NORTH-DOOR"}
    output_doc = {
        "status":"INDEPENDENT_NATURAL_GEOMETRY_TOPOLOGY_CHECK_PASS",
        "actor":"/root/r3_s_audit",
        "scope":"Raw frozen source, spatial partition, evidence, adopted graph edges, routes and GeoJSON; independent logic, frozen parser only",
        "raw_clip_sha256":sha(raw_path),"surface_checks":{k:v[2] for k,v in cases.items()},
        "raw_hazards_in_domain":[obj["id"] for obj in hard_sources],
        "separate_classification_and_queries":True,"search_window_role":window_props["role"],
        "audited_source_map_features":len(source_layers),
        "outside_1m_historical_gap_band_m2_diagnostic_only":cases["I-REGION"][0][POS].difference(old_line.buffer(1)).area,
        "native_interfaces":sum(p.startswith("node/") for p in interfaces["I-REGION"]),
        "existing_frozen_face_interfaces":sum(p.startswith("grid/") for p in interfaces["I-REGION"]),
        "query_checks":checks, "reused_region_sha256":north["surface"]["sha256"],
        "local_reused_queries":len(local),
        "original_port_pair_queries":sum(qid.startswith("NORTH-PAIR-") for qid in local),
        "supplemental_exploratory_control_queries":sum(qid.startswith("NORTH-CONTROL-") for qid in local),
        "local_reused_queries_using_inferred":sum(r["inferred_m"] > EPS for r in local.values()),
        "route_segments_checked":sum(r["route_edges"] for table in checks.values() for r in table.values()),
        "preserved_original_exit":north["target"],"field_validation":"NOT_VERIFIED",
        "unknown_not_observed":True,"external_requests":0,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(output_doc,stream,indent=2,ensure_ascii=False)
        stream.write("\n")
    print(output_doc["status"],output_doc["route_segments_checked"],output_doc["local_reused_queries_using_inferred"])


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "audits/region_independent.json")
    args = parser.parse_args()
    main(args.root.resolve(),args.output.resolve())
