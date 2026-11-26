import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from src.build_common_ir import frozen_r1
from src.common_ir import adapt_geoapify, adapt_osm, comparable_route_subset, validate

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema/common_ir.schema.json").read_text(encoding="utf-8"))
SCENE = {"scene_id": "fixture", "start": [121.0, 31.0], "target": [121.02, 31.0],
         "target_role": "OSM_TAGGED", "entry_native_id": "node/1",
         "views": {"detail": {"bounds": [121, 31, 122, 32]}}}
REF = {"scope": "FIXTURE", "path": "fixture", "sha256": "0" * 64, "bytes": 0}


def test_real_r1_bundles_obey_common_schema_and_keep_different_evidence():
    local, hosted = frozen_r1(ROOT / "inputs/r1")
    schema = Draft202012Validator(SCHEMA)
    schema.check_schema(SCHEMA)
    for branch in (local, hosted):
        validate(branch)
        schema.validate(branch)
    comparison = comparable_route_subset(local, hosted)
    assert comparison["same_request_coordinates_and_mode"] is True
    assert comparison["shared_native_graph"] == "UNKNOWN"
    assert [r["role"] for r in local["route_results"]] == ["TARGET_REQUEST", "APPROACH_DIAGNOSTIC"]
    assert local["route_results"][0]["status"] == "NO_ROUTE"
    assert local["route_results"][0]["geometry"] is None
    assert local["route_results"][0]["snap_target"]["native_edge"] == "osm:way/178719573"
    assert hosted["route_results"][0]["status"] == "LIVE_ROUTE_RETURNED"
    assert hosted["route_results"][0]["snap_target"]["status"] == "UNKNOWN"
    assert hosted["route_results"][0]["route_end"] != hosted["route_requests"][0]["target"]
    assert hosted["route_results"][0]["arrival_at_verified_entrance"] == "UNKNOWN"
    assert all(s == "UNKNOWN" for s in hosted["feature_availability"].values())
    plaza = next(f for f in local["features"]["open_spaces"] if f["id"] == "osm:relation/2385771")
    assert plaza["geometry"]["type"] == "Polygon" and len(plaza["geometry"]["coordinates"]) == 3
    assert plaza["native_fields"]["tags"]["area"] == "yes"
    assert plaza["access_state"] == "UNKNOWN"
    assert local["entrances"][0]["grade"] == "OSM_TAGGED"
    assert local["entrances"][0]["physical_validation"] == "UNKNOWN"


def test_disconnected_hosted_geometry_preserves_each_source_line():
    first = [[121.00, 31.0], [121.01, 31.0]]
    second = [[121.015, 31.0], [121.02, 31.0]]
    geom = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": line}}
        for line in (first, second)]}
    hosted = adapt_geoapify(SCENE, {"route": {"status": "OK", "route_endpoint_wgs84": second[-1]}},
                            geom, [REF])
    assert validate(hosted)["route_results"][0]["geometry"]["coordinates"] == [first, second]
    assert hosted["access_candidates"] == []
    assert hosted["access_candidates_availability"] == "UNKNOWN"


def test_native_access_restrictions_do_not_infer_physical_access():
    data = {"elements": [
        {"type": "node", "id": 1, "lon": 121, "lat": 31},
        {"type": "node", "id": 2, "lon": 121.01, "lat": 31},
        {"type": "way", "id": 9, "nodes": [1, 2], "tags": {"highway": "footway", "foot": "private"}},
        {"type": "way", "id": 10, "nodes": [1, 2], "tags": {"highway": "footway"}},
    ]}
    local = adapt_osm(SCENE, data, {}, [REF], REF)
    ways = local["features"]["pedestrian"]
    assert [w["access_state"] for w in ways] == ["TAGGED_RESTRICTED", "UNKNOWN"]
    assert ways[0]["native_fields"]["nodes"] == [1, 2]
    assert local["route_results"][0]["status"] == "NOT_RUN"
    assert local["access_candidates_availability"] == "UNKNOWN"


def test_failed_branch_and_invalid_end_identity_fail_closed():
    unavailable = adapt_geoapify(SCENE, {}, None, [REF])
    validate(unavailable)
    assert unavailable["route_results"][0]["status"] == "NOT_RUN"
    bad = copy.deepcopy(unavailable)
    result = bad["route_results"][0]
    result["geometry"] = {"type": "MultiLineString", "coordinates": [[[121, 31], [121.02, 31]]]}
    result["route_end"] = [121.03, 31]
    with pytest.raises(ValueError, match="ROUTE_END_NOT_LAST_SOURCE_VERTEX"):
        validate(bad)
