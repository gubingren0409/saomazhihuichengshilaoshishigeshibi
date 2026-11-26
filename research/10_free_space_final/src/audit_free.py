"""Independent geometry, route, graph and read-order checks for FREE-SPACE-R1.

Reads serialized source inputs, guard contracts and outputs. Does not import any
classification, constraint extraction, graph generation or solver code.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import re
import sys

from shapely import union_all
from shapely.geometry import LineString, Point, shape
from pyproj import Transformer
import networkx as nx

if __package__ in (None, ""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.score_free import (ATOL, LTOL, canonical_sha, cell_surface, file_sha, read, require)

CONSTRAINT_GEOMETRY_CACHE={}


def read_graph(path):
    if path.suffix == ".gz":
        with gzip.open(path,"rt",encoding="utf8") as f:
            return json.load(f)
    return read(path)


def observed_identity(root):
    old = read(root/"frozen_context/data/task_manifest.json")
    originals = {v["id"]:v for v in old["instances"]}
    originals.update({v["id"]:v for v in read(root/"frozen_context/data/e5/task_manifest.json")["instances"]})
    selected = read(root/"data/task_manifest.json")["instances"]
    primary = [t for t in selected if t["context_radius_m"]==80 and t["masking_mode"] in {"G","N"}]
    require(len(primary)==25 and len({t["parent_task_id"] for t in primary})==25,"Wrong fixed main parent denominator")
    observed = []
    queries = Counter()
    for task in selected:
        prior = originals[task["id"]]
        keys=("observed","query","route_graph") if task.get("natural") else ("observed","reference","query")
        for key in keys:
            require(task[key+"_sha256"]==prior[key+"_sha256"],"Manifest changed old source identity")
            require(file_sha(root/task[key])==prior[key+"_sha256"], "Frozen input bytes changed")
        for key in (() if task.get("natural") else ("prediction_domain_sha256","evaluation_domain_sha256","grid_sha256","mask_sha256")):
            require(task[key]==prior[key],f"Frozen {key} changed")
        q = read(root/task["query"])["queries"]
        if task in primary:
            queries[task["label"]] += len(q)
        observed.append({"id":task["id"],**{k:v for k,v in task.items() if k.endswith("_sha256")}})
    require(sum(queries.values())==41 and queries["POSITIVE"]==33 and queries["NEGATIVE"]==8,
            f"Fixed main query denominator differs: {dict(queries)}")
    return {"checked_instances":len(selected),"main_parents":25,"main_queries":dict(queries),"rows":observed}


def guard_source_audit(root,source_dir,guard_dir):
    """Reconstruct added road lines from raw node sequences, not author flags."""
    projection=Transformer.from_crs(4326,32651,always_xy=True).transform
    ledgers={(v["parent_task_id"],v["masking_mode"]):v for v in
             (json.loads(s) for s in (root/"frozen_context/data/mask_dependency_ledger.jsonl").read_text(encoding="utf8").splitlines())}
    tasks=read(root/"data/task_manifest.json")["instances"]
    originals={v["id"]:v for v in read(root/"frozen_context/data/task_manifest.json")["instances"]}
    rows=[]
    for clip in sorted({v["source_clip"] for v in originals.values()}):
        selected=[t for t in tasks if originals.get(t["id"],{}).get("source_clip")==clip or
                  t.get("natural") and clip=="sh-huangpu-01.osm.json"]
        if not selected:
            continue
        path=source_dir/clip
        expected={v["source_clip_sha256"] for v in originals.values() if v["source_clip"]==clip}
        require(expected=={file_sha(path)},"Common guard raw-source bytes differ")
        raw=read(path)
        nodes={v["id"]:v for v in raw["elements"] if v["type"]=="node"}
        ways={v["id"]:v for v in raw["elements"] if v["type"]=="way"}
        motor={"motorway","motorway_link","trunk","trunk_link","primary","primary_link","secondary","secondary_link",
               "tertiary","tertiary_link","unclassified","residential","service","living_street","road"}
        raw_roads={}
        for way_id,way in ways.items():
            tags=way.get("tags",{})
            if tags.get("highway") not in motor or tags.get("area")=="yes":continue
            if len(way.get("nodes",[]))<2 or any(n not in nodes for n in way["nodes"]):continue
            if any(tags.get(k) not in (None,"","0","no","false") for k in
                   ("level","layer","bridge","tunnel","indoor","repeat_on")):continue
            raw_roads["way/"+str(way_id)]=LineString([projection(nodes[n]["lon"],nodes[n]["lat"]) for n in way["nodes"]])
        for task in selected:
            gp=guard_dir/(task["id"]+".json")
            if not gp.exists():
                continue
            guard=read(gp)
            require(guard["source_bounds_wsen"]==raw["bounds_wsen"] and guard["source_parse_status"]=="PARSED",
                    "Coverage footprint does not match actually parsed source metadata")
            forbidden=set()
            ledger=ledgers.get((task["parent_task_id"],task["masking_mode"]),{})
            for key in ("hidden_relation_member_ids","removed_context_source_ids"):
                forbidden.update(ledger.get(key,[]))
            if ledger.get("masking_mode")=="H":
                forbidden.update(ledger.get("historical_hidden_way_ids",[]))
            for segment in ledger.get("historical_hidden_segments",[]):
                found=re.match(r"(?:node|way|relation)/\d+",segment)
                if found:forbidden.add(found.group())
            obs=read(root/task["observed"])
            disk=Point(obs["domain"]["anchor_xy"]).buffer(task["context_radius_m"],quad_segs=32)
            expected_roads={key for key,line in raw_roads.items() if key not in forbidden and
                            line.intersects(disk) and line.intersection(disk).length>1e-6}
            require({v["source_id"] for v in guard.get("road_centerlines",[])}==expected_roads,
                    "Common guard omitted/added an independent eligible ground road")
            checked=[]
            for road in guard.get("road_centerlines",[]):
                ident=road["source_id"]
                require(ident not in forbidden,"Hidden source object returned as road guard")
                way=ways[int(ident.split("/")[1])]
                # Independent motor-road geometry can share a source coordinate
                # with a hidden path; no hidden node IDs or member arrays are
                # serialized. Deleting the whole independent road would remove
                # the very no-new-crossing constraint this branch must enforce.
                require(road["tags"]==way.get("tags",{}),"Road guard source tag changed")
                native=LineString([projection(nodes[n]["lon"],nodes[n]["lat"]) for n in way["nodes"]])
                actual=shape(road["geometry"])
                target=native.intersection(disk)
                require(actual.hausdorff_distance(target)<=LTOL and abs(actual.length-target.length)<=LTOL,
                        "Road guard geometry is not exact raw source clipped only to context disk")
                checked.append({"source_id":ident,"length_m":actual.length})
            gate_checks=[]
            for barrier,gate_rows in guard.get("barrier_gates",{}).items():
                way=ways[int(barrier.split("/")[1])]
                for gate in gate_rows:
                    nid=int(gate["id"].split("/")[1])
                    require(nid in way["nodes"] and gate["id"] not in forbidden,"Gate has no valid original barrier membership")
                    node=nodes[nid]
                    require(gate["tags"]==node.get("tags",{}) and
                            math.dist(gate["xy"],projection(node["lon"],node["lat"]))<=LTOL,
                            "Gate tags/position changed from raw source")
                    gate_checks.append(gate["id"])
            require(not any(key in guard for key in ("geometry","reference","hidden_geometry","members","elements")),
                    "Guard top level unexpectedly serializes raw/hidden payload")
            rows.append({"id":task["id"],"guard_sha256":file_sha(gp),"raw_source_sha256":file_sha(path),
                         "forbidden_source_count":len(forbidden),"road_geometries_reconstructed":checked,
                         "gate_memberships_reconstructed":gate_checks,"coverage_bounds_from_actual_source":True})
    require(rows,"No common guards available for independent source audit")
    return {"status":"PASS","guard_directory":guard_dir.as_posix(),"checked_inputs":len(rows),"rows":rows,
            "scope":"ADDED_INDEPENDENT_ROAD_GEOMETRY_TAG_ID_AND_HIDDEN_OBJECT_DEPENDENCY_AUDIT; SOURCE_OMISSIONS_NOT_FIELD_VALIDATED",
            "shared_coordinate_policy":"INDEPENDENT_ROAD_GEOMETRY_RETAINED_WITHOUT_HIDDEN_NODE_IDS_OR_MEMBER_ARRAYS"}


def read_order(run):
    log = run["read_log"]
    events = [v for v in log if not v.get("role", "").startswith("DENIED_")]
    require([r["sequence"] for r in log] == list(range(1,len(log)+1)),"Read event order is invalid")
    denied = {r.get("role") for r in log if r.get("event")=="DENIED_OPEN"}
    denied_paths={r.get("path") for r in log if r.get("event")=="DENIED_OPEN"}
    require({"reference.json","query.json"} <= denied_paths,"Actual refused-open probe missing")
    roles = [r["role"].upper() for r in events]
    freezes = [i for i,r in enumerate(roles) if r in {"SURFACE_FROZEN","REGION_FROZEN"}]
    require(len(freezes)==1,"No unique surface freeze receipt")
    freeze=freezes[0]
    query = [i for i,r in enumerate(roles) if r=="QUERY"]
    require(query and min(query)>freeze,"Query read preceded frozen region")
    for i,event in enumerate(events):
        role=event["role"].upper()
        path=str(event.get("path", "")).replace("\\", "/").lower()
        require(not any(k in path.split("/") for k in ("reference","references","raw","frozen_context","frozen_r3")),
                "Predictor actually opened a hidden/reference/raw path")
        if role.endswith("ROUTE_ONLY_GRAPH") or role in {"ROUTE_GRAPH","NATURAL_ROUTE_GRAPH"}:
            require(i>freeze,"Full natural graph read before region freeze")
    receipt=events[freeze]
    frozen=receipt.get("surface_hashes",receipt.get("records"))
    if frozen:
        require(canonical_sha(frozen)==receipt["sha256"],"Joint freeze receipt hash mismatch")
        key="F0" if run["method"].startswith("F1") else run["method"]
        require(frozen[key]==run["surface"]["sha256"],"Frozen joint record and output surface differ")
    else:
        require(receipt.get("surface_sha256",receipt.get("sha256"))==run["surface"]["sha256"],"Freeze and output surface SHA differ")
    return {"events":len(log),"denied_probes":len(denied),"freeze_before_query":True,
            "classification_log_role":"INHERITED_INITIAL_RUN_NOT_RESUME" if run.get("routing_repair") else "CURRENT_CLASSIFICATION_WORKER",
            "isolation_scope":"APPLICATION_OPEN_AUDIT_NOT_OS_SANDBOX"}


def resume_check(root,run):
    if not run.get("routing_repair"):
        return None
    require(run.get("read_log_role")=="INHERITED_CLASSIFICATION_AND_FIRST_ROUTING_LOG_NOT_THIS_RESUME_EXECUTION",
            "Resume execution misrepresents inherited classifier reads as new probes")
    repair=run["routing_repair"]
    require(repair.get("new_region_builds")==0 and repair.get("surface_rebuilt") is False and
            repair.get("region_graph_changed") is False,"Unexpected reclassification in routing-only repair")
    events=run["route_only_read_log"]
    require([v["sequence"] for v in events]==list(range(1,len(events)+1)),"Resume actual file-read sequence malformed")
    previous=[]
    for event in events:
        path=(root/event["path"]).resolve()
        require(path.is_relative_to(root.resolve()) and path.is_file(),"Resume actual read points outside packaged task")
        require(file_sha(path)==event["sha256"],"Resume recorded read hash does not match actual file")
        require("reference" not in Path(event["path"]).parts,"Resume actually opened evaluation reference")
        if event["role"].startswith("ROUTE_ONLY_RESUME_PREVIOUS_PREDICTION"):
            previous.append(event)
    parent=next((e for e in previous if e["sha256"]==repair["parent_prediction_sha256"]),None)
    require(parent is not None,"Resume lacks its actual parent prediction read")
    old=read(root/parent["path"])
    require(old["surface"]==run["surface"] and old["graph"]["graph_sha256"]==run["graph"]["graph_sha256"] and
            old["query_sha256"]==run["query_sha256"],"Routing-only repair changed a frozen region/graph/query")
    return {"parent_prediction_sha256":parent["sha256"],"actual_resume_reads":len(events),"frozen_surface_graph_query_unchanged":True,
            "new_region_builds":0,"code_reviewed":"scripts/repair_north_terminals.py",
            "code_reviewed_sha256":file_sha(root/"scripts/repair_north_terminals.py"),
            "scope":"SEPARATE_CONTEXT_SOURCE_INSPECTION: old routes only used for historical reached count; new router receives source graphs/frozen region/original queries",
            "isolation_limit":"Resume loads whole old predictions, not an observed-only new classifier. Current forced-denial probes are inherited initial evidence. Pure-input final ZIP replay independently covers north."}


def formula(run,contract):
    masks,domain=cell_surface(run)
    require(domain.symmetric_difference(shape(contract["domain"])).area <= ATOL,"Constraint/prediction domain mismatch")
    valid=shape(contract["valid_geometry"])
    blocked=shape(contract["blocked_geometry"])
    target=valid.difference(blocked)
    actual=masks["NATIVE_WALKABLE"].union(masks["INFERRED_WALKABLE"])
    diff=target.symmetric_difference(actual).area
    require(diff <= ATOL,f"F0 is not full valid-domain minus common blocks: {diff}m²")
    require(actual.difference(valid).area <= ATOL,"No-data area became conditionally free")
    evidence=Counter()
    for cell in run["surface"]["cells"]:
        required={"source_evidence_state","planning_state","reason_code","policy_id","observed_source_ids",
                  "assumptions","constraint_ids","map_coverage_status","component_id"}
        require(required <= set(cell),f"Two-axis metadata missing: {required-set(cell)}")
        state=cell["walkability_state"]
        if state=="INFERRED_WALKABLE":
            require(cell["source_evidence_state"]=="UNLABELLED_UNVERIFIED" and
                    cell["planning_state"]=="ASSUMED_PASSABLE","Conditional free cells falsely claimed native facts")
            require(cell["policy_id"]=="DEFAULT_FREE_POLICY_V1","Default policy identity missing")
        evidence[cell["source_evidence_state"]] += 1
    return {"symmetric_difference_m2":diff,"no_data_passable_m2":actual.difference(valid).area,
            "evidence_cell_counts":dict(evidence),"valid_m2":valid.area,"blocked_m2":blocked.intersection(valid).area,
            "free_m2":target.area}


def independent_conflicts(line,contract,*,native=False,tags=None,source_id=None):
    """Separate Shapely checks against serialized constraint geometry."""
    tags=tags or {}
    key=contract.get("sha256",str(id(contract)))
    if key not in CONSTRAINT_GEOMETRY_CACHE:
        physical=shape(contract["physical_geometry"])
        CONSTRAINT_GEOMETRY_CACHE[key]={"owner":contract,"physical_interior":physical.buffer(-1e-7),
             "valid":shape(contract["valid_geometry"]),"background":shape(contract["background_geometry"]),
             "access":[Point(p["xy"]) for p in contract.get("native_road_access_points",[])],
             "permission_areas":[(r,shape(r["geometry"]).buffer(-1e-7),shape(r["source_geometry"]).boundary) for r in contract.get("access_area_constraints",[])],
             "permission_exceptions":[(r,shape(r["geometry"])) for r in contract.get("visible_native_boundary_exceptions",[])],
             "domain":shape(contract["domain"]),
             "roads":[(r,shape(r["geometry"])) for r in contract.get("road_centerlines",[])]}
    geometry=CONSTRAINT_GEOMETRY_CACHE[key]
    issues=[]
    denied={"no","private","customers","destination","delivery","permit","restricted","agricultural","forestry"}
    if tags.get("foot",tags.get("access")) in denied or tags.get("locked")=="yes" or any(k in tags for k in
       ("foot:conditional","access:conditional","oneway:foot:conditional")):
        issues.append("ACCESS")
    explicit=any(tags.get(k) not in (None,"","0","no","false") for k in
                 ("level","layer","bridge","tunnel","indoor","repeat_on"))
    if not native and explicit:
        issues.append("LAYER")
    for area,inside,boundary in geometry["permission_areas"]:
        if line.intersection(inside).length>1e-6:
            issues.append("SOURCE_ACCESS_INTERIOR:"+area["source_id"])
        touched=line.intersection(boundary).intersection(geometry["domain"])
        if touched.length>1e-6:
            permitted=union_all([g for r,g in geometry["permission_exceptions"] if native and
                r["area_source_id"]==area["source_id"] and r["source_id"]==source_id])
            if touched.difference(permitted).length>1e-6:
                issues.append("SOURCE_ACCESS_BOUNDARY_WITHOUT_EXACT_OBSERVED_EXCEPTION:"+area["source_id"])
    # Numerical interior check retains original exact terminal on obstacle boundary.
    structure=tags.get("bridge") not in (None,"no","false","0") or tags.get("tunnel") not in (None,"no","false","0")
    if line.intersection(geometry["physical_interior"]).length > 1e-6 and not (native and structure):
        issues.append("HARD_INTERIOR")
    if not native:
        if line.difference(geometry["valid"]).length > 1e-6:
            issues.append("OUTSIDE_VALID_DOMAIN")
        if line.intersection(geometry["background"]).length > 1e-6:
            issues.append("BACKGROUND_POLICY")
        allowed=geometry["access"]
        ends=[Point(line.coords[0]),Point(line.coords[-1])]
        for row,road in geometry["roads"]:
            hit=line.intersection(road)
            if hit.is_empty:
                continue
            points=[hit] if hit.geom_type=="Point" else list(hit.geoms) if hit.geom_type=="MultiPoint" else []
            exception=points and all(any(p.distance(e)<=1e-6 for e in ends) and
                                    any(p.distance(a)<=1e-6 for a in allowed) for p in points)
            if not exception:
                issues.append("ROAD_POLICY:"+row["source_id"])
    return sorted(set(issues))


def graph_edges(obj):
    rows=obj.get("edges", obj.get("arcs", []))
    for row in rows:
        if isinstance(row,dict):
            yield row
        elif len(row)==3 and isinstance(row[2],dict):
            yield {"u":row[0],"v":row[1],**row[2]}
        else:
            raise ValueError("Unsupported graph edge schema")


def graph_check(path,contract,run=None):
    graph=read_graph(path)
    actual_sha=canonical_sha({"nodes":graph["nodes"],"edges":graph["edges"]})
    require(actual_sha==graph["graph_sha256"],"Graph stored SHA does not describe actual unweighted nodes/edges")
    if run is not None:
        require(actual_sha==run["graph"]["graph_sha256"],"Graph geometry file differs from prediction graph SHA")
    counts=Counter()
    failures=[]
    weighted=[]
    nodes={r["id"]:r for r in graph.get("nodes",[])}
    topology=nx.DiGraph()
    topology.add_nodes_from(nodes)
    for edge in graph_edges(graph):
        topology.add_edge(edge.get("u"),edge.get("v"))
        segments=edge.get("segments",[edge] if "xy" in edge else [])
        if segments and edge.get("u") in nodes and edge.get("v") in nodes:
            require(math.dist(nodes[edge["u"]]["xy"],segments[0]["xy"][0])<=LTOL and
                    math.dist(nodes[edge["v"]]["xy"],segments[-1]["xy"][-1])<=LTOL,
                    "Graph edge geometry does not meet exact node coordinates")
        previous=None
        for segment in segments:
            points=segment["xy"]
            require(previous is None or math.dist(previous,points[0])<=LTOL,"Graph compound edge has a gap")
            previous=points[-1]
            line=LineString(points)
            require(abs(line.length-segment["length_m"])<=LTOL,"Graph segment length is not its actual geometry")
            native=segment.get("layer")=="native" or segment.get("geometry_kind", "").startswith("DERIVED_FROM_")
            if line.length > LTOL:
                issues=independent_conflicts(line,contract,native=native,tags=segment.get("tags",{}),source_id=segment.get("source_id"))
                if issues:
                    failures.append({"u":edge.get("u"),"v":edge.get("v"),"source_id":segment.get("source_id"),
                                     "issues":issues,"xy":points})
            counts["segments"]+=1
            counts[segment.get("layer", "UNKNOWN")]+=1
        weighted.append({"u":edge.get("u"),"v":edge.get("v"),"segments":[{k:v for k,v in s.items() if k not in {"cost_m","cost"}} for s in segments]})
    connection={}
    if run is not None:
        cell_area={c["region_id"]:shape(c["geometry"]).area for c in run["surface"]["cells"]
                   if c["walkability_state"] in {"NATIVE_WALKABLE","INFERRED_WALKABLE"}}
        interface_ids={r["id"] for r in run.get("graph",{}).get("interfaces",[])}
        components=list(nx.weakly_connected_components(topology))
        disconnected=[c for c in components if not (c & interface_ids)]
        area=sum(cell_area.get(n,0) for c in disconnected for n in c)
        absent=sum(v for k,v in cell_area.items() if k not in topology)
        connection={"local_weak_components":len(components),"local_components_without_native_interface":len(disconnected),
                    "local_components_without_native_interface_area_m2":area+absent,
                    "passable_cell_area_absent_from_graph_m2":absent,
                    "interface_count":len(interface_ids),
                    "meaning":"Weak component contact only; not a claim of directed full-route reachability"}
    return {"graph_file":path.as_posix(),"file_sha256":file_sha(path),"segments":dict(counts),
            "known_conflicts":failures,"unweighted_geometry_sha256":canonical_sha(weighted),"connection":connection}


def route_and_terminals_contract_check(run,contract):
    conflicts=[]
    routes=0
    edges=0
    for qid,result in run["routes"].items():
        routes+=1
        for segment in result["edges"]:
            edges+=1
            line=LineString(segment["xy"])
            source=segment.get("layer")=="native" or segment.get("geometry_kind", "").startswith("DERIVED_FROM_")
            if line.length <= LTOL:
                continue
            issues=independent_conflicts(line,contract,native=source,tags=segment.get("tags",{}),source_id=segment.get("source_id"))
            if issues:
                conflicts.append({"query_id":qid,"source_id":segment.get("source_id"),"issues":issues,"xy":segment["xy"]})
    terminals=0
    for terminal in run.get("graph",{}).get("terminals",[]):
        for segment in terminal["segments"]:
            terminals+=1
            line=LineString(segment["xy"])
            if line.length<=LTOL:continue
            issues=independent_conflicts(line,contract,native=False,tags=segment.get("tags",{}))
            if issues:
                conflicts.append({"terminal_id":terminal["id"],"issues":issues,"xy":segment["xy"]})
    return {"checked_routes":routes,"checked_route_segments":edges,"checked_terminal_segments":terminals,
            "known_conflicts":conflicts}


def independent_shortest_paths(run,observed,queries,graph_path,contract):
    """Rebuild small visible native graph and solve serialized region independently.

