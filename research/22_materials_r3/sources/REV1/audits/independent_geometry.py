"""Independent raw OSM, domain, route, and archive checks for R4-REV1."""
import argparse
from collections import Counter, defaultdict
from hashlib import file_digest
from itertools import combinations, pairwise, zip_longest
import json
import math
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from geographiclib.geodesic import Geodesic
import networkx as nx
import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, polygonize, unary_union
from shapely.strtree import STRtree


TO_METRES = Transformer.from_crs(4326, 32651, always_xy=True).transform
GEOD = Geodesic.WGS84
EPS = .001
MARGIN = .25
WIDTH = 3.
MAIN = "R1_AREA_EDGE_MAIN"
NATIVE = "NATIVE_LINEAR"
AREA_EDGE = "DERIVED_FROM_TAGGED_PEDESTRIAN_AREA"
TERMINAL = "DERIVED_TERMINAL_CONNECTOR"
GAP = "GAP_DIAGNOSTIC_NOT_ROUTABLE"
MUSEUM = "sh-huangpu-01"
SOUTH, NORTH = "relation/2385771", "relation/2153738"
SOUTH_DOOR, NORTH_DOOR = "node/6897141353", "node/6897145227"
TARGET_BUILDING = "way/161090899"
CONTACTS = {"node/1890745480": "way/761403177", "node/1890935415": "way/178737608",
            "node/1890935454": "way/178737605"}
FOOT_CLASSES = {"footway", "pedestrian", "path", "steps"}
SHARED_CLASSES = {"living_street", "residential", "unclassified", "service"}
ROAD_CLASSES = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
CONTEXT_CLASSES = {"track", "cycleway", "bridleway", "corridor"}
OPEN = {"yes", "designated", "permissive", "official"}
RESTRICTED = {"no", "private", "customers", "destination", "delivery", "permit",
              "agricultural", "forestry", "restricted"}
CONDITIONAL = {"access:conditional", "foot:conditional", "oneway:foot:conditional",
               "foot:forward:conditional", "foot:backward:conditional"}
BARRIERS = {"wall", "fence", "hedge", "retaining_wall", "chain", "city_wall",
            "jersey_barrier", "gate", "lift_gate", "swing_gate", "turnstile", "kissing_gate"}
GATES = {"gate", "lift_gate", "swing_gate", "turnstile", "kissing_gate"}
BASE_ENDPOINT_ALLOWED = {"no", "bollard", "block", "cycle_barrier", "cattle_grid", "kerb", "entrance"}


def check(predicate, label):
    if not predicate:
        raise AssertionError(label)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def native_number(name):
    return int(name.split("/")[1])


def geod_distance(a, b):
    return GEOD.Inverse(a[1], a[0], b[1], b[0])["s12"]


def ground(tags):
    return (tags.get("layer", "0") in ("", "0") and tags.get("level", "0") in ("", "0")
            and all(tags.get(k) in (None, "", "no") for k in ("bridge", "tunnel", "indoor", "ford", "covered")))


def node_allowed(tags):
    foot = tags.get("foot")
    return (tags.get("locked") != "yes" and not CONDITIONAL.intersection(tags)
            and (foot in OPEN or (foot is None and tags.get("access") not in RESTRICTED
                                  and tags.get("barrier", "no") in BASE_ENDPOINT_ALLOWED)))


def native_evidence(tags):
    highway, foot = tags.get("highway"), tags.get("foot")
    if (tags.get("area") == "yes" or tags.get("indoor") not in (None, "no")
            or tags.get("ford") not in (None, "no") or CONDITIONAL.intersection(tags)
            or (foot is not None and foot not in OPEN) or (foot is None and tags.get("access") in RESTRICTED)):
        return None
    if highway in FOOT_CLASSES:
        return "EXPLICIT_WALK"
    if highway not in SHARED_CLASSES | ROAD_CLASSES | CONTEXT_CLASSES:
        return None
    if foot in OPEN:
        return "EXPLICIT_WALK"
    if highway in SHARED_CLASSES | ROAD_CLASSES and any(
            tags.get(key) in {"yes", "left", "right", "both"} for key in
            ("sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both")):
        return "AXIS_ASSUMPTION"
    if highway in SHARED_CLASSES and tags.get("sidewalk") not in {"no", "separate"}:
        return "AXIS_ASSUMPTION"
    return None


def directions(tags):
    choice = tags.get("oneway:foot")
    if choice is None and tags.get("highway") in {"footway", "path", "steps"}:
        choice = tags.get("oneway")
    if choice not in {None, "no", "false", "0", "yes", "true", "1", "-1", "reverse"}:
        return ()
    forward = choice not in {"-1", "reverse"} and tags.get("foot:forward", "yes") in OPEN
    backward = choice not in {"yes", "true", "1"} and tags.get("foot:backward", "yes") in OPEN
    return tuple(i for i, ok in enumerate((forward, backward)) if ok)


