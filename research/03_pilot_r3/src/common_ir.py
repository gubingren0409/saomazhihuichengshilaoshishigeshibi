"""Translate retained source artifacts into the R3 shared, read-only map contract.

The adapters do not construct graph edges, compute routes, or infer a door from
a line end. Input evidence is referenced rather than duplicated byte for byte.
"""
from collections import defaultdict
import math

VERSION = "0.1.0"
CRS = "EPSG:4326"
UNKNOWN = "UNKNOWN"
GRADES = {"VERIFIED_FIELD", "VERIFIED_OFFICIAL", "OSM_TAGGED",
          "POI_ENTRANCE", "PROXY_OR_UNCERTAIN", UNKNOWN}
FOOT_OK = {"yes", "designated", "permissive"}
FOOT_RESTRICTED = {"no", "private", "permit", "customers", "destination"}


def point(value):
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(type(x) in (float, int) and math.isfinite(x) for x in value)
            and -180 <= value[0] <= 180 and -90 <= value[1] <= 90):
        return list(value)
    return None


def bounds(value):
    if isinstance(value, (list, tuple)) and len(value) == 4:
        a, b = point(value[:2]), point(value[2:])
        if a and b and a[0] < b[0] and a[1] < b[1]:
            return [*a, *b]
    return None


def source(provider, evidence, refs):
    return {"provider": provider, "status": evidence, "artifacts": list(refs)}


def osm_identity(object_type, identifier):
    if identifier is None:
        return None
    identifier = str(identifier)
    if "/" not in identifier:
        identifier = f"{object_type}/{identifier}"
    return f"osm:{identifier}"


def access_state(tags):
    # An explicit mode tag takes precedence over the general access tag.
    value = tags.get("foot", tags.get("access"))
    if value in FOOT_OK:
        return "TAGGED_ALLOWED"
    if value in FOOT_RESTRICTED:
        return "TAGGED_RESTRICTED"
    return UNKNOWN


def way_points(row, nodes):
    coordinates = [nodes.get(ref) for ref in row.get("nodes", ())]
    if len(coordinates) < 2 or any(coord is None for coord in coordinates):
        return None
    return coordinates


def closed_ring(coords):
    return coords and len(coords) >= 4 and coords[0] == coords[-1]


def osm_geometry(row, nodes, ways, area):
    if row["type"] == "node":
        coordinate = nodes.get(row["id"])
        return {"type": "Point", "coordinates": coordinate} if coordinate else None
    if row["type"] == "way":
        coords = way_points(row, nodes)
        if not coords:
            return None
        if area:
            return {"type": "Polygon", "coordinates": [coords]} if closed_ring(coords) else None
        return {"type": "LineString", "coordinates": coords}
    if row["type"] != "relation" or row.get("tags", {}).get("type") != "multipolygon":
        return None
    # Preserve closed native rings, including holes. Do not infer how to join
    # incomplete ring members or assign holes across ambiguous multiple outers.
    rings = defaultdict(list)
    for member in row.get("members", ()):
        if member["type"] != "way" or member["role"] not in {"outer", "inner"}:
            return None
        coords = way_points(ways.get(member["ref"], {}), nodes)
        if not closed_ring(coords):
            return None
        rings[member["role"]].append(coords)
    if len(rings["outer"]) == 1:
        return {"type": "Polygon", "coordinates": rings["outer"] + rings["inner"]}
    if len(rings["outer"]) > 1 and not rings["inner"]:
        return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings["outer"]]}
    return None


def osm_features(snapshot, ref):
    rows = snapshot["elements"]
    nodes = {r["id"]: point([r.get("lon"), r.get("lat")]) for r in rows if r["type"] == "node"}
    ways = {r["id"]: r for r in rows if r["type"] == "way"}
    features = {"buildings": [], "pedestrian": [], "open_spaces": []}
    for row in rows:
        tags = row.get("tags", {})
        if not tags:
            continue
        building = tags.get("building") not in (None, "", "no")
        plaza = tags.get("area:highway") is not None or (
            tags.get("highway") in {"pedestrian", "footway"} and tags.get("area") == "yes")
        green = tags.get("leisure") in {"park", "garden", "pitch", "recreation_ground"} or (
            tags.get("landuse") in {"grass", "meadow", "village_green", "recreation_ground"}
            or tags.get("natural") == "grassland")
        feature_kinds = []
        if building:
            feature_kinds.append(("buildings", "BuildingFeature", tags["building"], row["type"] != "node"))
        if tags.get("highway") or tags.get("barrier") or tags.get("indoor") in {"corridor", "area"}:
            category = tags.get("highway") or tags.get("indoor") or "barrier"
            feature_kinds.append(("pedestrian", "PedestrianFeature", category, plaza or tags.get("area") == "yes"))
        if plaza or green:
            feature_kinds.append(("open_spaces", "OpenSpaceFeature", "tagged_pedestrian_area" if plaza else "tagged_green_space", row["type"] != "node"))
        for collection, kind, category, area in feature_kinds:
            geom = osm_geometry(row, nodes, ways, area)
            features[collection].append({
                "kind": kind, "id": osm_identity(row["type"], row["id"]),
                "category": category, "geometry": geom,
                "geometry_status": ("OBSERVED" if row["type"] == "node" else "RECOMPUTED") if geom else UNKNOWN,
                "access_state": access_state(tags),
                "source": source("OSM", "OBSERVED", [ref]),
                "native_fields": {key: row[key] for key in ("type", "id", "tags", "nodes", "members", "version") if key in row},
            })
    return features


