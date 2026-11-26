"""Audit saved r2 parent evidence and strict-domain reuse certificates; no solver."""
import argparse
from hashlib import sha256
from pathlib import Path
import json
from shapely.geometry import LineString, shape
from independent_connectivity_source import ROOT, digest, read, write
from independent_connectivity_responses import FROZEN_VISIBILITY_SHA


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, default=ROOT / "audits/backend_freeze_r2.json")
    parser.add_argument("--output", type=Path, default=ROOT / "audits/independent_preparations_r2.json")
    args = parser.parse_args()
    code_sha = read(args.freeze)["code_sha256"]
    logs, preparation_records = {}, []
    for path in sorted((ROOT / "runs/preprocessing").glob("*.json")):
        data = read(path)
        if data.get("code_sha256") == code_sha and data.get("cache_key"):
            logs[data["cache_key"]] = (path, data)
            preparation_records.append((data["cache_key"], path, data))
    manifest = read(ROOT / "data/scene_manifest.json")["scenes"]
    scenes_by_sha = {r["source_sha256"]: r for r in manifest}

    def scene(key):
        visited = set()
        while key in logs and key not in visited:
            visited.add(key); row = logs[key][1]
            source_sha = row.get("source", {}).get("source_sha256")
            if source_sha in scenes_by_sha:
                return scenes_by_sha[source_sha]
            key = row.get("parent_cache_key", row.get("base_cache_key"))
        raise ValueError("NO_CURRENT_CODE_SOURCE_PARENT_CHAIN")

    source_refs = {}
    def reference(entry):
        sid = entry["scene_id"]
        if sid not in source_refs:
            faces_path = ROOT / "data/connectivity" / (sid + "_faces.json")
            common_path = ROOT / "data/connectivity" / (sid + "_full_common.json")
            proof = read(ROOT / "audits" / ("independent_omega_" + sid + ".json"))
            assert proof["status"] == "GEOMETRY_MATCH_FOR_REPORTED_SCOPE"
            assert digest(faces_path) == proof["author_faces_sha256"] and digest(common_path) == proof["author_full_common_sha256"]
            source_refs[sid] = ({f["source_id"]: f for f in read(faces_path)}, read(common_path))
        return source_refs[sid]

    rows = []
    for key, path, data in preparation_records:
        if data.get("namespace") != "APP_CONNECTIVITY":
            continue
        errors = []; entry = scene(key); faces, common = reference(entry)
        ev = data["connectivity_evidence"]; mode = data["mode"]
        parent_key = data["parent_cache_key"]
        parent = logs[parent_key][1]
        if ev.get("full_common_sha256") != common["sha256"] or ev.get("visibility_code_sha256") != FROZEN_VISIBILITY_SHA:
            errors.append("FULL_COMMON_OR_FROZEN_VISIBILITY_PARENT_HEADER")
        face_ids = {f["source_id"] for f in ev.get("faces", [])}
        if face_ids != set(faces):
            errors.append("FULL_B1_FACE_REPORT_POPULATION")
        if any(f["geometry_hash"] != faces[f["source_id"]]["geometry_hash"] for f in ev.get("faces", [])):
            errors.append("FACE_GEOMETRY_HASH")
        inherited = {}
        if mode in ("EXACT_STITCH", "CONDITIONAL_SEAMS"):
            pe = parent["connectivity_evidence"]
            expected_parent = "SOURCE_COMPLETE" if mode == "EXACT_STITCH" else "EXACT_STITCH"
            if parent.get("mode") != expected_parent:
                errors.append("ACTUAL_PARENT_MODE_OR_CACHE_CHAIN")
            for field in ("faces", "portals", "exact_directed_splits", "intersection_certificates"):
                inherited[field] = ev.get(field) == pe.get(field) and field in pe
                if not inherited[field]:
                    errors.append("LOST_PARENT_FIELD:" + field)
            if not data.get("graph_delta_only") or ev.get("parent_overlay_count", 0) < (1 if mode == "EXACT_STITCH" else 2):
                errors.append("INCREMENTAL_GRAPH_PARENT_OVERLAYS")
        graph_path = ROOT / data["stored_overlay"]
        if digest(graph_path) != data["stored_overlay_sha256"] or data.get("route_answers_stored") is not False:
            errors.append("STORED_DELTA_SHA_OR_ROUTE_ANSWER_STORAGE")
        certificates = []
        domains = {d["key"]: d for d in ev.get("stitch_domains", [])}
        for cert in ev.get("corner_reuse_certificates", []):
            q = shape(faces[cert["source_id"]]["components"][cert["component"]]["geometry"])
            r = shape(domains[cert["domain_key"]]["geometry"])
            added, lost = r.difference(q), q.difference(r)
            expected = {"original_geometry_sha256": q, "new_geometry_sha256": r,
                "added_geometry_sha256": added, "lost_geometry_sha256": lost}
            geometry_hashes = all(sha256(g.wkb).hexdigest() == cert[field] for field, g in expected.items())
            strict_subset = q.covers(r)
            samples = [LineString(s["xy"] if isinstance(s, dict) else s) for s in cert.get("negative_pair_samples", [])]
            if not geometry_hashes or strict_subset != cert["strict_global_subset"] or any(not line.disjoint(added) for line in samples):
                errors.append("REUSE_STRICT_GEOMETRY_CERTIFICATE")
            if cert.get("full_constraint_sha256") != common["sha256"] or cert.get("parent_full_common_sha256") != common["sha256"] or cert.get("visibility_code_sha256") != FROZEN_VISIBILITY_SHA:
                errors.append("REUSE_PARENT_CONSTRAINT_IDENTITY")
            certificates.append({"source_id": cert["source_id"], "component": cert["component"],
                "strict_geometry_hashes_match": geometry_hashes, "strict_global_subset": strict_subset,
                "sampled_negative_full_lines_disjoint_added": len(samples),
                **{k: cert.get(k) for k in ("reused_corner_count", "unchanged_neighbour_corner_count", "incident_options_checked", "reused_positive_pairs", "reused_negative_pairs", "negative_pairs_sha256")}})
        rows.append({"file": str(path.relative_to(ROOT)), "file_sha256": digest(path), "mode": mode,
            "scene_id": entry["scene_id"], "cache_key": key, "actual_parent_cache_key": parent_key,
            "actual_parent_mode": parent.get("mode", parent.get("namespace")),
            "inherited_parent_mode_field": ev.get("parent_mode"),
            "parent_mode_field_note": "Inherited header may name FROZEN_FULL_FACE; actual parent_cache_key and parent mode are authoritative",
            "full_face_reports": len(face_ids), "full_parent_fields_equal": inherited,
            "original_portals": len(ev.get("portals", [])), "stitch_portals": len(ev.get("stitch_portals", [])),
            "stitch_statistics": ev.get("stitch_statistics", {}), "reuse_certificates": certificates, "errors": errors})
    result = {"reviewer": "/root/connectivity_review", "scope": "Saved actual r2 preparation parent-chain/full B1 evidence and strict reuse domain hashes; overlay geometry audited separately",
        "backend_code_sha256": code_sha, "script_sha256": digest(Path(__file__)), "APP_solver_calls": 0,
        "rows": rows, "status": "PASS_FOR_COMPLETED_R2_PREPARATIONS" if rows and all(not r["errors"] for r in rows) else "NO_COMPLETED_CONNECTIVITY_PREPARATIONS_YET" if not rows else "REQUIRES_INSPECTION",
        "limits": ["All reused negative pairs are not re-enumerated here", "Saved preparation evidence is not a whole-network optimality or no-path proof", "Graph arcs and every accepted seam are audited separately"]}
    write(args.output, result)
    print(json.dumps({"status": result["status"], "rows": len(rows), "errors": sum(len(r["errors"]) for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
