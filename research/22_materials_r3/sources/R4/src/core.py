"""Source-neutral edge gating and native-topology routing."""
from dataclasses import dataclass

import networkx as nx
from pyproj import Geod
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

GEOD = Geod(ellps="WGS84")
REQUIRED_FIELDS = (
    "open_space_geometry", "native_pedestrian_geometry", "native_node_topology", "obstacle_geometry"
)


def capability(fields):
    missing = [key for key in REQUIRED_FIELDS if fields.get(key) != "AVAILABLE"]
    return {
        "status": "NOT_EXECUTABLE_MISSING_INPUT" if missing else "EXECUTABLE",
        "missing": missing,
    }


def distance(a, b):
    return GEOD.inv(*a, *b)[2]


def route_length(points):
    return sum(distance(a, b) for a, b in zip(points, points[1:]))


@dataclass(frozen=True)
class LinearEvidence:
    native_id: str
    index: int
    a: tuple
    b: tuple
    start: tuple
    end: tuple
    directions: tuple
    tags: dict
    geometry_m: object
    unsupported_reason: str | None = None

    @property
    def source_key(self):
        return self.native_id, self.index

    @property
    def native_geometry(self):
        return {"type": "LineString", "coordinates": [self.start, self.end]}


class Obstacles:
    def __init__(self, objects):
        self.objects = objects
        self.tree = STRtree([item[2] for item in objects])

    def hits(self, line):
        matches = []
        endpoint_band = Point(line.coords[0]).buffer(.01).union(Point(line.coords[-1]).buffer(.01))
        for i in self.tree.query(line, predicate="intersects"):
            native_id, kind, geometry = self.objects[i]
            overlap = line.intersection(geometry)
            if kind in {"FENCE_WALL", "RESTRICTED_NODE"}:
                if not overlap.is_empty:
                    matches.append(native_id)
            elif (overlap.difference(endpoint_band).length > 1e-6
                  or not line.relate_pattern(geometry, "F********")):
                # Interior overlap blocks even if shorter than the boundary-overlap tolerance.
                matches.append(native_id)
        return sorted(set(matches))


def add_supported_edges(graph, anchors, entrances, spaces, lines, obstacles, tolerance, minimum_length):
    """Validate source line geometry, then commit only attached native-node components."""
    records = []
    overlap_by_space = {}
    base_sources = {
        (data["native_id"], data["segment_index"])
        for _, _, data in graph.edges(data=True) if data.get("native_id")
    }
    for native_space, polygon, space_restriction in spaces:
        parts = [polygon] if polygon.geom_type == "Polygon" else polygon.geoms
        exterior = unary_union([part.exterior for part in parts])
        edge_band = exterior.buffer(tolerance)
        outer_anchors = {key for key, p in anchors.items() if exterior.distance(p) <= tolerance}
        overlap_by_space[native_space] = outer_anchors
        for line in lines:
            geom = line.geometry_m
            if not geom.intersects(edge_band) and not geom.intersects(polygon):
                continue
            variant = None
            if edge_band.covers(geom):
                variant = "B1"
            elif polygon.buffer(1e-7).covers(geom) and geom.intersection(
                polygon.buffer(-tolerance)
            ).length > minimum_length:
                variant = "B2"
            if variant is None:
                continue
            reason = line.unsupported_reason or space_restriction
            conflicts = obstacles.hits(geom)
            if not reason and conflicts:
                reason = "KNOWN_OBSTACLE_CONFLICT"
            if not reason and geom.length < minimum_length:
                reason = "DEGENERATE_SOURCE_SEGMENT"
            duplicate = line.source_key in base_sources
            if duplicate and not reason:
                reason = "ALREADY_IN_B0"
            record = {
                "space_id": native_space,
                "edge_id": f"{native_space}:{line.native_id}:{line.index}",
                "way_id": line.native_id,
                "segment_index": line.index,
                "start_node": f"node/{line.a[0]}",
                "end_node": f"node/{line.b[0]}",
                "variant": variant,
                "status": "ALREADY_IN_B0" if reason == "ALREADY_IN_B0" else (
                    "REJECTED" if reason else "PROPOSED"
                ),
                "reason": reason,
                "evidence": "EXPLICIT_NATIVE_WALK_LINE",
                "geometry_check": "PASS" if not conflicts and not line.unsupported_reason and not space_restriction else "FAIL",
                "topology_check": "OBSERVED_IN_B0" if duplicate else "NOT_EVALUATED",
                "obstacle_ids": conflicts,
                "length_m": route_length((line.start, line.end)),
                "boundary_distance_m": max(exterior.distance(geom.interpolate(t, normalized=True))
                                           for t in (0, .25, .5, .75, 1)) if variant == "B1" else None,
                "closest_boundary_distance_m": geom.distance(exterior),
                "geometry": line.native_geometry,
                "original_tags": line.tags,
                "_line": line,
            }
            records.append(record)
    def attach(prior, variant):
        result = prior.copy()
        verified = []
        for space_id, exterior_nodes in overlap_by_space.items():
            eligible_rows = [
                row for row in records if row["space_id"] == space_id
                and (row["variant"] == variant or variant == "B2" and row["variant"] == "B1")
                and row["status"] in {"ALREADY_IN_B0", "ALREADY_IN_OTHER_FOCUS", "PROPOSED", "VERIFIED"}
            ]
            evidence_graph = nx.DiGraph()
            orientations = {}
            for row in eligible_rows:
                line = row["_line"]
                pairs = [(line.a, line.b) if d == 1 else (line.b, line.a) for d in line.directions]
                orientations[row["edge_id"]] = pairs
                for a, b in pairs:
                    evidence_graph.add_edge(a, b, length_m=row["length_m"])
            directed_connections = {}
            for origin in sorted(exterior_nodes & evidence_graph.nodes):
                _, paths = nx.single_source_dijkstra(evidence_graph, origin, weight="length_m")
                for target in sorted((exterior_nodes | entrances) - {origin}):
                    if target not in paths:
                        continue
                    for pair in zip(paths[target], paths[target][1:]):
                        directed_connections.setdefault(pair, (origin, target))
            for row in eligible_rows:
                if row["variant"] != variant or row["status"] != "PROPOSED":
                    continue
                pairs = orientations[row["edge_id"]]
                proof = next((directed_connections[pair] for pair in pairs if pair in directed_connections), None)
                if proof is None:
                    row.update(status="REJECTED", reason="NO_EVIDENCE_FOR_CONNECTION",
                               topology_check="NO_DIRECTED_NATIVE_TERMINAL_CHAIN")
                    continue
                line = row["_line"]
                result.add_node(line.a, coord=line.start)
                result.add_node(line.b, coord=line.end)
                if not any(d.get("native_id") == line.native_id and d.get("segment_index") == line.index
                           for d in result.get_edge_data(*pairs[0], default={}).values()):
                    for a, b in pairs:
                        result.add_edge(a, b, native_id=line.native_id, segment_index=line.index,
                                        length_m=row["length_m"], evidence="EXPLICIT_NATIVE_WALK_LINE",
                                        r4_edge_id=row["edge_id"])
                    row.update(status="VERIFIED", reason="SOURCE_LINE_AND_EXACT_NATIVE_ATTACHMENTS",
                               topology_check="EXACT_DIRECTED_TERMINAL_CHAIN",
                               attachment_nodes=[f"node/{key[0]}" for key in proof])
                    verified.append(row)
                else:
                    row.update(status="ALREADY_IN_OTHER_FOCUS", reason="DEDUPLICATED_NATIVE_SEGMENT",
                               topology_check="OBSERVED_IN_ENHANCEMENT")
        return result, verified

    b1, added_b1 = attach(graph, "B1")
    b2, added_b2 = attach(b1, "B2")
    for row in records:
        del row["_line"]
    return b1, b2, records, added_b1, added_b2