def reference_grade(raw):
    value = str(raw or UNKNOWN)
    if value == "OSM_TAGGED_BUILDING_ENTRANCE_REFERENCE":
        return "OSM_TAGGED"
    if value == "SOUTH_FACADE_DIAGNOSTIC_POINT":
        return "PROXY_OR_UNCERTAIN"
    return value if value in GRADES else UNKNOWN


def entrance_references(scene, refs):
    target = point(scene.get("target"))
    candidates = scene.get("entrance_references") or []
    selected_id = scene.get("entry_native_id")
    target_grade = reference_grade(scene.get("target_role"))
    result = []
    for i, row in enumerate(candidates):
        native = row.get("native_id", row.get("node_id", row.get("id")))
        coordinate = point(row.get("coordinate", row.get("point", row.get("lonlat", row.get("wgs84")))))
        identifier = osm_identity("node", native)
        grade = reference_grade(row.get("grade", row.get("source_level", row.get("classification", row.get("role", "OSM_TAGGED" if identifier else UNKNOWN)))))
        result.append({
            "kind": "EntranceReference", "id": identifier or f"{scene['scene_id']}:entrance:{i}",
            "coordinate": coordinate, "grade": grade, "current_access": UNKNOWN,
            "selected_for_request": bool(target and coordinate == target and
                                         (not selected_id or identifier == osm_identity("node", selected_id)) and
                                         (target_grade == UNKNOWN or target_grade == grade)),
            "physical_validation": "FIELD" if grade == "VERIFIED_FIELD" else UNKNOWN,
            "source": source("FROZEN_SCENE", "OBSERVED", refs), "native_fields": row,
        })
    if target and not any(row["selected_for_request"] for row in result):
        grade = target_grade
        result.append({
            "kind": "EntranceReference", "id": osm_identity("node", selected_id) or f"{scene['scene_id']}:request-reference",
            "coordinate": target, "grade": grade, "current_access": UNKNOWN, "selected_for_request": True,
            "physical_validation": "FIELD" if grade == "VERIFIED_FIELD" else UNKNOWN,
            "source": source("FROZEN_SCENE", "OBSERVED", refs),
            "native_fields": {k:scene[k] for k in ("target_role","entry_scope","entry_native_id","institution_source") if k in scene},
        })
    return result


def snap(raw, provider, refs):
    raw = raw or {}
    coordinate = point(raw.get("position"))
    return {
        "coordinate": coordinate, "status": "OBSERVED" if coordinate else UNKNOWN,
        "distance_m": raw.get("distance_m"),
        "native_edge": osm_identity("way", raw.get("way_id")) if provider == "LOCAL_OSM" else None,
        "source": source(provider, "OBSERVED" if coordinate else UNKNOWN, refs),
        "native_fields": raw,
    }


def route_parts(value):
    if not value:
        return None
    t = value.get("type")
    if t == "FeatureCollection":
        parts = []
        for feature in value.get("features", []):
            geom = route_parts(feature)
            if geom:
                parts.extend(geom["coordinates"])
        return {"type": "MultiLineString", "coordinates": parts} if parts else None
    if t == "Feature":
        return route_parts(value.get("geometry"))
    if t == "LineString":
        return {"type": "MultiLineString", "coordinates": [value["coordinates"]]}
    if t == "MultiLineString":
        return value
    raise ValueError("UNEXPECTED_ROUTE_GEOMETRY")


def request(scene, provider, refs, engine, *, native=None, role="TARGET_REQUEST"):
    native = native or {}
    origin = point(native.get("requested_start", native.get("requested_start_wgs84", scene.get("start"))))
    target = point(native.get("requested_target", native.get("requested_target_wgs84", scene.get("target"))))
    return {
        "kind": "RouteRequest", "id": f"{scene['scene_id']}:{provider}:{role}",
        "role": role, "origin": origin, "target": target, "mode": "walk", "profile": engine,
        "status": "REQUEST_COORDINATES_AVAILABLE" if origin and target else "REQUEST_INPUT_MISSING",
        "source": source(provider, "OBSERVED", refs),
        "constraints": {"snap_limit_m": native.get("max_snap_m") if provider == "LOCAL_OSM" else None,
                        "snap_limit_status": "OBSERVED" if provider == "LOCAL_OSM" and native.get("max_snap_m") is not None else UNKNOWN},
    }


