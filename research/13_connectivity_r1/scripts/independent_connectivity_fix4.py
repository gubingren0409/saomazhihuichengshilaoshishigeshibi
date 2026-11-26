"""Independent focused Fix4 graph checks; no production route solver calls."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import networkx as nx
from shapely.geometry import LineString, box
from independent_connectivity_fixtures import ROOT, face, contract, source_graph
from src.face_visibility import build_overlay


def append_edge(graph, u, v, a, b, layer="derived"):
    for ident, xy in ((u, a), (v, b)):
        if ident not in graph:
            graph.add_node(ident, xy=tuple(xy), tags={}, layer_key="0", level_key="0")
    length = LineString([a, b]).length
    graph.add_edge(u, v, cost=length, segments=[{"xy": [a, b], "layer": layer,
        "source_id": "original/grid", "length_m": length, "cost_m": length,
        "tags": {}}])


def options(graph):
    return {(u, v, json.dumps(option, sort_keys=True)) for u, v, row in graph.edges(data=True)
        for option in row.get("routing_alternatives", [row["segments"]])}


def main():
    path = ROOT / "runtime/performance_fix_candidate/src/connectivity.py"
    before_sha = sha256(path.read_bytes()).hexdigest()
    assert before_sha == "12a30f7571fee7bb6db0fedaac232a45d1ee94df9ffcb5d6d5091b5e00b58e50"
    spec = importlib.util.spec_from_file_location("independent_fix4_candidate", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    checks = []
    for channel in ("SOURCE", "LOCAL_REGION"):
        faces = [face("room", [box(0, 0, 10, 10)])]
        source = source_graph([("native/A", "native/A2", [(1, 1), (1.5, 1)])])
        local = nx.DiGraph()
        grid = source if channel == "SOURCE" else local
        grid_ids = set()
        for x in range(1, 10):
            for y in range(1, 10):
                ident = f"grid/{x}/{y}"; grid_ids.add(ident)
                grid.add_node(ident, xy=(x, y), tags={}, layer_key="0", level_key="0")
                if x > 1:
                    append_edge(grid, f"grid/{x-1}/{y}", ident, (x-1, y), (x, y))
                if y > 1:
                    append_edge(grid, f"grid/{x}/{y-1}", ident, (x, y-1), (x, y))
        original_source, original_local = deepcopy(source), deepcopy(local)
        base, proof = build_overlay(faces, source, local, contract())
        delta, evidence = module.build_connectivity_overlay(faces, source, local, contract(),
            {"seam_max_m": 2.}, "EXACT_STITCH", base, proof)
        portal_ids = {p["id"] for p in evidence["stitch_portals"]}
        assert not (grid_ids & portal_ids), grid_ids & portal_ids
        assert options(source) == options(original_source) and options(local) == options(original_local)
        # Actual crossing must still get an ordered parent split and preserve direction.
        crossing_source = source_graph([("native/A", "native/A2", [(1, 1), (1.5, 1)])])
        crossing_local = nx.DiGraph()
        crossing = crossing_source if channel == "SOURCE" else crossing_local
        append_edge(crossing, "external", "internal", (-2, 6), (5, 6), "inferred")
        frozen, frozen_proof = build_overlay(faces, crossing_source, crossing_local, contract())
        new, ev = module.build_connectivity_overlay(faces, crossing_source, crossing_local, contract(),
            {"seam_max_m": 2.}, "EXACT_STITCH", frozen, frozen_proof)
        composed = nx.compose_all([crossing_source, crossing_local, frozen, new])
        assert nx.has_path(composed, "external", "native/A")
        assert not nx.has_path(composed, "native/A", "external")
        assert any(r["channel"] == channel for r in ev["stitch_directed_splits"])
        checks.append({"case": channel + "_DENSE_INTERIOR_AND_TRUE_TRANSITION", "passed": True,
            "interior_grid_nodes": len(grid_ids), "grid_portals": len(grid_ids & portal_ids),
            "old_source_local_options_unchanged": True, "directed_actual_boundary_split_routable": True})

    for channel in ("SOURCE", "LOCAL_REGION"):
        faces = [face("SW", [box(0, 0, 3, 3)]), face("NE", [box(3, 3, 6, 6)])]
        source = source_graph([("A", "A2", [(1, 1), (1.5, 1)]), ("B", "B2", [(4, 4), (4.5, 4)])])
        local = nx.DiGraph(); target = source if channel == "SOURCE" else local
        append_edge(target, "A", "shared/grid", (1, 1), (3, 3), "inferred")
        append_edge(target, "shared/grid", "B", (3, 3), (4, 4), "inferred")
        old_source, old_local = options(source), options(local)
        base, proof = build_overlay(faces, source, local, contract())
        delta, evidence = module.build_connectivity_overlay(faces, source, local, contract(),
            {"seam_max_m": 2.}, "EXACT_STITCH", base, proof)
        assert "shared/grid" not in {p["id"] for p in evidence["stitch_portals"]}
        composed = nx.compose_all([source, local, base, delta])
        assert nx.has_path(composed, "A", "B"), "original paid hypothesis path must survive"
        without_hypothesis = nx.DiGraph()
        without_hypothesis.add_nodes_from(composed.nodes(data=True))
        for graph in (source, local, base, delta):
            for u, v, row in graph.edges(data=True):
                for option in row.get("routing_alternatives", [row["segments"]]):
                    if all(s["layer"] not in {"inferred", "assumed", "unknown"} for s in option):
                        without_hypothesis.add_edge(u, v)
        assert not nx.has_path(without_hypothesis, "A", "B")
        assert options(source) == old_source and options(local) == old_local
        checks.append({"case": channel + "_PAID_HYPOTHESIS_POINT_TOUCH", "passed": True,
            "original_hypothesis_path_retained": True, "native_derived_only_path": False,
            "shared_grid_promoted": False, "old_options_unchanged": True})
    assert before_sha == sha256(path.read_bytes()).hexdigest()
    result = {"reviewer": "/root/connectivity_review", "scope": "Four independent synthetic Fix4 cases; no production shortest paths",
        "connectivity_source_sha256": before_sha, "script_sha256": sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),
        "APP_solver_calls": 0, "external_requests": 0, "checks": checks, "status": "PASS_FOR_FOUR_FIX4_CASES"}
    (ROOT / "audits/independent_fix4_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
