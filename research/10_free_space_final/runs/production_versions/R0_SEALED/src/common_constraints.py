"""Shared geometry/policy constraints; contains no reference or query reader.

The extra road geometry is a zero-width no-new-crossing policy, not a measured
carriageway polygon. Background lawn remains a policy restriction on *new*
free-space edges; original lawful graph lines are checked separately.
"""
from __future__ import annotations

from hashlib import sha256
import json

from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, Point, mapping, shape
from shapely.ops import unary_union

EPS = 1e-6
DENIED = {"no", "private", "customers", "destination", "delivery", "permit",
          "restricted", "agricultural", "forestry"}
BACKGROUND = {"GRASS", "BACKGROUND_GRASS", "FLOWERBED", "MEADOW"}
FACES = {"PEDESTRIAN_AREA", "WALKABLE_AREA", "NATIVE_WALKABLE_AREA"}


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()


def denied(tags):
    return (tags.get("foot", tags.get("access")) in DENIED or tags.get("locked") == "yes"
            or any(k in tags for k in ("foot:conditional", "access:conditional",
                                       "oneway:foot:conditional")))


def explicit_non_ground(tags):
    return any(tags.get(k) not in (None, "", "0", "no", "false")
               for k in ("level", "layer", "bridge", "tunnel", "indoor", "repeat_on"))


def geom(value):
    return value if hasattr(value, "geom_type") else make_valid(shape(value))


def union(items):
    return unary_union(list(items))


def build_contract(observed, guards, cfg, domain=None):
    """Pure same-input extraction. ``domain`` is the byte-frozen legacy 30m D.

    Only a successfully parsed source clip footprint establishes map coverage;
    it does not assert that all real obstacles have been mapped.
    """
    if observed.get("crs") != "EPSG:32651" or guards.get("crs") != "EPSG:32651":
        raise ValueError("Unconfirmed constraint CRS")
    domain = geom(domain) if domain is not None else Point(
        observed["domain"]["anchor_xy"]).buffer(cfg["domain_radius_m"], quad_segs=32)
    coverage = geom(guards["coverage_geometry"]) if guards.get("source_parse_status") == "PARSED" else GeometryCollection()
    valid = domain.intersection(coverage)
    physical, background, native, constraints = [], [], [], []
    gate_by_id = guards.get("barrier_gates", {})
    clearance = cfg.get("hard_line_clearance_m", .15)
    for layer, rows in observed["context"].items():
        for row in rows:
            tags, kind = row.get("tags", {}), row.get("kind")
            g = geom(row["geometry"])
            if g.is_empty:
                continue
            block = layer == "hard" or denied(tags) or explicit_non_ground(tags) or kind in BACKGROUND
            if block:
                policy = kind in BACKGROUND and not denied(tags)
                category = "BACKGROUND_NO_NEW_SHORTCUT_POLICY" if policy else "MAPPED_HARD_OR_ACCESS_LAYER_RESTRICTION"
                gates = gate_by_id.get(row["id"], row.get("gates", []))
                original = g
                if g.area <= EPS:
                    g = g.buffer(clearance)
                    opening = union(Point(x["xy"]).buffer(2*clearance) for x in gates if x.get("allowed"))
                    if not opening.is_empty:
                        g = g.difference(opening)
                (background if policy else physical).append(g)
                constraints.append({"constraint_id": f"context/{row['id']}/{layer}",
                    "source_id": row["id"], "kind": kind, "tags": tags,
                    "geometry": mapping(g), "source_geometry": mapping(original),
                    "restriction_role": category, "policy_only": policy,
                    "buffer_m": clearance if original.area <= EPS else 0,
                    "gates": gates, "exception": "VALID_NATIVE_LINE_ONLY_FOR_BACKGROUND; EXPLICIT_BRIDGE_TUNNEL_FOR_HARD_CONFLICT"})
            elif kind in FACES or tags.get("highway") == "pedestrian" or tags.get("area:highway") in {"footway", "pedestrian", "path", "steps", "corridor", "living_street"}:
                if g.area > EPS:
                    native.append(g)
    p, b = union(physical), union(background)
    blocked = p.union(b).intersection(domain)
    native_geometry = union(native).intersection(valid).difference(blocked)
    roads = guards.get("road_centerlines", [])
    for row in roads:
        constraints.append({"constraint_id": f"road/{row['source_id']}", **row,
            "restriction_role": "NO_NEW_FREE_CROSSING_ZERO_WIDTH_POLICY",
            "policy_only": True, "buffer_m": 0,
            "exception": "UNCHANGED_NATIVE_GRAPH_EDGE_OR_EXACT_SHARED_SOURCE_NODE"})
    result = {"contract_version": "COMMON_GUARDS_V1", "crs": observed["crs"],
        "domain": mapping(domain), "valid_geometry": mapping(valid),
        "blocked_geometry": mapping(blocked), "physical_geometry": mapping(p.intersection(domain)),
        "background_geometry": mapping(b.intersection(domain)),
        "native_geometry": mapping(native_geometry), "road_centerlines": roads,
        "constraints": constraints, "coverage_geometry": mapping(coverage),
        "coverage_status": guards.get("source_parse_status", "NO_DATA"),
        "coverage_semantics": "SOURCE_FILE_ACQUIRED_AND_GEOMETRY_PARSEABLE_NOT_COMPLETE_REAL_WORLD_SURVEY",
        "source_sha256": guards.get("source_sha256"),
        "guard_sha256": digest(guards),
        "road_policy": "ZERO_WIDTH_NO_NEW_FREE_CROSSING; NO_MEASURED_ROAD_WIDTH",
        "native_road_access_points": guards.get("native_road_access_points", []),
        "tolerance_m": EPS}
    result["sha256"] = digest(result)
    return result


