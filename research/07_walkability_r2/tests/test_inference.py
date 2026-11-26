"""Synthetic mechanism checks; these are not measured map cases."""
import json
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

from src.inference import INFERRED, run_observed

CFG = json.loads((Path(__file__).resolve().parents[1] / "config/inference.json").read_text())["main"]


def node(ident, xy):
    return dict(id=ident, xy=xy, tags={})


def walk(a, b):
    return dict(id=f"{a}>{b}", u=a, v=b, kind="NATIVE_LINEAR", tags={"highway": "footway"})


def fixture(park=True, target_tags=None):
    # The door is fixed on the left building facade; there is no existing door edge.
    target = {"id": "door", "xy": (12, 0), "registered": True, "building_id": "house",
              "tags": {"entrance": "exit", **(target_tags or {})}}
    return dict(task_id="SYNTHETIC_FRONTAGE", kind="REGISTERED_DOOR_TASK", crs="EPSG:32651",
                origin="origin", target=target,
                nodes=[node("origin", (0, 0)), node("edge", (4, 0))], edges=[walk("origin", "edge")],
                context={"hard": [{"id": "house", "kind": "BUILDING", "geometry": mapping(box(12, -4, 20, 4))}],
                         "background": [],
                         "support": [{"id": "park", "kind": "PARK", "geometry": mapping(box(-1, -3, 12, 3))}]
                                    if park else []})


def test_untagged_frontage_actually_connects_with_finite_cost():
    r = run_observed(fixture(), CFG)["methods"]
    assert r["I0"]["status"] == "APPROACH_WITH_GAP"
    assert r["ABL-I"]["reached_original_target"] is False
    assert r["I2"]["route"]["length_m"] == pytest.approx(12.0)
    assert r["I2"]["route"]["cost_m"] == pytest.approx(24.0)
    assert r["I2"]["route"]["edges"][-1]["kind"] == INFERRED
    assert r["I2"]["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT"


def test_no_walkability_context_requires_explicit_ablation():
    r = run_observed(fixture(park=False), CFG)["methods"]
    assert r["I2"]["admitted_edges"] == 0
    assert {d["reason"] for d in r["I2"]["candidates"]} == {"INSUFFICIENT_WALKABILITY_CONTEXT"}
    assert r["ABL-C"]["used_inferred_edges"] == 1


def test_explicit_non_ground_target_blocks_the_outdoor_assumption():
    r = run_observed(fixture(target_tags={"level": "1"}), CFG)["methods"]["I2"]
    assert r["admitted_edges"] == 0
    assert {d["reason"] for d in r["candidates"]} == {"EXPLICIT_NON_GROUND_TARGET"}


def test_disconnected_nearest_way_is_not_used_as_an_anchor():
    task = fixture()
    task["nodes"].extend((node("near1", (9, 1)), node("near2", (10, 1))))
    task["edges"].append(walk("near1", "near2"))
    result = run_observed(task, CFG)["methods"]["I2"]
    assert result["candidate_counts"]["unreachable_source_edges"] == 1
    assert all(row["source_id"] != "near1>near2" for row in result["candidates"])
    assert result["route"]["edges"][-1]["u"] == "edge"


def test_virtual_split_preserves_native_direction():
    task = fixture()
    task["nodes"] = [node("origin", (4, -4)), node("edge", (4, 4))]
    task["context"]["support"][0]["geometry"] = mapping(box(-1, -5, 12, 5))
    r = run_observed(task, CFG)["methods"]["I1"]
    native, inferred = r["route"]["edges"]
    assert native["u"] == "origin"
    assert native["v"] == inferred["u"]
    assert native["topology"] == "EXACT_DIRECTED_EDGE_SPLIT"
    assert native["length_m"] == pytest.approx(4.0)
    assert inferred["length_m"] == pytest.approx(8.0)
    assert r["route"]["inferred_edges_used"] == ["inferred/anchor/1"]
