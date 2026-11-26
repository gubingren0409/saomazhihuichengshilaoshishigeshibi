"""Report new graph arcs inside source-known access areas omitted from B_common."""
import json,gzip,sys,zipfile
from pathlib import Path
from shapely.geometry import LineString,shape
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.score_free import read,file_sha

def main():
    scope=read(ROOT/"audits/closed_access_D30_independent.json")
    gaps=scope["eligible_independent_area_assumed_overlaps"]
    targets=[{"id":r["id"],**h} for r in scope["rows"] for h in r["closed_restriction_hits"] if
             h["area_role"] in {"EXPLICIT_AREA","IMPLICIT_AREA_TAGS"} and not h["masked_or_removed_source_identity"]]
    areas=read(ROOT/"data/access_area_interpretations.json")["areas"]
    tasks={t["id"]:t for t in read(ROOT/"data/task_manifest.json")["instances"]}
    rows=[]
    historical=[]
    archive=ROOT/"delivery/OPEN_REVIEW_R0_PARTIAL.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as z:historical=json.loads(z.read("audits/source_access_graph_impact.json"))["rows"]
    for gap in targets:
        task=tasks[gap["id"]]
        area=next(a for a in areas if a["source_id"]==gap["source_id"] and a["source_clip"]==task["source_clip"])
        interior=shape(area["geometry"]).buffer(-1e-6)
        for method in ("M1-C","F0"):
            p=ROOT/"data/predictions"/task["id"]/(method+".json");run=read(p)
            graph_path=ROOT/run["graph"]["graph_path"]
            with gzip.open(graph_path,"rt",encoding="utf8") as f:graph=json.load(f)
            conflicts=[]
            for edge in graph["edges"]:
                for segment in edge["segments"]:
                    line=LineString(segment["xy"]);length=line.intersection(interior).length
                    if length>1e-6:
                        conflicts.append({"u":edge["u"],"v":edge["v"],"xy":segment["xy"],"layer":segment["layer"],
                                          "source_known_private_interior_length_m":length})
            prior=next((v for v in historical if v["id"]==task["id"] and v["method"]==("F0_SHARED_F1" if method=="F0" else method)),{})
            rows.append({"id":task["id"],"method":"F0_SHARED_F1" if method=="F0" else method,
                         "source_id":area["source_id"],"prediction_sha256":file_sha(p),"graph_sha256":run["graph"]["graph_sha256"],
                         "conflicting_directed_segments":len(conflicts),
                         "directed_total_private_interior_length_m":sum(x["source_known_private_interior_length_m"] for x in conflicts),
                         "historical_R0_conflicting_directed_segments":prior.get("conflicting_directed_segments"),
                         "segments":conflicts})
    payload={"status":"KNOWN_SOURCE_PERMISSION_GAP_NOT_REPAIRED" if gaps else "REPAIR_CHECK_PASSED" if all(r["conflicting_directed_segments"]==0 for r in rows) else "SOURCE_GRAPH_CONFLICT_REMAINS", "rows":rows,
             "scope":"POST_AUDIT_SOURCE_OVERLAY_ON_FROZEN_GRAPH; DIRECTED_ARCS_INCLUDE_BOTH_DIRECTIONS; NO_RECLASSIFICATION_OR_NEW_ROUTING",
             "interpretation":"Actual fixed query paths can avoid these arcs; that does not validate the entire default feasible area."}
    (ROOT/"audits/source_access_graph_impact.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"status":payload["status"],"counts":[{k:v for k,v in r.items() if k!="segments"} for r in rows]}))

if __name__=="__main__":main()
