"""Natural replay and observed-only two-phase controlled reconstruction."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
from itertools import combinations
import math

import networkx as nx
from pyproj import Transformer
from shapely import set_precision
from shapely.geometry import Point, LineString, mapping, shape
from shapely.ops import transform

if __package__ in (None,""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from src.inference import run_observed
from src.region import INFERRED, STATES, build_surface
from src.region_routing import native_graph, region_graph, routed_queries, empty, route, segment

ROOT=Path(__file__).resolve().parents[1]
WGS=Transformer.from_crs(32651,4326,always_xy=True).transform
XY=Transformer.from_crs(4326,32651,always_xy=True).transform
REGIONS=("I-REGION","I-REGION-ABL","I-REGION-NET-ABL")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value, compact=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False,indent=None if compact else 2,
                  separators=(",",":") if compact else None)
        stream.write("\n")


def fc(rows):
    return {"type":"FeatureCollection","features":rows}


def feature(geom,**props):
    return {"type":"Feature","geometry":mapping(transform(WGS,geom)),"properties":props}


def polygon_export(geometry):
    """Preserve the authoritative metric surface through a valid WGS84 exchange."""
    geographic=transform(WGS,geometry)
    restored=transform(XY,geographic)
    if geographic.is_valid and restored.is_valid:
        return geographic,False
    candidates=[geographic.buffer(0)]
    candidates.extend(transform(WGS,set_precision(geometry,step)) for step in (1e-7,1e-6,1e-5))
    for proposed in candidates:
        restored=transform(XY,proposed)
        if (proposed.is_valid and restored.is_valid and not proposed.is_empty and
                proposed.geom_type in {"Polygon","MultiPolygon"} and
                geometry.symmetric_difference(restored).area<=max(1e-5,geometry.area*1e-6)):
            return proposed,True
    raise ValueError("Lossless within tolerance WGS84 polygon serialization failed")


def write_surface(path,surface):
    props_excluded={"g","geometry","ij"}
    features=[]
    for row in surface.cells:
        geometry,repaired=polygon_export(row["g"])
        props={k:v for k,v in row.items() if k not in props_excluded}
        if repaired:
            props["serialization_note"]="WGS84_TOPOLOGY_REPAIRED_METRIC_AREA_PRESERVED"
        features.append({"type":"Feature","geometry":mapping(geometry),"properties":props})
    write(path,fc(features),True)


def summarize(s):
    return {"sha256":s.sha256,"area_m2":s.area_m2,**s.statistics}


def stage_surfaces(observed,cfg,variants,root,controlled):
    surfaces={}
    stages=[]
    base=native_graph(observed)
    for variant in variants:
        if variant not in REGIONS:
            continue
        build_start=perf_counter()
        if variant=="I-REGION-NET-ABL":
            surface=surfaces["I-REGION"][0]
        else:
            surface=build_surface(observed,cfg,ablate_context=variant=="I-REGION-ABL")
        if controlled:
            geo=root/"data/benchmark_predictions"/f"{observed['task_id']}_{variant}.geojson"
        else:
            file="north_regions" if variant=="I-REGION" else f"north_regions_{variant}"
            geo=root/"data"/(file+".geojson")
        write_surface(geo,surface)
        graph=region_graph(surface,base,cfg,disabled=variant=="I-REGION-NET-ABL")
        surfaces[variant]=(surface,graph)
        stages.append({"role":"SURFACE_FROZEN","variant":variant,"surface_sha256":surface.sha256,
                       "path":geo.relative_to(root).as_posix(),"sha256":file_sha(geo),
                       "seconds":perf_counter()-build_start})
    return base,surfaces,stages


def line_query(observed,q,legacy):
    source,target=q["source"],q["target"]
    if q.get("scope")=="LOCAL_REGION_ONLY" or not any(n["id"]==source["id"] for n in observed["nodes"]):
        return empty("LOCAL_REUSABLE_REGION_NOT_AVAILABLE")
    door=observed["registered_entrance"]
    target_arg=({k:v for k,v in door.items() if k in
                {"id","xy","wgs84","tags","registered","building_id"}} if door and target["id"]==door["id"]
                else {"id":target["id"],"xy":target["xy"],"registered":False,"tags":{}})
    task={k:observed[k] for k in ("task_id","crs","nodes","edges","context")}
    task.update(origin=source["id"],target=target_arg,kind="REGISTERED_DOOR_TASK" if
                target_arg["registered"] else "NETWORK_GAP_TASK")
    result=run_observed(task,legacy,methods=("I1",))["methods"]["I1"]
    value=result["route"]
    if not value:
        return empty(result["status"])
    edges=[dict(s,layer="inferred" if s["hypothesis"] else "native" if s["kind"]=="NATIVE_LINEAR" else "derived",
                geometry_kind="R2_SINGLE_LINE_BASELINE" if s["hypothesis"] else s["kind"],edge_id=s["id"])
           for s in value["edges"]]
    lengths={k:sum(e["length_m"] for e in edges if e["layer"]==k) for k in ("native","derived","inferred","unknown")}
    return dict(status=result["status"],length_m=value["length_m"],cost_m=value["cost_m"],layer_lengths=lengths,
                edges=edges,reached=result["reached_original_target"], residual_m=result["residual_m"],
                end_xy=edges[-1]["xy"][-1] if edges else source["xy"], candidate_count=len(result["candidates"]))


def s_prefix(source_root,mode,target):
    doc=read(source_root/"data/semantics_routes.geojson")
    row=next(f for f in doc["features"] if f["properties"].get("role")=="route_section" and
             f["properties"].get("target")=="north_fixed" and f["properties"]["variant"]==mode)
    coordinates=[XY(*p) for p in row["geometry"]["coordinates"]]
    ids=row["properties"]["source_ids"]
    edges=[segment([a,b],"native",ident,edge_id=f"historical/{n}",geometry_kind="NATIVE_LINEAR") for
           n,(a,b,ident) in enumerate(zip(coordinates,coordinates[1:],ids))]
    length=sum(e["length_m"] for e in edges)
    return dict(status="APPROACH_WITH_GAP",length_m=length,cost_m=length,
                layer_lengths={"native":length,"derived":0,"inferred":0,"unknown":0},edges=edges,
                end_xy=coordinates[-1],start_xy=coordinates[0],reached=False,
                residual_m=math.dist(coordinates[-1],target["xy"]),history_source=f"S_{mode}_SAME_FIXED_ENDPOINT")


def run_variants(observed,base,surfaces,queries,variants,cfg,legacy):
    results={}
    for name in variants:
        if name in REGIONS:
            surface,graph=surfaces[name]
            t=perf_counter()
            qs=routed_queries(base,graph,queries,cfg)
            results[name]={"surface":summarize(surface),"graph":graph.stats,"interfaces":graph.interfaces,
                           "routes":qs,"route_seconds":perf_counter()-t}
        elif name=="S1":
            results[name]={"routes":{q["query_id"]:route(base,q["source"]["id"],q["target"]["id"])
                                    if q.get("scope")!="LOCAL_REGION_ONLY" else empty("NO_REGION_GRAPH")
                                    for q in queries}}
        elif name=="I-LINE":
            results[name]={"routes":{q["query_id"]:line_query(observed,q,legacy) for q in queries}}
    return results


def queries_for_north(observed,ports,origin,surface):
    nodes={row["id"]:row for row in observed["nodes"]}
    door=observed["registered_entrance"]
    queries=[{"query_id":"NORTH-DOOR","source":{"id":origin,"xy":nodes[origin]["xy"],"role":"FROZEN_START"},
              "target":dict(door,role="REGISTERED_EXIT"),"scope":"FULL_NETWORK"}]
    # Pairs are selected by geometric separation after freezing the common region.
    # Pair success and route lengths are not examined here.
    pairs=sorted(combinations(ports,2),key=lambda p:(-math.dist(p[0]["xy"],p[1]["xy"]),p[0]["id"],p[1]["id"]))
    used=set()
    for a,b in pairs:
        if a["id"] in used or b["id"] in used:
            continue
        used.update([a["id"],b["id"]])
        queries.append({"query_id":f"NORTH-PAIR-{len(queries)}","source":{"id":a["id"],"xy":a["xy"]},
                        "target":{"id":b["id"],"xy":b["xy"]},"scope":"LOCAL_REGION_ONLY"})
        if len(queries)==5:
            break
    # This supplemental diagnostic was registered after the first natural run.
    # Pick interior points by geometry and stable IDs, not by route existence.
    inferred=surface.masks[INFERRED]
    controls=[]
    eligible=[(c["region_id"],c["g"].representative_point())
              for c in surface.cells if c["walkability_state"]==INFERRED and
              inferred.boundary.distance(c["g"].representative_point())>=surface.step]
    if eligible:
        first=min(eligible,key=lambda r:(r[1].x,r[1].y,r[0]))
        last=max(eligible,key=lambda r:(first[1].distance(r[1]),r[0]))
        for name,(_,p) in zip(("A","B"),(first,last)):
            controls.append({"id":"control/interior/"+name,"xy":list(p.coords[0]),
                             "role":"CONTROL_INTERIOR_POINT"})
    if len(ports)>=2 and len(controls)==2 and math.dist(controls[0]["xy"],controls[1]["xy"])>surface.step:
        selected=set()
        for n,end in enumerate(controls,1):
            port=min((p for p in ports if p["id"] not in selected),
                     key=lambda p:(math.dist(p["xy"],end["xy"]),p["id"]))
            selected.add(port["id"])
            queries.append({"query_id":f"NORTH-CONTROL-{n}",
                            "source":{"id":port["id"],"xy":port["xy"]},"target":end,
                            "scope":"LOCAL_REGION_ONLY","interpretation":"POST_FREEZE_TRAVERSABILITY_DIAGNOSTIC"})
        queries.append({"query_id":"NORTH-CONTROL-3","source":controls[0],"target":controls[1],
                        "scope":"LOCAL_REGION_ONLY","interpretation":"POST_FREEZE_TRAVERSABILITY_DIAGNOSTIC"})
    return queries


def route_export(result):
    rows=[]
    for name,v in result["variants"].items():
        for q, value in v["routes"].items():
            for n,e in enumerate(value["edges"]):
                rows.append(feature(LineString(e["xy"]),role="route_segment",variant=name,query_id=q,sequence=n,
                                    **{k:v for k,v in e.items() if k not in {"xy","sequence"}}))
    return fc(rows)


def memory():
    try:
        import psutil
    except ImportError:
        return None
    result=psutil.Process().memory_info()
    return getattr(result,"peak_wset",result.rss)


def natural(root,out,cfg,legacy):
    from src.run_inference import make_observation
    from src.semantics import build_native, load_area_graph
    from inputs.rev1.src.route_measure import overlay

    start=perf_counter()
    gate=read(root/"audits/S_FREEZE.json")
    if gate["status"]!="S1_FROZEN_INDEPENDENT_CHECK_PASS":
        raise ValueError("Independent S1 freeze is required before I")
    rev=root/"inputs/rev1"
    frozen=rev/"frozen_r4"
    scene=next(s for s in read(frozen/"runs/source_scene_contracts.json")["scenes"] if s["scene_id"]=="sh-huangpu-01")
    exit_ref=next(d for d in scene["r4_entrances"] if d["native_id"]=="node/6897145227")
    network=build_native(frozen,scene,"S1")
    graph=overlay(network.graph,[load_area_graph(rev,scene["scene_id"],{"relation/2153738"})])
    adapted=make_observation(scene,graph,network,exit_ref,legacy)
    door=adapted.pop("target")
    origin=adapted.pop("origin")
    if door["tags"].get("entrance")!="exit":
        raise ValueError("Registered exit identity changed")
    observed={k:adapted[k] for k in ("task_id","crs","nodes","edges","context")}
    observed.update(domain={"anchor_xy":door["xy"],"anchor_role":"REGISTERED_DOOR_FIXED_30M"},
                    registered_entrance=door)
    del network,graph,adapted
    variants=cfg["case_variants"]
    base,surfaces,stages=stage_surfaces(observed,cfg,variants,out,False)
    surface,regional=surfaces["I-REGION"]
    write(out/"data/north_surface_freeze.json",{"status":"FROZEN_BEFORE_QUERY_CONSTRUCTION","stages":stages,
                                                "anchor":observed["domain"],"config_sha256":file_sha(root/"config/region.json")})
    queries=queries_for_north(observed,regional.interfaces,origin,surface)
    write(out/"data/north_queries.json",{"queries":queries,"region_sha256":surface.sha256})
    values=run_variants(observed,base,surfaces,queries,variants,cfg,legacy)
    for mode,key in (("S0","B0"),("S1","S1")):
        values.setdefault(key,{"routes":{q["query_id"]:empty("NO_REGION_GRAPH") for q in queries}})
        values[key]["routes"]["NORTH-DOOR"]=s_prefix(root,mode,door)
    for key in REGIONS:
        q=values[key]["routes"]["NORTH-DOOR"]
        if not q["reached"]:
            values[key]["routes"]["NORTH-DOOR"]={**s_prefix(root,"S1",door),"status":"APPROACH_WITH_GAP",
                                                 "condition_graph_failure":q["status"],
                                                 "surface_sha256":surfaces[key][0].sha256}
    for variant in values.values():
        for value in variant["routes"].values():
            totals={}
            for edge in value["edges"]:
                kind=edge["geometry_kind"]
                totals[kind]=totals.get(kind,0)+edge["length_m"]
            value["geometry_kind_lengths"]=totals
    observed_reach=nx.descendants(base,origin) | {origin}
    for v in REGIONS:
        values[v]["graph"]["interfaces_reachable_on_S1"]=sum(p["id"] in observed_reach for p in values[v]["interfaces"])
    result={"status":"NATURAL_DEVELOPMENT","crs":"EPSG:32651","surface":summarize(surface),"queries":queries,
            "variants":values,"target":door,"entrance_role":"exit","inbound_eligibility":"NOT_ELIGIBLE_EXIT",
            "field_validation":"NOT_VERIFIED","S1_graph":{"nodes":len(base),"edges":base.number_of_edges()},
            "elapsed_s":perf_counter()-start,"peak_working_set_bytes":memory(),"external_requests":0}
    write(out/"runs/north.json",result,True)
    write(out/"data/north_domain.geojson",fc([feature(surface.domain,role="SEARCH_DOMAIN_ONLY",radius_m=cfg["domain_radius_m"],
                                                       area_m2=surface.domain.area)]))
    write(out/"data/north_sources.geojson",fc([
        feature(row["g"],role=layer,source_id=row["id"],kind=row["kind"],tags=row.get("tags",{}))
        for layer,rows in surface.context.items() for row in rows]),True)
    markers=[feature(Point(door["xy"]),role="registered_exit",id=door["id"],source_id=door["id"],tags=door["tags"]),
             feature(Point(queries[0]["source"]["xy"]),role="start",id=origin,source_id=origin)]
    controls={end["id"]:end for q in queries for end in (q["source"],q["target"]) if end.get("role")=="CONTROL_INTERIOR_POINT"}
    markers.extend(feature(Point(p["xy"]),role="query_endpoint",id=p["id"],source_id=p["id"],
                           interpretation="CONTROL_POINT_NOT_ENTRANCE") for p in controls.values())
    markers.extend(feature(Point(p["xy"]),role="network_interface",variant=k,**p)
                   for k,v in values.items() for p in v.get("interfaces",[]))
    write(out/"data/north_interfaces.geojson",fc(markers))
    write(out/"data/north_routes.geojson",route_export(result),True)
    print(json.dumps({"surface":result["surface"],"graph":values["I-REGION"]["graph"],
                      "routes":{k:{qid:(q["status"],q["length_m"],q["layer_lengths"]) for qid,q in v["routes"].items()}
                                for k,v in values.items()}},ensure_ascii=False))


def safe_read(path,role):
    if path.parent.name!=role or path.is_symlink() or path.parent.is_symlink() or path.suffix!=".json":
        raise ValueError("Controlled runtime accepts only role-bound task JSON")
    data=path.read_bytes()
    return json.loads(data),{"role":role,"path":f"{role}/{path.name}","sha256":sha256(data).hexdigest()}


def controlled(observed_file,queries_file,out,cfg,legacy,confirm=False):
    start=perf_counter()
    observed,obs_log=safe_read(observed_file,"observed")
    variants=("S1","I-LINE","I-REGION") if confirm else cfg["case_variants"]
    base,surfaces,stages=stage_surfaces(observed,cfg,variants,out,True)
    # No query file is opened until both the surface and its source-only reusable graph exist.
    query_doc,query_log=safe_read(queries_file,"queries")
    if query_doc["task_id"]!=observed["task_id"] or observed["task_id"]!=observed_file.stem:
        raise ValueError("Task identity differs")
    queries=query_doc["queries"]
    for q in queries:
        for end in (q["source"],q["target"]):
            if end["id"] in base and math.dist(base.nodes[end["id"]]["xy"],end["xy"])>1e-6:
                raise ValueError("Query changed a visible endpoint")
            if observed["registered_entrance"] and end["id"]==observed["registered_entrance"]["id"]:
                end.update(role="REGISTERED_DOOR",tags=observed["registered_entrance"]["tags"])
    results=run_variants(observed,base,surfaces,queries,variants,cfg,legacy)
    payload={"task_id":observed["task_id"],"variants":results,"queries":queries,
             "read_log":[dict(row,sequence=n) for n,row in enumerate([obs_log,*stages,query_log],start=1)],
             "elapsed_s":perf_counter()-start,"peak_working_set_bytes":memory(),"external_requests":0}
    write(out/"runs/benchmark"/f"{observed['task_id']}.json",payload,True)
    return observed["task_id"],summarize(surfaces["I-REGION"][0]),len(queries)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("north","controlled"))
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path)
    p.add_argument("--observed",type=Path)
    p.add_argument("--queries",type=Path)
    p.add_argument("--confirmation",action="store_true")
    p.add_argument("--sensitivity")
    a=p.parse_args()
    cfg=read(a.root/"config/region.json")
    legacy=read(a.root/"config/inference.json")["main"]
    out=a.out or a.root
    if a.sensitivity:
        settings=next(r for r in cfg["development_sensitivities"] if r["id"]==a.sensitivity)
        cfg.update({k:v for k,v in settings.items() if k!="id"})
        cfg["case_variants"]=["I-REGION"]
        if a.confirmation or a.mode!="controlled":
            p.error("Sensitivity is development/selection only")
    if a.mode=="north":
        natural(a.root,out,cfg,legacy)
    else:
        if not a.observed or not a.queries:
            p.error("Explicit observed and query paths are required")
        print(json.dumps(controlled(a.observed,a.queries,out,cfg,legacy,a.confirmation),ensure_ascii=False))
