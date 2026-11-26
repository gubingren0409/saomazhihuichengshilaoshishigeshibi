"""Contract construction regressions, separate from real frozen scene observations."""
import json

from shapely.geometry import shape

from src import local_batch


def point(id_, lon, lat, tags=None):
    return {"type": "node", "id": id_, "lon": lon, "lat": lat, "tags": tags or {}}


def way(id_, nodes, tags=None):
    return {"type": "way", "id": id_, "nodes": nodes, "tags": tags or {}}


def mock_snapshot(entrance):
    return {"osm3s": {"timestamp_osm_base": "2026-11-08T21:21:00Z"},
            "bounds_wsen": [121.42, 31.19, 121.45, 31.23],
            "elements": [
                point(1, 121.4334, 31.2059, {"entrance": "main"} if entrance else {}),
                point(2, 121.4339, 31.2059), point(3, 121.4339, 31.2065), point(4, 121.4334, 31.2065),
                point(5, 121.4306, 31.2063), point(6, 121.431, 31.2063),
                way(293434151, [1, 2, 3, 4, 1], {"building": "yes", "name": "Fixture footprint"}),
                way(50, [5, 6], {"highway": "footway"}),
            ]}


def test_entrance_reference_and_proxy_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr(local_batch, "ROOT", tmp_path)
    clip = tmp_path / "clip.json"
    clip.write_text("{}", encoding="utf-8")
    candidate = local_batch.CHOICES[0]
    tagged = local_batch.make_contract(candidate, mock_snapshot(True), clip)
    proxy = local_batch.make_contract(candidate, mock_snapshot(False), clip)
    assert tagged["start"] == proxy["start"]
    assert tagged["target_role"] == "OSM_TAGGED" and tagged["entry_native_id"] == "node/1"
    assert proxy["target_role"] == "PROXY_OR_UNCERTAIN" and proxy["entry_native_id"] is None
    assert tagged["views"] == proxy["views"]
    assert tagged["views"]["detail"]["width"] == 1200


def test_native_multipolygon_inner_ring_preserved():
    snapshot = mock_snapshot(False)
    snapshot["elements"].extend([
        point(11, 121.4335, 31.2060), point(12, 121.4337, 31.2060),
        point(13, 121.4337, 31.2063), point(14, 121.4335, 31.2063),
        way(51, [11, 12, 13, 14, 11]),
        {"type": "relation", "id": 88, "tags": {"building": "yes", "name": "Fixture relation"},
         "members": [{"ref": 293434151, "role": "outer"}, {"ref": 51, "role": "inner"}]},
    ])
    nodes, ways, relations = local_batch.index(snapshot)
    footprint, references, _ = local_batch.named_footprint("relation", 88, nodes, ways, relations)
    assert len(footprint.interiors) == 1
    assert references == [1, 2, 3, 4, 11, 12, 13, 14]
