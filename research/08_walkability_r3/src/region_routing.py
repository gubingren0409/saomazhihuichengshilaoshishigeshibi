"""Attach a frozen surface to the observed walk graph and then answer queries."""
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
import math

import networkx as nx
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

from src.region import INFERRED, NATIVE, RESTRICTED, UNKNOWN, access_conflict, edge_source, non_ground

EPS = 1e-6


def parts(geom):
    if geom.geom_type == "LineString":
        if geom.length > EPS:
            yield geom
    else:
        for child in getattr(geom, "geoms", []):
            yield from parts(child)


def coords(point):
    return tuple(point.coords[0])


def add_edge(graph, u, v, segments):
    cost = sum(s["cost_m"] for s in segments)
    if not graph.has_edge(u, v) or graph[u][v]["cost"] > cost:
        graph.add_edge(u, v, cost=cost, segments=segments)


def segment(xy, layer, source, cost_multiplier=1, fixed=0, **extra):
    length = math.dist(xy[0], xy[-1])
    return dict(xy=[list(p) for p in xy], layer=layer, source_id=source,
                length_m=length, cost_m=length*cost_multiplier+fixed, **extra)


def native_graph(observed):
    graph = nx.DiGraph()
    graph.add_nodes_from((row["id"], {"xy": tuple(row["xy"]), "tags": row.get("tags", {})}) for row in observed["nodes"])
    for row in observed["edges"]:
        u, v = row["u"], row["v"]
        a, b = graph.nodes[u]["xy"], graph.nodes[v]["xy"]
        if u == v or any(access_conflict(tags) for tags in (row.get("tags", {}), graph.nodes[u]["tags"], graph.nodes[v]["tags"])):
            continue
        layer = "derived" if row["kind"].startswith("DERIVED") else "native"
        add_edge(graph, u, v, [segment([a, b], layer, edge_source(row), edge_id=row["id"],
                                      tags=row.get("tags", {}), geometry_kind=row["kind"])])
    return graph


@dataclass
class RegionGraph:
    internal: object
    interfaces: list
    active: object
    points: list
    index: object
    surface: object
    stats: dict


def surface_parts(surface, line, cfg, budget=0, label=None):
    """The whole geometry is checked and split by surface evidence, not just its endpoints."""
    if line.length <= EPS:
        return []
    if (line.intersection(surface.masks[RESTRICTED]).length > EPS or
            line.difference(surface.domain).length > EPS):
        return None
    breaks = {0., line.length}
    for state in (NATIVE, INFERRED, UNKNOWN):
        for piece in parts(line.intersection(surface.masks[state])):
            breaks.update(line.project(Point(p)) for p in (piece.coords[0], piece.coords[-1]))
    result = []
    penalty_paid = False
    for a,b in zip(sorted(breaks), sorted(breaks)[1:]):
        if b-a <= EPS:
            continue
        mid = line.interpolate((a+b)/2)
        first, last = coords(line.interpolate(a)), coords(line.interpolate(b))
        if surface.masks[NATIVE].covers(mid):
            s = segment([first,last], "derived", label, geometry_kind="NEW_GRID_WITHIN_MAPPED_FACE")
        elif surface.masks[INFERRED].covers(mid):
            s = segment([first,last], "inferred", label, cfg["inference_cost_multiplier"],
                        geometry_kind="FROZEN_INFERRED_REGION", level="UNKNOWN_LOCAL_OUTDOOR_ASSUMPTION")
        elif surface.masks[UNKNOWN].covers(mid):
            s = segment([first,last], "unknown", label, cfg["unknown_penalty_per_m"],
                        0 if penalty_paid else cfg["unknown_fixed_penalty_m"],
                        geometry_kind="BOUNDED_UNKNOWN_PORTAL", level="UNKNOWN_LOCAL_OUTDOOR_ASSUMPTION")
            penalty_paid = True
        else:
            return None
        result.append(s)
    if not result or sum(s["length_m"] for s in result if s["layer"]=="unknown") > budget + EPS:
        return None
    return result


def bidirectional(graph, u, v, measured):
    add_edge(graph,u,v,measured)
    reverse = [dict(s, xy=s["xy"][::-1]) for s in reversed(measured)]
    add_edge(graph,v,u,reverse)


