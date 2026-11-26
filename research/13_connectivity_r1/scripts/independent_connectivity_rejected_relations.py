"""Independent raw-P review of rejected area relations, separate from active graph."""
from pathlib import Path
import argparse
import json

from shapely.geometry import LineString

from independent_connectivity_source import ROOT, RawGeometry, digest, read, write


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    root = a.root.resolve()
    inventory = read(root / "audits/independent_source_inventory.json")
    status = {(r["scene_id"], r["source_id"]): r["status"] for r in inventory}
    rows = []
    for scene in read(root / "data/scene_manifest.json")["scenes"]:
        sid = scene["scene_id"]
        src = RawGeometry(read(root / scene["source_path"]))
        path = root / "data/connectivity" / (sid + "_rejected_relations.json")
        if not path.exists():
            continue
        cache = {}
        def P(ident):
            if ident not in cache:
                kind, number = ident.split("/")
                cache[ident] = src.area(src.objects[(kind, int(number))])[0]
            return cache[ident]
        for r in read(path):
            aid, bid = r["a_source_id"], r["b_source_id"]
            a = P(aid)
            if r["kind"] == "FACE_LINE":
                b = LineString([src.xy[n] for n in src.objects[("way", int(bid.split("/")[1]))]["nodes"]])
            else:
                b = P(bid)
            errors = []
            expected_a = status[(sid, aid)]
            expected_b = status.get((sid, bid)) if r["kind"] == "FACE_FACE" else ("SOURCE_AREA_BOUNDARY_NOT_INDEPENDENT_NATIVE_LINE" if src.objects[("way", int(bid.split("/")[1]))].get("tags", {}).get("area") == "yes" else None)
            if expected_a != r["a_status"] or expected_b is not None and expected_b != r["b_status"]:
                errors.append("ADMISSION_STATUS_DIFFERS_FROM_INDEPENDENT_RAW_RULES")
            if abs(a.distance(b) - r["P"]["distance_m"]) > 1e-6:
                errors.append("P_DISTANCE")
            if r["kind"] == "FACE_FACE":
                if abs(a.intersection(b).area - r["P"]["overlap_area_m2"]) > 1e-6 or abs(a.boundary.intersection(b.boundary).length - r["P"]["shared_boundary_length_m"]) > 1e-6:
                    errors.append("P_AREA_OR_SHARED_EDGE")
            elif abs(a.intersection(b).length - r["P"]["intersection_length_m"]) > 1e-6:
                errors.append("P_LINE_INTERSECTION_LENGTH")
            if expected_a == "ADMITTED" and (expected_b is None or expected_b == "ADMITTED"):
                errors.append("NOT_A_REJECTED_FACE_RELATION")
            rows.append({"scene_id": sid, "kind": r["kind"], "a_source_id": aid, "b_source_id": bid,
                         "independent_a_status": expected_a, "independent_b_status": expected_b,
                         "P_distance_m": a.distance(b), "author_file_sha256": digest(path), "errors": errors})
    rejected = [r for r in inventory if r["explicit_walk_area"] and r["status"] != "ADMITTED"]
    result = {"reviewer": "/root/connectivity_review", "scope": "Independent raw P and frozen rejection reasons of all source-rejected relation records; no route or graph claim",
              "APP_solver_calls": 0, "external_requests": 0, "rejected_explicit_source_face_count": len(rejected),
              "rejected_explicit_source_faces": [{k: r[k] for k in ("scene_id", "source_id", "status", "tags", "geometry_reason")} for r in rejected],
              "rejected_relation_count": len(rows), "rows": rows,
              "status": "MATCH_FOR_REPORTED_REJECTED_SOURCE_SCOPE" if all(not r["errors"] for r in rows) else "DIFFERENCE_REQUIRES_INSPECTION",
              "reviewer_initial_alarm_adjudication": "Initial reviewer assumed every rejected-relation row must contain a rejected area. Two rows instead correctly reject an area=yes outer boundary as an independent native line beside an admitted face; classifier now independently preserves that distinction. Original alarm retained in independent_rejected_relation_initial_alarm.json; no author change.",
              "limits": ["Rejected P contact is not a permitted interface", "Empty rejected Omega does not establish a measured source gap", "Not an independent whole-network graph proof"]}
    write(root / "audits/independent_rejected_relation_review.json", result)
    print(json.dumps({"status": result["status"], "rejected_faces": len(rejected), "rejected_relations": len(rows), "errors": sum(bool(r["errors"]) for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
