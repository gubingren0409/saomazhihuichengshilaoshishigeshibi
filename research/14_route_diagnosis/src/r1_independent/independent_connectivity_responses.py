"""Independent saved-response length/cost/geometry/parent provenance review.

No planner, author validation flag or APP solver is called. Exact raw source
parents and the already registered 1e-8 m contact contract adjudicate native
binary-set alarms; the original strict alarm remains in the report.
"""
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import argparse
import json
import math
import re

from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import substring, unary_union
from shapely.strtree import STRtree

from independent_connectivity_source import ROOT, RawGeometry, coverage, digest, read, write
from independent_connectivity_omega import raw_masks, denied, nonground, STRUCTURES, GATES, COMMON_GATES

NUMERIC_LIMIT = 1e-8
FROZEN_VISIBILITY_SHA = "fc3c6220f8ac8f97847f01a355deba6c29680850ad44ec1f9a139c60cac5d56c"
EPS = 1e-6


def direction_allowed(tags, direction):
    public = {"yes", "designated", "permissive", "official"}
    oneway = tags.get("oneway:foot")
    if oneway is None and tags.get("highway") in {"footway", "path", "steps"}:
        oneway = tags.get("oneway")
    if oneway not in {None, "no", "false", "0", "yes", "true", "1", "-1", "reverse"}:
        return False
    return ((direction == 1 and oneway not in {"-1", "reverse"} and tags.get("foot:forward", "yes") in public) or
            (direction == -1 and oneway not in {"yes", "true", "1"} and tags.get("foot:backward", "yes") in public))


def point_bound(point, a, b):
    q, x, y = [tuple(Fraction(v) for v in p) for p in (point, a, b)]
    d, w = (y[0] - x[0], y[1] - x[1]), (q[0] - x[0], q[1] - x[1])
    den = d[0] ** 2 + d[1] ** 2
    t = (w[0] * d[0] + w[1] * d[1]) / den
    cross = w[0] * d[1] - w[1] * d[0]
    squared = cross * cross / den
    return {"passed": 0 <= t <= 1 and squared <= Fraction(str(NUMERIC_LIMIT)) ** 2,
            "projection_fraction": str(t), "perpendicular_distance_m": math.sqrt(float(squared)), "exact_squared_cross_bound": True}


