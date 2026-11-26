"""Offline OSM pedestrian routing using NetworkX and native node topology."""

from dataclasses import dataclass
from itertools import combinations
from math import isfinite

import networkx as nx
from pyproj import Geod, Transformer

PROFILE = "OSM_PEDESTRIAN_CONSERVATIVE_V1"
GEOD = Geod(ellps="WGS84")
PUBLIC = {"yes", "designated", "permissive", "official"}
RESTRICTED = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry"}
DEDICATED = {"footway", "pedestrian", "path", "steps"}
SHARED = {"living_street", "residential", "unclassified", "service"}
MAJOR = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
OPTIONAL = {"track", "cycleway", "bridleway", "corridor"}
SIDEWALK = {"yes", "both", "left", "right"}
OPEN_BARRIERS = {"no", "bollard", "block", "cycle_barrier", "cattle_grid", "kerb", "entrance"}
CONDITIONAL = {"access:conditional", "foot:conditional", "oneway:foot:conditional",
               "foot:forward:conditional", "foot:backward:conditional"}


@dataclass(frozen=True)
class Segment:
    way: int
    index: int
    a: tuple
    b: tuple
    p: tuple
    q: tuple
    directions: tuple
    evidence: str
    bridge: str | None
    tunnel: str | None

    @property
    def key(self):
        return self.way, self.index


def _point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(x) not in (int, float) or not isfinite(x) for x in value)
            or abs(value[0]) > 180 or abs(value[1]) > 90):
        raise ValueError("expected a finite WGS84 [longitude, latitude] pair")
    return tuple(map(float, value))


def length_m(points):
    """Ellipsoidal WGS84 length, in metres."""
    if len(points) < 2:
        return 0.0
    lng, lat = zip(*points)
    return GEOD.line_length(lng, lat)


def _evidence(tags):
    highway = tags.get("highway")
    foot = tags.get("foot")
    if (tags.get("area") == "yes" or tags.get("indoor") not in (None, "no")
            or tags.get("ford") not in (None, "no")
            or CONDITIONAL.intersection(tags)
            or (foot is not None and foot not in PUBLIC)
            or (foot is None and tags.get("access") in RESTRICTED)):
        return None
    if highway in DEDICATED:
        return "MAPPED_PEDESTRIAN_WAY"
    if highway not in SHARED | MAJOR | OPTIONAL:
        return None
    if foot in PUBLIC:
        return "EXPLICIT_FOOT_ON_WAY_AXIS"
    if highway in SHARED | MAJOR and (
        tags.get("sidewalk") in SIDEWALK
        or any(tags.get("sidewalk:" + side) in SIDEWALK for side in ("left", "right", "both"))
    ):
        return "SIDEWALK_TAG_WAY_AXIS"
    if highway in SHARED and tags.get("sidewalk") not in {"separate", "no"}:
        return "SHARED_STREET_ASSUMPTION"
    return None


def _directions(tags):
    oneway = tags.get("oneway:foot")
    if oneway is None and tags.get("highway") in {"footway", "path", "steps"}:
        oneway = tags.get("oneway")
    if oneway not in {None, "no", "false", "0", "yes", "true", "1", "-1", "reverse"}:
        return ()
    forward = oneway not in {"-1", "reverse"} and tags.get("foot:forward", "yes") in PUBLIC
    backward = oneway not in {"yes", "true", "1"} and tags.get("foot:backward", "yes") in PUBLIC
    return tuple(direction for direction, allowed in ((1, forward), (-1, backward)) if allowed)


def _allowed_node(tags):
    foot = tags.get("foot")
    if (tags.get("locked") == "yes" or CONDITIONAL.intersection(tags)
            or (foot is not None and foot not in PUBLIC)
            or (foot is None and tags.get("access") in RESTRICTED)):
        return False
    return tags.get("barrier", "no") in OPEN_BARRIERS or foot in PUBLIC


