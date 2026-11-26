"""Counterexamples exercise the identical evidence and topology gate."""
import networkx as nx
from shapely.geometry import LineString, Polygon, Point

from src.core import LinearEvidence, Obstacles, add_supported_edges, capability, select_entrance

A, B, C, D, E = ((n, "0", "0") for n in range(1, 6))
POINTS = {A: (0, 0), B: (5, 0), C: (10, 0), D: (5, 5), E: (6, 0)}
SPACE = ("relation/1", Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), None)


def source(a, b, index, directions=(1, -1), unsupported=None):
    p, q = POINTS[a], POINTS[b]
    pos = lambda point: (121.4 + point[0] / 100000, 31.2 + point[1] / 100000)
    return LinearEvidence("way/100", index, a, b, pos(p), pos(q), directions, {"highway": "footway"},
                          LineString([p, q]), unsupported)


def verify(lines, anchor_keys=(A, C), entrances=(), obstacles=(), spaces=(SPACE,)):
    base = nx.MultiDiGraph()
    base.add_nodes_from(anchor_keys)
    anchors = {k: Point(POINTS[k]) for k in anchor_keys}
    return add_supported_edges(base, anchors, set(entrances), spaces, lines, Obstacles(obstacles), .25, .05)


def test_area_alone_cannot_make_a_route():
    b1, b2, evidence, added_b1, added_b2 = verify([])
    assert list(b1.edges) == list(b2.edges) == evidence == added_b1 == added_b2 == []


def test_explicit_boundary_chain_and_internal_entry_path():
    b1, b2, _, added_b1, added_b2 = verify([source(A, B, 0), source(B, C, 1), source(B, D, 2)], entrances=[D])
    assert nx.has_path(b1, A, C) and D not in b1
    assert nx.has_path(b2, A, D)
    assert len(added_b1) == 2 and len(added_b2) == 1
    assert all(r["topology_check"] == "EXACT_DIRECTED_TERMINAL_CHAIN" for r in added_b1 + added_b2)


def test_obstacle_and_rejected_boundary_cannot_support_b2():
    fence = ("way/99", "FENCE_WALL", LineString([(2, -1), (2, 1)]))
    _, _, evidence, b1, b2 = verify([source(A, B, 0), source(B, D, 1)], anchor_keys=[A],
                                     entrances=[D], obstacles=[fence])
    assert b1 == b2 == []
    assert [row["reason"] for row in evidence] == ["KNOWN_OBSTACLE_CONFLICT", "NO_EVIDENCE_FOR_CONNECTION"]


def test_direction_and_native_identity_prohibit_implied_connection():
    _, _, evidence, b1, b2 = verify([source(A, B, 0, (-1,))], anchor_keys=[A], entrances=[B])
    assert b1 == b2 == []
    assert evidence[0]["topology_check"] == "NO_DIRECTED_NATIVE_TERMINAL_CHAIN"
    _, _, _, b1, _ = verify([source(A, B, 0), source(E, C, 1)])
    assert b1 == []


def test_restricted_surface_and_area_hole_are_not_walkable():
    garden = ("way/99", "RESTRICTED_SURFACE", Polygon([(2, -.2), (4, -.2), (4, .2), (2, .2)]))
    _, _, evidence, b1, _ = verify([source(A, B, 0), source(B, C, 1)], obstacles=[garden])
    assert not b1 and evidence[0]["obstacle_ids"] == ["way/99"]
    hole = ("way/1", Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                              [[(4, 2), (6, 2), (6, 4), (4, 4)]]), None)
    _, _, evidence, _, b2 = verify([source(B, D, 0)], anchor_keys=[B], entrances=[D], spaces=[hole])
    assert not evidence and not b2


def test_provider_missing_fields_and_b3_eligibility():
    assert capability({"open_space_geometry": "AVAILABLE"}) == {
        "status": "NOT_EXECUTABLE_MISSING_INPUT",
        "missing": ["native_pedestrian_geometry", "native_node_topology", "obstacle_geometry"],
    }
    long = {"target_native_id": "node/1", "status": "MAPPED_ENTRY_REACHED", "length_m": 40}
    short = {"target_native_id": "node/2", "status": "MAPPED_ENTRY_REACHED", "length_m": 20}
    conflict = {"target_native_id": "node/3", "status": "MAPPED_ENTRY_REACHED_WITH_PLANAR_CONFLICT", "length_m": 10}
    assert select_entrance([long])["selected"] is None
    assert select_entrance([long, short, conflict])["selected"] == short
