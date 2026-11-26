"""Run one observed-only regional reconstruction in a staged working directory."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter

import networkx as nx
try:
    import psutil
except ImportError:
    psutil=None
from shapely.geometry import mapping, shape

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.context_policy import enhance
from src.region import (STATES, Surface, build_surface, context_layers, digest, union)
from src.region_routing import empty, native_graph, region_graph, route, routed_queries


class ReadGuard:
    """Application-level allowlist. No source or reference is staged."""
    def __init__(self,root):
        self.root=root
        self.phase="BEFORE_SURFACE"
        self.log=[]
        self.approved={"observed.json":"OBSERVED","local_config.json":"FROZEN_CONFIG",
                       "methods.json":"METHOD_CONTRACT","m0_surface.json":"CURRENT_M0_SURFACE_CACHE",
                       "query.json":"QUERY","route_graph.json":"E5_ROUTE_ONLY_GRAPH"}
        self.post={"query.json","route_graph.json"}
        self.output={"prediction.json","surface.freeze"}
        self.external_reads=0

    def event(self,event,args):
        if event!="open" or not isinstance(args[0],(str,bytes,os.PathLike)):
            return
        p=Path(os.fsdecode(args[0]))
        # Imports use the already-trusted interpreter and source code, never source data.
        if p.suffix.lower() in {".py",".pyc",".pyd",".dll"} and p.is_absolute() and (
                p.is_relative_to(Path(sys.base_prefix)) or
                p.is_relative_to(Path(__file__).resolve().parent)):
            return
        p=p.resolve()
        flag=args[2]
        writing=bool(flag & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if p.parent!=self.root:
            raise PermissionError("READ_OUTSIDE_WORKER_ALLOWLIST")
        if writing:
            if p.name not in self.output:
                raise PermissionError("WRITE_OUTSIDE_WORKER_ALLOWLIST")
            return
        if p.name not in self.approved:
            raise PermissionError("INPUT_ROLE_DENIED")
        if p.name in self.post and self.phase!="AFTER_SURFACE":
            raise PermissionError("QUERY_READ_BEFORE_SURFACE")
        self.log.append({"role":self.approved[p.name],"path":p.name,"event":"ACTUAL_FILE_OPEN"})

    def read(self,name):
        data=(self.root/name).read_bytes()
        if self.log[-1]["path"]!=name:
            raise RuntimeError("Input audit did not record read")
        self.log[-1]["sha256"]=sha256(data).hexdigest()
        return json.loads(data)

    def denial_probe(self,name,role):
        try:
            (self.root/name).read_bytes()
        except PermissionError as e:
            self.log.append({"role":role,"path":name,"event":"DENIED_OPEN","reason":str(e)})
        else:
            raise RuntimeError("An unauthorized open succeeded")

    def freeze(self,surface):
        data={"surface_sha256":surface.sha256,"phase":"FROZEN_BEFORE_QUERY"}
        (self.root/"surface.freeze").write_text(json.dumps(data,sort_keys=True),encoding="utf8")
        self.log.append({"role":"SURFACE_FROZEN","path":"surface.freeze","sha256":surface.sha256,
                         "event":"ACTUAL_STAGE_WRITE"})
        self.phase="AFTER_SURFACE"


def pack(surface):
    return {"sha256":surface.sha256,"domain":mapping(surface.domain),
            "cells":[{k:v for k,v in row.items() if k!="g"} for row in surface.cells],
            "area_m2":surface.area_m2,"statistics":surface.statistics,"grid_m":surface.step}


def unpack(cache,observed,cfg):
    if set(cache)!={"sha256","domain","cells","area_m2","statistics","grid_m"} or digest(cache["cells"])!=cache["sha256"]:
        raise ValueError("Current-run M0 surface cache has invalid scope or hash")
    cells=[{**c,"ij":tuple(c["ij"]),"g":shape(c["geometry"])} for c in cache["cells"]]
    domain=shape(cache["domain"])
    masks={s:union(c["g"] for c in cells if c["walkability_state"]==s) for s in STATES}
    return Surface(domain,cells,masks,context_layers(observed,domain,cfg),cache["sha256"],
                   cache["area_m2"],cache["statistics"],cache["grid_m"])


def run(args):
    start=perf_counter()
    root=Path.cwd().resolve()
    guard=ReadGuard(root)
    sys.addaudithook(guard.event)
    guard.denial_probe("reference.json","DENIED_REFERENCE_PROBE")
    guard.denial_probe("query.json","DENIED_EARLY_QUERY_PROBE")
    cfg=guard.read("local_config.json")
    contract=guard.read("methods.json")
    observed=guard.read("observed.json")
    observed_sha=guard.log[-1]["sha256"]
    if (cfg["domain_radius_m"],cfg["cell_m"],contract["score_radius_m"])!=(30,1,30):
        raise ValueError("Fixed prediction domain or grid changed")
    if args.method=="M0":
        surface=build_surface(observed,cfg)
        features={"mode":"FROZEN_LOCAL_M0","changed_cells":0,"witnesses":{}}
    else:
        m0=guard.read("m0_surface.json")
        if set(m0)!={"observed_sha256","surface"} or m0["observed_sha256"]!=observed_sha:
            raise ValueError("Only same-input, current R4 M0 cell cache may be used")
        surface,features=enhance(unpack(m0["surface"],observed,cfg),observed,cfg,contract["M1"])
    guard.freeze(surface)
    queries=guard.read("query.json")["queries"]
    query_sha=guard.log[-1]["sha256"]
    routing=guard.read("route_graph.json") if args.natural else observed
    base=native_graph(routing)
    interfaces=native_graph(observed) if args.natural else base
    region=region_graph(surface,interfaces,cfg)
    queries=[dict(q,source=dict(q["source"]),target=dict(q["target"])) for q in queries]
    door=observed["registered_entrance"]
    for q in queries:
        for field in ("source","target"):
            end=q[field]
            if door and end["id"]==door["id"]:
                end.update(role="REGISTERED_DOOR",tags=door["tags"])
    base_routes={q["query_id"]:(empty("NO_REGION_GRAPH") if q.get("scope")=="LOCAL_REGION_ONLY" else
                               route(base,q["source"]["id"],q["target"]["id"])) for q in queries}
    routes=routed_queries(base,region,queries,cfg)
    mem=psutil.Process().memory_info() if psutil is not None else None
    data={"input_id":args.input_id,"method":args.method,"context_radius_m":args.radius,
          "observed_sha256":observed_sha,"query_sha256":query_sha,
          "config_sha256":args.config_sha,"code_sha256":args.code_sha,
          "read_log":[dict(row,sequence=i) for i,row in enumerate(guard.log,1)],
          "surface":pack(surface),"routes":routes,"base_routes":base_routes,
          "graph":dict(region.stats,observed_nodes=len(interfaces),observed_arcs=interfaces.number_of_edges(),
                       routing_nodes=len(base),routing_arcs=base.number_of_edges(),
                       observed_components=nx.number_weakly_connected_components(interfaces),
                       interfaces=region.interfaces),
          "features":features,"elapsed_s":perf_counter()-start,"external_requests":0,
          "peak_working_set_bytes":getattr(mem,"peak_wset",getattr(mem,"rss",None)),
          "isolation_scope":"APPLICATION_OPEN_AUDIT_NO_RAW_SOURCE_OR_REFERENCE_STAGED"}
    with (root/"prediction.json").open("x",encoding="utf8",newline="\n") as f:
        json.dump(data,f,ensure_ascii=False,separators=(",",":"),allow_nan=False)
        f.write("\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--method",choices=("M0","M1"),required=True)
    p.add_argument("--input-id",required=True)
    p.add_argument("--radius",type=int,required=True)
    p.add_argument("--config-sha",required=True)
    p.add_argument("--code-sha",required=True)
    p.add_argument("--natural",action="store_true")
    run(p.parse_args())
