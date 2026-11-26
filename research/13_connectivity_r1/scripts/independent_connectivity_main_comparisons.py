"""Measure every fixed main four-mode comparison; metadata is not geometry gain."""
from collections import defaultdict
from shapely.geometry import LineString
from independent_connectivity_source import ROOT, read, write, digest


def coordinates(body):
    points = []
    for segment in body["route"]["segments"]:
        for xy in segment["xy"]:
            xy = tuple(xy)
            if not points or xy != points[-1]:
                points.append(xy)
    return points


def main():
    raw = (ROOT / "results/formal_registry.jsonl").read_bytes()
    raw = raw[:raw.rfind(b"\n") + 1]
    groups = defaultdict(dict)
    for line in raw.splitlines():
        row = __import__("json").loads(line)
        if row.get("role") != "BASELINE_POSITIVE":
            continue
        key = row["request"]["request_id"]
        mode = row["request"]["connectivity_mode"]
        body = read(ROOT / row["path"])
        assert digest(ROOT / row["path"]) == row["result_sha256"]
        groups[key][mode] = (row, body)
    expected = {r["request"]["request_id"] for r in read(ROOT / "data/formal_requests_lock.json")["requests"] if r["role"] == "BASELINE_POSITIVE"}
    output = []; errors = []
    modes = ("FROZEN_FULL_FACE", "SOURCE_COMPLETE", "EXACT_STITCH", "CONDITIONAL_SEAMS")
    for ident, rows in sorted(groups.items()):
        if set(rows) != set(modes):
            errors.append({"request_id": ident, "error": "INCOMPLETE_FOUR_MODES"}); continue
        baseline_request, baseline = rows[modes[0]]
        if not baseline.get("route"):
            errors.append({"request_id": ident, "error": "MAIN_BASELINE_HAS_NO_ROUTE"}); continue
        base_xy = coordinates(baseline); base = LineString(base_xy)
        comparisons = []
        for mode in modes:
            record, body = rows[mode]
            a = {k: v for k, v in baseline_request["request"].items() if k != "connectivity_mode"}
            b = {k: v for k, v in record["request"].items() if k != "connectivity_mode"}
            if a != b:
                errors.append({"request_id": ident, "mode": mode, "error": "OTHER_ROUTING_INPUT_CHANGED"})
            route = body.get("route")
            if not route:
                errors.append({"request_id": ident, "mode": mode, "error": "MODE_HAS_NO_ROUTE"}); continue
            xy = coordinates(body); geometry = LineString(xy)
            same_ordered_xy = xy == base_xy
            same_exact_point_set = geometry.equals(base)
            source_lengths = route["source_lengths_m"]
            row = {"mode": mode, "run_id": body["run_id"], "response_sha256": record["result_sha256"],
                "length_m": route["length_m"], "cost_m": route["cost_weighted_m"],
                "geometry_length_gain_m": baseline["route"]["length_m"] - route["length_m"],
                "weighted_cost_gain_m": baseline["route"]["cost_weighted_m"] - route["cost_weighted_m"],
                "same_exact_ordered_coordinates_after_consecutive_duplicate_removal": same_ordered_xy,
                "same_exact_geometry_point_set": same_exact_point_set,
                "strict_new_geometry_outside_baseline_m": geometry.difference(base).length,
                "strict_baseline_geometry_outside_new_m": base.difference(geometry).length,
                "source_lengths_m": source_lengths, "interface_ids_used": route.get("interface_ids_used", []),
                "interpretation": "Identical ordered route; source-class/interface labels may change without a geometric gain" if same_ordered_xy else
                    "Exact same point set; inspect ordered trace before treating segmentation as a route gain" if same_exact_point_set else
                    "Strict geometry differs; a native floating-set alarm alone is not a displacement or a gain proof"}
            comparisons.append(row)
        output.append({"request_id": ident, "fixed_request_except_mode": a, "comparisons": comparisons})
    all_rows = [r for q in output for r in q["comparisons"]]
    result = {"reviewer": "/root/connectivity_review", "scope": "All fixed main four-mode route geometry, costs and classification-only changes; independent saved-response measurement, no shortest-path invocation",
        "APP_solver_calls": 0, "script_sha256": digest(__import__("pathlib").Path(__file__)),
        "complete_registry_snapshot_sha256": __import__("hashlib").sha256(raw).hexdigest(), "expected_main_requests": len(expected),
        "observed_complete_main_requests": len(output), "checked_main_responses": len(all_rows), "rows": output, "errors": errors,
        "all_modes_exact_same_ordered_route_as_B0": bool(all_rows) and all(r["same_exact_ordered_coordinates_after_consecutive_duplicate_removal"] for r in all_rows),
        "status": "PASS_FOR_ALL_THIRTY_TWO_FIXED_MAIN_COMPARISONS" if not errors and set(groups) == expected and len(all_rows) == 32 else "REQUIRES_INSPECTION",
        "limits": ["This measures model routes; no source-boundary accuracy or physical passage truth follows", "Interface source-class lengths are reported separately and are not automatically new geometric route lengths"]}
    write(ROOT / "audits/independent_main_comparisons.json", result)
    print(__import__("json").dumps({k: result[k] for k in ("status", "checked_main_responses", "all_modes_exact_same_ordered_route_as_B0")}))


if __name__ == "__main__":
    main()