class RawScene:
    def __init__(self, path):
        self.path = path
        self.sha = digest(path)
        payload = read(path)
        self.bounds = payload["bounds_wsen"]
        self.objects = {kind: {} for kind in ("node", "way", "relation")}
        for row in payload["elements"]:
            self.objects[row["type"]][row["id"]] = row
        self.wgs = {n: (v["lon"], v["lat"]) for n, v in self.objects["node"].items()}
        self.xy = {n: TO_METRES(*p) for n, p in self.wgs.items()}
        self._areas = {}
        self.native, self.native_segments = self.make_native()

    def get(self, name):
        kind, i = name.split("/")
        return self.objects[kind][int(i)]

    def points(self, way):
        ids = way.get("nodes", [])
        return [self.xy[i] for i in ids if i in self.xy]

    def raw_line(self, way):
        points = self.points(way)
        if len(points) >= 2 and len(points) == len(way["nodes"]):
            return LineString(points)
        return None

    def members(self, name):
        item = self.get(name)
        if item["type"] == "way":
            return [(name, "outer")]
        return [(f"way/{part['ref']}", part["role"] or "outer") for part in item["members"]
                if part["type"] == "way"]

    def outer_nodes(self, name):
        return {i for way, role in self.members(name) if role == "outer" for i in self.get(way)["nodes"]}

    def area(self, name):
        if name in self._areas:
            return self._areas[name]
        item = self.get(name)
        groups = defaultdict(list)
        members = self.members(name)
        if item["type"] == "relation" and len(members) != len(item["members"]):
            return None
        for way, role in members:
            try:
                line = self.raw_line(self.get(way))
            except KeyError:
                return None
            if line is None or role not in {"inner", "outer"}:
                return None
            groups[role].append(line)
        outer, inner = (unary_union(list(polygonize(groups[k]))) for k in ("outer", "inner"))
        if outer.is_empty or (groups["inner"] and (inner.is_empty or not outer.covers(inner))):
            return None
        if any(not shape.boundary.buffer(1e-7).covers(line)
               for name, shape in (("outer", outer), ("inner", inner)) for line in groups[name]):
            return None
        polygon = outer.difference(inner)
        value = polygon if polygon.is_valid and polygon.geom_type in {"Polygon", "MultiPolygon"} else None
        self._areas[f"{item['type']}/{item['id']}"] = value
        return value

    def make_native(self):
        graph = nx.MultiDiGraph()
        segments = {}
        endings = defaultdict(set)
        west, south, east, north = self.bounds
        for way_id, way in self.objects["way"].items():
            tags = way.get("tags", {})
            evidence, orient = native_evidence(tags), directions(tags)
            if evidence is None or not orient:
                continue
            default_layer = "1" if tags.get("bridge") not in (None, "no") else "-1" if tags.get("tunnel") not in (None, "no") else "0"
            layer, level = tags.get("layer", default_layer), tags.get("level", "0")
            nodes = way["nodes"]
            for i, ids in enumerate(pairwise(nodes)):
                if ids[0] == ids[1] or any(n not in self.wgs for n in ids):
                    continue
                coords = [self.wgs[n] for n in ids]
                if coords[0] == coords[1] or not all(west <= x <= east and south <= y <= north for x, y in coords):
                    continue
                if any(not node_allowed(self.objects["node"][n].get("tags", {})) for n in ids):
                    continue
                keys = [(n, layer, level) for n in ids]
                for d in orient:
                    u, v = keys[d], keys[1-d]
                    graph.add_edge(u, v, way=way_id, segment=i, metres=math.dist(self.xy[u[0]], self.xy[v[0]]))
                segments[(way_id, i)] = (keys, orient, evidence)
                if i == 0:
                    endings[ids[0]].add(keys[0])
                if i == len(nodes)-2:
                    endings[ids[1]].add(keys[1])
        for keys in endings.values():
            for a, b in combinations(keys, 2):
                if a[2] == b[2]:
                    graph.add_edge(a, b, metres=0.)
                    graph.add_edge(b, a, metres=0.)
        return graph, segments

    def obstacles(self):
        if hasattr(self, "_obstacles"):
            return self._obstacles
        areas, barriers = [], []
        for kind in ("way", "relation"):
            for i, item in self.objects[kind].items():
                name = f"{kind}/{i}"
                tags = item.get("tags", {})
                cat = obstacle_kind(tags, kind)
                if cat is None:
                    continue
                if cat == "BARRIER" and (line := self.raw_line(item)) is not None:
                    open_gates = {n: Point(self.xy[n]) for n in item["nodes"]
                                  if allowed_gate(self.objects["node"][n].get("tags", {}))}
                    barriers.append((name, line, open_gates))
                    continue
                geom = self.area(name) if cat != "BARRIER" else None
                if geom is None:
                    points = [p for way, _ in self.members(name) if native_number(way) in self.objects["way"]
                              for p in self.points(self.get(way))]
                    if not points:
                        continue
                    xs, ys = zip(*points)
                    geom, cat = box(min(xs), min(ys), max(xs), max(ys)).buffer(.01), "UNKNOWN"
                areas.append((name, geom, cat))
        for i, obj in self.objects["node"].items():
            tags = obj.get("tags", {})
            if tags.get("barrier") in BARRIERS and not allowed_gate(tags):
                barriers.append((f"node/{i}", Point(self.xy[i]), {}))
        self._obstacles = areas, barriers
        return self._obstacles


def allowed_gate(tags):
    return (tags.get("barrier") in GATES and ground(tags) and tags.get("locked") != "yes"
            and not any(key in tags for key in ("access:conditional", "foot:conditional", "oneway:conditional"))
            and all(tags.get(key) not in RESTRICTED for key in ("access", "foot"))
            and any(tags.get(key) in OPEN for key in ("access", "foot")))


def obstacle_kind(tags, kind):
    if any(tags.get(key) not in (None, "no") for key in ("building", "building:part")):
        return "BUILDING"
    surface = (tags.get("natural") in {"water", "wetland"} or tags.get("water") or tags.get("waterway") == "riverbank"
               or tags.get("landuse") in {"reservoir", "basin", "grass", "flowerbed", "flower_bed"}
               or tags.get("leisure") == "flowerbed" or tags.get("landcover") in {"grass", "flowerbed"}
               or tags.get("barrier") in {"flower_bed", "planter"} or tags.get("garden:type") == "flower_bed")
    restricted_area = ((tags.get("area") == "yes" or tags.get("type") == "multipolygon")
                       and (any(tags.get(k) in RESTRICTED for k in ("access", "foot"))
                            or any(key in tags for key in ("access:conditional", "foot:conditional", "oneway:conditional"))))
    if surface or restricted_area:
        return "AREA"
    return "BARRIER" if kind == "way" and tags.get("barrier") in BARRIERS else None