def _segments(data):
    elements = data["elements"]
    bounds = data.get("bounds_wsen")
    if bounds is not None:
        west, south, east, north = bounds
    nodes = {}
    for row in elements:
        if row["type"] == "node":
            try:
                pos = _point((row.get("lon"), row.get("lat")))
            except ValueError:
                continue
            nodes[row["id"]] = pos, _allowed_node(row.get("tags", {}))
    segments, endings = [], {}
    counts = {"eligible_ways": 0, "eligible_segments": 0, "missing_node_segments": 0,
              "blocked_node_segments": 0, "outside_snapshot_segments": 0}
    for way in sorted((row for row in elements if row["type"] == "way"), key=lambda row: row["id"]):
        tags = way.get("tags", {})
        evidence, directions = _evidence(tags), _directions(tags)
        if evidence is None or not directions:
            continue
        ids = way["nodes"]
        bridge, tunnel = tags.get("bridge"), tags.get("tunnel")
        default_layer = "1" if bridge not in (None, "no") else "-1" if tunnel not in (None, "no") else "0"
        layer, level = tags.get("layer", default_layer), tags.get("level", "0")
        first = len(segments)
        for index, (u, v) in enumerate(zip(ids, ids[1:])):
            if u not in nodes or v not in nodes:
                counts["missing_node_segments"] += 1
                continue
            p, allowed_p = nodes[u]
            q, allowed_q = nodes[v]
            if bounds is not None and not all(west <= x <= east and south <= y <= north for x, y in (p, q)):
                counts["outside_snapshot_segments"] += 1
                continue
            if not allowed_p or not allowed_q:
                counts["blocked_node_segments"] += 1
                continue
            if u == v or p == q:
                continue
            a, b = (u, layer, level), (v, layer, level)
            segments.append(Segment(way["id"], index, a, b, p, q, directions, evidence, bridge, tunnel))
            if index == 0:
                endings.setdefault(u, set()).add(a)
            if index == len(ids) - 2:
                endings.setdefault(v, set()).add(b)
        counts["eligible_ways"] += len(segments) > first
    counts["eligible_segments"] = len(segments)
    return segments, endings, counts


def _snap(point, segments):
    # Local azimuthal equidistant metres avoid comparing latitude and longitude degrees.
    project = Transformer.from_crs("EPSG:4326",
                                   f"+proj=aeqd +lat_0={point[1]} +lon_0={point[0]} +ellps=WGS84",
                                   always_xy=True).transform
    best = None
    for seg in segments:
        x0, y0 = project(*seg.p)
        x1, y1 = project(*seg.q)
        dx, dy = x1 - x0, y1 - y0
        denom = dx * dx + dy * dy
        frac = max(0.0, min(1.0, -(x0 * dx + y0 * dy) / denom)) if denom else 0.0
        if frac <= 1e-9:
            frac, pos = 0.0, seg.p
        elif frac >= 1 - 1e-9:
            frac, pos = 1.0, seg.q
        else:
            bearing, _, meters = GEOD.inv(*seg.p, *seg.q)
            pos = GEOD.fwd(*seg.p, bearing, meters * frac)[:2]
        meters = GEOD.inv(*point, *pos)[2]
        ordering = (meters, seg.way, seg.index)
        if best is None or ordering < best[0]:
            best = ordering, seg, frac, pos
    _, seg, frac, pos = best
    return seg, frac, pos, GEOD.inv(*point, *pos)[2]


def _build_graph(segments, endings, snaps):
    graph = nx.MultiDiGraph()
    interior = {}
    snap_keys = []
    for seg, frac, pos, _ in snaps:
        if frac == 0:
            snap_keys.append(seg.a)
        elif frac == 1:
            snap_keys.append(seg.b)
        else:
            key = ("edge_snap", seg.way, seg.index, frac)
            snap_keys.append(key)
            interior.setdefault(seg.key, {})[key] = (frac, pos)
    for seg in segments:
        cuts = [(seg.a, (0.0, seg.p)), *sorted(interior.get(seg.key, {}).items(), key=lambda x: x[1][0]),
                (seg.b, (1.0, seg.q))]
        for (a, (_, p)), (b, (_, q)) in zip(cuts, cuts[1:]):
            graph.add_node(a, coord=p)
            graph.add_node(b, coord=q)
            metadata = {"length_m": length_m((p, q)), "osm_way_id": seg.way, "segment_index": seg.index,
                        "osm_source_node_ids": [seg.a[0], seg.b[0]], "evidence": seg.evidence,
                        "layer": seg.a[1], "level": seg.a[2], "bridge": seg.bridge, "tunnel": seg.tunnel}
            for direction in seg.directions:
                u, v = (a, b) if direction == 1 else (b, a)
                graph.add_edge(u, v, **metadata)
    for source_node, keys in sorted(endings.items()):
        for a, b in combinations(sorted(keys), 2):
            # Allow an explicit same-level shared way endpoint across layer tags.
            # No edge is formed from a 2D intersection or an interior grade-separated node.
            if a[2] == b[2]:
                attrs = {"length_m": 0.0, "osm_way_id": None, "source_node_transition": source_node,
                         "evidence": "NATIVE_SHARED_WAY_ENDPOINT"}
                graph.add_edge(a, b, **attrs)
                graph.add_edge(b, a, **attrs)
    return graph, snap_keys


