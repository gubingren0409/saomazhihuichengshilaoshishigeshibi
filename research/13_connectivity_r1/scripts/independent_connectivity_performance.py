"""Independent isolated cache equivalence and real certificate checks; no solver."""
from copy import deepcopy
from hashlib import sha256
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import importlib.util
import gzip
import json
import sys

import networkx as nx
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import unary_union

from independent_connectivity_source import ROOT, digest, read, write
from independent_connectivity_fixtures import face, contract, source_graph
sys.path.insert(0, str(ROOT))
from src.face_visibility import VisibilityRoadmap, build_overlay, _reflex_corner_map
from src.common_constraints import parsed_contract


def option_geometry(graphs):
    values = set()
    for graph in graphs:
        for u, v, row in graph.edges(data=True):
            for option in row.get("routing_alternatives", [row["segments"]]):
                if not option:
                    item = {"zero": [list(graph.nodes[u]["xy"]), list(graph.nodes[v]["xy"])]}
                else:
                    item = [{k: s.get(k) for k in ("xy", "layer", "source_id", "source_area_id", "source_area_ids", "geometry_kind", "length_m", "cost_m", "tags")} for s in option]
                values.add(json.dumps(item, sort_keys=True, separators=(",", ":")))
    return values


def independent_reflex_neighbors(poly):
    output = {}
    for hole, ring in [(False, poly.exterior), *[(True, r) for r in poly.interiors]]:
        points = [tuple(p) for p in list(ring.coords)[:-1]]
        signed = sum(Fraction(a[0]) * Fraction(b[1]) - Fraction(b[0]) * Fraction(a[1]) for a, b in zip(points, points[1:] + points[:1]))
        winding = 1 if signed > 0 else -1
        for i, b in enumerate(points):
            a, c = points[i - 1], points[(i + 1) % len(points)]
            cross = (Fraction(b[0]) - Fraction(a[0])) * (Fraction(c[1]) - Fraction(a[1])) - (Fraction(b[1]) - Fraction(a[1])) * (Fraction(c[0]) - Fraction(a[0]))
            if ((cross > 0) - (cross < 0)) * winding * (1 if hole else -1) > 0:
                output[b] = frozenset((a, c))
    return output