def native_proof(s, source, body, registered):
    errors = []
    obj = source.objects.get(("way", int(s["source_id"].split("/")[1])))
    if obj is None:
        return {"passed": False, "errors": ["NO_RAW_NATIVE_WAY"]}
    tags = obj.get("tags", {})
    if s.get("tags", {}) != tags:
        errors.append("RAW_NATIVE_TAGS_CHANGED")
    match = re.fullmatch(r"way/(\d+)/segment/(\d+)/(node/\d+)>(node/\d+)", s.get("edge_id", ""))
    if match is None:
        return {"passed": False, "errors": errors + ["NO_ADJACENT_RAW_PARENT_EDGE_ID"]}
    wid, index, u, v = match.groups()
    ui, vi = int(u.split("/")[1]), int(v.split("/")[1])
    ids = obj["nodes"]
    index = int(index)
    if wid != s["source_id"].split("/")[1] or index >= len(ids) - 1 or (ui, vi) not in [(ids[index], ids[index + 1]), (ids[index + 1], ids[index])]:
        errors.append("WRONG_RAW_ADJACENT_PARENT")
    direction = 1 if index < len(ids) - 1 and (ui, vi) == (ids[index], ids[index + 1]) else -1
    if not direction_allowed(tags, direction):
        errors.append("WRONG_RAW_PARENT_DIRECTION")
    parent = [list(source.xy[ui]), list(source.xy[vi])]
    line = LineString(parent)
    positions = {tuple(parent[0]): 0., tuple(parent[-1]): line.length}
    certificates = [c for field in (body.get("face_network", {}), body.get("connectivity_evidence", {})) for key in ("intersection_certificates", "stitch_intersection_certificates") for c in field.get(key, [])]
    selected = []
    for cert in certificates:
        if cert.get("channel") != "SOURCE" or (cert.get("u"), cert.get("v")) != (u, v):
            continue
        if cert.get("parent_source_ids") not in (None, [s["source_id"]]):
            continue
        if cert.get("roundoff_limit_m") != NUMERIC_LIMIT or max(math.dist(cert["raw_intersection_xy"], cert["xy"]), abs(cert["parent_position_after_m"] - cert["parent_position_before_m"])) > NUMERIC_LIMIT:
            errors.append("CONTACT_CERTIFICATE_LIMIT_OR_SHIFT")
            continue
        positions[tuple(cert["xy"])] = cert["parent_position_after_m"]
        selected.append(cert)
    for seam in body.get("connectivity_evidence", {}).get("seams", []):
        p = seam.get("parent", {})
        if (p.get("u"), p.get("v")) == (u, v) and s["source_id"] in seam.get("source_ids", []):
            positions[tuple(seam["geometry"]["coordinates"][-1])] = p["position_m"]
    actual = LineString(s["xy"])
    strict = actual.difference(line).length
    lo, hi = positions.get(tuple(s["xy"][0])), positions.get(tuple(s["xy"][-1]))
    proof = {"strict_original_difference_length_m": strict, "original_strict_alarm_preserved": strict > EPS,
             "parent_source_id": s["source_id"], "raw_adjacent_index": index, "parent_native_ids": [u, v], "parent_coordinates": parent,
             "direction": direction, "source_tags_equal": s.get("tags", {}) == tags}
    if lo is not None and hi is not None:
        if not 0 <= lo < hi <= line.length:
            errors.append("NONFORWARD_REGISTERED_PARENT_PARAMETERS")
        else:
            expected = [list(p) for p in substring(line, lo, hi).coords]
            if s["xy"] != expected:
                errors.append("NOT_IDENTICAL_ORDERED_REGISTERED_PARENT_SUBSTRING")
            bounds = [point_bound(q, *parent) for q in s["xy"]]
            if not all(b["passed"] for b in bounds):
                errors.append("OUTSIDE_REGISTERED_WHOLE_PARENT_NUMERIC_BOUND")
            if abs(actual.length - (hi - lo)) > NUMERIC_LIMIT:
                errors.append("PARENT_PARAMETER_LENGTH_MISMATCH")
            if strict > EPS and not registered:
                errors.append("NUMERICAL_POLICY_NOT_FIXED_BASELINE")
            proof.update(parameter_interval_m=[lo, hi], ordered_expected_coordinates=expected, whole_piece_endpoint_bounds=bounds,
                         whole_piece_bound_reason="Distance to finite convex parent segment is convex; both projected endpoint parameters are within [0,1]", certificate_count=len(selected))
    elif strict <= EPS and all(line.covers(Point(p)) for p in s["xy"]) and line.project(Point(s["xy"][-1])) > line.project(Point(s["xy"][0])):
        proof["exact_raw_subsegment_no_roundoff_adjudication_needed"] = True
    else:
        errors.append("NO_EXACT_OR_REGISTERED_PARENT_SUBSTRING")
    proof.update(passed=not errors, errors=errors, strict_binary_set_coincidence_claimed=strict == 0)
    return proof


