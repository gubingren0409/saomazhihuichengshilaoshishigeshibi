"""Measured route and endpoint diagnostics without modifying original network weights."""
from collections import defaultdict
from itertools import pairwise
import math

import networkx as nx
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

from .native_adapter import GEOD, INVERSE, PROJECT, ground, node_number

NATIVE = "NATIVE_LINEAR"
DERIVED = "DERIVED_FROM_TAGGED_PEDESTRIAN_AREA"
TERMINAL = "DERIVED_TERMINAL_CONNECTOR"
GAP = "GAP_DIAGNOSTIC_NOT_ROUTABLE"


def key(value):
    return (node_number(value), "0", "0") if value.startswith("node/") else value


def geo_length(coordinates):
    if len(coordinates) < 2:
        return 0.0
    return GEOD.line_length(*zip(*coordinates))


def prepare_weights(graph):
    for _, attrs in graph.nodes(data=True):
        attrs["xy"] = PROJECT(*attrs["coord"])
    for a, b, attrs in graph.edges(data=True):
        attrs["route_weight_m"] = math.dist(graph.nodes[a]["xy"], graph.nodes[b]["xy"])
        attrs["kind"] = NATIVE


def area_graph(source, model):
    result = nx.MultiDiGraph()
    for ident, xy in model["nodes"].items():
        coord = source.coord(ident) if ident.startswith("node/") else INVERSE(*xy)
        result.add_node(key(ident), xy=xy, coord=coord)
    for row in model["edges"]:
        a, b = key(row["u"]), key(row["v"])
        attrs = dict(kind=row["kind"], route_weight_m=row["length_m"], edge_id=row["edge_id"],
                     source_area_id=row["source_area_id"], native_port_id=row.get("native_port_id"))
        result.add_edge(a, b, **attrs)
        if row.get("direction") == "BIDIRECTIONAL":
            result.add_edge(b, a, **attrs)
    return result


def overlay(base, graphs):
    augmented = base.copy()
    for graph in graphs:
        for n, attrs in graph.nodes(data=True):
            if n not in augmented:
                augmented.add_node(n, **attrs)
            elif math.dist(augmented.nodes[n]["xy"], attrs["xy"]) > 0.000001:
                raise ValueError(f"Coordinate changed at topology merge: {n}")
        augmented.add_edges_from(graph.edges(data=True))
    return augmented


def statistics(graph, origin):
    components = list(nx.weakly_connected_components(graph))
    return dict(nodes=graph.number_of_nodes(), directed_edges=graph.number_of_edges(),
                weak_components=len(components),
                largest_weak_component=max(map(len, components), default=0),
                reachable_nodes=len(nx.descendants(graph, origin)) + 1 if origin in graph else 0)


def walk(graph, start, end, weight="route_weight_m"):
    if start not in graph or end not in graph:
        return None
    try:
        path = nx.shortest_path(graph, start, end, weight=weight, method="dijkstra")
    except nx.NetworkXNoPath:
        return None
    rows = []
    for a, b in pairwise(path):
        candidates = graph[a][b].values()
        row = min(candidates, key=lambda e: (e[weight], e.get("edge_id", ""), e.get("osm_way_id") or -1))
        rows.append(dict(row, a=tuple(graph.nodes[a]["coord"]), b=tuple(graph.nodes[b]["coord"]),
                         a_xy=tuple(graph.nodes[a]["xy"]), b_xy=tuple(graph.nodes[b]["xy"])))
    return rows


def obstacle_index(obstacles):
    return obstacles, STRtree([o["geometry"] for o in obstacles])


def path_conflicts(rows, index, target, building_id):
    obstacles, tree = index
    conflicts = defaultdict(set)
    for row in rows:
        line = LineString([row["a_xy"], row["b_xy"]])
        if line.length == 0:
            continue
        is_final = row["b"] == tuple(target)
        for i in tree.query(line, predicate="intersects"):
            obj = obstacles[i]
            geom = obj["geometry"]
            overlap = line.intersection(geom)
            if obj["kind"] in ("BUILDING", "AREA", "UNKNOWN"):
                # A source path may share a mapped area boundary. Flag planar interior crossings.
                if not line.relate_pattern(geom, "F********"):
                    conflicts[row["kind"]].add(obj["id"])
                elif obj["kind"] == "BUILDING" and obj["id"] == building_id and is_final:
                    # The accepted terminal rule is already checked segment-by-segment in the area engine.
                    continue
            elif not overlap.is_empty:
                if any(overlap.difference(Point(gate["xy"]).buffer(1e-7)).is_empty for gate in obj["gates"]):
                    continue
                conflicts[row["kind"]].add(obj["id"])
    return {k: sorted(v) for k, v in conflicts.items()}


def feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def line_feature(points, **properties):
    return feature({"type": "LineString", "coordinates": points}, **properties)


