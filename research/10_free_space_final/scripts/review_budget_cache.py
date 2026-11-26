"""Independent stage-evidence budget bound and natural-only surface-cache audit."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.score_free import read,require,file_sha,canonical_sha


def main(args):
    root=args.root.resolve()
    old=root/"frozen_context"
    stage=root/"runs/superseded/R1_partition_defect"
    worker=stage/"interrupted_workers/W71107d26ecd_G_080_7p_zah9i"
    files=sorted(p.name for p in worker.iterdir())
    require(files==sorted(["config.json","guards.json","historical_methods.json","observed.json","query.json"]),
            "Interrupted worker no longer matches preserved pre-constraint stage")
    source=stage/"code/predict_free.py"
    text=source.read_text(encoding="utf8")
    calls=[text.index(s,text.index("def run(")) for s in
           ("m0=build_surface(","m1,features=enhance(","put('constraints.json'","mc=build_free_surface(","f0=build_free_surface(")]
    require(calls==sorted(calls),"Preserved worker call order cannot bound missing stage")
    receipt=next((stage/"runs/executions").glob("*W711*INTERRUPTED.json"))
    original=read(receipt)
    require(original["region_builds"]==4 and original["status"]=="INTERRUPTED_UPPER_BOUND","Old upper-bound receipt was rewritten")
    evidence={"original_interrupted_receipt":receipt.relative_to(root).as_posix(),"original_receipt_sha256":file_sha(receipt),
              "original_upper_bound":4,"supported_upper_bound":2,"adjustment_delta":-2,
              "reason":"Full preserved worker has only inputs; constraints write occurs after M0/M1 and before both new surfaces",
              "preserved_code_sha256":file_sha(source),"preserved_worker_inputs":[{"name":n,"sha256":file_sha(worker/n)} for n in files],
              "condition":"Affected process is stopped and preserved worker directory is complete; absence alone cannot identify how much of M0/M1 completed"}
    methods={}
    for method in ("M0","M1"):
        p=old/"data/predictions/NORTH_160"/(method+".json")
        run=read(p)
        require(run["observed_sha256"]==file_sha(root/"data/e5/observed/NORTH_160.json"),"Natural surface cache observation mismatch")
        require(canonical_sha(run["surface"]["cells"])==run["surface"]["sha256"],"Historical surface cells hash mismatch")
        events=[r for r in run["read_log"] if not r["role"].startswith("DENIED_")]
        roles=[r["role"] for r in events]
        fi=roles.index("SURFACE_FROZEN");qi=roles.index("QUERY")
        require(fi<qi and events[fi]["sha256"]==run["surface"]["sha256"],"Historical surface was not frozen before query")
        methods[method]={"source_path":p.relative_to(root).as_posix(),"source_file_sha256":file_sha(p),
                         "observed_sha256":run["observed_sha256"],"surface_sha256":run["surface"]["sha256"],
                         "historical_freeze_precedes_query":True,"surface":run["surface"]}
    require(methods["M0"]["surface"]==methods["M1"]["surface"],"Historical natural M0/M1 surfaces are not identical")
    for name in ("region.py","context_policy.py","region_routing.py"):
        require(file_sha(root/"src"/name)==file_sha(old/"src"/name),"Historical source alias changed before cache reuse")
    cache_review=None
    if args.cache:
        cache=read(args.cache)
        require(set(cache)=={"observed_sha256","classifier_bindings","M0","M1"},
                "Natural surface cache carries unexpected role/answer fields")
        require(cache["observed_sha256"]==methods["M0"]["observed_sha256"],"Staged cache observed identity mismatch")
        bindings={p:file_sha(old/p) for p in ("src/region.py","src/context_policy.py","config/frozen_region.json","config/methods.json")}
        require(cache["classifier_bindings"]==bindings,"Staged cache classifier/config bindings do not match frozen source bytes")
        surfaces=cache.get("surfaces",cache)
        for method in ("M0","M1"):
            require(surfaces[method]==methods[method]["surface"],"Staged cache not the exact frozen historical surface")
        payload=json.dumps(cache,sort_keys=True)
        require(not any('"'+field+'"' in payload for field in ("routes","base_routes","queries","reference","query_id")),
                "Historical route/query/reference leaked into pre-query surface cache")
        cache_review={"path":str(args.cache),"sha256":file_sha(args.cache),"surface_only":True,
                      "source":"EXACT_SAME_UNMASKED_NATURAL_OBSERVATION; NOT_CONTROLLED_HIDDEN_REFERENCE"}
    final={"status":"PASS_SCOPED","reviewer":"/root/free_evaluation","budget_stage_review":evidence,
           "historical_cache_candidates":{m:{k:v for k,v in row.items() if k!="surface"} for m,row in methods.items()},
           "actual_staged_cache_review":cache_review,
           "accounting_rule":"Keep original upper-bound receipt. Append -2 supported bound correction. North builds only M1-C/F0=2, F1 costs reuse graph.",
           "limits":"Does not claim interrupted M0/M1 completed; does not authorize reading historical routes or controlled answers before query"}
    (root/"audits/free_budget_cache_review.json").write_text(json.dumps(final,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("Independent natural cache/stage bound PASS",bool(cache_review))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--cache",type=Path)
    main(p.parse_args())
