"""Remeasure author relation records from independently reconstructed raw P."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json

from shapely.geometry import LineString, shape

from independent_connectivity_source import RawGeometry, ROOT, digest, read, write


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.root.resolve()
    records, scene_rows = [], []
    admitted = read(root / "audits/independent_source_admitted_P.geojson")["features"]
    lookup = {(f["properties"]["scene_id"], f["properties"]["source_id"]): shape(f["geometry"]) for f in admitted}
    for scene in read(root / "data/scene_manifest.json")["scenes"]:
        sid = scene["scene_id"]
        source = RawGeometry(read(root / scene["source_path"]))
        omega_report = read(root / "audits" / ("independent_omega_" + sid + ".json"))
        if omega_report["status"] != "GEOMETRY_MATCH_FOR_REPORTED_SCOPE":
            raise ValueError("OMEGA_NOT_INDEPENDENTLY_VALIDATED:" + sid)
        author_faces = read(root / "data/connectivity" / (sid + "_faces.json"))
        omega = {r["source_id"]: shape(r["omega"]) for r in author_faces}
        path = root / "data/connectivity" / (sid + "_relations.json")
        rows = read(path)
        counts = Counter()
        for row in rows:
            aid, bid = row["a_source_id"], row["b_source_id"]
            P = lookup[(sid, aid)]
            if row["kind"] == "FACE_LINE":
                obj = source.objects[(bid.split("/")[0], int(bid.split("/")[1]))]
                b = LineString([source.xy[n] for n in obj["nodes"]])
                ob = b
            else:
                b = lookup[(sid, bid)]
                ob = omega[bid]
            hit, ohit = P.intersection(b), omega[aid].intersection(ob)
            pd = P.distance(b)
            od = None if omega[aid].is_empty or ob.is_empty else omega[aid].distance(ob)
            category = "EMPTY_OMEGA" if od is None else "SOURCE_POSITIVE_GAP" if pd > 1e-8 else "P_CONTACT_OMEGA_SEPARATED" if od > 1e-8 else "BOTH_CONTACT"
            errors = []
            if abs(pd - row["P"]["distance_m"]) > 1e-6:
                errors.append("P_DISTANCE")
            if (od is None) != (row["omega"]["distance_m"] is None) or od is not None and abs(od - row["omega"]["distance_m"]) > 1e-6:
                errors.append("OMEGA_DISTANCE")
            if row["kind"] == "FACE_LINE":
                if abs(hit.length - row["P"]["intersection_length_m"]) > 1e-6:
                    errors.append("P_INTERSECTION_LENGTH")
                if abs(ohit.length - row["omega"]["intersection_length_m"]) > 1e-6:
                    errors.append("OMEGA_INTERSECTION_LENGTH")
            else:
                if abs(P.boundary.intersection(b.boundary).length - row["P"]["shared_boundary_length_m"]) > 1e-6 or abs(hit.area - row["P"]["overlap_area_m2"]) > 1e-6:
                    errors.append("P_SHARED_BOUNDARY_OR_AREA")
                if abs(omega[aid].boundary.intersection(ob.boundary).length - row["omega"]["shared_boundary_length_m"]) > 1e-6 or abs(ohit.area - row["omega"]["overlap_area_m2"]) > 1e-6:
                    errors.append("OMEGA_SHARED_BOUNDARY_OR_AREA")
            counts[category] += 1
            records.append({"scene_id": sid, "kind": row["kind"], "a_source_id": aid, "b_source_id": bid,
                            "P_distance_m": pd, "omega_distance_m": od, "P_intersection_length_m": hit.length,
                            "omega_intersection_length_m": ohit.length, "category": category,
                            "b_ground_permission_eligible": row.get("b_ground_permission_eligible"),
                            "author_nearest_connector_conflicts": row.get("nearest_connector_conflicts"), "errors": errors})
        scene_rows.append({"scene_id": sid, "relations": len(rows), "independent_categories": dict(counts),
                           "author_relation_sha256": digest(path), "omega_independent_check_sha256": digest(root / "audits" / ("independent_omega_" + sid + ".json"))})
    inventory = read(root / "audits/independent_source_inventory.json")
    admitted_rows = [r for r in inventory if r["status"] == "ADMITTED"]
    unique = defaultdict(list)
    for r in admitted_rows:
        unique[(r["source_id"], r["version"])].append(r["scene_id"])
    omitted_unique = {key for key in unique if not any(r["legacy_selected"] for r in admitted_rows if (r["source_id"], r["version"]) == key)}
    summary = {"reviewer": "/root/connectivity_review", "scope": "Raw source population and remeasurement of every frozen author relation; Omega verified separately before reuse",
               "APP_solver_calls": 0, "external_requests": 0, "source_admitted_scene_objects": len(admitted_rows), "source_admitted_unique_type_id_versions": len(unique),
               "newly_qualified_scene_objects": sum(not r["legacy_selected"] for r in admitted_rows), "newly_qualified_unique_type_id_versions": len(omitted_unique),
               "cross_clip_repeated_unique_objects": sum(len(scenes) > 1 for scenes in unique.values()),
               "raw_highway_line_scene_objects": len(read(root / "audits/independent_source_lines.json")),
               "scenes": scene_rows, "relation_count": len(records), "errors": [r for r in records if r["errors"]],
               "P_contact_omega_gap": [r for r in records if r["category"] == "P_CONTACT_OMEGA_SEPARATED"],
               "status": "MATCH_FOR_REPORTED_SOURCE_AND_RELATION_SCOPE" if all(not r["errors"] for r in records) else "DIFFERENCE_REQUIRES_INSPECTION",
               "limits": ["A P contact separated by Omega is a constraint/clearance case, not proof of an OSM gap", "Matching geometry does not prove graph admission or route use", "Repeated scene objects are not distinct new physical surfaces", "No user acceptance or field validation"]}
    write(root / "audits/independent_source_relation_review.json", summary)
    write(root / "audits/independent_source_relation_measurements.json", records)
    print(json.dumps({k: summary[k] for k in ("status", "source_admitted_scene_objects", "source_admitted_unique_type_id_versions", "newly_qualified_scene_objects", "newly_qualified_unique_type_id_versions", "raw_highway_line_scene_objects", "relation_count")}, ensure_ascii=False))
    print("errors", len(summary["errors"]), "P_contacts_separated_by_Omega", len(summary["P_contact_omega_gap"]))


if __name__ == "__main__":
    main()
