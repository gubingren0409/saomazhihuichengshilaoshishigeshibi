"""Independent metric-only scoring of frozen free-space predictions.

No predictor, classifier, or routing function is imported. References are opened
only here, after prediction files already exist. All geometry is EPSG:32651.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from shapely import union_all
from shapely.geometry import GeometryCollection, LineString, Point, shape

ATOL = 1e-5
LTOL = 1e-5
STATES = ("NATIVE_WALKABLE", "INFERRED_WALKABLE", "RESTRICTED", "UNKNOWN")
PRIMARY = ("M1-C", "F0", "F1")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def csv_write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v, ensure_ascii=False, separators=(",", ":")) if isinstance(v, (list, dict)) else v
                             for k,v in row.items()})


def cell_surface(run):
    surface = run["surface"]
    cells = surface["cells"]
    require(canonical_sha(cells) == surface["sha256"], "Surface content hash mismatch")
    geometries = {s:[] for s in STATES}
    ids = set()
    for cell in cells:
        require(cell["region_id"] not in ids, "Duplicate region id")
        ids.add(cell["region_id"])
        geom = shape(cell["geometry"])
        require(geom.is_valid and not geom.is_empty, "Invalid region geometry")
        require(geom.geom_type in {"Polygon", "MultiPolygon"}, "Non-area region")
        i,j = cell["ij"]
        x0,y0,x1,y1 = geom.bounds
        require(min(x0-i, y0-j, i+1-x1, j+1-y1) >= -LTOL, "Region outside fixed global 1m grid")
        geometries[cell["walkability_state"]].append(geom)
    masks = {k:union_all(v) for k,v in geometries.items()}
    domain = shape(surface["domain"])
    merged = union_all(list(masks.values()))
    require(domain.symmetric_difference(merged).area <= ATOL, "Cells do not cover exact fixed domain")
    require(abs(sum(g.area for g in masks.values())-merged.area) <= ATOL, "Surface states overlap")
    return masks, domain


def score_reference(run, reference):
    masks,domain = cell_surface(run)
    require(domain.symmetric_difference(shape(reference["domain_geometry"])).area <= ATOL,
            "Prediction and frozen reference domains differ")
    assumed = masks["INFERRED_WALKABLE"]
    reference_geom = shape(reference["geometry"]).intersection(domain)
    negative = reference["label"] == "NEGATIVE"
    is_line = reference["kind"].startswith("LINE_")
    row = {"evaluation_area_m2":domain.area, "native_area_m2":masks["NATIVE_WALKABLE"].area,
           "assumed_area_m2":assumed.area, "restricted_area_m2":masks["RESTRICTED"].area,
           "unknown_area_m2":masks["UNKNOWN"].area,
           "reference_area_m2":None, "reference_area_covered_m2":None, "area_recall":None,
           "reference_length_m":None, "reference_length_covered_m":None, "line_recall":None,
           "unverified_expansion_m2":None, "negative_overlap_m2":None, "negative_false_walkable":None}
    if negative:
        hit = assumed.intersection(reference_geom).area
        row.update(negative_overlap_m2=hit, negative_false_walkable=hit > ATOL)
    elif is_line:
        length = reference_geom.length
        covered = assumed.intersection(reference_geom).length
        row.update(reference_length_m=length, reference_length_covered_m=covered,
                   line_recall=covered/length if length else None)
        for radius in (.5,1.,2.):
            proxy = reference_geom.buffer(radius, cap_style="flat").intersection(domain)
            name = str(radius).replace(".", "p")
            row[f"line_proxy_{name}_area_m2"] = proxy.area
            row[f"line_proxy_{name}_covered_m2"] = assumed.intersection(proxy).area
            row[f"line_proxy_{name}_unverified_expansion_m2"] = assumed.difference(proxy).area
    else:
        area = reference_geom.area
        covered = assumed.intersection(reference_geom).area
        row.update(reference_area_m2=area, reference_area_covered_m2=covered,
                   area_recall=covered/area if area else None,
                   unverified_expansion_m2=assumed.difference(reference_geom).area)
    return row, masks, domain


def directional_sources(observed,needed_ids=None,needed_sources=None):
    nodes = {r["id"]:r for r in observed["nodes"]}
    by_id = defaultdict(list)
    by_source = defaultdict(list)
    for edge in observed["edges"]:
        key = source_identity(edge.get("source_id", edge["id"]))
        if needed_ids is not None and edge["id"] not in needed_ids and key not in (needed_sources or set()):
            continue
        points = edge.get("xy") or [nodes[edge["u"]]["xy"], nodes[edge["v"]]["xy"]]
        line = LineString(points)
        by_id[edge["id"]].append((line,edge))
        by_source[key].append((line,edge))
    return by_id,by_source


def source_identity(value):
    match=re.match(r"(?:node|way|relation)/\d+",str(value))
    return match.group() if match else str(value)


def access_area_records(registry,clip):
    return [{**row,"g":shape(row["geometry"]),"inner":shape(row["geometry"]).buffer(-LTOL)}
            for row in registry.get("areas",[]) if row["source_clip"]==clip]


def qualified_native_boundary(edge,line,area,source_edge):
    """A specific exact source footpath boundary exception, never a free area."""
    if not source_edge or line.length<=LTOL or area["inner"].intersection(line).length>LTOL:
        return False
    for exception in area.get("boundary_exceptions",[]):
        if source_identity(edge.get("source_id",""))!=exception["allowed_source_footway_id"]:
            continue
        if exception.get("allowed_source_tags",{}).get("foot")!="yes":
            continue
        boundary=shape(exception["geometry"])
        if line.difference(boundary.buffer(LTOL)).length<=LTOL:
            return True
    return False


def source_access_metrics(metrics,masks,domain,reference,areas):
    restricted=union_all([r["g"] for r in areas]).intersection(domain)
    assumed=masks["INFERRED_WALKABLE"]
    metrics.update(source_known_restricted_area_in_domain_m2=restricted.area,
                   source_known_permission_conflict_area_m2=assumed.intersection(restricted).area,
                   source_known_permission_conflict_ids=[r["source_id"] for r in areas if assumed.intersection(r["g"]).area>ATOL])
    if reference is None:
        return
    if restricted.is_empty or restricted.area<=ATOL:
        # No source access area reaches this D. Preserve the already-scored
        # reference difference instead of asking GEOS to overlay an empty mask
        # against a near-coincident reference ring a second time.
        if reference["kind"].startswith("LINE_"):
            for radius in (.5,1.,2.):
                name=str(radius).replace(".","p")
                metrics[f"line_proxy_{name}_raw_off_reference_area_m2"]=metrics[f"line_proxy_{name}_unverified_expansion_m2"]
                metrics[f"line_proxy_{name}_known_conflict_off_reference_m2"]=0.
        elif reference["label"]!="NEGATIVE":
            metrics["raw_off_reference_area_m2"]=metrics["unverified_expansion_m2"]
            metrics["source_known_conflict_off_reference_m2"]=0.
        return
    ref=shape(reference["geometry"]).intersection(domain)
    if reference["kind"].startswith("LINE_"):
        for radius in (.5,1.,2.):
            name=str(radius).replace(".","p")
            proxy=ref.buffer(radius,cap_style="flat").intersection(domain)
            outside=assumed.difference(proxy)
            metrics[f"line_proxy_{name}_raw_off_reference_area_m2"]=outside.area
            metrics[f"line_proxy_{name}_known_conflict_off_reference_m2"]=outside.intersection(restricted).area
            metrics[f"line_proxy_{name}_unverified_expansion_m2"]=outside.difference(restricted).area
    elif reference["label"]!="NEGATIVE":
        outside=assumed.difference(ref)
        metrics["raw_off_reference_area_m2"]=outside.area
        metrics["source_known_conflict_off_reference_m2"]=outside.intersection(restricted).area
        metrics["unverified_expansion_m2"]=outside.difference(restricted).area


def has_conflict(line, obstacle):
    if obstacle.area:
        return line.intersection(obstacle.buffer(-LTOL)).length > LTOL
    if obstacle.length:
        return line.crosses(obstacle) or line.intersection(obstacle).length > LTOL
    return line.distance(obstacle) <= LTOL


def route_scores(run, queries, observed, masks, domain, *, natural=False, route_graph=None,access_areas=None):
    source = route_graph if natural and route_graph else observed
    source_segments=[edge for result in run["routes"].values() for edge in result["edges"] if edge["layer"]=="native" or
                     natural and edge["layer"]=="derived" and edge.get("geometry_kind", "").startswith("DERIVED_FROM_")]
    needed_ids={edge["edge_id"] for edge in source_segments if edge.get("edge_id")}
    needed_sources={source_identity(edge.get("source_id", "")) for edge in source_segments if not edge.get("edge_id")}
    by_id,by_source = directional_sources(source,needed_ids,needed_sources)
    hard = [(r["id"],shape(r["geometry"])) for r in observed.get("context",{}).get("hard",[])]
    area_by_id={r["source_id"]:r for r in (access_areas or [])}
    expected = {q["query_id"] for q in queries}
    require(set(run["routes"]) == expected, "Frozen query set dropped/replaced")
    outcomes = {}
    for q in queries:
        qid = q["query_id"]
        result = run["routes"][qid]
        last = q["source"]["xy"]
        lengths = Counter()
        cost = 0.
        outside = 0.
        source_failures = []
        conflicts = set()
        access_conflicts=set()
        boundary_uses=[]
        for edge in result["edges"]:
            coords = edge["xy"]
            require(math.dist(last,coords[0]) <= LTOL, f"Discontinuous route {qid}")
            last = coords[-1]
            line = LineString(coords)
            require(abs(line.length-edge["length_m"]) <= LTOL, f"Stored edge length mismatch {qid}")
            layer = edge["layer"]
            lengths[layer] += line.length
            multiplier=run.get("lambda_value",1) if layer in {"inferred","assumed","unknown"} else 1
            require(abs(edge["cost_m"]-line.length*multiplier)<=LTOL,
                    f"Finite cost contract violated {run['method']}/{qid}")
            cost += edge["cost_m"]
            outside += line.difference(domain).length
            source_edge = layer == "native" or (natural and layer == "derived" and
                           edge.get("geometry_kind", "").startswith("DERIVED_FROM_"))
            if source_edge and line.length > LTOL:
                eid = edge.get("edge_id")
                source_id = source_identity(edge.get("source_id", ""))
                candidates = by_id.get(eid, []) or by_source.get(source_id, [])
                valid = any(g.buffer(LTOL).covers(line) and candidate.get("tags",{})==edge.get("tags",{}) and
                            g.project(Point(coords[-1]))-g.project(Point(coords[0])) > 0 for g,candidate in candidates)
                if not valid:
                    source_failures.append({"edge_id":eid,"source_id":source_id})
            if not source_edge and line.length > LTOL:
                require(line.difference(domain.buffer(LTOL)).length <= LTOL, f"New free edge outside 30m {qid}")
                if layer in {"inferred","assumed"}:
                    require(line.difference(masks["INFERRED_WALKABLE"].buffer(LTOL)).length <= LTOL,
                            f"Assumed route outside frozen assumed cells {qid}")
                elif layer == "derived":
                    require(line.difference(masks["NATIVE_WALKABLE"].buffer(LTOL)).length <= LTOL,
                            f"Mapped-area route outside native face {qid}")
            elevated = any(edge.get("tags",{}).get(k) not in {None,"","0","no",0}
                           for k in ("bridge","tunnel","layer","level"))
            for ident,geom in hard:
                if line.length > LTOL and has_conflict(line,geom) and not (source_edge and elevated):
                    interpreted=area_by_id.get(ident)
                    if interpreted is not None and qualified_native_boundary(edge,line,interpreted,source_edge):
                        boundary_uses.append({"source_access_area":ident,"source_footway_id":source_identity(edge["source_id"]),
                                              "length_m":line.length,"basis":"EXACT_SHARED_ORIGINAL_FOOT_YES_BOUNDARY_LINE_ONLY"})
                        continue
                    conflicts.add(ident)
            for area in access_areas or []:
                if line.intersection(area["inner"]).length>LTOL:
                    access_conflicts.add(area["source_id"])
        residual = math.dist(last,q["target"]["xy"])
        reached = bool(result["edges"] or q["source"]["id"] == q["target"]["id"]) and residual <= LTOL
        require(reached == bool(result["reached"]), f"Actual terminal mismatch {qid}")
        if result.get("length_m") is not None:
            require(abs(sum(lengths.values())-result["length_m"]) <= LTOL, f"Stored total route length mismatch {qid}")
            require(abs(cost-result["cost_m"]) <= LTOL, f"Stored route cost mismatch {qid}")
        baseline = run.get("base_routes",{}).get(qid,{})
        baseline_evaluated=bool(baseline) and baseline.get("status") not in {"NO_REGION_GRAPH","NOT_EVALUATED"}
        assumed = lengths["inferred"] + lengths["assumed"]
        unknown = lengths["unknown"]
        outcomes[qid] = {"query_id":qid,"status":result["status"],"reached":reached,
                         "valid_reached":reached and not (source_failures or conflicts or access_conflicts),
                         "source_failures":source_failures,"hard_conflicts":sorted(conflicts),
                         "source_access_interior_conflicts":sorted(access_conflicts),
                         "source_access_boundary_exceptions":boundary_uses,
                         "length_m":result.get("length_m"),"cost":result.get("cost_m"),
                         "native_m":lengths["native"],"mapped_area_derived_m":lengths["derived"],
                         "assumed_m":assumed,"bounded_unknown_m":unknown,
                         "assumed_fraction":assumed/sum(lengths.values()) if lengths else None,
                         "source_supported_fraction":(lengths["native"]+lengths["derived"])/sum(lengths.values()) if lengths else None,
                         "outside_domain_m":outside,"residual_m":residual,
                         "baseline_reached":bool(baseline.get("reached")) if baseline_evaluated else None,
                         "baseline_evaluation_status":"EVALUATED_NATIVE_GRAPH" if baseline_evaluated else "NOT_EVALUATED_LOCAL_REGION_ONLY",
                         "new_vs_native":baseline_evaluated and reached and not baseline.get("reached",False) and assumed > LTOL,
                         "outer_native_detour_only":reached and assumed <= LTOL and unknown <= LTOL and outside > LTOL}
    return outcomes


def aggregate(rows):
    group = defaultdict(list)
    for row in rows:
        group[(row["panel"],row["method"],row["reference_type"])].append(row)
    outputs = []
    for key, values in sorted(group.items()):
        def total(name):
            return sum(r["metrics"].get(name) or 0 for r in values)
        routes = [v for r in values for v in r["routes"].values()]
        area, length = total("reference_area_m2"), total("reference_length_m")
        outputs.append({"panel":key[0],"method":key[1],"reference_type":key[2],"parents":len(values),
                        "reference_area_m2":area,"reference_area_covered_m2":total("reference_area_covered_m2"),
                        "area_recall":total("reference_area_covered_m2")/area if area else None,
                        "reference_length_m":length,"reference_length_covered_m":total("reference_length_covered_m"),
                        "line_recall":total("reference_length_covered_m")/length if length else None,
                        "assumed_area_m2":total("assumed_area_m2"),
                        "unverified_expansion_m2":total("unverified_expansion_m2"),
                        "negative_overlap_m2":total("negative_overlap_m2"),
                        "source_known_permission_conflict_area_m2":total("source_known_permission_conflict_area_m2"),
                        "queries":len(routes),"reached":sum(v["reached"] for v in routes),
                        "valid_reached":sum(v["valid_reached"] for v in routes),
                        "new_vs_native":sum(v["new_vs_native"] for v in routes),
                        "outer_native_detour_only":sum(v["outer_native_detour_only"] for v in routes),
                        "route_native_m":sum(v["native_m"] for v in routes),
                        "route_derived_m":sum(v["mapped_area_derived_m"] for v in routes),
                        "route_assumed_m":sum(v["assumed_m"] for v in routes)})
    return outputs


def score_main(root, *, predictions=None, manifest=None,require_main=False):
    predictions = predictions or root/"data/predictions"
    manifest = manifest or root/"data/task_manifest.json"
    inventory = read(manifest)
    instances = inventory.get("instances", inventory.get("tasks", []))
    registry_path=root/"data/access_area_interpretations.json"
    registry=read(registry_path) if registry_path.exists() else {"areas":[]}
    gap_path=root/"audits/closed_access_D30_independent.json"
    gaps=read(gap_path).get("eligible_independent_area_assumed_overlaps",[]) if gap_path.exists() else []
    gap_ids={row["id"] for row in gaps}
    rows, missing = [], []
    for task in instances:
        paths = sorted((predictions/task["id"]).glob("*.json"))
        if not paths:
            missing.append(task["id"])
            continue
        observed_path,query_path = [root/task[k] for k in ("observed", "query")]
        natural=task.get("natural",False)
        reference_path=root/task["reference"] if not natural else None
        observed,reference,queries = read(observed_path),(read(reference_path) if reference_path else None),read(query_path)["queries"]
        route_graph=read(root/task["route_graph"]) if natural else None
        access_areas=access_area_records(registry,task.get("source_clip","sh-huangpu-01.osm.json"))
        file_keys=[("observed",observed_path),("query",query_path)]
        if reference_path:
            file_keys.append(("reference",reference_path))
        for k,path in file_keys:
            require(file_sha(path) == task[k+"_sha256"], f"Frozen {k} hash changed {task['id']}")
        for path in paths:
            run = read(path)
            method = run["method"]
            if "surface" not in run or "routes" not in run:
                continue
            require(run["input_id"]==task["id"] and run["observed_sha256"]==task["observed_sha256"] and
                    run["query_sha256"]==task["query_sha256"],"Actual predictor input identity differs from frozen manifest")
            guard_path=root/task["guards"] if task.get("guards") else root/"data/common_guards_v2"/(task["id"]+".json")
            if task.get("guards_sha256"):
                require(file_sha(guard_path)==task["guards_sha256"],"Task guard binding changed")
            require(run["guards_sha256"]==file_sha(guard_path),"Actual common guard bytes differ between contract and prediction")
            open_hashes={r["role"]:r.get("sha256") for r in run["read_log"] if r.get("event")=="ACTUAL_FILE_OPEN"}
            require(open_hashes.get("OBSERVED")==task["observed_sha256"] and open_hashes.get("QUERY")==task["query_sha256"] and
                    open_hashes.get("OBSERVED_COMMON_GUARDS")==run["guards_sha256"],"Actual logged opened input bytes differ from manifest")
            if task.get("classifier_cache"):
                cache_sha=file_sha(root/task["classifier_cache"])
                require(any("CLASSIFIER_SURFACE" in k and v==cache_sha for k,v in open_hashes.items()),
                        "Actual same-observed classifier cache read differs from bound file")
            if natural:
                masks,domain=cell_surface(run)
                metrics={"evaluation_area_m2":domain.area,"native_area_m2":masks["NATIVE_WALKABLE"].area,
                         "assumed_area_m2":masks["INFERRED_WALKABLE"].area,"restricted_area_m2":masks["RESTRICTED"].area,
                         "unknown_area_m2":masks["UNKNOWN"].area}
            else:
                metrics,masks,domain = score_reference(run,reference)
            source_access_metrics(metrics,masks,domain,reference,access_areas)
            route_rows = route_scores(run,queries,observed,masks,domain,natural=natural,route_graph=route_graph,access_areas=access_areas)
            panel = "NORTH_NATURAL" if natural else "MAIN_G80_N80" if task["context_radius_m"]==80 and task["masking_mode"] in {"G","N"} else "SUPPLEMENTARY"
            rows.append({"id":task["id"],"parent_task_id":task["parent_task_id"],"panel":panel,
                         "masking_mode":task["masking_mode"],"context_radius_m":task["context_radius_m"],
                         "method":method,"reference_type":"NATURAL_NO_REFERENCE" if natural else "KNOWN_OBSTACLE" if reference["label"]=="NEGATIVE" else
                         "LINE" if reference["kind"].startswith("LINE_") else "AREA",
                         "label":reference["label"] if reference else "NATURAL","split":task.get("split","development"),
                         "common_constraint_status":"COMMON_CONSTRAINT_INCOMPLETE" if task["id"] in gap_ids else "NO_SOURCE_ACCESS_AREA_GAP_FOUND_IN_FIXED_SCOPE",
                         "surface_sha256":run["surface"]["sha256"],"prediction_sha256":file_sha(path),
                         "metrics":metrics,"routes":route_rows,"graph":run.get("graph",{})})
    require(rows,"No actual free-space prediction exists")
    if require_main:
        primary=[t for t in instances if t["context_radius_m"]==80 and t["masking_mode"] in {"G","N"}]
        index={(r["id"],r["method"]) for r in rows}
        expected={(t["id"],m) for t in primary for m in PRIMARY}
        require(len(primary)==25 and expected <= index,f"Incomplete fixed 25-parent primary matrix: {sorted(expected-index)}")
        require({("NORTH_160",m) for m in PRIMARY} <= index,"Required natural north comparison missing")
    # Matched changes retain exact query identity and distinguish selection from reachability.
    by_key = {(r["id"],r["method"]):r for r in rows}
    pairs = []
    for row in rows:
        if row["method"] not in {"F0","F1"}:
            continue
        baseline = by_key.get((row["id"],"M1-C"))
        if baseline:
            added = [q for q,v in row["routes"].items() if v["valid_reached"] and not baseline["routes"][q]["valid_reached"]]
            lost = [q for q,v in row["routes"].items() if not v["valid_reached"] and baseline["routes"][q]["valid_reached"]]
            pairs.append({"id":row["id"],"method":row["method"],"added_query_ids":added,"lost_query_ids":lost})
    out = root/"runs/free_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload={"status":"SCORED_WITH_KNOWN_COMMON_CONSTRAINT_GAP" if gaps else "INDEPENDENT_GEOMETRY_AND_ROUTE_SCORING", "reference_role":"EVALUATION_ONLY",
             "observational_status":"EXPOSED_SAME_SOURCE_PAIRED_DIAGNOSTIC", "manifest_sha256":file_sha(manifest),
             "rows":rows,"aggregate":aggregate(rows),"paired_query_changes":pairs,"missing_predictions":missing,
             "access_area_registry_sha256":file_sha(registry_path) if registry_path.exists() else None,
             "unresolved_common_constraint_gaps":gaps,
             "limitations":["Reference is incomplete map evidence, not field truth", "Unknown obstacles are not independently observed",
                            "Known obstacle controls test compliance, not universal real-world safety"]}
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    csv_write(root/"runs/paired_metrics.csv",[{k:v for k,v in r.items() if k not in {"metrics","routes","graph"}}|r["metrics"] for r in rows])
    csv_write(root/"runs/query_outcomes.csv",[{"id":r["id"],"parent_task_id":r["parent_task_id"],"panel":r["panel"],
              "method":r["method"],"label":r["label"],**q} for r in rows for q in r["routes"].values()])
    csv_write(root/"runs/cost_sensitivity.csv",[{"id":r["id"],"method":r["method"],**q} for r in rows
              if r["method"].startswith("F1") or r["method"]=="F0" for q in r["routes"].values()])
    print(json.dumps({"scored_predictions":len(rows),"aggregate":payload["aggregate"],"missing":missing},ensure_ascii=False))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--predictions",type=Path)
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--require-main",action="store_true")
    args = parser.parse_args()
    score_main(args.root.resolve(),predictions=args.predictions,manifest=args.manifest,require_main=args.require_main)