def json_feature_stream(path):
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8") as f:
        text = f.read(65536)
        pos = text.index('"features":[') + len('"features":[')
        while True:
            text = text[pos:]
            while True:
                text = text.lstrip(" \t\r\n,")
                if text.startswith("]"):
                    return
                try:
                    value, pos = decoder.raw_decode(text)
                    break
                except json.JSONDecodeError:
                    part = f.read(65536)
                    if not part:
                        raise
                    text += part
            yield value


def band_sources(scene, area_id, width=WIDTH):
    area = scene.area(area_id)
    tags = scene.get(area_id)["tags"]
    check(area is not None and (
        tags.get("area") == "yes" and tags.get("highway") in {"footway", "pedestrian", "path"}
        or tags.get("area:highway") in {"footway", "pedestrian", "path"}), f"{area_id}: no frozen tagged area")
    check(ground(tags) and not CONDITIONAL.intersection(tags)
          and not any(tags.get(key) in RESTRICTED for key in ("access", "foot")), f"{area_id}: source restrictions")
    polys = [area] if area.geom_type == "Polygon" else list(area.geoms)
    ring = unary_union([x.exterior for x in polys])
    band = area.intersection(ring.buffer(width))
    hazards, barriers = scene.obstacles()
    local = [(name, shape, kind) for name, shape, kind in hazards if shape.distance(band) <= MARGIN]
    holes = [Polygon(r) for p in polys for r in p.interiors]
    local += [(f"{area_id}:inner/{i}", g, "HOLE") for i, g in enumerate(holes) if g.distance(band) <= MARGIN]
    walls = [(name, geom, gates) for name, geom, gates in barriers if geom.intersects(band)]
    return area, ring, band, local, walls


def verify_candidate_batch(batch, source, area_id, spatial, config):
    area, ring, band, hazards, walls, native_lines, native_tree = spatial
    lengths = np.array([e["length_m"] for e in batch])
    lines = shapely.linestrings([row["coordinates_metric"] for row in batch])
    bounds = ring.buffer(config["main_width_m"] + EPS, quad_segs=24)
    check(np.all(shapely.covers(area.buffer(1e-7), lines)), f"{area_id}: leaves raw area or hole")
    check(np.all(shapely.covers(bounds, lines)), f"{area_id}: leaves outer inner band")
    check(np.max(np.abs(shapely.length(lines) - lengths)) < 1e-8, f"{area_id}: inconsistent edge metres")
    present = STRtree([shape for _, shape, _ in hazards])
    near = present.query(lines, predicate="dwithin", distance=MARGIN - EPS)
    for i, j in zip(*near):
        row, line = batch[int(i)], lines[int(i)]
        name, geom, kind = hazards[int(j)]
        endpoint = Point(line.coords[-1])
        overlap = line.intersection(geom)
        check(row["kind"] == TERMINAL and kind == "BUILDING" and row["clearance_exception"]
              and name in row["obstacle_ids"] and row["v"].startswith("node/")
              and native_number(row["v"]) in source.outer_nodes(name)
              and overlap.geom_type == "Point" and overlap.distance(endpoint) <= EPS
              and line.relate_pattern(geom, "F********"),
              f"{row['qualified_id']}: .25m restriction failure {name}")
    if walls:
        wall_tree = STRtree([wall for _, wall, _ in walls])
        wall_pairs = wall_tree.query(lines, predicate="intersects")
        for i, j in zip(*wall_pairs):
            line = lines[int(i)]
            row = batch[int(i)]
            name, wall, gates = walls[int(j)]
            overlap = line.intersection(wall)
            points = [overlap] if overlap.geom_type == "Point" else list(overlap.geoms) if overlap.geom_type == "MultiPoint" else []
            check(points and all(any(point.distance(gate) <= EPS and f"node/{n}" in row["gate_ids"]
                                     for n, gate in gates.items()) for point in points),
                  f"{row['qualified_id']}: unlicensed line barrier crossing {name}")
    duplicate = defaultdict(list)
    if native_lines:
        pairs = native_tree.query(lines, predicate="dwithin", distance=EPS)
        for i, j in zip(*pairs):
            duplicate[int(i)].append(int(j))
        for i, js in duplicate.items():
            cover = unary_union([native_lines[j].buffer(EPS, cap_style="flat") for j in js])
            check(not cover.covers(lines[i]), f"{batch[i]['qualified_id']}: covers an existing native path")
    for row in batch:
        if row["kind"] == TERMINAL:
            check(row["direction"] == "U_TO_V" and row["native_port_id"] == row["v"]
                  and row["native_port_kind"] == "REGISTERED_ENTRANCE" and row["length_m"] <= config["port_max_m"]
                  and source.get(row["v"]).get("tags", {}).get("entrance") in {"main", "yes", "entrance", "exit"},
                  f"{row['qualified_id']}: incorrect registered terminal")
        elif row["native_port_id"]:
            check(row["length_m"] <= config["port_max_m"] and row["direction"] == "BIDIRECTIONAL",
                  f"{row['qualified_id']}: improper connection port")
            if row["native_port_kind"] == "NATIVE_CONTACT":
                n = native_number(row["native_port_id"])
                expected = {f"way/{way}" for (way, i), (keys, _, evidence) in source.native_segments.items()
                            if evidence == "EXPLICIT_WALK" and (n, "0", "0") in keys
                            and ground(source.objects["way"][way]["tags"])}
                check(n in source.outer_nodes(area_id) and expected == set(row["native_port_source_way_ids"]),
                      f"{row['qualified_id']}: non-native or misattributed boundary contact")
        else:
            check(row["direction"] == "BIDIRECTIONAL" and row["length_m"] <= math.sqrt(2)*config["grid_step_m"] + 1e-8,
                  f"{row['qualified_id']}: grid step exceeded")
    return len(batch)


