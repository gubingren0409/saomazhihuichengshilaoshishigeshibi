"""Independently locate the original local objects supporting every M1 promotion."""
import argparse
from collections import Counter
import math
from pathlib import Path
import sys

from shapely import union_all
from shapely.geometry import LineString, Point, shape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.context_audit_common import LENGTH_TOL, ROOT, district_band, item_id, read, require, write

LOCAL_GEOMETRY_TOL_M = 1e-4
PAVED={"PAVING","PAVED","PAVED_AREA","PLAZA"}
PARK={"PARK","PARK_GARDEN_OR_RECREATION"}
FACE={"PEDESTRIAN_AREA","WALKABLE_AREA","NATIVE_WALKABLE_AREA"}
DENY={"private","no","restricted","customers","delivery","permit","destination","forestry","agricultural"}
GROUND={None,"","0",0,"no","false"}


def supports(row, line, point, fraction):
    return row[1].covers(point) and row[1].intersection(line).length+LOCAL_GEOMETRY_TOL_M>=fraction*line.length


def validate_witness(row,graph,nodes,center,cfg):
    chain=row["node_path"]
    require(len(chain)>1 and len(row["fragment_ids"])==len(chain)-1,"Malformed witnessed topology")
    points=[nodes[n]["xy"] for n in chain]
    path=LineString(points)
    require(path.length<=cfg["max_observed_chain_m"]+LENGTH_TOL and
            center.distance(Point(points[0]))<=cfg["portal_max_from_center_m"]+LENGTH_TOL and
            center.distance(Point(points[-1]))>cfg["perimeter_junction_min_m"],"Witness leaves bounded contract")
    for a,b,ident in zip(chain,chain[1:],row["fragment_ids"]):
        e=graph[ident]
        require((e["u"],e["v"])==(a,b),"Witness not an allowed directed edge")
        for tags in (e.get("tags",{}),nodes[a].get("tags",{}),nodes[b].get("tags",{})):
            require(tags.get("foot",tags.get("access")) not in DENY and tags.get("locked")!="yes" and
                    not any(k in tags for k in ("foot:conditional","access:conditional","oneway:foot:conditional")) and
                    all(tags.get(k) in GROUND for k in ("level","layer","bridge","tunnel","indoor","repeat_on")),
                    f"Context witness uses a restricted or elevated edge: {ident}")
    return { "node_path":chain,"ordered_fragment_ids":row["fragment_ids"],"raw_source_way_ids":sorted(
                 {item_id(graph[e]) for e in row["fragment_ids"]}),
             "observed_path_m":path.length,"max_radius_m":max(center.distance(Point(p)) for p in points),
             "radius_band":district_band(max(center.distance(Point(p)) for p in points)) }


