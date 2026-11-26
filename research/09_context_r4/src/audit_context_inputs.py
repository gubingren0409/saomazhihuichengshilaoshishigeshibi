"""Independent read-only audit of frozen R4 observed geometry and paired contracts."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

from shapely import union_all
from shapely.geometry import LineString, Point, Polygon, box, shape

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.context_audit_common import (ALIGNMENT_TOL, AREA_TOL, FORWARD, LENGTH_TOL, ROOT,
                                      RawClip, hash_file, item_id, read, require,
                                      source_id, source_way_segment, visible_lines, write)

SAFE_OBS = {"task_id","crs","domain","registered_entrance","nodes","edges","context"}
CONTEXT_ROLES = {"hard","background","support"}
RADIUS_SET = {40,80,160}
OUTSIDE_EDGE_TOL = 0.001


def blocked_rows(path):
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        return {(row["scene_id"],row["source_id"],int(row["segment_index"])):row
                for row in csv.DictReader(f)}


def active_paths(root, instance):
    for k in ("observed","query","reference"):
        path = root/instance[k]
        require(path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink(),
                f"Invalid manifest path: {instance[k]}")
        require(hash_file(path)==instance[k+"_sha256"],f"Manifest byte mismatch: {instance[k]}")
        yield path


def historical_export(instance):
    return "ORIGINAL" in instance["id"].upper() or "H0" in str(instance["masking_mode"]).upper()


def mode_name(instance):
    value = str(instance["masking_mode"])
    return {"HISTORICAL_STRONG_MASK":"H","LOCAL_GAP_MISSING":"G",
            "SEMANTIC_MISSING":"S","KNOWN_OBSTACLE":"N"}.get(value,value)


def get_point_mark(row):
    value = row.get("endpoint_kind", "NATIVE_ENDPOINT")
    return str(value)


def blocked_segment(raw, source, segment, sign, blocked, group):
    row = blocked.get((group,source,segment))
    if row is None:
        return False
    if row["S1_status"] != "KEEP_NATIVE":
        return True
    sign_list = row.get("directions")
    return sign_list in ("[1]","[-1]") and int(sign_list[1:-1]) != sign


def whole_raw_context(raw, row, available):
    """Audit complete-source polygon / line geometry, independent of export implementation."""
    name = item_id(row)
    g = shape(row["geometry"])
    if name.startswith("node/"):
        if name not in raw.objects:
            return None
        expected = Point(raw.node(name))
        return g.distance(expected) <= LENGTH_TOL and (g.geom_type=="Point" or row.get("kind")=="UNKNOWN")
    if name not in raw.objects:
        return None
    if g.area and row.get("kind")=="UNKNOWN":
        obj=raw.objects[name]
        ways=[obj] if obj["type"]=="way" else [raw.objects[f"way/{m['ref']}"] for m in obj.get("members",[])
                                                if m["type"]=="way" and f"way/{m['ref']}" in raw.objects]
        coords=[raw.xy[n] for w in ways for n in w["nodes"] if n in raw.xy]
        if not coords:
            return None
        xs,ys=zip(*coords)
        fallback=box(min(xs),min(ys),max(xs),max(ys)).buffer(.01)
        return g.symmetric_difference(fallback).area<=AREA_TOL
    if g.area:
        try:
            expected = raw.area(name)
        except (KeyError,ValueError):
            expected = None
        if expected is not None:
            return g.symmetric_difference(expected).area <= AREA_TOL
        return None
    if name.startswith("way/"):
        expected = raw.line(name)
        return g.hausdorff_distance(expected.intersection(available)) <= LENGTH_TOL
    return None


def mask_geometry(ledger, ref):
    for key in ("hidden_core_geometry","masked_geometry","mask_geometry","hidden_geometry","geometry"):
        value = ledger.get(key)
        if isinstance(value, dict) and "type" in value:
            return shape(value)
    return shape(ref["geometry"])


def aligned_shadow_length(line, original):
    """Short transversal intersections remain legal; parallel aliases do not."""
    from src.context_audit_common import line_pieces

    if line.distance(original)>.015:
        return 0.
    dx,dy = (line.coords[-1][i]-line.coords[0][i] for i in (0,1))
    shadows = []
    for part in line_pieces(original):
        xy = list(part.coords)
        for a,b in zip(xy,xy[1:]):
            ux,uy = b[0]-a[0],b[1]-a[1]
            size = math.hypot(ux,uy)
            if size <= LENGTH_TOL:
                continue
            cosine=abs(dx*ux+dy*uy)/(line.length*size)
            if cosine >= .98:
                band=LineString((a,b)).buffer(.015,cap_style="flat")
                if band.intersects(line):
                    shadows.append(band)
    return union_all(shadows).intersection(line).length if shadows else 0.


def verify_mask_cuts(ledger, graphs, raw, available, ref):
    by_source = defaultdict(list)
    for (way,index,_),parts in graphs.items():
        by_source[way,index].extend(parts)
    check = Counter()
    mode=ledger["masking_mode"]
    core=mask_geometry(ledger,ref)
    for row in ledger["source_cut_rows"]:
        source,index=row["source_id"],row["source_segment_index"]
        line=raw.segment(source,index)
        require(line.hausdorff_distance(shape(row["source_geometry"]))<=ALIGNMENT_TOL and
                abs(line.length-row["source_length_m"])<=ALIGNMENT_TOL,
                f"Ledger source segment was moved: {source}/{index}")
        intervals=row["visible_source_intervals_m"]
        require(abs(line.length-sum(hi-lo for lo,hi in intervals)-row["removed_m"])<=LENGTH_TOL,
                f"Ledger length accounting differs: {source}/{index}")
        require(all(0<=lo<hi<=line.length+LENGTH_TOL for lo,hi in intervals),
                f"Ledger interval outside original source: {source}/{index}")
        keep=union_all([LineString([line.interpolate(lo),line.interpolate(hi)]) for lo,hi in intervals])
        if mode=="G" and core.area:
            # The area and aligned boundary shadow are withheld; transverse native
            # junctions remain lawful. The definitely exterior portion must all survive.
            exterior=line.difference(core.buffer(ledger["shadow_m"]))
            require(exterior.difference(keep.buffer(ALIGNMENT_TOL)).length<=LENGTH_TOL and
                    keep.intersection(core.buffer(-ALIGNMENT_TOL)).length<=LENGTH_TOL,
                    f"Local mask loses definite exterior or exposes interior: {source}/{index}")
        if mode=="H" and row["reason"]=="HISTORICAL_WHOLE_WAY":
            require(keep.is_empty and source in ledger["historical_hidden_way_ids"],
                    f"H changed frozen whole-way suppression: {source}/{index}")
        declared=keep.intersection(available)
        actual=union_all(by_source[source,index])
        require(declared.difference(actual.buffer(ALIGNMENT_TOL)).length<=LENGTH_TOL and
                actual.difference(declared.buffer(ALIGNMENT_TOL)).length<=LENGTH_TOL,
                f"Clipped source continuation is missing or leaks a masked part: {source}/{index}")
        check["source_cut_intervals_rebuilt"] += 1
        if mode=="G" and not declared.is_empty and source in ledger["historical_hidden_way_ids"]:
            check["historically_hidden_ways_with_proved_legal_continuation"] += 1
    return check


def validate_observed(obs, instance, ref, ledger, raw, blocked, inventory):
    ident = instance["id"]
    mode = mode_name(instance)
    legacy = historical_export(instance)
    radius = instance["context_radius_m"]
    require(set(obs)==SAFE_OBS and set(obs["context"])==CONTEXT_ROLES and obs["crs"]=="EPSG:32651",
            f"Unexpected predictor information field: {ident}")
    anchor = Point(obs["domain"]["anchor_xy"])
    historical_radius = anchor.buffer(40,quad_segs=32)
    available = shape(inventory["observation_available_geometry"]) if inventory else historical_radius
    require(anchor.buffer(30,quad_segs=32).symmetric_difference(shape(ref["domain_geometry"])).area <= AREA_TOL,
            f"30m fixed reference domain differs: {ident}")
    hidden_original = set(ref["source_id_hidden"])
    target_ids = set(ref["source_ids"]) if ref["label"] == "POSITIVE" else set()
    hidden = hidden_original | target_ids
    core = mask_geometry(ledger,ref)
    trace = core.buffer(0.015) if core.geom_type in {"LineString","MultiLineString"} else None
    hidden_area = core.buffer(-0.015) if core.area else None
    target_outline = core.boundary if core.area else None
    if target_ids and core.area:
        source_face = next((raw.area(name) for name in sorted(target_ids) if name in raw.objects),None)
        if source_face is not None:
            target_outline = source_face.boundary.intersection(anchor.buffer(30,quad_segs=32))
    outline_band = target_outline.buffer(0.015) if target_outline is not None else None
    nodes = {row["id"]:row for row in obs["nodes"]}
    edges = {row["id"]:row for row in obs["edges"]}
    require(len(nodes)==len(obs["nodes"]) and len(edges)==len(obs["edges"]), f"Duplicate node/fragment key: {ident}")
    graph_sources = defaultdict(list)
    incident = defaultdict(set)
    endpoints = Counter()
    scope_kinds = Counter()
    retained = defaultdict(dict)
    checks = Counter()
    old_geometry_outside = 0.
    if not legacy:
        require(radius in RADIUS_SET and inventory, f"Missing normalized scope record: {ident}")
        require(available.difference(anchor.buffer(radius,quad_segs=32)).area <= AREA_TOL,
                f"Available area exceeds declared observation radius: {ident}")
        require(inventory["node_count"]==len(nodes) and inventory["directed_edge_count"]==len(edges),
                f"Observation receipt counts do not match the actual graph: {ident}")
    for row in obs["nodes"]:
        node = row["id"]
        kind = get_point_mark(row)
        endpoints[kind] += 1
        if not legacy:
            require(anchor.distance(Point(row["xy"])) <= radius+OUTSIDE_EDGE_TOL,
                    f"Node escapes normalized observation scope: {ident}/{node}")
            if "CONTEXT_CLIP" in kind:
                require(abs(anchor.distance(Point(row["xy"]))-radius) < .35,
                        f"Context clip marker is not near observation radius: {ident}/{node}")
                require(not node.startswith("node/"), f"Artificial point uses native-node identity: {node}")
            if "MASK_BOUNDARY" in kind:
                require(not node.startswith("node/"), f"Mask cut uses native-node identity: {node}")
            if "SOURCE_CROP_LIMIT" in kind:
                require(available.boundary.distance(Point(row["xy"]))<=.35,
                        f"Source-limit marker is not near an available-area boundary: {ident}/{node}")
        if node.startswith("node/"):
            nkey = source_id(node)
            require(nkey in raw.objects and math.dist(raw.node(nkey),row["xy"]) <= ALIGNMENT_TOL,
                    f"Observed raw node is absent or moved: {ident}/{node}")
            if mode=="H" and not legacy and nkey in set(ref.get("masked_node_ids",[])):
                # The historical whole-way audit included exterior nodes incident to
                # separate lawful ways beyond its observed crop. Verify the independent
                # incidence below; such exterior nodes cannot describe the hidden target.
                require(ref["kind"].startswith("AREA_") and not core.buffer(-ALIGNMENT_TOL).contains(Point(row["xy"])),
                        f"Historically hidden interior node restored in H: {ident}/{node}")
                checks["historical_shared_exterior_nodes"]+=1
        require(not any(k in row for k in ("nodes","members","reference","old_route","route_cache","geometry_full")),
                f"Extra source data serialized on observed node: {ident}/{node}")
    for row, line in visible_lines(obs):
        way, index, sign = source_way_segment(row)
        require(line.length > 0 and way in raw.objects and index is not None and sign in {-1,1},
                f"Fragment lacks original source segment/direction: {ident}/{row['id']}")
        original = raw.segment(way,index)
        a,b = (Point(p) for p in line.coords)
        moved = not original.buffer(ALIGNMENT_TOL).covers(line)
        reversed_segment = (original.project(b)-original.project(a))*sign <= 0
        require(not moved and not reversed_segment,f"Moved/reversed original fragment: {ident}/{row['id']}")
        require(not blocked_segment(raw,way,index,sign,blocked,ref["group"]),
                f"Frozen S1 rejected direction/edge enters observations: {ident}/{row['id']}")
        tags = row.get("tags",{})
        raw_tags = raw.objects[way].get("tags",{})
        require(tags==raw_tags,f"Native fragment tags differ from original: {ident}/{row['id']}")
        require(not any(k in row for k in ("nodes","members","reference","old_route","route_cache","geometry_full")),
                f"Extra source data serialized on observed fragment: {ident}/{row['id']}")
        key=(way,index,sign)
        graph_sources[key].append(line)
        for end in (row["u"],row["v"]):
            incident[end].add((way,index,tags.get("layer", tags.get("level","0"))))
        if legacy:
            old_geometry_outside += line.difference(historical_radius).length
            continue
        require(line.difference(available.buffer(ALIGNMENT_TOL)).length<=LENGTH_TOL,
                f"Fragment exceeds declared source/radius clipping: {ident}/{row['id']}")
        if mode=="H":
            if ref["kind"].startswith("AREA_"):
                require(way not in hidden,f"Historically hidden whole way reappears: {ident}/{way}")
            else:
                archived_ids=ledger.get("historical_hidden_segments", [])
                require(not any(v.split(":")[0]==f"{way}/{index}" for v in archived_ids),
                        f"Historical hidden segment reappears: {ident}/{way}/{index}")
        if mode=="G":
            if way in hidden:
                # This is exactly the claimed legal continuation; it must be outside
                # the mask, from the original segment and not a resurrected inside edge.
                if hidden_area is not None:
                    require(line.intersection(hidden_area).length <= OUTSIDE_EDGE_TOL,
                            f"G reintroduced an originally hidden interior section: {ident}/{way}")
                if trace is not None and way in target_ids:
                    require(line.intersection(trace).length <= .05,
                            f"G reinstated part of the exact target centerline: {ident}/{way}")
                canonical=tuple(sorted(tuple(pt) for pt in line.coords))
                retained[way][canonical]=line
        if mode in {"G","H"} and ref["label"]=="POSITIVE":
            # Search geometry independently of source IDs. Only along-trace overlap
            # counts; crossing a hidden line at a point is not a duplicate trace.
            if trace is not None:
                match = aligned_shadow_length(line,core)
                direct = line.intersection(core).length
                require(direct <= OUTSIDE_EDGE_TOL and match <= .075,
                        f"Duplicate hidden centerline visible under another source: {ident}/{way}, overlap {match:.3f}m")
            elif outline_band is not None:
                match = aligned_shadow_length(line,target_outline)
                direct = line.intersection(target_outline).length
                require(direct <= OUTSIDE_EDGE_TOL and match <= .075,
                        f"Hidden footprint outline retained as a walking line: {ident}/{way}, overlap {match:.3f}m")
    for node, attaches in incident.items():
        if not node.startswith("node/"):
            require(len(attaches)==1,f"Synthetic cut welds separate raw edges/levels: {ident}/{node}")
        else:
            levels={str(v) for _,_,v in attaches if v is not None}
            require(len(levels)<=1 or "@" in node,
                    f"Different explicit levels are welded at a native graph ID: {ident}/{node}")
    for key, values in obs["context"].items():
        for row in values:
            g = shape(row["geometry"])
            name = item_id(row)
            scope_kinds[(key,row["kind"])]+=1
            require(not any(k in row for k in ("nodes","members","reference","old_route","route_cache","geometry_full")),
                    f"Relation/member or unmasked cache leaks through context row: {ident}/{name}")
            if not legacy:
                require(g.distance(anchor) <= radius+OUTSIDE_EDGE_TOL,f"Entire map feature lies outside observation: {ident}/{name}")
            if key != "hard" and not legacy and mode=="H":
                require(name not in hidden, f"Strongly masked object is serialized in context: {ident}/{name}")
            if key != "hard" and mode=="G":
                require(name not in target_ids, f"G exposes target area geometry directly: {ident}/{name}")
                if target_ids and core.area and g.area:
                    common = g.intersection(core).area
                    require(not (common > .7*core.area and common > .7*g.area),
                            f"G retains target face geometry under a different source: {ident}/{name}")
            # Compare legal full polygons to source rings; a carved mask-shaped
            # hole in a legitimate park/landcover would fail this exact check.
            if not legacy:
                equivalent = whole_raw_context(raw,row,available)
                if equivalent is False and mode!="S":
                    raise ValueError(f"Context object changed raw shape (possible carved negative mask): {ident}/{name}")
                if equivalent is True:
                    checks["exact_context_objects"]+=1
                else:
                    checks["context_objects_without_complete_raw_geometry"]+=1
    entrance = obs.get("registered_entrance")
    if entrance:
        name = entrance["id"]
        require(name in raw.objects and math.dist(entrance["xy"],raw.node(name)) < ALIGNMENT_TOL and
                entrance["tags"]==raw.objects[name].get("tags",{}), f"Registered entrance changed: {ident}/{name}")
    if ref["label"]=="NEGATIVE":
        hard = {item_id(row) for row in obs["context"]["hard"]}
        require(target_ids <= hard and set(ref["source_ids"]) <= hard, f"Known negative obstacle hidden: {ident}")
    if not legacy:
        checks.update(verify_mask_cuts(ledger,graph_sources,raw,available,ref))
    bands = length_bands(graph_sources,anchor) if not legacy else None
    total_retained=sum(g.length for group in retained.values() for g in group.values())
    domain=shape(ref["domain_geometry"])
    retained_outer=sum(g.difference(domain).length for group in retained.values() for g in group.values())
    if not legacy:
        require(abs(retained_outer-inventory["restored_legal_outer_length_m"])<=LENGTH_TOL,
                f"Independent undirected retained outer lengths differ {ident}")
    return ({
        "id":ident,"parent_task_id":instance["parent_task_id"],"mode":mode,"radius_m":radius,
        "observed_nodes":len(nodes),"directed_fragments":len(edges),"endpoint_kinds":dict(endpoints),
        "object_counts":{"/".join(k):v for k,v in sorted(scope_kinds.items())},
        "registered_entrance":entrance["id"] if entrance else None,"historical_export":legacy,
        "undirected_fragments_on_historically_hidden_ways":sum(len(v) for v in retained.values()),
        "historically_hidden_source_ways_retained":len(retained),
        "historically_hidden_way_all_legal_retained_m":total_retained,
        "historically_hidden_way_outside_fixed_30m_retained_m":retained_outer,
        "retained_original_way_lengths_m":{k:sum(g.length for g in v.values()) for k,v in sorted(retained.items())},
        "historical_full_segment_length_outside_40m":old_geometry_outside if legacy else None,
        "independent_source_checks":dict(checks),"native_network_length_by_band_m":bands
    },graph_sources)


def length_bands(graphs,anchor):
    unsigned=defaultdict(list)
    for (src,ix,_),pieces in graphs.items():
        unsigned[src,ix].extend(pieces)
    boundary40=anchor.buffer(40,quad_segs=32)
    boundary80=anchor.buffer(80,quad_segs=32)
    result=Counter()
    for lines in unsigned.values():
        geo=union_all(lines)
        first=geo.intersection(boundary40).length
        second=geo.intersection(boundary80).length
        result["0-40"]+=first
        result["40-80"]+=second-first
        result["80-160"]+=geo.length-second
    return dict(result)


def nesting(groups):
    comparisons = []
    for (parent,mode), rows in groups.items():
        keys = sorted(rows)
        for lower,higher in zip(keys,keys[1:]):
            small, large = rows[lower],rows[higher]
            require(set(small) <= set(large), f"Smaller context has original edges absent at greater radius: {parent}/{mode}")
            max_lost = 0.
            for segment, fragments in small.items():
                added = union_all(large[segment]).buffer(ALIGNMENT_TOL)
                lost = sum(f.difference(added).length for f in fragments)
                require(lost <= LENGTH_TOL,f"Inner visible fragment trimmed differently at larger radius: {parent}/{mode}")
                max_lost = max(lost,max_lost)
            comparisons.append({"parent_task_id":parent,"mode":mode,"radii":[lower,higher],
                                "compared_directed_source_segments":len(small),"max_lost_legal_m":max_lost})
    return comparisons


def main(args):
    root=args.root.resolve()
    data=args.data or root/"data"
    frozen=root/"frozen_r3"
    raw_base=frozen/"inputs/rev1/frozen_r4/data/source"
    manifests=read(data/"task_manifest.json")
    ledger_file=data/"mask_dependency_ledger.jsonl"
    ledgers = {(r["parent_task_id"],r["masking_mode"]):r for line in ledger_file.read_text(encoding="utf8").splitlines()
               if line.strip() and (r:=json.loads(line)).get("masking_mode") is not None} if ledger_file.exists() else {}
    inventory_file=data/"context_inventory.jsonl"
    context_inventory={r["id"]:r for line in inventory_file.read_text(encoding="utf8").splitlines()
                       if line.strip() and (r:=json.loads(line))} if inventory_file.exists() else {}
    blocked=blocked_rows(frozen/"data/semantics_edges.csv")
    frozen_cases={r["task_id"]:r for r in read(frozen/"data/benchmark/inventory.json")["tasks"]}
    caches={}
    parents={}
    variants={}
    counts=[]
    graphs=defaultdict(dict)
    for instance in manifests["instances"]:
        parent=instance["parent_task_id"]
        if args.task and parent not in args.task:
            continue
        ident=instance["id"]
        mode=mode_name(instance)
        observed_path,query_path,ref_path=active_paths(root,instance)
        observed,queries,ref=map(read,(observed_path,query_path,ref_path))
        old=frozen_cases[parent]
        require(hash_file(ref_path)==old["reference_sha256"] and hash_file(query_path)==old["queries_sha256"],
                f"Frozen reference or fixed query changed: {ident}")
        require(all(instance[k]==old[k] for k in ("group","split","label","kind")),
                f"Historical source/group/exposure contract changed: {ident}")
        require(len(queries["queries"])==old["query_count"],f"Query denominator changed: {ident}")
        raw_name=ref["source_clip"]
        if raw_name not in caches:
            caches[raw_name]=RawClip(raw_base/raw_name)
        raw=caches[raw_name]
        require(raw.sha256==ref["source_clip_sha256"],f"Original frozen clip digest differs {raw_name}")
        old_observed=read(frozen/"data/benchmark/observed"/(parent+".json"))
        require(old_observed["domain"]==observed["domain"] and
                old_observed["registered_entrance"]==observed["registered_entrance"],
                f"Anchor or actual entrance changed: {ident}")
        invariants=tuple(instance[k] for k in ("reference_sha256","query_sha256","prediction_domain_sha256",
                                              "evaluation_domain_sha256","grid_sha256"))
        if parent not in parents:
            raw.replay_reference(ref)
        require(parents.setdefault(parent,invariants)==invariants,f"Fixed denominator or grid differs: {ident}")
        is_legacy=historical_export(instance)
        if is_legacy:
            require(instance["observed_sha256"]==old["observed_sha256"], f"H0 original export changed: {ident}")
        else:
            mask=instance["mask_sha256"]
            require(variants.setdefault((parent,mode),mask)==mask,f"Cross-radius hidden contents differ: {ident}")
        ledger=ledgers.get((parent,mode),{})
        if not is_legacy:
            declared=ledger.get("mask_sha256")
            independent_sha=sha256(json.dumps({k:v for k,v in ledger.items() if k!="mask_sha256"},sort_keys=True,
                                               ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
            require(declared==mask==independent_sha,f"Frozen hidden ledger differs: {ident}")
        info,edges=validate_observed(observed,instance,ref,ledger,raw,blocked,context_inventory.get(ident))
        counts.append(info)
        if not is_legacy:
            graphs[(parent,mode)][instance["context_radius_m"]]=edges
    require(counts,"No frozen observed cases found")
    require(len(variants)<=60,"Task version budget exceeded")
    if manifests["status"]=="FROZEN_SOURCE_EXPORT" and not args.task:
        require(set(parents)==set(frozen_cases),"A historical parent or difficult query disappeared")
    normalized = [r for r in counts if not r["historical_export"]]
    frozen_total=sum(frozen_cases[p]["query_count"] for p in parents)
    output=dict(status="INDEPENDENT_OBSERVATION_AND_MASK_AUDIT",scope="RAW_GEOMETRY_RECONSTRUCTION_AND_APP_INPUT_CONTRACT",
                observed_inputs=len(counts), normalized_observed_inputs=len(normalized),parent_cases=len(parents),
                fixed_parent_queries=frozen_total, normalized_parent_mask_versions=len(variants),
                manifest_sha256=hash_file(data/"task_manifest.json"),
                original_raw_clips=[{"name":k,"sha256":v.sha256} for k,v in sorted(caches.items())],
                nested_pairs=nesting(graphs),observed=counts,external_requests=0)
    write(args.out or root/"audits/context_input_audit.json",output)
    print(f"Independent input audit: {len(counts)} observed inputs, {len(parents)} parents, {frozen_total} fixed parent queries.",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--data",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--task",action="append")
    main(parser.parse_args())