def parsed_contract(contract):
    """Shapely cache is kept out of the serialized/hash contract."""
    return {"contract": contract,
        **{key: geom(contract[key]) for key in ("domain", "valid_geometry", "blocked_geometry",
                    "physical_geometry", "background_geometry", "native_geometry")},
        "roads": [(row, geom(row["geometry"])) for row in contract.get("road_centerlines", [])],
        "access_points": [Point(x["xy"]) for x in contract.get("native_road_access_points", [])]}


def edge_conflicts(line, contract, native=False, tags=None):
    """Whole segment constraints; native policy exceptions never open an area.

    Existing native bridge/tunnel structures keep their original graph direction
    and identity. New free links may not use their existence to bridge levels.
    Endpoint-only touching of a building boundary is allowed (original door).
    """
    p = contract if "contract" in contract else parsed_contract(contract)
    tags = tags or {}
    line = geom(line)
    result = []
    if denied(tags):
        result.append("EXPLICIT_ACCESS_OR_CONDITIONAL_RESTRICTION")
    if not native and explicit_non_ground(tags):
        result.append("EXPLICIT_NON_GROUND_FREE_INTERFACE")
    if not native and line.difference(p["valid_geometry"]).length > EPS:
        result.append("OUTSIDE_LOCAL_VALID_DOMAIN")
    # The physical mask retains original full hard geometries, so a line merely
    # running along a wall boundary is also conservatively checked.
    physical = p["physical_geometry"]
    interior = physical.buffer(-1e-7) if physical.area > EPS else physical
    if line.intersection(interior).length > EPS:
        structure = tags.get("bridge") not in (None, "no", "false", "0") or tags.get("tunnel") not in (None, "no", "false", "0")
        if not (native and structure):
            result.append("MAPPED_HARD_INTERIOR_CONFLICT")
    if not native and line.intersection(p["background_geometry"]).length > EPS:
        result.append("BACKGROUND_NO_NEW_SHORTCUT_POLICY")
    if not native:
        for row, road in p["roads"]:
            hit = line.intersection(road)
            if hit.is_empty:
                continue
            # Source-shared access points permit only endpoint attachment. An
            # entire new cross-road segment is never licensed by nearby points.
            contacts = ([hit] if hit.geom_type == "Point" else
                        list(hit.geoms) if hit.geom_type == "MultiPoint" else [])
            ends = [Point(line.coords[0]), Point(line.coords[-1])]
            if contacts and all(any(q.distance(e) <= EPS for e in ends) and
                                any(q.distance(a) <= EPS for a in p["access_points"]) for q in contacts):
                continue
            result.append("NO_NEW_FREE_ROAD_CROSSING:" + row["source_id"])
    return sorted(set(result))
