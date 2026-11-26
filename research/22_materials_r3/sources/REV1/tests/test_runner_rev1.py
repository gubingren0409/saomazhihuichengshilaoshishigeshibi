"""Run-level safeguards independent of the lattice unit tests."""
from types import SimpleNamespace

import networkx as nx
import pytest
from shapely.geometry import LineString, Polygon

from src.native_adapter import INVERSE
from src.route_measure import GAP, NATIVE, TERMINAL, closest_reachable, gap_evidence
from src.run_rev1 import ablate, execute


def native_graph():
    g = nx.MultiDiGraph()
    x, y = 353000.0, 3455500.0
    keys = [(1, "0", "0"), (2, "0", "0")]
    for k, point in zip(keys, [(x, y), (x + 20, y)]):
        g.add_node(k, coord=INVERSE(*point), xy=point)
    g.add_edge(*keys, kind=NATIVE, length_m=20.0, route_weight_m=20.0,
               osm_way_id=3, segment_index=0)
    return g, keys, (x, y)


def test_north_position_on_reachable_segment_is_not_door_snap():
    g, (origin, _), (x, y) = native_graph()
    door = INVERSE(x + 10, y + 8)
    shape = Polygon([(x-5,y-5), (x+25,y-5), (x+25,y), (x-5,y)])
    raw = SimpleNamespace(ways={3: {"tags": {"highway": "footway"}}})
    prefix, endpoint, edge = closest_reachable(g, raw, origin, door, "relation/1")
    assert prefix[-1]["route_weight_m"] == pytest.approx(10)
    assert endpoint != door and edge["osm_way_id"] == 3
    evidence = gap_evidence(raw, door, endpoint, "relation/1", [("relation/1", shape)],
                            [("way/3", LineString([(x, y), (x+20, y)]))], [])
    assert evidence["kind"] == GAP and evidence["routable"] is False
    assert evidence["unsupported_length_m"] == pytest.approx(8)


def test_delete_increment_restores_exact_native_weight_and_coordinate():
    g, (origin, end), (x, y) = native_graph()
    augmented = g.copy()
    added = "grid/1"
    augmented.add_node(added, xy=(x+25,y), coord=INVERSE(x+25,y))
    augmented.add_edge(end, added, kind=TERMINAL, route_weight_m=5.0)
    restored, evidence = ablate(augmented, g, origin)
    assert evidence["removed_directed_edges"] == 1 and evidence["same_topology_and_native_weights"]
    assert len(restored) == len(g) and g.get_edge_data(origin, end) == restored.get_edge_data(origin, end)
    assert len(augmented) == 3 and augmented.has_edge(end, added)


def test_existing_run_refuses_before_loading_other_inputs(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs/experiment.json").write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        execute(tmp_path / "missing-source", tmp_path, tmp_path / "missing-config")
    assert (tmp_path / "runs/experiment.json").read_text() == "preserve"
