"""Keep frozen M1 separate from M1-C; score surfaces without rerunning models."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.score_free import read,require,file_sha,score_reference,csv_write


def main(args):
    root=args.root.resolve()
    old=root/"frozen_context"
    code=[]
    for name in ("region.py","context_policy.py","region_routing.py"):
        require(file_sha(root/"src"/name)==file_sha(old/"src"/name),"Historical M1 classifier/router alias changed")
        code.append({"file":"src/"+name,"sha256":file_sha(root/"src"/name)})
    rows=[]
    for task in read(root/"data/task_manifest.json")["instances"]:
        if task.get("natural") or task["context_radius_m"]!=80 or task["masking_mode"] not in {"G","N"}:continue
        current=root/"data/predictions"/task["id"]/"M1-C.json"
        if not current.exists():continue
        before=read(old/"data/predictions"/task["id"]/"M1.json")
        after=read(current)
        calibration=read(root/"data/calibration"/(task["id"]+".json"))
        rebuilt=calibration["M1"]
        require(all(rebuilt[k]==before["surface"][k] for k in ("sha256","cells","domain","grid_m")),
                "Rebuilt historical M1 authoritative cells/domain differ from frozen bytes")
        summary_error=max(abs(rebuilt["area_m2"][k]-before["surface"]["area_m2"][k]) for k in rebuilt["area_m2"])
        require(summary_error<=1e-8,"Historical M1 numeric area summary changed beyond roundoff")
        require(after["historical_m1_surface_sha256"]==before["surface"]["sha256"],"Historical surface identity metadata differs")
        reference=read(root/task["reference"])
        a,_,_=score_reference(before,reference)
        b,_,_=score_reference(after,reference)
        rows.append({"id":task["id"],"parent_task_id":task["parent_task_id"],"label":task["label"],"kind":task["kind"],
                     "historical_observed_sha256":before["observed_sha256"],"historical_surface_sha256":before["surface"]["sha256"],
                     "common_surface_sha256":after["surface"]["sha256"],"historical_cells_and_hash_match_frozen":True,
                     "classifier_execution_role":after.get("classifier_origin","CURRENT_OBSERVED_ONLY_CLASSIFIER_EXECUTION"),
                     "historical_area_summary_max_roundoff_m2":summary_error,
                     "historical_area_covered_m2":a["reference_area_covered_m2"],"common_area_covered_m2":b["reference_area_covered_m2"],
                     "historical_line_covered_m":a["reference_length_covered_m"],"common_line_covered_m":b["reference_length_covered_m"],
                     "historical_assumed_area_m2":a["assumed_area_m2"],"common_assumed_area_m2":b["assumed_area_m2"],
                     "historical_reachable":sum(v["reached"] for v in before["routes"].values()),
                     "common_reachable":sum(v["reached"] for v in after["routes"].values()),
                     "route_comparison_scope":"COMMON_ROUTER_CONSTRAINTS_AND_PURE_GEOMETRIC_COST_CHANGED; NOT_IDENTICAL_OLD_METHOD"})
    if args.require_main:require(len(rows)==25,"Incomplete historical bridge")
    payload={"status":"PASS_SCOPED","reviewer":"/root/free_evaluation","checked_inputs":len(rows),"historical_code":code,"rows":rows,
             "scope":"Authoritative cells/domain/hash byte-identical; area summaries within1e-8m²; historical route counts read from fixed outputs, not new experiment"}
    (root/"audits/historical_bridge.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    csv_write(root/"runs/historical_bridge.csv",rows)
    print("Historical/common bridge PASS",len(rows))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--require-main",action="store_true")
    main(p.parse_args())