def _snap_metadata(snap):
    seg, frac, pos, distance = snap
    return {"way_id": seg.way, "source_node_ids": [seg.a[0], seg.b[0]], "segment_index": seg.index,
            "fraction": frac, "position": list(pos), "distance_m": distance, "evidence": seg.evidence}


def route_osm(data, start, target, max_snap_m=35):
    """Route between independent nearest bounded projections; leave snap gaps untraversed."""
    start, target = _point(start), _point(target)
    if type(max_snap_m) not in (int, float) or not isfinite(max_snap_m) or max_snap_m <= 0:
        raise ValueError("max_snap_m must be finite and positive")
    segments, endings, counts = _segments(data)
    out = {"status": "NO_ROUTE", "geometry": None, "failure_reason": "NO_ELIGIBLE_EDGES",
           "requested_start": list(start), "requested_target": list(target),
           "route_start": None, "route_end": None, "snap_start_m": None, "snap_end_m": None,
           "length_m": None, "node_ids": [], "way_ids": [], "segments": [],
           "profile": PROFILE, "engine": f"NetworkX {nx.__version__} Dijkstra",
           "graph_stats": counts, "max_snap_m": max_snap_m}
    if not segments:
        return out
    start_snap, end_snap = _snap(start, segments), _snap(target, segments)
    out.update(snap_start=_snap_metadata(start_snap), snap_end=_snap_metadata(end_snap),
               snap_start_m=start_snap[3], snap_end_m=end_snap[3])
    if start_snap[3] > max_snap_m or end_snap[3] > max_snap_m:
        out["failure_reason"] = ("BOTH_SNAPS_OUTSIDE_LIMIT" if min(start_snap[3], end_snap[3]) > max_snap_m
                                 else "START_SNAP_OUTSIDE_LIMIT" if start_snap[3] > max_snap_m
                                 else "TARGET_SNAP_OUTSIDE_LIMIT")
        return out
    graph, (a, b) = _build_graph(segments, endings, (start_snap, end_snap))
    counts.update(graph_nodes=graph.number_of_nodes(), graph_directed_edges=graph.number_of_edges())
    try:
        path = nx.shortest_path(graph, a, b, weight="length_m", method="dijkstra")
    except nx.NetworkXNoPath:
        out["failure_reason"] = "NO_DIRECTED_PATH_BETWEEN_NEAREST_SNAPS"
        return out
    geometry, used = [], []
    for key in path:
        pos = list(graph.nodes[key]["coord"])
        if not geometry or geometry[-1] != pos:
            geometry.append(pos)
    if len(geometry) < 2:
        out["failure_reason"] = "ZERO_LENGTH"
        return out
    for u, v in zip(path, path[1:]):
        edge = min(graph[u][v].values(), key=lambda x: (x["length_m"], x["osm_way_id"] or -1))
        used.append(dict(edge, start=list(graph.nodes[u]["coord"]), end=list(graph.nodes[v]["coord"])))
    node_ids = []
    for key in path:
        if isinstance(key[0], int) and (not node_ids or node_ids[-1] != key[0]):
            node_ids.append(key[0])
    out.update(status="PASS", failure_reason=None,
               geometry={"type": "LineString", "coordinates": geometry},
               route_start=geometry[0], route_end=geometry[-1], length_m=length_m(geometry),
               node_ids=node_ids, way_ids=list(dict.fromkeys(
                   edge["osm_way_id"] for edge in used if edge["osm_way_id"] is not None)), segments=used)
    return out

