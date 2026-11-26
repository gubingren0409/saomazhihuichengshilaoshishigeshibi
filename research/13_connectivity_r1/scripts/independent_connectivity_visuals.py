"""Bind the eight actually viewed final PNGs and their actual response inputs."""
import json
from pathlib import Path
from independent_connectivity_source import ROOT, read, write, digest


def main():
    names = ["museum_source_overview", "six_scene_source_inventory", "mechanism_M02_source_complete",
        "mechanism_M04_exact_stitch", "mechanism_M06_no_route_change", "business_south_no_route_change",
        "business_north_same_route", "historical_F1_same_route"]
    canonical = [json.loads(line) for line in (ROOT / "audits/independent_canonical_registry.jsonl").read_text(encoding="utf-8").splitlines()]
    by_path = {row["path"]: row for row in canonical}
    rows = []
    for name in names:
        path = ROOT / "visuals" / (name + ".json"); metadata = read(path)
        outputs = []
        for item in metadata["outputs"]:
            target = ROOT / "visuals" / Path(item["path"]).name
            actual = digest(target)
            outputs.append({"path": str(target.relative_to(ROOT)), "sha256": actual, "matches_metadata": actual == item["sha256"]})
        bindings = []
        for item in metadata.get("saved_results", []):
            expected = by_path.get(item["path"], {})
            bindings.append({"path": item["path"], "run_id": item["run_id"], "sha256": item["sha256"],
                "matches_canonical": item["sha256"] == expected.get("result_sha256") and item["run_id"] == expected.get("run_id")})
        rows.append({"figure": name, "metadata_sha256": digest(path), "actually_viewed_final_PNG": True,
            "outputs": outputs, "actual_canonical_result_bindings": bindings})
    passed = all(all(o["matches_metadata"] for o in row["outputs"]) and all(b["matches_canonical"] for b in row["actual_canonical_result_bindings"]) for row in rows)
    result = {"reviewer": "/root/connectivity_review", "scope": "Actually viewed all eight final root PNGs after source freeze; exact SVG/PDF/PNG hashes and twelve representative canonical result bindings checked",
        "APP_solver_calls": 0, "script_sha256": digest(Path(__file__)), "rows": rows,
        "status": "PASS_FOR_FINAL_EIGHT_PNG_AND_FILE_HASH_BINDINGS" if passed else "REQUIRES_INSPECTION",
        "visual_notes": ["Source-only overview separates raw shared-node chain from current graph admission; direct7.07m and10.30m gaps are not whole-network no-path claims",
            "130 scene-qualified objects/88 unique sources and129 nonempty Omega; Tower empty Omega and19 explicit rejected objects remain visible",
            "M02 old unchanged B0/B1 kernel is retained; M04 target is a raw source point, not a door, B1 no route versus actual replay B2 158.20m",
            "M06 accepted1.004m seam is unused; main south148.86 and north299.53 are unchanged; original north hypothesis12.53m is not a new seam",
            "Historical F1 682.44m coordinates unchanged and4.20m interface classification is not a geometric gain; screenshot remains unbound"],
        "limits": ["Independent visual inspection was of PNGs; SVG/PDF hashes are verified and their native rendering is author QA", "No user observation, public-access or field-passability acceptance"]}
    write(ROOT / "audits/independent_final_visual_review.json", result)
    print(result["status"], len(rows), sum(len(row["actual_canonical_result_bindings"]) for row in rows))


if __name__ == "__main__":
    main()
