"""Small synthetic policy fixtures, separate from real route metrics."""
from shapely.geometry import LineString, box

from src.semantics import KEEP, REJECT, UNRESOLVED, segment_decision


LINE = LineString([(0, 0), (4, 0)])
WALK = {"highway": "footway"}
GRASS = {"id": "grass", "kind": "AREA", "geometry": box(1, -1, 3, 1), "tags": {"landuse": "grass"}}


def test_native_walkway_stays_on_original_grass_crossing():
    before = segment_decision(LINE, WALK, [GRASS], "S0")
    after = segment_decision(LINE, WALK, [GRASS], "S1")
    assert before["status"] == REJECT
    assert after["status"] == KEEP
    assert after["reasons"] == ["MAPPED_PATH_OVER_LANDCOVER"]
    assert after["contacts"][0]["overlap_m"] == 2
    assert list(LINE.coords) == [(0, 0), (4, 0)]


def test_grass_without_explicit_walkway_does_not_open():
    result = segment_decision(LINE, {"highway": "service"}, [GRASS], "S1")
    assert result["status"] == REJECT
    assert "NO_MAPPED_WALKWAY_OVER_GRASS" in result["reasons"]


def test_foot_restriction_and_explicit_grade_conflict():
    forbidden = segment_decision(LINE, {**WALK, "access": "yes", "foot": "no"}, [GRASS], "S1")
    conditional = segment_decision(LINE, {**WALK, "foot:conditional": "no @ (night)"}, [], "S1")
    separate = segment_decision(LINE, WALK, [], "S1", endpoint_tags=({"level": "0"}, {"level": "1"}))
    assert forbidden["status"] == REJECT
    assert conditional["status"] == UNRESOLVED
    assert separate["reasons"] == ["EXPLICIT_LEVEL_CONFLICT"]


def test_wall_needs_shared_permitted_opening():
    wall = {"id": "wall", "kind": "BARRIER", "geometry": LineString([(2, -1), (2, 1)]), "tags": {},
            "gates": [{"id": "node/12", "allowed": True, "xy": [2, 0]}]}
    to_gate = LineString([(0, 0), (2, 0)])
    without = segment_decision(to_gate, WALK, [wall], "S1", native_nodes=(11, 13))
    through_gate = segment_decision(to_gate, WALK, [wall], "S1", native_nodes=(11, 12))
    assert without["status"] == REJECT
    assert through_gate["status"] == KEEP
    assert through_gate["reasons"] == ["SHARED_MAPPED_GATE_ALLOWED"]


def test_mapped_bridge_can_cross_water_but_ordinary_footway_cannot():
    water = dict(GRASS, id="water", tags={"natural": "water"})
    blocked = segment_decision(LINE, WALK, [water], "S1")
    bridge = segment_decision(LINE, {**WALK, "bridge": "yes", "layer": "1"}, [water], "S1")
    conflict = segment_decision(LINE, {**WALK, "bridge": "yes", "layer": "-1"}, [water], "S1")
    assert blocked["status"] == conflict["status"] == REJECT
    assert bridge["status"] == KEEP
    assert bridge["reasons"] == ["MAPPED_BRIDGE_OR_TUNNEL_OVER_WATER"]


def test_native_walkway_does_not_open_building_or_flowerbed():
    building = dict(GRASS, id="building", kind="BUILDING", tags={"building": "yes"})
    flowers = dict(GRASS, id="flowerbed", tags={"leisure": "flowerbed"})
    for obj, expected in [(building, "MAPPED_BUILDING_CONFLICT"), (flowers, "MAPPED_FLOWERBED_CONFLICT")]:
        decision = segment_decision(LINE, WALK, [obj], "S1")
        assert decision["status"] == REJECT and decision["reasons"] == [expected]
