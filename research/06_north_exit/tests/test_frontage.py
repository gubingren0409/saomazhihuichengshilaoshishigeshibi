from pathlib import Path
import sys

from shapely.geometry import LineString, Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from run_experiment import EPS, REJECTED, frontage_domain, has_level_conflict, planar_obstacle_hits, visibility_route


def test_visibility_uses_direct_line_only_when_entire_line_is_inside():
    start, exit = (1, 2), (9, 2)
    domain = box(0, 0, 10, 6)
    path, nodes, edges = visibility_route(domain, start, exit, lambda line: True)
    assert path == [start, exit] and nodes >= 2 and edges > 0
    obstacle = box(4, 1, 6, 3)
    allowed = domain.difference(obstacle.buffer(.20, quad_segs=3))
    path, _, _ = visibility_route(allowed, start, exit, lambda line: not line.intersects(obstacle))
    assert path and len(path) > 2
    assert LineString(path).length > LineString([start, exit]).length
    assert allowed.buffer(EPS).covers(LineString(path))


def test_frontage_corridor_is_local_and_subtracts_mapped_fence_setback():
    park = box(-30, -40, 30, 40)
    fence = {"id": "way/1", "kind": "BARRIER", "geometry": LineString([(4, -4), (4, 4)])}
    config = {"radius_m": 12, "half_width_m": 2, "obstacle_clearance_m": .25}
    window, domain, relevant = frontage_domain((0, 0), (8, 0), park, [fence], "way/2", config)
    assert window.area < park.area
    assert domain.area < window.area and len(relevant) == 1
    route, _, _ = visibility_route(domain, (0, 0), (8, 0), lambda line: True)
    assert route is None


def test_original_exit_allows_one_terminal_point_but_rejects_entering_footprint():
    target = Point(10, 0)
    building = {"id": "way/1", "kind": "BUILDING", "geometry": box(10, -2, 12, 2)}
    clean = planar_obstacle_hits(LineString([(0, 0), (10, 0)]), [building], "way/1", target)
    assert clean[0]["status"] == "ORIGINAL_EXIT_BOUNDARY_TOUCH_ONLY"
    crossed = planar_obstacle_hits(LineString([(0, 0), (11, 0)]), [building], "way/1", target)
    assert crossed[0]["status"] == REJECTED
    wall = planar_obstacle_hits(LineString([(10, -1), (10, 0)]), [building], "way/1", target)
    assert wall[0]["status"] == REJECTED


def test_explicit_level_or_access_tags_gate_a_hypothesis():
    assert has_level_conflict({"layer": "1"})
    assert has_level_conflict({"tunnel": "yes"})
    assert has_level_conflict({"highway": "steps"})
    assert has_level_conflict({"foot": "private"})
    assert not has_level_conflict({"entrance": "exit"})
    assert not has_level_conflict({"surface": "paving_stones"})
