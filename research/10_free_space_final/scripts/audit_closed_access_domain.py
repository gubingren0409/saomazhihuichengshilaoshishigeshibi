"""Independent post-prediction closed restricted source area vs fixed D30 audit."""
import argparse,json,sys
from pathlib import Path
from collections import Counter
from pyproj import Transformer
from shapely.geometry import Polygon,LineString,shape
from shapely.ops import polygonize,unary_union

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.score_free import read,file_sha,require,cell_surface

DENY={"no","private","customers","destination","delivery","permit","restricted","agricultural","forestry"}


def role(tags):
    if tags.get("area")=="yes" or tags.get("type")=="multipolygon":return "EXPLICIT_AREA"
    if tags.get("area")=="no" or "barrier" in tags or "highway" in tags:return "CLOSED_LINEAR_OBJECT_NOT_INFERRED_AS_AREA"
    if any(k in tags for k in ("building","landuse","leisure","natural")) or tags.get("amenity") in {
       "parking","parking_space","school","college","university","hospital","marketplace","grave_yard"}:
        return "IMPLICIT_AREA_TAGS"
    return "UNCERTAIN_CLOSED_RESTRICTION"


def main(a):
    root=a.root.resolve();source_dir=a.source_dir.resolve()
    tasks=[t for t in read(root/"data/task_manifest.json")["instances"] if t.get("natural") or
           t["context_radius_m"]==80 and t["masking_mode"] in {"G","N"}]
    ledgers={(v["parent_task_id"],v["masking_mode"]):v for v in
             (json.loads(s) for s in (root/"frozen_context/data/mask_dependency_ledger.jsonl").read_text(encoding="utf8").splitlines())}
    project=Transformer.from_crs(4326,32651,always_xy=True).transform
    rows=[];inventory=[]
    for clip in sorted({t.get("source_clip","sh-huangpu-01.osm.json") for t in tasks}):
        path=source_dir/clip;raw=read(path);objects={v["type"]+"/"+str(v["id"]):v for v in raw["elements"]}
        nodes={v["id"]:project(v["lon"],v["lat"]) for v in raw["elements"] if v["type"]=="node"}
        areas=[]
        for ident,obj in objects.items():
            tags=obj.get("tags",{})
            if tags.get("foot",tags.get("access")) not in DENY:continue
            if obj["type"]=="way":
                ns=obj.get("nodes",[])
                if len(ns)<4 or ns[0]!=ns[-1] or any(n not in nodes for n in ns):continue
                geom=Polygon([nodes[n] for n in ns])
            elif obj["type"]=="relation" and tags.get("type")=="multipolygon":
                rings={"outer":[],"inner":[]}
                valid=True
                for m in obj.get("members",[]):
                    if m["type"]!="way" or m.get("role","") not in {"","outer","inner"}:continue
                    way=objects.get("way/"+str(m["ref"]));ns=way.get("nodes",[]) if way else []
                    if len(ns)<2 or any(n not in nodes for n in ns):valid=False;break
                    rings[m.get("role") or "outer"].append(LineString([nodes[n] for n in ns]))
                if not valid:continue
                geom=unary_union(list(polygonize(rings["outer"]))).difference(unary_union(list(polygonize(rings["inner"]))))
            else:continue
            if geom.is_empty or not geom.is_valid:continue
            category=role(tags);areas.append((ident,tags,geom,category))
            inventory.append({"source_clip":clip,"source_sha256":file_sha(path),"source_id":ident,"tags":tags,
                              "role":category,"area_m2":geom.area})
        for task in (t for t in tasks if t.get("source_clip","sh-huangpu-01.osm.json")==clip):
            prediction=root/"data/predictions"/task["id"]/"F0.json"
            run=read(prediction);masks,domain=cell_surface(run)
            observed=read(root/task["observed"])
            visible={v["id"] for vs in observed["context"].values() for v in vs}
            ledger=ledgers.get((task["parent_task_id"],task["masking_mode"]),{})
            unavailable=set()
            for k in ("historical_hidden_way_ids","hidden_relation_member_ids","removed_context_source_ids"):
                unavailable.update(ledger.get(k,[]))
            hits=[]
            for ident,tags,g,category in areas:
                touched=g.intersection(domain).area
                if touched<=1e-5:continue
                assumed=g.intersection(masks["INFERRED_WALKABLE"]).area
                native=g.intersection(masks["NATIVE_WALKABLE"]).area
                hits.append({"source_id":ident,"tags":tags,"area_role":category,"inside_D30_m2":touched,
                             "assumed_overlap_m2":assumed,"native_area_overlap_m2":native,
                             "source_present_in_original_observed_context":ident in visible,
                             "masked_or_removed_source_identity":ident in unavailable})
            rows.append({"id":task["id"],"prediction_sha256":file_sha(prediction),"source_clip":clip,"closed_restriction_hits":hits})
    known_overlaps=[{"id":r["id"],**h} for r in rows for h in r["closed_restriction_hits"] if
                    h["assumed_overlap_m2"]>1e-5 and h["area_role"] in {"EXPLICIT_AREA","IMPLICIT_AREA_TAGS"} and
                    not h["masked_or_removed_source_identity"]]
    result={"status":"PASS_NO_KNOWN_AREA_DEFAULT_OVERLAP" if not known_overlaps else "REQUIRES_SCOPE_DECISION",
            "reviewer":"/root/free_evaluation","scope":"POST_PREDICTION_SOURCE_COMPLETENESS_DIAGNOSTIC; NO_REFERENCE_READ_OR_PREDICTION_CHANGE",
            "fixed_domains":len(rows),"closed_restricted_source_inventory":inventory,"rows":rows,
            "eligible_independent_area_assumed_overlaps":known_overlaps,
            "limitations":"Closed highway/barrier loops are retained as linear objects, not silently filled. Uncertain closed semantics are diagnostic flags. Hidden/removed source identities do not become legal new predictor constraints."}
    (root/"audits/closed_access_D30_independent.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"status":result["status"],"domains":len(rows),"source_inventory":len(inventory),"eligible_overlaps":known_overlaps},ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--root",type=Path,default=ROOT);p.add_argument("--source-dir",type=Path,required=True)
    main(p.parse_args())