def route(scene, provider, record, geometry, refs, *, role="TARGET_REQUEST"):
    record = record or {}
    geom = route_parts(geometry)
    geo_m = record.get("geometry_length_m_wgs84", record.get("geometry_length_m"))
    metric = "WGS84_ELLIPSOID" if record.get("geometry_length_m_wgs84") is not None else record.get("geometry_length_metric", UNKNOWN)
    status = str(record.get("status", "NOT_RUN"))
    return {
        "kind": "RouteResult", "request_id": f"{scene['scene_id']}:{provider}:{role}",
        "role": role, "status": status, "failure_reason": record.get("failure_reason"),
        "geometry": geom, "geometry_status": "OBSERVED" if geom else UNKNOWN,
        "route_origin": point(record.get("route_start", record.get("route_start_wgs84"))),
        "route_end": point(record.get("route_end", record.get("route_endpoint_wgs84"))),
        "route_end_role": "RETURNED_ROUTE_VERTEX" if geom else UNKNOWN,
        "engine": record.get("engine") or record.get("source") or UNKNOWN,
        "distance": {"reported_m": record.get("provider_distance_m", record.get("length_m")),
                     "geometry_m": geo_m,
                     "geometry_metric": metric,
                     "duration_s": record.get("provider_duration_s")},
        "snap_origin": snap(record.get("snap_start"), provider, refs),
        "snap_target": snap(record.get("snap_end"), provider, refs),
        "arrival_at_verified_entrance": UNKNOWN,
        "source": source(provider, "OBSERVED" if record else UNKNOWN, refs),
        "native_fields": {k:v for k,v in record.items() if k not in {"geometry", "geojson"}},
    }


def view_union(views):
    valid = [bounds(v.get("bounds")) for v in views.values()]
    valid = [v for v in valid if v]
    if not valid:
        return None
    return [min(v[0] for v in valid), min(v[1] for v in valid),
            max(v[2] for v in valid), max(v[3] for v in valid)]


def branch(scene, provider, refs, *, snapshot_time=None, attribution=None, actual_views=None):
    views = scene.get("views", {})
    return {
        "schema_version": VERSION,
        "scene": {"kind": "MapScene", "scene_id": scene["scene_id"], "label": scene.get("label"),
                  "bounds": view_union(views), "crs": CRS, "coordinate_order": "longitude,latitude",
                  "timestamp": snapshot_time, "timestamp_status": "OBSERVED" if snapshot_time else UNKNOWN,
                  "attribution": attribution, "requested_views": views, "retained_views": actual_views,
                  "source": source(provider, "OBSERVED", refs)},
        "entrances": entrance_references(scene, refs),
        "features": {"buildings": [], "pedestrian": [], "open_spaces": []},
        "feature_availability": {"buildings": UNKNOWN, "pedestrian": UNKNOWN, "open_spaces": UNKNOWN},
        "route_requests": [], "route_results": [], "access_candidates": [],
        "access_candidates_availability": UNKNOWN,
        "topology_availability": UNKNOWN,
    }


def adapt_osm(scene, snapshot, local, refs, snapshot_ref, *, actual_views=None):
    local = local or {}
    snapshot = snapshot or {}
    osm_stamp = snapshot.get("osm3s", {}).get("timestamp_osm_base")
    result = branch(scene, "LOCAL_OSM", refs, snapshot_time=osm_stamp,
                    attribution=["© OpenStreetMap contributors", "ODbL-1.0"], actual_views=actual_views)
    if snapshot:
        result["features"] = osm_features(snapshot, snapshot_ref)
        result["feature_availability"] = {key: "OBSERVED_CLIP" for key in result["features"]}
        result["topology_availability"] = "NATIVE_MEMBERSHIP"
    record = local.get("route") or {"status": local.get("status", "NOT_RUN")}
    if snapshot and record.get("profile"):
        result["topology_availability"] = "NATIVE_MEMBERSHIP_AND_FROZEN_PROFILE"
    diagnostic = local.get("diagnostic") or {}
    for role, item in (("TARGET_REQUEST", record), ("APPROACH_DIAGNOSTIC", diagnostic)):
        if role == "APPROACH_DIAGNOSTIC" and not item:
            continue
        result["route_requests"].append(request(scene, "LOCAL_OSM", refs, item.get("profile", UNKNOWN), native=item, role=role))
        result["route_results"].append(route(scene, "LOCAL_OSM", item, item.get("geometry"), refs, role=role))
    nearest = snap(record.get("snap_end"), "LOCAL_OSM", refs)
    if nearest["coordinate"] is not None:
        result["access_candidates"].append({
            "kind": "AccessCandidate", "id": f"{scene['scene_id']}:LOCAL_OSM:target-snap",
            "coordinate": nearest["coordinate"], "role": "NEAREST_ELIGIBLE_NETWORK_POINT",
            "entrance_identity": UNKNOWN, "native_edge": nearest["native_edge"], "distance_to_request_target_m": nearest["distance_m"],
            "source": nearest["source"], "native_fields": nearest["native_fields"],
        })
        result["access_candidates_availability"] = "OBSERVED_CANDIDATE"
    return result


