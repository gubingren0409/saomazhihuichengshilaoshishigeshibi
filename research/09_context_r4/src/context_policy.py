"""Add bounded source-grounded context to the frozen local M0 surface."""
from collections import Counter
from math import dist
import networkx as nx
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

from src.region import (INFERRED, NATIVE, UNKNOWN, RESTRICTED, PARK, PAVING, STATES,
                        Surface, access_conflict, digest, edge_source, non_ground, polygons, union)

EPS=1e-7


def distance_band(distance):
    return "0–40" if distance<=40+EPS else "40–80" if distance<=80+EPS else "80–160"


def blocked(line, hard, index):
    for i in index.query(line,predicate="intersects"):
        geom,row=hard[i]
        if geom.area>0:
            if line.intersection(geom.buffer(-.001)).length>EPS:
                return True
        elif line.crosses(geom) or line.intersection(geom).length>EPS:
            at=line.intersection(geom)
            known=[Point(g["xy"]) for g in row.get("gates",[]) if g.get("allowed")]
            openings=union(g.buffer(.001) for g in known)
            if at.length>EPS or not at.difference(openings).is_empty:
                return True
    return False


def exterior_connections(observed,surface,cfg):
    center=Point(observed["domain"]["anchor_xy"])
    nodes={r["id"]:r for r in observed["nodes"]}
    hard=[(shape(r["geometry"]),r) for r in observed["context"]["hard"]]
    hard.extend((shape(r["geometry"]),r) for r in observed["context"]["support"] if access_conflict(r.get("tags",{})))
    hard_index=STRtree([g for g,_ in hard])
    graph=nx.DiGraph()
    provenance={}
    for e in observed["edges"]:
        u,v=e["u"],e["v"]
        if e["kind"] not in {"NATIVE_LINEAR","NATIVE"} or u==v:
            continue
        tags=(e.get("tags",{}),nodes[u].get("tags",{}),nodes[v].get("tags",{}))
        if any(access_conflict(t) or non_ground(t) for t in tags):
            continue
        a,b=nodes[u]["xy"],nodes[v]["xy"]
        line=LineString([a,b])
        if line.length<=EPS or blocked(line,hard,hard_index):
            continue
        if not graph.has_edge(u,v):
            graph.add_edge(u,v,length=line.length,source=edge_source(e),fragment=e["id"])
    targets=[]
    for node in sorted(graph):
        p=Point(nodes[node]["xy"])
        endpoint=nodes[node].get("endpoint_kind","NATIVE_ENDPOINT")
        if p.distance(center)<=cfg["perimeter_junction_min_m"] or not node.startswith("node/") or any(
                token in endpoint for token in ("CLIP","MASK","CROP_LIMIT")):
            continue
        neighbors=set(graph.predecessors(node))|set(graph.successors(node))
        sources={data["source"] for *_,data in list(graph.in_edges(node,data=True))+list(graph.out_edges(node,data=True))}
        if len(neighbors)>=3 and len(sources)>=2:
            targets.append(node)
    if not targets:
        return [],{},dict(topology_nodes=len(graph),topology_arcs=graph.number_of_edges(),exterior_junctions=0)
    lengths,reverse=nx.multi_source_dijkstra(graph.reverse(copy=False),targets,
        cutoff=cfg["max_observed_chain_m"],weight="length")
    portals=[]
    for port in sorted(lengths):
        point=Point(nodes[port]["xy"])
        if point.distance(center)>cfg["portal_max_from_center_m"] or lengths[port]<=EPS:
            continue
        chain=list(reversed(reverse[port]))
        edges=[graph[a][b] for a,b in zip(chain,chain[1:])]
        if not edges:
            continue
        witness_id=f"context/{port}"
        coords=[nodes[n]["xy"] for n in chain]
        max_radius=max(Point(xy).distance(center) for xy in coords)
        ways=sorted({e["source"] for e in edges})
        provenance[witness_id]={"portal_id":port,"junction_id":chain[-1],"node_path":chain,
                               "source_ids":ways,"fragment_ids":[e["fragment"] for e in edges],
                               "xy":coords,"observed_path_m":lengths[port],
                               "max_radius_m":max_radius,"radius_band":distance_band(max_radius)}
        portals.append({"id":port,"point":point,"source":edges[0]["source"],"witness":witness_id})
    return portals,provenance,dict(topology_nodes=len(graph),topology_arcs=graph.number_of_edges(),
        exterior_junctions=len(targets),topology_components=nx.number_weakly_connected_components(graph))


