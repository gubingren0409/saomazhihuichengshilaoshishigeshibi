"""Check preserved reference identity and the common execution boundary on real inputs."""
from src.run_dual_paths import ROOT, diagnostics, read, target_entry


def test_common_input_receipt_has_same_gate_and_no_hosted_topology():
    receipt = read(ROOT / "runs/dual_paths.json")
    assert receipt["new_geoapify_requests"] == 0
    assert receipt["shared_auxiliary_osm_input"] is False
    assert len(receipt["scenes"]) == 6
    for row in receipt["scenes"]:
        assert row["same_frozen_task"]
        local, hosted = row["local"], row["hosted"]
        assert local["shared_core_gate"] == hosted["shared_core_gate"]
        assert hosted["shared_core_gate"]["status"] == "NOT_EXECUTABLE_MISSING_INPUT"
        assert hosted["provider_native_topology"] == "UNKNOWN"
        assert set(hosted["provider_native_features"].values()) == {"UNKNOWN"}
        assert local["shared_reference"] == hosted["shared_reference"]


def test_retained_hosted_end_is_not_promoted_to_entrance():
    bundle = read(ROOT / "data/ir/sh-huangpu-01.hosted.json")
    request, result, entry = target_entry(bundle)
    measured = diagnostics(request, result)
    assert 54.9 < measured["target_gap_m"] < 55.1
    assert entry["id"] == "osm:node/6897141353"
    assert result["snap_target"]["status"] == "UNKNOWN"
    assert measured["geometry_end"] != entry["coordinate"]