def region_graph(surface, network, cfg, *, disabled=False):
    graph = nx.DiGraph()
    inferred = surface.masks[INFERRED]
    transition = inferred.buffer(cfg["cell_m"] * 2)
    rows = [c for c in surface.cells if c["walkability_state"] == INFERRED or
            (c["walkability_state"] == NATIVE and c["g"].intersects(transition))]
    points = [c["g"].representative_point() for c in rows]
    point_idx = STRtree(points)
    ij = defaultdict(list)
    for index,row in enumerate(rows):
        key = row["region_id"]
        graph.add_node(key, xy=coords(points[index]), state=row["walkability_state"])
        ij[row["ij"]].append(index)
    active = unary_union([c["g"] for c in rows])
    stats = {"active_cells": len(rows), "interface_candidates": 0, "interface_rejected":0}
    if disabled:
        return RegionGraph(nx.DiGraph(), [], active, [], STRtree([]), surface,
                           dict(stats, active_cells=0, internal_arcs=0, components=0, interface_count=0))
    for index,row in enumerate(rows):
        i,j = row["ij"]
        neighbors = [(i+1,j), (i,j+1), (i,j)]
        for key in neighbors:
            for k in ij.get(key, []):
                if key == (i,j) and k <= index:
                    continue
                if row["g"].intersection(rows[k]["g"]).length <= EPS:
                    continue
                line = LineString([points[index],points[k]])
                if line.difference(row["g"].union(rows[k]["g"])).length > EPS:
                    continue
                link = row["region_id"] + "|" + rows[k]["region_id"]
                edge = surface_parts(surface, line, cfg, label=link)
                if edge:
                    bidirectional(graph, row["region_id"], rows[k]["region_id"], edge)
    live_cells = {node for node, deg in graph.degree() if deg}
    xmin,ymin,xmax,ymax = surface.domain.bounds
    candidates = []
    for ident, n in network.nodes(data=True):
        x,y = n["xy"]
        if not (xmin<=x<=xmax and ymin<=y<=ymax) or non_ground(n["tags"]) or access_conflict(n["tags"]):
            continue
        if not network.degree(ident):
            continue
        edge_candidates = list(network.in_edges(ident, data=True)) + list(network.out_edges(ident, data=True))
        provenance = sorted({s["source_id"] for _, _, data in edge_candidates for s in data["segments"]
                             if not non_ground(s.get("tags", {})) and not access_conflict(s.get("tags", {}))})
        if not provenance:
            continue
        p = Point(x,y)
        d = inferred.distance(p)
        if d <= cfg["interface_reach_m"] and not surface.masks[RESTRICTED].contains(p):
            candidates.append((d,ident,p,provenance))
    stats["interface_candidates"] = len(candidates)
    interfaces = []
    for distance, ident, p, provenance in sorted(candidates, key=lambda row:(row[0],row[1])):
        if any(p.distance(Point(old["xy"])) < cfg["interface_separation_m"] for old in interfaces):
            continue
        accepted = None
        neighbors = sorted(point_idx.query(p, predicate="dwithin", distance=cfg["interface_reach_m"]),
                           key=lambda i: (p.distance(points[i]), rows[i]["region_id"]))
        for j in neighbors:
            node = rows[j]["region_id"]
            if node not in live_cells:
                continue
            line = LineString([p,points[j]])
            budget = cfg["unknown_portal_budget_m"] if rows[j]["walkability_state"]==INFERRED else 0
            measured = (surface_parts(surface,line,cfg,budget,label=node) if line.length > EPS else [])
            if measured is None:
                continue
            if measured and not any(s["layer"] in {"derived","inferred"} for s in measured):
                continue
            if not measured:
                measured = [segment([coords(p),coords(points[j])], "derived" if rows[j]["walkability_state"]==NATIVE else "inferred",
                                    node, geometry_kind="EXACT_REGION_PORTAL")]
            accepted = node, measured
            break
        if accepted is None:
            stats["interface_rejected"] += 1
            continue
        node, measured = accepted
        graph.add_node(ident, xy=coords(p), tags=network.nodes[ident]["tags"])
        bidirectional(graph,ident,node,measured)
        interfaces.append({"id":ident,"xy":coords(p),"source_id":provenance[0],"source_ids":provenance,
                           "cell_id":node,"distance_to_inferred_m":distance,
                           "unknown_m":sum(s["length_m"] for s in measured if s["layer"]=="unknown"),
                           "evidence":"EXISTING_NETWORK_NODE_WITH_FULLY_MEASURED_REGION_STITCH"})
        if len(interfaces) >= cfg["max_interfaces"]:
            break
    stats.update(internal_arcs=graph.number_of_edges(), components=nx.number_weakly_connected_components(graph),
                 interface_count=len(interfaces), interface_candidates_not_selected=len(candidates)-len(interfaces))
    return RegionGraph(graph,interfaces,active,[(r["region_id"],points[i],r["walkability_state"])
                             for i,r in enumerate(rows)],point_idx,surface,stats)


