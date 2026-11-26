import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_route import length_m, route_osm


def osm(nodes, ways):
    return {"elements": [
        *({"type": "node", "id": k, "lon": x, "lat": y, "tags": t} for k, x, y, t in nodes),
        *({"type": "way", "id": k, "nodes": refs, "tags": t} for k, refs, t in ways),
    ]}


def test_independent_edge_snap_crops_route_without_off_network_connector():
    data = osm([(1, 0, 0, {}), (2, .001, 0, {})], [(20, [1, 2], {"highway": "footway"})])
    result = route_osm(data, [.0002, .00005], [.0007, -.00004])
    assert result["status"] == "PASS"
    assert result["route_start"] == pytest.approx([.0002, 0], abs=1e-9)
    assert result["route_end"] == pytest.approx([.0007, 0], abs=1e-9)
    assert result["snap_start_m"] == pytest.approx(5.529, abs=.01)
    assert result["snap_end_m"] == pytest.approx(4.423, abs=.01)
    assert result["length_m"] == pytest.approx(55.66, abs=.01)
    assert result["length_m"] == length_m(result["geometry"]["coordinates"])
    assert result["segments"][0]["osm_source_node_ids"] == [1, 2]
    assert result["way_ids"] == [20]


def test_fixed_snap_limit_retains_projection_and_does_not_create_route():
    data = osm([(1, 0, 0, {}), (2, .001, 0, {})], [(20, [1, 2], {"highway": "footway"})])
    result = route_osm(data, [.0002, 0], [.0005, .0005])
    assert result["status"] == "NO_ROUTE"
    assert result["failure_reason"] == "TARGET_SNAP_OUTSIDE_LIMIT"
    assert result["geometry"] is None and result["route_end"] is None
    assert result["snap_end"]["distance_m"] > 35
    assert result["snap_end"]["position"] == pytest.approx([.0005, 0], abs=1e-9)


def test_foot_direction_respected_but_vehicle_oneway_not_applied_to_residential():
    nodes = [(1, 0, 0, {}), (2, .001, 0, {})]
    footway = osm(nodes, [(20, [1, 2], {"highway": "footway", "oneway:foot": "yes"})])
    a, b = [.0002, 0], [.0007, 0]
    assert route_osm(footway, a, b)["status"] == "PASS"
    assert route_osm(footway, b, a)["failure_reason"] == "NO_DIRECTED_PATH_BETWEEN_NEAREST_SNAPS"
    road = osm(nodes, [(20, [1, 2], {"highway": "residential", "oneway": "yes"})])
    backward = route_osm(road, b, a)
    assert backward["status"] == "PASS"
    assert backward["segments"][0]["evidence"] == "SHARED_STREET_ASSUMPTION"


@pytest.mark.parametrize("tags", [
    {"highway": "footway", "foot": "private"},
    {"highway": "footway", "foot:conditional": "no @ (21:00-05:00)"},
    {"highway": "primary", "sidewalk": "separate"},
    {"highway": "pedestrian", "area": "yes"},
    {"highway": "corridor", "indoor": "yes", "foot": "yes"},
])
def test_unknown_restricted_or_non_linear_walkways_are_not_routed(tags):
    data = osm([(1, 0, 0, {}), (2, .001, 0, {})], [(20, [1, 2], tags)])
    result = route_osm(data, [0, 0], [.001, 0])
    assert result["failure_reason"] == "NO_ELIGIBLE_EDGES"


def test_gate_without_foot_permission_and_missing_node_do_not_bridge_network():
    nodes = [(1, 0, 0, {}), (2, .001, 0, {}), (3, .002, 0, {"barrier": "gate"}),
             (4, .003, 0, {}), (5, .004, 0, {})]
    result = route_osm(osm(nodes, [(20, [1, 2, 3, 4, 5], {"highway": "footway"})]), [0, 0], [.004, 0])
    assert result["failure_reason"] == "NO_DIRECTED_PATH_BETWEEN_NEAREST_SNAPS"
    assert result["graph_stats"]["blocked_node_segments"] == 2
    result = route_osm(osm(nodes, [(20, [1, 2, 8, 4, 5], {"highway": "footway"})]), [0, 0], [.004, 0])
    assert result["failure_reason"] == "NO_DIRECTED_PATH_BETWEEN_NEAREST_SNAPS"
    assert result["graph_stats"]["missing_node_segments"] == 2


def test_grade_separated_interior_crossing_does_not_connect():
    nodes = [(1, -.001, 0, {}), (2, 0, 0, {}), (3, .001, 0, {}),
             (4, 0, -.001, {}), (5, 0, .001, {})]
    ways = [(20, [1, 2, 3], {"highway": "footway"}),
            (21, [4, 2, 5], {"highway": "footway", "bridge": "yes", "layer": "1"})]
    result = route_osm(osm(nodes, ways), [-.001, 0], [0, .001])
    assert result["failure_reason"] == "NO_DIRECTED_PATH_BETWEEN_NEAREST_SNAPS"


def test_native_adjacent_grade_transition_is_evidenced_and_has_no_fake_length():
    nodes = [(1, -.001, 0, {}), (2, 0, 0, {}), (3, .001, 0, {})]
    ways = [(20, [1, 2], {"highway": "footway"}),
            (21, [2, 3], {"highway": "footway", "bridge": "yes", "layer": "1"})]
    result = route_osm(osm(nodes, ways), [-.001, 0], [.001, 0])
    assert result["status"] == "PASS"
    assert result["way_ids"] == [20, 21]
    assert result["node_ids"] == [1, 2, 3]
    assert result["segments"][1]["source_node_transition"] == 2
    assert result["segments"][1]["length_m"] == 0.0
    assert result["geometry"]["coordinates"] == [[-.001, 0], [0, 0], [.001, 0]]



def test_bounded_clip_does_not_traverse_retained_outer_way_refs():
    nodes = [(1, 0, 0, {}), (2, .001, 0, {}), (3, .002, 0, {}), (4, .003, 0, {})]
    data = osm(nodes, [(20, [1, 2, 3, 4], {"highway": "footway"})])
    data["bounds_wsen"] = [-.001, -.001, .0015, .001]
    result = route_osm(data, [0, 0], [.003, 0])
    assert result["failure_reason"] == "TARGET_SNAP_OUTSIDE_LIMIT"
    assert result["graph_stats"]["outside_snapshot_segments"] == 2
