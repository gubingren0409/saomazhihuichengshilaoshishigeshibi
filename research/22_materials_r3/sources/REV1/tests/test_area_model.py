"""Counterexamples for supported area, strict endpoint and physical geometry."""
import networkx as nx
from shapely.geometry import LineString, Point, Polygon, box

from src.area_model import AREA_EDGE, TERMINAL_EDGE, derive, gate_intersections

TAGS = {"highway": "pedestrian", "area": "yes"}
BASE = {"width_m": 3, "grid_step_m": .5, "clearance_m": .25, "tolerance_m": .001, "port_max_m": 1}
PLAZA = box(0, 0, 12, 8)
BUILDING = {"id": "way/building", "kind": "BUILDING", "geometry": box(6, 8, 12, 12)}


def port(id, xy, kind="NATIVE_CONTACT", **kwargs):
    return dict(id=id, source_node_id=id, xy=xy, kind=kind, **kwargs)


START = port("node/a", (0, 4))
DOOR = port("node/door", (9, 8), "REGISTERED_ENTRANCE", building_id="way/building")


def graph(result):
    g = nx.DiGraph()
    for e in result["edges"]:
        g.add_edge(e["u"], e["v"])
        if e["direction"] == "BIDIRECTIONAL":
            g.add_edge(e["v"], e["u"])
    return g


def run(area=PLAZA, tags=TAGS, ports=(START, DOOR), obstacles=(BUILDING,), native=()):
    return derive("relation/test", tags, area, obstacles, ports, BASE, native)


def test_polygon_without_native_internal_line_reaches_original_door():
    result = run()
    g = graph(result)
    assert nx.has_path(g, START["id"], DOOR["id"])
    assert g.out_degree(DOOR["id"]) == 0
    assert result["nodes"][DOOR["id"]] == DOOR["xy"]
    normal = [e for e in result["edges"] if e["kind"] == AREA_EDGE]
    terminal = [e for e in result["edges"] if e["native_port_id"] == DOOR["id"]]
    assert normal and terminal
    assert all(result["domain"].covers(LineString(e["coordinates_metric"])) for e in normal)
    assert all(e["kind"] == TERMINAL_EDGE and e["clearance_exception"] and e["length_m"] <= 1 for e in terminal)
    assert all(LineString(e["coordinates_metric"]).intersection(BUILDING["geometry"]).equals(Point(DOOR["xy"]))
               for e in terminal)


def test_area_flag_without_pedestrian_semantics_does_not_create_edges():
    result = run(tags={"area": "yes"})
    assert not result["edges"]
    assert result["area_status"] == "SOURCE_NOT_EXPLICIT_PEDESTRIAN_AREA"


def test_entire_lines_respect_concavity_holes_and_area_margin():
    concave = Polygon([(0, 0), (12, 0), (12, 8), (7.45, 8), (7.45, 5.5), (7.15, 5.5), (7.15, 8), (0, 8)],
                      [[(1.5, 1), (3, 1), (3, 2), (1.5, 2)]])
    water = {"id": "way/water", "kind": "AREA", "geometry": box(9, 1, 10, 2)}
    out = run(area=concave, ports=(START,), obstacles=(water,))
    assert out["edges"]
    hole = Polygon(concave.interiors[0])
    for e in out["edges"]:
        line = LineString(e["coordinates_metric"])
        assert concave.covers(line)
        assert line.distance(hole) >= .25 - 1e-6
        assert line.distance(water["geometry"]) >= .25 - 1e-6
    assert out["rejected"]["SEGMENT_NOT_COVERED_BY_EDGE_DOMAIN"] > 0


def test_fence_gate_is_point_local_and_respects_registered_permission():
    fence = {"id": "way/fence", "kind": "BARRIER", "geometry": LineString([(4, -1), (4, 9)])}
    blocked = run(obstacles=(BUILDING, fence))
    assert DOOR["id"] not in graph(blocked)
    gate = dict(fence, gates=[{"id": "node/gate", "xy": (4, .75), "allowed": True}])
    permitted = run(obstacles=(BUILDING, gate))
    assert nx.has_path(graph(permitted), START["id"], DOOR["id"])
    through = [e for e in permitted["edges"] if LineString(e["coordinates_metric"]).intersects(fence["geometry"])]
    assert through and all(e["gate_ids"] == ["node/gate"] for e in through)
    assert gate_intersections(LineString([(4, .5), (4, 1)]), gate, .001) is None


def test_layer_and_missing_native_membership_stop_topological_attachment():
    raised = port("node/raised", (0, 4), layer="1")
    floating = port("node/floating", (0, 4), native_membership=False)
    result = run(ports=(raised, floating, DOOR))
    assert result["area_status"] == "NO_ELIGIBLE_NATIVE_NETWORK_PORT"
    assert not result["edges"]
    assert result["port_results"][raised["id"]]["reason"] == "UNSUPPORTED_NATIVE_PORT_IDENTITY_OR_LAYER"
    assert result["port_results"][floating["id"]]["reason"] == "NO_NATIVE_SHARED_OUTER_BOUNDARY"
    assert not run(tags=dict(TAGS, layer="-1"))["edges"]


def test_exterior_gap_and_exit_role_preserved():
    exit_port = port("node/exit", (9, 16), "REGISTERED_ENTRANCE", building_id="way/north",
                     role="exit", inbound_eligibility="INELIGIBLE_EXIT")
    north = {"id": "way/north", "kind": "BUILDING", "geometry": box(6, 16, 12, 20)}
    result = run(ports=(START, exit_port), obstacles=(north,))
    assert result["edges"]
    assert exit_port["id"] not in result["nodes"]
    record = result["port_results"][exit_port["id"]]
    assert record["source_outer_distance_m"] == 8.0
    assert record["role"] == "exit"
    assert record["inbound_eligibility"] == "INELIGIBLE_EXIT"


def test_unknown_obstacle_region_and_multipart_do_not_gain_links():
    merged = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]).union(box(20, 0, 30, 8))
    unknown = {"id": "relation/unknown", "kind": "UNKNOWN", "geometry": box(3.8, -.5, 4.1, 8.5)}
    result = run(area=merged, obstacles=(BUILDING, unknown))
    assert result["edges"]
    assert all(x < 4 for x, _ in result["nodes"].values())
    assert DOOR["id"] not in result["nodes"]
    assert result["retained_components"] == 1


def test_native_duplicate_is_logged_and_grid_edge_does_not_snap_to_existing_way():
    native = [("way/already", LineString([(0, 1), (12, 1)]))]
    result = run(native=native)
    assert result["deduplicated"] > 0
    assert result["rejected"]["NATIVE_GEOMETRY_DUPLICATE"] > 0
    assert all(not native[0][1].covers(LineString(e["coordinates_metric"])) for e in result["edges"])
