"""One-site registered-exit frontage experiment using frozen OSM inputs."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import networkx as nx
from pyproj import Geod, Transformer
from shapely import get_parts
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
INVERSE = Transformer.from_crs(32651, 4326, always_xy=True).transform
GEOD = Geod(ellps="WGS84")
EPS = 0.000001
HYP = "HYPOTHETICAL_NOT_VERIFIED"
PARK = "DERIVED_FROM_MAPPED_PARK_AREA"
NATIVE_WALK = "NATIVE_MAPPED_WALKWAY"
NO_CONFLICT = "NO_MAPPED_CONFLICT"
UNKNOWN_GRADE = "UNKNOWN_NO_CONTINUOUS_LEVEL_HEIGHT_EVIDENCE"
REJECTED = "REJECTED_OBSTACLE_OR_LEVEL_CONFLICT"
GRADE_KEYS = {"layer", "level", "repeat_on", "bridge", "tunnel", "indoor", "ele", "height",
              "incline", "ramp", "covered", "step_count"}
TAG_KEYS = GRADE_KEYS | {"access", "foot", "surface", "highway", "area", "area:highway",
                         "leisure", "landuse", "barrier", "entrance", "name"}
WALK_HIGHWAY = {"footway", "pedestrian", "path", "steps", "corridor"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def tags_of(source, native_id):
    kind, number = native_id.split("/", 1)
    return getattr(source, {"node": "nodes", "way": "ways", "relation": "relations"}[kind])[int(number)].get("tags", {})


def relevant_tags(tags):
    return {k: tags[k] for k in sorted(TAG_KEYS & tags.keys())}


def metric_line(coords):
    return LineString([PROJECT(*c) for c in coords])


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def planar_obstacle_hits(line, obstacles, building_id, target):
    """Record all exact contacts, allowing only the original exit to touch its own footprint."""
    contacts = []
    for row in obstacles:
        inter = row["geometry"].intersection(line)
        if inter.is_empty:
            continue
        terminal = (row["id"] == building_id and inter.geom_type == "Point"
                    and inter.distance(target) <= EPS and line.boundary.distance(target) <= EPS)
        contacts.append({"source_id": row["id"], "source_kind": row["kind"], "contact_type": inter.geom_type,
                         "intersection_m": inter.length,
                         "status": "ORIGINAL_EXIT_BOUNDARY_TOUCH_ONLY" if terminal else REJECTED})
    return contacts


def has_level_conflict(tags):
    return (any(tags.get(k) not in (None, "0", 0) for k in ("layer", "level"))
            or any(tags.get(k) not in (None, "no", "0", 0) for k in ("bridge", "tunnel", "indoor"))
            or tags.get("highway") in {"steps", "elevator"}
            or tags.get("access") in {"no", "private"}
            or tags.get("foot") in {"no", "private"})


def frontage_domain(approach, exit_xy, park, obstacles, building_id, params):
    distance = math.dist(approach, exit_xy)
    if distance <= EPS:
        raise ValueError("Expected a non-zero frontage gap")
    vx, vy = ((exit_xy[i] - approach[i]) / distance for i in (0, 1))
    ox, oy = -vy * params["half_width_m"], vx * params["half_width_m"]
    strip = Polygon([(approach[0]+ox, approach[1]+oy), (exit_xy[0]+ox, exit_xy[1]+oy),
                     (exit_xy[0]-ox, exit_xy[1]-oy), (approach[0]-ox, approach[1]-oy)])
    window = strip.intersection(Point(exit_xy).buffer(params["radius_m"], quad_segs=16))
    relevant = [obj for obj in obstacles if obj["geometry"].distance(window) <= params["obstacle_clearance_m"] + EPS]
    exclusions = [obj["geometry"] if obj["id"] == building_id else
                  obj["geometry"].buffer(params["obstacle_clearance_m"], quad_segs=8)
                  for obj in relevant]
    return window, park.intersection(window).difference(unary_union(exclusions)), relevant


def visibility_route(domain, start, end, allowed):
    """Shortest path on visible polygon ring vertices plus the exact query endpoints."""
    padded = domain.buffer(EPS)
    if not padded.covers(Point(start)) or not padded.covers(Point(end)):
        return None, 0, 0
    vertices = {start, end}
    for part in get_parts(domain):
        if part.geom_type == "Polygon":
            for ring in (part.exterior, *part.interiors):
                vertices.update(map(tuple, ring.coords))
    nodes = sorted(vertices)
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    for index, a in enumerate(nodes):
        for b in nodes[index+1:]:
            segment = LineString([a, b])
            if padded.covers(segment) and allowed(segment):
                graph.add_edge(a, b, weight=segment.length)
    try:
        path = nx.shortest_path(graph, start, end, weight="weight")
    except nx.NetworkXNoPath:
        path = None
    return path, len(nodes), graph.number_of_edges()


def level_records(source, connector, fixed_ids):
    rows = []
    for kind, index in (("node", source.nodes), ("way", source.ways), ("relation", source.relations)):
        for number, obj in index.items():
            native_id = f"{kind}/{number}"
            tags = obj.get("tags", {})
            if native_id not in fixed_ids and not (GRADE_KEYS & tags.keys() or
                    tags.get("highway") in {"steps", "elevator"} or
                    tags.get("access") in {"no", "private"} or tags.get("foot") in {"no", "private"}):
                continue
            if kind == "node":
                geom = Point(source.projected[number])
            elif kind == "relation" or tags.get("area") == "yes" or (
                    kind == "way" and len(obj["nodes"]) >= 4 and obj["nodes"][0] == obj["nodes"][-1]
                    and any(k in tags for k in ("leisure", "building", "landuse", "natural"))):
                geom = source.area(native_id)
            else:
                pts = source.known_coords(obj)
                geom = LineString(pts) if len(pts) >= 2 and len(pts) == len(obj["nodes"]) else None
            if geom is None:
                pts = source.known_coords(obj) if kind != "node" else []
                if len(pts) >= 2 and LineString(pts).envelope.intersects(connector):
                    rows.append({"source_id": native_id, "tags": relevant_tags(tags),
                                 "relation": "UNRESOLVED_NEARBY_GEOMETRY", "distance_m": None,
                                 "intersection_m": None, "explicit_conflict": True,
                                 "level_status": "UNRESOLVED_SOURCE_GEOMETRY"})
                continue
            distance = geom.distance(connector)
            if distance > 12 and native_id not in fixed_ids:
                continue
            crosses = distance <= EPS
            inter = geom.intersection(connector)
            evidence = "EXPLICIT_TAGS" if GRADE_KEYS & tags.keys() or tags.get("highway") in {"steps", "elevator"} else UNKNOWN_GRADE
            rows.append({"source_id": native_id, "tags": relevant_tags(tags), "relation":
                         "INTERSECTS_OR_TOUCHES" if crosses else "NEARBY_ONLY",
                         "distance_m": distance, "intersection_m": inter.length,
                         "explicit_conflict": crosses and has_level_conflict(tags),
                         "level_status": evidence})
    return sorted(rows, key=lambda x: (x["relation"], x["distance_m"] or 0, x["source_id"]))


def csv_write(path, rows):
    cols = list(rows[0])
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                          if isinstance(v, (list, dict, tuple)) else v for k, v in row.items()} for row in rows)


def json_write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def run(input_root, prior_root, output, config_path):
    config = load(config_path)
    ids = config["source_ids"]
    original = input_root / "frozen_r4"
    source_path = original / "data/source/sh-huangpu-01.osm.json"
    diagnostic_path = input_root / "data/native_prefix_diagnostic.json"
    original_geojson = input_root / "data/native_prefix_diagnostic.geojson"
    baseline_paths = [source_path, diagnostic_path, original_geojson,
                      original / "src/frozen_r1/local_route.py", prior_root / "trial.json", prior_root / "trial.geojson"]
    initial_shas = [sha(path) for path in baseline_paths]
    sys.path.insert(0, str(input_root))
    from src.audit_native_prefix import native_view
    from src.native_adapter import Source, grounded_lines, load_frozen_engine
    from src.route_measure import closest_reachable, key, obstacle_index, prepare_weights, walk

    source = Source(load(source_path))
    exit_id, building_id, park_id = ids["exit"], ids["building"], ids["park"]
    plaza_id, approach_way_id = ids["pedestrian_area"], ids["footway"]
    exit_coord = tuple(source.coord(exit_id))
    exit_tags = tags_of(source, exit_id)
    if exit_tags.get("entrance") != "exit":
        raise ValueError("Expected original registered exit")
    target = Point(PROJECT(*exit_coord))
    park, plaza, building = map(source.area, (park_id, plaza_id, building_id))
    if any(g is None for g in (park, plaza, building)) or building.boundary.distance(target) > EPS:
        raise ValueError("Unresolved park/plaza/building or displaced exit")

    raw = load(source_path)
    engine = load_frozen_engine(original)
    segments, endings, _ = engine._segments(raw)
    base, _ = engine._build_graph(segments, endings, ())
    prepare_weights(base)
    obstacles, unlocated_obstacles = source.obstacles([])
    obstacle_tree = obstacle_index(obstacles)
    filtered, blocked, _ = native_view(base, obstacle_tree)
    origin = key(ids["origin"])
    if origin not in filtered:
        raise ValueError("Frozen origin is not in the source graph")
    origin_reachable = nx.descendants(filtered, origin) | {origin}
    native_exit_present = key(exit_id) in filtered
    if key(exit_id) in origin_reachable:
        raise ValueError("The frozen origin can already reach the native exit node")
    archived = next(row["alternate"] for row in load(diagnostic_path)["records"] if row["subject"] == "NORTH_APPROACH")
    nearest = closest_reachable(filtered, source, origin, exit_coord, plaza_id)
    if nearest is None:
        raise ValueError("No eligible reachable native approach")
    _, approach_coord, raw_edge = nearest
    approach_coord = tuple(approach_coord)
    if f'way/{raw_edge["osm_way_id"]}' != approach_way_id or math.dist(approach_coord, archived["endpoint"]) > 1e-12:
        raise ValueError("Recomputed native approach projection differs from frozen input")
    anchor_xy = PROJECT(*approach_coord)
    target_xy = tuple(target.coords[0])
    connector = LineString([anchor_xy, target_xy])
    way_nodes = source.obj(approach_way_id)["nodes"]
    index = ids["footway_segment_index"]
    raw_segment_order = way_nodes[index:index+2]
    raw_segment_nodes = set(raw_segment_order)
    native_geom = LineString([source.projected[n] for n in raw_segment_order])
    if native_geom.distance(Point(anchor_xy)) > EPS or not math.isclose(native_geom.distance(target), connector.length, abs_tol=EPS):
        raise ValueError("Query endpoint no longer matches frozen native segment projection")

    ground_lines = grounded_lines(source, segments)

    def mapped_coverage(line):
        return unary_union([plaza.intersection(line), *(g.intersection(line) for _, g in ground_lines
                           if g.intersects(line))]).length

    explicit_ground_lines = [(ident, geom) for ident, geom in ground_lines
                             if tags_of(source, ident.rsplit('/', 1)[0]).get('highway') in WALK_HIGHWAY
                             or tags_of(source, ident.rsplit('/', 1)[0]).get('foot') in {'yes', 'designated'}]
    nearest_raw_edge, nearest_raw_geom = min(explicit_ground_lines, key=lambda item: (item[1].distance(target), item[0]))
    positive_walk_m = mapped_coverage(connector)
    explicit_native_nodes = {node for a, b, row in filtered.edges(data=True)
                             if row.get("osm_way_id") is not None
                             and tags_of(source, f'way/{row["osm_way_id"]}').get("highway") in WALK_HIGHWAY
                             and a in origin_reachable and a[1:] == b[1:] == ("0", "0") for node in (a, b)}
    nearest_node = min(explicit_native_nodes, key=lambda k: (math.dist(filtered.nodes[k]["xy"], target_xy), k))
    levels = level_records(source, connector, {exit_id, approach_way_id, park_id, plaza_id, building_id,
                                              *(f"node/{n}" for n in raw_segment_nodes)})
    native_obstacles = planar_obstacle_hits(connector, obstacles, building_id, target)
    n1_conflicts = [x for x in native_obstacles if x["status"] == REJECTED]
    n1_grade_conflicts = [x for x in levels if x["explicit_conflict"]]
    n1_path = [anchor_xy, target_xy] if not n1_conflicts and not n1_grade_conflicts else None

    # A split is added only to the query copy, respecting original edge directions.
    query = filtered.copy()
    snap_key, exit_key = "QUERY_POINT_ON_NATIVE_EDGE", "QUERY_ORIGINAL_EXIT_EXTERIOR"
    query.add_node(snap_key, coord=approach_coord, xy=anchor_xy)
    query.add_node(exit_key, coord=exit_coord, xy=target_xy)
    split_directions = 0
    for a, b, row in filtered.edges(data=True):
        if row.get("osm_way_id") == raw_edge["osm_way_id"] and {a[0], b[0]} == raw_segment_nodes:
            query.add_edge(a, snap_key, **dict(row, route_weight_m=math.dist(filtered.nodes[a]["xy"], anchor_xy)))
            query.add_edge(snap_key, b, **dict(row, route_weight_m=math.dist(anchor_xy, filtered.nodes[b]["xy"])))
            split_directions += 1
    baseline = walk(query, origin, snap_key)
    if not split_directions or baseline is None or walk(query, origin, exit_key) is not None:
        raise ValueError("N0 raw graph/query attachment mismatch")
    prefix_coords = [baseline[0]["a"], *(row["b"] for row in baseline)]
    archived_prefix = next(f["geometry"]["coordinates"] for f in load(original_geojson)["features"]
                           if f["properties"].get("route_id") == archived["route_id"]
                           and f["properties"]["kind"] == "NATIVE_LINEAR")
    if prefix_coords != list(map(tuple, archived_prefix)):
        raise ValueError("N0 native approach differs from frozen reference geometry")
    prior = load(prior_root / "trial.json")
    prior_geo = load(prior_root / "trial.geojson")
    prior_line = next(f["geometry"]["coordinates"] for f in prior_geo["features"]
                      if f["properties"]["role"] == "candidate")
    if list(map(tuple, prior_line)) != [approach_coord, exit_coord] or abs(metric_line(prior_line).length - prior["gap_m"]) > EPS:
        raise ValueError("N1 does not reproduce the prior measured straight hypothesis")
    native_m = metric_line(prefix_coords).length
    native_contacts = {}
    for i, edge in enumerate(baseline, 1):
        line = metric_line([edge['a'], edge['b']])
        contacts = []
        for obstacle_index_value in obstacle_tree[1].query(line, predicate='intersects'):
            obj = obstacles[obstacle_index_value]
            inter = line.intersection(obj['geometry'])
            boundary_only = obj['kind'] in {'AREA', 'BUILDING', 'UNKNOWN'} and line.relate_pattern(obj['geometry'], 'F********')
            contacts.append({'source_id': obj['id'], 'source_kind': obj['kind'], 'contact_type': inter.geom_type,
                             'intersection_m': inter.length, 'status': 'NATIVE_SOURCE_BOUNDARY_CONTACT_ONLY'
                             if boundary_only else 'NATIVE_SOURCE_GATE_CONTACT_OR_RECHECK'})
        native_contacts[i] = sorted(contacts, key=lambda item: item['source_id'])

    def evaluate(params):
        window, domain, nearby = frontage_domain(anchor_xy, target_xy, park, obstacles, building_id, params)

        def segment_allowed(line):
            if any(r["status"] == REJECTED for r in planar_obstacle_hits(line, nearby, building_id, target)):
                return False
            return not any(row["explicit_conflict"] for row in level_records(source, line, set()))

        path, vertices, visible_edges = visibility_route(domain, anchor_xy, target_xy, segment_allowed)
        length = LineString(path).length if path else None
        return (dict(params, status="HYPOTHETICAL_CANDIDATE" if path else "NO_FEASIBLE_CANDIDATE",
                     connector_m=length, length_m=native_m+length if path else None,
                     corridor_area_m2=domain.area, visibility_vertices=vertices, visible_edges=visible_edges,
                     geometry_status=NO_CONFLICT if path else "NO_COVERED_OBSTACLE_FREE_PATH",
                     level_status=UNKNOWN_GRADE, evidence_status=HYP if path else "UNKNOWN",
                     source_scope_grade=PARK, field_status="NOT_VERIFIED"), path, window, domain, nearby)

    n2_info, n2_path, window, domain, nearby = evaluate(config["main"])
    sensitivity = [n2_info]
    if n2_path:
        sensitivity.extend(evaluate(params)[0] for params in config["sensitivity"])

    def routed(path):
        if not path:
            return None, None
        model = query.copy()
        connector_coords = [approach_coord, *(INVERSE(*x) for x in path[1:-1]), exit_coord]
        nodes = [snap_key]
        for i, xy in enumerate(path[1:-1], 1):
            name = f"CANDIDATE_VERTEX/{i}"
            model.add_node(name, coord=connector_coords[i], xy=xy)
            nodes.append(name)
        nodes.append(exit_key)
        for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
            model.add_edge(a, b, kind=HYP, edge_id=f"HYPOTHESIS/{i+1}", route_weight_m=math.dist(path[i], path[i+1]))
        result = walk(model, origin, exit_key)
        if result is None or result[:len(baseline)] != baseline or result[-1]["b"] != exit_coord:
            raise ValueError("Hypothesis query did not use unchanged N0 and exact exit")
        return [result[0]["a"], *(r["b"] for r in result)], connector_coords

    route_geo, ledger, obstacle_csv, level_csv = [], [], [], []
    variants = {}
    for variant, candidate in (("N0", None), ("N1", n1_path), ("N2", n2_path)):
        combined, gap_coords = routed(candidate)
        coords = combined or prefix_coords
        length = metric_line(coords).length
        modeled = bool(combined)
        added_m = metric_line(gap_coords).length if gap_coords else 0.0
        data = {"variant": variant, "status": "HYPOTHETICAL_EXTERIOR_REACH" if modeled else (
                "APPROACH_WITH_GAP" if variant == "N0" else "REJECTED_OR_NO_CANDIDATE"),
                "length_m": length, "geodesic_length_m": GEOD.line_length(*zip(*coords)),
                "native_m": native_m, "connector_m": added_m,
                "derived_m": added_m if variant == "N2" else 0.0,
                "hypothesis_m": added_m, "residual_m": math.dist(PROJECT(*coords[-1]), target_xy),
                "end_wgs84": coords[-1], "entrance_id": exit_id, "entrance_role": "exit",
                "inbound_eligibility": "NOT_ELIGIBLE_EXIT", "field_status": "NOT_VERIFIED",
                "connector_evidence": HYP if modeled else "UNKNOWN",
                "source_scope_grade": PARK if variant == "N2" and modeled else HYP if modeled else "UNKNOWN",
                "geometry_status": NO_CONFLICT if modeled or variant == "N0" else "REJECTED_OR_NO_CANDIDATE",
                "level_status": UNKNOWN_GRADE,
                "topology_status": "CONTINUOUS_IN_HYPOTHESIS_QUERY_ONLY" if modeled else "NO_NATIVE_EXIT_CONNECTION",
                "failure_reason": None if modeled else "NO_NATIVE_CONNECTOR" if variant == "N0" else
                                  "RECORDED_OBSTACLE_OR_GRADE_CONFLICT" if variant == "N1" else "NO_PATH_IN_ALLOWED_CORRIDOR"}
        variants[variant] = data
        route_geo.extend([
            feature(mapping(LineString(coords)), variant=variant, role="route", status=data["status"], length_m=length),
            feature(mapping(LineString(prefix_coords)), variant=variant, role="native_approach",
                    evidence_status="FROZEN_NATIVE_GRAPH", length_m=native_m),
            feature(mapping(Point(approach_coord)), variant=variant, role="approach_point", source_id=approach_way_id),
            feature(mapping(Point(exit_coord)), variant=variant, role="exit", source_id=exit_id, tags={"entrance": "exit"}),
            feature(mapping(Point(coords[-1])), variant=variant, role="route_end", status=data["status"]),
        ])
        if gap_coords:
            route_geo.append(feature(mapping(LineString(gap_coords)), variant=variant, role="connector", evidence_status=HYP,
                                     source_scope_grade=data["source_scope_grade"], length_m=added_m,
                                     routable_in_frozen_graph=False))
        for i, row in enumerate(baseline, 1):
            way = f'way/{row["osm_way_id"]}' if row.get("osm_way_id") is not None else "NO_NATIVE_WAY_ID"
            way_tags = tags_of(source, way) if way.startswith("way/") else {}
            evidence = NATIVE_WALK if way_tags.get("highway") in WALK_HIGHWAY else "UNKNOWN"
            segment_m = metric_line([row['a'], row['b']]).length
            contacts = native_contacts[i]
            for contact in contacts:
                obstacle_csv.append(dict(variant=variant, segment=i, section='FROZEN_NATIVE_APPROACH',
                                         segment_m=segment_m, **contact))
            ledger.append(dict(variant=variant, section="FROZEN_NATIVE_APPROACH", segment=i, source_ids=[way],
                               length_m=segment_m, evidence_status=evidence,
                               level_status="FROZEN_GRAPH_LAYER_KEYS", obstacle_status='NATIVE_MAPPED_CONTACT_RECORDED' if contacts else NO_CONFLICT,
                               topology_status="ORIGINAL_GRAPH_EDGE_OR_QUERY_SPLIT",
                               walkability_status="POSITIVE_WALKABILITY_EVIDENCE" if evidence == NATIVE_WALK else "SOURCE_PROFILE_ASSUMPTION",
                               start_wgs84=row["a"], end_wgs84=row["b"], field_status="NOT_VERIFIED",
                               source_segment_index=row.get("segment_index"), source_tags=relevant_tags(way_tags),
                               source_scope_grade=evidence, native_profile_evidence=row.get('evidence'),
                               mapped_pedestrian_coverage_m=segment_m if evidence == NATIVE_WALK else None,
                               mapped_park_coverage_m=None, obstacle_source_ids=[x['source_id'] for x in contacts]))
        target_pairs = list(zip(gap_coords, gap_coords[1:])) if gap_coords else [(approach_coord, exit_coord)]
        for i, (a, b) in enumerate(target_pairs, 1):
            line = metric_line([a, b])
            for row in planar_obstacle_hits(line, obstacles, building_id, target) or [{
                    "source_id": "", "source_kind": "", "contact_type": "", "intersection_m": 0.0, "status": NO_CONFLICT}]:
                obstacle_csv.append(dict(variant=variant, segment=i, section="CANDIDATE" if modeled else "GAP_DIAGNOSTIC",
                                         segment_m=line.length, **row))
            for row in level_records(source, line, {exit_id, approach_way_id, park_id, plaza_id, building_id}):
                level_csv.append(dict(variant=variant, segment=i, section="CANDIDATE" if modeled else "GAP_DIAGNOSTIC", **row))
            contacts = planar_obstacle_hits(line, obstacles, building_id, target)
            covered_m = mapped_coverage(line)
            coverage_status = ('POSITIVE_WALKABILITY_EVIDENCE' if covered_m >= line.length - EPS else
                               'PARTIAL_POSITIVE_COVERAGE' if covered_m > EPS else 'NO_POSITIVE_COVERAGE')
            ledger.append(dict(variant=variant, section="HYPOTHETICAL_CONNECTOR" if modeled else "GAP_DIAGNOSTIC",
                               segment=i, source_ids=[approach_way_id, exit_id, plaza_id] + ([park_id] if variant == "N2" else []),
                               length_m=line.length, evidence_status=HYP if modeled else "UNKNOWN",
                               level_status=UNKNOWN_GRADE, obstacle_status=data["geometry_status"],
                               topology_status=data["topology_status"], walkability_status=coverage_status,
                               start_wgs84=a, end_wgs84=b, field_status="NOT_VERIFIED",
                               source_segment_index=None, source_tags={}, source_scope_grade=data['source_scope_grade'],
                               native_profile_evidence=None, mapped_pedestrian_coverage_m=covered_m,
                               mapped_park_coverage_m=park.intersection(line).length,
                               obstacle_source_ids=[x['source_id'] for x in contacts]))

    constraints = [
        feature(mapping(transform(INVERSE, park)), role="park", source_id=park_id, tags=relevant_tags(tags_of(source, park_id))),
        feature(mapping(transform(INVERSE, plaza)), role="pedestrian_area", source_id=plaza_id, tags=relevant_tags(tags_of(source, plaza_id))),
        feature(mapping(transform(INVERSE, building)), role="building", source_id=building_id, tags=relevant_tags(tags_of(source, building_id))),
        feature(mapping(transform(INVERSE, native_geom)), role="footway", source_id=approach_way_id, tags=relevant_tags(tags_of(source, approach_way_id))),
        feature(mapping(LineString([approach_coord, exit_coord])), role="gap", source_id="RECOMPUTED_GAP",
                evidence_status="UNKNOWN", routable=False),
        feature(mapping(transform(INVERSE, window)), role="N2_search_strip", source_id="LOCKED_FRONTAGE_WINDOW", tags={}),
        feature(mapping(transform(INVERSE, domain)), role="N2_corridor", source_id=park_id, tags={"leisure": "park"},
                evidence_status=HYP, source_scope_grade=PARK, area_m2=domain.area),
    ]
    for item in obstacles:
        if item["id"] != building_id and item["geometry"].distance(connector) <= 18:
            constraints.append(feature(mapping(transform(INVERSE, item["geometry"])), role="obstacle", source_id=item["id"],
                                       kind=item["kind"], tags=relevant_tags(item.get("tags", {}))))
    same = bool(n1_path and n2_path and LineString(n1_path).equals_exact(LineString(n2_path), EPS))
    result = {"scene_id": "sh-huangpu-01", "crs": "EPSG:32651", "wgs84_axis_order": "lon,lat",
              "status": "COMPLETED_HYPOTHESIS_ONLY", "config_sha256": sha(config_path),
              "source_geometry": {"exit_id": exit_id, "exit_wgs84": exit_coord, "exit_tags": exit_tags,
                                  "approach_wgs84": approach_coord, "footway_id": approach_way_id,
                                  "footway_segment_index": index, "footway_native_nodes": raw_segment_order,
                                  "clip_wide_nearest_explicit_walk_edge": nearest_raw_edge,
                                  "clip_wide_nearest_explicit_walk_edge_distance_m": nearest_raw_geom.distance(target),
                                  "exit_native_graph_node_present": native_exit_present,
                                  "exit_native_graph_node_reachable": False,
                                  "nearest_reachable_walk_node_id": f"node/{nearest_node[0]}",
                                  "nearest_reachable_walk_node_distance_m": math.dist(filtered.nodes[nearest_node]["xy"], target_xy),
                                  "pedestrian_area_id": plaza_id, "park_id": park_id, "building_id": building_id,
                                  "exit_to_pedestrian_boundary_m": plaza.boundary.distance(target),
                                  "exit_to_nearest_eligible_edge_m": native_geom.distance(target),
                                  "n1_line_m": connector.length, "prior_line_recomputed_m": metric_line(prior_line).length,
                                  "park_contains_entire_segment": park.buffer(EPS).covers(connector),
                                  "park_coverage_m": park.intersection(connector).length,
                                  "explicit_walkway_coverage_m": positive_walk_m,
                                  "building_interior_intersection_m": connector.intersection(building).difference(building.boundary).length,
                                  "pedestrian_area_holes": sum(len(part.interiors) for part in get_parts(plaza)),
                                  "pedestrian_area_hole_intersection_m": sum(Polygon(ring).intersection(connector).length
                                      for part in get_parts(plaza) for ring in part.interiors),
                                  "native_query_split_directions": split_directions,
                                  "frozen_obstacle_filtered_graph_edges": filtered.number_of_edges(),
                                  "frozen_graph_removed_obstacle_arcs": len(blocked)},
              "evidence_summary": {"geometry": NO_CONFLICT if not n1_conflicts else REJECTED,
                                   "level_status": UNKNOWN_GRADE, "field_status": "NOT_VERIFIED",
                                   "n1_source_obstacle_contacts": native_obstacles,
                                   "explicit_level_or_access_conflicts": n1_grade_conflicts,
                                   "unlocated_obstacle_count_in_clip": len(unlocated_obstacles),
                                   "native_prefix_evidence_counts": dict(Counter(r["evidence_status"] for r in ledger
                                      if r["variant"] == "N0" and r["section"] == "FROZEN_NATIVE_APPROACH")),
                                   "native_boundary_contact_segments": sum(bool(rows) for rows in native_contacts.values()),
                                   "positive_connector_walkability_evidence": positive_walk_m >= connector.length - EPS},
              "variants": variants, "sensitivity": sensitivity,
              "comparison": {"same_connector_geometry": same,
                             "length_difference_n2_minus_n1_m": variants["N2"]["connector_m"] - variants["N1"]["connector_m"]
                                                                 if n1_path and n2_path else None,
                             "n2_adds_explicit_spatial_constraints": True,
                             "n2_upgrades_walkability_evidence": False,
                             "admitted_as_verified_walkway": False},
              "external_requests": 0, "field_checks": 0}
    if initial_shas != [sha(path) for path in baseline_paths]:
        raise ValueError("A frozen source changed")
    result["frozen_source_sha256"] = dict(zip((p.name for p in baseline_paths), initial_shas))
    for folder in ("data", "runs"):
        (output / folder).mkdir(parents=True, exist_ok=True)
    json_write(output / "runs/experiment.json", result)
    json_write(output / "data/route_variants.geojson", fc(route_geo))
    json_write(output / "data/constraints.geojson", fc(constraints))
    csv_write(output / "data/segment_evidence.csv", ledger)
    csv_write(output / "data/obstacle_intersections.csv", obstacle_csv)
    csv_write(output / "data/level_evidence.csv", level_csv)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=ROOT / "inputs/source")
    parser.add_argument("--prior-root", type=Path, default=ROOT / "inputs/prior_trial")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=ROOT / "config/frontage.json")
    args = parser.parse_args()
    output = args.output_root.resolve()
    if output.is_relative_to(args.input_root.resolve()) or output.is_relative_to(args.prior_root.resolve()):
        raise ValueError("Output must remain outside frozen source paths")
    result = run(args.input_root.resolve(), args.prior_root.resolve(), output, args.config.resolve())
    print(json.dumps({"status": result["status"], "variants": result["variants"], "comparison": result["comparison"]}))


if __name__ == "__main__":
    main()
