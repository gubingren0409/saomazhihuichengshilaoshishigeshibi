"""Independent raw-source inventory; no src imports, graph building or solver calls.

Ring reconstruction uses exact source-node chain joining, independently of the
author's polygonize-based Source.area. No snapping, closing, hull or repair.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import argparse
import json
import time

from pyproj import Transformer
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, mapping
from shapely.ops import nearest_points, unary_union
from shapely import normalize

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
WALK = {"footway", "pedestrian", "path"}
DENIED = {"no", "private", "customers", "destination", "delivery", "permit", "restricted", "agricultural", "forestry"}
PUBLIC = {"yes", "public", "permissive", "designated", "official"}
FALSE = {None, "", "0", "no", "false"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def explicit_face(tags):
    return tags.get("area:highway") in WALK or tags.get("area") == "yes" and tags.get("highway") in WALK


def area_candidate(obj):
    tags = obj.get("tags", {})
    return (explicit_face(tags) or tags.get("type") == "multipolygon" or
            any(k in tags for k in ("area", "area:highway", "landuse", "leisure", "landcover", "natural", "building", "building:part", "water", "garden:type")))


def permission_reason(tags):
    if tags.get("foot", tags.get("access")) in DENIED or tags.get("locked") == "yes":
        return "RESTRICTED_OR_CONDITIONAL_AREA"
    if any(k in tags for k in ("foot:conditional", "access:conditional", "oneway:foot:conditional", "pedestrian:conditional")):
        return "RESTRICTED_OR_CONDITIONAL_AREA"
    if "pedestrian" in tags and tags["pedestrian"] not in PUBLIC:
        return "RESTRICTED_OR_CONDITIONAL_AREA"
    return None


def ground_reason(tags):
    if any(tags.get(k) not in FALSE for k in ("level", "layer", "bridge", "tunnel", "indoor", "repeat_on")) or tags.get("ford") not in {None, "no", "false", "0"}:
        return "NON_GROUND_OR_UNRESOLVED_LAYER"
    return None


def linear_tag_reason(tags):
    public = {"yes", "designated", "permissive", "official"}
    dedicated = {"footway", "pedestrian", "path", "steps"}
    shared = {"living_street", "residential", "unclassified", "service"}
    major = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
    optional = {"track", "cycleway", "bridleway", "corridor"}
    if tags.get("area") == "yes":
        return "AREA_BOUNDARY_NOT_NATIVE_LINEAR_WAY"
    if tags.get("indoor") not in (None, "no") or tags.get("ford") not in (None, "no"):
        return "FROZEN_NON_OUTDOOR_LINEAR_TAGS"
    if any(k in tags for k in ("access:conditional", "foot:conditional", "oneway:foot:conditional", "foot:forward:conditional", "foot:backward:conditional")):
        return "FROZEN_CONDITIONAL_LINEAR_TAGS"
    if "foot" in tags and tags["foot"] not in public or "foot" not in tags and tags.get("access") in DENIED:
        return "FROZEN_RESTRICTED_LINEAR_TAGS"
    highway = tags.get("highway")
    if highway in dedicated:
        return None
    if highway not in shared | major | optional:
        return "NO_FROZEN_WALK_AXIS_CLASS"
    if tags.get("foot") in public:
        return None
    sidewalk = {"yes", "both", "left", "right"}
    if highway in shared | major and (tags.get("sidewalk") in sidewalk or any(tags.get("sidewalk:" + side) in sidewalk for side in ("left", "right", "both"))):
        return None
    if highway in shared and tags.get("sidewalk") not in {"separate", "no"}:
        return None
    return "NO_FROZEN_WALK_AXIS_EVIDENCE"


class RawGeometry:
    def __init__(self, raw):
        self.objects = {(r["type"], r["id"]): r for r in raw["elements"]}
        self.xy = {ident: PROJECT(obj["lon"], obj["lat"]) for (kind, ident), obj in self.objects.items() if kind == "node"}

    def way(self, ident):
        return self.objects.get(("way", ident))

    def rings(self, ways):
        """Join only exact native endpoint IDs; require closed unambiguous chains."""
        pending = [list(w["nodes"]) for w in ways]
        if any(len(nodes) < 2 for nodes in pending):
            raise ValueError("SHORT_MEMBER_WAY")
        rings = []
        while pending:
            chain = pending.pop(0)
            while chain[0] != chain[-1]:
                choices = [(i, False) for i, ns in enumerate(pending) if ns[0] == chain[-1]]
                choices += [(i, True) for i, ns in enumerate(pending) if ns[-1] == chain[-1]]
                if len(choices) != 1:
                    raise ValueError("OPEN_OR_BRANCHING_RING")
                index, reverse = choices[0]
                part = pending.pop(index)
                if reverse:
                    part.reverse()
                chain += part[1:]
            if len(chain) < 4:
                raise ValueError("SHORT_CLOSED_RING")
            rings.append(chain)
        return rings

    def area(self, obj):
        audit = {"missing_way_ids": [], "missing_node_ids": [], "unsupported_members": [], "duplicate_member_refs": [], "outer_rings": [], "inner_rings": []}
        if obj["type"] == "way":
            groups = {"outer": [obj], "inner": []}
        else:
            groups = {"outer": [], "inner": []}
            counts = Counter((m["type"], m["ref"], m.get("role") or "outer") for m in obj.get("members", []))
            audit["duplicate_member_refs"] = [list(k) for k, count in counts.items() if count > 1]
            for member in obj.get("members", []):
                role = member.get("role") or "outer"
                if member["type"] != "way" or role not in groups:
                    audit["unsupported_members"].append(member)
                elif self.way(member["ref"]) is None:
                    audit["missing_way_ids"].append(member["ref"])
                else:
                    groups[role].append(self.way(member["ref"]))
        audit["missing_node_ids"] = sorted({n for ws in groups.values() for w in ws for n in w.get("nodes", []) if n not in self.xy})
        if audit["missing_way_ids"] or audit["missing_node_ids"] or audit["unsupported_members"] or audit["duplicate_member_refs"]:
            return None, audit, "INCOMPLETE_OR_UNSUPPORTED_SOURCE_MEMBERS"
        try:
            for role, ways in groups.items():
                audit[role + "_rings"] = self.rings(ways)
            outers = [Polygon([self.xy[n] for n in ring]) for ring in audit["outer_rings"]]
            inners = [Polygon([self.xy[n] for n in ring]) for ring in audit["inner_rings"]]
            if not outers or any(p.is_empty or not p.is_valid for p in outers + inners):
                return None, audit, "INVALID_RING_GEOMETRY"
            outer, inner = unary_union(outers), unary_union(inners)
            if not inner.is_empty and not outer.covers(inner):
                return None, audit, "INNER_OUTSIDE_OUTER"
            result = outer.difference(inner)
            if result.is_empty or not result.is_valid or result.geom_type not in {"Polygon", "MultiPolygon"}:
                return None, audit, "INVALID_POLYGON_GEOMETRY"
            return result, audit, None
        except ValueError as error:
            return None, audit, str(error)


def coverage(bounds):
    w, s, e, n = bounds
    corners = [(w, s), (e, s), (e, n), (w, n)]
    return Polygon([PROJECT(a[0] + (b[0] - a[0]) * i / 32, a[1] + (b[1] - a[1]) * i / 32)
                    for a, b in zip(corners, corners[1:] + corners[:1]) for i in range(32)])


def relation(a, b):
    dist = a.distance(b)
    hit = a.intersection(b)
    boundary = a.boundary.intersection(b.boundary) if b.geom_type in {"Polygon", "MultiPolygon"} else a.boundary.intersection(b)
    if hit.is_empty:
        kind = "POSITIVE_GAP"
    elif hit.area > 1e-6:
        kind = "AREA_OVERLAP"
    elif hit.length > 1e-6:
        kind = "POSITIVE_LENGTH_CONTACT_OR_COVERAGE"
    else:
        kind = "POINT_ONLY_CONTACT"
    return {"P_relation": kind, "P_distance_m": dist, "P_intersection_length_m": hit.length,
            "P_intersection_area_m2": hit.area, "P_boundary_contact_length_m": boundary.length,
            "nearest_xy": [list(p.coords)[0] for p in nearest_points(a, b)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    started = time.perf_counter()
    manifest = read(root / "data/scene_manifest.json")
    old = {r["scene_id"]: set(r["area_ids"]) for r in read(root / "data/face_selection_lock.json")["scenes"]}
    inventories, relations, scenes, geometries, all_lines = [], [], [], [], []
    for scene in manifest["scenes"]:
        sid = scene["scene_id"]
        path = root / scene["source_path"]
        actual_hash = digest(path)
        if actual_hash != scene["source_sha256"]:
            raise ValueError("SOURCE_HASH_CHANGED:" + sid)
        raw = read(path)
        data = RawGeometry(raw)
        cov = coverage(scene["full_source_clip_bounds"])
        admitted, line_rows = [], []
        counts = Counter()
        relation_members = defaultdict(list)
        for (kind, number), obj in data.objects.items():
            if kind == "relation":
                for member in obj.get("members", []):
                    if member["type"] == "way":
                        relation_members[member["ref"]].append({"relation_id": "relation/" + str(number), "role": member.get("role")})
        for (kind, number), obj in sorted(data.objects.items()):
            if kind not in {"way", "relation"} or not area_candidate(obj):
                continue
            ident = f"{kind}/{number}"
            tags = obj.get("tags", {})
            geom, rings, geometry_reason = data.area(obj)
            why = None
            if not explicit_face(tags):
                why = "SOURCE_NOT_EXPLICIT_PEDESTRIAN_AREA"
            else:
                why = permission_reason(tags) or ground_reason(tags)
                if why is None and geom is None:
                    why = "UNRESOLVED_SOURCE_AREA_GEOMETRY"
                if why is None and geom.difference(cov).area > 1e-6:
                    why = "INCOMPLETE_SOURCE_COVERAGE"
            row = {"scene_id": sid, "source_id": ident, "version": obj.get("version"), "tags": tags,
                   "members": obj.get("members", []), "native_nodes": obj.get("nodes", []), "ring_audit": rings,
                   "explicit_walk_area": explicit_face(tags), "status": why or "ADMITTED", "geometry_reason": geometry_reason,
                   "source_sha256": actual_hash, "legacy_selected": ident in old[sid],
                   "source_relation_memberships": relation_members.get(number, []) if kind == "way" else [],
                   "source_area_m2": geom.area if geom is not None else None,
                   "P_bounds_m": list(geom.bounds) if geom is not None else None,
                   "P_holes": sum(len(p.interiors) for p in ([geom] if geom.geom_type == "Polygon" else geom.geoms)) if geom is not None else None,
                   "P_geometry_sha256": sha256(normalize(geom).wkb).hexdigest() if geom is not None else None}
            inventories.append(row)
            counts[row["status"]] += 1
            if why is None:
                admitted.append((row, geom))
                geometries.append({"type": "Feature", "properties": {k: row[k] for k in ("scene_id", "source_id", "version", "tags", "source_sha256")}, "geometry": mapping(geom)})
        for (kind, number), obj in sorted(data.objects.items()):
            tags = obj.get("tags", {})
            if kind != "way":
                continue
            # Broad source candidates, with permissions/ground recorded rather
            # than silently treating nearby restricted structures as interfaces.
            if not tags.get("highway"):
                continue
            ns = obj.get("nodes", [])
            if len(ns) < 2 or any(n not in data.xy for n in ns):
                continue
            line = LineString([data.xy[n] for n in ns])
            lrow = {"source_id": f"way/{number}", "version": obj.get("version"), "tags": tags,
                    "permission_reason": permission_reason(tags), "ground_reason": "NON_GROUND_OR_UNRESOLVED_LAYER" if tags.get("highway") in {"steps", "elevator"} else ground_reason(tags),
                    "frozen_linear_tag_reason": linear_tag_reason(tags), "scene_id": sid,
                    "native_nodes": ns, "length_m": line.length, "source_sha256": actual_hash}
            if tags.get("area") != "yes":
                line_rows.append((lrow, line))
            all_lines.append(lrow)
        duplicates = []
        for i, (a, ga) in enumerate(admitted):
            anodes = {n for key in ("outer_rings", "inner_rings") for ring in a["ring_audit"][key] for n in ring}
            for b, gb in admitted[i + 1:]:
                if ga.equals(gb):
                    duplicates.append([a["source_id"], b["source_id"]])
                if ga.distance(gb) <= 10:
                    bnodes = {n for key in ("outer_rings", "inner_rings") for ring in b["ring_audit"][key] for n in ring}
                    relations.append({"scene_id": sid, "pair_type": "FACE_FACE", "a": a["source_id"], "b": b["source_id"],
                                      "a_tags": a["tags"], "b_tags": b["tags"], "shared_node_ids": sorted(anodes & bnodes), **relation(ga, gb)})
            for b, gb in line_rows:
                if ga.distance(gb) <= 10:
                    hit = ga.intersection(gb)
                    relations.append({"scene_id": sid, "pair_type": "FACE_LINE", "a": a["source_id"], "b": b["source_id"],
                                      "a_tags": a["tags"], "b_tags": b["tags"], "b_permission_reason": b["permission_reason"], "b_ground_reason": b["ground_reason"],
                                      "b_frozen_linear_tag_reason": b["frozen_linear_tag_reason"],
                                      "shared_node_ids": sorted(anodes & set(b["native_nodes"])), "line_P_covered_fraction": hit.length / gb.length if gb.length else 0,
                                      "whole_line_native_nodes": b["native_nodes"], **relation(ga, gb)})
        ids = {row["source_id"] for row, _ in admitted}
        scenes.append({"scene_id": sid, "source_sha256": actual_hash, "raw_bounds_wsen": raw.get("bounds_wsen"),
                       "manifest_bounds_wsen": scene["full_source_clip_bounds"], "raw_type_counts": dict(Counter(k for k, _ in data.objects)),
                       "area_candidate_count": sum(counts.values()), "admission_counts": dict(counts), "admitted_ids": sorted(ids),
                       "old_selected_ids": sorted(old[sid]), "newly_qualified_ids": sorted(ids - old[sid]), "old_selected_not_admitted": sorted(old[sid] - ids),
                       "exact_geometry_duplicate_groups": duplicates, "broad_walk_line_count": len(line_rows)})
    header = {"reviewer": "/root/connectivity_review", "independent_reference": "RAW_OSM_EXACT_NODE_CHAIN_RING_CONSTRUCTION_NO_AUTHOR_CLASSIFICATION_IMPORTS",
              "crs": "EPSG:32651", "APP_solver_calls": 0, "external_requests": 0, "scenes": scenes,
              "elapsed_s": time.perf_counter() - started, "scope": "Source P and broad source-line relations only; no claim of Omega legality or routing admission yet",
              "limits": ["Source geometry is not field truth", "Broad line set deliberately includes blocked/non-ground lines for rejection review", "No object is snapped, repaired, closed or inferred", "No screenshot request metadata; SCREENSHOT_REQUEST_UNBOUND", "Historical user observation remains PENDING_USER_OBSERVATION"]}
    out = root / "audits"
    write(out / "independent_source_inventory_summary.json", header)
    write(out / "independent_source_inventory.json", inventories)
    write(out / "independent_source_P_relations.json", relations)
    write(out / "independent_source_lines.json", all_lines)
    write(out / "independent_source_admitted_P.geojson", {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:32651"}}, "features": geometries})
    print(json.dumps(header, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
