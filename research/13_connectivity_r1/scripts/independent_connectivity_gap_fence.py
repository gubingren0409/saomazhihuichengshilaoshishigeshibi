"""Independent gap-only barrier regression; never calls the APP solver."""
from hashlib import sha256
from copy import deepcopy
from pathlib import Path
import json
import sys
import importlib.util

import networkx as nx
from shapely.geometry import LineString, Point, box, mapping, shape

from independent_connectivity_fixtures import ROOT, face, source_graph, contract
sys.path.insert(0, str(ROOT))
from src.face_visibility import build_overlay
from src.connectivity import build_connectivity_overlay, validate_connectivity_segment


def main():
    code_path = ROOT / "src/connectivity.py"
    global build_connectivity_overlay, validate_connectivity_segment
    if len(sys.argv) == 2:
        code_path = (ROOT / sys.argv[1]).resolve()
        spec = importlib.util.spec_from_file_location("independent_gap_candidate", code_path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        build_connectivity_overlay = module.build_connectivity_overlay
        validate_connectivity_segment = module.validate_connectivity_segment
    fence = LineString([(4.5, -1), (4.5, 12)])
    fs = [face("left", [box(0, 0, 4, 10)]), face("right", [box(5, 0, 9, 10)])]
    source = source_graph([("left", "left2", [(1, 5), (2, 5)]), ("right", "right2", [(7, 5), (8, 5)])])
    rows = []
    for name, gate_y, expected in [("EXACT_NATIVE_GATE", 10., True), ("OFF_GATE_0_15M", 10.15, False), ("NO_GATE", None, False), ("MISSING_RAW_BARRIER_GEOMETRY", 10., False)]:
        gates = [] if gate_y is None else [{"id": "node/gate", "xy": [4.5, gate_y], "allowed": True}]
        mask = fence.buffer(.15)
        if gates:
            mask = mask.difference(Point(gates[0]["xy"]).buffer(.30))
        c = contract()
        c.update(blocked_geometry=mapping(mask), physical_geometry=mapping(mask), constraints=[{
            "source_id": "way/fence", "kind": "BARRIER", "geometry": mapping(mask), "source_geometry": mapping(fence),
            "gates": gates, "tags": {"barrier": "fence"}}])
        if name == "MISSING_RAW_BARRIER_GEOMETRY":
            del c["constraints"][0]["source_geometry"]
        frozen, base = build_overlay(fs, source, nx.DiGraph(), c)
        delta, evidence = build_connectivity_overlay(fs, source, nx.DiGraph(), c, {"seam_max_m": 2.}, "CONDITIONAL_SEAMS", frozen, base)
        record = next(r for r in evidence["seams"] if not r["source_ids"])
        line = shape(record["geometry"])
        hit = line.intersection(fence)
        gap_segments = [s for _, _, arc in delta.edges(data=True) for option in arc.get("routing_alternatives", [arc["segments"]]) for s in option if s.get("geometry_kind") == "CONDITIONAL_GAP_LINK" and s.get("interface_id") == record["id"]]
        replay_errors = [validate_connectivity_segment(s, fs, c, evidence) for s in gap_segments]
        # Negative replay must independently reject an incorrectly accepted
        # record, rather than merely trusting generation's rejected flag.
        forced_errors = []
        if not expected:
            forged = deepcopy(evidence)
            for r in forged["seams"]:
                if r["id"] == record["id"]:
                    r.update(accepted=True, entered_graph=True)
            forced_errors = validate_connectivity_segment({"xy": record["geometry"]["coordinates"], "length_m": line.length,
                "layer": "inferred", "geometry_kind": "CONDITIONAL_GAP_LINK", "interface_id": record["id"]}, fs, c, forged)
        rows.append({"case": name, "expected_accepted": expected, "actual_accepted": record["accepted"],
                     "passed": record["accepted"] == expected and all(not errors for errors in replay_errors) and (expected or bool(forced_errors)),
                     "record": record, "fence_crossing": mapping(hit), "gate_crossing_distance_m": hit.distance(Point(gates[0]["xy"])) if gates else None,
                     "whole_replay_errors": replay_errors, "forced_incorrectly_accepted_record_replay_errors": forced_errors})
    code_sha = sha256(code_path.read_bytes()).hexdigest()
    result = {"reviewer": "/root/connectivity_review", "scope": "Full-source barrier lying strictly inside a source-positive gap, absent from all per-face near-barrier lists",
              "APP_solver_calls": 0, "external_requests": 0, "connectivity_source_sha256": code_sha, "fixture_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "checks": rows, "status": "PASS_FOR_REPORTED_FULL_SOURCE_GAP_BARRIER_CHECKS" if all(r["passed"] for r in rows) else "FAIL_REQUIRES_REPAIR",
              "original_counterexample": "audits/independent_gap_fence_counterexample.json"}
    output = ROOT / "audits" / ("independent_gap_fence_regression_" + code_sha[:12] + ".json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "source_sha256": code_sha, "checks": [{k: r[k] for k in ("case", "expected_accepted", "actual_accepted", "passed")} for r in rows]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
