"""Independently score R3 region and route outputs against the withheld benchmarks."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
from pathlib import Path
import sys

from pyproj import Transformer
from shapely import make_valid, segmentize, union_all
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
WGS = Transformer.from_crs(32651, 4326, always_xy=True).transform
STATES = ("NATIVE_WALKABLE", "INFERRED_WALKABLE", "RESTRICTED", "UNKNOWN")
HARD = {"BUILDING", "WATER", "FLOWERBED", "BARRIER", "RESTRICTED", "RESTRICTED_AREA", "LEVEL_CONFLICT"}
ROUTED_TOL = 1e-4
AREA_TOL = 0.01
LINE_TOL = 1e-4


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sign(path):
    return sha256(path.read_bytes()).hexdigest()


def segments(geom):
    if geom.geom_type == "LineString":
        yield geom
    elif geom.geom_type in ("MultiLineString", "GeometryCollection"):
        for piece in geom.geoms:
            yield from segments(piece)


def p90_distances(source, target):
    if source is None or target is None or source.is_empty or target.is_empty:
        return None
    points = [Point(xy) for line in segments(segmentize(source, 0.75)) for xy in line.coords]
    ds = sorted(p.distance(target) for p in points)
    return ds[math.ceil(.90*len(ds))-1] if ds else None


def block_geometries(obs):
    hard = [(r["id"], shape(r["geometry"])) for r in obs["context"]["hard"] if r["kind"] in HARD]
    grass = [(r["id"], shape(r["geometry"])) for r in obs["context"]["background"]
             if r["kind"] in {"GRASS","BACKGROUND_GRASS","FLOWERBED","MEADOW"}]
    return hard, grass


def replay_raw_reference(ref, window, raw):
    if ref["kind"].startswith("LINE_"):
        expected = raw.obj(ref["source_ids"][0])
        geom = LineString([raw.projected[n] for n in expected["nodes"]])
        if geom.hausdorff_distance(shape(ref["geometry"])) > 1e-5:
            raise ValueError("Reference line differs from raw way")
    elif ref["kind"].startswith("AREA_"):
        geom = raw.area(ref["source_ids"][0]).intersection(window)
        if geom.symmetric_difference(shape(ref["geometry"])).area > 1e-5:
            raise ValueError("Reference face differs from raw shape")
    else:
        areas = [raw.area(ident) for ident in ref["source_ids"]]
        geom = union_all(areas).intersection(window)
        if geom.symmetric_difference(shape(ref["geometry"])).area > 1e-5:
            raise ValueError("Reference obstacle differs from raw shape")
        if shape(ref["control_chord"]).intersection(geom).length < 1:
            raise ValueError("Negative chord does not traverse the reference obstacle")


def check_group_separation(refs):
    for i, left in enumerate(refs):
        for right in refs[i+1:]:
            if left["split"] == right["split"]:
                continue
            if (left["group"] == right["group"] or set(left["source_ids"]) & set(right["source_ids"]) or
                    set(left["source_id_hidden"]) & set(right["source_id_hidden"]) or
                    shape(left["domain_geometry"]).intersection(shape(right["domain_geometry"])).area > .1):
                raise ValueError("Source/split/spatial leakage between controlled sets")


def load_surface(root, stage, run, window, observed_ids, diagnostic_repair=False):
    path = root / stage["path"]
    if sign(path) != stage["sha256"] or stage["surface_sha256"] != run["surface"]["sha256"]:
        raise ValueError("Frozen surface digest mismatch")
    items = read(path)["features"]
    collected = {s:[] for s in STATES}
    region_ids = set()
    row_areas = Counter()
    for feature in items:
        p = feature["properties"]
        if not {"region_id","walkability_state","evidence_sources","assumptions",
                "hard_conflicts","uncertainty_level","source_status","decision_reason"} <= set(p):
            raise ValueError("Incomplete cell evidence contract")
        if p["region_id"] in region_ids:
            raise ValueError("Duplicate region fragment identity")
        region_ids.add(p["region_id"])
        wgs = shape(feature["geometry"])
        geom = transform(PROJECT, wgs)
        if not wgs.is_valid or not geom.is_valid:
            if not diagnostic_repair:
                raise ValueError(f"Invalid region fragment polygon {path.name}: {p['region_id']}")
            repaired = make_valid(geom)
            geom = union_all([g for g in getattr(repaired,"geoms",[repaired]) if g.area > 1e-9])
            if abs(geom.area-p["area_m2"]) > 1e-5:
                raise ValueError("Diagnostic numerical repair changed the measured area")
        if geom.geom_type not in ("Polygon", "MultiPolygon") or not geom.is_valid:
            raise ValueError("Invalid repaired geometry")
        state = p["walkability_state"]
        if (set(p["evidence_sources"]) | set(p["hard_conflicts"])) - observed_ids:
            raise ValueError("Unobserved positive evidence source")
        if state == "INFERRED_WALKABLE" and p["source_status"] != "inferred":
            raise ValueError("Inferred cells lose their evidence identity")
        if state == "UNKNOWN" and p["source_status"] in {"native","inferred"}:
            raise ValueError("Unknown cells promoted to native/inferred")
        collected[state].append(geom)
        row_areas[state] += geom.area
    shapes = {k:union_all(v) for k,v in collected.items()}
    union = union_all(list(shapes.values()))
    summed = sum(row_areas.values())
    if (union.symmetric_difference(window).area > AREA_TOL or
            abs(summed - union.area) > AREA_TOL or any(
                abs(shapes[s].area-run["surface"]["area_m2"][s]) > AREA_TOL for s in STATES)):
        raise ValueError("Four state partitions do not match the frozen domain and area table")
    return shapes, len(items)


def edge_layer_status(edge):
    return edge["layer"]


def inspect_routes(runs, queries, shapes, hard, reference, ref_kind, visible_directions):
    rows = []
    for ident, result in runs.items():
        q = queries[ident]
        lengths = Counter()
        native_conflicts = Counter()
        conditional_conflicts = Counter()
        geometry = []
        previous = q["source"]["xy"]
        cost = 0
        for edge in result["edges"]:
            line = LineString(edge["xy"])
            if math.dist(previous, edge["xy"][0]) > ROUTED_TOL:
                raise ValueError(f"Discontinuous controlled route {ident}")
            if abs(line.length - edge["length_m"]) > ROUTED_TOL:
                raise ValueError("Controlled route stored edge length differs")
            previous = edge["xy"][-1]
            length = line.length
            layer = edge_layer_status(edge)
            if layer == "native":
                source = "/".join(edge["source_id"].split("/")[:2])
                if not any(original.buffer(1e-5).covers(line) and
                           original.project(Point(line.coords[-1])) > original.project(Point(line.coords[0]))
                           for original in visible_directions[source]):
                    raise ValueError(f"Native route {ident} has no exact observed directed source edge: {source}")
            lengths[layer] += length
            cost += edge["cost_m"]
            geometry.append((line, edge))
            tags = edge.get("tags",{})
            bridge_or_tunnel = any(tags.get(k) not in (None, "", "no") for k in ("bridge", "tunnel"))
            for source_id, obj in hard:
                if not line.intersects(obj):
                    continue
                if obj.geom_type in ("Polygon","MultiPolygon"):
                    contact = line.intersection(obj.buffer(-1e-5)).length > LINE_TOL
                else:
                    contact = line.crosses(obj) or line.intersection(obj).length > LINE_TOL
                if contact:
                    if layer == "native":
                        if not bridge_or_tunnel:
                            native_conflicts[source_id] += 1
                    else:
                        conditional_conflicts[source_id] += 1
            kind = edge.get("geometry_kind", "")
            if shapes and kind in {"FROZEN_INFERRED_REGION", "NEW_GRID_WITHIN_MAPPED_FACE", "BOUNDED_UNKNOWN_PORTAL"}:
                expected = {"FROZEN_INFERRED_REGION":"INFERRED_WALKABLE",
                            "NEW_GRID_WITHIN_MAPPED_FACE":"NATIVE_WALKABLE",
                            "UNKNOWN_PORTAL_STITCH":"UNKNOWN"}[kind]
                if line.difference(shapes[expected].buffer(1e-5)).length > ROUTED_TOL:
                    raise ValueError(f"Route {ident} uses a wrong frozen surface state: {kind}")
        reached = bool(result["edges"] or q["source"]["id"] == q["target"]["id"]) and (
            math.dist(previous, q["target"]["xy"]) < ROUTED_TOL)
        if reached != bool(result["reached"]):
            raise ValueError(f"Stored route reach differs from geometry for {ident}")
        if result["length_m"] is not None and abs(result["length_m"] - sum(lengths.values())) > ROUTED_TOL:
            raise ValueError("Controlled route stored total length differs")
        if result["cost_m"] is not None and abs(result["cost_m"] - cost) > ROUTED_TOL:
            raise ValueError("Controlled route stored total cost differs")
        inferred = union_all([line for line, edge in geometry if edge["layer"] == "inferred"])
        rows.append(dict(query_id=ident, status=result["status"], reached=reached,
                         valid_reached=reached and not bool(native_conflicts or conditional_conflicts),
                         length_m=result["length_m"], cost_m=result["cost_m"], layer_lengths_m=dict(lengths),
                         residual_m=math.dist(previous, q["target"]["xy"]),
                         conditional_conflicts=dict(conditional_conflicts), native_conflicts=dict(native_conflicts),
                         obstacle_inferred_crossing_m=(inferred.intersection(reference).length
                                                       if ref_kind=="MAPPED_OBSTACLE_NEGATIVE" else None),
                         surface_sha256=result.get("surface_sha256")))
    return rows


def assess_region(shapes, window, ref, hard, grass, park, widths):
    pred = shapes["INFERRED_WALKABLE"]
    native = shapes["NATIVE_WALKABLE"]
    unknown = shapes["UNKNOWN"]
    reference = shape(ref["geometry"])
    hard_union = union_all([g for _,g in hard if g.area > 0])
    grass_union = union_all([g for _,g in grass if g.area > 0])
    negative = ref["label"] == "NEGATIVE"
    line = ref["kind"].startswith("LINE_")
    areas = {k:v.area for k,v in shapes.items()}
    if line:
        centerline = pred.intersection(reference).length/reference.length
        assisted = union_all([pred,native]).intersection(reference).length/reference.length
        proxies = []
        for width in widths:
            held = reference.buffer(width, cap_style="flat").intersection(window)
            overlap = held.intersection(pred).area
            proxies.append(dict(proxy_buffer_radius_m=width, proxy_area_m2=held.area, overlap_m2=overlap,
                                area_recall=overlap/held.area))
    else:
        centerline=assisted=None
        proxies=[]
    area_overlap = (pred.intersection(reference).area if not line else None)
    # Exclude artificial study-window boundary; do not report a fictitious error
    # when the predictor cannot draw any inferred boundary.
    interior=window.buffer(-.05)
    park_mask=union_all(park)
    pred_boundary=pred.boundary.intersection(interior) if not pred.is_empty else None
    ref_boundary=reference.boundary.intersection(interior) if not line and not negative else None
    return dict(state_m2=areas, unknown_fraction=unknown.area/window.area,
                inferred_m2=pred.area, hard_expansion_m2=pred.intersection(hard_union).area,
                grass_expansion_m2=pred.intersection(grass_union).area,
                inferred_in_park_context_m2=pred.intersection(park_mask).area,
                inferred_park_outside_positive_reference_m2=pred.intersection(park_mask).difference(reference).area
                    if not line and not negative else None,
                hard_barrier_crossline_m=pred.intersection(union_all(
                    [g for _,g in hard if g.geom_type in {"LineString","MultiLineString"}])).length,
                native_assisted_centerline_coverage=assisted, inferred_centerline_coverage=centerline,
                reference_length_m=reference.length if line else None,
                reference_area_m2=None if line else reference.area,
                overlap_m2=area_overlap,
                area_recall=area_overlap/reference.area if not line and not negative else None,
                reference_boundary_p90_m=p90_distances(ref_boundary,pred_boundary),
                inferred_boundary_p90_m=p90_distances(pred_boundary,ref_boundary),
                outside_reference_m2=pred.difference(reference).area if not line and not negative else None,
                negative_false_inferred=area_overlap>AREA_TOL if negative else None,
                proxy_widths=proxies)


def visual(task_id, obs, queries, ref, surface, prediction, result):
    window = shape(ref["domain_geometry"])
    frame = window.buffer(4)
    out = []
    common = {"task_id":task_id, "case_type":ref["kind"],"split":ref["split"]}
    def feature(role, geometry, **props):
        if not geometry.is_empty:
            out.append(dict(type="Feature",geometry=mapping(transform(WGS,geometry)),
                            properties={**common,"role":role,**props}))
    feature("domain",window, interpretation="SEARCH_DOMAIN_NOT_WALKABILITY")
    nodes = {r["id"]:r for r in obs["nodes"]}
    drawn=set()
    for e in obs["edges"]:
        key=frozenset([e["u"],e["v"]])
        if key in drawn:
            continue
        drawn.add(key)
        line=LineString([nodes[e["u"]]["xy"],nodes[e["v"]]["xy"]]).intersection(frame)
        if line.length > 0.001:
            feature("observed_network",line,source_id=e["id"],tags=e["tags"])
    for key, role in (("hard","observed_obstacle"),("background","observed_background"),("support","observed_support")):
        for row in obs["context"][key]:
            feature(role,shape(row["geometry"]).intersection(frame), source_id=row["id"],
                    tags=row["tags"],kind=row["kind"])
    role = ("obstacle_reference" if ref["label"]=="NEGATIVE" else "reference_line"
            if ref["kind"].startswith("LINE_") else "reference_area")
    feature(role,shape(ref["geometry"]),source_ids=ref["source_ids"],
            interpretation="WITHHELD_SCORING_ONLY" if ref["label"]=="POSITIVE" else "INDEPENDENT_MAPPED_OBSTACLE")
    if ref["control_chord"]:
        feature("route_gap",shape(ref["control_chord"]),interpretation="CONTROL_CHORD_NOT_A_ROUTE")
    for state, geo in surface.items():
        feature("predicted_region",geo,walkability_state=state,region_id=task_id+"/"+state,
                area_m2=geo.area,source_status="aggregated_exact_cell_union")
    door = obs["registered_entrance"]
    if door:
        feature("registered_exit" if door["tags"].get("entrance")=="exit" else "target",
                Point(door["xy"]), source_id=door["id"], tags=door["tags"])
    for q in queries:
        for key in ("source","target"):
            row=q[key]
            feature("query_endpoint",Point(row["xy"]),source_id=row["id"],query_id=q["query_id"],
                    interpretation=key)
    if prediction["routes"]:
        for qid, route in prediction["routes"].items():
            for edge in route["edges"]:
                feature("route",LineString(edge["xy"]).intersection(frame),query_id=qid,
                        layer=edge["layer"],source_id=edge["source_id"],length_m=edge["length_m"],
                        status=route["status"])
    return out


def aggregate(scored, threshold):
    out=[]
    for split in ("all","development","selection","confirmation"):
        for variant in sorted({v["variant"] for v in scored}):
            subset=[r for r in scored if r["variant"]==variant and (split=="all" or r["split"]==split)]
            if not subset:
                continue
            for kind in ("ALL_TASKS", *sorted({r["kind"] for r in subset})):
                part=[r for r in subset if kind=="ALL_TASKS" or r["kind"]==kind]
                metrics=[r["region"] for r in part if r["region"] is not None]
                routes=[q for row in part for q in row["routes"]]
                areas=[r for r in metrics if r["area_recall"] is not None]
                lines=[r for r in metrics if r["inferred_centerline_coverage"] is not None]
                negatives=[r for r in metrics if r["negative_false_inferred"] is not None]
                unknown=[r["unknown_fraction"] for r in metrics]
                boundary=[r["reference_boundary_p90_m"] for r in areas if r["reference_boundary_p90_m"] is not None]
                total_ref=sum(r["reference_area_m2"] for r in areas)
                total_line=sum(r["reference_length_m"] for r in lines)
                out.append(dict(split=split,variant=variant,case_type=kind,cases=len(part),
                                area_cases=len(areas), area_cases_half_covered=sum(r["area_recall"]>=threshold for r in areas),
                                area_reference_m2=total_ref, area_overlap_m2=sum(r["overlap_m2"] for r in areas),
                                pooled_area_coverage=sum(r["overlap_m2"] for r in areas)/total_ref if total_ref else None,
                                mean_area_boundary_p90_m=sum(boundary)/len(boundary) if boundary else None,
                                n_area_boundary_values=len(boundary),
                                line_cases=len(lines),line_cases_half_covered=sum(r["inferred_centerline_coverage"]>=threshold for r in lines),
                                mean_line_coverage=sum(r["inferred_centerline_coverage"] for r in lines)/len(lines) if lines else None,
                                pooled_line_coverage=sum(r["inferred_centerline_coverage"]*r["reference_length_m"] for r in lines)
                                    /total_line if total_line else None,
                                negative_cases=len(negatives),negative_cases_false_walkable=sum(r["negative_false_inferred"] for r in negatives),
                                negative_overlap_m2=sum(r["overlap_m2"] for r in negatives),
                                hard_expansion_m2=sum(r["hard_expansion_m2"] for r in metrics),
                                grass_expansion_m2=sum(r["grass_expansion_m2"] for r in metrics),
                                inferred_in_park_context_m2=sum(r["inferred_in_park_context_m2"] for r in metrics),
                                inferred_off_reference_m2=sum(r["outside_reference_m2"] for r in areas),
                                mean_unknown_fraction=sum(unknown)/len(unknown) if unknown else None,
                                queries=len(routes), valid_routes=sum(r["valid_reached"] for r in routes),
                                routes_with_inference=sum(r["valid_reached"] and r["layer_lengths_m"].get("inferred",0)>LINE_TOL for r in routes),
                                routes_with_unknown=sum(r["valid_reached"] and r["layer_lengths_m"].get("unknown",0)>LINE_TOL for r in routes),
                                routes_with_known_conflicts=sum(bool(r["native_conflicts"] or r["conditional_conflicts"]) for r in routes)))
    return out


def main(args):
    if args.diagnostic_repair and not (args.no_visual and args.no_audit and args.output.resolve().is_relative_to(ROOT/"runtime")):
        raise ValueError("Diagnostic geometry repairs cannot produce released scores")
    score_root=args.prediction_root
    inventory=read(args.benchmark/"inventory.json")
    protocol=read(args.protocol)
    if sign(args.protocol)!=inventory["protocol_sha256"] or sign(args.semantics)!=protocol["native_policy_sha256"]:
        raise ValueError("Frozen study/semantics manifest mismatch")
    sys.path.insert(0,str(args.rev1))
    from src.native_adapter import Source
    spec=spec_from_file_location("prep_input_contract",ROOT/"src/prepare_benchmark.py")
    curator=module_from_spec(spec)
    spec.loader.exec_module(curator)
    blocked=curator.blocked_s1(args.semantics)
    tasks=inventory["tasks"]
    refs=[read(args.benchmark/"reference"/f"{row['task_id']}.json") for row in tasks]
    check_group_separation(refs)
    selected={x["task_id"] for x in tasks if (not args.split or x["split"]==args.split)
              and (not args.task or x["task_id"] in args.task)}
    scored, proofs, visuals, index = [], [], [], {}
    raw_cache={}
    for row,ref in zip(tasks,refs):
        ident=row["task_id"]
        if ident not in selected:
            continue
        inputs = {role:args.benchmark/role/f"{ident}.json" for role in ("observed","queries","reference")}
        if any(sign(path)!=row[f"{role}_sha256"] for role,path in inputs.items()):
            raise ValueError(f"{ident}: benchmark member fingerprint mismatch")
        obs=read(inputs["observed"])
        qs=read(inputs["queries"])["queries"]
        curator.audit_one(obs,qs,ref)
        if any(curator.blocked_edge(row["group"],e,blocked) for e in obs["edges"]):
            raise ValueError("An S1 rejected or unresolved graph edge reached observations")
        observed_ids = ({r["id"] for group in obs["context"].values() for r in group} |
                        {r["id"] for r in obs["nodes"]} | {curator.way_id(e) for e in obs["edges"]})
        if obs["registered_entrance"]:
            observed_ids.add(obs["registered_entrance"]["id"])
        pred_path=score_root/"runs/benchmark"/f"{ident}.json"
        run=read(pred_path)
        if run["task_id"]!=ident or run.get("external_requests")!=0:
            raise ValueError("Unexpected run identity or request")
        read_log=run["read_log"]
        if ([r["role"] for r in read_log][0::len(read_log)-1]!=["observed","queries"] or
            any(r["role"]!="SURFACE_FROZEN" for r in read_log[1:-1]) or
            [r["sequence"] for r in read_log]!=list(range(1,len(read_log)+1))):
            raise ValueError("Read order is not observed → all surface freezes → query")
        for log, role in ((read_log[0],"observed"),(read_log[-1],"queries")):
            if log["path"]!=f"{role}/{ident}.json" or log["sha256"]!=row[f"{role}_sha256"]:
                raise ValueError("Prediction read log differs from allowed member")
        stages={log["variant"]:log for log in read_log[1:-1]}
        if set(stages)!={m for m,run_ in run["variants"].items() if run_.get("surface")}:
            raise ValueError("Region build receipt missing a frozen variant")
        if "I-REGION-NET-ABL" in stages and stages["I-REGION-NET-ABL"]["surface_sha256"]!=stages["I-REGION"]["surface_sha256"]:
            raise ValueError("Network ablation uses a different surface")
        if row["split"]=="confirmation" and set(run["variants"])!={"S1","I-LINE","I-REGION"}:
            raise ValueError("Confirmation contains untuned extra method")
        if ref["source_clip"] not in raw_cache:
            raw_path=args.rev1/"frozen_r4/data/source"/ref["source_clip"]
            if sign(raw_path)!=ref["source_clip_sha256"]:
                raise ValueError("Frozen raw clip SHA changed")
            raw_cache[ref["source_clip"]]=Source(read(raw_path))
        window=shape(ref["domain_geometry"])
        replay_raw_reference(ref,window,raw_cache[ref["source_clip"]])
        hard, grass=block_geometries(obs)
        node_xy={n["id"]:n["xy"] for n in obs["nodes"]}
        visible_directions=defaultdict(list)
        for edge in obs["edges"]:
            visible_directions[curator.way_id(edge)].append(LineString([node_xy[edge["u"]],node_xy[edge["v"]]]))
        if ref["kind"].startswith("LINE_"):
            geom=shape(ref["geometry"])
            shadow=geom.buffer(protocol["line_shadow_m"],cap_style="flat")
            if any(line.intersection(shadow).length > .25 or line.intersection(geom).length > .025
                   for rows in visible_directions.values() for line in rows):
                raise ValueError("A partially surviving line duplicates the withheld reference")
        park=[shape(r["geometry"]) for r in obs["context"]["support"] if r["kind"]=="PARK"]
        queries={q["query_id"]:q for q in qs}
        out_q={q["query_id"]:q for q in run["queries"]}
        if (set(queries)!=set(out_q) or any(out_q[k][side][field]!=queries[k][side][field]
            for k in queries for side in ("source","target") for field in ("id","xy"))):
            raise ValueError("Recorded query endpoints differ from frozen")
        fragments=0
        for method,data in run["variants"].items():
            if set(data["routes"])!=set(queries):
                raise ValueError("Controlled output route query set changed")
            surfaces=None
            assessment=None
            if method in stages:
                stage=stages[method]
                if stage["path"]!=f"data/benchmark_predictions/{ident}_{method}.geojson":
                    raise ValueError("Unexpected surface source receipt")
                surfaces,n=load_surface(score_root,stage,data,window,observed_ids,args.diagnostic_repair)
                fragments+=n
                assessment=assess_region(surfaces,window,ref,hard,grass,park,protocol["widths_buffer_radius_m"])
                if any(route.get("surface_sha256") and route["surface_sha256"]!=data["surface"]["sha256"]
                       for route in data["routes"].values()):
                    raise ValueError("Different queries used different region surfaces")
            routes=inspect_routes(data["routes"],queries,surfaces,hard,shape(ref["geometry"]),ref["kind"],visible_directions)
            result={**{k:row[k] for k in ("task_id","group","split","kind","label")},
                    "source_ids":ref["source_ids"],"variant":method,"region":assessment,"routes":routes,
                    "interfaces":len(data.get("interfaces",[])),"region_graph":data.get("graph"),
                    "peak_working_set_bytes":run.get("peak_working_set_bytes"),"elapsed_s":run.get("elapsed_s")}
            scored.append(result)
            if method=="I-REGION" and not args.no_visual:
                visuals+=visual(ident,obs,qs,ref,surfaces,data,result)
                index[ident]={"case_type":ref["kind"],"kind":ref["kind"],"split":ref["split"],
                              "source_ids":ref["source_ids"],"metrics":assessment,
                              "routes":routes,"query_count":len(routes),"route_successes":sum(r["valid_reached"] for r in routes)}
        proofs.append(dict(task_id=ident,split=row["split"],source_ids=ref["source_ids"],
                           raw_source_sha256=ref["source_clip_sha256"],observed_sha256=row["observed_sha256"],
                           queries_sha256=row["queries_sha256"],prediction_sha256=sign(pred_path),
                           original_source_geometry_recomputed=True, observed_graph_edges=len(obs["edges"]),
                           hidden_source_count=len(ref["source_id_hidden"]),
                           surface_count=len(stages), area_fragments_verified=fragments,
                           query_count=len(qs),surface_before_query=True))
    table=aggregate(scored,protocol["positive_thresholds"]["eligible_geometry_coverage"])
    write(args.output,dict(status="INDEPENDENT_SCORE_COMPLETE",benchmark_sha256=sign(args.benchmark/"inventory.json"),
                            protocol_sha256=sign(args.protocol),counts=inventory["counts"],runs=scored,
                            aggregate=table,external_requests=0))
    if not args.no_visual:
        write(args.visual,dict(type="FeatureCollection",features=visuals))
        write(args.index,index)
    if not args.no_audit:
        write(args.audit,dict(status="INDEPENDENT_GEOMETRY_AND_APPLICATION_READ_AUDIT",
                             source="frozen local OSM",score_sha256=sign(args.output),
                             raw_clip_count=len(raw_cache),tasks=proofs,scope="Application read order, not OS isolation",
                             cross_split_overlap=False,reference_runtime_reads=0,external_requests=0))
    for row in table:
        if row["case_type"]=="ALL_TASKS" and row["split"] in {"all","confirmation"}:
            print(json.dumps(row,ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark",type=Path,default=ROOT/"data/benchmark")
    p.add_argument("--prediction-root",type=Path,default=ROOT)
    p.add_argument("--rev1",type=Path,default=ROOT/"inputs/rev1")
    p.add_argument("--protocol",type=Path,default=ROOT/"config/benchmark.json")
    p.add_argument("--semantics",type=Path,default=ROOT/"data/semantics_edges.csv")
    p.add_argument("--output",type=Path,default=ROOT/"runs/benchmark_evaluation.json")
    p.add_argument("--visual",type=Path,default=ROOT/"data/benchmark_review.geojson")
    p.add_argument("--index",type=Path,default=ROOT/"runs/benchmark_review.json")
    p.add_argument("--audit",type=Path,default=ROOT/"audits/benchmark_leakage.json")
    p.add_argument("--diagnostic-repair",action="store_true",help="Allow sub-tolerance invalid projections in scratch diagnostics only")
    p.add_argument("--task",action="append",help="Limit independent replay to specified opaque task IDs")
    p.add_argument("--split",choices=["development","selection","confirmation"])
    p.add_argument("--no-visual",action="store_true")
    p.add_argument("--no-audit",action="store_true")
    main(p.parse_args())
