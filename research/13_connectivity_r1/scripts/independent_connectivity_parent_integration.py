"""Independent planner handoff/cache ownership checks; no APP solver calls."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import json
import sys

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import planner
from independent_connectivity_source import digest, read, write


def main():
    original_root = planner.ROOT
    temp = ROOT / "audits" / ("independent_parent_integration_" + uuid4().hex[:10])
    (temp / "data/connectivity").mkdir(parents=True, exist_ok=False)
    selection = read(ROOT / "data/connectivity/source_selection_lock.json")
    write(temp / "data/connectivity/source_selection_lock.json", selection)
    scene = selection["scenes"][0]
    graph = nx.DiGraph()
    graph.add_node("source/A", xy=(0., 0.), tags={"foot": "yes"})
    graph.add_node("source/B", xy=(1., 0.), tags={})
    graph.add_edge("source/A", "source/B", segments=[{"xy": [[0., 0.], [1., 0.]], "length_m": 1., "cost_m": 1., "layer": "native", "source_id": "way/test"}], cost=1.)
    base = {"data": {"scene_id": scene["scene_id"], "source_info": {"source_sha256": scene["source_sha256"]}}, "cfg": {},
            "source": graph, "region": SimpleNamespace(internal=nx.DiGraph()), "full_common": {"sha256": "FULL-SAME"}, "full_parsed": {},
            "cache_key": "INDEPENDENT-BASE", "surface": SimpleNamespace(sha256="SURFACE-SAME"), "code_sha": "INDEPENDENT-SYNTHETIC"}
    parent_overlay = nx.DiGraph()
    parent_overlay.add_node("face-parent-portal", xy=(0., 0.), tags={})
    parent_proof = {"mode": "FULL_FACE", "faces": [{"source_id": "face/reference", "components": [{"component": 0, "portal_count": 1}]}],
                    "portals": [{"id": "face-parent-portal", "xy": [0., 0.], "source_area_id": "face/reference", "component": 0, "evidence": [{"kind": "ORIGINAL_COMPLETE_PARENT_PROOF"}]}],
                    "exact_directed_splits": [{"u": "source/A", "v": "source/B", "split_positions_m": [0., 1.]}],
                    "intersection_certificates": [{"roundoff_limit_m": 1e-8, "policy": "REGISTERED_UNCHANGED"}]}
    proof_before = deepcopy(parent_proof)
    captures = []
    def child_builder(*args, **kwargs):
        received = deepcopy(kwargs["base_evidence"])
        captures.append(received)
        return nx.DiGraph(), {**received, "mode": kwargs["mode"], "connectivity_mode": kwargs["mode"], "delta_only": True}
    planner.ROOT = temp
    try:
        with patch.object(planner, "_prepare", return_value=(base, False, 0.)), patch("src.face_geometry.compile_faces", return_value=[]), \
             patch("src.face_visibility.build_overlay", return_value=(parent_overlay, parent_proof)), patch("src.connectivity.build_connectivity_overlay", side_effect=child_builder):
            B1, _, _ = planner.prepare_connectivity(scene["scene_id"], "door/reference", "SOURCE_COMPLETE")
            B2, _, _ = planner.prepare_connectivity(scene["scene_id"], "door/reference", "EXACT_STITCH")
            assert captures
            for key in ("faces", "portals", "exact_directed_splits", "intersection_certificates"):
                assert captures[0][key] == proof_before[key] and B1["connectivity_evidence"][key] == proof_before[key]
            assert captures[0]["mode"] == "SOURCE_COMPLETE" and captures[0]["parent_mode"] == "FROZEN_FULL_FACE"
            assert parent_proof == proof_before
            assert B1["face_overlays"][0] is parent_overlay and B2["face_overlays"][0] is parent_overlay
            graph_before = deepcopy(graph)
            first_reference = B2
            planner._activate_preprocessing_group("OTHER-SCENE", "OTHER-DOOR")
            assert not planner.CONNECTIVITY_CACHE and not planner.CACHE and not planner.PREPARED_INDEX
            assert first_reference["source"] is graph and list(graph.nodes(data=True)) == list(graph_before.nodes(data=True)) and list(graph.edges(data=True)) == list(graph_before.edges(data=True))
            assert first_reference["face_overlays"][0] is parent_overlay and parent_proof == proof_before
            assertions = {"complete_parent_faces_portals_splits_certificates_preserved": True, "thin_header_did_not_replace_parent_proof": True,
                          "child_received_actual_parent_overlay_references": True, "group_eviction_releases_cache_only": True,
                          "inflight_prepared_graph_and_parent_proof_unchanged_after_eviction": True}
    finally:
        planner.ROOT = original_root
    result = {"reviewer": "/root/connectivity_review", "scope": "Independent small integration handoff and cache lifetime checks with stubbed preprocessing only; no source compiler or APP solver runs",
              "APP_solver_calls": 0, "external_requests": 0, "planner_source_sha256": digest(ROOT / "src/planner.py"),
              "request_selection_sha256": digest(ROOT / "data/connectivity/source_selection_lock.json"), "assertions": assertions,
              "owned_synthetic_artifact_directory": str(temp), "status": "PASS_FOR_REPORTED_PARENT_HANDOFF_AND_CACHE_OWNERSHIP_SCOPE",
              "limits": ["Real new preparation proof and geometry still require actual rebuilt outputs", "No concurrent real solver invoked; final live concurrency remains pending"]}
    write(ROOT / "audits/independent_parent_integration.json", result)
    print(json.dumps({"status": result["status"], "planner_source_sha256": result["planner_source_sha256"], "checks": len(assertions)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
