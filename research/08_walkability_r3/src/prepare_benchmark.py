"""Prepare independent, frozen R3 observations, routes queries and withheld references."""
import argparse
from collections import Counter
import csv
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
from pathlib import Path
import sys

from shapely.geometry import LineString, Point, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
RADIUS = 30
GRID = 20
CROP = 40
SHADOW = 0.05
MIN_AREA_OVERLAP = 20
SPLITS = {"sh-huangpu-01": "development", "sh-library": "development",
          "sh-tower": "selection", "sh-wukang": "selection",
          "sh-newworld": "confirmation", "sh-exhibition": "confirmation"}
POSITIVE_SURFACES = {"PEDESTRIAN_AREA", "PAVING"}
PHYSICAL = {"BUILDING", "WATER", "FLOWERBED", "BARRIER", "RESTRICTED", "RESTRICTED_AREA"}
SHADOW_WIDTHS = [0.5, 1.0, 2.0]  # buffer radii in metres, evaluation proxies only
APPROVED_OBS = {"task_id", "crs", "domain", "registered_entrance", "nodes", "edges", "context"}


def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def stable(*terms):
    return sha256(":".join(map(str, ("WALK_R3_REFERENCE_V1", *terms))).encode()).hexdigest()


def raw_id(value):
    return value.split("@")[0]


def way_id(edge):
    return "/".join(edge["id"].split("/")[:2])