def review(root, paths, output, registry_meta=None):
    catalog = {r["scene_id"]: r for r in read(root / "data/scene_manifest.json")["scenes"]}
    registered = digest(root / "src/face_visibility.py") == FROZEN_VISIBILITY_SHA
    caches, rows, grouped = {}, [], defaultdict(dict)
    for path in paths:
        body = read(path)
        if not isinstance(body, dict) or not body.get("run_id"):
            continue
        request = body.get("normalized_request", body.get("input", {}))
        if body.get("namespace") == "REAL_SOURCE_INTERFACE_MECHANISM" and body.get("query"):
            query = body["query"]
            request = {**request, "scene_id": query["scene_id"], "start_id": query["start"]["id"], "target_id": query["end"]["id"],
                       "method": body.get("method", request.get("method")), "connectivity_mode": body.get("connectivity_mode", request.get("connectivity_mode")),
                       "purpose": "LOCAL_MECHANISM_NO_DOOR_OR_ENTRANCE_ASSERTION"}
        scene = request.get("scene_id")
        route = body.get("route")
        row = {"file": str(path), "sha256": digest(path), "run_id": body["run_id"], "status": body.get("status"), "errors": []}
        if registry_meta and str(path.resolve()) in registry_meta["rows"]:
            recorded = registry_meta["rows"][str(path.resolve())]
            row["formal_attempt_id"] = recorded["attempt_id"]
            row["formal_role"] = recorded["role"]
            expected_input = {**recorded["request"], "run_purpose": registry_meta.get("expected_run_purpose", "FORMAL_PRELOCKED_MATRIX")}
            if row["sha256"] != recorded["result_sha256"] or body["run_id"] != recorded["run_id"] or body.get("input") != expected_input:
                row["errors"].append("FORMAL_REGISTRY_HASH_RUN_OR_INPUT_BINDING")
        if scene not in catalog or not route:
            row["scope"] = "REQUEST_STATUS_ONLY_NO_ROUTE_GEOMETRY_OR_IMPOSSIBILITY_PROOF"
            rows.append(row)
            continue
        if scene not in caches:
            entry = catalog[scene]
            source_path = root / entry["source_path"]
            if digest(source_path) != entry["source_sha256"]:
                raise ValueError("SOURCE_HASH_CHANGED")
            raw = read(source_path)
            source, area_masks, common = raw_masks(raw)
            ai, ci = STRtree([r["geometry"] for r in area_masks]), STRtree([r["geometry"] for r in common])
            caches[scene] = {"source": source, "area_masks": area_masks, "common": common, "area_index": ai, "common_index": ci, "omega": {}, "P": {}}
        cache = caches[scene]
        source = cache["source"]
        def omega(ident):
            if ident not in cache["omega"]:
                kind, number = ident.split("/")
                P, _, error = source.area(source.objects[(kind, int(number))])
                if P is None:
                    raise ValueError("SOURCE_FACE_UNRESOLVED:" + ident + ":" + str(error))
                masks = [cache["area_masks"][int(i)]["geometry"] for i in cache["area_index"].query(P, predicate="intersects")]
                holes = [Polygon(r).buffer(.25, quad_segs=16) for part in ([P] if P.geom_type == "Polygon" else P.geoms) for r in part.interiors]
                cmasks = [cache["common"][int(i)]["geometry"] for i in cache["common_index"].query(P, predicate="intersects")]
                cache["P"][ident] = P
                cache["omega"][ident] = P.difference(unary_union(masks + holes)).difference(unary_union(cmasks)).intersection(coverage(catalog[scene]["full_source_clip_bounds"]))
            return cache["omega"][ident]
        factor = 2 if request.get("method") == "F1" else 1
        layers, categories = defaultdict(float), defaultdict(float)
        proofs, geometry_errors = [], []
        length, cost, previous, first = 0., 0., None, None
        for index, s in enumerate(route["segments"]):
            line = LineString(s["xy"])
            measured = line.length
            layer, kind = s.get("layer"), s.get("geometry_kind")
            if first is None:
                first = s["xy"][0]
            if previous is not None and math.dist(previous, s["xy"][0]) > EPS:
                row["errors"].append("ROUTE_DISCONTINUITY:" + str(index))
            previous = s["xy"][-1]
            value = measured * (factor if layer in {"inferred", "assumed", "unknown"} else 1)
            length += measured; cost += value; layers[layer] += measured
            if abs(measured - s["length_m"]) > EPS or abs(value - s["cost_m"]) > EPS:
                row["errors"].append("SEGMENT_GEOMETRY_LENGTH_OR_COST:" + str(index))
            category = "conditional_seam" if kind in {"CONDITIONAL_GAP_LINK", "CONDITIONAL_GAP_PATCH"} else "exact_interface_derived" if kind == "SOURCE_SUPPORTED_INTERFACE" else "native" if layer == "native" else "full_face_derived" if kind == "DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE" else "local_mapped_grid_derived" if str(s.get("source_id", "")).startswith("cell/") and layer == "derived" else "edge_band_derived" if layer == "derived" else "assumed"
            categories[category] += measured
            if s.get("source_class", category) != category:
                row["errors"].append("SOURCE_CATEGORY_MISMATCH:" + str(index))
            if layer == "native" and str(s.get("source_id", "")).startswith("way/"):
                p = native_proof(s, source, body, registered)
                proofs.append({"segment_index": index, **p})
                if not p["passed"]:
                    row["errors"].append("NATIVE_PARENT_PROOF:" + str(index))
            if kind in {"DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE", "SOURCE_SUPPORTED_INTERFACE"}:
                owners = s.get("source_area_ids", [s.get("source_area_id", s.get("source_id"))])
                if layer != "derived" or not any(omega(owner).covers(line) for owner in owners):
                    geometry_errors.append({"segment_index": index, "reason": "NO_INDEPENDENT_OMEGA_COVERS_WHOLE_DERIVED_SEGMENT", "owners": owners})
            if kind in {"CONDITIONAL_GAP_LINK", "CONDITIONAL_GAP_PATCH"}:
                evidence = body.get("connectivity_evidence", {})
                record = next((r for r in evidence.get("seams", []) if r["id"] == s.get("interface_id")), None)
                if layer != "inferred" or record is None or not record.get("accepted") or not record.get("entered_graph") or measured > float(request.get("seam_max_m") or 2.) + NUMERIC_LIMIT:
                    geometry_errors.append({"segment_index": index, "reason": "CONDITIONAL_SEAM_ID_LAYER_CAP_OR_GRAPH_RECORD"})
                active = [f["source_id"] for f in body.get("mapped_faces", []) if f.get("status") == "ADMITTED"]
                if not active and body.get("namespace") == "REAL_SOURCE_INTERFACE_MECHANISM":
                    if request.get("connectivity_mode") == "FROZEN_FULL_FACE":
                        active = next(s["area_ids"] for s in read(root / "data/face_selection_lock.json")["scenes"] if s["scene_id"] == scene)
                    else:
                        active = next(s["admitted_ids"] for s in read(root / "audits/independent_source_inventory_summary.json")["scenes"] if s["scene_id"] == scene)
                legal = unary_union([omega(ident) for ident in active])
                removed = unary_union([cache["P"][ident].difference(omega(ident)) for ident in active])
                if line.intersection(removed).difference(legal).length > 0:
                    geometry_errors.append({"segment_index": index, "reason": "SEAM_RESTORES_P_TO_OMEGA_REMOVAL"})
        if abs(length - route["length_m"]) > EPS or abs(cost - route["cost_weighted_m"]) > EPS:
            row["errors"].append("TOTAL_ROUTE_GEOMETRY_LENGTH_OR_COST")
        for category, measured in categories.items():
            if abs(measured - route.get("source_lengths_m", {}).get(category, measured)) > EPS:
                row["errors"].append("SOURCE_LENGTH_CATEGORY:" + category)
        for field, measured in [("native_m", layers.get("native", 0.)), ("mapped_derived_m", layers.get("derived", 0.)),
                                ("conditional_seam_m", categories.get("conditional_seam", 0.)), ("all_hypothesis_m", sum(layers.get(k, 0.) for k in ("inferred", "assumed", "unknown")))]:
            if field in route and abs(route[field] - measured) > EPS:
                row["errors"].append("MECHANISM_LENGTH_CATEGORY:" + field)
        actual_interface_ids = sorted({s["interface_id"] for s in route["segments"] if s.get("interface_id")})
        if route.get("interface_ids_used", actual_interface_ids) != actual_interface_ids:
            row["errors"].append("ROUTE_INTERFACE_USE_IDS")
        endpoint_details = {}
        for name, ident, actual in [("start", request.get("start_id"), first), ("target", request.get("door_id", request.get("target_id")), previous)]:
            match = re.match(r"node/(\d+)", str(ident))
            if match:
                expected = source.xy[int(match.group(1))]
                if actual is None and route.get("zero_length"):
                    actual = expected
                error = math.dist(expected, actual) if actual is not None else None
                endpoint_details[name] = {"id": ident, "raw_source_xy": list(expected), "error_m": error}
                if error is None or error > EPS:
                    row["errors"].append("RAW_SOURCE_ENDPOINT_MOVED:" + name)
        if body.get("door") and body["door"].get("id", "").startswith("node/"):
            number = int(body["door"]["id"].split("/")[1])
            if body["door"].get("tags", {}) != source.objects[("node", number)].get("tags", {}):
                row["errors"].append("REGISTERED_DOOR_TAGS_OR_EXIT_IDENTITY_CHANGED")
        if not body.get("solver", {}).get("invoked") or body.get("route_answer_cache") != {"enabled": False, "hit": False}:
            row["errors"].append("NOT_REAL_UNCACHED_SOLVER_RESPONSE")
        if body.get("user_observation", "PENDING_USER_OBSERVATION") != "PENDING_USER_OBSERVATION":
            row["errors"].append("USER_OBSERVATION_NOT_PENDING")
        if geometry_errors:
            row["errors"].append("WHOLE_DERIVED_OR_SEAM_GEOMETRY")
        row.update(measured_length_m=length, measured_cost_m=cost, measured_layers_m=dict(layers), measured_source_lengths_m=dict(categories),
                   source_endpoint_measurements=endpoint_details, native_parent_proofs=proofs, whole_geometry_errors=geometry_errors,
                   graph_sha256=body.get("graph", {}).get("unweighted_sha256", body.get("versions", {}).get("unweighted_graph_sha256")), solver_invocation_id=body.get("solver", {}).get("invocation_id"))
        identity = (scene, request.get("start_id"), request.get("door_id", request.get("target_id")), request.get("purpose"), request.get("connectivity_mode"), request.get("seam_max_m"))
        grouped[identity][request.get("method")] = row
        rows.append(row)
    pairs = []
    for identity, methods in grouped.items():
        if "F0" in methods and "F1" in methods:
            x, y = methods["F0"], methods["F1"]
            pairs.append({"identity": identity, "same_unweighted_graph": x["graph_sha256"] == y["graph_sha256"], "distinct_run_ids": x["run_id"] != y["run_id"], "distinct_solver_invocations": x["solver_invocation_id"] != y["solver_invocation_id"]})
    result = {"reviewer": "/root/connectivity_review", "scope": "Saved-response independent geometry/length/cost/native parent provenance and paired graph identities; no independent whole-network shortest-path solve",
              "review_script_sha256": digest(Path(__file__)),
              "APP_solver_calls": 0, "external_requests": 0, "numeric_policy_registered": registered, "frozen_visibility_sha256": FROZEN_VISIBILITY_SHA,
              "native_numeric_limit_m": NUMERIC_LIMIT, "rows": rows, "F0_F1_pairs": pairs,
              "status": "PASS_FOR_REPORTED_RESPONSE_SCOPE" if all(not r["errors"] for r in rows) and all(all(r[k] for k in ("same_unweighted_graph", "distinct_run_ids", "distinct_solver_invocations")) for r in pairs) else "REQUIRES_INSPECTION",
              "limitations": ["No-route and refusal status is not independently proved impossible", "Conditional links checked for source geometry roles/cap/no-fill; full-source barrier regression is separate", "No field or user observation acceptance", "Original strict binary native-set alarms retained and may be resolved only by registered ordered-parent proof"]}
    if registry_meta:
        result["formal_registry_snapshot"] = {k: v for k, v in registry_meta.items() if k != "rows"}
        result["formal_input_envelope"] = "Frozen request plus run_purpose=" + registry_meta.get("expected_run_purpose", "FORMAL_PRELOCKED_MATRIX") + ", explicitly declared by the audit caller and assigned by run_formal.py or run_performance_replays.py. No other input difference allowed. Initial reviewer envelope-only alarm retained separately."
    write(output, result)
    print(json.dumps({"status": result["status"], "responses": len(rows), "rows_with_errors": sum(bool(r["errors"]) for r in rows), "F0_F1_pairs": len(pairs)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--registry", type=Path)
    ap.add_argument("--since-index", type=int, default=0)
    ap.add_argument("--registry-run-purpose", choices=("FORMAL_PRELOCKED_MATRIX", "FORMAL_PERFORMANCE_FIX_REPLAY"), default="FORMAL_PRELOCKED_MATRIX")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--output", type=Path, default=ROOT / "audits/independent_response_review.json")
    a = ap.parse_args()
    paths = [p for item in a.paths for p in (sorted(item.glob("*.json")) if item.is_dir() else [item])]
    registry_meta = None
    if a.registry:
        registry_bytes = a.registry.read_bytes()
        complete = registry_bytes[:registry_bytes.rfind(b"\n") + 1]
        entries = [json.loads(line) for line in complete.splitlines() if line.strip()]
        selected = entries[a.since_index:]
        paths.extend(a.root.resolve() / r["path"] for r in selected)
        registry_meta = {"file": str(a.registry.resolve()), "completed_snapshot_sha256": sha256(complete).hexdigest(), "completed_entries_at_read": len(entries),
                         "selected_from_index": a.since_index, "selected_entry_count": len(selected), "expected_run_purpose": a.registry_run_purpose, "rows": {str((a.root.resolve() / r["path"]).resolve()): r for r in selected}}
    review(a.root.resolve(), paths, a.output, registry_meta)