def candidate_evidence(point,surface,portals,neighbors,space_index,spaces,frontage,faces,cfg):
    passing=[]
    near_frontage=[source for source,g in frontage if g.distance(point)<=cfg["face_or_frontage_m"]]
    face_distance=cfg["face_or_frontage_m"]
    for i in sorted(neighbors,key=lambda i:(point.distance(portals[i]["point"]),portals[i]["id"])):
        portal=portals[i]
        anchor=portal["point"]
        line=LineString([point,anchor])
        if line.length<=EPS or line.intersection(surface.masks[RESTRICTED]).length>EPS:
            continue
        zones=[spaces[k] for k in space_index.query(point,predicate="intersects")
               if spaces[k]["g"].covers(point) and
               spaces[k]["g"].intersection(line).length>=cfg["support_line_fraction"]*line.length]
        paved=[r for r in zones if r["kind"] in PAVING]
        park=[r for r in zones if r["kind"] in PARK]
        face=[r for r in faces if r["g"].distance(point)<=face_distance and r["g"].distance(anchor)<=.5]
        if paved or face or (park and near_frontage):
            reasons=("PAVED_OPEN_SPACE" if paved else "MAPPED_FACE_EDGE" if face else "PARK_WITH_BUILDING_FRONTAGE")
            relation=[r["id"] for r in (paved or face or park)]
            if reasons=="PARK_WITH_BUILDING_FRONTAGE":
                relation.extend(near_frontage)
            return [portal["witness"]],sorted(set(relation)),reasons
        if park and line.length>=1:
            dx=(anchor.x-point.x)/line.length
            dy=(anchor.y-point.y)/line.length
            for prior,px,py,ids in passing:
                common=sorted(set(ids)&{r["id"] for r in park})
                if common and portal["source"]!=prior["source"] and dx*px+dy*py<=cfg["opposite_dot_max"]:
                    return [prior["witness"],portal["witness"]],common,"PARK_BETWEEN_TWO_CONNECTED_APPROACHES"
            passing.append((portal,dx,dy,[r["id"] for r in park]))
    return None


def enhance(surface,observed,base_cfg,cfg):
    """Reclassify only locally supported UNKNOWN cells. No scoring or route input."""
    portals,provenance,stats=exterior_connections(observed,surface,cfg)
    cells=[dict(c) for c in surface.cells]
    spaces=[r for r in surface.context["support"] if r["kind"] in PARK|PAVING]
    faces=surface.context["native"]
    frontage=[(r["id"],r["g"].boundary) for r in surface.context["hard"] if r["kind"]=="BUILDING"]
    point_index=STRtree([p["point"] for p in portals])
    space_index=STRtree([r["g"] for r in spaces])
    possible={}
    if portals:
        for i,cell in enumerate(cells):
            if cell["walkability_state"]!=UNKNOWN:
                continue
            point=cell["g"].representative_point()
            neighbors=point_index.query(point,predicate="dwithin",distance=cfg["portal_to_cell_m"])
            hit=candidate_evidence(point,surface,portals,neighbors,space_index,spaces,frontage,faces,cfg)
            if hit:
                possible[i]=hit
    proposed=union([surface.masks[NATIVE],surface.masks[INFERRED],*(cells[i]["g"] for i in possible)])
    core=proposed.buffer(-base_cfg["min_region_clearance_m"])
    admissible=union(g for g in polygons(proposed) if g.area>=base_cfg["min_patch_area_m2"] and g.intersects(core))
    used=Counter()
    for i,(witnesses,relations,reason) in possible.items():
        cell=cells[i]
        if not admissible.covers(cell["g"].representative_point()):
            continue
        object_ids={way for witness in witnesses for way in provenance[witness]["source_ids"]}
        cell.update(walkability_state=INFERRED,source_status="inferred",
                    decision_reason="EXTERIOR_TOPOLOGY_AND_"+reason,context_witnesses=witnesses,
                    evidence_sources=sorted(set(cell["evidence_sources"])|object_ids|set(relations)),
                    assumptions=["OUTDOOR_LOCAL_GROUND_CONTINUITY_UNVERIFIED",
                                 "EXTERIOR_OBSERVED_TOPOLOGY_IS_SUPPORT_NOT_PASSABILITY_PROOF"],
                    uncertainty_level="CONDITIONAL_UNCALIBRATED")
        used.update(witnesses)
    if used:
        masks={state:union(c["g"] for c in cells if c["walkability_state"]==state) for state in STATES}
        area={state:masks[state].area for state in STATES}
        stats_surface={**surface.statistics,"inferred_components":len(list(polygons(masks[INFERRED]))),
                       "classified_m2":sum(area.values())}
        surface=Surface(surface.domain,cells,masks,surface.context,
            digest([{k:v for k,v in row.items() if k!="g"} for row in cells]),area,stats_surface,surface.step)
    witnesses={key:dict(provenance[key],affected_cells=count) for key,count in sorted(used.items())}
    stats.update(eligible_portals=len(portals),locally_supported_candidates=len(possible),
                 used_witnesses=len(used),changed_cells=sum("context_witnesses" in row for row in surface.cells),
                 used_witnesses_by_band=dict(Counter(row["radius_band"] for row in witnesses.values())),
                 witnesses=witnesses,ablation="M0_IDENTICAL_FROZEN_LOCAL_CLASSIFICATION")
    return surface,stats
