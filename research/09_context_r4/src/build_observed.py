"""Construct context exports from verified frozen OSM. No prediction code or results."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import shutil

import networkx as nx
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
RADII = (40, 80, 160)
SCORE_RADIUS = 30
SHADOW = 0.05
EPS = 1e-6
CONTRACT = "CONTEXT_V1"
PILOT = ("Wc4183046a70", "W6daddd19fdb", "W745941f0f92", "W0440b97497a")
WALK = {"MAPPED_PEDESTRIAN_WAY", "EXPLICIT_FOOT_ON_WAY_AXIS"}
POSITIVE_SURFACES = {"PEDESTRIAN_AREA", "PAVING"}
CTX = ("hard", "background", "support")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def sign(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical(data) + "\n")


def lines(geometry):
    if geometry.geom_type == "LineString":
        if geometry.length > EPS:
            yield geometry
    else:
        for part in getattr(geometry, "geoms", []):
            yield from lines(part)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def native_key(key):
    raw = f"node/{key[0]}"
    return raw if key[1:] == ("0", "0") else f"{raw}@{key[1]}:{key[2]}"


def coverage_polygon(bounds, project):
    west, south, east, north = bounds
    corners = [(west, south), (east, south), (east, north), (west, north)]
    coords = []
    for a, b in zip(corners, corners[1:] + corners[:1]):
        for n in range(32):
            u = n / 32
            coords.append(project(a[0] * (1-u) + b[0] * u, a[1] * (1-u) + b[1] * u))
    return Polygon(coords)


def interval_pieces(native, visible):
    """Project result vertices onto this exact original segment, sorted by source order."""
    result = []
    for part in lines(visible):
        a = native.project(Point(part.coords[0]))
        b = native.project(Point(part.coords[-1]))
        lo, hi = sorted((a, b))
        if hi-lo > EPS:
            result.append((lo, hi))
    return sorted(result)


def ground_segment(seg):
    return seg.evidence in WALK and seg.a[1:] == seg.b[1:] == ("0", "0")


def raw_members(source, identity):
    if not identity.startswith("relation/"):
        return set()
    return {f"{item['type']}/{item['ref']}" for item in source.obj(identity)["members"]}


def mask_contract(ref, clip, old_r2):
    is_area = ref["kind"].startswith("AREA_")
    negative = ref["label"] == "NEGATIVE"
    strong_ids = set(ref["source_id_hidden"])
    refs = set(ref["source_ids"])
    if negative:
        return {"core": None, "basis": "NO_MASK_FOR_MAPPED_OBSTACLE_NEGATIVE",
                "line_parts": [], "full_ids": set(), "hidden_edges": set(),
                "old_nodes": set(), "strong_ids": set(), "target_dependency_ids": set()}
    if is_area:
        ident = next(iter(refs))
        geometry = clip.source.area(ident)
        if geometry is None:
            raise ValueError(f"Missing frozen area {ident}")
        old_members = set()
        for target in refs:
            old_members.update(raw_members(clip.source, target))
        # Remove entire duplicate support polygons, never a target-shaped hole from them.
        suppressed_support = set(refs)
        for row in clip.support:
            g = row["geometry"]
            if not g.intersects(geometry):
                continue
            overlap = g.intersection(geometry).area
            near_duplicate = overlap > .7 * g.area and overlap > .7 * geometry.area
            if (near_duplicate or row["kind"] in POSITIVE_SURFACES and overlap > SHADOW
                    or bool(raw_members(clip.source, row["id"]) & old_members)):
                suppressed_support.add(row["id"])
        return {"core": geometry, "basis": "FULL_ORIGINAL_NATIVE_FACE_AND_OUTLINE_SHADOW",
                "line_parts": [], "full_ids": suppressed_support, "hidden_edges": set(),
                "old_nodes": set(ref["masked_node_ids"]), "strong_ids": strong_ids,
                "target_dependency_ids": old_members | suppressed_support}
    reference = shape(ref["geometry"])
    parts = [(LineString([a, b]), (b[0]-a[0], b[1]-a[1]))
             for a, b in zip(reference.coords, list(reference.coords)[1:]) if math.dist(a, b) > EPS]
    old = old_r2[ref["legacy_task"]]
    return {"core": reference, "basis": "FULL_ORIGINAL_R2_MISSING_LINE",
            "line_parts": parts, "full_ids": set(refs), "hidden_edges": set(old["hidden_edges"]),
            "old_nodes": set(old["hidden_intermediate_nodes"]), "strong_ids": strong_ids,
            "target_dependency_ids": set(refs)}


def line_parts(geometry):
    return [(LineString([a,b]),(b[0]-a[0],b[1]-a[1]))
            for part in lines(geometry) for a,b in zip(part.coords,list(part.coords)[1:])
            if math.dist(a,b)>EPS]


def line_mask(native, contract, bands, tree=None):
    p, q = native.coords[0], native.coords[-1]
    vector = q[0]-p[0], q[1]-p[1]
    candidates = []
    selected = range(len(bands)) if tree is None else sorted(tree.query(native,predicate="intersects"))
    for index in selected:
        piece,direction = contract["line_parts"][index]
        band = bands[index]
        cosine = abs(vector[0]*direction[0] + vector[1]*direction[1])/(native.length*piece.length)
        if cosine >= .98 and native.intersection(band).length > .025:
            candidates.append(band)
    return unary_union(candidates) if candidates else None


def local_masks(clip, ref, anchor, contract, blocked):
    """Apply a source-layer mask once before projecting any context radius."""
    maximum = anchor.buffer(RADII[-1], quad_segs=32)
    core = contract["core"]
    area = ref["kind"].startswith("AREA_")
    geometric_policy={"line_parts":line_parts(core.boundary)} if area else contract
    line_bands = [p.buffer(SHADOW, cap_style="flat") for p, _ in geometric_policy["line_parts"]]
    band_tree = STRtree(line_bands)
    mask_modes = ["N"] if core is None else ["H", "G"]
    linework = {mode: [] for mode in mask_modes}
    cuts = {mode: [] for mode in mask_modes}
    for i in sorted(clip.line_tree.query(maximum, predicate="intersects")):
        i = int(i)
        seg, native = clip.segs[i], clip.lines[i]
        way = f"way/{seg.way}"
        src = f"{way}/{seg.index}"
        if native.length <= EPS or (ref["group"], way, seg.index) in blocked or (area and not ground_segment(seg)):
            continue
        shadow = line_mask(native, geometric_policy, line_bands, band_tree)
        geometric_cut = core if area and shadow is None else (core.union(shadow) if area else shadow)
        for mode in mask_modes:
            reason = None
            full_remove = False
            if mode == "H":
                if area and way in contract["strong_ids"]:
                    full_remove, reason = True, "HISTORICAL_WHOLE_WAY"
                elif src in contract["hidden_edges"]:
                    full_remove, reason = True, "HISTORICAL_HIDDEN_SEGMENT"
                elif not area and (f"node/{seg.a[0]}" in contract["old_nodes"] or
                                   f"node/{seg.b[0]}" in contract["old_nodes"]):
                    full_remove, reason = True, "HISTORICAL_HIDDEN_INTERMEDIATE_NODE"
            if full_remove:
                visible = []
            elif geometric_cut is not None and native.intersection(geometric_cut).length > EPS:
                reason = "TARGET_CORE_OR_DUPLICATE_SHADOW"
                visible = interval_pieces(native, native.difference(geometric_cut))
            else:
                visible = [(0, native.length)]
            if reason:
                cuts[mode].append({"source_id": way, "source_segment_index": seg.index, "reason": reason,
                                   "source_geometry": mapping(native), "source_length_m": native.length,
                                   "removed_m": native.length - sum(hi-lo for lo, hi in visible),
                                   "visible_source_intervals_m": visible})
            linework[mode].extend((seg, native, lo, hi, reason) for lo, hi in visible)
    return linework, cuts


def context_visible(clip, ref, mode, contract, disk):
    groups = {key: [] for key in CTX}
    hidden = set(contract["full_ids"])
    if mode == "H":
        hidden |= contract["strong_ids"]
    # Do not export a masked geometry through a duplicate serialized context object.
    # Keep independently sourced restrictions, even when overlapping the hidden target.
    removed = []
    for group, objects in zip(CTX, (clip.hard, clip.bg, clip.support)):
        for row in objects:
            g = row["geometry"]
            if not g.intersects(disk):
                continue
            ident = row["id"]
            core = contract["core"]
            coincident_line = (core is not None and core.geom_type == "LineString"
                               and group == "support" and g.geom_type == "LineString"
                               and g.intersection(core.buffer(SHADOW, cap_style="flat")).length > EPS)
            if group != "hard" and (ident in hidden or coincident_line):
                removed.append({"source_id": ident, "layer": group, "reason": "TARGET_OR_SHADOW_POLYGON_REMOVED_WHOLE",
                                "source_area_m2": g.area})
                continue
            if g.geom_type not in {"Polygon", "MultiPolygon"}:
                g = g.intersection(disk)
            if not g.is_empty:
                groups[group].append({"id": ident, "kind": row["kind"], "geometry": mapping(g),
                                      "tags": row.get("tags", {})})
    return groups, removed


def endpoint(seg, native, clip, source_coverage, measure, local_bound):
    # Only original shared nodes join source ways; synthetic cuts are segment-local,
    # sharing identity across reverse arcs but never across nearby or different levels.
    if measure < EPS:
        key = seg.a
    elif native.length-measure < EPS:
        key = seg.b
    else:
        key = None
    point = native.interpolate(measure)
    if key is not None:
        ident = native_key(key)
        xy = clip.points[key[0]]
        role = "SOURCE_CROP_LIMIT" if source_coverage.boundary.distance(point) <= .2 else "NATIVE_ENDPOINT"
        tags = clip.source.nodes[key[0]].get("tags", {})
    else:
        role = "SOURCE_CROP_LIMIT" if source_coverage.boundary.distance(point) <= EPS*8 else local_bound
        ident = f"fragment-end/{seg.way}/{seg.index}/{measure:.9f}"
        xy, tags = point.coords[0], {}
    return {"id": ident, "xy": list(xy), "tags": tags, "endpoint_kind": role}


def export_observed(clip, ref, historical, mode, radius, selected, contract, coverage):
    anchor = Point(historical["domain"]["anchor_xy"])
    requested = anchor.buffer(radius, quad_segs=32)
    disk = requested.intersection(coverage)
    nodes, edges, records = {}, [], []
    for seg, native, ml, mh, reason in selected:
        initial = LineString([native.interpolate(ml), native.interpolate(mh)])
        if not initial.intersects(disk):
            continue
        way = f"way/{seg.way}"
        for lo, hi in interval_pieces(native, initial.intersection(disk)):
            # roundoff at a mask/crop intersection cannot create a native vertex
            left = "MASK_BOUNDARY_ENDPOINT" if abs(lo-ml) < EPS and ml > EPS else "CONTEXT_CLIP_ENDPOINT"
            right = "MASK_BOUNDARY_ENDPOINT" if abs(hi-mh) < EPS and native.length-mh > EPS else "CONTEXT_CLIP_ENDPOINT"
            a = endpoint(seg, native, clip, coverage, lo, left)
            b = endpoint(seg, native, clip, coverage, hi, right)
            if a["id"] == b["id"]:
                continue
            nodes[a["id"]], nodes[b["id"]] = a, b
            tag = clip.source.ways[seg.way].get("tags", {})
            fragment = f"{way}/{seg.index}/{lo:.9f}-{hi:.9f}"
            for direction in seg.directions:
                u, v = (a, b) if direction == 1 else (b, a)
                edges.append({"id": f"{fragment}:{direction}", "source_id": way,
                              "source_segment_index": seg.index, "source_direction": direction,
                              "u": u["id"], "v": v["id"], "tags": tag, "kind": "NATIVE_LINEAR"})
            records.append({"source_id": way, "source_segment_index": seg.index, "geometry": mapping(LineString(
                [a["xy"], b["xy"]])), "length_m": math.dist(a["xy"], b["xy"]), "fragment_id": fragment,
                            "source_range_m": [lo, hi], "source_length_m": native.length,
                            "formerly_whole_way_masked": way in contract["strong_ids"] and mode=="G",
                            "reason": reason})
    ctx, removed = context_visible(clip, ref, mode, contract, disk)
    door = historical["registered_entrance"]
    observed = {"task_id": ref["task_id"], "crs": historical["crs"], "domain": historical["domain"],
                "registered_entrance": door, "nodes": [nodes[i] for i in sorted(nodes)], "edges": edges, "context": ctx}
    graph = nx.Graph()
    graph.add_edges_from((e["u"], e["v"]) for e in edges)
    score = shape(ref["domain_geometry"])
    touches = [record for record in records if shape(record["geometry"]).intersects(score)]
    legal_outer = sum(shape(r["geometry"]).difference(score).length for r in records)
    outer_native_len = sum(shape(r["geometry"]).difference(score).length for r in records
                           if r["formerly_whole_way_masked"])
    all_geometry = [shape(r["geometry"]) for r in records] + [
        shape(r["geometry"]) for rows in ctx.values() for r in rows]
    envelopes = [g.bounds for g in all_geometry if not g.is_empty]
    envelope = ([min(b[0] for b in envelopes), min(b[1] for b in envelopes),
                 max(b[2] for b in envelopes), max(b[3] for b in envelopes)] if envelopes else None)
    flags = [a for a, applies in (("SOURCE_CROP_LIMIT", not coverage.covers(requested)),
            ("NO_VISIBLE_NETWORK", not edges), ("NO_POSITIVE_CONTEXT", not ctx["support"])) if applies]
    counters = {
        "source_available_fraction": disk.area/requested.area, "source_extent_status":
            "SOURCE_CROP_LIMIT" if "SOURCE_CROP_LIMIT" in flags else "COMPLETE_WITHIN_FROZEN_CLIP",
        "observation_requested_geometry": mapping(requested), "observation_available_geometry": mapping(disk),
        "source_coverage_geometry": mapping(coverage), "returned_geometry_envelope_utm": envelope,
        "retained_complete_polygon_count": sum(shape(r["geometry"]).geom_type in {"Polygon", "MultiPolygon"}
                                                for rows in ctx.values() for r in rows),
        "native_nodes": sum(n["endpoint_kind"] == "NATIVE_ENDPOINT" for n in nodes.values()),
        "node_count": len(nodes), "directed_edge_count": len(edges), "fragment_count": len(records),
        "component_count": nx.number_connected_components(graph),
        "road_length_m": sum(record["length_m"] for record in records),
        "road_length_outside_fixed_domain_m": legal_outer,
        "restored_legal_outer_length_m": outer_native_len,
        "restored_source_fragments": [r for r in records if r["formerly_whole_way_masked"]],
        "inner_circle_touching_fragments": len(touches),
        "inner_circle_contact_points": len({(round(p.x, 7), round(p.y, 7)) for r in touches
                   for p in getattr(shape(r["geometry"]).intersection(score.boundary), "geoms",
                                    [shape(r["geometry"]).intersection(score.boundary)])
                   if p.geom_type=="Point" and not p.is_empty}),
        "context_type_counts": {key: dict(sorted(Counter(r["kind"] for r in ctx[key]).items())) for key in CTX},
        "legal_registered_entrances": int(bool(door)), "endpoint_type_counts":
            dict(sorted(Counter(n["endpoint_kind"] for n in nodes.values()).items())),
        "flags": flags, "suppressed_context_count": len(removed),
    }
    return observed, counters, records, removed


def verify_visible_geometry(observed, records, contract, mode, counter, query, ref):
    expected_fields = {"task_id","crs","domain","registered_entrance","nodes","edges","context"}
    assert set(observed)==expected_fields
    assert set(observed["context"])==set(CTX)
    disk = shape(counter["observation_available_geometry"])
    core = contract["core"]
    area_inside = core.buffer(-SHADOW) if core is not None and core.area else None
    line_shadow = core.buffer(SHADOW-1e-7, cap_style="flat") if core is not None and core.geom_type=="LineString" else None
    for rec in records:
        g = shape(rec["geometry"])
        assert g.difference(disk.buffer(1e-7)).length < EPS, (ref["task_id"], mode, rec["fragment_id"])
        assert not rec["formerly_whole_way_masked"] or mode=="G"
        if area_inside is not None:
            assert g.intersection(area_inside).length < EPS, (ref["task_id"], mode, rec["fragment_id"])
        if line_shadow is not None:
            assert not line_shadow.covers(g), (ref["task_id"], mode, rec["fragment_id"])
    all_nodes = {n["id"] for n in observed["nodes"]}
    for e in observed["edges"]:
        assert e["u"] in all_nodes and e["v"] in all_nodes
    missing = {p["id"] for q in query["queries"] for p in (q["source"],q["target"])
               if p["role"]!="REGISTERED_DOOR" and p["id"] not in all_nodes}
    counter["unavailable_frozen_query_endpoint_ids"]=sorted(missing)
    hidden = contract["full_ids"] | (contract["strong_ids"] if mode=="H" else set())
    for k, rows in observed["context"].items():
        for r in rows:
            assert set(r)=={"id","kind","geometry","tags"}
            assert r["id"] not in hidden or k=="hard", r["id"]


def prove_nested(record_rows):
    previous = {}
    for radius, rows in record_rows:
        current = defaultdict(list)
        for row in rows:
            current[(row["source_id"],row["source_segment_index"])].append(row["source_range_m"])
        for ident, intervals in previous.items():
            for lo, hi in intervals:
                assert any(a<=lo+EPS and b>=hi-EPS for a,b in current[ident]), (radius, ident,lo,hi)
        previous = current


def synthetic_semantics_note():
    return {"status":"NO_APPLICABLE_REAL_S_TASK",
            "area_scan":"No independent neutral boundary for the same native face. A broad commercial land-use outline near W0caca58bc41 overlapped 98.2% of the target face but was 2.2× its total area. It cannot be substituted for the target outline.",
            "line_scan":"No independently represented neutral line matching the masked target geometry was identified.",
            "why_not_generate":"Deriving a neutral shape from a withheld reference would reconstruct an input from the answer.",
            "contract":"If supplied independently, retain geometry with no walkability/category/name/source tag revealing its target role. Keep all independent hard restrictions and evaluate a whole-neutral-shape diagnostic separately."}


def main(args):
    target = args.output
    target.mkdir(parents=True, exist_ok=True)
    r3 = args.r3
    old = r3/"data/benchmark"
    rev1 = r3/"inputs/rev1"
    frozen = rev1/"frozen_r4"
    r2 = r3/"inputs/r2"
    adapter = module("context_r4_frozen_native_adapter", rev1/"src/native_adapter.py")
    curate_r2 = module("context_r4_frozen_r2_curator",r2/"src/prepare_masking.py")
    engine = adapter.load_frozen_engine(frozen)
    with (r3/"data/semantics_edges.csv").open(encoding="utf-8-sig",newline="") as s:
        blocked = {(r["scene_id"],r["source_id"],int(r["segment_index"])) for r in csv.DictReader(s)
                   if r["S1_status"]!="KEEP_NATIVE"}
    scenes = {s["scene_id"]:s for s in read(frozen/"runs/source_scene_contracts.json")["scenes"]}
    old_r2 = {x["task_id"]:read(r2/"data/masking"/x["reference"])
              for x in read(r2/"data/masking/inventory.json")["tasks"]}
    matrix, inventory, ledgers, parents = [], [], [], []
    grid_sha = digest({"crs":"EPSG:32651","origin":"GLOBAL_INTEGER_UTM","cell_m":1,"domain_radius_m":30})
    active = None
    orig_inventory = read(old/"inventory.json")["tasks"]
    chosen = set(PILOT if args.pilot else args.parents or [x["task_id"] for x in orig_inventory])
    if chosen - {x["task_id"] for x in orig_inventory}:
        raise ValueError("Requested parent is not in the frozen historical inventory")
    for task in sorted(orig_inventory,key=lambda t:(t["group"],t["task_id"])):
        ident = task["task_id"]
        if ident not in chosen:
            continue
        if active != task["group"]:
            scene = scenes[task["group"]]
            clip = curate_r2.Clip(frozen,scene,engine,adapter.Source)
            coverage = coverage_polygon(scene["snapshot_bounds_wsen"],adapter.PROJECT)
            active = task["group"]
        ro, oo, qo = (old/key/f"{ident}.json" for key in ("reference","observed","queries"))
        assert all(sign(p)==task[key+"_sha256"] for p,key in ((ro,"reference"),(oo,"observed"),(qo,"queries")))
        ref,historical,query = read(ro),read(oo),read(qo)
        ref_domain_hash = digest(ref["domain_geometry"])
        assert shape(ref["domain_geometry"]).symmetric_difference(
            Point(historical["domain"]["anchor_xy"]).buffer(SCORE_RADIUS,quad_segs=32)).area < EPS
        assert sign(clip.path)==ref["source_clip_sha256"]
        exported = {}
        for role, source in (("reference",ro),("queries",qo)):
            p=target/role/f"{ident}.json"
            p.parent.mkdir(exist_ok=True,parents=True)
            with source.open("rb") as f,p.open("xb") as out:
                shutil.copyfileobj(f,out)
            exported[role]=p
        base = {"parent_task_id":ident,"query":exported["queries"].relative_to(ROOT).as_posix(),
                "reference":exported["reference"].relative_to(ROOT).as_posix(),
                "query_sha256":task["queries_sha256"],"reference_sha256":task["reference_sha256"],
                "prediction_domain_sha256":ref_domain_hash,"evaluation_domain_sha256":ref_domain_hash,
                "grid_sha256":grid_sha,"group":ref["group"],"label":ref["label"],"kind":ref["kind"],
                "split":ref["split"],"exposure":"HISTORICAL_SOURCE_DIAGNOSTIC_ONLY",
                "prediction_domain":{"anchor_xy":historical["domain"]["anchor_xy"],"radius_m":30,"geometry_sha256":ref_domain_hash},
                "evaluation_domain":{"anchor_xy":historical["domain"]["anchor_xy"],"radius_m":30,"geometry_sha256":ref_domain_hash},
                "display_extent":{"street_target_radius_m":160,"detail_radius_m":30,"prediction_input_role":"SEPARATE"},
                "query_count":len(query["queries"]),"source_clip":ref["source_clip"],
                "source_clip_sha256":ref["source_clip_sha256"]}
        if ident in PILOT:
            e0=target/"observed"/f"{ident}_H0_ORIGINAL_EXPORT.json"
            e0.parent.mkdir(parents=True,exist_ok=True)
            with oo.open("rb") as f,e0.open("xb") as out:
                shutil.copyfileobj(f,out)
            matrix.append(dict(base,id=e0.stem,masking_mode="H0",context_radius_m=40,
                               mask_sha256=digest({"policy":"FROZEN_R3_HISTORICAL_STRONG","reference_sha256":task["reference_sha256"]}),
                               observed=e0.relative_to(ROOT).as_posix(),observed_sha256=sign(e0)))
        contract = mask_contract(ref,clip,old_r2)
        linework,cuts=local_masks(clip,ref,Point(historical["domain"]["anchor_xy"]),contract,blocked)
        for mode in linework:
            ledger={"parent_task_id":ident,"masking_mode":mode,"contract_version":CONTRACT,
                    "source_clip":ref["source_clip"],"source_clip_sha256":ref["source_clip_sha256"],
                    "hidden_geometry":mapping(contract["core"]) if contract["core"] is not None else None,
                    "core_measurement_m2":contract["core"].area if contract["core"] is not None else None,
                    "core_measurement_m":contract["core"].length if contract["core"] is not None and contract["core"].area==0 else None,
                    "mask_basis":contract["basis"],"shadow_m":SHADOW,"historical_hidden_way_ids":sorted(contract["strong_ids"]),
                    "removed_context_source_ids":sorted(contract["full_ids"] | (contract["strong_ids"] if mode=="H" else set())),
                    "historical_hidden_segments":sorted(contract["hidden_edges"]),
                    "historical_hidden_node_ids":sorted(contract["old_nodes"]),
                    "hidden_relation_member_ids":sorted(contract["target_dependency_ids"]),
                    "source_cut_rows":cuts[mode],"source_cut_scope":"UNTRIMMED_SOURCE_SEGMENTS_INTERSECTING_MAX_CONTEXT",
                    "forbidden_serialized_dependencies":["raw nodes arrays","relation member arrays","old route","derived cache"],
                    "background_geometry_policy":"RETAIN_COMPLETE_INDEPENDENT_POLYGONS_OR_OMIT_DUPLICATE_WHOLE_NO_PUNCHOUT",
                    "boundary_shadow_policy":"EXACT_FACE_AND_ALIGNED_RING_SHADOWS_0_05M; LEGITIMATE_TRANSVERSE_CONTACT_RETAINED",
                    "score_core_policy":"SAME_REFERENCE_AND_SAME_30M_EVALUATION_DOMAIN_AS_PARENT"}
            mask_sha=digest(ledger)
            ledgers.append(dict(ledger,mask_sha256=mask_sha))
            per_radius=[]
            for radius in RADII:
                observed, counts, records, removed = export_observed(clip,ref,historical,mode,radius,
                    linework[mode],contract,coverage)
                verify_visible_geometry(observed,records,contract,mode,counts,query,ref)
                per_radius.append((radius,records))
                name=f"{ident}_{mode}_{radius:03d}"
                p=target/"observed"/(name+".json")
                write(p,observed)
                matrix.append(dict(base,id=name,masking_mode=mode,context_radius_m=radius,mask_sha256=mask_sha,
                                   observed=p.relative_to(ROOT).as_posix(),observed_sha256=sign(p)))
                inventory.append(dict(counts,id=name,parent_task_id=ident,masking_mode=mode,context_radius_m=radius,
                                      source_clip=ref["source_clip"],source_clip_sha256=ref["source_clip_sha256"],
                                      mask_sha256=mask_sha,context_objects_removed=removed,
                                      area_geometry_policy="WHOLE_NATIVE_POLYGON_INTERSECTING_AVAILABLE_DISK",
                                      cut_policy="NETWORK_CLIPPED_THEN_SERIALIZED_WITH_ORIGINAL_SEGMENT_PROVENANCE"))
            prove_nested(per_radius)
        parents.append(dict(base,modes=sorted(linework),semantic_shape="NOT_APPLICABLE_NO_INDEPENDENT_NEUTRAL_GEOMETRY"
                            if ref["label"]=="POSITIVE" else "NOT_APPLICABLE_OBSTACLE_CONTROL"))
        print(f"EXPORT {ident} {','.join(linework)}",flush=True)
    for name, rows in (("context_inventory.jsonl",inventory),("mask_dependency_ledger.jsonl",ledgers)):
        with (target/name).open("x",encoding="utf-8",newline="\n") as stream:
            for row in rows: stream.write(canonical(row)+"\n")
    doc={"status":"FROZEN_SOURCE_EXPORT_PILOT" if args.pilot else "FROZEN_SOURCE_EXPORT", "contract_version":CONTRACT,
         "parent_count":len(parents),"mode_version_count":len(ledgers),"radius_instances":len(inventory),
         "version_count_policy":"H/N carries original 25 parent task versions forward, G adds revised versions, H0 is an archived original export of the same task and not a new mode version",
         "preserved_historical_parent_exports":sum(x["masking_mode"]=="H0" for x in matrix),
         "historical_parent_group_policy":"SAME_PARENT_NO_CROSS_SPLIT_VARIANTS",
         "neutral_semantic_mode":synthetic_semantics_note(),"instances":matrix,"parents":parents}
    if len(ledgers)>60: raise ValueError("Version budget exceeded")
    write(target/"task_manifest.json",doc)
    print(canonical({k:doc[k] for k in ("status","parent_count","mode_version_count","radius_instances")}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r3",type=Path,default=ROOT/"frozen_r3")
    p.add_argument("--output",type=Path,default=ROOT/"data")
    p.add_argument("--pilot",action="store_true")
    p.add_argument("--parents",nargs="*")
    args=p.parse_args()
    args.output=args.output.resolve()
    main(args)
