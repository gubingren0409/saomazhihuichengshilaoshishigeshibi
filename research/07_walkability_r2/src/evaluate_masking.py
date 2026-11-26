"""Score frozen masked observations without importing the inference implementation."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
WGS84 = Transformer.from_crs(32651, 4326, always_xy=True).transform
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
DENIED = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry", "restricted"}
METHODS = ("I0", "I1", "I2", "ABL-I", "ABL-C")
INFERRED = "INFERRED_ALLOWED"
EPS = 1e-5


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def source_keys(obs):
    return {row["id"]: row for row in obs["nodes"]}


def audit_observation(obs, ref, locked):
    required = {"task_id", "kind", "crs", "origin", "target", "nodes", "edges", "context"}
    if set(obs) != required or obs["task_id"] != ref["task_id"] or obs["target"]["id"] != ref["target_id"]:
        raise ValueError("Unapproved observed keys or inconsistent task identity")
    hidden_edges = set(ref["hidden_edges"])
    hidden_nodes = set(ref["hidden_intermediate_nodes"])
    way = ref["original_way_id"]
    raw_context = [r for rs in obs["context"].values() for r in rs]
    if way and any(r["id"] == way for r in raw_context):
        raise ValueError("Hidden way in visible context")
    if any(r["id"].split("@")[0] in hidden_nodes for r in obs["nodes"]):
        raise ValueError("Hidden intermediate node is visible")
    if ref["label"] != "POSITIVE":
        return
    line = shape(ref["geometry"])
    shadow = line.buffer(locked["shadow_m"], cap_style="flat")
    nodes = source_keys(obs)
    for row in obs["edges"]:
        base = row["id"].rsplit(":", 1)[0]
        if base in hidden_edges or (way and base.startswith(way + "/")):
            raise ValueError("Hidden raw way/direction appears in the observed graph")
        section = LineString([nodes[row["u"]]["xy"], nodes[row["v"]]["xy"]])
        if section.length > .001 and shadow.covers(section):
            raise ValueError("Hidden line geometry has an observed duplicate")


def hard_contacts(line, obstacles, target):
    hits = []
    for obj in obstacles:
        geo = shape(obj["geometry"])
        contact = line.intersection(geo)
        if contact.is_empty:
            continue
        if (obj["id"] == target.get("building_id") and contact.geom_type == "Point"
                and contact.distance(Point(target["xy"])) <= EPS and line.relate_pattern(geo, "F********")):
            continue
        if obj["kind"] == "BUILDING" and line.relate_pattern(geo, "F********"):
            # Building exterior is allowed for a local walk, interior is not.
            continue
        hits.append(obj["id"])
    return sorted(set(hits))


def permitted(tags):
    return (tags.get("locked") != "yes" and tags.get("foot", tags.get("access")) not in DENIED
            and not any(key in tags for key in ("access:conditional", "foot:conditional", "oneway:conditional")))


def inspect_route(method, obs):
    route = method["route"]
    if route is None:
        return [], None, None
    segments = route["edges"]
    total = 0.0
    joined = []
    previous = None
    nodes = source_keys(obs)
    visible = {r["id"]: r for r in obs["edges"]}
    for row in segments:
        pts = row["xy"]
        if previous is not None and previous != row["u"]:
            raise ValueError("Route graph edge sequence is discontinuous")
        previous = row["v"]
        if len(pts) < 2:
            raise ValueError("Invalid route section")
        if joined and math.dist(joined[-1], pts[0]) > EPS:
            raise ValueError("Route geometry is discontinuous")
        joined.extend(pts if not joined else pts[1:])
        line = LineString(pts)
        if row["kind"] != INFERRED:
            original = visible[row["id"]]
            a, b = nodes[original["u"]], nodes[original["v"]]
            directed = LineString([a["xy"], b["xy"]])
            if (line.difference(directed.buffer(EPS)).length > EPS
                    or directed.project(Point(pts[0])) >= directed.project(Point(pts[-1]))):
                raise ValueError("Route does not follow an original visible edge and direction")
            if not all(permitted(t) for t in (original["tags"], a["tags"], b["tags"])):
                raise ValueError("Visible route traverses an explicit prohibition")
            if hard_contacts(line, obs["context"]["hard"], obs["target"]):
                raise ValueError("Routed visible segment contacts a mapped hard conflict")
        if abs(line.length - row["length_m"]) > EPS:
            raise ValueError("Route section metric length differs")
        total += line.length
    if abs(total - route["length_m"]) > EPS:
        raise ValueError("Route length differs")
    origin = nodes[obs["origin"]]["xy"]
    if not joined:
        if math.dist(PROJECT(*route["end_wgs84"]), origin) > EPS:
            raise ValueError("Zero-length route did not stay on its origin")
        joined = [origin]
    if math.dist(joined[0], origin) > EPS:
        raise ValueError("Route origin moved")
    gap = math.dist(joined[-1], obs["target"]["xy"])
    if method["residual_m"] is not None and abs(gap-method["residual_m"]) > EPS:
        raise ValueError("Measured terminal residual differs")
    if method["reached_original_target"] and gap > EPS:
        raise ValueError("Reached result moved the original target")
    return segments, total, gap


def score(obs, ref, result, lock, methods):
    reference = shape(ref["geometry"])
    obstacles = obs["context"]["hard"]
    original_endpoints = [Point(reference.coords[0]), Point(reference.coords[-1])]
    if ref["label"] == "NEGATIVE":
        control = hard_contacts(reference, obstacles, obs["target"])
        if not set(ref["negative_obstacle_ids"]) <= set(control):
            raise ValueError("The negative control chord lacks its declared raw visible conflict")
    records = []
    support_kinds = sorted({r["kind"] for r in obs["context"]["support"]
                            if r["id"] in ref["positive_observed_support_ids"]})
    support = ("TAGGED_PEDESTRIAN_FACE" if "PEDESTRIAN_AREA" in support_kinds else
               "PAVING_OR_PARK_CONTEXT" if support_kinds else "NO_MAPPED_AREA_SUPPORT")
    for method in methods:
        trial = result["methods"][method]
        sections, length, gap = inspect_route(trial, obs)
        used = [LineString(r["xy"]) for r in sections if r["kind"] == INFERRED]
        if trial["used_inferred_edges"] != len(used):
            raise ValueError("Declared used inferred edge count differs from the selected route")
        admitted = [r for r in trial["candidates"] if r["status"] == INFERRED]
        if len(admitted) != trial["admitted_edges"]:
            raise ValueError("Declared admission count differs")
        collisions = {}
        for c in admitted:
            line = LineString(c["candidate_xy"])
            found = hard_contacts(line, obstacles, obs["target"])
            if found:
                collisions[c["id"]] = found
        selected_hits = sorted({o for line in used for o in hard_contacts(line, obstacles, obs["target"])})
        ref_cover, end_max, used_m = 0.0, None, 0.0
        recovery = False
        if used:
            combined = unary_union(used)
            used_m = sum(line.length for line in used)
            ref_cover = reference.intersection(combined.buffer(lock["reference_buffer_m"])).length/reference.length
            inferred_endpoints = [Point(pt) for ln in used for pt in [ln.coords[0], ln.coords[-1]]]
            end_max = max(min(p.distance(q) for q in inferred_endpoints) for p in original_endpoints)
            recovery = (ref["label"] == "POSITIVE" and trial["reached_original_target"] and not selected_hits
                        and end_max <= lock["endpoint_tolerance_m"]
                        and ref_cover >= lock["minimum_reference_coverage"]
                        and used_m <= lock["max_inferred_ratio"] * reference.length)
        records.append(dict(task_id=ref["task_id"], kind=ref["kind"], label=ref["label"], group=ref["group"],
                            split=ref["split"], method=method, route_status=trial["status"],
                            observed_support_stratum=support, observed_support_kinds=support_kinds,
                            reached=trial["reached_original_target"], route_length_m=length,
                            residual_m=gap, selected_inferred_m=used_m, admitted_candidates=len(admitted),
                            accepted_conflicting_edges=collisions, selected_conflicts=selected_hits,
                            exposed_control_conflicts=sum(bool(set(hard_contacts(LineString(c["candidate_xy"]), obstacles,
                                                                obs["target"])) & set(ref["negative_obstacle_ids"]))
                                                          for c in trial["candidates"] if len(c["candidate_xy"]) >= 2),
                            negative_false_connection=ref["label"] == "NEGATIVE" and bool(collisions),
                            controlled_recovery=recovery, reference_coverage=ref_cover,
                            reference_endpoint_max_distance_m=end_max,
                            reason_counts=dict(Counter(c["reason"] for c in trial["candidates"]))))
    return records


def table(rows):
    cells = []
    for split in ("all", "development", "selection", "confirmation"):
        for kind in ("ALL_TASKS", "NETWORK_GAP_TASK", "REGISTERED_DOOR_TASK"):
            for method in METHODS:
                curr = [r for r in rows if r["method"] == method and (split == "all" or r["split"] == split)
                        and (kind == "ALL_TASKS" or r["kind"] == kind)]
                if not curr:
                    continue
                positives = [r for r in curr if r["label"] == "POSITIVE"]
                negatives = [r for r in curr if r["label"] == "NEGATIVE"]
                cells.append(dict(split=split, kind=kind, method=method, positive=len(positives),
                                  recovered=sum(r["controlled_recovery"] for r in positives),
                                  negative=len(negatives), false_connections=sum(r["negative_false_connection"] for r in negatives),
                                  exposed_control_conflicts=sum(r["exposed_control_conflicts"] > 0 for r in negatives),
                                  accepted_conflicting_edges=sum(len(r["accepted_conflicting_edges"]) for r in curr),
                                  with_conditional_route=sum(r["reached"] and r["selected_inferred_m"] > 0 for r in curr)))
    return cells


def support_table(rows):
    cells = []
    groups = sorted({(r["method"], r["kind"], r["observed_support_stratum"]) for r in rows
                     if r["label"] == "POSITIVE"})
    for method, kind, support in groups:
        group = [r for r in rows if r["label"] == "POSITIVE" and
                 (r["method"], r["kind"], r["observed_support_stratum"]) == (method, kind, support)]
        cells.append(dict(method=method, kind=kind, observed_support_stratum=support,
                          positive=len(group), recovered=sum(r["controlled_recovery"] for r in group)))
    return cells


def feature(items, geometry, task_id, role, **props):
    if not geometry.is_empty:
        items.append(dict(type="Feature", geometry=mapping(transform(WGS84, geometry)),
                          properties=dict(task_id=task_id, role=role, **props)))


def visual_features(obs, ref, result, verdicts):
    items = []
    ident = ref["task_id"]
    nearby = Point(obs["target"]["xy"]).buffer(34)
    nodes = source_keys(obs)
    seen = set()
    for r in obs["edges"]:
        unique = frozenset([r["u"], r["v"]])
        if unique not in seen:
            seen.add(unique)
            ln = LineString([nodes[r["u"]]["xy"], nodes[r["v"]]["xy"]])
            if ln.intersects(nearby):
                feature(items, ln.intersection(nearby), ident, "observed_network", source_id=r["id"], tags=r["tags"])
    for block, role in (("hard", "observed_obstacle"), ("background", "observed_background"), ("support", "observed_support")):
        for r in obs["context"][block]:
            g = shape(r["geometry"])
            if g.intersects(nearby):
                feature(items, g.intersection(nearby), ident, role, source_id=r["id"], kind=r["kind"], tags=r["tags"])
    feature(items, Point(nodes[obs["origin"]]["xy"]), ident, "origin", source_id=obs["origin"])
    feature(items, Point(obs["target"]["xy"]), ident, "target", source_id=obs["target"]["id"], registered=obs["target"]["registered"])
    role = "reference_hidden" if ref["label"] == "POSITIVE" else "blocked_control"
    feature(items, shape(ref["geometry"]), ident, role, source_id=ref["original_way_id"],
            negative_obstacles=ref["negative_obstacle_ids"], split=ref["split"], kind=ref["kind"])
    for m in ("I1", "I2", "ABL-C"):
        if m not in result["methods"]:
            continue
        for cand in result["methods"][m]["candidates"]:
            xy = cand["candidate_xy"]
            if len(xy) < 2:
                continue
            g = LineString(xy)
            if g.length <= EPS:
                continue
            role = ("inferred_selected" if cand["route_selected"] else "inferred_candidate"
                    if cand["status"] == INFERRED else "rejected")
            feature(items, g, ident, role, method=m, status=cand["status"], source_id=cand.get("source_id"),
                    reason=cand["reason"], verdict=next(r["controlled_recovery"] for r in verdicts if r["method"] == m))
    return items


def raw_reference_check(reference, source):
    if reference["label"] == "POSITIVE":
        row = source.obj(reference["original_way_id"])
        expected = LineString([source.projected[n] for n in row["nodes"]])
        current = shape(reference["geometry"])
        if not current.equals_exact(expected, EPS) and not current.equals_exact(expected.reverse(), EPS):
            raise ValueError("Reference geometry does not match the raw masked way")
    else:
        for ident in reference["negative_obstacle_ids"]:
            kind, raw_id = ident.split("/")
            row = (source.ways if kind == "way" else source.relations)[int(raw_id)]
            raw = source.area(ident) if row.get("tags", {}).get("building") or row.get("tags", {}).get("natural") == "water" or kind == "relation" else None
            if raw is None and kind == "way":
                coords = source.known_coords(row)
                raw = LineString(coords) if len(coords) > 1 else None
            if raw is None or not shape(reference["geometry"]).intersects(raw):
                raise ValueError("Negative control no longer hits the original map object")


def main(masking, predictions, output, visual, config, frozen, split=None, methods=None):
    sys.path.insert(0, str(frozen.parent))
    from src.native_adapter import Source

    inventory, pred, lock = read(masking / "inventory.json"), read(predictions), read(config)
    if inventory["status"] != "FROZEN_BEFORE_PREDICTION":
        raise ValueError("Reference inventory was not frozen")
    tasks = [r for r in inventory["tasks"] if split is None or r["split"] == split]
    by_task = {r["task_id"]: r for r in pred["predictions"]}
    read_logs = pred["read_log"]
    if set(by_task) != {r["task_id"] for r in tasks} or len(by_task) != len(pred["predictions"]):
        raise ValueError("Missing or duplicate prediction")
    logs = {}
    for row in read_logs:
        path = str(row["path"]).replace("\\", "/")
        if "/observed/" not in "/" + path or "/reference/" in "/" + path:
            raise ValueError(f"Prediction read outside the observed-only scope: {path}")
        if row["task_id"] in logs:
            raise ValueError("Duplicate prediction observation read record")
        logs[row["task_id"]] = row
    if set(logs) != set(by_task):
        raise ValueError("Prediction read log does not cover all tasks")
    rows, layers, ref_by_group, obs_windows = [], [], {}, []
    source_cache = {}
    for item in tasks:
        op, rp = masking / item["observed"], masking / item["reference"]
        if digest(op) != item["observed_sha256"] or digest(rp) != item["reference_sha256"]:
            raise ValueError("Observed or reference file changed after freezing")
        obs, ref = read(op), read(rp)
        log = logs[ref["task_id"]]
        if Path(log["path"]).as_posix() != item["observed"] or log["bytes"] != op.stat().st_size:
            raise ValueError("Prediction read path or size does not match the locked task observation")
        if log["sha256"] != item["observed_sha256"]:
            raise ValueError("Prediction digest does not match the exact frozen observation")
        audit_observation(obs, ref, lock)
        original = frozen / "data/source" / ref["source_clip"]
        if digest(original) != ref["source_clip_sha256"]:
            raise ValueError("Reference source clip bytes changed")
        if original not in source_cache:
            source_cache[original] = Source(read(original))
        raw_reference_check(ref, source_cache[original])
        result = by_task[ref["task_id"]]
        expected = (("I0", "I1", "I2") if ref["split"] == "confirmation" else METHODS) if methods is None else methods
        if set(result["methods"]) != set(expected):
            raise ValueError(f"Unexpected prediction method scope for {ref['task_id']}")
        outcomes = score(obs, ref, result, lock, expected)
        rows.extend(outcomes)
        if visual is not None:
            layers.extend(visual_features(obs, ref, result, outcomes))
        ref_by_group.setdefault(ref["group"], ref["split"])
        if ref_by_group[ref["group"]] != ref["split"]:
            raise ValueError("One spatial/site group straddles splits")
        obs_windows.append((ref["group"], ref["original_way_id"], Point(obs["target"]["xy"]),
                            shape(ref["geometry"])))
    for i, (group, way, center, line) in enumerate(obs_windows):
        for other, oid, other_center, other_line in obs_windows[i+1:]:
            if way and way == oid:
                raise ValueError("One raw reference way appears in two tasks")
            if line.distance(other_line) < lock["spacing_m"] - EPS:
                raise ValueError("Repeated or overlapping control/reference geometry")
            if group != other and center.distance(other_center) < 2 * lock["crop_m"] - EPS:
                raise ValueError("Cross-group observation circles overlap")
    result = dict(status="INDEPENDENT_MASKING_RECOMPUTED", roles="REFERENCE_CURATOR_AND_INDEPENDENT_GEOMETRY_EVALUATOR",
                  input_inventory_sha256=digest(masking / "inventory.json"), prediction_sha256=digest(predictions),
                  reviewed_tasks=len(tasks), reviewed_groups=len(ref_by_group), read_scope="OBSERVED_ONLY_APP_LOG",
                  hidden_reference_scoring="ENDPOINTS_COVERAGE_LENGTH_KNOWN_CONFLICTS",
                  independent_field_checks=0, outcomes=rows, aggregate=table(rows),
                  support_strata=support_table(rows))
    write(output, result)
    if visual is not None:
        write(visual, dict(type="FeatureCollection", features=layers))
    print(json.dumps(dict(verified=len(tasks), aggregate=[r for r in result["aggregate"]
                         if r["split"] in {"all", "confirmation"} and r["kind"]=="ALL_TASKS"], features=len(layers)),
                     ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--masking", type=Path, default=ROOT / "data/masking")
    p.add_argument("--predictions", type=Path, default=ROOT / "runs/masked_predictions.json")
    p.add_argument("--output", type=Path, default=ROOT / "runs/masking_evaluation.json")
    p.add_argument("--visual", type=Path)
    p.add_argument("--split", choices=("development", "selection", "confirmation"))
    p.add_argument("--methods", choices=METHODS, nargs="+")
    p.add_argument("--config", type=Path, default=ROOT / "config/masking.json")
    p.add_argument("--frozen", type=Path, default=ROOT / "inputs/rev1/frozen_r4")
    args = p.parse_args()
    visual = args.visual or (ROOT / "data/masking/review_cases.geojson" if args.split is None else None)
    if args.split and args.output == ROOT / "runs/masking_evaluation.json":
        p.error("--split requires a separate --output path")
    main(args.masking.resolve(), args.predictions.resolve(), args.output.resolve(),
         None if visual is None else visual.resolve(), args.config.resolve(), args.frozen.resolve(), args.split, args.methods)