def describe(rows, target, route_id, scene_id, run_id, target_id, features, index,
             building_id, contact_id=None, forced_status=None):
    if rows is None or not rows:
        return dict(status="NO_ROUTE", route_id=route_id, entrance_id=target_id,
                    contact_id=contact_id, original_coordinate=target, endpoint=None,
                    gap_m=None, gap_geodesic_m=None, length_m=None, length_geodesic_m=None,
                    section_lengths_m={}, route_sections=[], obstacle_conflicts={}, continuous=False)
    current = None
    groups = []
    lengths = defaultdict(float)
    total_coords = [rows[0]["a"]]
    for row in rows:
        if total_coords[-1] != row["a"]:
            raise ValueError(f"Non-continuous measured route: {route_id}")
        total_coords.append(row["b"])
        if row["a"] == row["b"]:
            continue
        group_key = (row["kind"], row.get("source_area_id"))
        if current != group_key:
            current = group_key
            groups.append(dict(kind=row["kind"], source_area_id=row.get("source_area_id"),
                               length_m=0.0, points=[row["a"]], source_edges=[]))
        group = groups[-1]
        group["points"].append(row["b"])
        group["length_m"] += row["route_weight_m"]
        group["source_edges"].append(row.get("edge_id") or f"way/{row.get('osm_way_id')}/{row.get('segment_index')}")
        lengths[row["kind"]] += row["route_weight_m"]
    if not groups:
        raise ValueError(f"Zero length route marked as traversed: {route_id}")
    obstacle_conflicts = path_conflicts(rows, index, target, building_id)
    end = total_coords[-1]
    gap = math.dist(PROJECT(*end), PROJECT(*target))
    geodesic_gap = GEOD.inv(*end, *target)[2]
    status = forced_status or ("EXTERIOR_REACHED_CONDITIONAL" if gap <= 0.000001 else "APPROACH_WITH_GAP")
    if obstacle_conflicts and not forced_status:
        status = "PLANAR_CONFLICT_ROUTE_REQUIRES_REVIEW"
    section_ids = []
    for i, group in enumerate(groups):
        sid = f"{route_id}/{i}"
        section_ids.append(sid)
        features.append(line_feature(group["points"], run_id=run_id, scene_id=scene_id, route_id=route_id,
                                     route_section=i, id=sid, kind=group["kind"], source_area_id=group["source_area_id"],
                                     entrance_id=target_id, contact_id=contact_id, source_edges=group["source_edges"],
                                     status=status, length_m=group["length_m"]))
    return dict(status=status, route_id=route_id, entrance_id=target_id, contact_id=contact_id,
                original_coordinate=target, endpoint=end, origin=total_coords[0], gap_m=gap,
                gap_geodesic_m=geodesic_gap, length_m=sum(lengths.values()),
                length_geodesic_m=geo_length(total_coords), section_lengths_m=dict(lengths),
                route_sections=section_ids, obstacle_conflicts=obstacle_conflicts, continuous=True)


def closest_reachable(graph, source, origin, target, area_id):
    """Nearest point on a reachable directed ground segment, for diagnosis only."""
    if origin not in graph:
        return None
    goal = Point(PROJECT(*target))
    distances = nx.single_source_dijkstra_path_length(graph, origin, weight="route_weight_m")
    best = None
    for a, b, row in graph.edges(data=True):
        if a not in distances or row["route_weight_m"] <= 0:
            continue
        if row["kind"] == NATIVE:
            way = row.get("osm_way_id")
            if way is None or a[1:] != ("0", "0") or b[1:] != ("0", "0") or not ground(source.ways[way].get("tags", {})):
                continue
        elif row.get("source_area_id") != area_id or row["kind"] == TERMINAL:
            continue
        line = LineString([graph.nodes[a]["xy"], graph.nodes[b]["xy"]])
        at = nearest_points(goal, line)[1]
        distance_along = line.project(at)
        ranking = (at.distance(goal), distances[a] + distance_along, str(a), str(b), str(row.get("osm_way_id") or row.get("edge_id")))
        if best is None or ranking < best[0]:
            best = ranking, a, b, row, at, distance_along
    if best is None:
        return None
    _, a, b, row, at, distance_along = best
    prefix = walk(graph, origin, a)
    if distance_along < 1e-7:
        return prefix, graph.nodes[a]["coord"], row
    at_coords = tuple(at.coords[0])
    coord = graph.nodes[b]["coord"] if abs(distance_along - row["route_weight_m"]) < 1e-7 else INVERSE(*at_coords)
    prefix.append(dict(row, a=tuple(graph.nodes[a]["coord"]), b=tuple(coord),
                       a_xy=tuple(graph.nodes[a]["xy"]), b_xy=at_coords, route_weight_m=distance_along))
    return prefix, coord, row


def gap_evidence(source, target, endpoint, area_id, supported_areas, native_lines, obstacles):
    line = LineString([PROJECT(*endpoint), PROJECT(*target)])
    relevant = [(ident, geom) for ident, geom in [*supported_areas, *native_lines] if geom.intersects(line)]
    coverage = unary_union([geom.intersection(line) for _, geom in relevant]).length
    rows = []
    for obj in obstacles:
        geom = obj["geometry"]
        if geom.intersects(line):
            rows.append(dict(native_id=obj["id"], kind=obj["kind"],
                             inside_length_m=line.intersection(geom).length,
                             source_tags=obj["tags"], building_boundary_contact_only=(
                                 obj["kind"] == "BUILDING" and line.relate_pattern(geom, "F********"))))
    return dict(kind=GAP, status="GAP_UNSUPPORTED", routable=False,
                geometry_metric=list(line.coords), source_area_id=area_id,
                length_m=line.length, supported_length_m=coverage,
                unsupported_length_m=max(0.0, line.length - coverage),
                supported_source_ids=[ident for ident, _ in relevant], intersected_obstacles=rows,
                level_status="UNKNOWN_OUTSIDE_MAPPED_SUPPORT")
