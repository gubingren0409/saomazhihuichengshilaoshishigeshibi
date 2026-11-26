"""Independently score fixed R4-CONTEXT references and route pairs in EPSG:32651."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

from shapely import segmentize, union_all
from shapely.geometry import LineString, Point, shape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.context_audit_common import (AREA_TOL, LENGTH_TOL, ROOT, STATES, district_band,
                                  hash_file, item_id, known_masks, line_pieces, read,
                                  require, source_id, visible_lines, write)


def domain_check(observed, reference, actual):
    """Same anchor and 30m polygonal disk, independent of context or display radius."""
    require(observed["crs"] == "EPSG:32651", "Unexpected observed CRS")
    fixed = Point(observed["domain"]["anchor_xy"]).buffer(30, quad_segs=32)
    ref_window = shape(reference["domain_geometry"])
    run_window = shape(actual)
    require(fixed.symmetric_difference(ref_window).area < AREA_TOL and
            fixed.symmetric_difference(run_window).area < AREA_TOL,
            "Prediction or reference window differs from fixed 30m disk")
    return fixed


def topology_witnesses(witness_counts, run, observed):
    """Independently reconstruct every used directed outer chain and its range."""
    features = run.get("features", {})
    witnesses = features.get("witnesses", {})
    require(set(witness_counts) == set(witnesses), "M1 cell and witness registries differ")
    if not witnesses:
        return {}
    graph = {row["id"]:row for row in observed["edges"]}
    nodes = {row["id"]:row for row in observed["nodes"]}
    center = Point(observed["domain"]["anchor_xy"])
    bands = Counter()
    used_ids = set()
    for ident, row in witnesses.items():
        require(row["affected_cells"]==witness_counts[ident], f"Witness affected cell count differs: {ident}")
        chain = row["node_path"]
        edges = row["fragment_ids"]
        points = row["xy"]
        require(len(chain)==len(points)==len(edges)+1 and chain[0]==row["portal_id"] and
                chain[-1]==row["junction_id"] and chain[-1].startswith("node/"),
                f"Malformed witness chain {ident}")
        require(all(v in nodes for v in chain) and all(math.dist(nodes[v]["xy"],p)<LENGTH_TOL for v,p in zip(chain,points)),
                f"Witness chain is not actual observed nodes: {ident}")
        require(all(e in graph and (graph[e]["u"],graph[e]["v"])==(a,b) for e,a,b in zip(edges,chain,chain[1:])),
                f"Witness cites an absent or oppositely directed edge {ident}")
        ways = {item_id(graph[e]) for e in edges}
        require(set(row["source_ids"])==ways, f"Witness source way list differs from actual edges: {ident}")
        path = LineString(points)
        max_radius = max(center.distance(Point(p)) for p in points)
        junction = nodes[chain[-1]]
        incident = [e for e in observed["edges"] if chain[-1] in (e["u"],e["v"])]
        linked = {k for e in incident for k in (e["u"],e["v"])} - {chain[-1]}
        require(len(linked)>=3 and len({item_id(e) for e in incident})>=2 and
                not any(token in junction.get("endpoint_kind","") for token in ("CLIP","MASK","CROP_LIMIT")) and
                center.distance(Point(junction["xy"]))>30,
                f"Witness ends at artificial or non-exterior junction {ident}")
        require(abs(path.length-row["observed_path_m"])<LENGTH_TOL and abs(max_radius-row["max_radius_m"])<LENGTH_TOL,
                f"Witness distance or length differs from coordinates: {ident}")
        band = district_band(max_radius)
        require(row["radius_band"].replace("–","-")==band, f"Witness band differs from actual range {ident}")
        bands[band] += witness_counts[ident]
        used_ids.update(ways)
    return {"witness_uses_by_band":dict(bands),"source_ids":sorted(used_ids),"witnesses":len(witnesses)}


def surface_shapes(run, observed, window):
    categories = {name: [] for name in STATES}
    observed_ids = ({item_id(row) for row in observed["edges"]} |
                    {row["id"] for row in observed["nodes"]} |
                    {row["id"] for values in observed["context"].values() for row in values})
    if observed.get("registered_entrance"):
        observed_ids.add(observed["registered_entrance"]["id"])
    row_ids = set()
    witnesses = Counter()
    cells_using_context = 0
    changed_context_area = 0.
    state_sum = Counter()
    for row in run["surface"]["cells"]:
        ident = row["region_id"]
        require(ident not in row_ids, f"Duplicate fragment {ident}")
        row_ids.add(ident)
        g = shape(row["geometry"])
        state = row["walkability_state"]
        require(g.is_valid and not g.is_empty and g.geom_type in {"Polygon", "MultiPolygon"},
                f"Invalid authoritative metric fragment {ident}")
        if "ij" in row:
            i, j = row["ij"]
        else:
            match = re.fullmatch(r"cell/(-?\d+)/(-?\d+)/\d+", ident)
            require(match is not None, f"Missing anchored grid index {ident}")
            i, j = (int(v) for v in match.groups())
        x0, y0, x1, y1 = g.bounds
        require(min(x0-i, y0-j, i+1-x1, j+1-y1) >= -LENGTH_TOL, f"Non-1m grid fragment {ident}")
        categories[state].append(g)
        state_sum[state] += g.area
        cited = set(row.get("evidence_sources", [])) | set(row.get("hard_conflicts", []))
        require(all(ident in observed_ids or source_id(ident) in observed_ids for ident in cited),
                f"Fragment {ident} cites unavailable observations: {cited-observed_ids}")
        if state == "INFERRED_WALKABLE":
            require(row.get("source_status") in (None, "inferred"), f"Unmarked inference {ident}")
        if state == "UNKNOWN":
            require(row.get("source_status") not in {"native", "inferred"}, f"UNKNOWN treated as observed {ident}")
        trace = row.get("context_witnesses", [])
        if trace:
            require(state == "INFERRED_WALKABLE" and run["method"] == "M1",
                    "Unexpected M0 or non-inference cell carrying added feature")
            witnesses.update(trace if isinstance(trace, list) else [trace])
            cells_using_context += 1
            changed_context_area += g.area
    masks = {name: union_all(items) for name, items in categories.items()}
    pooled = union_all(list(masks.values()))
    require(pooled.symmetric_difference(window).area <= AREA_TOL and
            abs(sum(state_sum.values()) - pooled.area) <= AREA_TOL,
            "Four classes do not partition exactly the fixed scoring domain")
    areas = {name: g.area for name, g in masks.items()}
    if "area_m2" in run["surface"]:
        require(all(abs(areas[k]-run["surface"]["area_m2"][k]) <= AREA_TOL for k in STATES),
                "Stored area differs from the actual polygons")
    trace = topology_witnesses(witnesses, run, observed)
    recorded = run["surface"]["sha256"]
    actual = sha256(json.dumps(run["surface"]["cells"],sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    require(recorded==actual,"Frozen cells do not match their authoritative hash")
    return masks, areas, {"cells":len(row_ids),"cells_using_context":cells_using_context,
                          "context_added_area_m2":changed_context_area, **trace}


def percentile_distance(source, target, p=.9):
    if source is None or target is None or source.is_empty or target.is_empty:
        return None
    dist = sorted(Point(xy).distance(target) for ln in line_pieces(segmentize(source, .75)) for xy in ln.coords)
    return dist[math.ceil(p*len(dist))-1] if dist else None


def score_surface(masks, areas, window, reference, observed):
    is_line = reference["kind"].startswith("LINE_")
    is_negative = reference["label"] == "NEGATIVE"
    geom = shape(reference["geometry"]).intersection(window)
    require(geom.length > LENGTH_TOL if is_line else geom.area > AREA_TOL, "Empty reference in fixed domain")
    inferred = masks["INFERRED_WALKABLE"]
    hard, fences, grass = known_masks(observed)
    known = union_all([g for _, g in hard])
    line_barriers = union_all([g for _, g in fences if g.geom_type in {"LineString","MultiLineString","LinearRing"}])
    grass_area = union_all([g for _, g in grass if g.area])
    native = masks["NATIVE_WALKABLE"]
    out = dict(
        evaluation_area_m2=window.area, states_m2=areas, inferred_area_m2=inferred.area,
        unknown_area_m2=areas["UNKNOWN"], unknown_fraction=areas["UNKNOWN"]/window.area,
        empty_inference=inferred.is_empty, reference_area_m2=None, reference_area_covered_m2=None,
        area_recall=None, reference_length_m=None, reference_length_covered_m=None, line_recall=None,
        native_or_inferred_line_recall=None, proxy_widths=[], off_reference_area_m2=None,
        hard_conflict_area_m2=inferred.intersection(known).area,
        grass_conflict_area_m2=inferred.intersection(grass_area).area,
        hard_conflict_length_m=inferred.intersection(line_barriers).length,
        known_hard_objects=[key for key, g in hard if inferred.intersection(g).area > AREA_TOL],
        known_line_barriers=[key for key, g in fences if inferred.intersection(g).length > LENGTH_TOL],
        negative_false_walkable=None, negative_overlap_m2=None,
        reference_boundary_p90_m=None, inferred_boundary_p90_m=None,
    )
    if is_line:
        covered = inferred.intersection(geom).length
        out.update(reference_length_m=geom.length, reference_length_covered_m=covered, line_recall=covered/geom.length,
                   native_or_inferred_line_recall=union_all([inferred,native]).intersection(geom).length/geom.length)
        for radius in (.5, 1., 2.):
            proxy = geom.buffer(radius, cap_style="flat").intersection(window)
            hit = proxy.intersection(inferred).area
            out["proxy_widths"].append({"buffer_radius_m":radius,"proxy_area_m2":proxy.area,
                                       "covered_area_m2":hit,"recall":hit/proxy.area,
                                       "off_proxy_reference_area_m2":inferred.difference(proxy).area})
    elif is_negative:
        area = inferred.intersection(geom).area
        out.update(negative_false_walkable=area > AREA_TOL, negative_overlap_m2=area)
    else:
        hit = inferred.intersection(geom).area
        inner = window.buffer(-.05)
        r_boundary = geom.boundary.intersection(inner)
        p_boundary = inferred.boundary.intersection(inner) if not inferred.is_empty else None
        out.update(reference_area_m2=geom.area,reference_area_covered_m2=hit,area_recall=hit/geom.area,
                   off_reference_area_m2=inferred.difference(geom).area,
                   reference_boundary_p90_m=percentile_distance(r_boundary, p_boundary),
                   inferred_boundary_p90_m=percentile_distance(p_boundary, r_boundary))
    return out


def has_conflict(path, geom):
    if geom.area:
        return path.intersection(geom.buffer(-LENGTH_TOL)).length > LENGTH_TOL
    if geom.length:
        return path.crosses(geom) or path.intersection(geom).length > LENGTH_TOL
    return path.distance(geom) <= LENGTH_TOL


def score_routes(values, queries, observed, masks, window, *, retain_frozen_derived=False):
    # Only the visible source graph can certify a native route edge.
    by_id, by_source = defaultdict(list), defaultdict(list)
    for edge, line in visible_lines(observed):
        by_id[edge["id"]].append(line)
        by_source[item_id(edge)].append(line)
    hard, barriers, _ = known_masks(observed)
    expected_ids = {row["query_id"] for row in queries}
    require(set(values) == expected_ids, "Fixed query set was dropped or replaced")
    rows = {}
    for query in queries:
        ident = query["query_id"]
        result = values[ident]
        edges = result["edges"]
        previous = query["source"]["xy"]
        ground_conflicts, conditional_conflicts = set(), set()
        lengths = Counter()
        outer = 0.
        inside_inferred = 0.
        for edge in edges:
            line = LineString(edge["xy"])
            layer = edge["layer"]
            require(math.dist(previous, edge["xy"][0]) <= LENGTH_TOL, f"Route discontinuity {ident}")
            require(abs(line.length-edge["length_m"]) <= LENGTH_TOL, f"Incorrect edge length {ident}")
            previous = edge["xy"][-1]
            lengths[layer] += line.length
            outer += line.difference(window).length
            if layer == "inferred":
                inside_inferred += line.intersection(window).length
            source_edge=(layer=="native" or (retain_frozen_derived and layer=="derived" and
                          edge.get("geometry_kind","").startswith("DERIVED_FROM_")))
            if source_edge:
                key = edge.get("edge_id")
                paths = by_id[key] if key in by_id else by_source[source_id(edge["source_id"])]
                if line.length > LENGTH_TOL:
                    require(any(g.buffer(LENGTH_TOL).covers(line) and
                                g.project(Point(line.coords[-1])) > g.project(Point(line.coords[0]))
                                for g in paths), f"Route source edge is not an observed directed edge {ident}/{key}")
            elif masks is not None and line.length > LENGTH_TOL:
                kind = edge.get("geometry_kind")
                state = {"FROZEN_INFERRED_REGION":"INFERRED_WALKABLE",
                         "BOUNDED_UNKNOWN_PORTAL":"UNKNOWN","NEW_GRID_WITHIN_MAPPED_FACE":"NATIVE_WALKABLE"}.get(kind)
                if state:
                    require(line.difference(masks[state].buffer(LENGTH_TOL)).length <= LENGTH_TOL,
                            f"Route {ident} uses wrong frozen class {state}")
                require(line.difference(window).length <= LENGTH_TOL, f"New inference leaves evaluation domain {ident}")
            elif masks is None and layer in {"inferred","unknown"}:
                raise ValueError("No-inference baseline includes a conditional edge")
            non_ground = any(edge.get("tags",{}).get(k) not in {None,"","0","no",0}
                             for k in ("bridge","tunnel","layer","level"))
            if line.length <= LENGTH_TOL:
                continue
            for key, g in hard + barriers:
                if has_conflict(line, g):
                    if not source_edge:
                        conditional_conflicts.add(key)
                    elif not non_ground:
                        ground_conflicts.add(key)
        reached = bool(edges or query["source"]["id"] == query["target"]["id"]) and (
            math.dist(previous, query["target"]["xy"]) < LENGTH_TOL)
        require(reached == bool(result["reached"]), f"Recorded endpoint reach differs {ident}")
        if result.get("length_m") is not None:
            require(abs(result["length_m"]-sum(lengths.values())) <= LENGTH_TOL, f"Incorrect total route length {ident}")
        rows[ident] = dict(query_id=ident,status=result["status"],reached=reached,
                           valid_reached=reached and not (ground_conflicts or conditional_conflicts),
                           length_m=result.get("length_m"),cost_m=result.get("cost_m"),
                           layer_lengths_m=dict(lengths),inferred_inside_m=inside_inferred,
                           outside_scoring_domain_m=outer,residual_m=math.dist(previous,query["target"]["xy"]),
                           native_conflicts=sorted(ground_conflicts),conditional_conflicts=sorted(conditional_conflicts))
    return rows


def compare_routes(candidate, baseline):
    for ident, row in candidate.items():
        base = baseline[ident]
        row["baseline_valid_reached"] = base["valid_reached"]
        row["baseline_outside_scoring_domain_m"] = base["outside_scoring_domain_m"]
        row["uses_inferred_inside"] = row["valid_reached"] and row["inferred_inside_m"] > LENGTH_TOL
        row["locally_recovered_query"] = row["uses_inferred_inside"] and not base["valid_reached"]
        row["alternative_with_inference"] = row["uses_inferred_inside"] and base["valid_reached"]
        row["native_outer_detour_only"] = (row["valid_reached"] and not row["uses_inferred_inside"] and
                                           row["outside_scoring_domain_m"] > LENGTH_TOL)
    return list(candidate.values())


def inspect_read_log(run, instance):
    events = run["read_log"]
    ordered = [r for r in events if not r.get("role","").startswith("DENIED_")]
    denials = {r.get("role") for r in events if r.get("event") == "DENIED_OPEN"}
    require({"DENIED_REFERENCE_PROBE","DENIED_EARLY_QUERY_PROBE"} <= denials,
            "Application-level forbidden reads were not demonstrated")
    require([r["sequence"] for r in events] == list(range(1,len(events)+1)), "Read log out of sequence")
    roles = [r["role"].lower() for r in ordered]
    obs_pos = next(i for i,r in enumerate(roles) if "observ" in r)
    query_pos = next(i for i,r in enumerate(roles) if "quer" in r)
    surface_pos = roles.index("surface_frozen")
    require(obs_pos < surface_pos < query_pos, "Queries preceded the surface freeze")
    require(ordered[obs_pos].get("sha256")==instance["observed_sha256"] and
            ordered[query_pos].get("sha256")==instance["query_sha256"], "File-open bytes differ from manifest")
    freeze = ordered[surface_pos]
    require(freeze.get("surface_sha256",freeze.get("sha256")) == run["surface"]["sha256"],
            "Frozen surface receipt and run identity differ")
    for event in ordered:
        role = event["role"].lower()
        if role != "surface_frozen":
            require(role in {"frozen_config","method_contract","observed","query","current_m0_surface_cache"},
                    f"Unexpected actual read role {role}")
            require(role != "current_m0_surface_cache" or run["method"]=="M1", "M0 read a cached outcome")
            path = event.get("path","").replace("\\","/").lower()
            require(not any(v in path.split("/") for v in ("reference","references","raw","frozen_r3")),
                    "Actual predictor read reached restricted source")
    return sum(r.get("role")=="DENIED_REFERENCE_PROBE" for r in events)


def typed(reference):
    if reference["label"] == "NEGATIVE":
        return "KNOWN_OBSTACLE"
    if reference["kind"].startswith("LINE_"):
        return reference["kind"]
    return "NATIVE_FACE"


def score_one(root, instance, path, lock_hashes):
    run = read(path)
    method = run["method"]
    same_worker_lock=run["code_sha256"]==lock_hashes["code"] and run["config_sha256"]==lock_hashes["config"]
    earlier_original_export=False
    if not same_worker_lock and "H0_ORIGINAL_EXPORT" in instance["id"] and method=="M0":
        receipt=read(root/"runs/execution_e0_M0.json")
        old=next(v for v in receipt["runs"] if v["id"]==instance["id"])
        earlier_original_export=(receipt["code_sha256"]==run["code_sha256"] and
                                 receipt["config_sha256"]==run["config_sha256"] and
                                 old["prediction_sha256"]==hash_file(path))
    require(method==path.stem and (same_worker_lock or earlier_original_export),
            f"Frozen worker method/code/config does not match recorded run {instance['id']}")
    require(run["input_id"] == instance["id"] and run["context_radius_m"] == instance["context_radius_m"],
            "Run identity/radius differ from observed contract")
    require(run["observed_sha256"]==instance["observed_sha256"] and run["query_sha256"]==instance["query_sha256"],
            "Stored run bindings differ from frozen input")
    observed, reference, query_doc = [read(root/instance[k]) for k in ("observed", "reference", "query")]
    require(all(hash_file(root/instance[k])==instance[k+"_sha256"] for k in ("observed","reference","query")),
            "Frozen score inputs and manifest disagree")
    window = domain_check(observed, reference, run["surface"]["domain"])
    masks, areas, trace = surface_shapes(run, observed, window)
    metrics = score_surface(masks, areas, window, reference, observed)
    baseline = score_routes(run["base_routes"],query_doc["queries"],observed,None,window)
    with_region = score_routes(run["routes"],query_doc["queries"],observed,masks,window)
    routes = compare_routes(with_region, baseline)
    return {k:instance[k] for k in ("id","parent_task_id","masking_mode","context_radius_m","reference_sha256",
                                   "query_sha256","observed_sha256","mask_sha256","grid_sha256",
                                   "prediction_domain_sha256","evaluation_domain_sha256","group","split","kind","label")} | {
        "method":method,"reference_type":typed(reference),"surface_sha256":run["surface"]["sha256"],
        "config_sha256":run.get("config_sha256"),"code_sha256":run.get("code_sha256"),
        "input_was_previously_observed":True,"metrics":metrics,"routes":routes,"base_routes":baseline,
        "context_trace":trace,"registered_entrance":observed.get("registered_entrance"),
        "graph":run.get("graph"),"elapsed_s":run.get("elapsed_s"),"peak_working_set_bytes":run.get("peak_working_set_bytes"),
        "denied_reference_probes":inspect_read_log(run,instance),"prediction_sha256":hash_file(path),
    }


def report_rows(rows):
    result = defaultdict(list)
    for row in rows:
        for category in ("ALL_TASKS", row["reference_type"]):
            result[(row["masking_mode"],row["context_radius_m"],row["method"],category)].append(row)
    return [{"masking_mode":k[0],"context_radius_m":k[1],"method":k[2],"reference_type":k[3],**aggregate(v)}
            for k,v in sorted(result.items(),key=lambda p:repr(p[0]))]


def aggregate(rows):
    metrics = [x["metrics"] for x in rows]
    routes = [q for x in rows for q in x["routes"]]
    def add(field):
        return sum(m[field] or 0 for m in metrics)
    area, length = add("reference_area_m2"), add("reference_length_m")
    return dict(
        cases=len(rows), parent_task_ids=sorted({r["parent_task_id"] for r in rows}),
        area_cases=sum(m["area_recall"] is not None for m in metrics),
        area_hit_m2=add("reference_area_covered_m2"), area_reference_m2=area,
        pooled_area_recall=add("reference_area_covered_m2")/area if area else None,
        line_cases=sum(m["line_recall"] is not None for m in metrics),
        line_hit_m=add("reference_length_covered_m"), line_reference_m=length,
        pooled_line_recall=add("reference_length_covered_m")/length if length else None,
        negative_cases=sum(m["negative_false_walkable"] is not None for m in metrics),
        false_negative_areas=sum(m["negative_false_walkable"] is True for m in metrics),
        negative_overlap_m2=add("negative_overlap_m2"),
        unknown_area_m2=add("unknown_area_m2"),
        mean_unknown_fraction=add("unknown_fraction")/len(rows) if rows else None,
        inferred_area_m2=add("inferred_area_m2"), off_reference_area_m2=add("off_reference_area_m2"),
        hard_conflict_area_m2=add("hard_conflict_area_m2"), hard_conflict_length_m=add("hard_conflict_length_m"),
        grass_conflict_area_m2=add("grass_conflict_area_m2"), empty_inferences=sum(m["empty_inference"] for m in metrics),
        queries=len(routes), baseline_reached=sum(q["baseline_valid_reached"] for q in routes),
        valid_reached=sum(q["valid_reached"] for q in routes),
        using_inferred=sum(q["uses_inferred_inside"] for q in routes),
        new_local_reaches=sum(q["locally_recovered_query"] for q in routes),
        alternative_with_inference=sum(q["alternative_with_inference"] for q in routes),
        native_outer_detour_only=sum(q["native_outer_detour_only"] for q in routes),
        known_conditional_conflict_routes=sum(bool(q["conditional_conflicts"]) for q in routes),
        cells_using_context=sum(row["context_trace"]["cells_using_context"] for row in rows))


def paired_report(rows):
    index = {(r["parent_task_id"],r["masking_mode"],r["context_radius_m"],r["method"]):r for r in rows}
    results = {name:[] for name in ("E0","E1","E2","E3","E4")}
    common = ("reference_sha256","query_sha256","prediction_domain_sha256","evaluation_domain_sha256","grid_sha256")
    for key,left in index.items():
        parent, mode, radius, method = key
        combinations = []
        if method == "M0":
            if mode in {"H","N"}:
                for other in (80,160):
                    if radius in {40,80} and radius < other:
                        combinations.append(("E1", (parent,mode,other,method), common+("mask_sha256",)))
            if radius == 80 and mode in {"H","G"}:
                for other in ("G","S") if mode == "H" else ("S",):
                    combinations.append(("E2",(parent,other,80,method),common))
            combinations.append(("E3",(parent,mode,radius,"M1"),common+("mask_sha256","observed_sha256")))
        for exp, target, keys in combinations:
            if target not in index:
                continue
            right = index[target]
            require(all(left[k] == right[k] for k in keys), f"{exp} paired contract differs {key}->{target}")
            l,r = left["metrics"],right["metrics"]
            def change(k):
                return r[k]-l[k] if r[k] is not None and l[k] is not None else None
            routes = {v["query_id"]:v for v in right["routes"]}
            if exp == "E3":
                require(left["base_routes"] == right["base_routes"], "Same input M0/M1 gave different no-inference routes")
            pair = {
                "parent_task_id":parent,"reference_type":left["reference_type"],
                "left_id":left["id"],"left_mode":mode,"left_radius":radius,"left_method":method,
                "right_id":right["id"],"right_mode":right["masking_mode"],
                "right_radius":right["context_radius_m"],"right_method":right["method"],
                "shared_reference_area_m2":l["reference_area_m2"],
                "shared_reference_length_m":l["reference_length_m"],
                "area_recall_delta":change("area_recall"),"area_hit_delta_m2":change("reference_area_covered_m2"),
                "line_recall_delta":change("line_recall"),"line_hit_delta_m":change("reference_length_covered_m"),
                "inferred_area_delta_m2":change("inferred_area_m2"),"unknown_area_delta_m2":change("unknown_area_m2"),
                "hard_conflict_area_delta_m2":change("hard_conflict_area_m2"),
                "off_reference_delta_m2":change("off_reference_area_m2"),
                "same_surface_sha256":left["surface_sha256"] == right["surface_sha256"],
                "reachable_added_query_ids":[v["query_id"] for v in left["routes"]
                                             if not v["valid_reached"] and routes[v["query_id"]]["valid_reached"]],
                "reachable_lost_query_ids":[v["query_id"] for v in left["routes"]
                                            if v["valid_reached"] and not routes[v["query_id"]]["valid_reached"]],
                "local_increment_delta":sum(v["locally_recovered_query"] for v in right["routes"])
                                      -sum(v["locally_recovered_query"] for v in left["routes"]),
                "base_outer_detours_delta":sum(v["native_outer_detour_only"] for v in right["routes"])
                                      -sum(v["native_outer_detour_only"] for v in left["routes"]),
            }
            results[exp].append(pair)
            if exp == "E3":
                results["E4"].append({"parent_task_id":parent,"input_id":left["id"],"M1_without_outer_features":"M0",
                                       "M1_with_outer_features_equals_M0":pair["same_surface_sha256"],
                                       "removed_feature_cells":right["context_trace"]["cells_using_context"],
                                       "added_area_m2":pair["inferred_area_delta_m2"]})
    for row in rows:
        if "ORIGINAL" in str(row["masking_mode"]).upper() or "H0_ORIGINAL" in row["id"]:
            results["E0"].append({"parent_task_id":row["parent_task_id"],"old_export_id":row["id"],
                                  "status":"R3_ORIGINAL_EXPORT_REPLAY","replayed_metrics":row["metrics"]})
    return results


def pair_groups(pairs, rows):
    index = {(r["id"],r["method"]):r for r in rows}
    result = {}
    for exp, values in pairs.items():
        if exp not in {"E1","E2","E3"}:
            continue
        groups = defaultdict(list)
        for p in values:
            for t in ("ALL_TASKS",p["reference_type"]):
                k = (p["left_mode"],p["left_radius"],p["left_method"],p["right_mode"],p["right_radius"],
                     p["right_method"],t)
                groups[k].append(p)
        result[exp] = [
            dict(left_mode=k[0],left_radius=k[1],left_method=k[2],right_mode=k[3],right_radius=k[4],
                 right_method=k[5],reference_type=k[6],pairs=len(v),
                 identical_surfaces=sum(x["same_surface_sha256"] for x in v),
                 left=aggregate([index[(x["left_id"],x["left_method"])] for x in v]),
                 right=aggregate([index[(x["right_id"],x["right_method"])] for x in v]))
            for k,v in sorted(groups.items(),key=lambda p:repr(p[0]))]
    return result


def validate_paired_surface_cache(rows,pred):
    by_input=defaultdict(set)
    for r in rows:
        by_input[r["id"]].add(r["method"])
    verified=[]
    for ident, methods in by_input.items():
        if methods!={"M0","M1"}:
            continue
        base,model=[read(pred/ident/(m+".json")) for m in ("M0","M1")]
        frozen=base["surface"]
        cache_bytes=json.dumps({"observed_sha256":base["observed_sha256"],"surface":frozen},
                               ensure_ascii=False,separators=(",",":")).encode("utf8")
        actual_cache_reads=[r for r in model["read_log"] if r["role"]=="CURRENT_M0_SURFACE_CACHE"]
        require(len(actual_cache_reads)==1 and actual_cache_reads[0]["sha256"]==sha256(cache_bytes).hexdigest(),
                f"M1 did not read the identical current-input M0 cells {ident}")
        original,updated=frozen["cells"],model["surface"]["cells"]
        require(len(original)==len(updated),f"M1 changed the fixed grid {ident}")
        affected=0
        for a,b in zip(original,updated):
            if a==b:
                continue
            require(a["region_id"]==b["region_id"] and a["ij"]==b["ij"] and a["geometry"]==b["geometry"] and
                    a["walkability_state"]=="UNKNOWN" and b["walkability_state"]=="INFERRED_WALKABLE" and
                    bool(b.get("context_witnesses")),
                    f"M1 altered a non-unknown class, cell geometry, or restrictions {ident}/{a['region_id']}")
            affected+=1
        require(affected==model["features"]["changed_cells"] and
                (affected>0)==(frozen["sha256"]!=model["surface"]["sha256"]),
                f"Actual M1 promotions and run trace disagree {ident}")
        verified.append({"id":ident,"unchanged_cell_geometry":True,"same_input_m0_cache":True,
                         "only_contextual_unknown_promotions":affected,
                         "ablation_target_surface_sha256":frozen["sha256"]})
    return {"checked_pairs":len(verified),"rows":verified}


def score_historical_replay(root,rows,pred):
    old_rows=read(root/"frozen_r3/runs/benchmark_evaluation.json")
    archived={r["task_id"]:r for r in old_rows["runs"] if r["variant"]=="I-REGION"}
    replayed={r["parent_task_id"]:r for r in rows if "H0_ORIGINAL_EXPORT" in r["id"] and r["method"]=="M0"}
    index={(r["parent_task_id"],r["masking_mode"],r["context_radius_m"],r["method"]):r for r in rows}
    checked=[]
    for parent,row in replayed.items():
        prior=read(root/"frozen_r3/runs/benchmark"/(parent+".json"))["variants"]["I-REGION"]
        current=read(pred/row["id"]/"M0.json")
        require(prior["surface"]["sha256"]==current["surface"]["sha256"],
                f"E0 original export M0 surface hash mismatch: {parent}")
        require(prior["routes"]==current["routes"], f"E0 original export route bytes mismatch: {parent}")
        original=archived[parent]["region"]
        metrics=row["metrics"]
        for a,b in (("area_recall","area_recall"),("inferred_centerline_coverage","line_recall"),
                    ("unknown_fraction","unknown_fraction"),("inferred_m2","inferred_area_m2")):
            if original[a] is None:
                require(metrics[b] is None,f"E0 score applicability changed: {parent}/{b}")
            else:
                require(abs(original[a]-metrics[b])<=AREA_TOL,f"E0 re-scored metric changed: {parent}/{b}")
        norm=index.get((parent,"N" if row["label"]=="NEGATIVE" else "H",40,"M0"))
        comparison=None
        if norm:
            require(all(row[k]==norm[k] for k in ("reference_sha256","query_sha256","prediction_domain_sha256",
                                                "evaluation_domain_sha256","grid_sha256")),
                    "E0 normalized comparison changed query, reference, grid, or domain")
            comparison={
                "normalized_id":norm["id"],"norm_area_recall":norm["metrics"]["area_recall"],
                "norm_line_recall":norm["metrics"]["line_recall"],
                "inferred_area_delta_m2":norm["metrics"]["inferred_area_m2"]-metrics["inferred_area_m2"],
                "unknown_area_delta_m2":norm["metrics"]["unknown_area_m2"]-metrics["unknown_area_m2"],
                "observed_node_delta":norm["graph"]["observed_nodes"]-row["graph"]["observed_nodes"],
                "directed_graph_arc_delta":norm["graph"]["observed_arcs"]-row["graph"]["observed_arcs"],
                "scope":"EXPORT_NORMALIZATION_AT_SAME_40_M_NOT_RADIUS_EFFECT",
            }
        checked.append({"parent_task_id":parent,"old_export_id":row["id"],"surface_hash_identical":True,
                        "complete_routes_identical":True,"replayed_metrics":metrics,"normalized_40m_comparison":comparison,
                        "status":"R3_ORIGINAL_EXPORT_REPLAY"})
    return checked


def main(args):
    root = args.root.resolve()
    manifest=args.manifest or root/"data/task_manifest.json"
    inventory=read(manifest)
    config=read(root/"config/methods.json")
    for field,file in (("region_sha256","src/region.py"),("routing_sha256","src/region_routing.py"),
                       ("config_sha256","config/frozen_region.json")):
        require(config["M0"][field]==hash_file(root/file),f"M0 frozen source or config changed: {file}")
    def combined(files):
        return sha256("".join(hash_file(root/f) for f in files).encode()).hexdigest()
    lock_hashes={"config":combined(["config/frozen_region.json","config/methods.json"]),
                 "code":combined(["src/region.py","src/region_routing.py","src/context_policy.py","src/predict.py"])}
    tasks = inventory["instances"]
    pred = args.predictions or root/"data/predictions"
    rows = []
    missing=[]
    for task in tasks:
        if args.task and task["parent_task_id"] not in args.task:
            continue
        for method in ("M0","M1"):
            path = pred/task["id"]/(method+".json")
            if path.exists():
                rows.append(score_one(root,task,path,lock_hashes))
            elif not (method=="M1" and "ORIGINAL" in task["id"]):
                missing.append(task["id"]+"/"+method)
    require(rows, "No actual prediction matches the frozen task manifest")
    if args.require_full:
        require(not missing,f"Expected final paired results missing: {missing[:10]}")
    pairs = paired_report(rows)
    witness_ablation=validate_paired_surface_cache(rows,pred)
    e0_pairs=score_historical_replay(root,rows,pred)
    pairs["E0"]=e0_pairs
    out = args.out or root/"runs/context_metrics.json"
    write(out, {"status":"INDEPENDENT_FIXED_DOMAIN_SCORED","observational_status":"EXPOSED_SAME_SOURCE_DIAGNOSTIC",
                "task_manifest_sha256":hash_file(manifest),"rows":rows,
                "aggregate":report_rows(rows),"paired":pairs,"paired_aggregate":pair_groups(pairs,rows),
                "case_rows":len(rows),"missing_run_rows":missing,"context_ablation_audit":witness_ablation,"external_requests":0})
    flat = []
    for row in rows:
        visible = {k:row[k] for k in ("id","parent_task_id","masking_mode","context_radius_m","method","reference_type","split")}
        columns = ("reference_area_m2","reference_area_covered_m2","area_recall","reference_length_m","reference_length_covered_m",
                   "line_recall","inferred_area_m2","unknown_area_m2","off_reference_area_m2","hard_conflict_area_m2",
                   "hard_conflict_length_m","grass_conflict_area_m2","negative_false_walkable","reference_boundary_p90_m")
        visible.update({k:row["metrics"][k] for k in columns})
        summary = aggregate([row])
        visible.update({k:summary[k] for k in ("queries","baseline_reached","valid_reached","using_inferred",
                       "new_local_reaches","alternative_with_inference","native_outer_detour_only","cells_using_context")})
        flat.append(visible)
    with out.with_suffix(".csv").open("x",encoding="utf-8-sig",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    print(f"Scored {len(rows)} actual runs; pairs: " + ", ".join(f"{k}={len(v)}" for k,v in pairs.items()),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--predictions",type=Path)
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--task",action="append",help="Restrict to already frozen parent IDs for review replay")
    parser.add_argument("--require-full",action="store_true",help="Require both methods for each selected normalized input")
    main(parser.parse_args())