def local_evidence(c,geom,nodes,rows,witnesses,restricted,config):
    point=geom.representative_point()
    portals=[Point(nodes[witnesses[w]["node_path"][0]]["xy"]) for w in c["context_witnesses"]]
    links=[LineString([point,p]) for p in portals]
    for line in links:
        require(line.length<=config["portal_to_cell_m"]+LENGTH_TOL and
                line.intersection(restricted).length<=LENGTH_TOL,
                f"Local context-to-cell link crosses a restriction or is unbounded: {c['region_id']}")
    reason=c["decision_reason"].removeprefix("EXTERIOR_TOPOLOGY_AND_")
    evidence=set(c["evidence_sources"])
    qualifying=[]
    buildings=[]
    if reason=="MAPPED_FACE_EDGE":
        threshold=config["face_or_frontage_m"]+LENGTH_TOL
        qualifying=[key for key,g,t in rows["support"] if key in evidence and t in FACE and
                    point.distance(g)<=threshold and portals[0].distance(g)<=.5+LENGTH_TOL]
    else:
        types=PAVED if reason=="PAVED_OPEN_SPACE" else PARK
        qualifying=[key for key,g,t in rows["support"] if key in evidence and t in types and
                    all(supports((key,g),line,point,config["support_line_fraction"]) for line in links)]
        if reason=="PARK_WITH_BUILDING_FRONTAGE":
            buildings=[key for key,g,t in rows["hard"] if t=="BUILDING" and
                       point.distance(g.boundary)<=config["face_or_frontage_m"]+LENGTH_TOL]
            require(buildings and set(buildings)<=evidence,
                    f"Building frontage witness missing matching original source ID: {c['region_id']}")
        elif reason=="PARK_BETWEEN_TWO_CONNECTED_APPROACHES":
            require(len(portals)==2 and min(p.distance(point) for p in portals)>=1-LENGTH_TOL,
                    f"Opposite approach witness has no two directions: {c['region_id']}")
            va,vb=[(p.x-point.x,p.y-point.y) for p in portals]
            cos=(va[0]*vb[0]+va[1]*vb[1])/(math.hypot(*va)*math.hypot(*vb))
            require(cos<=config["opposite_dot_max"]+LENGTH_TOL,"Claimed opposing network approaches are not opposing")
        else:
            require(reason=="PAVED_OPEN_SPACE",f"Unrecognized contextual decision: {reason}")
    require(qualifying,f"Missing eligible local geometry supporting {reason}: {c['region_id']}")
    return {"region_id":c["region_id"],"reason":reason,"area_m2":geom.area,
            "source_space_ids":sorted(set(qualifying)),"compatible_frontage_building_ids":sorted(set(buildings)),
            "witness_ids":c["context_witnesses"],"local_link_length_m":[x.length for x in links]}


def check_case(root,instance,path,cfg):
    run=read(path)
    used=run["features"].get("witnesses",{})
    if not used:
        require(run["features"]["changed_cells"]==0,"Changed M1 cell without topology trace")
        return {"id":instance["id"],"cells":0,"witnesses":{},"spatial_evidence":[]}
    obs=read(root/instance["observed"])
    source_rows={kind:[(row["id"],shape(row["geometry"]),row["kind"]) for row in objects]
                 for kind,objects in obs["context"].items()}
    center=Point(obs["domain"]["anchor_xy"])
    nodes={row["id"]:row for row in obs["nodes"]}
    graph={row["id"]:row for row in obs["edges"]}
    witnesses={k:validate_witness(row,graph,nodes,center,cfg) for k,row in used.items()}
    cells=run["surface"]["cells"]
    restricted=union_all([shape(c["geometry"]) for c in cells if c["walkability_state"]=="RESTRICTED"])
    evidence=[local_evidence(c,shape(c["geometry"]),nodes,source_rows,witnesses,restricted,cfg)
              for c in cells if c.get("context_witnesses")]
    require(len(evidence)==run["features"]["changed_cells"],"Context evidence count differs from prediction")
    return {"id":instance["id"],"cells":len(evidence),"witnesses":witnesses,"spatial_evidence":evidence}


def main(args):
    root=args.root.resolve()
    m=read(root/"data/task_manifest.json")
    cfg=read(root/"config/methods.json")["M1"]
    details=[]
    causes=Counter()
    for row in m["instances"]:
        if "ORIGINAL" in row["id"] or args.task and row["parent_task_id"] not in args.task:
            continue
        path=root/"data/predictions"/row["id"]/"M1.json"
        report=check_case(root,row,path,cfg)
        details.append(report)
        causes.update(cell["reason"] for cell in report["spatial_evidence"])
    write(args.out or root/"audits/context_feature_spatial.json",{
        "status":"INDEPENDENT_M1_WITNESS_AND_LOCAL_GEOMETRY_CHECK",
        "inputs":len(details),"inputs_with_actual_changed_cells":sum(bool(r["cells"]) for r in details),
        "changed_cells":sum(r["cells"] for r in details),"counts_by_reason":dict(causes),
        "frontage_provenance":"For each affected cell, every original building that satisfies the frontage condition was independently located and cross-checked with the recorded evidence IDs.",
        "runs":details})
    print(f"Audited {len(details)} M1 inputs, {sum(causes.values())} actual local promotions",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--task",action="append")
    p.add_argument("--out",type=Path)
    main(p.parse_args())
