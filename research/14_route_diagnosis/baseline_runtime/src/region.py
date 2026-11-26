"""Build a four-state local surface before any route queries are read."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

import networkx as nx
from shapely import make_valid, normalize
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

NATIVE = "NATIVE_WALKABLE"
INFERRED = "INFERRED_WALKABLE"
RESTRICTED = "RESTRICTED"
UNKNOWN = "UNKNOWN"
STATES = (NATIVE, INFERRED, RESTRICTED, UNKNOWN)
EPS = 1e-8
DENIED = {"no", "private", "customers", "destination", "delivery", "permit", "restricted",
          "agricultural", "forestry"}
WALK = {"footway", "pedestrian", "path", "steps", "corridor", "living_street"}
FACE = {"PEDESTRIAN_AREA", "WALKABLE_AREA", "NATIVE_WALKABLE_AREA"}
PARK = {"PARK", "PARK_GARDEN_OR_RECREATION"}
PAVING = {"PAVING", "PAVED", "PAVED_AREA", "PLAZA"}
BACKGROUND = {"GRASS", "BACKGROUND_GRASS", "FLOWERBED", "MEADOW"}


def digest(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def polygons(geometry):
    if isinstance(geometry, Polygon):
        if geometry.area > EPS:
            yield geometry
    else:
        for part in getattr(geometry, "geoms", []):
            yield from polygons(part)


def union(items):
    return unary_union(list(items))


def access_conflict(tags):
    level = tags.get("foot", tags.get("access"))
    return (level in DENIED or tags.get("locked") == "yes" or
            any(k in tags for k in ("foot:conditional", "access:conditional", "oneway:foot:conditional")))


def non_ground(tags):
    return (tags.get("highway") in {"steps", "elevator"} or
            any(tags.get(k) not in (None, "", "0", "no", "false")
                for k in ("level", "layer", "bridge", "tunnel", "indoor", "repeat_on")))


def edge_source(edge):
    key = edge.get("source_id", edge["id"])
    return re.match(r"(?:node|way|relation)/\d+", key).group() if re.match(
        r"(?:node|way|relation)/\d+", key) else key


class Objects:
    def __init__(self, rows):
        self.rows = rows
        self.tree = STRtree([row["g"] for row in rows])

    def hits(self, geometry, distance=None):
        if distance is None:
            idx = self.tree.query(geometry, predicate="intersects")
        else:
            idx = self.tree.query(geometry, predicate="dwithin", distance=distance)
        return [self.rows[i] for i in sorted(idx)]

    def covering(self, point):
        return [row for row in self.hits(point) if row["g"].covers(point)]


@dataclass
class Surface:
    domain: object
    cells: list
    masks: dict
    context: dict
    sha256: str
    area_m2: dict
    statistics: dict
    step: float


def context_layers(observed, domain, cfg):
    layers = {k: [] for k in ("hard", "background", "support", "native")}
    for layer, rows in observed["context"].items():
        for row in rows:
            tags = row.get("tags", {})
            kind = row["kind"]
            geom = make_valid(shape(row["geometry"]))
            if geom.is_empty or not geom.intersects(domain.buffer(cfg["network_near_m"])):
                continue
            props = {**row, "g": geom}
            if layer == "hard" or access_conflict(tags) or non_ground(tags) or kind in BACKGROUND:
                group = "background" if layer == "background" and not access_conflict(tags) else "hard"
                if geom.area <= EPS:
                    # Shared openings are separately supplied by the source as known gate points.
                    geom = geom.buffer(cfg["hard_line_clearance_m"])
                    gates = [Point(g["xy"]).buffer(cfg["hard_line_clearance_m"] * 2)
                             for g in row.get("gates", []) if g.get("allowed")]
                    if gates:
                        geom = geom.difference(union(gates))
                layers[group].append({**props, "g": geom})
            elif kind in FACE or tags.get("highway") == "pedestrian" or tags.get("area:highway") in WALK:
                if geom.area > EPS:
                    layers["native"].append(props)
            else:
                layers["support"].append(props)
    return layers


def visible_network(observed, domain, cfg):
    nodes = {node["id"]: node for node in observed["nodes"]}
    local = domain.buffer(cfg["network_near_m"])
    lx, ly, ux, uy = local.bounds
    seen, rows = set(), []
    for edge in observed["edges"]:
        u, v = (nodes[edge[k]] for k in ("u", "v"))
        source = edge_source(edge)
        key = (min(edge["u"], edge["v"]), max(edge["u"], edge["v"]), source)
        if key in seen:
            continue
        seen.add(key)
        if any(access_conflict(x) or non_ground(x) for x in
               (edge.get("tags", {}), u.get("tags", {}), v.get("tags", {}))):
            continue
        a, b = u["xy"], v["xy"]
        if max(a[0], b[0]) < lx or min(a[0], b[0]) > ux or max(a[1], b[1]) < ly or min(a[1], b[1]) > uy:
            continue
        line = LineString([a, b])
        tags = edge.get("tags", {})
        if (edge.get("kind") in {"NATIVE_LINEAR", "NATIVE"} and
                (tags.get("highway") in WALK or tags.get("foot") in {"yes", "designated", "permissive", "official"})
                and line.length > EPS and line.intersects(local)):
            rows.append({"id": source, "g": line, "tags": tags})
    return Objects(rows)


def distinct_sides(point, nearby):
    """Two separated map ways on different sides, evaluated without route endpoints."""
    offsets = {}
    for row in nearby:
        line = row["g"]
        closest = line.interpolate(line.project(point))
        dx, dy = closest.x-point.x, closest.y-point.y
        d = math.hypot(dx, dy)
        if d < 1 or (row["id"] in offsets and offsets[row["id"]][0] < d):
            continue
        offsets[row["id"]] = (d, dx/d, dy/d)
    ids = sorted(offsets)
    return any(offsets[a][1]*offsets[b][1]+offsets[a][2]*offsets[b][2] <= -0.25
               for i, a in enumerate(ids) for b in ids[i+1:])


def contextual_reason(point, layers, network, door, facade, cfg, ablate):
    nearby = network.hits(point, cfg["network_near_m"])
    native_near = layers["native"].hits(point, cfg["face_near_m"])
    if not nearby and not native_near:
        return None, []
    support = layers["support"].covering(point)
    paved = [row for row in support if row["kind"] in PAVING]
    park = [row for row in support if row["kind"] in PARK]
    ids = {row["id"] for row in nearby + native_near + paved + park}
    if ablate:
        return "GEOMETRY_AND_NETWORK_ONLY_ABLATION", sorted(ids)
    if paved:
        return "PAVING_AND_OBSERVED_NETWORK_ADJACENCY", sorted(ids)
    if native_near and nearby:
        return "MAPPED_PEDESTRIAN_FACE_AND_WALKWAY_ADJACENCY", sorted(ids)
    frontage = (door and facade is not None and point.distance(Point(door["xy"])) <= cfg["door_near_m"] and
                point.distance(facade.boundary) <= cfg["frontage_near_m"] and
                not access_conflict(door.get("tags", {})) and not non_ground(door.get("tags", {})))
    if park and frontage and nearby:
        return "PARK_AND_REGISTERED_FRONTAGE_AND_WALKWAY", sorted(ids | {door["id"], door["building_id"]})
    if park and distinct_sides(point, nearby):
        return "PARK_AND_OBSERVED_WALKWAYS_ON_DISTINCT_SIDES", sorted(ids)
    return None, sorted(ids)


def build_surface(observed, cfg, *, ablate_context=False):
    """Only a spatial observation and fixed domain may enter. No start/end/query/reference."""
    allowed = {"task_id", "crs", "domain", "registered_entrance", "nodes", "edges", "context"}
    if set(observed) != allowed or observed["crs"] != "EPSG:32651":
        raise ValueError("Surface observation violates the coordinate or field whitelist")
    center = Point(observed["domain"]["anchor_xy"])
    domain = center.buffer(cfg["domain_radius_m"], quad_segs=32)
    door = observed["registered_entrance"]
    layers = context_layers(observed, domain, cfg)
    # A hard constraint overrides an area claim. A background grass face restricts new area
    # inference, while the original valid walking centerline remains a separate graph layer.
    hard_objs = Objects(layers["hard"] + layers["background"])
    index = {k: Objects(layers[k]) for k in ("native", "support")}
    network = visible_network(observed, domain, cfg)
    hard = union(row["g"].intersection(domain) for row in hard_objs.rows)
    native = union(row["g"].intersection(domain) for row in layers["native"]).difference(hard)
    facade = next((row["g"] for row in layers["hard"] if door and row["id"] == door["building_id"]), None)
    step = cfg["cell_m"]
    x0, y0, x1, y1 = domain.bounds
    cell_rows = []
    for i in range(math.floor(x0/step), math.ceil(x1/step)):
        for j in range(math.floor(y0/step), math.ceil(y1/step)):
            part = box(i*step, j*step, (i+1)*step, (j+1)*step).intersection(domain)
            if part.area <= EPS:
                continue
            for geom, state in ((part.intersection(hard), RESTRICTED),
                                (part.intersection(native), NATIVE),
                                (part.difference(hard).difference(native), UNKNOWN)):
                for g in polygons(geom):
                    if state == RESTRICTED:
                        conflicts = [row["id"] for row in hard_objs.hits(g) if row["g"].intersection(g).area > EPS]
                        rec = (state, sorted(set(conflicts)), sorted(set(conflicts)), "MAPPED_CONFLICT_OR_BACKGROUND_LANDCOVER")
                    elif state == NATIVE:
                        ids = [row["id"] for row in index["native"].hits(g) if row["g"].intersection(g).area > EPS]
                        rec = (state, sorted(set(ids)), [], "EXPLICIT_MAPPED_PEDESTRIAN_AREA")
                    else:
                        reason, ids = contextual_reason(g.representative_point(), index, network, door, facade, cfg, ablate_context)
                        rec = (INFERRED if reason else UNKNOWN, ids, [], reason or "INSUFFICIENT_POSITIVE_EVIDENCE")
                    cell_rows.append((i, j, g, *rec))

    # Reject narrow or isolated inferred patches. Geometric erosion tests width without
    # dilating a known centerline or using a route; it does not assert an actual sidewalk width.
    proposed = union(g for _, _, g, state, *_ in cell_rows if state in (INFERRED, NATIVE))
    cores = proposed.buffer(-cfg["min_region_clearance_m"])
    wide = union(part for part in polygons(proposed) if part.area >= cfg["min_patch_area_m2"]
                 and part.intersects(cores))
    cells = []
    for i, j, g, state, ids, conflicts, reason in cell_rows:
        if state == INFERRED and not wide.covers(g.representative_point()):
            state, reason = UNKNOWN, "INSUFFICIENT_CONNECTED_PATCH_WIDTH_OR_AREA"
        coords = mapping(normalize(g))
        cells.append({"region_id": f"cell/{i}/{j}/{len(cells)}", "ij": (i, j),
                      "geometry": coords, "g": g, "walkability_state": state,
                      "evidence_sources": ids, "hard_conflicts": conflicts, "decision_reason": reason,
                      "assumptions": (["OUTDOOR_LOCAL_GROUND_CONTINUITY_UNVERIFIED",
                                       "SURFACE_PERMISSION_AND_LEVEL_NOT_FIELD_VERIFIED"]
                                      if state == INFERRED else []),
                      "uncertainty_level": {INFERRED:"CONDITIONAL_UNCALIBRATED", NATIVE:"SOURCE_MAPPED",
                                            RESTRICTED:"RULE_OR_SOURCE_CONFLICT", UNKNOWN:"UNRESOLVED"}[state],
                      "source_status": {NATIVE:"native", INFERRED:"inferred", RESTRICTED:"derived", UNKNOWN:"derived"}[state],
                      "area_m2": g.area})
    masks = {s: union(c["g"] for c in cells if c["walkability_state"] == s) for s in STATES}
    area = {s: masks[s].area for s in STATES}
    canonical = [{k:v for k,v in c.items() if k != "g"} for c in cells]
    return Surface(domain, cells, masks, layers, digest(canonical), area,
                   {"cell_fragments":len(cells), "inferred_components":len(list(polygons(masks[INFERRED]))),
                    "classified_m2":sum(area.values()), "search_domain_m2":domain.area,
                    "direct_native_way_ids":len({r["id"] for r in network.rows})}, step)
