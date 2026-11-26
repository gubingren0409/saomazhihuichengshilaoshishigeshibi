"""Independent raw-source endpoint provenance checks; no APP solver calls."""
from copy import deepcopy
from pathlib import Path
import json
import sys

import networkx as nx
from shapely.geometry import Point, box, shape

from independent_connectivity_source import ROOT, RawGeometry, digest, read, write
from independent_connectivity_fixtures import face, contract
sys.path.insert(0, str(ROOT))
from src.mechanism import boundary_binding_endpoint, _bind_endpoint
from src.common_constraints import parsed_contract


class IndependentRawReference:
    def __init__(self, raw):
        self.raw = RawGeometry(raw)
        self.projected = self.raw.xy

    def outline(self, ident):
        kind, number = ident.split("/")
        obj = self.raw.objects[(kind, int(number))]
        if kind == "way":
            return set(obj["nodes"])
        return {n for m in obj["members"] if m["type"] == "way" and (m.get("role") or "outer") == "outer" for n in self.raw.way(m["ref"])["nodes"]}


def deserialize(f):
    return {**f, "source_geometry": shape(f["source_geometry"]), "omega": shape(f["omega"]),
            "components": [{**c, "geometry": shape(c["geometry"])} for c in f["components"]],
            "barriers": [{**b, "geometry": shape(b["geometry"])} for b in f.get("barriers", [])]}


def corner_graph(faces):
    graph = nx.DiGraph()
    for f in faces:
        for ci, component in enumerate(f["components"]):
            p = component["geometry"]
            points = list(p.exterior.coords) + [xy for r in p.interiors for xy in r.coords]
            for i, xy in enumerate(points):
                graph.add_node(f"fullface/{f['source_id']}/component/{ci}/independent-corner/{i}", xy=tuple(xy), tags={})
    return graph


def main():
    lock_path = ROOT / "data/connectivity/mechanism_request_endpoints_lock.json"
    lock_before = digest(lock_path)
    query = next(q for q in read(lock_path)["queries"] if q["mechanism_id"] == "M04")
    manifest = next(s for s in read(ROOT / "data/scene_manifest.json")["scenes"] if s["scene_id"] == query["scene_id"])
    reference = IndependentRawReference(read(ROOT / manifest["source_path"]))
    admitted = next(s["admitted_ids"] for s in read(ROOT / "audits/independent_source_inventory_summary.json")["scenes"] if s["scene_id"] == query["scene_id"])
    faces = [deserialize(f) for f in read(ROOT / "data/connectivity" / (query["scene_id"] + "_faces.json")) if f["source_id"] in {query["a_source_id"], query["b_source_id"]}]
    resolved, source_checks = [], []
    for key, side in [("start", "a_source_id"), ("end", "b_source_id")]:
        original = deepcopy(query[key])
        ident = int(original["native_id"].split("/")[1])
        exact = tuple(original["xy"]) == tuple(reference.projected[ident])
        membership = ident in reference.outline(query[side])
        result = boundary_binding_endpoint(original, query[side], reference, set(admitted))
        unchanged = all(result[k] == v for k, v in original.items()) and original == query[key]
        own = next(f for f in faces if f["source_id"] == query[side])
        source_checks.append({"endpoint": key, "id": original["id"], "side_source_id": query[side], "exact_raw_coordinate_values": exact,
                              "raw_outer_node_membership": membership, "independently_checked_omega_covers": own["omega"].covers(Point(original["xy"])),
                              "original_fields_unchanged": unchanged, "resolved_area": result.get("source_area_id")})
        assert exact and membership and unchanged and result.get("source_area_id") == query[side]
        resolved.append(result)
    c = parsed_contract(read(ROOT / "data/connectivity" / (query["scene_id"] + "_full_common.json")))
    mode_rows = []
    for mode in ("FROZEN_FULL_FACE", "SOURCE_COMPLETE", "EXACT_STITCH", "CONDITIONAL_SEAMS"):
        active = [] if mode == "FROZEN_FULL_FACE" else deepcopy(faces)
        graph = corner_graph(active)
        prepared = {"faces": active, "connectivity_mode": mode, "full_parsed": c, "face_evidence": {}, "connectivity_evidence": {}}
        bindings = [_bind_endpoint(e, prepared, graph) for e in resolved]
        expected = mode != "FROZEN_FULL_FACE"
        assert all(r["bound"] == expected for r in bindings)
        mode_rows.append({"mode": mode, "bindings": bindings, "expected_bound": expected,
                          "scope": "Raw corner-node visibility attachment only, not full-network route solve"})
    raw_end = query["end"]
    wrong_side = boundary_binding_endpoint(raw_end, query["a_source_id"], reference, set(admitted))
    inactive = boundary_binding_endpoint(raw_end, query["b_source_id"], reference, set())
    aliased = {**raw_end, "layer_aware_native_graph_id": raw_end["id"] + "@layer=1@level=0"}
    no_downgrade = boundary_binding_endpoint(aliased, query["b_source_id"], reference, set(admitted))
    assert "source_area_id" not in wrong_side and "source_area_id" not in inactive and "source_area_id" not in no_downgrade
    # A side-specific boundary endpoint at a point-only junction must not add
    # visibility attachments to the other component's corner identities.
    fs = [face("left", [box(0, 0, 3, 3)]), face("right", [box(3, 3, 6, 6)])]
    g = corner_graph(fs)
    p = {"faces": fs, "connectivity_mode": "EXACT_STITCH", "full_parsed": parsed_contract(contract()), "face_evidence": {}, "connectivity_evidence": {}}
    endpoints = [{"id": "query/left-corner", "xy": [3., 3.], "source_area_id": "left", "source_node_tags": {}},
                 {"id": "query/right", "xy": [6., 5.], "source_area_id": "right", "source_node_tags": {}}]
    bindings = [_bind_endpoint(e, p, g) for e in endpoints]
    assert all(r["bound"] for r in bindings) and not nx.has_path(g, endpoints[0]["id"], endpoints[1]["id"])
    assert all(not str(n).startswith("fullface/right/") for n in bindings[0]["attached_node_ids"])
    result = {"reviewer": "/root/connectivity_review", "APP_solver_calls": 0, "external_requests": 0,
              "mechanism_source_sha256": digest(ROOT / "src/mechanism.py"), "fixture_script_sha256": digest(Path(__file__)),
              "endpoint_lock_sha256": lock_before, "endpoint_lock_unchanged": digest(lock_path) == lock_before,
              "raw_M04_endpoint_checks": source_checks, "mode_visibility_binding_checks": mode_rows,
              "unrelated_side_rejected": "source_area_id" not in wrong_side, "inactive_admission_rejected": "source_area_id" not in inactive,
              "layer_alias_not_downgraded": no_downgrade == aliased, "point_only_query_boundary_alias_bridge": False,
              "status": "PASS_FOR_REPORTED_RAW_ENDPOINT_AND_VISIBILITY_ATTACHMENT_SCOPE",
              "limits": ["No APP solver or real full-network shortest-path query", "M04 end basis B_LINE is historical template wording; actual raw source is a B-face outer node", "Query endpoints are local network references, never generated entrances"]}
    write(ROOT / "audits/independent_mechanism_binding.json", result)
    print(json.dumps({k: result[k] for k in ("status", "mechanism_source_sha256", "endpoint_lock_sha256", "endpoint_lock_unchanged")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