This verifies costs/reachability, not independently regenerating the policy grid.
The very large natural front graph is outside this bounded solver replay.
"""
    nodes={v["id"]:v for v in observed["nodes"]}
    denied={"no","private","customers","destination","delivery","permit","restricted","agricultural","forestry"}
    def access(tags):
        return tags.get("foot",tags.get("access")) in denied or tags.get("locked")=="yes" or any(k in tags for k in
               ("foot:conditional","access:conditional","oneway:foot:conditional"))
    base=nx.DiGraph()
    base.add_nodes_from(nodes)
    for edge in observed["edges"]:
        u,v=edge["u"],edge["v"]
        if u==v or any(access(t) for t in (edge.get("tags",{}),nodes[u].get("tags",{}),nodes[v].get("tags",{}))):continue
        line=LineString([nodes[u]["xy"],nodes[v]["xy"]])
        source_id=edge.get("source_id",edge["id"])
        match=re.match(r"(?:node|way|relation)/\d+",str(source_id))
        source_id=match.group() if match else str(source_id)
        if independent_conflicts(line,contract,native=True,tags=edge.get("tags",{}),source_id=source_id):continue
        cost=line.length
        if not base.has_edge(u,v) or cost<base[u][v]["weight"]:base.add_edge(u,v,weight=cost)
    serialized=read_graph(graph_path)
    local=nx.DiGraph()
    local.add_nodes_from(row["id"] for row in serialized["nodes"])
    weight=run.get("lambda_value",1)
    for edge in graph_edges(serialized):
        value=sum(LineString(s["xy"]).length*(weight if s["layer"] in {"inferred","unknown","assumed"} else 1)
                  for s in edge["segments"])
        local.add_edge(edge["u"],edge["v"],weight=value)
    checked=[]
    for q in queries:
        graph=local.copy() if q.get("scope")=="LOCAL_REGION_ONLY" else nx.compose(base,local)
        for terminal in run.get("graph",{}).get("terminals",[]):
            if terminal["query_id"]!=q["query_id"]:continue
            value=sum(LineString(s["xy"]).length*(weight if s["layer"] in {"inferred","unknown","assumed"} else 1)
                      for s in terminal["segments"])
            graph.add_edge(terminal["id"],terminal["attach"],weight=value)
            graph.add_edge(terminal["attach"],terminal["id"],weight=value)
        source,target=q["source"]["id"],q["target"]["id"]
        distances=nx.single_source_dijkstra_path_length(graph,source,weight="weight") if source in graph else {}
        value=distances.get(target)
        actual=run["routes"][q["query_id"]]
        require((value is not None)==bool(actual["reached"]),"Independent solver reachable set differs")
        if value is not None:
            require(abs(value-actual["cost_m"])<=LTOL,"Recorded path is not minimal finite-cost route on frozen graph")
        checked.append({"query_id":q["query_id"],"reached":value is not None,"independent_minimum_cost":value})
    return {"scope":"INDEPENDENT_SHORTEST_COST_ON_SERIALIZED_REGION_AND_RECONSTRUCTED_VISIBLE_NATIVE_GRAPH",
            "queries":checked}


def compare_finite(left,right):
    require(left["surface"]==right["surface"],"F0/F1 exact surfaces differ")
    a={q:bool(v["reached"]) for q,v in left["routes"].items()}
    b={q:bool(v["reached"]) for q,v in right["routes"].items()}
    require(a==b,"Finite cost changed same-graph reachability")
    lgraph=left.get("graph",{})
    rgraph=right.get("graph",{})
    keys=[k for k in ("unweighted_sha256","unweighted_graph_sha256","graph_sha256") if k in lgraph or k in rgraph]
    require(keys,"Unweighted graph hash absent")
    for k in keys:
        require(lgraph.get(k)==rgraph.get(k),f"F0/F1 graph hash differs {k}")
    require(lgraph.get("interfaces")==rgraph.get("interfaces"),"F0/F1 interfaces differ")
    require(lgraph.get("graph_path")==rgraph.get("graph_path"),"F0/F1 do not use the same actual graph file")
    require(lgraph.get("terminals")==rgraph.get("terminals") and
            lgraph.get("terminal_graph_sha256")==rgraph.get("terminal_graph_sha256"),"F0/F1 terminal interface structures differ")
    return {"surface_identical":True,"unweighted_graph_identical":True,"reachable_set_identical":True,
            "reachable_query_ids":[q for q,v in a.items() if v]}


def main(args):
    root=args.root.resolve()
    inventory=observed_identity(root)
    root.joinpath("audits").mkdir(exist_ok=True)
    write=lambda name,obj: (root/"audits"/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8")
    write("free_input_identity.json",{"status":"PASS","scope":"FROZEN_INPUT_BYTES_AND_FIXED_MAIN_DENOMINATORS",**inventory})
    if args.inputs_only:
        print("Independent fixed input identity PASS",inventory["checked_instances"])
        return
    if args.source_dir:
        source_check=guard_source_audit(root,args.source_dir,args.guard_dir or root/"data/common_guards_v2")
        write("free_guard_source_audit_v2.json",source_check)
        if args.guards_only:
            print("Independent guard source audit PASS",source_check["checked_inputs"])
            return
    tasks=read(root/"data/task_manifest.json")["instances"]
    checks=[]
    for task in tasks:
        ident=task["id"]
        folder=root/"data/predictions"/ident
        if not folder.exists():
            continue
        f0path=folder/"F0.json"
        if not f0path.exists():
            continue
        f0=read(f0path)
        contract_paths=[root/"data/constraints"/(ident+".json"),root/"data/constraint_contracts"/(ident+".json")]
        cp=next((p for p in contract_paths if p.exists()),None)
        require(cp is not None,f"No serialized per-input common constraint: {ident}")
        contract=read(cp)
        row={"id":ident,"formula":formula(f0,contract),"read_order":{"F0":read_order(f0)},"finite_comparisons":{}}
        row["route_contracts"]={"F0":route_and_terminals_contract_check(f0,contract)}
        row["routing_resume"]={"F0":resume_check(root,f0)}
        for method in ("M1-C","F1","F1-L1","F1-L1p5","F1-L3","F1-L5"):
            path=folder/(method+".json")
            if not path.exists():
                continue
            run=read(path)
            row["read_order"][method]=read_order(run)
            row["route_contracts"][method]=route_and_terminals_contract_check(run,contract)
            row["routing_resume"][method]=resume_check(root,run)
            if method.startswith("F1"):
                row["finite_comparisons"][method]=compare_finite(f0,run)
                if method=="F1-L1":
                    require(f0["routes"]==run["routes"],"Lambda=1 does not exactly reproduce F0 routes/costs")
        require(not any(v["known_conflicts"] for v in row["route_contracts"].values()),
                f"Actual route/terminal violates common constraint: {ident}")
        if args.graphs:
            gp=root/f0["graph"]["graph_path"]
            if not gp.exists():
                gp=gp.with_suffix(".json.gz")
            require(gp.exists(),f"Graph geometry missing: {ident}")
            row["graph"]=graph_check(gp,contract,f0)
            require(not row["graph"]["known_conflicts"],f"Graph contains known conflict {ident}")
            row["graphs"]={"F0_SHARED_F1":row["graph"]}
            mcpath=folder/"M1-C.json"
            if mcpath.exists():
                mc=read(mcpath)
                row["graphs"]["M1-C"]=graph_check(root/mc["graph"]["graph_path"],contract,mc)
                require(not row["graphs"]["M1-C"]["known_conflicts"],f"M1-C graph contains known conflict {ident}")
            if not task.get("natural"):
                observed=read(root/task["observed"])
                queries=read(root/task["query"])["queries"]
                row["independent_solver"]={}
                for method in ("M1-C","F0","F1"):
                    rp=folder/(method+".json")
                    if not rp.exists():continue
                    run=read(rp)
                    row["independent_solver"][method]=independent_shortest_paths(run,observed,queries,
                          root/run["graph"]["graph_path"],contract)
        checks.append(row)
        write("free_review_progress.json",{"status":"RUNNING_PARTIAL_NOT_FULL_PASS","completed_ids":[v["id"] for v in checks],
              "last_graph_segment_counts":{k:v["segments"] for k,v in row.get("graphs",{}).items()}})
        print("INDEPENDENT",ident,"PASS",len(checks),flush=True)
    require(checks,"No F0 actual output exists")
    if args.require_main:
        ids={r["id"] for r in checks}
        expected={t["id"] for t in tasks if t["context_radius_m"]==80 and t["masking_mode"] in {"G","N"}}
        require(len(expected)==25 and expected <= ids,f"Incomplete primary independent checks: {sorted(expected-ids)}")
        require("NORTH_160" in ids,"Required natural north comparison not independently checked")
    write("free_independent_checks.json",{"status":"PASS","checked_inputs":len(checks),"rows":checks,
          "graph_checks":bool(args.graphs),"scope":"INDEPENDENT_SERIALIZED_GEOMETRY_RECOMPUTATION_NOT_AUTHOR_PASS"})
    print("Independent checks PASS",len(checks))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--inputs-only",action="store_true")
    parser.add_argument("--graphs",action="store_true")
    parser.add_argument("--source-dir",type=Path)
    parser.add_argument("--guards-only",action="store_true")
    parser.add_argument("--guard-dir",type=Path)
    parser.add_argument("--require-main",action="store_true")
    main(parser.parse_args())
