"""Deterministic, observed-only local path inference in EPSG:32651 metres."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
import math

import networkx as nx
from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union

INVERSE = Transformer.from_crs(32651, 4326, always_xy=True).transform
GEOD = Geod(ellps="WGS84")
EPS = 1e-5
NATIVE = "NATIVE_LINEAR"
DERIVED = "DERIVED_FROM_TAGGED_PEDESTRIAN_AREA"
INFERRED = "INFERRED_ALLOWED"
WALK_TYPES = {"footway", "path", "pedestrian", "steps"}
PUBLIC = {"yes", "designated", "official", "permissive"}
RESTRICTED = {"no", "private", "restricted", "permit", "customers", "destination", "delivery",
              "agricultural", "forestry", "use_sidepath"}
LEVEL_KEYS = {"level", "layer", "repeat_on", "bridge", "tunnel", "indoor", "ele", "height", "incline", "ramp"}
SUPPORTED_CONTEXT = {"PARK", "PEDESTRIAN_AREA", "PAVING", "PAVED_AREA", "PLAZA", "WALKABLE_AREA"}
KINDS = {"NETWORK_GAP_TASK", "REGISTERED_DOOR_TASK"}
TOP_FIELDS = {"task_id", "kind", "crs", "origin", "target", "nodes", "edges", "context", "schema_version"}
NODE_FIELDS = {"id", "xy", "wgs84", "tags"}
EDGE_FIELDS = {"id", "u", "v", "tags", "kind", "source_id", "segment_index", "evidence"}
TARGET_FIELDS = {"id", "xy", "wgs84", "tags", "registered", "building_id"}
CONTEXT_FIELDS = {"hard", "background", "support"}
OBJECT_FIELDS = {"id", "kind", "geometry", "tags", "gates"}


def points(xy):
    out = tuple(float(value) for value in xy)
    if len(out) != 2 or not all(map(math.isfinite, out)):
        raise ValueError("Expected finite XY coordinates")
    return out


def read_fields(obj, allowed):
    if not isinstance(obj, dict) or not obj.keys() <= allowed:
        raise ValueError("Observation has fields outside the prediction contract")


def access_conflict(tags):
    if any(k in tags for k in ("access:conditional", "foot:conditional")):
        return "CONDITIONAL_ACCESS_UNRESOLVED"
    if tags.get("foot") in RESTRICTED or (tags.get("foot") not in PUBLIC and tags.get("access") in RESTRICTED):
        return "EXPLICIT_WALK_ACCESS_RESTRICTION"
    return None


def grade_conflict(tags):
    active = lambda key: tags.get(key) not in (None, "", "no", "0", 0, False)
    return (tags.get("highway") in {"steps", "elevator"}
            or any(active(k) for k in ("layer", "level", "repeat_on", "bridge", "tunnel", "indoor")))


def mapped_walk(tags):
    return (tags.get("highway") in WALK_TYPES or tags.get("foot") in PUBLIC) and not access_conflict(tags)


def pedestrian_edge(row):
    return (row["kind"] in {DERIVED, "DERIVED_TERMINAL_CONNECTOR"} or mapped_walk(row["tags"]))


def union(items):
    return unary_union(list(items))


@dataclass
class Observation:
    task: dict
    graph: nx.MultiDiGraph
    objects: dict

    @classmethod
    def parse(cls, task):
        read_fields(task, TOP_FIELDS)
        if task["crs"] != "EPSG:32651" or task["kind"] not in KINDS:
            raise ValueError("Unsupported observation CRS or task kind")
        target = task["target"]
        read_fields(target, TARGET_FIELDS)
        if task["kind"] == "REGISTERED_DOOR_TASK" and (
                target.get("registered") is not True or not target.get("building_id")
                or target.get("tags", {}).get("entrance") in (None, "no")):
            raise ValueError("Registered door task has no preserved native identity")
        g = nx.MultiDiGraph()
        for node in task["nodes"]:
            read_fields(node, NODE_FIELDS)
            key = str(node["id"])
            if key in g:
                raise ValueError("Duplicate observed node")
            xy = points(node["xy"])
            wgs = points(node["wgs84"]) if node.get("wgs84") is not None else INVERSE(*xy)
            g.add_node(key, xy=xy, wgs84=wgs, tags=node.get("tags", {}))
        if str(task["origin"]) not in g:
            raise ValueError("Unknown frozen origin")
        for edge in task["edges"]:
            read_fields(edge, EDGE_FIELDS)
            a, b = str(edge["u"]), str(edge["v"])
            if a not in g or b not in g:
                raise ValueError("Observed edge refers to an absent node")
            xy = [g.nodes[a]["xy"], g.nodes[b]["xy"]]
            length = math.dist(*xy)
            if a == b:
                continue
            kind = edge.get("kind", NATIVE)
            if kind not in {NATIVE, DERIVED, "DERIVED_TERMINAL_CONNECTOR"}:
                raise ValueError("Only observed native and pre-existing derived edges are admissible")
            tags = edge.get("tags", {})
            if access_conflict(tags) or any(access_conflict(g.nodes[k]["tags"]) for k in (a, b)):
                continue
            g.add_edge(a, b, id=str(edge["id"]), source_id=str(edge.get("source_id", edge["id"])),
                       kind=kind, tags=tags, segment_index=edge.get("segment_index"), evidence=edge.get("evidence"),
                       length_m=length, cost_m=length, xy=xy, hypothesis=False)
        context = task["context"]
        read_fields(context, CONTEXT_FIELDS)
        objects = {}
        for category in CONTEXT_FIELDS:
            objects[category] = []
            for row in context.get(category, []):
                read_fields(row, OBJECT_FIELDS)
                geometry = shape(row["geometry"])
                if not geometry.is_empty and geometry.is_valid:
                    objects[category].append(dict(row, geometry=geometry))
                else:
                    raise ValueError("Observation must resolve geometry or provide an explicit unknown mask")
        return cls(task, g, objects)


def polygon_parts(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [part for p in getattr(geometry, "geoms", ()) for part in polygon_parts(p)]


class LocalDomain:
    def __init__(self, observed, config):
        self.target = observed.task["target"]
        self.end = Point(points(self.target["xy"]))
        self.cfg = config
        self.window = self.end.buffer(config["radius_m"], quad_segs=16)
        self.building = None
        self.masks = []
        self.support = []
        self.observed = observed
        for row in observed.objects["hard"] + observed.objects["background"]:
            geom = row["geometry"]
            if geom.distance(self.window) > config["clearance_m"]:
                continue
            own_building = row["id"] == self.target.get("building_id") and row["kind"] == "BUILDING"
            if own_building:
                self.building = row
            if own_building or row["kind"] in {"GRASS", "FLOWERBED"}:
                mask = geom
            else:
                mask = geom.buffer(config["clearance_m"], quad_segs=6) if config["clearance_m"] else geom
            self.masks.append((row, mask, own_building))
        for row in observed.objects["support"]:
            if (row["kind"] in SUPPORTED_CONTEXT and row["geometry"].intersects(self.window)
                    and not access_conflict(row.get("tags", {})) and not grade_conflict(row.get("tags", {}))):
                self.support.append(row)
        cutouts = union(mask for _, mask, _ in self.masks if mask.area > EPS)
        self.domain = self.window.difference(cutouts)
        self.padded = self.domain.buffer(EPS)
        self.pedestrian = union(row["geometry"] for row in self.support)
        self.target_conflict = access_conflict(self.target.get("tags", {}))
        if not self.target_conflict and grade_conflict(self.target.get("tags", {})):
            self.target_conflict = "EXPLICIT_NON_GROUND_TARGET"
        if observed.task["kind"] == "REGISTERED_DOOR_TASK" and not (
                self.building and self.building["geometry"].boundary.distance(self.end) <= EPS):
            self.target_conflict = "REGISTERED_DOOR_EXTERIOR_NOT_LOCATED"

    def conflict_ids(self, line, terminal):
        reasons = []
        for row, mask, own in self.masks:
            overlap = line.intersection(mask)
            if overlap.is_empty:
                continue
            if own:
                if terminal and overlap.difference(self.end.buffer(EPS)).is_empty:
                    continue
            elif mask.area > EPS:
                # Tangency at the outside of an explicit exclusion does not cross it.
                if line.relate_pattern(mask, "F********") and not line.intersects(row["geometry"]):
                    continue
            reasons.append((row["id"], row["kind"]))
        return reasons

    def allowed(self, line, terminal):
        return self.padded.covers(line) and not self.conflict_ids(line, terminal)

    def paths(self, anchors):
        """Exact visibility search for detours; a valid straight edge already attains the lower bound."""
        outcomes = {}
        needs_detour = []
        for candidate in anchors:
            a = candidate["xy"]
            line = LineString([a, self.end.coords[0]])
            if self.allowed(line, True):
                outcomes[candidate["id"]] = (list(line.coords), None)
            else:
                needs_detour.append(candidate)
        if not needs_detour:
            return outcomes
        vertices = {tuple(self.end.coords[0])}
        for poly in polygon_parts(self.domain):
            for ring in (poly.exterior, *poly.interiors):
                vertices.update(map(tuple, ring.coords))
        vertices.update(c["xy"] for c in needs_detour if self.padded.covers(Point(c["xy"])))
        if len(vertices) > self.cfg["visibility_vertex_limit"]:
            outcomes.update((c["id"], (None, "VISIBILITY_VERTEX_LIMIT")) for c in needs_detour)
            return outcomes
        graph = nx.Graph()
        graph.add_nodes_from(vertices)
        end = tuple(self.end.coords[0])
        for a, b in combinations(sorted(vertices), 2):
            line = LineString([a, b])
            if self.allowed(line, end in (a, b)):
                graph.add_edge(a, b, metres=line.length)
        paths = nx.single_source_dijkstra_path(graph, end, weight="metres")
        for c in needs_detour:
            path = paths.get(c["xy"])
            outcomes[c["id"]] = (list(reversed(path)) if path else None, None if path else "NO_CONSTRAINED_PATH")
        return outcomes


def group_edges(graph):
    by_way = defaultdict(list)
    for a, b, key, edge in graph.edges(keys=True, data=True):
        group = (tuple(sorted((a, b))), edge["source_id"], edge["kind"], edge["segment_index"])
        by_way[group].append((a, b, key, edge))
    return by_way


def anchors_for(observed, local):
    graph = observed.graph
    distances = nx.single_source_dijkstra_path_length(graph, str(observed.task["origin"]), weight="cost_m")
    target_key = str(local.target["id"])
    positions = {}
    counts = Counter()
    for group, rows in group_edges(graph).items():
        a, b, _, sample = rows[0]
        if target_key in (a, b):
            continue
        if not pedestrian_edge(sample):
            continue
        xy_a, xy_b = graph.nodes[a]["xy"], graph.nodes[b]["xy"]
        segment = LineString([xy_a, xy_b])
        if segment.distance(local.end) > local.cfg["radius_m"]:
            continue
        counts["local_mapped_walk_edges"] += 1
        if grade_conflict(sample["tags"]) or grade_conflict(graph.nodes[a]["tags"]) or grade_conflict(graph.nodes[b]["tags"]):
            counts["explicit_non_ground_source_edges"] += 1
            continue
        if not any(u in distances for u, _, _, _ in rows):
            counts["unreachable_source_edges"] += 1
            continue
        nearest = tuple(segment.interpolate(segment.project(local.end)).coords[0])
        for p, node in [(nearest, None), (xy_a, a), (xy_b, b)]:
            gap = local.end.distance(Point(p))
            if not local.cfg["min_length_m"] <= gap <= local.cfg["radius_m"]:
                continue
            if node is None:
                node = a if math.dist(p, xy_a) <= EPS else b if math.dist(p, xy_b) <= EPS else None
            reach = (distances.get(node, math.inf) if node is not None else
                     min((distances.get(u, math.inf) + math.dist(graph.nodes[u]["xy"], p)
                          for u, _, _, _ in rows), default=math.inf))
            if not math.isfinite(reach):
                continue
            rank = (gap, reach, str(group))
            key = (node, p) if node is not None else (group, p)
            if key not in positions or rank < positions[key]["rank"]:
                positions[key] = dict(xy=p, node=node, group=group, rows=rows, gap_m=gap, graph_distance_m=reach,
                                      rank=rank, source_id=sample["source_id"], source_tags=sample["tags"],
                                      source_segment_index=sample["segment_index"], source_kind=sample["kind"])
    candidates = []
    counts["raw_distinct_positions"] = len(positions)
    for row in sorted(positions.values(), key=lambda r: r["rank"]):
        if any(math.dist(row["xy"], c["xy"]) < local.cfg["anchor_separation_m"] for c in candidates):
            counts["spatially_deduplicated"] += 1
            continue
        row["id"] = f"anchor/{len(candidates)+1}"
        candidates.append(row)
        if len(candidates) == local.cfg["max_candidates"]:
            break
    counts["submitted"] = len(candidates)
    return candidates, dict(counts)


def continuation_dot(graph, at, outgoing, candidates):
    direction = (outgoing[0] - at[0], outgoing[1] - at[1])
    norm = math.hypot(*direction)
    if norm <= EPS:
        return None
    result = []
    for n in candidates:
        x, y = graph.nodes[n]["xy"]
        # A visible observed walkway behind the join supports continuation in the opposite direction.
        dx, dy = at[0] - x, at[1] - y
        l = math.hypot(dx, dy)
        if l > EPS:
            result.append((direction[0] * dx + direction[1] * dy) / (norm * l))
    return max(result, default=None)


def pedestrian_neighbours(graph, key):
    if key not in graph:
        return set()
    return {b for a, b, e in graph.out_edges(key, data=True) if pedestrian_edge(e) and not grade_conflict(e["tags"])} | {
        a for a, b, e in graph.in_edges(key, data=True) if pedestrian_edge(e) and not grade_conflict(e["tags"])}


def context_evidence(observed, local, anchor, path):
    line = LineString(path)
    hits = []
    for row in local.support:
        length = line.intersection(row["geometry"]).length
        if length > EPS:
            hits.append({"source_id": row["id"], "kind": row["kind"], "coverage_m": length})
    overlap = line.intersection(local.pedestrian).length
    graph = observed.graph
    neighbours = (pedestrian_neighbours(graph, anchor["node"]) if anchor["node"] is not None
                  else set(anchor["group"][0]))
    source_dot = continuation_dot(graph, path[0], path[1], neighbours)
    target_neighbours = pedestrian_neighbours(graph, str(local.target["id"]))
    target_dot = continuation_dot(graph, path[-1], path[-2], target_neighbours)
    alignment = (source_dot is not None and target_dot is not None
                 and min(source_dot, target_dot) >= local.cfg["alignment_dot"])
    threshold = local.cfg["context_overlap_fraction"] * line.length
    cues = (["MAPPED_PEDESTRIAN_OR_PARK_CONTEXT"] if overlap + EPS >= threshold else []) + (
        ["TWO_SIDED_OBSERVED_WALKWAY_CONTINUATION"] if alignment else [])
    return dict(support=hits, combined_coverage_m=overlap, coverage_ratio=overlap / line.length,
                source_continuation_dot=source_dot, target_continuation_dot=target_dot, cues=cues)


def decide(observed, local, anchor, path, reason=None, ignore_context=False):
    end = tuple(local.end.coords[0])
    direct = LineString([anchor["xy"], end])
    conflicts = local.conflict_ids(direct, True)
    info = {k: v for k, v in anchor.items() if k not in {"group", "rows", "rank"}}
    info.update(status="UNRESOLVED", reason=reason, direct_conflicts=conflicts,
                route_selected=False, candidate_xy=path or list(direct.coords), grade_status="UNOBSERVED_CONTINUOUS_LEVEL")
    if local.target_conflict:
        info.update(status="REJECTED", reason=local.target_conflict)
    elif path is None:
        if conflicts:
            info.update(status="REJECTED", reason="MAPPED_OBSTACLE_OR_LEVEL_CONFLICT")
        return info
    else:
        line = LineString(path)
        if not all(local.allowed(LineString([a, b]), index == len(path) - 2)
                   for index, (a, b) in enumerate(zip(path, path[1:]))):
            info.update(status="REJECTED", reason="CONNECTOR_HARD_CONFLICT")
        elif line.length > local.cfg["max_length_m"]:
            info.update(status="REJECTED", reason="CONNECTOR_LENGTH_LIMIT")
        else:
            evidence = context_evidence(observed, local, anchor, path)
            info.update(length_m=line.length, context=evidence, geometry_status="NO_MAPPED_CONFLICT",
                        same_level_assumption="UNOBSERVED_LEVEL_LOCAL_OUTDOOR_SURFACE",
                        level_penalty_m=local.cfg["level_assumption_penalty_m"],
                        inference_penalty_m=local.cfg["inference_penalty_m"])
            if evidence["cues"] or ignore_context:
                info.update(status=INFERRED, reason=("CONTEXT_ABLATION" if ignore_context else "CONTEXT_AND_HARD_RULES"),
                            cost_m=line.length + local.cfg["inference_penalty_m"] + local.cfg["level_assumption_penalty_m"])
            else:
                info["reason"] = "INSUFFICIENT_WALKABILITY_CONTEXT"
    return info


def replace_splits(graph, placements):
    group_anchors = defaultdict(list)
    for candidate in placements:
        if candidate["node"] is None:
            group_anchors[candidate["group"]].append(candidate)
    for anchors in group_anchors.values():
        for row in anchors:
            graph.add_node(row["id"], xy=row["xy"], wgs84=INVERSE(*row["xy"]), tags={})
        for a, b, key, edge in anchors[0]["rows"]:
            start, end = graph.nodes[a]["xy"], graph.nodes[b]["xy"]
            nodes = [a, *(c["id"] for c in sorted(anchors, key=lambda c: math.dist(start, c["xy"]))), b]
            graph.remove_edge(a, b, key)
            for u, v in zip(nodes, nodes[1:]):
                xy = [graph.nodes[u]["xy"], graph.nodes[v]["xy"]]
                length = math.dist(*xy)
                graph.add_edge(u, v, **dict(edge, xy=xy, length_m=length, cost_m=length,
                                            topology="EXACT_DIRECTED_EDGE_SPLIT"))


def routing_weight(edge):
    # Resolve equal generalized costs in favor of reusing observed geometry.
    tie_break = edge["length_m"] * 1e-10 if edge["kind"] == INFERRED else 0.0
    return edge["cost_m"] + tie_break


def compute_route(graph, origin, target):
    if target not in graph:
        return None
    try:
        path = nx.shortest_path(graph, origin, target,
                                weight=lambda _a, _b, rows: min(map(routing_weight, rows.values())))
    except nx.NetworkXNoPath:
        return None
    records = []
    for a, b in zip(path, path[1:]):
        edge = min(graph[a][b].values(), key=lambda e: (routing_weight(e), e["id"]))
        xy = edge["xy"]
        coords = [graph.nodes[a]["wgs84"], *(INVERSE(*p) for p in xy[1:-1]), graph.nodes[b]["wgs84"]]
        records.append(dict(edge, u=a, v=b, wgs84=coords))
    totals = Counter()
    for row in records:
        totals[row["kind"]] += row["length_m"]
    native = totals[NATIVE]
    derived = totals[DERIVED] + totals["DERIVED_TERMINAL_CONNECTOR"]
    inferred = totals[INFERRED]
    geodesic = sum(GEOD.line_length(*zip(*r["wgs84"])) for r in records)
    return dict(length_m=native + derived + inferred, length_wgs84_geodesic_m=geodesic,
                native_m=native, derived_m=derived, inferred_m=inferred,
                cost_m=sum(r["cost_m"] for r in records), end_wgs84=graph.nodes[target]["wgs84"], edges=records,
                inferred_edges_used=[r["id"] for r in records if r["kind"] == INFERRED])


def solve_variant(observed, local, method, candidates, anchor_counts):
    variant = method
    graph = observed.graph.copy()
    target = str(local.target["id"])
    origin = str(observed.task["origin"])
    direct = method == "I1"
    strict = method in {"I0", "ABL-I"}
    selected = candidates[:1] if direct else candidates
    decisions = []
    if not strict:
        paths = ({c["id"]: ([c["xy"], tuple(local.end.coords[0])], None) for c in selected}
                 if direct else local.paths(selected))
        decisions = [decide(observed, local, c, *paths[c["id"]], ignore_context=method == "ABL-C") for c in selected]
    passing = {d["id"]: d for d in decisions if d["status"] == INFERRED}
    admitted = [c for c in selected if c["id"] in passing]
    placements = admitted
    if candidates and (target not in graph or not nx.has_path(graph, origin, target)):
        # For strict/failure diagnostic compare nearest reachable observation with the exact goal.
        placements = list({c["id"]: c for c in [*admitted, candidates[0]]}.values())
    replace_splits(graph, placements)
    if admitted and target not in graph:
        xy = points(local.target["xy"])
        wgs = points(local.target["wgs84"]) if local.target.get("wgs84") is not None else INVERSE(*xy)
        graph.add_node(target, xy=xy, wgs84=wgs, tags=local.target.get("tags", {}))
    if target in graph and math.dist(graph.nodes[target]["xy"], points(local.target["xy"])) > EPS:
        raise ValueError("Observed target coordinate changed")
    for c in admitted:
        d = passing[c["id"]]
        graph.add_edge(c["node"] or c["id"], target, id=f"inferred/{c['id']}", source_id=c["source_id"],
                       kind=INFERRED, tags={}, hypothesis=True, xy=d["candidate_xy"],
                       length_m=d["length_m"], cost_m=d["cost_m"])
    route = compute_route(graph, origin, target)
    residual_m = 0.0 if route is not None else None
    reached = route is not None
    if not reached and candidates:
        nearest = candidates[0]
        route = compute_route(graph, origin, nearest["node"] or nearest["id"])
        if route is not None:
            residual_m = nearest["gap_m"]
    selected_ids = {edge for edge in route["inferred_edges_used"]} if reached else set()
    for d in decisions:
        d["route_selected"] = f"inferred/{d['id']}" in selected_ids
    entrance = local.target.get("tags", {}).get("entrance")
    status = ("INFERRED_CONDITIONAL_EXTERIOR_REACH" if selected_ids else "STRICT_REACH") if reached else (
        "APPROACH_WITH_GAP" if route else "NO_ROUTE")
    return dict(variant=variant, status=status, reached_original_target=reached, residual_m=residual_m,
                route=route, candidate_counts=anchor_counts, candidates=decisions,
                admitted_edges=len(admitted), used_inferred_edges=len(selected_ids),
                graph={"nodes": graph.number_of_nodes(), "directed_edges": graph.number_of_edges(),
                       "weak_components": nx.number_weakly_connected_components(graph)},
                entrance_role=entrance, inbound_eligibility="NOT_ELIGIBLE_EXIT" if entrance == "exit" else "NOT_EVALUATED",
                field_validation="NOT_VERIFIED")


def run_observed(task, config, methods=("I0", "I1", "I2", "ABL-I", "ABL-C")):
    observed = Observation.parse(task)
    local = LocalDomain(observed, config)
    anchors, counts = anchors_for(observed, local)
    return dict(task_id=task["task_id"], kind=task["kind"], crs="EPSG:32651", window=mapping(local.window),
                domain=mapping(local.domain), target=dict(local.target), candidates_generated=len(anchors),
                source_graph={"nodes": observed.graph.number_of_nodes(), "directed_edges": observed.graph.number_of_edges(),
                              "weak_components": nx.number_weakly_connected_components(observed.graph)},
                methods={m: solve_variant(observed, local, m, anchors, counts) for m in methods})
