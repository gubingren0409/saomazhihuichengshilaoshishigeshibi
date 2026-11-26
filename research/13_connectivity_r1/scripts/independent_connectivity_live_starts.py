"""Read-only raw eligibility of already predeclared live starts; no reselection."""
from shapely.geometry import Point, LineString, shape
from shapely.strtree import STRtree
from independent_connectivity_source import ROOT, RawGeometry, coverage, digest, read, write, linear_tag_reason
from independent_connectivity_omega import nonground


def main():
    plan = read(ROOT / "audits/independent_live_request_plan.json")
    sid = plan["fixed_fields"]["scene_id"]
    entry = next(r for r in read(ROOT / "data/scene_manifest.json")["scenes"] if r["scene_id"] == sid)
    src = RawGeometry(read(ROOT / entry["source_path"]))
    common = read(ROOT / "data/connectivity" / (sid + "_full_common.json"))
    hard = [r for r in common["constraints"] if not r.get("policy_only")]
    geoms = [shape(r["geometry"]) for r in hard]; index = STRtree(geoms)
    rows = []
    for ident in sorted({r["start_id"] for r in plan["ui_calls"] + plan["final_clean_calls"]}):
        number = int(ident.split("/")[1]); traces = []
        for (kind, way_id), way in src.objects.items():
            if kind != "way" or number not in way.get("nodes", []):
                continue
            if not way.get("tags", {}).get("highway") or way.get("tags", {}).get("area") == "yes":
                continue
            for i, (a, b) in enumerate(zip(way["nodes"], way["nodes"][1:])):
                if number not in (a, b) or a not in src.xy or b not in src.xy:
                    continue
                line = LineString([src.xy[a], src.xy[b]]); hits = []
                for j in index.query(line, predicate="intersects"):
                    j = int(j); g = geoms[j]
                    overlap = line.intersection(g.buffer(-1e-7) if g.area > 1e-6 else g).length
                    if overlap > 1e-6:
                        hits.append({"source_id": hard[j]["source_id"], "kind": hard[j]["kind"], "overlap_m": overlap})
                traces.append({"source_id": "way/" + str(way_id), "raw_segment_index": i, "raw_nodes": [a, b],
                    "raw_xy": [src.xy[a], src.xy[b]], "tags": way.get("tags", {}),
                    "linear_tag_reason": linear_tag_reason(way.get("tags", {})), "non_ground": nonground(way.get("tags", {})), "hard_contacts": hits})
        qualifies = any(r["linear_tag_reason"] is None and not r["non_ground"] and not r["hard_contacts"] for r in traces)
        rows.append({"native_id": ident, "raw_xy": src.xy[number], "raw_node_tags": src.objects[("node", number)].get("tags", {}),
            "inside_full_acquired_coverage": coverage(entry["full_source_clip_bounds"]).covers(Point(src.xy[number])),
            "has_ground_tag_eligible_whole_native_segment_without_hard_interior_contact": qualifies, "incident_segments": traces})
    result = {"reviewer": "/root/connectivity_review", "scope": "Only fixed predeclared original start eligibility; no route outcomes, new point selection or graph solve",
        "APP_solver_calls": 0, "request_plan_sha256": digest(ROOT / "audits/independent_live_request_plan.json"),
        "source_sha256": digest(ROOT / entry["source_path"]), "rows": rows,
        "status": "PASS_FOR_DECLARED_RAW_START_ELIGIBILITY" if all(r["inside_full_acquired_coverage"] and r["has_ground_tag_eligible_whole_native_segment_without_hard_interior_contact"] for r in rows) else "REQUIRES_INSPECTION",
        "limits": ["This is not a claim of whole-network reachability or a replacement for actual fresh solver calls"]}
    write(ROOT / "audits/independent_live_start_eligibility.json", result)
    print(__import__("json").dumps({"status": result["status"], "rows": [{k: r[k] for k in ("native_id", "has_ground_tag_eligible_whole_native_segment_without_hard_interior_contact")} for r in rows]}))


if __name__ == "__main__":
    main()