def graph_stats(graph):
    components = list(nx.weakly_connected_components(graph))
    return {
        "nodes": graph.number_of_nodes(),
        "directed_edges": graph.number_of_edges(),
        "weak_components": len(components),
        "largest_weak_component": max(map(len, components), default=0),
    }


def entrance_route(graph, start_key, entrance_key, entry, obstacle_index, projector):
    target = entry["coordinate"]
    base = {"target_native_id": entry["native_id"], "target": target, "geometry": None,
            "route_end": None, "length_m": None, "target_gap_m": None,
            "obstacle_ids": [], "used_added_edge_ids": [], "source_way_ids": []}
    if start_key not in graph:
        return {**base, "status": "NO_ROUTE", "failure_reason": "FROZEN_ORIGIN_NOT_IN_GRAPH"}
    if entrance_key not in graph:
        return {**base, "status": "NO_ROUTE", "failure_reason": "NO_NATIVE_ENTRY_GRAPH_NODE"}
    if distance(graph.nodes[entrance_key]["coord"], target) > 1e-6:
        return {**base, "status": "NO_ROUTE", "failure_reason": "NATIVE_ENTRY_COORDINATE_MISMATCH"}
    try:
        path = nx.shortest_path(graph, start_key, entrance_key, weight="length_m", method="dijkstra")
    except nx.NetworkXNoPath:
        return {**base, "status": "NO_ROUTE", "failure_reason": "NO_DIRECTED_PATH_TO_NATIVE_ENTRY"}
    coordinates = [graph.nodes[key]["coord"] for key in path]
    if len(coordinates) < 2 or route_length(coordinates) <= 1e-8:
        return {**base, "status": "NO_ROUTE", "failure_reason": "ZERO_LENGTH"}
    selected = [min(graph[a][b].values(), key=lambda row: (
        row["length_m"], str(row.get("native_id") or ""), str(row.get("r4_edge_id") or "")
    )) for a, b in zip(path, path[1:])]
    projected = LineString([projector(*point) for point in coordinates])
    conflicts = obstacle_index.hits(projected)
    return {**base, "status": "MAPPED_ENTRY_REACHED_WITH_PLANAR_CONFLICT" if conflicts else "MAPPED_ENTRY_REACHED",
            "failure_reason": "PLANAR_OBSTACLE_REVIEW" if conflicts else None,
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "route_end": coordinates[-1], "length_m": route_length(coordinates),
            "target_gap_m": distance(coordinates[-1], target),
            "obstacle_ids": conflicts,
            "used_added_edge_ids": [row["r4_edge_id"] for row in selected if "r4_edge_id" in row],
            "source_way_ids": list(dict.fromkeys(row["native_id"] for row in selected if row.get("native_id")))}


def select_entrance(routes):
    if len(routes) < 2:
        return {"status": "NOT_APPLICABLE_LT2_ELIGIBLE_REGISTERED_ENTRANCES", "selected": None}
    valid = [r for r in routes if r["status"] == "MAPPED_ENTRY_REACHED"]
    selected = min(valid, key=lambda r: (r["length_m"], r["target_native_id"]), default=None)
    return {"status": "SELECTED_SHORTEST_VALID" if selected else "NO_VALID_ROUTE", "selected": selected}