def adapt_geoapify(scene, hosted, retained_geometry, refs, *, actual_views=None):
    hosted = hosted or {}
    record = hosted.get("route") or {"status": hosted.get("status", "NOT_RUN")}
    result = branch(scene, "GEOAPIFY", refs, attribution=[
        "© OpenStreetMap contributors", "© OpenMapTiles", "Powered by Geoapify"],
        actual_views=actual_views)
    params = (record.get("receipt") or {}).get("parameters") or {}
    provider_profile = ";".join(f"{k}={params[k]}" for k in ("mode", "type") if params.get(k)) or UNKNOWN
    result["route_requests"].append(request(scene, "GEOAPIFY", refs, provider_profile, native=record))
    result["route_results"].append(route(scene, "GEOAPIFY", record, retained_geometry, refs))
    return result


def comparable_route_subset(local, hosted):
    a, b = local["scene"], hosted["scene"]
    req_a, req_b = local["route_requests"][0], hosted["route_requests"][0]
    if a["scene_id"] != b["scene_id"] or a["crs"] != b["crs"]:
        raise ValueError("DIFFERENT_SCENES_OR_COORDINATE_CONTRACTS")
    same = req_a["origin"] is not None and req_a["target"] is not None and all(
        req_a[key] == req_b[key] for key in ("origin", "target", "mode"))
    return {
        "scene_id": a["scene_id"], "same_request_coordinates_and_mode": same,
        "same_snapshot_or_engine": UNKNOWN,
        "views_share_requested_bounds": a["requested_views"] == b["requested_views"],
        "local_target_route_status": local["route_results"][0]["status"],
        "hosted_target_route_status": hosted["route_results"][0]["status"],
        "shared_fields": ["frozen_origin", "frozen_target", "route_geometry", "route_end", "route_status", "evidence"],
        "shared_native_graph": UNKNOWN,
        "graph_experiment_eligibility": "LOCAL_ONLY_UNTIL_EQUAL_INDEPENDENT_GRAPH_INPUT",
        "meaning": "Comparable geometry measurements and failure handling. Full graph inputs differ.",
    }


def validate(bundle):
    """Check spatial and identity invariants without a dependency or inference."""
    scene = bundle["scene"]
    if scene["crs"] != CRS or scene["coordinate_order"] != "longitude,latitude":
        raise ValueError("INVALID_COORDINATE_CONTRACT")
    if scene["bounds"] is not None and bounds(scene["bounds"]) is None:
        raise ValueError("INVALID_SCENE_BOUNDS")
    request_ids = {item["id"] for item in bundle["route_requests"]}
    if len(request_ids) != len(bundle["route_requests"]):
        raise ValueError("DUPLICATE_REQUEST_ID")
    for item in bundle["route_results"]:
        if item["request_id"] not in request_ids:
            raise ValueError("ORPHAN_ROUTE_RESULT")
        geom = item["geometry"]
        if geom is not None and (geom["type"] != "MultiLineString" or not geom["coordinates"] or any(
            len(line) < 2 or any(point(p) is None for p in line) for line in geom["coordinates"]
        )):
            raise ValueError("INVALID_ROUTE_GEOMETRY")
        if geom and item["route_end"] is not None and item["route_end"] != geom["coordinates"][-1][-1]:
            raise ValueError("ROUTE_END_NOT_LAST_SOURCE_VERTEX")
        if item["arrival_at_verified_entrance"] != UNKNOWN:
            raise ValueError("ADAPTER_CANNOT_VALIDATE_ARRIVAL")
    for item in bundle["entrances"]:
        if item["grade"] not in GRADES or item["current_access"] != UNKNOWN:
            raise ValueError("INVALID_ENTRANCE_EVIDENCE")
    for key, rows in bundle["features"].items():
        if rows and bundle["feature_availability"][key] == UNKNOWN:
            raise ValueError("FEATURES_WITH_UNKNOWN_SOURCE")
    if bundle["scene"]["source"]["provider"] == "GEOAPIFY":
        if any(bundle["features"].values()) or bundle["access_candidates"]:
            raise ValueError("HOSTED_API_DOES_NOT_SUPPLY_VECTOR_INVENTORY_OR_SNAP_CANDIDATES")
    return bundle
