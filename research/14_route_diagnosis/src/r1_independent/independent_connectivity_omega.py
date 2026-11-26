"""Independently reconstruct P/Omega masks from raw OSM, without src imports."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import json
import time

from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from independent_connectivity_source import RawGeometry, ROOT, DENIED, FALSE, coverage, digest, explicit_face, ground_reason, permission_reason, read, relation, write

STRUCTURES = {"wall", "fence", "hedge", "retaining_wall", "chain", "city_wall", "jersey_barrier"}
GATES = {"gate", "lift_gate", "swing_gate", "turnstile", "kissing_gate"}
COMMON_GATES = {"gate", "lift_gate", "swing_gate", "kissing_gate", "bollard", "cycle_barrier", "entrance"}
PUBLIC = {"yes", "designated", "permissive", "official"}
EPS = 1e-6
DIFFERENCE_AREA_LIMIT = 1e-5  # inherited independent ordered-overlay reporting precision


def denied(t):
    return t.get("foot", t.get("access")) in DENIED or t.get("locked") == "yes" or any(k.endswith(":conditional") and k.split(":")[0] in {"foot", "access", "oneway"} for k in t)


def old_restricted(t):
    return t.get("access") in DENIED or t.get("foot") in DENIED or any(k.endswith(":conditional") and k.split(":")[0] in {"foot", "access", "oneway"} for k in t)


def nonground(t):
    return t.get("highway") in {"steps", "elevator"} or any(t.get(k) not in FALSE for k in ("level", "layer", "bridge", "tunnel", "indoor", "repeat_on"))


def strict_gate_allowed(t):
    # Frozen Source gate recognition has the stricter ground/permission rule;
    # common guard apertures use COMMON_GATES plus pedestrian priority instead.
    return (t.get("barrier") in GATES and not old_restricted(t) and t.get("locked") != "yes" and
            all(t.get(k) in (None, "", "no") for k in ("bridge", "tunnel", "ford", "indoor", "covered")) and
            t.get("layer") in (None, "", "0") and t.get("level") in (None, "", "0") and
            (t.get("foot") in PUBLIC or t.get("access") in PUBLIC))


def semantic_permission(t):
    if any(k.endswith(":conditional") and k.split(":", 1)[0] in {"foot", "access", "oneway"} for k in t) or t.get("locked") == "yes":
        return False
    if "foot" in t:
        return t["foot"] in PUBLIC
    return t.get("access") not in DENIED


def area_role(t):
    return t.get("area") != "no" and (t.get("area") == "yes" or t.get("amenity") in {"parking", "parking_space"} or "landuse" in t or "leisure" in t or t.get("building") not in (None, "no") or t.get("natural") in {"water", "wetland"} or t.get("type") == "multipolygon")


def source_kind(kind, t):
    if t.get("building") not in (None, "no") or t.get("building:part") not in (None, "no"):
        return "BUILDING"
    if (t.get("natural") in {"water", "wetland"} or t.get("water") or t.get("waterway") == "riverbank" or
            t.get("landuse") in {"reservoir", "basin", "grass", "flowerbed", "flower_bed"} or t.get("leisure") == "flowerbed" or
            t.get("landcover") in {"grass", "flowerbed"} or t.get("barrier") in {"flower_bed", "planter"} or
            t.get("garden:type") == "flower_bed" or old_restricted(t) and (t.get("area") == "yes" or t.get("type") == "multipolygon")):
        return "AREA"
    if kind == "way" and t.get("barrier") in STRUCTURES | GATES:
        return "BARRIER"
    return None


def semantic_kind(kind, t):
    if kind != "AREA":
        return kind
    if t.get("natural") in {"water", "wetland"} or t.get("water") or t.get("waterway") == "riverbank" or t.get("landuse") in {"reservoir", "basin"}:
        return "WATER"
    if t.get("landuse") in {"flowerbed", "flower_bed"} or t.get("leisure") == "flowerbed" or t.get("landcover") == "flowerbed" or t.get("garden:type") == "flower_bed" or t.get("barrier") in {"flower_bed", "planter"}:
        return "FLOWERBED"
    if not semantic_permission(t):
        return "RESTRICTED_OR_UNRESOLVED_AREA"
    if t.get("landuse") == "grass" or t.get("landcover") == "grass":
        return "GRASS"
    return "PERMITTED_AREA_SUPPORT"


def raw_masks(raw):
    source = RawGeometry(raw)
    cache = {}
    def polygon(obj):
        key = (obj["type"], obj["id"])
        if key not in cache:
            cache[key] = source.area(obj)[0]
        return cache[key]
    hazards, common, area_masks = [], [], []
    represented = set()
    for (kind, number), obj in source.objects.items():
        if kind not in {"way", "relation"}:
            continue
        t = obj.get("tags", {})
        category = source_kind(kind, t)
        if category is None:
            continue
        if kind == "way":
            refs = obj.get("nodes", [])
        else:
            refs = [n for m in obj.get("members", []) if m["type"] == "way" and source.way(m["ref"]) is not None for n in source.way(m["ref"]).get("nodes", [])]
        coords = [source.xy[n] for n in refs if n in source.xy]
        if not coords:
            continue
        ident = f"{kind}/{number}"
        represented.add(ident)
        if category == "BARRIER" and kind == "way" and len(coords) == len(refs) and len(coords) > 1:
            g = LineString(coords)
        elif category != "BARRIER":
            g = polygon(obj)
            # The frozen adapter additionally insists that every original
            # member edge remains on the final boundary. Two complete outer
            # rings sharing an internal edge trigger its conservative UNKNOWN
            # extent, even though their independently assembled union is valid.
            if g is not None:
                members = [obj] if kind == "way" else [source.way(m["ref"]) for m in obj.get("members", []) if m["type"] == "way" and source.way(m["ref"]) is not None]
                original_lines = [LineString([source.xy[n] for n in w["nodes"]]) for w in members if len(w.get("nodes", [])) > 1 and all(n in source.xy for n in w["nodes"])]
                if any(line.difference(g.boundary.buffer(1e-7)).length > 1e-6 for line in original_lines):
                    g = None
        else:
            g = None
        if g is None:
            xs, ys = zip(*coords)
            g = box(min(xs), min(ys), max(xs), max(ys)).buffer(.01)
            category = "UNKNOWN"
        sem = semantic_kind(category, t)
        record = {"source_id": ident, "source_kind": category, "kind": sem, "geometry": g, "tags": t}
        hazards.append(record)
        if category != "BARRIER" and sem != "PERMITTED_AREA_SUPPORT":
            area_masks.append({**record, "geometry": g.buffer(.25, quad_segs=16), "buffer_m": .25})
        if sem != "PERMITTED_AREA_SUPPORT" or denied(t) or nonground(t):
            mask = g
            if mask.area <= EPS:
                openings = []
                if category == "BARRIER" and kind == "way":
                    for n in refs:
                        nt = source.objects.get(("node", n), {}).get("tags", {})
                        if nt.get("barrier") in COMMON_GATES and not denied(nt) and not nonground(nt):
                            openings.append(Point(source.xy[n]).buffer(.30))
                mask = g.buffer(.15).difference(unary_union(openings))
            common.append({**record, "geometry": mask})
    # Additional negative areas, linear restrictions and blocked support objects
    # are scanned from every raw object, independently of positive face IDs.
    for (kind, number), obj in source.objects.items():
        if kind not in {"way", "relation"}:
            continue
        t = obj.get("tags", {})
        refs = obj.get("nodes", [])
        closed = kind == "relation" and t.get("type") == "multipolygon" or len(refs) >= 4 and refs[0] == refs[-1]
        ident = f"{kind}/{number}"
        if denied(t) and closed and area_role(t):
            g = polygon(obj)
            if g is None:
                raise ValueError("UNRESOLVED_NEGATIVE_AREA:" + ident)
            common.append({"source_id": ident, "kind": "RAW_PERMISSION_AREA", "geometry": g, "tags": t})
            represented.add(ident)
        elif denied(t) and kind == "way" and ident not in represented and len(refs) > 1 and all(n in source.xy for n in refs):
            common.append({"source_id": ident, "kind": "RAW_RESTRICTED_LINEAR", "geometry": LineString([source.xy[n] for n in refs]).buffer(.15), "tags": t})
            represented.add(ident)
        face_or_support = (t.get("highway") == "pedestrian" and t.get("area") == "yes" or t.get("area:highway") in {"pedestrian", "footway", "path"} or
                           t.get("leisure") in {"park", "garden", "recreation_ground"} or t.get("surface") in {"paved", "paving_stones", "concrete", "asphalt"})
        if closed and face_or_support and ident not in represented and (denied(t) or nonground(t)):
            g = polygon(obj)
            if g is not None:
                common.append({"source_id": ident, "kind": "RAW_BLOCKED_SUPPORT", "geometry": g, "tags": t})
    for (kind, number), obj in source.objects.items():
        if kind != "node":
            continue
        t = obj.get("tags", {})
        if t.get("barrier") in STRUCTURES | GATES and not strict_gate_allowed(t):
            common.append({"source_id": "node/" + str(number), "kind": "RAW_BLOCKED_BARRIER_NODE", "geometry": Point(source.xy[number]).buffer(.15), "tags": t})
    return source, area_masks, common


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--scene", required=True)
    a = ap.parse_args()
    root = a.root.resolve()
    author_dir = root / "data/connectivity"
    author_path = author_dir / (a.scene + "_faces.json")
    common_path = author_dir / (a.scene + "_full_common.json")
    before_hash = digest(author_path)
    scene = next(s for s in read(root / "data/scene_manifest.json")["scenes"] if s["scene_id"] == a.scene)
    source_path = root / scene["source_path"]
    if digest(source_path) != scene["source_sha256"]:
        raise ValueError("SOURCE_CHANGED")
    tick = time.perf_counter()
    source, area_masks, common = raw_masks(read(source_path))
    a_index = STRtree([r["geometry"] for r in area_masks])
    c_index = STRtree([r["geometry"] for r in common])
    cov = coverage(scene["full_source_clip_bounds"])
    output = []
    admitted_rows = read(author_path)
    for face in admitted_rows:
        obj = source.objects[(face["source_id"].split("/")[0], int(face["source_id"].split("/")[1]))]
        P, audit, reason = source.area(obj)
        if P is None:
            raise ValueError("INDEPENDENT_SOURCE_UNRESOLVED:" + face["source_id"])
        masks = [area_masks[int(i)] for i in a_index.query(P, predicate="intersects")]
        cmasks = [common[int(i)] for i in c_index.query(P, predicate="intersects")]
        holes = [Polygon(r).buffer(.25, quad_segs=16) for p in ([P] if P.geom_type == "Polygon" else P.geoms) for r in p.interiors]
        expected = P.difference(unary_union([r["geometry"] for r in masks] + holes)).difference(unary_union([r["geometry"] for r in cmasks])).intersection(cov)
        actual_P, actual = shape(face["source_geometry"]), shape(face["omega"])
        p_diff, omega_diff = P.symmetric_difference(actual_P).area, expected.symmetric_difference(actual).area
        outside = actual.difference(P).area
        output.append({"source_id": face["source_id"], "author_status": face["status"], "independent_tag_eligible": explicit_face(obj.get("tags", {})) and permission_reason(obj.get("tags", {})) is None and ground_reason(obj.get("tags", {})) is None,
                       "source_P_symmetric_difference_m2": p_diff, "omega_symmetric_difference_m2": omega_diff, "outside_source_P_m2": outside,
                       "independent_P_area_m2": P.area, "independent_omega_area_m2": expected.area, "author_omega_area_m2": actual.area,
                       "independent_mask_sources": [{k: r[k] for k in ("source_id", "kind", "tags")} for r in masks],
                       "independent_common_sources": [{k: r[k] for k in ("source_id", "kind", "tags")} for r in cmasks],
                       "status": "MATCH_WITHIN_INHERITED_ORDERED_OVERLAY_PRECISION" if max(p_diff, omega_diff, outside) <= DIFFERENCE_AREA_LIMIT else "DIFFERENCE_REQUIRES_INSPECTION"})
    author_common = read(common_path)
    raw_blocked = unary_union([r["geometry"] for r in common]).intersection(cov)
    common_difference = raw_blocked.symmetric_difference(shape(author_common["blocked_geometry"])).area
    result = {"reviewer": "/root/connectivity_review", "scene_id": a.scene, "independent_reference": "RAW_OSM_EXACT_NODE_RING_AND_NEGATIVE_MASK_RECONSTRUCTION_NO_SRC_IMPORTS",
              "APP_solver_calls": 0, "external_requests": 0, "source_sha256": digest(source_path), "author_faces_sha256": before_hash, "author_full_common_sha256": digest(common_path),
              "author_faces_stable": digest(author_path) == before_hash, "raw_common_blocked_symmetric_difference_m2": common_difference,
              "inherited_ordered_overlay_area_reporting_precision_m2": DIFFERENCE_AREA_LIMIT, "elapsed_s": time.perf_counter() - tick, "rows": output,
              "status": "GEOMETRY_MATCH_FOR_REPORTED_SCOPE" if common_difference <= DIFFERENCE_AREA_LIMIT and all(r["status"].startswith("MATCH_") for r in output) else "DIFFERENCE_REQUIRES_INSPECTION",
              "limits": ["No route or interface graph correctness inferred from matching Omega", "No field validation", "P geometry remains unchanged; common and areal masks preserve distinct roles", "Roads are zero-width component constraints and are not extra areal masks"]}
    write(root / "audits" / ("independent_omega_" + a.scene + ".json"), result)
    print(json.dumps({k: result[k] for k in ("scene_id", "status", "raw_common_blocked_symmetric_difference_m2", "elapsed_s")}, ensure_ascii=False))
    print(json.dumps({r["source_id"]: r["omega_symmetric_difference_m2"] for r in output if r["omega_symmetric_difference_m2"] > DIFFERENCE_AREA_LIMIT}))


if __name__ == "__main__":
    main()
