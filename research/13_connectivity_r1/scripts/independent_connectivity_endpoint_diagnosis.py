"""Raw endpoint identity, coverage, incident way and whole-edge policy diagnosis."""
from collections import defaultdict
from pathlib import Path
import json

from shapely.geometry import Point, LineString, shape
from shapely.strtree import STRtree

from independent_connectivity_source import ROOT, RawGeometry, coverage, digest, read, write, linear_tag_reason
from independent_connectivity_omega import nonground


def main():
    lock = read(ROOT / "data/connectivity/mechanism_request_endpoints_lock.json")
    manifest = {r["scene_id"]: r for r in read(ROOT / "data/scene_manifest.json")["scenes"]}
    cache, rows = {}, []
    for query in lock["queries"]:
        sid = query["scene_id"]
        if sid not in cache:
            src = RawGeometry(read(ROOT / manifest[sid]["source_path"]))
            common = read(ROOT / "data/connectivity" / (sid + "_full_common.json"))
            hard = [r for r in common["constraints"] if not r.get("policy_only")]
            geometries = [shape(r["geometry"]) for r in hard]
            index = STRtree(geometries)
            incident = defaultdict(list)
            for (kind, wid), obj in src.objects.items():
                if kind == "way" and obj.get("tags", {}).get("highway") and obj.get("tags", {}).get("area") != "yes":
                    for i, (a, b) in enumerate(zip(obj["nodes"], obj["nodes"][1:])):
                        if a in src.xy and b in src.xy:
                            for n in (a, b):
                                incident[n].append((obj, i, a, b))
            cache[sid] = (src, common, hard, geometries, index, incident)
        src, common, hard, geometries, index, incident = cache[sid]
        for endpoint in ("start", "end"):
            e = query[endpoint]; n = int(e["native_id"].split("/")[1]); raw = src.objects[("node", n)]
            traces = []
            for obj, i, a, b in incident[n]:
                line = LineString([src.xy[a], src.xy[b]])
                hits = []
                for j in index.query(line, predicate="intersects"):
                    j = int(j); g = geometries[j]
                    amount = line.intersection(g.buffer(-1e-7) if g.area > 1e-6 else g).length
                    if amount > 1e-6:
                        hits.append({"source_id": hard[j]["source_id"], "kind": hard[j]["kind"], "tags": hard[j].get("tags", {}), "whole_segment_interior_overlap_m": amount})
                traces.append({"source_id": "way/" + str(obj["id"]), "segment_index": i, "raw_node_ids": [a, b], "tags": obj.get("tags", {}),
                               "linear_tag_reason": linear_tag_reason(obj.get("tags", {})), "explicit_non_ground": nonground(obj.get("tags", {})), "hard_mask_contacts": hits})
            rows.append({"mechanism_id": query["mechanism_id"], "scene_id": sid, "endpoint": endpoint, "native_id": e["native_id"],
                         "exact_raw_coordinate_values": tuple(e["xy"]) == tuple(src.xy[n]), "exact_raw_wgs84_values": e["wgs84"] == [raw["lon"], raw["lat"]],
                         "exact_raw_tags": e["source_node_tags"] == raw.get("tags", {}), "source_version": raw.get("version"),
                         "within_acquired_coverage": coverage(manifest[sid]["full_source_clip_bounds"]).covers(Point(src.xy[n])),
                         "layer_aware_native_graph_id": e.get("layer_aware_native_graph_id"), "incident_raw_segment_diagnosis": traces})
    result = {"reviewer": "/root/connectivity_review", "scope": "All 16 locked raw original endpoints and their immediate original highway edges; source and acquired policy only, no whole-network graph solve",
              "APP_solver_calls": 0, "external_requests": 0, "endpoint_lock_sha256": digest(ROOT / "data/connectivity/mechanism_request_endpoints_lock.json"),
              "rows": rows, "status": "PASS_FOR_REPORTED_SOURCE_ENDPOINT_IDENTITY_AND_DIAGNOSIS" if all(r["exact_raw_coordinate_values"] and r["exact_raw_wgs84_values"] and r["exact_raw_tags"] and r["within_acquired_coverage"] for r in rows) else "DIFFERENCE_REQUIRES_INSPECTION",
              "interpretation": ["M03 start has mapped incident lines; its eligible footway's whole segment hits common hard policy, so unbound is not a coverage failure or absence of all source lines", "M08 retains its explicit layer-aware identity; it must not become an ordinary ground face endpoint", "A directly measured gap and source-native chain do not establish full graph reachability", "Private vehicle-line restriction masks are inherited conservatism, not changed to improve this round"]}
    write(ROOT / "audits/independent_mechanism_endpoint_diagnosis.json", result)
    print(json.dumps({"status": result["status"], "points": len(rows), "M03_start": next(r for r in rows if r["mechanism_id"] == "M03" and r["endpoint"] == "start")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
