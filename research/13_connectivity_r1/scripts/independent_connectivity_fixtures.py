"""Independent synthetic expectations against the frozen connectivity API.

These are geometry/graph unit checks, not APP solver calls or real-map queries.
Fixtures and reference measurements are created here, not imported from tests.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import math
import sys

import networkx as nx
from shapely.geometry import GeometryCollection, LineString, Point, box, mapping
from shapely.ops import substring, unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.connectivity import build_connectivity_overlay
from src.face_visibility import build_overlay


def face(ident, components, P=None):
    omega = unary_union(components)
    return {"source_id": ident, "id": ident, "status": "ADMITTED", "omega": omega,
            "source_geometry": P if P is not None else omega, "tags": {"area": "yes", "highway": "pedestrian"},
            "components": [{"geometry": p} for p in components], "barriers": [], "clearance_m": .25, "geometry_hash": ident}


def contract(roads=()):
    domain = mapping(box(-20, -20, 30, 30))
    empty = mapping(GeometryCollection())
    return {"sha256": "INDEPENDENT_SYNTHETIC_EMPTY_CONSTRAINTS", "crs": "EPSG:32651", "domain": domain, "coverage_geometry": domain,
            "valid_geometry": domain, "blocked_geometry": empty, "physical_geometry": empty, "background_geometry": empty,
            "native_geometry": empty, "constraints": [], "road_centerlines": [{"source_id": "road/test", "geometry": mapping(r)} for r in roads],
            "native_road_access_points": []}


def source_graph(lines):
    graph = nx.DiGraph()
    for u, v, xy in lines:
        graph.add_node(u, xy=list(xy[0]), tags={}, layer_key="0", level_key="0", source_marker=u)
        graph.add_node(v, xy=list(xy[-1]), tags={}, layer_key="0", level_key="0", source_marker=v)
        length = LineString(xy).length
        graph.add_edge(u, v, cost=length, segments=[{"source_id": "way/" + u + ">" + v, "layer": "native", "tags": {"highway": "footway"}, "xy": [list(p) for p in xy], "length_m": length, "cost_m": length}])
    return graph


def build(fs, source, *, roads=(), cap=2., mode="CONDITIONAL_SEAMS"):
    common = contract(roads)
    frozen, initial = build_overlay(fs, source, nx.DiGraph(), common)
    delta, evidence = build_connectivity_overlay(fs, source, nx.DiGraph(), common,
        {"seam_max_m": cap}, mode, frozen, initial)
    combined = nx.compose_all([source, frozen, delta])
    return combined, delta, evidence


def weighted_graph(graph, factor):
    result = nx.DiGraph()
    result.add_nodes_from(graph.nodes(data=True))
    for u, v, row in graph.edges(data=True):
        options = row.get("routing_alternatives", [row["segments"]])
        measured = [(sum(LineString(s["xy"]).length * (factor if s["layer"] in {"inferred", "assumed", "unknown"} else 1) for s in option), option) for option in options]
        value, selected = min(measured, key=lambda p: p[0])
        result.add_edge(u, v, weight=value, segments=selected)
    return result


def run():
    output = []
    def check(name, action):
        try:
            detail = action()
            output.append({"name": name, "passed": True, "detail": detail})
        except Exception as error:
            output.append({"name": name, "passed": False, "error": repr(error)})

    def attrs():
        src = source_graph([("near", "far", [(5, 1), (6, 1)])])
        src.nodes["near"].update(tags={"entrance": "exit", "foot": "yes"}, registered_source_identity="MUST_SURVIVE")
        original = deepcopy(dict(src.nodes(data=True)))
        graph, _, e = build([face("surface", [box(0, 0, 4, 3)])], src)
        assert any(r["accepted"] for r in e["seams"])
        for n, attributes in original.items():
            assert tuple(graph.nodes[n]["xy"]) == tuple(attributes["xy"])
            assert {k: v for k, v in graph.nodes[n].items() if k != "xy"} == {k: v for k, v in attributes.items() if k != "xy"}
        assert dict(src.nodes(data=True)) == original
        return {"accepted_seams": sum(r["accepted"] for r in e["seams"]), "source_metadata_equal": True,
                "xy_comparison": "Exact coordinate values; Python list/tuple container representation treated as equivalent; all other attributes exact"}
    check("NATIVE_GAP_ENDPOINT_FULL_ATTRIBUTES_PRESERVED", attrs)

    def road_partition():
        fs = [face("one-source", [box(0, 0, 5, 10), box(5, 0, 10, 10)])]
        src = source_graph([("left", "left2", [(1, 5), (2, 5)]), ("right", "right2", [(8, 5), (9, 5)])])
        graph, _, e = build(fs, src, roads=[LineString([(5, -5), (5, 15)])], mode="EXACT_STITCH")
        assert not nx.has_path(graph, "left", "right")
        assert all(not r["accepted"] and not r["entered_graph"] for r in e["face_relations"])
        assert any(r["reason"] == "ROAD_PARTITION_NO_NEW_FREE_CROSSING" for r in e["face_relations"])
        return {"domain_count": len(e["stitch_domains"]), "new_crossing": False}
    check("SAME_SOURCE_ROAD_PARTITION_REMAINS_DISCONNECTED", road_partition)

    def point_only():
        fs = [face("southwest", [box(0, 0, 3, 3)]), face("northeast", [box(3, 3, 6, 6)])]
        src = source_graph([("left", "touch", [(2, 2), (3, 3)]), ("right", "right2", [(4, 4), (5, 4)])])
        graph, _, e = build(fs, src)
        assert not nx.has_path(graph, "left", "right")
        assert not any(r["accepted"] for r in e["seams"])
        return {"one_sided_native_did_not_bridge": True}
    check("POINT_TOUCH_ONE_SIDED_NATIVE_NO_ALIAS_OR_GAP_BYPASS", point_only)

    def curved():
        xy = [(-2, 2), (3, 2), (3, 8), (12, 8)]
        parent = LineString(xy)
        src = source_graph([("before", "after", xy)])
        graph, delta, e = build([face("surface", [box(0, 0, 10, 10)])], src, mode="EXACT_STITCH")
        assert nx.has_path(graph, "before", "after") and not nx.has_path(graph, "after", "before")
        assert e["stitch_directed_splits"]
        maximum = 0.
        for _, _, row in delta.edges(data=True):
            for option in row.get("routing_alternatives", [row["segments"]]):
                for s in option:
                    if s["layer"] != "native":
                        continue
                    actual = LineString(s["xy"])
                    lo, hi = parent.project(Point(s["xy"][0])), parent.project(Point(s["xy"][-1]))
                    assert hi >= lo
                    expected = substring(parent, lo, hi)
                    assert len(actual.coords) == len(expected.coords), "original bend missing"
                    shift = max(math.dist(a, b) for a, b in zip(actual.coords, expected.coords))
                    maximum = max(maximum, shift)
                    assert shift <= 1e-8 and abs(actual.length - expected.length) <= 1e-8
        assert all(abs(r["split_length_m"] - parent.length) <= 1e-8 for r in e["stitch_directed_splits"])
        return {"ordered_parent_substring_max_coordinate_difference_m": maximum, "parent_bends_retained": True}
    check("CURVED_PARENT_ORDER_LENGTH_DIRECTION_AND_BENDS", curved)

    def no_fill():
        fs = [face("surface", [box(0, 0, 4.5, 10), box(5.5, 0, 10, 10)], box(0, 0, 10, 10))]
        src = source_graph([("left", "left2", [(1, 5), (2, 5)]), ("right", "right2", [(8, 5), (9, 5)])])
        graph, _, e = build(fs, src)
        assert not nx.has_path(graph, "left", "right")
        assert any("NO_FILL_P_TO_OMEGA_REMOVAL" in r["reasons"] for r in e["seams"])
        return {"P_to_Omega_removed_strip_not_filled": True}
    check("CLEARANCE_REMOVAL_IS_NOT_SOURCE_GAP", no_fill)

    def cap_check():
        fs = [face("left", [box(0, 0, 2, 2)]), face("right", [box(5, 0, 7, 2)])]
        src = source_graph([("left", "left2", [(.5, 1), (1, 1)]), ("right", "right2", [(6, 1), (6.5, 1)])])
        observed = {}
        for cap in (.5, 2., 5.):
            graph, _, _ = build(fs, src, cap=cap)
            observed[str(cap)] = nx.has_path(graph, "left", "right")
        assert observed == {"0.5": False, "2.0": False, "5.0": True}
        return observed
    check("PREDECLARED_CAPS_ONLY_0_5_2_5_METRES", cap_check)

    def cost_reversal():
        fs = [face("left", [box(0, 0, 3, 1)]), face("right", [box(4, 0, 7, 1)])]
        src = source_graph([("start", "end", [(1, 1), (1, 1.25), (6, 1.25), (6, 1)])])
        graph, _, e = build(fs, src)
        lengths = {}
        for factor in (1, 2):
            weighted = weighted_graph(graph, factor)
            path = nx.shortest_path(weighted, "start", "end", weight="weight")
            segments = [s for u, v in zip(path, path[1:]) for s in weighted[u][v]["segments"]]
            lengths[str(factor)] = {"cost_m": sum(weighted[u][v]["weight"] for u, v in zip(path, path[1:])), "assumed_length_m": sum(LineString(s["xy"]).length for s in segments if s["layer"] in {"inferred", "assumed", "unknown"})}
        assert lengths["1"]["assumed_length_m"] > 0 and lengths["2"]["assumed_length_m"] == 0
        assert lengths["2"]["cost_m"] <= 5.5 + 1e-8
        return {"independently_weighted_same_graph": lengths, "accepted_seams": sum(r["accepted"] for r in e["seams"])}
    check("F0_F1_PARALLEL_NATIVE_AND_ASSUMED_CHOICES_REMAIN_DISTINCT", cost_reversal)

    result = {"reviewer": "/root/connectivity_review", "scope": "Independent synthetic graph and geometry expectations against frozen API; no full-map shortest-path proof",
              "connectivity_source_sha256": sha256((ROOT / "src/connectivity.py").read_bytes()).hexdigest(),
              "fixture_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(), "APP_solver_calls": 0, "external_requests": 0,
              "checks": output, "status": "PASS_FOR_SEVEN_REPORTED_SYNTHETIC_CHECKS" if all(r["passed"] for r in output) else "FAIL_REQUIRES_REPAIR"}
    (ROOT / "audits/independent_connectivity_fixtures.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
