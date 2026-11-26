"""Independent streaming review of every new arc and every accepted gap.

Uses raw OSM and previously independently reconstructed, SHA-bound Omega
artifacts. No author validator, planner or APP solver is invoked.
"""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import argparse
import gzip
import json
import math
import re

from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union, substring
from shapely import normalize
from shapely.strtree import STRtree

from independent_connectivity_source import ROOT, RawGeometry, digest, read, write
from independent_connectivity_omega import STRUCTURES, GATES, COMMON_GATES, denied, nonground
from independent_connectivity_responses import native_proof, FROZEN_VISIBILITY_SHA, direction_allowed


def contacts(g):
    if g.geom_type == "Point":
        return [g]
    if g.geom_type == "MultiPoint":
        return list(g.geoms)
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", type=Path, default=ROOT)
    ap.add_argument("--reference-root", type=Path, default=ROOT)
    ap.add_argument("--output", type=Path, default=ROOT / "audits/independent_overlay_review.json")
    ap.add_argument("--registry", type=Path)
    ap.add_argument("--code-sha", help="Audit only actual preparations bound to this frozen backend")
    a = ap.parse_args()
    artifact, reference = a.artifact_root.resolve(), a.reference_root.resolve()
    manifest = read(reference / "data/scene_manifest.json")["scenes"]
    by_sha = {r["source_sha256"]: r for r in manifest}
    logs, pending = {}, []
    for p in sorted((artifact / "runs/preprocessing").glob("*.json")):
        try:
            data = read(p)
        except json.JSONDecodeError:
            pending.append(str(p)); continue
        if data.get("cache_key") and (not a.code_sha or data.get("code_sha256") == a.code_sha):
            logs[data["cache_key"]] = (p, data)
    target_keys = None
    registry_sha = None
    if a.registry:
        raw = a.registry.read_bytes(); complete = raw[:raw.rfind(b"\n") + 1]
        registry_sha = sha256(complete).hexdigest()
        target_keys = set()
        for line in complete.splitlines():
            r = json.loads(line)
            body = read(artifact / r["path"])
            key = body.get("preprocessing_cache", {}).get("key")
            while key and key in logs and key not in target_keys:
                target_keys.add(key)
                key = logs[key][1].get("parent_cache_key", logs[key][1].get("base_cache_key"))
    def scene_of(key, visited=()):
        if key in visited or key not in logs:
            raise ValueError("NO_SOURCE_PARENT_CACHE_BINDING:" + str(key))
        d = logs[key][1]
        raw_sha = d.get("source", {}).get("source_sha256")
        if raw_sha in by_sha:
            return by_sha[raw_sha]
        return scene_of(d.get("parent_cache_key", d.get("base_cache_key")), visited + (key,))
    source_cache = {}
    def reference_scene(entry):
        sid = entry["scene_id"]
        if sid in source_cache:
            return source_cache[sid]
        raw_path = reference / entry["source_path"]
        if digest(raw_path) != entry["source_sha256"]:
            raise ValueError("RAW_SOURCE_HASH_CHANGED")
        src = RawGeometry(read(raw_path))
        omega_check = read(reference / "audits" / ("independent_omega_" + sid + ".json"))
        fp = reference / "data/connectivity" / (sid + "_faces.json")
        cp = reference / "data/connectivity" / (sid + "_full_common.json")
        if omega_check["status"] != "GEOMETRY_MATCH_FOR_REPORTED_SCOPE" or omega_check["author_faces_sha256"] != digest(fp) or omega_check["author_full_common_sha256"] != digest(cp):
            raise ValueError("INDEPENDENT_OMEGA_OR_COMMON_REFERENCE_NOT_BOUND")
        faces = read(fp); omega = {f["source_id"]: shape(f["omega"]) for f in faces if f["status"] == "ADMITTED"}
        Ps = {}
        for ident in omega:
            kind, number = ident.split("/")
            Ps[ident] = src.area(src.objects[(kind, int(number))])[0]
        legal = unary_union(list(omega.values()))
        removed = unary_union([Ps[k].difference(v) for k, v in omega.items()])
        common = read(cp)
        physical = shape(common["physical_geometry"]).buffer(-1e-7)
        background = shape(common["background_geometry"])
        barrier_rows = []
        for (kind, number), obj in src.objects.items():
            if kind != "way" or obj.get("tags", {}).get("barrier") not in STRUCTURES | GATES:
                continue
            refs = obj.get("nodes", [])
            if len(refs) < 2 or any(n not in src.xy for n in refs):
                continue
            gates = [Point(src.xy[n]) for n in refs if src.objects[("node", n)].get("tags", {}).get("barrier") in COMMON_GATES and
                     not denied(src.objects[("node", n)].get("tags", {})) and not nonground(src.objects[("node", n)].get("tags", {}))]
            barrier_rows.append({"source_id": "way/" + str(number), "geometry": LineString([src.xy[n] for n in refs]), "gates": gates})
        roads = []
        for r in common.get("road_centerlines", []):
            way = src.objects[("way", int(r["source_id"].split("/")[1]))]
            raw_line = LineString([src.xy[n] for n in way["nodes"]])
            if list(raw_line.coords) != [tuple(xy) for xy in r["geometry"]["coordinates"]] or nonground(way.get("tags", {})):
                raise ValueError("ROAD_REFERENCE_NOT_RAW_GROUND_SOURCE")
            roads.append({"source_id": r["source_id"], "geometry": raw_line, "native_nodes": set(way["nodes"])})
        access = []
        for r in common.get("native_road_access_points", []):
            n = int(r["id"].split("/")[1])
            if tuple(r["xy"]) != tuple(src.xy[n]) or denied(src.objects[("node", n)].get("tags", {})) or nonground(src.objects[("node", n)].get("tags", {})):
                raise ValueError("ROAD_ACCESS_POINT_NOT_UNMOVED_RAW_NODE")
            access.append(Point(src.xy[n]))
        entry = {"source": src, "omega": omega, "P": Ps, "legal": legal, "removed": removed, "common": common,
                 "physical": physical, "background": background, "barriers": barrier_rows,
                 "barrier_index": STRtree([r["geometry"] for r in barrier_rows]), "roads": roads,
                 "road_index": STRtree([r["geometry"] for r in roads]), "access": access,
                 "global_gap_clearance": unary_union([shape(c.get("source_geometry", c["geometry"])).buffer(.25, quad_segs=16)
                    for c in common["constraints"] if shape(c.get("source_geometry", c["geometry"])).area > 1e-6 and c.get("kind") not in {"BARRIER", "SOURCE_RESTRICTED_ACCESS_AREA"} and c.get("physical_barrier_asserted") is not False])}
        source_cache[sid] = entry
        return entry
    def free_conflicts(line, ref, seam=False):
        errors = []
        if line.intersection(ref["physical"]).length > 1e-6:
            errors.append("RAW_BOUND_COMMON_PHYSICAL_INTERIOR")
        if line.intersection(ref["background"]).length > 1e-6:
            errors.append("RAW_BOUND_BACKGROUND_NO_NEW_SHORTCUT")
        for i in ref["barrier_index"].query(line, predicate="intersects"):
            r = ref["barriers"][int(i)]; hit = line.intersection(r["geometry"]); points = contacts(hit)
            if not points or any(not any(q.distance(g) <= .001 and r["geometry"].distance(g) <= .001 for g in r["gates"]) for q in points):
                errors.append("RAW_EXACT_BARRIER_GATE:" + r["source_id"])
        ends = [Point(line.coords[0]), Point(line.coords[-1])]
        for i in ref["road_index"].query(line, predicate="intersects"):
            r = ref["roads"][int(i)]; hit = line.intersection(r["geometry"]); points = contacts(hit)
            if not points or any(not any(q.distance(e) <= 1e-6 for e in ends) or not any(q.distance(e) <= 1e-6 for e in ref["access"]) for q in points):
                errors.append("NO_NEW_RAW_ROAD_CROSSING:" + r["source_id"])
        if seam and line.intersection(ref["removed"]).difference(ref["legal"]).length > 0:
            errors.append("NO_P_TO_OMEGA_REFILL")
        if seam and not ref["global_gap_clearance"].is_empty and line.relate(ref["global_gap_clearance"])[0] == "1":
            errors.append("FULL_SOURCE_AREAL_CLEARANCE_0_25")
        if not shape(ref["common"]["coverage_geometry"]).covers(line):
            errors.append("OUTSIDE_FULL_SOURCE_COVERAGE")
        return sorted(set(errors))
    rows = []
    registered = digest(reference / "src/face_visibility.py") == FROZEN_VISIBILITY_SHA
    for key, (path, d) in logs.items():
        if d.get("namespace") != "APP_CONNECTIVITY" or d.get("mode") not in {"EXACT_STITCH", "CONDITIONAL_SEAMS"} or target_keys is not None and key not in target_keys:
            continue
        entry = scene_of(key); ref = reference_scene(entry); evidence = d["connectivity_evidence"]
        graph_path = artifact / d["stored_overlay"]
        errors, segment_counts, raw_alarms = [], Counter(), []
        if digest(graph_path) != d["stored_overlay_sha256"]:
            raise ValueError("STORED_GRAPH_ARCHIVE_HASH_MISMATCH")
        nodes, arc_refs = {}, {}
        for record in evidence.get("seams", []):
            arc_refs[record["id"]] = []
        with gzip.open(graph_path, "rt", encoding="utf-8") as stream:
            for text in stream:
                r = json.loads(text)
                if r["kind"] == "node":
                    nodes[r["id"]] = r
                    n = re.fullmatch(r"node/(\d+)(?:@.*)?", r["id"])
                    if n:
                        raw_node = ref["source"].objects[("node", int(n.group(1)))]
                        if tuple(r["xy"]) != tuple(ref["source"].xy[int(n.group(1))]) or r.get("tags", {}) != raw_node.get("tags", {}):
                            errors.append({"node": r["id"], "errors": ["ORIGINAL_NODE_COORDINATE_OR_TAGS_CHANGED"]})
                    continue
                for option in r.get("routing_alternatives", [r["segments"]]):
                    for s in option:
                        kind = s.get("geometry_kind", "UNKNOWN"); segment_counts[kind] += 1
                        line = LineString(s["xy"]); bad = []
                        if abs(line.length - s["length_m"]) > 1e-6 or abs(line.length - s["cost_m"]) > 1e-6:
                            bad.append("BASE_F0_GEOMETRY_LENGTH_OR_COST_CHANGED")
                        if kind in {"SOURCE_SUPPORTED_INTERFACE", "DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE"}:
                            owners = s.get("source_area_ids", [s.get("source_area_id", s.get("source_id"))])
                            if s["layer"] != "derived" or not any(ident in ref["omega"] and ref["omega"][ident].covers(line) for ident in owners):
                                bad.append("WHOLE_NEW_DERIVED_SEGMENT_WITHOUT_INDEPENDENT_OMEGA_OWNER")
                            bad += free_conflicts(line, ref)
                        elif kind == "CONDITIONAL_GAP_LINK":
                            if s["layer"] != "inferred":
                                bad.append("SEAM_PROMOTED_TO_NATIVE_OR_DERIVED")
                            if line.length > float(evidence["seam_max_m"]):
                                bad.append("SEAM_ABOVE_PREDECLARED_CAP")
                            bad += free_conflicts(line, ref, seam=True)
                            arc_refs.setdefault(s.get("interface_id"), []).append({"u": r["u"], "v": r["v"], "xy": s["xy"], "layer": s["layer"]})
                        elif s.get("layer") == "native" and s.get("source_id", "").startswith("way/"):
                            proof = native_proof(s, ref["source"], {"connectivity_evidence": evidence}, registered)
                            if not proof["passed"]:
                                bad += proof["errors"]
                            if proof["original_strict_alarm_preserved"]:
                                raw_alarms.append({"u": r["u"], "v": r["v"], "proof": proof})
                        if bad:
                            errors.append({"u": r["u"], "v": r["v"], "source_id": s.get("source_id"), "kind": kind, "errors": sorted(set(bad))})
        accepted = []
        for record in evidence.get("seams", []):
            actual = arc_refs.get(record["id"], [])
            if not record["accepted"]:
                if actual:
                    errors.append({"seam_id": record["id"], "errors": ["REJECTED_SEAM_ENTERED_NEW_GRAPH"]})
                continue
            line = shape(record["geometry"]); bad = free_conflicts(line, ref, seam=True)
            if line.length != record["distance_m"] or line.length > float(evidence["seam_max_m"]) or record.get("assumption_multiplier_F0") != 1 or record.get("assumption_multiplier_F1") != 2:
                bad.append("SEAM_DISTANCE_CAP_OR_COST_ROLE_METADATA")
            if not any(ident in ref["omega"] and ref["omega"][ident].covers(Point(line.coords[0])) for ident in record["source_area_ids"]):
                bad.append("SEAM_FACE_ENDPOINT_NOT_COVERED_BY_DECLARED_INDEPENDENT_OMEGA")
            parent = record.get("parent")
            parent_proof = None
            if parent:
                parent_line = shape(parent["geometry"])
                uid, vid = int(parent["u"].split("/")[1]), int(parent["v"].split("/")[1])
                raw_parent = [ref["source"].xy[uid], ref["source"].xy[vid]]
                eligible = []
                for ident in record["source_ids"]:
                    way = ref["source"].objects[("way", int(ident.split("/")[1]))]
                    for x, y in zip(way["nodes"], way["nodes"][1:]):
                        if (uid, vid) == (x, y) and direction_allowed(way.get("tags", {}), 1) or (uid, vid) == (y, x) and direction_allowed(way.get("tags", {}), -1):
                            eligible.append(ident)
                if list(parent_line.coords) != raw_parent or not eligible or not 0 <= parent["position_m"] <= parent_line.length:
                    bad.append("SEAM_PARENT_NOT_EXACT_RAW_DIRECTED_ADJACENT_EDGE")
                position = parent["position_m"]
                expected = raw_parent[0] if position == 0 else raw_parent[-1] if position == parent_line.length else tuple(substring(parent_line, 0, position).coords[-1])
                if tuple(line.coords[-1]) != tuple(expected):
                    bad.append("SEAM_NATIVE_PROJECTION_NOT_IDENTICAL_REGISTERED_PARENT_PARAMETER")
                parent_proof = {"native_ids": [parent["u"], parent["v"]], "position_m": position, "source_ids_with_allowed_direction": eligible,
                                "identical_raw_parent_geometry": list(parent_line.coords) == raw_parent, "projection_exact_xy": list(expected)}
            elif not any(ident in ref["omega"] and ref["omega"][ident].covers(Point(line.coords[-1])) for ident in record["source_area_ids"]):
                bad.append("SEAM_SECOND_FACE_ENDPOINT_NOT_COVERED_BY_DECLARED_INDEPENDENT_OMEGA")
            if not record.get("entered_graph") or len(actual) < 2:
                bad.append("ACCEPTED_SEAM_MISSING_TWO_DIRECTED_GRAPH_OPTIONS")
            ids = record.get("graph_node_ids", [])
            if len(ids) != 2 or any(ident not in nodes for ident in ids):
                bad.append("ACCEPTED_SEAM_NODE_IDS_NOT_IN_NEW_GRAPH")
            elif [tuple(nodes[ident]["xy"]) for ident in ids] != list(line.coords):
                bad.append("ACCEPTED_SEAM_NODE_COORDINATES_DIFFER")
            if len(ids) == 2 and ({(ids[0], ids[1]), (ids[1], ids[0])} - {(r["u"], r["v"]) for r in actual}):
                bad.append("ACCEPTED_SEAM_DIRECTION_PAIR_MISSING")
            if any(r["xy"] not in [[list(p) for p in line.coords], [list(p) for p in reversed(line.coords)]] for r in actual):
                bad.append("SEAM_RECORD_AND_GRAPH_GEOMETRY_DIFFER")
            accepted.append({"id": record["id"], "distance_m": line.length, "source_area_ids": record["source_area_ids"], "source_ids": record["source_ids"],
                             "geometry_sha256": sha256(normalize(line).wkb).hexdigest(), "graph_options": len(actual), "errors": sorted(set(bad))})
            if parent_proof is not None:
                accepted[-1]["independent_parent_projection_proof"] = parent_proof
            if bad:
                errors.append({"seam_id": record["id"], "errors": sorted(set(bad))})
        rows.append({"scene_id": entry["scene_id"], "mode": d["mode"], "seam_max_m": d["seam_max_m"], "cache_key": key,
                     "preprocessing_file": str(path), "preprocessing_sha256": digest(path), "stored_overlay": str(graph_path), "stored_overlay_sha256": digest(graph_path),
                     "all_segment_option_counts": dict(segment_counts), "accepted_seam_record_count": len(accepted),
                     "accepted_distinct_geometry_count": len({r["geometry_sha256"] for r in accepted}), "accepted_seams": accepted,
                     "strict_native_binary_alarms_with_registered_parent_proofs": raw_alarms, "errors": errors})
    result = {"reviewer": "/root/connectivity_review", "scope": "Every option segment in each reported new delta and every accepted seam, including unused seams; raw-source negative constraints and SHA-bound independently reconstructed Omega",
              "APP_solver_calls": 0, "external_requests": 0, "review_script_sha256": digest(Path(__file__)), "artifact_root": str(artifact),
              "formal_registry_snapshot_sha256": registry_sha, "backend_code_sha256_filter": a.code_sha, "rows": rows, "pending_unparsed_live_logs_excluded": pending,
              "status": "PASS_FOR_REPORTED_NEW_OVERLAYS_AND_ALL_ACCEPTED_SEAMS" if rows and all(not r["errors"] for r in rows) else "REQUIRES_INSPECTION",
              "limits": ["This does not independently resolve all preexisting whole-network paths", "Counts include distinct evidence records for opposite original parent directions; distinct physical seam geometry count is separate", "No APP or field/user acceptance"]}
    write(a.output, result)
    print(json.dumps({"status": result["status"], "overlays": len(rows), "accepted_seam_records": sum(r["accepted_seam_record_count"] for r in rows), "errors": sum(len(r["errors"]) for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
