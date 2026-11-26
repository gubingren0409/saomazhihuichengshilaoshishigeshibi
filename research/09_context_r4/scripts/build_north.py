"""Stage unmasked E5 local observation and separately bind the unchanged S1 full route graph."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from shapely.geometry import LineString, Point

ROOT=Path(__file__).resolve().parents[1]
FROZEN=ROOT/"frozen_r3"
sys.path.insert(0,str(FROZEN))
from src.run_inference import make_observation
from src.semantics import build_native, load_area_graph
from inputs.rev1.src.route_measure import overlay

RADIUS=160


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf8",newline="\n") as f:
        json.dump(data,f,ensure_ascii=False,separators=(",",":"))
        f.write("\n")
    return sha256(path.read_bytes()).hexdigest()


def main():
    rev=FROZEN/"inputs/rev1"
    raw=rev/"frozen_r4"
    scene=next(s for s in read(raw/"runs/source_scene_contracts.json")["scenes"] if s["scene_id"]=="sh-huangpu-01")
    raw_exit=next(r for r in scene["r4_entrances"] if r["native_id"]=="node/6897145227")
    s1=build_native(raw,scene,"S1")
    north_area=load_area_graph(rev,scene["scene_id"],{"relation/2153738"})
    graph=overlay(s1.graph,[north_area])
    legacy=read(FROZEN/"config/inference.json")["main"]
    obs=make_observation(scene,graph,s1,raw_exit,dict(legacy,radius_m=RADIUS))
    door=obs["target"]
    if door["id"]!="node/6897145227" or door["tags"].get("entrance")!="exit":
        raise ValueError("Original registered exit changed")
    center=Point(door["xy"])
    circle=center.buffer(RADIUS,quad_segs=64)
    nodes={n["id"]:n for n in obs["nodes"]}
    x0,y0,x1,y1=circle.bounds
    local,edges={},[]
    for e in obs["edges"]:
        a,b=nodes[e["u"]]["xy"],nodes[e["v"]]["xy"]
        if max(a[0],b[0])<x0 or min(a[0],b[0])>x1 or max(a[1],b[1])<y0 or min(a[1],b[1])>y1:
            continue
        line=LineString([a,b])
        part=line.intersection(circle)
        if part.geom_type!="LineString" or part.length<=1e-6:
            continue
        seq=list(part.coords)
        if line.project(Point(seq[0]))>line.project(Point(seq[-1])):
            seq.reverse()
        ids=[]
        for coord,orig in zip((seq[0],seq[-1]),(e["u"],e["v"])):
            if Point(coord).distance(Point(nodes[orig]["xy"]))<=1e-6:
                ident=orig
                local[ident]=dict(nodes[orig],endpoint_kind="NATIVE_ENDPOINT" if orig.startswith("node/") else "FROZEN_FACE_NODE")
            else:
                bind="-".join(sorted([e["u"],e["v"]]))
                key=sha256(f"{bind}:{coord[0]:.6f}:{coord[1]:.6f}".encode()).hexdigest()[:22]
                ident="context/"+key
                local[ident]={"id":ident,"xy":coord,"tags":{},"endpoint_kind":"CONTEXT_CLIP_ENDPOINT"}
            ids.append(ident)
        edges.append(dict(e,u=ids[0],v=ids[1]))
    scoped={"task_id":"NORTH_160","crs":obs["crs"],
            "domain":{"anchor_xy":door["xy"],"anchor_role":"REGISTERED_DOOR_FIXED_30M"},
            "registered_entrance":door,"nodes":[local[k] for k in sorted(local)],"edges":edges,"context":obs["context"]}
    archived=read(FROZEN/"runs/north.json")
    queries={"queries":archived["queries"],"task_id":"NORTH"}
    full={"nodes":obs["nodes"],"edges":obs["edges"]}
    record={"id":"NORTH_160","parent_task_id":"NORTH","masking_mode":"UNMASKED_NORTH_E5","context_radius_m":160,
            "natural":True,"historical_route_graph":"FROZEN_S1_WITH_R4_REV1_NORTH_FACE_ONLY",
            "entrance_role":"exit","inbound_eligibility":"NOT_ELIGIBLE_EXIT","field_validation":"NOT_VERIFIED"}
    for key,path,data in (("observed","data/e5/observed/NORTH_160.json",scoped),
                          ("query","data/e5/queries/NORTH.json",queries),
                          ("route_graph","data/e5/north_route_graph.json",full)):
        record[key]=path
        record[key+"_sha256"]=put(ROOT/path,data)
    put(ROOT/"data/e5/task_manifest.json",{"instances":[record]})
    print(json.dumps({"visible_nodes":len(local),"visible_arcs":len(edges),"route_only_nodes":len(nodes),
                      "route_only_arcs":len(obs["edges"]),"queries":len(queries["queries"]),"entrance":door},ensure_ascii=False))


if __name__=="__main__":
    main()
