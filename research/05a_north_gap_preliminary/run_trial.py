"""Run a one-edge hypothetical approach test against the sealed R4-REV1 source."""
import argparse
from hashlib import file_digest
import json
import math
from pathlib import Path
import sys

import networkx as nx
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT.parent / "OSM_GEOAPIFY_R4_REV1"
OSM_CLIP = "frozen_r4/data/source/sh-huangpu-01.osm.json"
PREFIX = "data/native_prefix_diagnostic.json"
AREA = "relation/2153738"
SITE = "way/404709025"
BUILDING = "way/161090899"
DOOR = "node/6897145227"
APPROACH_WAY = "way/178719573"
SOURCE_SEGMENT_INDEX = 110
EPS_M = .000001
GRADE_TAGS = {"level", "layer", "repeat_on", "bridge", "tunnel", "indoor", "covered",
              "ele", "incline", "ramp", "step_count", "height", "min_height"}
ACCESS_TAGS = {"access", "foot", "access:conditional", "foot:conditional", "oneway:foot"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def layer_evidence(source, line):
    confirmed = []
    unresolved = []
    for kind, group in (("node", source.nodes), ("way", source.ways), ("relation", source.relations)):
        for number, raw in group.items():
            tags = raw.get("tags", {})
            selected = {k: v for k, v in tags.items() if k in GRADE_TAGS | ACCESS_TAGS}
            if tags.get("highway") in {"steps", "elevator"}:
                selected["highway"] = tags["highway"]
            if not selected:
                continue
            ident = f"{kind}/{number}"
            if kind == "node":
                geo = Point(source.projected[number])
            elif kind == "relation" or tags.get("area") == "yes" or "building" in tags or "building:part" in tags:
                geo = source.area(ident)
                if geo is None:
                    coordinates = source.known_coords(raw)
                    if coordinates and LineString(coordinates if len(coordinates) > 1 else coordinates * 2).envelope.intersects(line):
                        unresolved.append({"source": ident, "tags": selected})
                    continue
            else:
                coords = source.known_coords(raw)
                if len(coords) != len(raw["nodes"]) or len(coords) < 2:
                    if coords and LineString(coords if len(coords) > 1 else coords * 2).envelope.intersects(line):
                        unresolved.append({"source": ident, "tags": selected})
                    continue
                geo = LineString(coords)
            if geo.distance(line) <= EPS_M:
                inter = geo.intersection(line)
                confirmed.append({"source": ident, "tags": selected, "intersection_m": inter.length,
                                  "position": "APPROACH_ENDPOINT" if geo.distance(Point(line.coords[0])) <= EPS_M
                                  and inter.length <= EPS_M else "ON_CANDIDATE"})
    return confirmed, unresolved


def run(original, out):
    # Load the frozen implementation without writing Python caches in the source directory.
    sys.path.insert(0, str(original))
    from src.audit_native_prefix import native_view
    from src.native_adapter import PROJECT, Source, grounded_lines, load_frozen_engine, node_number
    from src.route_measure import NATIVE, obstacle_index, prepare_weights, walk

    input_paths = (OSM_CLIP, PREFIX, "data/native_prefix_diagnostic.geojson",
                   "frozen_r4/src/frozen_r1/local_route.py", "delivery/OPEN_REVIEW.zip")
    protected_before = {path: sha(original / path) for path in input_paths}
    if protected_before["delivery/OPEN_REVIEW.zip"] != "f2de5326ffbffe1e62c0fa5d622cec6645582342824ea1ae13716789d5af5ee0":
        raise ValueError("Unexpected original R4-REV1 archive")
    if any((out / name).exists() for name in ("trial.json", "trial.geojson")):
        raise FileExistsError("Use a fresh output directory")
    raw = read(original / OSM_CLIP)
    source = Source(raw)
    old = read(original / PREFIX)
    approach = next(row["alternate"] for row in old["records"] if row["subject"] == "NORTH_APPROACH")
    exit_coord = source.coord(DOOR)
    exit_tags = source.nodes[node_number(DOOR)].get("tags", {})
    endpoint = tuple(approach["endpoint"])
    if exit_tags.get("entrance") != "exit" or exit_coord != tuple(approach["original_coordinate"]):
        raise ValueError("Frozen exit identity or coordinate differs")
    line = LineString([PROJECT(*endpoint), PROJECT(*exit_coord)])
    gap_m = line.length
    park, plaza = source.area(SITE), source.area(AREA)
    if park is None or plaza is None:
        raise ValueError("Frozen park or pedestrian geometry cannot be resolved")

    engine = load_frozen_engine(original / "frozen_r4")
    segments, endings, _ = engine._segments(raw)
    base, _ = engine._build_graph(segments, endings, ())
    prepare_weights(base)
    obstacles, unlocated = source.obstacles([])
    filtered, _, _ = native_view(base, obstacle_index(obstacles))
    ground_lines = grounded_lines(source, segments)
    walked = [plaza.intersection(line)]
    walked.extend(geom.intersection(line) for _, geom in ground_lines if geom.intersects(line))
    walkable_m = unary_union(walked).length
    overlap_records = []
    for row in obstacles:
        geom = row["geometry"]
        inter = geom.intersection(line)
        if inter.is_empty:
            continue
        own_exit_touch = (row["id"] == BUILDING and inter.geom_type == "Point"
                          and inter.distance(Point(line.coords[-1])) <= EPS_M)
        overlap_records.append({"source": row["id"], "kind": row["kind"], "intersection_m": inter.length,
                                "status": "ORIGINAL_EXIT_BOUNDARY_TOUCH_ONLY" if own_exit_touch else "POTENTIAL_OBSTACLE"})
    collisions = [r for r in overlap_records if r["status"] == "POTENTIAL_OBSTACLE"]
    grade, grade_unresolved = layer_evidence(source, line)
    grade_fields = [x for x in grade if any(k in GRADE_TAGS or k == "highway" for k in x["tags"])]
    # No promotion to a verified edge. This query merely tests the consequence of allowing it.
    if collisions or grade_fields or grade_unresolved:
        raise ValueError("Candidate has a recorded obstacle or requires explicit grade adjudication")
    approach_way = source.obj(APPROACH_WAY)
    n0, n1 = approach_way["nodes"][SOURCE_SEGMENT_INDEX:SOURCE_SEGMENT_INDEX+2]
    source_nodes = {n0, n1}
    metric_endpoint = PROJECT(*endpoint)
    query = filtered.copy()
    snap_key = "TRIAL_QUERY_POINT"
    exit_key = "TRIAL_EXTERIOR_EXIT"
    query.add_node(snap_key, coord=endpoint, xy=metric_endpoint)
    query.add_node(exit_key, coord=exit_coord, xy=PROJECT(*exit_coord))
    inserted = 0
    for a, b, attrs in filtered.edges(data=True):
        if attrs.get("osm_way_id") != int(APPROACH_WAY.split("/")[1]) or {a[0], b[0]} != source_nodes:
            continue
        geom = LineString([filtered.nodes[a]["xy"], filtered.nodes[b]["xy"]])
        if geom.distance(Point(metric_endpoint)) > EPS_M:
            raise ValueError("Frozen approach point no longer lies on the raw footway segment")
        query.add_edge(a, snap_key, **dict(attrs, route_weight_m=math.dist(filtered.nodes[a]["xy"], metric_endpoint)))
        query.add_edge(snap_key, b, **dict(attrs, route_weight_m=math.dist(metric_endpoint, filtered.nodes[b]["xy"])))
        inserted += 1
    if not inserted:
        raise ValueError("No valid directed raw footway segment for the query point")

    origin = next(k for k, v in base.nodes(data=True)
                  if k[0] == 476682043 and tuple(v["coord"]) == tuple(approach["origin"]))
    baseline = walk(query, origin, snap_key)
    if baseline is None or walk(query, origin, exit_key) is not None:
        raise ValueError("Without-candidate query is inconsistent with the frozen gap")
    baseline_m = sum(r["route_weight_m"] for r in baseline)
    frozen_routes = read(original / "data/native_prefix_diagnostic.geojson")
    archived = next(f for f in frozen_routes["features"]
                    if f["properties"]["route_id"] == approach["route_id"] and f["properties"]["kind"] == NATIVE)
    archived_coords = archived["geometry"]["coordinates"]
    coords = [list(baseline[0]["a"])] + [list(row["b"]) for row in baseline]
    if coords != archived_coords or abs(baseline_m - approach["length_m"]) > EPS_M:
        raise ValueError("The native approach differs from the frozen obstacle-filtered route")
    query.add_edge(snap_key, exit_key, kind="HYPOTHESIS", edge_id="NORTH_GAP_TRIAL_EDGE", route_weight_m=gap_m)
    hypothetical = walk(query, origin, exit_key)
    if hypothetical is None or hypothetical[:-1] != baseline or tuple(hypothetical[-1]["b"]) != exit_coord:
        raise ValueError("Hypothesis query did not use only the unchanged approach plus the one candidate")
    if protected_before != {path: sha(original / path) for path in input_paths}:
        raise ValueError("Sealed source or referenced artifacts changed")

    summary = {
        "status": "HYPOTHESIS_ONLY",
        "entrance_id": DOOR, "entrance_role": exit_tags["entrance"], "inbound_eligibility": "NOT_ELIGIBLE_EXIT",
        "entrance_coordinate": exit_coord, "approach_coordinate": endpoint, "crs": "EPSG:32651",
        "approach_way_id": APPROACH_WAY, "source_segment_index": SOURCE_SEGMENT_INDEX,
        "approach_way_tags": approach_way["tags"], "pedestrian_area_id": AREA,
        "site_area_id": SITE, "site_tags": source.obj(SITE)["tags"], "site_cover_m": park.intersection(line).length,
        "gap_m": gap_m, "baseline_approach_m": baseline_m, "walkable_covered_m": walkable_m,
        "hypothetical_total_m": sum(r["route_weight_m"] for r in hypothetical),
        "level_status": "UNKNOWN_NO_CONTINUOUS_GRADE_EVIDENCE", "obstacle_status": "NO_MAPPED_CONFLICT_ON_CANDIDATE",
        "intersecting_source_obstacles": overlap_records, "layer_or_access_intersections": grade,
        "grade_tags_on_continuous_segment": grade_fields, "unlocated_obstacle_ids_in_clip": unlocated,
        "without": {"status": "APPROACH_WITH_GAP", "routed_end": endpoint, "distance_to_original_exit_m": gap_m},
        "with": {"status": "HYPOTHETICAL_EXTERIOR_REACH", "routed_end": exit_coord, "distance_to_original_exit_m": 0.0,
                 "requires_assumption": "CONTINUOUS_SAME_LEVEL_OUTDOOR_WALKING_SURFACE_AND_ACCESS"},
        "protected_source_sha256": protected_before, "external_requests": 0, "field_checks": 0,
    }
    def feature(role, kind, coordinates, **props):
        return {
            "type": "Feature", "geometry": {"type": kind, "coordinates": coordinates},
            "properties": {"role": role, **props},
        }
    geo = {"type": "FeatureCollection", "features": [
        feature("native_approach", "LineString", coords, length_m=baseline_m, source_edges=archived["properties"]["source_edges"]),
        feature("candidate", "LineString", [endpoint, exit_coord], status="HYPOTHESIS_ONLY", length_m=gap_m,
                routable_in_frozen_graph=False, routable_in_hypothesis_query=True),
        feature("approach_point", "Point", endpoint, source=APPROACH_WAY),
        feature("exit", "Point", exit_coord, source=DOOR, entrance="exit", inbound_eligibility="NOT_ELIGIBLE_EXIT"),
    ]}
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("trial.json", summary), ("trial.geojson", geo)):
        with (out / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({k: summary[k] for k in ("gap_m", "site_cover_m", "walkable_covered_m", "baseline_approach_m",
                                            "hypothetical_total_m", "level_status", "obstacle_status")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=ORIGINAL)
    parser.add_argument("--output-root", type=Path, default=ROOT / "public")
    args = parser.parse_args()
    if args.output_root.resolve().is_relative_to(args.input_root.resolve()):
        raise ValueError("Output must be outside the sealed R4-REV1 directory")
    run(args.input_root.resolve(), args.output_root.resolve())