def audit_edges(root, raw, config, used):
    by_area, edge_index, shapes = Counter(), {}, {}
    counts = Counter()
    coords_seen, duplicate_areas = {}, Counter()
    evidence_path = root / "data/edge_evidence.jsonl"
    geo_path = root / "data/derived_edges.geojson"
    batch = []
    prior = None
    with evidence_path.open(encoding="utf-8") as f:
        for line, feature in zip_longest(f, json_feature_stream(geo_path)):
            check(line is not None and feature is not None, "edge/evidence cardinalities differ")
            row = json.loads(line)
            area_key = row["scene_id"], row["source_area_id"]
            scene = raw[area_key[0]]
            area_id = area_key[1]
            if batch and (prior != area_key or len(batch) >= 4096):
                verify_candidate_batch(batch, raw[prior[0]], prior[1], shapes[prior], config)
                batch = []
            if area_key not in shapes:
                area, ring, band, hazards, walls = band_sources(scene, area_id)
                native = [LineString([scene.xy[k[0]] for k in keys])
                          for (way, i), (keys, _, _) in scene.native_segments.items()
                          if all(k[1:] == ("0", "0") for k in keys)
                          and ground(scene.objects["way"][way]["tags"])]
                shapes[area_key] = (area, ring, band, hazards, walls, native, STRtree(native))
            check(row["parent_input_sha256"] == scene.sha and row["source_tags"] == scene.get(area_id)["tags"]
                  and row["method_version"] == config["contract"] and row["run_id"] == MAIN
                  and row["crs_roundtrip_residual_m"] < EPS and row["width_m"] == WIDTH, "edge provenance differs")
            props = feature["properties"]
            check(feature["geometry"]["type"] == "LineString"
                  and row["coordinates_wgs84"] == feature["geometry"]["coordinates"]
                  and all(row[k] == props[k] for k in ("qualified_id", "u", "v", "kind", "source_area_id", "length_m")),
                  f"{row['qualified_id']}: GeoJSON/evidence mismatch")
            for node, wgs, xy in zip((row["u"], row["v"]), row["coordinates_wgs84"], row["coordinates_metric"]):
                check(math.dist(TO_METRES(*wgs), xy) < EPS, f"{row['qualified_id']}: CRS residual")
                if node.startswith("node/"):
                    check(tuple(wgs) == scene.wgs[native_number(node)] and tuple(xy) == scene.xy[native_number(node)],
                          f"{row['qualified_id']}: native coordinate changed")
            canonical = (area_key[0], tuple(sorted(tuple(x) for x in row["coordinates_metric"])))
            previous_area = coords_seen.setdefault(canonical, area_id)
            if previous_area != area_id:
                duplicate_areas[(area_key[0], previous_area, area_id)] += 1
            counts[row["kind"]] += 1
            by_area[area_key] += 1
            if (area_key[0], row["edge_id"]) in used:
                edge_index[(area_key[0], row["edge_id"])] = row
            batch.append(row)
            prior = area_key
    if batch:
        verify_candidate_batch(batch, raw[prior[0]], prior[1], shapes[prior], config)
    return counts, by_area, edge_index, [{"scene_id": k[0], "areas": k[1:], "count": n}
                                         for k, n in duplicate_areas.items()]


def planar_conflicts(source, section):
    hazards, walls = source.obstacles()
    line = LineString([TO_METRES(*p) for p in section["geometry"]["coordinates"]])
    hits = set()
    for name, geom, _ in hazards:
        if line.intersects(geom) and not line.relate_pattern(geom, "F********"):
            hits.add(name)
    for name, geom, gates in walls:
        if not line.intersects(geom):
            continue
        crossing = line.intersection(geom)
        clearance = unary_union([g.buffer(1e-7) for g in gates.values()])
        if not clearance.covers(crossing):
            hits.add(name)
    return hits


def audit_route(source, result, features, edge_index, origin, contact_id=None, audit_obstacles=True):
    sections = [features[i] for i in result["route_sections"]]
    coords = []
    measure, ellipsoid = 0., 0.
    conflicts = defaultdict(set)
    contact = source.wgs[native_number(contact_id)] if contact_id else None
    for f in sections:
        properties = f["properties"]
        part = [tuple(p) for p in f["geometry"]["coordinates"]]
        kind = properties["kind"]
        check(kind != GAP and len(properties["source_edges"]) == len(part)-1, "route references unsupported segment")
        if coords:
            check(coords[-1] == part[0], "route sections do not meet at exact coordinate")
        coords.extend(part[1:] if coords else part)
        part_len = 0.
        for (a, b), edge_id in zip(pairwise(part), properties["source_edges"]):
            part_len += math.dist(TO_METRES(*a), TO_METRES(*b))
            ellipsoid += geod_distance(a, b)
            if kind == NATIVE:
                _, way, i = edge_id.split("/")
                keys, orient, _ = source.native_segments[(int(way), int(i))]
                exact = {(source.wgs[keys[d][0]], source.wgs[keys[1-d][0]]) for d in orient}
                if (a, b) not in exact:
                    check(result["status"] == "APPROACH_WITH_GAP" and
                          any(a == x and LineString([TO_METRES(*x), TO_METRES(*y)]).distance(
                              Point(TO_METRES(*b))) < EPS for x, y in exact), f"{edge_id}: non-native line in route")
            elif properties["run_id"] == MAIN:
                row = edge_index[(properties["scene_id"], edge_id)]
                exact = tuple(map(tuple, row["coordinates_wgs84"]))
                check((a, b) == exact or row["direction"] == "BIDIRECTIONAL" and (b, a) == exact,
                      f"{edge_id}: route line does not follow its edge/direction")
        check(abs(part_len-properties["length_m"]) < EPS, "route section metric differs")
        measure += part_len
        if audit_obstacles:
            conflicts[kind].update(planar_conflicts(source, f))
    check(coords[0] == origin and coords[-1] == tuple(result["endpoint"]), "route origin/endpoint changed")
    if contact:
        native_end = [f for f in sections if f["properties"]["kind"] == NATIVE][-1]
        start_derived = next(f for f in sections if f["properties"]["kind"] == AREA_EDGE)
        check(tuple(native_end["geometry"]["coordinates"][-1]) == contact
              and tuple(start_derived["geometry"]["coordinates"][0]) == contact
              and all(f["properties"]["source_area_id"] == SOUTH for f in sections
                      if f["properties"]["kind"] != NATIVE), "route uses a different south contact or area")
    check(abs(measure-result["length_m"]) < EPS and abs(ellipsoid-result["length_geodesic_m"]) < EPS,
          "route total inconsistent with projected or WGS84 segment lengths")
    verified = {k: sorted(v) for k, v in conflicts.items() if v}
    check(not audit_obstacles or verified == result["obstacle_conflicts"], f"route conflict flags differ: {result['route_id']}")
    return {"status": result["status"], "projection_m": measure, "ellipsoid_m": ellipsoid,
            "segments": len(coords)-1, "conflicts": verified, "endpoint": coords[-1]}