def blocked_s1(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {(r["scene_id"], r["source_id"], int(r["segment_index"])) for r in csv.DictReader(stream)
                if r["S1_status"] != "KEEP_NATIVE"}


def blocked_edge(scene, edge, blocked):
    source, idx = edge["id"].rsplit("/", 1)
    return (scene, source, int(idx.split(":")[0])) in blocked


def grid_points(bounds):
    x0, y0, x1, y1 = bounds
    for x in range(math.floor(x0 / GRID) * GRID, math.ceil(x1 / GRID) * GRID + 1, GRID):
        for y in range(math.floor(y0 / GRID) * GRID, math.ceil(y1 / GRID) * GRID + 1, GRID):
            yield Point(x, y)


def study_window(anchor):
    # Explicit benchmark reference window uses the same polygonal disk convention
    # as Shapely point buffering, never a route-line buffer.
    return anchor.buffer(RADIUS, quad_segs=32)


def select_legacy_anchor(legacy, reference):
    target = Point(legacy["target"]["xy"])
    if legacy["target"]["registered"]:
        return target, "REGISTERED_DOOR"
    nodes = {n["id"]: Point(n["xy"]) for n in legacy["nodes"]}
    origin = nodes[legacy["origin"]]
    middle = reference.representative_point()
    choices = [p for p in grid_points(middle.buffer(RADIUS).bounds)
               if max(p.distance(origin), p.distance(target)) <= RADIUS-3]
    if not choices:
        raise ValueError("No fixed grid window for legacy task")
    return min(choices, key=lambda p: stable("study-grid", p.x, p.y)), "FROZEN_STUDY_GRID"


def clip_visible(nodes, edges, context, anchor):
    crop = anchor.buffer(CROP)
    nodes = {row["id"]: row for row in nodes}
    visible = [e for e in edges if LineString([nodes[e["u"]]["xy"], nodes[e["v"]]["xy"]]).intersects(crop)]
    used = {e[k] for e in visible for k in ("u", "v")}
    blocks = {k: [item for item in values if shape(item["geometry"]).intersects(crop)]
              for k, values in context.items()}
    return [nodes[n] for n in sorted(used)], visible, blocks


def query_pair(src, dst, query_id):
    return dict(query_id=query_id,
                source={"id": src["id"], "xy": src["xy"], "role": "NATIVE_NODE"},
                target={"id": dst["id"], "xy": dst["xy"],
                        "role": "REGISTERED_DOOR" if dst.get("registered") else "NATIVE_NODE"})


def legacy_cases(r2, frozen, blocked, omitted):
    base = r2 / "data/masking"
    for row in read(base / "inventory.json")["tasks"]:
        op, rp = base / row["observed"], base / row["reference"]
        assert digest(op) == row["observed_sha256"] and digest(rp) == row["reference_sha256"]
        legacy, old = read(op), read(rp)
        geom = shape(old["geometry"])
        anchor, role = select_legacy_anchor(legacy, geom)
        window = study_window(anchor)
        allowed = [e for e in legacy["edges"] if not blocked_edge(row["group"], e, blocked)]
        nodes, edges, ctx = clip_visible(legacy["nodes"], allowed, legacy["context"], anchor)
        point_index = {n["id"]: n for n in nodes}
        masked_source_blocked = any(blocked_edge(row["group"], {"id": f}, blocked)
                                    for f in old["hidden_edges"] if way_id({"id": f}) == old["original_way_id"])
        if (legacy["origin"] not in point_index or
                (not legacy["target"]["registered"] and legacy["target"]["id"] not in point_index) or
                masked_source_blocked):
            omitted.append(dict(group=row["group"], legacy_task=old["task_id"],
                                reason="NOT_VALID_UNDER_FROZEN_S1_WALKING_POLICY"))
            continue
        primary = query_pair(point_index[legacy["origin"]], legacy["target"], "Q1")
        queries = [primary]
        # A second fixed observed-network pair exercises the same frozen surface.
        # Avoid endpoint alternatives within a metre of the original endpoints.
        visible_near = [n for n in nodes if Point(n["xy"]).distance(anchor) <= RADIUS-3 and
                        Point(n["xy"]).distance(Point(primary["source"]["xy"])) >= 8 and
                        Point(n["xy"]).distance(Point(primary["target"]["xy"])) >= 5 and
                        "@" not in n["id"]]
        if visible_near:
            alternative = min(visible_near, key=lambda n: stable("alternate", n["id"]))
            queries.append(query_pair(alternative, legacy["target"], "Q2"))
        if row["label"] == "NEGATIVE":
            blockers = {item["id"]: shape(item["geometry"]) for item in ctx["hard"]}
            from shapely import union_all
            blocker_geometry = union_all([blockers[ident] for ident in old["negative_obstacle_ids"]])
            if blocker_geometry.area == 0:
                raise ValueError("Line-only obstacle requires separate routing evaluation")
            score_geom = blocker_geometry.intersection(window)
            assert score_geom.area > 0 and geom.intersection(blocker_geometry).length > 0
            typ = "MAPPED_OBSTACLE_NEGATIVE"
            source_ids = old["negative_obstacle_ids"]
            shadow_ids = []
        else:
            score_geom = geom.intersection(window)
            assert geom.difference(window).length < 1e-5
            support = [item["id"] for item in ctx["support"]
                       if item["kind"] in {"PEDESTRIAN_AREA", "PAVING", "PARK"}
                       and shape(item["geometry"]).intersection(geom).length > .5]
            typ = "LINE_MASK_WITH_RETAINED_SUPPORT" if support else "LINE_MASK_NO_AREA_SUPPORT"
            source_ids = [old["original_way_id"]]
            shadow_ids = sorted({"/".join(k.split("/")[:2]) for k in old["hidden_edges"]})
        observed = dict(crs="EPSG:32651", domain={"anchor_xy": list(anchor.coords[0]), "anchor_role": role},
                        registered_entrance=legacy["target"] if legacy["target"]["registered"] else None,
                        nodes=nodes, edges=edges, context=ctx)
        reference = dict(label=row["label"], kind=typ, group=row["group"], split=SPLITS[row["group"]],
                         geometry=mapping(score_geom), domain_geometry=mapping(window), source_ids=source_ids,
                         source_clip=old["source_clip"], source_clip_sha256=old["source_clip_sha256"],
                         legacy_task=old["task_id"], control_chord=mapping(geom) if row["label"] == "NEGATIVE" else None,
                         source_id_hidden=shadow_ids, masked_node_ids=old["hidden_intermediate_nodes"],
                         positive_support_ids=support if row["label"] == "POSITIVE" else [],
                         score_geometry_role="native_way_centerline" if row["label"] == "POSITIVE" else "mapped_hard_obstacle",
                         evaluation_site_was_previously_observed=True,
                         area_reference_width="UNOBSERVED" if row["label"] == "POSITIVE" else None)
        assert digest(frozen / "data/source" / reference["source_clip"]) == reference["source_clip_sha256"]
        yield observed, queries, reference


def area_observation(clip, geom, id_, rings, blocked):
    """Suppress raw selected face, all supporting shadows, and whole touching way IDs."""
    outer_ids, inner_ids = rings
    hidden = {id_, *outer_ids}
    hidden_lines = {int(x.split("/")[1]) for x in hidden if x.startswith("way/")}
    # Any permitted graph way that recreates positive internal geometry is masked
    # whole. No new boundary-snapped node, clipped edge or derived cache is exported.
    core = geom.buffer(-SHADOW)
    if core.is_empty:
        return None
    for i in clip.line_tree.query(geom.buffer(SHADOW), predicate="intersects"):
        edge = clip.segs[int(i)]
        line = clip.lines[int(i)]
        if (line.intersection(core).length > 0.10 or
                (line.length > 0.1 and line.difference(geom.boundary.buffer(SHADOW)).length <= 0.025)):
            hidden_lines.add(edge.way)
    hidden.update(f"way/{n}" for n in hidden_lines)
    context = {}
    for group, objs in (("hard", clip.hard), ("background", clip.bg), ("support", clip.support)):
        visible = []
        for row in objs:
            if row["id"] in hidden:
                if group == "hard":
                    return None  # do not hide a physical object that conflicts with the face
                continue
            rgeo = row["geometry"]
            # An independent broad park can remain. Exact or near-covering native
            # pedestrian/paving duplicates or an outline-only shadow cannot.
            overlap = geom.intersection(rgeo).area
            near_duplicate = overlap > .70 * geom.area and overlap > .70 * rgeo.area
            covered_support = row["kind"] in POSITIVE_SURFACES and overlap > .05
            if group == "support" and (near_duplicate or covered_support):
                hidden.add(row["id"])
                continue
            visible.append(dict(id=row["id"], kind=row["kind"], geometry=mapping(rgeo), tags=row["tags"]))
        context[group] = visible
    # A removed duplicate surface's ring can itself be a native route record.
    # Suppress it in all observed sources except independently retained hazards.
    for ident in sorted(hidden.copy()):
        try:
            rr = clip.source.rings(ident)
        except KeyError:
            continue
        if rr:
            hidden.update(f"way/{o['id']}" for o in rr[0])
    if any(row["id"] in hidden for row in context["hard"]):
        return None
    for group in ("background", "support"):
        context[group] = [row for row in context[group] if row["id"] not in hidden]
    nodes, edges = {}, []
    for i, seg in enumerate(clip.segs):
        identity = f"way/{seg.way}"
        if (clip.scene["scene_id"], identity, seg.index) in blocked or identity in hidden or seg.evidence not in {"MAPPED_PEDESTRIAN_WAY", "EXPLICIT_FOOT_ON_WAY_AXIS"}:
            continue
        if seg.a[1:] != ("0", "0") or seg.b[1:] != ("0", "0"):
            continue
        tags = clip.source.ways[seg.way].get("tags", {})
        for k in (seg.a[0], seg.b[0]):
            ident = f"node/{k}"
            nodes[ident] = dict(id=ident, xy=clip.points[k], tags=clip.source.nodes[k].get("tags", {}))
        for direction in seg.directions:
            a, b = (seg.a[0], seg.b[0]) if direction == 1 else (seg.b[0], seg.a[0])
            edges.append(dict(id=f"{identity}/{seg.index}:{direction}", u=f"node/{a}", v=f"node/{b}",
                              tags=tags, kind="NATIVE_LINEAR"))
    return nodes, edges, context, sorted(hidden), inner_ids


def area_window(clip, geom, center, nodes):
    """Screen fixed windows by usable observed ports and a nontrivial reference intersection."""
    # Rank grid anchors before any prediction. This is retrospective task curation.
    eligible = [p for p in grid_points(geom.bounds)
                if p.distance(center) <= 500 and p.distance(geom) <= 18]
    if not eligible:
        return None
    # Keep the shortlist bounded; prefer site-local grid anchors independently of route performance.
    geometry_only = None
    for anchor in sorted(eligible, key=lambda p: (p.distance(center), stable("grid", p.x, p.y)))[:160]:
        win = study_window(anchor)
        held = geom.intersection(win)
        if held.area < MIN_AREA_OVERLAP or held.area > .90 * win.area:
            continue
        if geometry_only is None:
            geometry_only = anchor, win, held, []
        visible = [row for row in nodes.values()
                   if Point(row["xy"]).distance(anchor) <= RADIUS-2 and
                   Point(row["xy"]).distance(geom.boundary) <= 10]
        visible.sort(key=lambda n: stable("port", n["id"]))
        # Distinct native pairs on observed linework adjacent to the reference;
        # the pair coordinates enter the query file, never the region builder.
        query = []
        for i, a in enumerate(visible[:60]):
            for b in visible[i+1:60]:
                ln = LineString([a["xy"], b["xy"]])
                if not 8 <= ln.length <= 42 or ln.intersection(held).length < 3:
                    continue
                if clip.blockers(ln):
                    continue
                query.append(query_pair(a, b, f"Q{len(query)+1}"))
                if len(query) == 3:
                    break
            if len(query) == 3:
                break
        if query:
            return anchor, win, held, query
    return geometry_only


def area_cases(r2, rev1, scan, blocked):
    frozen = rev1 / "frozen_r4"
    sys.path.insert(0, str(rev1))
    from src.native_adapter import PROJECT, Source, load_frozen_engine

    spec = spec_from_file_location("walk_r2_reference_tools", r2 / "src/prepare_masking.py")
    old = module_from_spec(spec)
    spec.loader.exec_module(old)
    engine = load_frozen_engine(frozen)
    scenes = read(frozen / "runs/source_scene_contracts.json")["scenes"]
    inventory = read(frozen / "runs/source_open_spaces.json")["features"]
    for scene in scenes:
        group = scene["scene_id"]
        options = [row for row in inventory
                   if row["scene_id"] == group and row["category"] == "PEDESTRIAN_AREA"]
        scan[group] = dict(native_area_candidates=len(options), candidates=[])
        if not options:
            continue
        clip = old.Clip(frozen, scene, engine, Source)
        center = Point(PROJECT(*scene["target"]))
        for row in sorted(options, key=lambda r: stable(r["native_id"])):
            id_ = row["native_id"]
            decision = {"source_id": id_}
            scan[group]["candidates"].append(decision)
            geom = clip.source.area(id_)
            if (geom is None or not old.permission(row["tags"]) or not old.ground_node(row["tags"])):
                decision["reason"] = "INVALID_OR_RESTRICTED_NATIVE_FACE"
                continue
            rings = ([f"way/{x}" for x in row.get("outer_way_ids", [])],
                     [f"way/{x}" for x in row.get("inner_way_ids", [])])
            obs = area_observation(clip, geom, id_, rings, blocked)
            if obs is None:
                decision["reason"] = "POSITIVE_GEOMETRY_CONFLICT_OR_NO_MASKABLE_CORE"
                continue
            nodes, edges, ctx, hidden, inner_rings = obs
            fixed = area_window(clip, geom, center, nodes)
            if fixed is None:
                decision["reason"] = "NO_NONTRIVIAL_NATIVE_AREA_IN_FIXED_WINDOW"
                continue
            anchor, window, held, queries = fixed
            nodes, edges, ctx = clip_visible(nodes.values(), edges, ctx, anchor)
            observed = dict(crs="EPSG:32651", domain={"anchor_xy": list(anchor.coords[0]),
                            "anchor_role": "FROZEN_STUDY_GRID"}, registered_entrance=None,
                            nodes=nodes, edges=edges, context=ctx)
            points_before = set()
            for ident in hidden:
                if ident.startswith("way/"):
                    way = clip.source.ways.get(int(ident.split("/")[1]))
                    if way:
                        points_before.update(way["nodes"])
            visible_ids = {raw_id(n["id"]) for n in nodes}
            independent_inner_geometry_ids = [i for i in inner_rings if any(
                row["id"] == i for group in ctx.values() for row in group)]
            reference = dict(label="POSITIVE", kind="AREA_AND_INTERNAL_LINES_MASKED", group=group,
                             split=SPLITS[group], geometry=mapping(held), domain_geometry=mapping(window),
                             source_ids=[id_], source_id_hidden=hidden, source_clip=clip.path.name,
                             source_clip_sha256=digest(clip.path), legacy_task=None, control_chord=None,
                             masked_node_ids=sorted(f"node/{n}" for n in points_before
                                                    if f"node/{n}" not in visible_ids),
                             retained_shared_endpoint_node_ids=sorted(f"node/{n}" for n in points_before
                                                                     if f"node/{n}" in visible_ids),
                             retained_independent_inner_geometry_ids=independent_inner_geometry_ids,
                             positive_support_ids=[], score_geometry_role="native_pedestrian_face",
                             evaluation_site_was_previously_observed=True,
                             source_tags=row["tags"], reference_m2=held.area)
            decision["reason"] = ("EVALUABLE_FIXED_WINDOW_WITH_QUERY_PAIRS" if queries else
                                  "AREA_ONLY_NO_VISIBLE_NONCONFLICTING_QUERY_PAIR")
            yield observed, queries, reference


def audit_one(obs, queries, ref):
    if set(obs) != APPROVED_OBS or set(obs["context"]) != {"hard", "background", "support"}:
        raise ValueError("Observed input schema changed")
    if set(obs["domain"]) != {"anchor_xy", "anchor_role"}:
        raise ValueError("Unapproved domain payload")
    if not all(query[k]["id"] in {n["id"] for n in obs["nodes"]} or
               obs["registered_entrance"] and query[k]["id"] == obs["registered_entrance"]["id"]
               for query in queries for k in ("source", "target")):
        raise ValueError("Query endpoint not a visible source node")
    hidden, obscured = set(ref["source_id_hidden"]), set(ref["masked_node_ids"])
    by_node = {row["id"]: row for row in obs["nodes"]}
    for row in by_node.values():
        if set(row) != {"id", "xy", "tags"} or raw_id(row["id"]) in obscured:
            raise ValueError("Unapproved or hidden node")
    for rows in obs["context"].values():
        for row in rows:
            if set(row) != {"id", "kind", "geometry", "tags"} or row["id"] in hidden:
                raise ValueError("Unapproved/hidden source object in observed context")
    geom = shape(ref["geometry"])
    for row in obs["edges"]:
        if set(row) != {"id", "u", "v", "tags", "kind"} or row["kind"] != "NATIVE_LINEAR":
            raise ValueError("Unapproved observed graph schema")
        if way_id(row) in hidden and (not ref["legacy_task"] or
                                     "/".join(row["id"].split(":")[0].split("/")[:2]) in ref["source_ids"]):
            raise ValueError("Reference way in observed graph")
        if ref["label"] != "POSITIVE":
            continue
        line = LineString([by_node[row["u"]]["xy"], by_node[row["v"]]["xy"]])
        if ref["kind"].startswith("LINE_") and line.length > .001 and geom.buffer(SHADOW, cap_style="flat").covers(line):
            raise ValueError("Coincident hidden line in observed graph")
        if ref["kind"].startswith("AREA_") and (
                line.intersection(geom.buffer(-SHADOW)).length > .10 or
                line.length > 0.1 and line.difference(geom.boundary.buffer(SHADOW)).length <= .025):
            raise ValueError("Hidden internal/boundary face line in observed graph")
    if ref["kind"].startswith("AREA_"):
        for row in obs["context"]["support"]:
            support = shape(row["geometry"])
            if row["kind"] in POSITIVE_SURFACES and support.intersection(geom).area > .05:
                raise ValueError("Coincident pedestrian/paving reference surface in observed")


def main(args):
    frozen = args.rev1 / "frozen_r4"
    scans = {}
    blocked = blocked_s1(args.semantics)
    omitted = []
    area = list(area_cases(args.r2, args.rev1, scans, blocked))
    legacy = list(legacy_cases(args.r2, frozen, blocked, omitted))
    rows = []
    files = []
    for obs, queries, ref in area + legacy:
        sig = stable(ref["group"], ref["kind"], *ref["source_ids"], ref["legacy_task"])
        task = "W" + sig[:11]
        # No shared native reference or spatial window may cross a split. Geometry
        # coincidence checks use only reference evaluation here, never the model.
        frame = shape(ref["domain_geometry"])
        if any(o["split"] != ref["split"] and (
                set(ref["source_ids"]) & set(o["source_ids"]) or
                set(ref["source_id_hidden"]) & set(o["source_id_hidden"]) or
                frame.intersection(shape(o["domain_geometry"])).area > 0.1) for o in rows):
            omitted.append(dict(task_id=task, group=ref["group"], source_ids=ref["source_ids"],
                                reason="CROSS_SPLIT_SHARED_SOURCE_OR_SPATIAL_WINDOW"))
            continue
        obs["task_id"] = ref["task_id"] = task
        audit_one(obs, queries, ref)
        members = {"observed": obs, "queries": {"task_id": task, "queries": queries}, "reference": ref}
        record = {"task_id": task, "label": ref["label"], "kind": ref["kind"], "group": ref["group"],
                  "split": ref["split"], "anchor_role": obs["domain"]["anchor_role"], "query_count": len(queries)}
        for role, payload in members.items():
            path = args.output / role / f"{task}.json"
            write(path, payload)
            record[f"{role}_sha256"] = digest(path)
        rows.append(ref)
        files.append(record)
    protocol = dict(status="FROZEN_BEFORE_PREDICTION", crs="EPSG:32651", radius_m=RADIUS,
                    fixed_grid_spacing_m=GRID, observation_crop_m=CROP, line_shadow_m=SHADOW,
                    source_splits=SPLITS, true_area_min_reference_m2=MIN_AREA_OVERLAP,
                    widths_buffer_radius_m=SHADOW_WIDTHS,
                    case_selection="historical bounded frozen raw cases, one per native area source; no usable visible pairs means area-only",
                    predicted_area="INFERRED_WALKABLE only; native classification reported separately",
                    positive_thresholds={"eligible_geometry_coverage": .5, "line_coverage": .5},
                    separation="No shared source reference ID or positive-area window across splits",
                    query_file_read="After frozen per-task surface only",
                    native_policy="Exclude source segments blocked or unresolved under frozen S1, keyed by scene/way/source index",
                    native_policy_sha256=digest(args.semantics),
                    localization="Selected eligible windows on fixed grid with knowledge of approximate control locality; not blind gap localization",
                    field_truth=False, external_requests=0)
    write(args.protocol, protocol)
    summary = dict(status="FROZEN_BEFORE_PREDICTION", tasks=files, omitted=omitted, raw_area_scan=scans,
                   counts=[dict(split=split, case_type=kind, n=n) for (split, kind), n in sorted(
                           Counter((r["split"], r["kind"]) for r in files).items())],
                   protocol_sha256=digest(args.protocol))
    write(args.output / "inventory.json", summary)
    print(json.dumps(dict(tasks=len(files), counts=summary["counts"], omitted=omitted, area_scan=scans), ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rev1", type=Path, default=ROOT / "inputs/rev1")
    p.add_argument("--r2", type=Path, default=ROOT / "inputs/r2")
    p.add_argument("--output", type=Path, default=ROOT / "data/benchmark")
    p.add_argument("--semantics", type=Path, default=ROOT / "data/semantics_edges.csv")
    p.add_argument("--protocol", type=Path, default=ROOT / "config/benchmark.json")
    main(p.parse_args())
