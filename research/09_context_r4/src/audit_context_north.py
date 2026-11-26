"""Independently check natural E5 against frozen north routes and original exit."""
import argparse
from pathlib import Path
import sys

from shapely.geometry import Point, shape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.context_audit_common import AREA_TOL, LENGTH_TOL, ROOT, RawClip, hash_file, read, require, write
from src.score_context import compare_routes, score_routes, surface_shapes


def main(args):
    root=args.root.resolve()
    e5=read(root/"data/e5/task_manifest.json")["instances"][0]
    fields=("observed","query","route_graph")
    require(all(hash_file(root/e5[k])==e5[k+"_sha256"] for k in fields),"Natural E5 inputs differ from binding")
    obs,queries_doc,network=[read(root/e5[k]) for k in fields]
    archive=read(root/"frozen_r3/runs/north.json")
    archive_routes=archive["variants"]["I-REGION"]["routes"]
    old_s1=read(root/"frozen_r3/audits/S_FREEZE.json")
    target=obs["registered_entrance"]
    raw=RawClip(root/"frozen_r3/inputs/rev1/frozen_r4/data/source/sh-huangpu-01.osm.json")
    source=raw.objects[target["id"]]
    require(target["id"]=="node/6897145227" and source.get("tags",{}).get("entrance")=="exit" and
            target["wgs84"]==[source["lon"],source["lat"]] and
            Point(target["xy"]).distance(Point(raw.node(target["id"])))<=LENGTH_TOL,
            "Natural exit identity, coordinate, or role changed")
    require(queries_doc["queries"]==archive["queries"],"Natural E5 altered original fixed query objects")
    graph={**network,"context":obs["context"]}
    circle=Point(obs["domain"]["anchor_xy"]).buffer(30,quad_segs=32)
    out={}
    for method in ("M0","M1"):
        r=read(root/"data/predictions/NORTH_160"/(method+".json"))
        actual=[v for v in r["read_log"] if not v["role"].startswith("DENIED_")]
        roles=[v["role"] for v in actual]
        freeze=roles.index("SURFACE_FROZEN")
        index=roles.index("E5_ROUTE_ONLY_GRAPH")
        require(index>freeze and actual[index]["sha256"]==e5["route_graph_sha256"],
                "Natural full graph reached surface calculation")
        require(shape(r["surface"]["domain"]).symmetric_difference(circle).area<=AREA_TOL,
                "Natural E5 domain changed")
        masks,areas,trace=surface_shapes(r,obs,circle)
        baseline=score_routes(r["base_routes"],queries_doc["queries"],graph,None,circle,retain_frozen_derived=True)
        result=score_routes(r["routes"],queries_doc["queries"],graph,masks,circle,retain_frozen_derived=True)
        compared=compare_routes(result,baseline)
        archive_exact=all(r["routes"][q]["edges"]==archive_routes[q]["edges"] for q in archive_routes)
        if method=="M0":
            require(archive_exact and r["surface"]["sha256"]==archive["surface"]["sha256"],
                    "Frozen M0 natural route or surface does not reproduce R3")
        require(not any(v["conditional_conflicts"] for v in compared),
                "Natural E5 route crossed a known local hard constraint")
        out[method]={"surface_sha256":r["surface"]["sha256"],"areas_m2":areas,
                     "fixed_queries":len(compared),"replayed_original_route_segments_exactly":archive_exact,
                     "routes":compared,"surface_before_full_route_graph":True,"trace":trace}
    write(args.out or root/"audits/context_north_independent.json",{
        "status":"INDEPENDENT_NORTH_EXIT_AND_E5_GEOMETRY_PASS","result_type":"UNMASKED_NATURAL_DIAGNOSTIC",
        "raw_clip_sha256":raw.sha256,"fixed_exit":{"id":target["id"],"wgs84":target["wgs84"],"tags":target["tags"]},
        "inbound_eligibility":"NOT_ELIGIBLE_EXIT","field_validation":"NOT_VERIFIED",
        "frozen_s1_prior_audit_status":old_s1["status"],
        "results":out,
        "scope":"Raw exit, frozen query objects, full path continuity/edge geometry, inferred class/length and locally observed restrictions; no physical field verification."})
    print(f"E5 verified original exit and {len(queries_doc['queries'])} fixed routes per method",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path)
    main(p.parse_args())