def north_gap(source, origin_key, row, routes, edge_index):
    north_id = native_number(NORTH_DOOR)
    target = Point(source.xy[north_id])
    face = source.area(NORTH)
    raw_area_gap = face.distance(target)
    reachable = nx.descendants(source.native, origin_key) | {origin_key}
    candidates = []
    for (way, i), (keys, orient, _) in source.native_segments.items():
        if not ground(source.objects["way"][way]["tags"]):
            continue
        if all(keys[d] not in reachable for d in orient):
            continue
        line = LineString([source.xy[k[0]] for k in keys])
        candidates.append((line.distance(target), way, i, nearest_points(line, target)[0]))
    gap, way, i, point = min(candidates, key=lambda v: v[:3])
    check(row["reachable_edge"] == f"way/{way}" and math.dist(TO_METRES(*row["endpoint"]), point.coords[0]) < EPS
          and abs(row["gap_m"]-gap) < EPS and abs(row["source_face_gap_m"]-raw_area_gap) < EPS
          and raw_area_gap > 7.9 and row["exterior_approach"] == "APPROACH_WITH_GAP"
          and row["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT" and row["entrance_role"] == "exit",
          "north residual/role is inconsistent with native graph")
    nearby_line = LineString([point.coords[0], target.coords[0]])
    check(nearby_line.intersection(face).length < EPS and nearby_line.relate_pattern(source.area(TARGET_BUILDING), "F********")
          and row["gap_evidence"]["unsupported_length_m"] >= gap-EPS
          and row["gap_evidence"]["routable"] is False, "north gap is incorrectly supported")
    diagnostics = [f for f in routes.values() if f["properties"].get("route_id") == row["route_id"]
                   and f["properties"].get("kind") == GAP]
    check(len(diagnostics) == 1 and diagnostics[0]["properties"]["routable"] is False
          and diagnostics[0]["geometry"]["coordinates"] == [row["endpoint"], row["original_coordinate"]],
          "north gap is missing or leaks into route geometry")
    metrics = audit_route(source, row, routes, edge_index, source.wgs[origin_key[0]])
    return {"raw_face_distance_m": raw_area_gap, "reachable_projected_gap_m": gap, "nearest_native_way": f"way/{way}",
            "nearest_segment_index": i, "supported_length_m": nearby_line.intersection(face).length,
            "strict_reaches_door": False, "inbound": row["inbound_eligibility"], "route": metrics}


def alternate_south(source, contact_route, route_features):
    area, ring, band, hazards, walls = band_sources(source, SOUTH)
    domain = band.difference(unary_union([g.buffer(MARGIN) for _, g, _ in hazards]))
    sections = [route_features[i] for i in contact_route["route_sections"]]
    inner_lines = [x for x in sections if x["properties"]["kind"] == AREA_EDGE]
    terminal = sections[-1]["geometry"]["coordinates"]
    begin = Point(TO_METRES(*inner_lines[0]["geometry"]["coordinates"][1]))
    end = Point(TO_METRES(*terminal[0]))
    tris = list(shapely.constrained_delaunay_triangles(domain).geoms)
    check(tris, "no independent constrained triangles")
    grid = STRtree(tris)
    near_a = grid.query(begin, predicate="dwithin", distance=1e-7)
    near_b = grid.query(end, predicate="dwithin", distance=1e-7)
    check(len(near_a) and len(near_b), "independent mesh misses terminal interior candidates")
    dual, faces = nx.Graph(), defaultdict(list)
    for i, tri in enumerate(tris):
        for a, b in pairwise(tri.exterior.coords):
            faces[tuple(sorted((a, b)))].append(i)
    for (a, b), owners in faces.items():
        if len(owners) != 2:
            continue
        middle = ((a[0]+b[0])/2, (a[1]+b[1])/2)
        i, j = owners
        passage = LineString([tris[i].centroid, middle, tris[j].centroid])
        if not any(passage.intersects(wall) for _, wall, _ in walls):
            dual.add_edge(i, j, crossing=middle)
    chain = None
    for a in near_a:
        for b in near_b:
            if a == b:
                chain = [a]
            elif a in dual and b in dual and nx.has_path(dual, a, b):
                chain = nx.shortest_path(dual, a, b)
            if chain:
                break
        if chain:
            break
    check(chain is not None, "independent mesh found no connected component")
    witness = [begin.coords[0], tris[chain[0]].centroid.coords[0]]
    for a, b in pairwise(chain):
        witness.extend([dual[a][b]["crossing"], tris[b].centroid.coords[0]])
    witness.append(end.coords[0])
    line = LineString(witness)
    check(domain.buffer(1e-7).covers(line) and not any(line.intersects(wall) for _, wall, _ in walls),
          "independent mesh witness violates full polyline domain or barrier")
    return {"method": "CONSTRAINED_DELAUNAY_TRIANGLE_DUAL_WITH_CHECKED_INTERIOR_POLYLINE",
            "contact_id": contact_route["contact_id"], "triangle_count": len(tris),
            "triangles_along_witness": len(chain), "in_band_witness_m": line.length,
            "geometry_scope": "Between actual validated port interior ends; separate edge audit checks both ports."}


def graph_stats(graph, origin):
    groups = list(nx.weakly_connected_components(graph))
    return dict(nodes=len(graph), directed_edges=graph.number_of_edges(), weak_components=len(groups),
                largest_weak_component=max(map(len, groups), default=0),
                reachable_nodes=len(nx.descendants(graph, origin))+1 if origin in graph else 0)


def index_scenes(run):
    return {row["scene_id"]: row for row in run["scenes"]}


def audit(root):
    frozen = root / "frozen_r4"
    manifest = read(frozen / "BASELINE_MANIFEST.json")
    check(manifest["original_archive_sha256"] == "36d83fb2d792b33457968f1c649099380cc5cffa1e7b561c1dd6463fd82ce2f3",
          "incorrect historical archive identity")
    for row in manifest["entries"]:
        path = frozen / row["path"]
        check(path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], "portable source manifest mismatch")
    exp = read(root / "runs/experiment.json")
    cfg = read(root / "config/rev1_main.json")
    check(cfg == exp["config"] and exp["config_sha256"] == digest(root / "config/rev1_main.json")
          and cfg["widths_m"] == [3, 1, 5] and cfg["grid_step_m"] == .5 and cfg["clearance_m"] == .25
          and cfg["tolerance_m"] <= EPS and exp["external_requests"] == exp["field_checks"] == 0,
          "frozen parameters/request accounting differ")
    read_scene = lambda run: index_scenes(exp["runs"][run])
    old = read_scene("H0_FROZEN_B0")
    old_strict = read_scene("H1_R4_STRICT_LINES")
    no_added = read_scene("R1_WITHOUT_DERIVED_EDGES")
    main = read_scene(MAIN)
    hosted = read_scene("HISTORICAL_HOSTED_BASELINE")
    cases = exp["case_catalog"]
    raw = {s["scene_id"]: RawScene(frozen / s["osm_clip"]) for s in cases}
    check(len(raw) == 6 and all(set(raw) == set(d) for d in (old, old_strict, no_added, main, hosted)),
          "six frozen cases not preserved")
    for case in cases:
        sid = case["scene_id"]
        source = raw[sid]
        origin = (native_number(case["start_native_id"]), "0", "0")
        stats = graph_stats(source.native, origin)
        historic = read(frozen / case["historical_local_route"])
        historic = historic.get("route", historic)
        check(stats == old[sid]["graph"] == no_added[sid]["graph"]
              and old[sid]["matches_frozen"] and len(old[sid]["matched_fields"]) == 13
              and old[sid]["status"] == historic["status"] and old[sid]["length_m"] == historic["length_m"]
              and old[sid]["snap_end_m"] == historic["snap_end_m"] and old_strict[sid]["added_edges"] == 0
              and no_added[sid]["same_topology_and_native_weights"] and no_added[sid]["same_strict_entrances"]
              and no_added[sid]["native_signature_before"] == no_added[sid]["native_signature_after"]
              and hosted[sid]["internal_graph"] == "UNKNOWN"
              and hosted[sid]["status"] == "HISTORICAL_HOSTED_BASELINE",
              f"{sid}: baseline/ablation/native graph identity discrepancy")
        for door in case["r4_entrances"]:
            n = native_number(door["native_id"])
            check(tuple(door["original_coordinate"]) == source.wgs[n] and n in source.outer_nodes(case["building_native_id"]),
                  "registered door coordinate/way association changed")
        if not case["r4_entrances"]:
            check(not main[sid]["entrances"], f"{sid}: proxy entered eligibility")
    routes = {}
    for i, feature in enumerate(read(root / "data/routes.geojson")["features"]):
        key = feature["properties"].get("id", f"no-id/{i}")
        check(key not in routes, "duplicate route feature id")
        routes[key] = feature
    used = {(f["properties"]["scene_id"], edge) for f in routes.values()
            if f["properties"]["kind"] in (AREA_EDGE, TERMINAL) and f["properties"]["run_id"] == MAIN
            for edge in f["properties"]["source_edges"]}
    counts, by_area, edge_index, duplicates = audit_edges(root, raw, cfg, used)
    for sid, scenario in main.items():
        check(sum(n for (s, _), n in by_area.items() if s == sid) == scenario["truly_added_edges_unique"],
              f"{sid}: accepted edge total differs")
        for area in scenario["areas"]:
            check(by_area[(sid, area["area_id"])] == area["graph_edges_unique"], "accepted area edge count differs")
    report = read(root / "data/entrance_approach.json")
    museum = raw[MUSEUM]
    origin_key = (native_number(next(s for s in cases if s["scene_id"] == MUSEUM)["start_native_id"]), "0", "0")
    reachable = nx.descendants(museum.native, origin_key)
    south_native = {f"node/{k[0]}" for k in reachable if k[0] in museum.outer_nodes(SOUTH)
                    and any(evidence == "EXPLICIT_WALK" and k in keys for keys, _, evidence in museum.native_segments.values())}
    check(set(CONTACTS) == south_native and native_number(SOUTH_DOOR) in museum.outer_nodes(SOUTH)
          and native_number(SOUTH_DOOR) in museum.outer_nodes(TARGET_BUILDING)
          and native_number(NORTH_DOOR) not in museum.outer_nodes(NORTH)
          and museum.get(SOUTH_DOOR)["tags"]["entrance"] == "main"
          and museum.get(NORTH_DOOR)["tags"]["entrance"] == "exit",
          "museum raw source doors or three contacts mismatch")
    for contact, way in CONTACTS.items():
        check(native_number(contact) in museum.get(way)["nodes"], "wrong native contact supporting way")
    check({name for name, role in museum.members(SOUTH) if role == "inner"} == {"way/178721634", "way/178721647"},
          "south inner rings altered")
    actual_south = report["south"]["all_contacts"]
    check(set(CONTACTS) == {r["contact_id"] for r in actual_south}, "south attempts missing")
    south_results = {}
    for row in actual_south:
        check(row["continuous"] and tuple(row["endpoint"]) == museum.wgs[native_number(SOUTH_DOOR)]
              and row["gap_m"] < EPS, "south route did not end at native entrance")
        measured = audit_route(museum, row, routes, edge_index, museum.wgs[origin_key[0]], row["contact_id"])
        south_results[row["contact_id"]] = measured
    eligible = [r for r in actual_south if not r["obstacle_conflicts"]]
    winner = min(eligible, key=lambda r: r["length_m"])
    check(winner == report["south"]["selected"], "selected south route is not shortest clean among the three tested")
    north = north_gap(museum, origin_key, report["north"]["main"], routes, edge_index)
    library_id = "sh-library"
    lib = next(s for s in cases if s["scene_id"] == library_id)
    library = audit_route(raw[library_id], report["library"]["main"], routes, edge_index, tuple(lib["start"]))
    check(tuple(library["endpoint"]) == tuple(lib["target"]) and not library["conflicts"], "library regression failed")
    alternate = alternate_south(museum, winner, routes)
    sensitivity = {}
    for width in (1, 3, 5):
        run = MAIN if width == 3 else f"R1_WIDTH_{width}M"
        variants = index_scenes(exp["runs"][run])
        check(set(variants) == set(raw), "sensitivity coverage incomplete")
        by_scene = variants[MUSEUM]
        sensitivity[width] = dict(
            raw_derived_edges=sum(s["truly_added_edges_unique"] for s in variants.values()),
            south_statuses={r["contact_id"]: r["status"] for r in by_scene["south_contacts"]},
            north_gap_m=by_scene["entrances"][NORTH_DOOR]["gap_m"])
    return dict(status="PASS", method_identity="INDEPENDENT_RAW_SOURCE_NO_AUTHOR_GEOMETRY_IMPORTS",
                frozen_source_members=len(manifest["entries"]), raw_graphs=len(raw),
                evidence_and_geojson_edges=sum(counts.values()), edge_counts=dict(counts),
                exact_cross_area_duplicate_geometries=duplicates,
                edge_area_counts={f"{scene}/{area}": n for (scene, area), n in by_area.items()},
                south=south_results, selected_contact=winner["contact_id"], north=north,
                library=library, alternate_south=alternate, sensitivity=sensitivity,
                experiment_sha256=digest(root/"runs/experiment.json"),
                main_edge_evidence_sha256=digest(root/"data/edge_evidence.jsonl"),
                field_checks=0, user_review="PENDING", gpt_review="PENDING")