def route(graph, a, b):
    if a not in graph or b not in graph:
        return empty("UNAVAILABLE_ENDPOINT")
    try:
        nodes = nx.shortest_path(graph, a, b, weight="cost")
    except nx.NetworkXNoPath:
        return empty("NO_PATH")
    edges = [dict(s,u=u,v=v) for u,v in zip(nodes,nodes[1:]) for s in graph[u][v]["segments"]]
    layer_lengths = {k:sum(s["length_m"] for s in edges if s["layer"]==k)
                     for k in ("native","derived","inferred","unknown")}
    return dict(status="ROUTED" if edges else "ZERO_LENGTH", length_m=sum(layer_lengths.values()),
                cost_m=sum(e["cost_m"] for e in edges), layer_lengths=layer_lengths, edges=edges,
                reached=True, start_xy=graph.nodes[a]["xy"], end_xy=graph.nodes[b]["xy"],
                path_node_count=len(nodes))


def empty(status):
    return dict(status=status,length_m=None,cost_m=None,layer_lengths={k:0 for k in
                ("native","derived","inferred","unknown")},edges=[],reached=False)


def bind_endpoint(endpoint, region, cfg):
    ident, p = endpoint["id"], Point(endpoint["xy"])
    graph = region.internal
    if ident in graph and p.distance(Point(graph.nodes[ident]["xy"])) <= EPS:
        return ident, None
    if endpoint.get("role") not in {"REGISTERED_EXIT","REGISTERED_DOOR","CONTROL_INTERIOR_POINT"}:
        return ident, None
    if access_conflict(endpoint.get("tags",{})) or non_ground(endpoint.get("tags",{})):
        return ident, None
    neighbors = sorted(region.index.query(p,predicate="dwithin",distance=cfg["interface_reach_m"]),
                       key=lambda i:(p.distance(region.points[i][1]),region.points[i][0]))
    for i in neighbors:
        key, pt, state = region.points[i]
        if not graph.degree(key):
            continue
        line = LineString([p,pt])
        budget = cfg["unknown_portal_budget_m"] if state == INFERRED else 0
        measured = surface_parts(region.surface,line,cfg,budget,label=key) if line.length > EPS else []
        if measured is not None and (not measured or any(s["layer"] in {"inferred","derived"} for s in measured)):
            if not measured:
                measured=[segment([coords(p),coords(pt)], "inferred" if state==INFERRED else "derived",key,
                                  geometry_kind="EXACT_REGION_PORTAL")]
            return ident, (key,measured)
    return ident, None


def routed_queries(base, region, queries, cfg):
    combined = nx.compose(base,region.internal)
    outcomes = {}
    for q in queries:
        graph = region.internal if q.get("scope") == "LOCAL_REGION_ONLY" else combined
        added = []
        ids = []
        for end in (q["source"],q["target"]):
            key, stitch = bind_endpoint(end,region,cfg)
            ids.append(key)
            if key in graph:
                if math.dist(graph.nodes[key]["xy"],end["xy"]) > EPS:
                    raise ValueError("Endpoint ID changed its coordinates")
            elif stitch:
                attach,measured = stitch
                graph.add_node(key,xy=tuple(end["xy"]),tags=end.get("tags",{}))
                bidirectional(graph,key,attach,measured)
                added.append(key)
        result = route(graph,*ids)
        result["query_scope"] = q.get("scope","FULL_NETWORK")
        result["surface_sha256"] = region.surface.sha256
        result["uses_inferred_region"] = result["layer_lengths"]["inferred"]>EPS
        outcomes[q["query_id"]] = result
        graph.remove_nodes_from(added)
    return outcomes
