"""Audit actual accepted domain joins against independent raw P contacts."""
from shapely.geometry import shape
from shapely.ops import unary_union
from independent_connectivity_source import ROOT, digest, read, write


def main():
    independent_path = ROOT / "audits/independent_source_admitted_P.geojson"
    raw_P = {(f["properties"]["scene_id"], f["properties"]["source_id"]): shape(f["geometry"])
        for f in read(independent_path)["features"]}
    manifest = read(ROOT / "data/scene_manifest.json")["scenes"]
    scene_by_sha = {r["source_sha256"]: r["scene_id"] for r in manifest}
    frozen = read(ROOT / "audits/backend_freeze_r2.json")["code_sha256"]
    logs, records = {}, []
    for path in (ROOT / "runs/preprocessing").glob("*.json"):
        row = read(path)
        if row.get("code_sha256") != frozen or not row.get("cache_key"):
            continue
        logs[row["cache_key"]] = row
        if row.get("mode") in {"EXACT_STITCH", "CONDITIONAL_SEAMS"}:
            records.append((path, row))
    def scene_of(key):
        while key in logs:
            row = logs[key]; raw_sha = row.get("source", {}).get("source_sha256")
            if raw_sha in scene_by_sha:
                return scene_by_sha[raw_sha]
            key = row.get("parent_cache_key", row.get("base_cache_key"))
        raise ValueError("NO_SOURCE_PARENT")
    commons = {}; rows = []
    for path, pp in records:
        sid = scene_of(pp["cache_key"])
        if sid not in commons:
            common_path = ROOT / "data/connectivity" / (sid + "_full_common.json")
            omega = read(ROOT / "audits" / ("independent_omega_" + sid + ".json"))
            assert digest(common_path) == omega["author_full_common_sha256"]
            commons[sid] = unary_union([shape(r["geometry"]) for r in read(common_path)["road_centerlines"]])
        accepted, point_rejected, errors = 0, 0, []
        for relation in pp["connectivity_evidence"].get("face_relations", []):
            if not relation["accepted"]:
                point_rejected += relation["kind"] == "POINT_TOUCH"
                continue
            accepted += 1; a, b = relation["source_ids"]
            if a != b:
                raw_contact = raw_P[(sid, a)].intersection(raw_P[(sid, b)])
                if raw_contact.area == 0 and raw_contact.length <= 1e-9:
                    errors.append({"source_ids": [a, b], "reason": "NO_POSITIVE_RAW_P_AREA_OR_EDGE_CONTACT", "raw_intersection": raw_contact.wkt})
            if relation["kind"] == "SHARED_BOUNDARY" and shape(relation["geometry"]).difference(commons[sid]).length <= 1e-9:
                errors.append({"source_ids": [a, b], "reason": "SHARED_EDGE_ENTIRELY_ROAD_PARTITION"})
        rows.append({"PREP_file": str(path.relative_to(ROOT)), "PREP_sha256": digest(path), "scene_id": sid, "mode": pp["mode"],
            "accepted_component_pair_records": accepted, "explicit_point_contact_pair_records_rejected": point_rejected, "errors": errors})
    result = {"reviewer": "/root/connectivity_review", "scope": "Every accepted domain pair in actual r2 cold PREPs must have positive raw-P support and must not join solely across a road partition; no geometry tolerance added",
        "APP_solver_calls": 0, "independently_reconstructed_P_sha256": digest(independent_path), "rows": rows,
        "status": "PASS_FOR_REPORTED_RAW_P_DOMAIN_JOINS" if rows and all(not r["errors"] for r in rows) else "REQUIRES_INSPECTION",
        "limits": ["Original graph native connectivity may remain across point-touch faces; this check forbids new free joins", "Graph edge constraints, full parent curves, geometry/cost and source qualification are audited separately"]}
    write(ROOT / "audits/independent_domain_relation_review.json", result)
    print(__import__("json").dumps({"status": result["status"], "PREPs": len(rows), "accepted_records": sum(r["accepted_component_pair_records"] for r in rows), "errors": sum(len(r["errors"]) for r in rows)}))


if __name__ == "__main__":
    main()