def verify_zip(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        check(len(names) == len(set(names)) and archive.testzip() is None, "ZIP duplicate or CRC fail")
        for name in names:
            p = PurePosixPath(name)
            check(not p.is_absolute() and not any(x in name for x in ("\\", ":"))
                  and all(not x.startswith(".") for x in p.parts), f"Unsafe archive path: {name}")
        rows = read_manifest(archive)
        check(set(names) == {r["path"] for r in rows} | {"MANIFEST.json"}
              and len(rows) + 1 == len(names), "ZIP manifest membership differs")
        for row in rows:
            name = row["path"]
            with archive.open(name) as f:
                checksum = file_digest(f, "sha256").hexdigest()
            check(checksum == row["sha256"] and archive.getinfo(name).file_size == row["bytes"],
                  f"ZIP member integrity: {name}")
    return {"status": "PASS", "members": len(names), "manifest_hashes": len(rows),
            "bytes": path.stat().st_size, "sha256": digest(path)}


def read_manifest(archive):
    return json.loads(archive.read("MANIFEST.json"))["entries"]



def audit_supplement(root):
    scene = RawScene(root / "frozen_r4/data/source/sh-huangpu-01.osm.json")
    old_rows = read(root / "data/routes.geojson")["features"]
    originals = {f["properties"]["id"]: f for f in old_rows if "id" in f["properties"]}
    rows = read(root / "data/native_prefix_diagnostic.geojson")["features"]
    native = {f["properties"]["id"]: f for f in rows if f["properties"]["kind"] == NATIVE}
    report = read(root / "data/native_prefix_diagnostic.json")
    check(report["selection_unchanged"] and report["removed_from_query_view_only"]
          and report["frozen_graph_signature_before"] == report["frozen_graph_signature_after"],
          "supplement altered frozen base or main selection")
    origin = tuple(next(s for s in read(root / "runs/experiment.json")["case_catalog"]
                        if s["scene_id"] == MUSEUM)["start"])
    measures = {}
    for record in report["records"]:
        side = record["subject"]
        alternate = record["alternate_native_prefix"] if side == "SOUTH_CONTACT" else record["alternate"]
        result = audit_route(scene, alternate, native, {}, origin)
        check(not result["conflicts"], "supplement has an independently observed obstacle conflict")
        if side == "SOUTH_CONTACT":
            fixed = [f for f in rows if f["properties"].get("source_route_id") == record["first_run_route"]]
            check(len(fixed) == 2 and all(f["geometry"] == originals[f["properties"]["id"]]["geometry"]
                                          for f in fixed), "derived suffix geometry changed in supplement")
            check(tuple(fixed[0]["geometry"]["coordinates"][0]) == result["endpoint"]
                  and fixed[-1]["geometry"]["coordinates"][-1] == record["original_registered_entrance"],
                  "supplemental south endpoint discontinuous")
            suffix = sum(math.dist(TO_METRES(*a), TO_METRES(*b)) for f in fixed
                         for a, b in pairwise(f["geometry"]["coordinates"]))
            check(abs(suffix+result["projection_m"]-record["total_m"]) < EPS, "supplemental south total differs")
            result["whole_route_to_same_door_m"] = suffix + result["projection_m"]
        else:
            first = read(root / "data/entrance_approach.json")["north"]["main"]
            check(result["endpoint"] == tuple(first["endpoint"]) and alternate["gap_evidence"] == first["gap_evidence"]
                  and alternate["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT"
                  and alternate["gap_evidence"]["routable"] is False,
                  "supplemental north endpoint/gap/role changed")
            result["gap_m"] = alternate["gap_m"]
        measures[side] = result
    check(set(measures) == {"SOUTH_CONTACT", "NORTH_APPROACH"}, "supplementary cases missing")
    return {"status": "PASS", "scope": "SEPARATE_NATIVE_OBSTACLE_VIEW_ROUTE_EVIDENCE",
            "routes": measures, "sha256": digest(root / "data/native_prefix_diagnostic.json")}



def browser_audit(root):
    from playwright.sync_api import sync_playwright
    import xml.etree.ElementTree as ET

    panel = "#panel-tabs [data-panel"
    network, errors = [], []
    edge_path = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(edge_path) if edge_path.exists() else None,
                                     headless=True, args=["--disable-background-networking"], timeout=20000)
        page = browser.new_page(accept_downloads=True, viewport={"width": 1420, "height": 1000})
        page.route("http://**/*", lambda route: (network.append("HTTP"), route.abort()))
        page.route("https://**/*", lambda route: (network.append("HTTPS"), route.abort()))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((root / "visuals/index.html").resolve().as_uri(), wait_until="load")
        check(page.locator("#panel-tabs a").count() == 6, "six review panels absent")
        old_new = page.locator("#map-grid svg[data-run]")
        check(old_new.count() == 2 and old_new.nth(0).get_attribute("viewBox") == old_new.nth(1).get_attribute("viewBox"),
              "old/new maps use different views")
        layer = page.locator("[data-layer-toggle=derived]")
        check(layer.count() == 1 and page.locator("#map-grid [data-layer=derived]").count() > 0,
              "derived overlay not inspectable")
        layer.uncheck()
        check(page.locator("#map-grid [data-layer=derived]").count() == 0, "derived layer toggle ineffective")
        layer.check()
        old_box = old_new.nth(0).get_attribute("viewBox")
        page.locator("#zoom-in").click()
        check(old_new.nth(0).get_attribute("viewBox") == old_new.nth(1).get_attribute("viewBox")
              and old_box != old_new.nth(0).get_attribute("viewBox"), "comparison zoom unsynchronized")
        page.locator("#zoom-reset").click()
        page.locator("#variant").select_option("R1_WITHOUT_DERIVED_EDGES")
        check(page.locator("#map-grid [data-layer=derived]").count() == 0, "ablation draws derived overlay")
        page.locator("#variant").select_option(MAIN)
        page.locator(panel + '="south-terminal"]').click()
        point = page.locator("#map-grid [data-layer=entrance]").first
        point.focus()
        point.press("Enter")
        check("121.4712158" in page.locator("#inspector").inner_text(), "original south coordinates not inspectable")
        page.locator(panel + '="north"]').click()
        check("7.95" in page.locator("#north-metric").inner_text()
              and page.locator("#map-grid [data-layer=gap]").count() > 0
              and "出口" in page.locator("#detail").inner_text(), "north gap/role missing in review")
        with page.expect_download() as downloaded:
            page.locator("#export").click()
        path = downloaded.value.path()
        tree = ET.parse(path)
        check(tree.getroot().tag.endswith("svg") and "north" in downloaded.value.suggested_filename,
              "SVG export unavailable or wrong review panel")
        for i in range(page.locator("#scene-select option").count()):
            page.locator("#scene-select").select_option(index=i)
            check(page.locator("#map-grid svg[data-run]").count() >= 1, "scene does not render")
        check(page.locator(".feedback li").count() == 4 and page.locator("input[type=number]").count() == 0,
              "natural language review changed")
        browser.close()
    check(not network and not errors, f"Offline browser network or page errors: {network}/{errors}")
    return {"status": "PASS", "offline_requests": 0, "six_panels": True, "all_scenes_rendered": True,
            "same_camera_zoom": True, "ablation_layer": True, "north_gap_visible": True,
            "native_coordinate_keyboard_inspection": True, "downloaded_svg_parses": True,
            "scope": "Independent browser interaction, no human scoring"}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    cli.add_argument("--archive", type=Path)
    cli.add_argument("--supplement-only", action="store_true")
    cli.add_argument("--browser", action="store_true")
    cli.add_argument("--out", type=Path)
    options = cli.parse_args()
    report = (verify_zip(options.archive) if options.archive else
              audit_supplement(options.root) if options.supplement_only else
              browser_audit(options.root) if options.browser else audit(options.root))
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if options.out:
        with options.out.open("x", encoding="utf-8") as f:
            f.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