def main():
    candidate_path = ROOT / (sys.argv[1] if len(sys.argv) == 2 else "runtime/performance_fix_candidate/src/connectivity.py")
    frozen_sha = digest(candidate_path)
    spec = importlib.util.spec_from_file_location("independent_performance_candidate", candidate_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    c = parsed_contract(contract())
    outer = [(0, 0), (10, 0), (10, 10), (8, 10), (8, 5), (7, 5), (7, 10), (3, 10), (3, 5), (2, 5), (2, 10), (0, 10)]
    Q = Polygon(outer, holes=[[(4, 3), (6, 3), (6, 6), (4, 6)]])
    cases = [("ADDED_REFLEX_NOTCH", Q.difference(box(4.2, 9.5, 4.8, 10.1))),
             ("LOST_OLD_VISIBLE_INTERVAL", Q.difference(box(4.5, 2.8, 5.5, 6.1))),
             ("STRICT_ADDED_MICRO_STRIP", Q.union(box(3.9, 4.999999999, 6.1, 5.000000001)))]
    checks = []
    for name, R in cases:
        f = face("source/reference", [Q]); f["full_constraint_sha256"] = c["contract"]["sha256"]
        source = source_graph([("A", "A2", [(1, 1), (1.5, 1)]), ("B", "B2", [(8.5, 1), (9, 1)])])
        parent, proof = build_overlay([f], source, nx.DiGraph(), c)
        proof.update(full_common_sha256=c["contract"]["sha256"], visibility_code_sha256=module._VISIBILITY_CODE_SHA256)
        def domains(_faces, _common):
            return [{"key": "independent/" + name, "prefix": "stitch/independent/" + name, "poly": R, "faces": [f], "portals": {}}], [], [], Q.difference(R)
        with patch.object(module, "_domains", side_effect=domains):
            fast, fe = module.build_connectivity_overlay([f], source, nx.DiGraph(), c, {}, "EXACT_STITCH", parent, proof)
            with patch.object(module, "_reuse_original_corners", return_value=None):
                slow, se = module.build_connectivity_overlay([f], source, nx.DiGraph(), c, {}, "EXACT_STITCH", parent, proof)
        fg, sg = option_geometry([source, parent, fast]), option_geometry([source, parent, slow])
        assert fg == sg, name + " geometric options differ"
        checks.append({"case": name, "passed": True, "geometric_directed_option_set_size": len(fg),
                       "fast_only_options": len(fg - sg), "slow_only_options": len(sg - fg),
                       "reuse_certificates": fe.get("corner_reuse_certificates", [])})
    # An old component split into multiple new domains cannot share old corner
    # identities, even if the old graph has no incident arcs at those corners.
    f = face("one-source", [Q]); f["full_constraint_sha256"] = c["contract"]["sha256"]
    old = nx.DiGraph()
    for i, xy in enumerate(sorted(_reflex_corner_map(Q))):
        old.add_node(f"fullface/one-source/component/0/v/{i}", xy=xy, tags={})
    proof = {"faces": [{"source_id": f["source_id"], "geometry_hash": f["geometry_hash"]}],
             "full_common_sha256": c["contract"]["sha256"], "visibility_code_sha256": module._VISIBILITY_CODE_SHA256}
    parts = [Q.intersection(box(-1, -1, 5, 11)), Q.intersection(box(5, -1, 11, 11))]
    ds = [{"key": "split/" + str(i), "prefix": "stitch/split/" + str(i), "poly": p, "faces": [f], "portals": {}} for i, p in enumerate(parts)]
    for d in ds:
        model = VisibilityRoadmap(d["poly"], prefix=d["prefix"])
        assert module._reuse_original_corners(model, d, ds, c, [old], proof, __import__("collections").defaultdict(int)) is None
    checks.append({"case": "SPLIT_OLD_COMPONENT_WITH_ISOLATED_CORNERS_NO_ALIAS", "passed": True})
    # Missing/mismatched constraint or visibility-code registration disables reuse.
    R = cases[0][1]; d = {"key": "guard", "prefix": "stitch/guard", "poly": R, "faces": [f], "portals": {}}
    for key in ("full_common_sha256", "visibility_code_sha256"):
        bad = {**proof, key: "DIFFERENT"}
        assert module._reuse_original_corners(VisibilityRoadmap(R, prefix=d["prefix"]), d, [d], c, [old], bad, __import__("collections").defaultdict(int)) is None
    checks.append({"case": "CONSTRAINT_AND_VISIBILITY_HASH_MISMATCH_FAILS_CLOSED", "passed": True})
    # Independently inspect real north proof samples under the actual old/new sets.
    path = ROOT / "runtime/performance_fix_candidate/audits/north_roadmap_replay.json"
    north = read(path); assert north["candidate_source_sha256"] == frozen_sha
    certs = []
    for cert in north["corner_certificates"]:
        added = shape(cert["added_geometry"])
        sample_checks = [{"line": sample, "strict_added_disjoint": added.disjoint(LineString(sample))} for sample in cert["negative_pair_samples"]]
        assert all(r["strict_added_disjoint"] for r in sample_checks) or cert["strict_global_subset"]
        assert cert["unchanged_neighbour_corner_count"] <= cert["reused_corner_count"] and cert["full_constraint_sha256"]
        certs.append({"source_id": cert["source_id"], "component": cert["component"], "strict_global_subset": cert["strict_global_subset"],
                      "reused_corners": cert["reused_corner_count"], "unchanged_neighbors": cert["unchanged_neighbour_corner_count"],
                      "reused_positive_pairs": cert["reused_positive_pairs"], "reused_negative_pairs": cert["reused_negative_pairs"],
                      "negative_sample_remeasurements": sample_checks})
    assert not north["interval_source_validation_failures"] and north["APP_solver_calls"] == 0
    faces_path = ROOT / "data/connectivity/sh-huangpu-01_faces.json"
    independent_omega = read(ROOT / "audits/independent_omega_sh-huangpu-01.json")
    assert digest(faces_path) == independent_omega["author_faces_sha256"]
    fs = read(faces_path)
    removed = unary_union([shape(f["source_geometry"]).difference(shape(f["omega"])) for f in fs if f["status"] == "ADMITTED"])
    reconstructed = []
    parent_record = north["parent_preprocessing_record"]
    parent_graph_path = ROOT / parent_record["stored_overlay"]
    assert digest(parent_graph_path) == parent_record["stored_overlay_sha256"]
    for cert in north["corner_certificates"]:
        f = next(f for f in fs if f["source_id"] == cert["source_id"])
        Q = shape(f["components"][cert["component"]]["geometry"])
        R = unary_union([Q]).difference(removed)
        added, lost = R.difference(Q), Q.difference(R)
        for geometry, key in [(Q, "original_geometry_sha256"), (R, "new_geometry_sha256"), (added, "added_geometry_sha256"), (lost, "lost_geometry_sha256")]:
            assert sha256(geometry.wkb).hexdigest() == cert[key]
        assert Q.covers(R) == cert["strict_global_subset"]
        old_map, new_map = independent_reflex_neighbors(Q), independent_reflex_neighbors(R)
        unchanged = {p for p in old_map if p in new_map and old_map[p] == new_map[p]}
        assert len(unchanged) == cert["unchanged_neighbour_corner_count"]
        prefix = f"fullface/{cert['source_id']}/component/{cert['component']}/v/"
        ids = {p: prefix + str(i) for i, p in enumerate(sorted(old_map))}
        targets = set()
        for sample in cert["negative_pair_samples"]:
            a, b = map(tuple, sample)
            assert a in unchanged and b in unchanged and (cert["strict_global_subset"] or added.disjoint(LineString(sample)))
            targets.update([(ids[a], ids[b]), (ids[b], ids[a])])
        negative_edges_found, incident_checks, incident_errors = [], 0, []
        with gzip.open(parent_graph_path, "rt", encoding="utf-8") as stream:
            for text in stream:
                row = json.loads(text)
                if row["kind"] == "node":
                    if row["id"].startswith(prefix):
                        assert tuple(row["xy"]) == sorted(old_map)[int(row["id"][len(prefix):])]
                    continue
                if (row["u"], row["v"]) in targets:
                    negative_edges_found.append([row["u"], row["v"]])
                if not row["u"].startswith(prefix) and not row["v"].startswith(prefix):
                    continue
                for option in row.get("routing_alternatives", [row["segments"]]):
                    incident_checks += 1
                    if option:
                        line = LineString([p for s in option for p in s["xy"]])
                        if not R.covers(line):
                            incident_errors.append([row["u"], row["v"]])
        assert not negative_edges_found and not incident_errors and incident_checks == cert["incident_options_checked"]
        reconstructed.append({"source_id": cert["source_id"], "old_reflex_count": len(old_map), "new_reflex_count": len(new_map),
                              "unchanged_neighbor_count": len(unchanged), "strict_global_subset_independently_recomputed": Q.covers(R),
                              "all_four_geometry_WKB_hashes_match": True, "all_old_corner_coordinates_match_parent_graph": True,
                              "negative_samples_absent_in_parent_both_directions": True, "all_parent_corner_incident_options_strictly_covered_by_current_domain": incident_checks})
    assert digest(candidate_path) == frozen_sha
    result = {"reviewer": "/root/connectivity_review", "scope": "Independent cache-on versus full pair recomputation on three small changed domains, inverse ownership/hash guards, and real north strict-added negative certificate samples",
              "candidate_source_sha256": frozen_sha, "parent_main_source_sha256": digest(ROOT / "src/connectivity.py"), "review_script_sha256": digest(Path(__file__)),
              "APP_solver_calls": 0, "external_requests": 0, "checks": checks, "north_author_receipt_sha256": digest(path), "north_independent_certificate_samples": certs,
              "north_independent_domain_neighbor_parent_graph_reconstruction": reconstructed,
              "status": "PASS_FOR_REPORTED_ISOLATED_PERFORMANCE_CACHE_SCOPE",
              "limits": ["Real north full slow N-squared graph was not rebuilt independently", "All 1,563,624 real negative certificates were not re-enumerated; strict-set implication and samples plus small exhaustive graphs checked", "Real new integrated preparation and routes remain to be rebuilt under the new frozen backend", "Source geometry, thresholds, penalties and original point coordinates are not relaxed"]}
    write(ROOT / "audits/independent_performance_cache_review.json", result)
    print(json.dumps({"status": result["status"], "candidate_sha256": frozen_sha, "small_checks": len(checks), "north_certificates": len(certs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
