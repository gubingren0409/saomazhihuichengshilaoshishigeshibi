"""Replay the frozen six-case network, then apply the R4 evidence gates."""
import csv
from hashlib import file_digest
import json
from pathlib import Path

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import nearest_points, polygonize, transform, unary_union

from .core import LinearEvidence, Obstacles, add_supported_edges, capability, distance, entrance_route, graph_stats, select_entrance
from .frozen_r1 import local_route as frozen

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
INVERSE = Transformer.from_crs(32651, 4326, always_xy=True).transform
LINE_HIGHWAY = {"footway", "pedestrian", "path", "steps"}
LEVEL_TAGS = {"bridge", "tunnel", "ford", "indoor", "covered"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path, payload):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def hash_file(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def feature(kind, geometry, **props):
    return {"type": "Feature", "geometry": geometry, "properties": {"kind": kind, **props}}


def coord(node):
    return node["lon"], node["lat"]


def point(coords):
    return {"type": "Point", "coordinates": coords}


def base_record(route):
    if isinstance(route, dict) and "route" in route and isinstance(route["route"], dict):
        return route["route"]
    return route


def geometry_in(document):
    if not isinstance(document, dict):
        return None
    if document.get("type") == "FeatureCollection":
        return next((f["geometry"] for f in document.get("features", []) if f.get("geometry")), None)
    if document.get("type") == "Feature":
        return document.get("geometry")
    return document.get("geometry")


def ends(geom):
    parts = geom["coordinates"]
    if geom["type"] == "MultiLineString":
        return parts[0][0], parts[-1][-1]
    return parts[0], parts[-1]


def reference_id(ref):
    return int(ref.rsplit("/", 1)[-1])


def allowed_ground(tags):
    if frozen.CONDITIONAL.intersection(tags) or ("access" in tags and tags["access"] not in frozen.PUBLIC) or (
        "foot" in tags and tags["foot"] not in frozen.PUBLIC
    ):
        return "RESTRICTED_OR_CONDITIONAL_WALK_ACCESS"
    if (any(tags.get(key) not in (None, "no") for key in LEVEL_TAGS)
            or tags.get("layer", "0") != "0" or tags.get("level", "0") != "0"):
        return "NON_GROUND_OR_UNRESOLVED_LAYER"
    return None


def polygon_for(obj, ways, projected, kind):
    def way_coords(ids):
        return [projected[k] for k in ids] if len(ids) >= 2 and all(k in projected for k in ids) else None

    if kind == "way":
        coords = way_coords(obj["nodes"])
        if coords is None or len(coords) < 4 or coords[0] != coords[-1]:
            return None
        geometry = Polygon(coords)
    else:
        rings = {"outer": [], "inner": []}
        for member in obj["members"]:
            role = member["role"] or "outer"
            if member["type"] != "way" or role not in rings or member["ref"] not in ways:
                return None
            coords = way_coords(ways[member["ref"]]["nodes"])
            if coords is None:
                return None
            rings[role].append(LineString(coords))
        outer = unary_union(list(polygonize(rings["outer"])))
        inner = unary_union(list(polygonize(rings["inner"])))
        if outer.is_empty or (rings["inner"] and inner.is_empty) or (
            not inner.is_empty and not outer.covers(inner)
        ):
            return None
        # Require all declared ring pieces to participate in the reconstructed boundaries.
        for role, polygons in (("outer", outer), ("inner", inner)):
            if any(line.difference(polygons.boundary.buffer(1e-7)).length > 1e-6 for line in rings[role]):
                return None
        geometry = outer.difference(inner)
    return geometry if not geometry.is_empty and geometry.is_valid and geometry.geom_type in {"Polygon", "MultiPolygon"} else None


def shells(polygon):
    parts = [polygon] if polygon.geom_type == "Polygon" else polygon.geoms
    return [part.exterior for part in parts]


def native_inputs(data, focus_ids):
    nodes = {r["id"]: r for r in data["elements"] if r["type"] == "node"}
    ways = {r["id"]: r for r in data["elements"] if r["type"] == "way"}
    relations = {r["id"]: r for r in data["elements"] if r["type"] == "relation"}
    projected = {k: PROJECT(*coord(v)) for k, v in nodes.items()}
    spaces = []
    missing_spaces = []
    perimeter_nodes = {}
    for native_id in focus_ids:
        kind, k = native_id.split("/")
        obj = (ways if kind == "way" else relations).get(int(k))
        geometry = polygon_for(obj, ways, projected, kind) if obj else None
        if geometry is None:
            missing_spaces.append(native_id)
        else:
            spaces.append((native_id, geometry, allowed_ground(obj.get("tags", {}))))
            outer_ways = [obj] if kind == "way" else [ways[m["ref"]] for m in obj["members"] if m["role"] in ("", "outer")]
            perimeter_nodes[native_id] = {n for w in outer_ways for n in w["nodes"]}
    obstacles = []
    unresolved = []
    barriers = {"fence", "wall", "hedge", "retaining_wall", "gate", "lift_gate", "turnstile", "block"}
    for kind, objects in (("way", ways), ("relation", relations)):
        for k, obj in objects.items():
            tags = obj.get("tags", {})
            name = f"{kind}/{k}"
            if kind == "way" and tags.get("barrier") in barriers:
                if len(obj["nodes"]) >= 2 and all(n in projected for n in obj["nodes"]):
                    obstacles.append((name, "FENCE_WALL", LineString([projected[n] for n in obj["nodes"]])))
                else:
                    unresolved.append(name)
            area = None
            if tags.get("building") not in (None, "no"):
                area = "BUILDING"
            elif (tags.get("natural") in {"water", "wetland"} or tags.get("water") or tags.get("waterway") == "riverbank"
                  or tags.get("landuse") in {"reservoir", "basin", "grass", "flowerbed", "flower_bed"}
                  or tags.get("leisure") == "flowerbed" or tags.get("landcover") in {"grass", "flowerbed"}
                  or tags.get("barrier") in {"flower_bed", "planter"} or tags.get("garden:type") == "flower_bed"):
                area = "RESTRICTED_SURFACE"
            if area is not None:
                poly = polygon_for(obj, ways, projected, kind)
                if poly is not None:
                    obstacles.append((name, area, poly))
                else:
                    unresolved.append(name)
    for k, obj in nodes.items():
        tags = obj.get("tags", {})
        if tags.get("barrier") in barriers and not (tags.get("foot") in frozen.PUBLIC and frozen._allowed_node(tags)):
            obstacles.append((f"node/{k}", "RESTRICTED_NODE", Point(projected[k])))
    return nodes, ways, projected, spaces, perimeter_nodes, missing_spaces, obstacles, unresolved


def explicit_walk(tags):
    return tags.get("highway") in LINE_HIGHWAY or (
        tags.get("highway") in frozen.OPTIONAL and tags.get("foot") in frozen.PUBLIC
    )


def to_lines(data, nodes, ways, projected, space_polygons):
    vicinity = unary_union(space_polygons).buffer(1)
    if vicinity.is_empty:
        return []
    limit = data.get("bounds_wsen")
    records = []
    for k, way in sorted(ways.items()):
        tags = way.get("tags", {})
        if not explicit_walk(tags) or tags.get("area") == "yes":
            continue
        directions = frozen._directions(tags)
        blocked_way = allowed_ground(tags)
        for i, (a, b) in enumerate(zip(way["nodes"], way["nodes"][1:])):
            if a == b or a not in nodes or b not in nodes or projected[a] == projected[b]:
                continue
            p, q = coord(nodes[a]), coord(nodes[b])
            if limit and any(not (limit[0] <= lon <= limit[2] and limit[1] <= lat <= limit[3]) for lon, lat in (p, q)):
                continue
            geom = LineString([projected[a], projected[b]])
            if not geom.intersects(vicinity):
                continue
            blocked = blocked_way
            if not directions:
                blocked = blocked or "NO_VERIFIED_WALK_DIRECTION"
            if not all(frozen._allowed_node(nodes[n].get("tags", {})) for n in (a, b)):
                blocked = blocked or "NATIVE_BARRIER_OR_ACCESS"
            records.append(LinearEvidence(f"way/{k}", i, (a, "0", "0"), (b, "0", "0"),
                                          p, q, directions, tags, geom, blocked))
    return records


def boundary_objects(spaces, perimeter_nodes, lines, segments, projected, graph, start, tolerance):
    rows, features = [], []
    by_node = {}
    for s in segments:
        if s.evidence not in {"MAPPED_PEDESTRIAN_WAY", "EXPLICIT_FOOT_ON_WAY_AXIS"}:
            continue
        for k in (s.a, s.b):
            if k[1:] == ("0", "0"):
                by_node.setdefault(k[0], set()).add(f"way/{s.way}")
    reachable = nx.descendants(graph, start) | {start} if start in graph else set()
    for name, polygon, restricted in spaces:
        perimeter = unary_union(shells(polygon))
        features.append(feature("open_space", mapping(transform(INVERSE, polygon)), native_ids=[name],
                                status="OBSERVED", evidence="NATIVE_AREA_GEOMETRY", reason=restricted,
                                variant="ALL", area_m2=polygon.area))
        contacts = {}
        for node_id, way_ids in sorted(by_node.items()):
            p = Point(projected[node_id])
            if perimeter.distance(p) > tolerance:
                continue
            # A coordinate-only point is retained as a diagnostic; it has no authority to add topology.
            actual_contact = node_id in perimeter_nodes[name] and perimeter.distance(p) <= 1e-6
            can_reach = (node_id, "0", "0") in reachable
            props = {"native_ids": [name, f"node/{node_id}", *sorted(way_ids)], "space_id": name,
                     "variant": "ALL", "status": "OBSERVED" if actual_contact else "PROPOSED",
                     "evidence": "B0_NATIVE_NODE_ON_PERIMETER" if actual_contact else "GEOMETRIC_PROXIMITY_ONLY",
                     "reason": "B0_ORIGIN_REACHABLE" if can_reach else "B0_ORIGIN_NOT_CONNECTED",
                     "distance_m": perimeter.distance(p), "reachable_from_start": can_reach}
            rows.append(props)
            features.append(feature("access_candidate", point(INVERSE(p.x, p.y)), **props))
            contacts[(round(p.x, 3), round(p.y, 3))] = props
        for line in lines:
            separation = line.geometry_m.distance(perimeter)
            if separation > tolerance:
                continue
            hit = line.geometry_m.intersection(perimeter)
            if hit.geom_type == "Point" and not hit.is_empty:
                contact = hit
            elif hit.is_empty:
                contact, _ = nearest_points(line.geometry_m, perimeter)
            else:
                continue
            key = round(contact.x, 3), round(contact.y, 3)
            if key in contacts:
                continue
            props = {"native_ids": [name, line.native_id], "space_id": name, "variant": "ALL",
                     "status": "PROPOSED", "evidence": "GEOMETRIC_INTERSECTION_ONLY" if separation <= 1e-6 else "GEOMETRIC_PROXIMITY_ONLY",
                     "reason": "NATIVE_SHARED_TOPOLOGY_UNVERIFIED", "distance_m": separation,
                     "reachable_from_start": None}
            rows.append(props)
            contacts[key] = props
            features.append(feature("access_candidate", point(INVERSE(contact.x, contact.y)), **props))
        for ring_no, ring in enumerate(shells(polygon)):
            for n, (a, b) in enumerate(zip(ring.coords, list(ring.coords)[1:])):
                line = LineString([a, b])
                if line.length <= 0:
                    continue
                band = line.buffer(tolerance)
                support = sorted({l.native_id for l in lines if not l.unsupported_reason
                                  and band.intersection(l.geometry_m).length > tolerance
                                  and l.geometry_m.buffer(tolerance).covers(line)})
                features.append(feature("boundary_candidate", {"type": "LineString",
                                                                "coordinates": [INVERSE(*a), INVERSE(*b)]},
                                        native_ids=[name, *support], space_id=name, variant="B1",
                                        status="PROPOSED" if support else "REJECTED",
                                        evidence="NATIVE_RING_WITH_LINEAR_SUPPORT" if support else "NATIVE_RING_GEOMETRY_ONLY",
                                        reason=restricted or ("REQUIRES_TOPOLOGY_VALIDATION" if support else "UNSUPPORTED_BOUNDARY"),
                                        edge_id=f"{name}:ring{ring_no}:edge{n}", distance_m=None))
    return rows, features


def csv_file(name, rows, columns):
    path = ROOT / "data" / name
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else v
                             for k, v in row.items()})


def run_scene(scene, protocol):
    clip = ROOT / scene["osm_clip"]
    data = read(clip)
    b0_lock = base_record(read(ROOT / scene["historical_local_route"]))
    b0_frozen = frozen.route_osm(data, scene["start"], scene["target"], protocol["frozen_baseline_snap_m"])
    for k in ("status", "failure_reason", "geometry", "length_m", "snap_start_m", "snap_end_m",
              "snap_start", "snap_end", "way_ids", "node_ids", "segments", "profile", "graph_stats"):
        if b0_frozen.get(k) != b0_lock.get(k):
            raise ValueError(f"{scene['scene_id']} frozen B0 mismatch on {k}")
    segments, endings, _ = frozen._segments(data)
    graph, _ = frozen._build_graph(segments, endings, ())
    for _, _, edge in graph.edges(data=True):
        if edge["osm_way_id"] is not None:
            edge["native_id"] = f"way/{edge['osm_way_id']}"
    focus_ids = scene["r4_focus_space_ids"]
    nodes, ways, projected, spaces, perimeter_nodes, missing_spaces, obstacle_rows, unresolved = native_inputs(data, focus_ids)
    structured_gate = capability({"open_space_geometry": "AVAILABLE" if spaces else "UNKNOWN",
                                  "native_pedestrian_geometry": "AVAILABLE", "native_node_topology": "AVAILABLE",
                                  "obstacle_geometry": "AVAILABLE"})
    lines = to_lines(data, nodes, ways, projected, [space[1] for space in spaces])
    obstacles = Obstacles(obstacle_rows)
    anchor_keys = {key for s in segments if s.evidence in {"MAPPED_PEDESTRIAN_WAY", "EXPLICIT_FOOT_ON_WAY_AXIS"}
                   for key in (s.a, s.b) if key[1:] == ("0", "0")}
    anchors = {key: Point(projected[key[0]]) for key in anchor_keys}
    origin = (reference_id(scene["start_native_id"]), "0", "0")
    eligible = [e for e in scene["r4_entrances"] if e["eligible"]]
    entrance_keys = {(reference_id(e["native_id"]), "0", "0") for e in eligible}
    tol = protocol["geometry_tolerance_m"]
    b1, b2, evidence, a1, a2 = add_supported_edges(graph, anchors, entrance_keys, spaces, lines, obstacles, tol,
                                                 protocol["tagged_path_min_length_m"])
    metrics = {}
    features = []
    access_rows = []
    for variant, current, added in (("B0", graph, []), ("B1", b1, a1), ("B2", b2, a1 + a2)):
        routes = [entrance_route(current, origin, (reference_id(e["native_id"]), "0", "0"), e, obstacles, PROJECT)
                  for e in eligible]
        for route in routes:
            if route["target"] == scene["target"]:
                route["baseline_nearest_network_gap_m"] = b0_frozen["snap_end_m"]
        access_rows.extend({"scene_id": scene["scene_id"], "variant": variant, **r} for r in routes)
        summary = graph_stats(current)
        metrics[variant] = {"status": "EVALUATED" if eligible else "NO_ELIGIBLE_ENTRY_LOCAL_TOPOLOGY_ONLY",
                            "routes": routes, "route": routes[0] if routes else None,
                            "graph": summary, "added_edges": len(added),
                            "valid_entry_route_count": sum(r["status"] == "MAPPED_ENTRY_REACHED" for r in routes)}
        for route in routes:
            if route["geometry"]:
                props = {"variant": variant, "native_ids": [route["target_native_id"], *route["source_way_ids"]],
                         "status": route["status"], "evidence": "NATIVE_GRAPH_RECOMPUTED",
                         "distance_m": route["target_gap_m"], "length_m": route["length_m"],
                         "target_native_id": route["target_native_id"], "reason": route["failure_reason"]}
                features.append(feature("route", route["geometry"], **props))
                features.append(feature("route_end", point(route["route_end"]), **props))
    selected = select_entrance(metrics["B2"]["routes"])
    metrics["B3"] = {"status": selected["status"], "routes": metrics["B2"]["routes"] if len(eligible) >= 2 else [],
                     "route": selected["selected"], "graph": graph_stats(b2), "added_edges": len(a1 + a2),
                     "valid_entry_route_count": metrics["B2"]["valid_entry_route_count"] if len(eligible) >= 2 else None}
    if selected["selected"]:
        route = selected["selected"]
        access_rows.append({"scene_id": scene["scene_id"], "variant": "B3", **route})
        features.append(feature("route", route["geometry"], variant="B3", status=route["status"],
                                native_ids=[route["target_native_id"]], length_m=route["length_m"],
                                distance_m=route["target_gap_m"], evidence="REGISTERED_ENTRY_SELECTION"))
    matches, geometry = boundary_objects(spaces, perimeter_nodes, lines, segments, projected, graph, origin, tol)
    features.extend(geometry)
    for row in evidence:
        features.append(feature("edge_added" if row["status"] == "VERIFIED" else "edge_evidence", row["geometry"],
                                variant=row["variant"], native_ids=[row["space_id"], row["way_id"], row["start_node"], row["end_node"]],
                                status=row["status"], reason=row["reason"], evidence=row["evidence"],
                                distance_m=row["closest_boundary_distance_m"], edge_id=row["edge_id"],
                                length_m=row["length_m"], obstacle_ids=row["obstacle_ids"]))
    for entry in scene["r4_entrances"]:
        if not entry["eligible"]:
            access_rows.extend({"scene_id": scene["scene_id"], "variant": variant, "target_native_id": entry["native_id"],
                                "target": entry["coordinate"], "status": "EXCLUDED_REGISTERED_ENTRANCE",
                                "failure_reason": entry["reason"]} for variant in ("B0", "B1", "B2"))
        features.append(feature("entry", point(entry["coordinate"]), native_ids=[entry["native_id"]],
                                status="ELIGIBLE" if entry["eligible"] else "EXCLUDED",
                                evidence=entry["entrance_grade"], reason=entry["reason"], variant="ALL",
                                tags=entry["tags"]))
        for name, space, _ in spaces:
            p = Point(PROJECT(*entry["coordinate"]))
            gap = p.distance(unary_union(shells(space)))
            if gap <= tol:
                features.append(feature("access_candidate", point(entry["coordinate"]), native_ids=[name, entry["native_id"]],
                                        status="OBSERVED", evidence="REGISTERED_ENTRY_ON_OR_NEAR_BOUNDARY",
                                        reason=entry["reason"], distance_m=gap, variant="ALL"))
    features.append(feature("origin", point(scene["start"]), native_ids=[scene["start_native_id"]],
                            status="OBSERVED", evidence="FROZEN_SOURCE_ORIGIN", variant="ALL"))
    features.append(feature("building", scene["building_footprint"], native_ids=[scene["building_native_id"]],
                            status="OBSERVED", evidence="FROZEN_FOOTPRINT", variant="ALL"))
    snap = b0_frozen.get("snap_end")
    if snap:
        features.append(feature("route_end", point(snap["position"]), native_ids=[f"way/{snap['way_id']}"],
                                status="FROZEN_NEAREST_NETWORK_POINT", evidence=snap["evidence"],
                                distance_m=snap["distance_m"], variant="B0_DIAGNOSTIC"))
    for field, variant in (("historical_local_diagnostic", "B0_DIAGNOSTIC"), ("historical_hosted_route", "HOSTED")):
        if scene.get(field):
            doc = read(ROOT / scene[field])
            geom = geometry_in(doc)
            if geom:
                _, end = ends(geom)
                props = {"variant": variant, "native_ids": [], "status": "HISTORICAL_DIAGNOSTIC" if field == "historical_local_diagnostic" else "HISTORICAL_HOSTED_SERVICE",
                         "evidence": "PRESERVED_HISTORICAL_GEOMETRY", "distance_m": distance(end, scene["target"])}
                features.append(feature("route", geom, **props))
                features.append(feature("route_end", point(end), **props))
    if b0_frozen.get("geometry"):
        features.append(feature("route", b0_frozen["geometry"], variant="B0_FROZEN", native_ids=[],
                                status="FROZEN_NEAR_NETWORK_ROUTE", evidence="FROZEN_PROFILE_REPLAY",
                                distance_m=b0_frozen["snap_end_m"]))
    projected_footprint = transform(PROJECT, shape(scene["building_footprint"]))
    vicinity = (unary_union([p for _, p, _ in spaces]).buffer(120)
                if spaces else projected_footprint.buffer(100))
    comps = {key: i for i, keys in enumerate(sorted(nx.weakly_connected_components(graph),
                                                  key=lambda c: (-len(c), min(map(str, c)))), 1)
             for key in keys}
    for s in segments:
        geom = LineString([projected[s.a[0]], projected[s.b[0]]])
        if geom.intersects(vicinity):
            features.append(feature("b0_network", {"type": "LineString", "coordinates": [s.p, s.q]},
                                    native_ids=[f"way/{s.way}", f"node/{s.a[0]}", f"node/{s.b[0]}"],
                                    variant="ALL", status="OBSERVED_IN_B0", evidence=s.evidence,
                                    component_id=comps[s.a], native_direction=s.directions))
    for name, kind, geom in obstacle_rows:
        if geom.intersects(vicinity):
            features.append(feature("obstacle", mapping(transform(INVERSE, geom)), native_ids=[name],
                                    variant="ALL", status="OBSERVED", evidence=kind))
    diagnostic_boundary = sum(f["properties"].get("reason") == "UNSUPPORTED_BOUNDARY" for f in geometry)
    sensitivity = []
    for scale in protocol["sensitivity_m"]:
        _, _, sc, sa1, sa2 = add_supported_edges(graph, anchors, entrance_keys, spaces, lines, obstacles, scale,
                                                protocol["tagged_path_min_length_m"])
        sensitivity.append({"tolerance_m": scale, "source_line_candidates": len(sc),
                            "verified_b1": len(sa1), "verified_b2_additional": len(sa2)})
    summary = {"scene_id": scene["scene_id"], "label": scene["label"], "focus_space_ids": focus_ids,
               "missing_focus_geometries": missing_spaces, "open_space_count": len(spaces), "entrances": scene["r4_entrances"],
               "eligible_entrance_count": len(eligible), "boundary_contacts": matches,
               "boundary_contact_count": sum(p["evidence"] == "B0_NATIVE_NODE_ON_PERIMETER" for p in matches),
               "geometric_boundary_candidate_count": sum(p["status"] == "PROPOSED" for p in matches),
               "unsupported_boundary_segments": diagnostic_boundary,
               "source_line_candidates": len(evidence), "candidate_status_counts": {},
               "verified_b1_edges": len(a1), "verified_b2_additional_edges": len(a2),
               "variants": metrics, "sensitivity": sensitivity, "structured_input_gate": structured_gate,
               "unresolved_obstacle_geometry_count": len(unresolved),
               "local_b0_frozen_replay": {"match": True, "status": b0_frozen["status"], "failure_reason": b0_frozen["failure_reason"],
                                           "length_m": b0_frozen["length_m"], "target_gap_m": b0_frozen["snap_end_m"],
                                           "start_gap_m": b0_frozen["snap_start_m"], "target_snap": snap,
                                           "graph_stats": b0_frozen["graph_stats"], "historical_path": scene["historical_local_route"]},
               "clip_sha256": hash_file(clip), "geometry_path": f"runs/geometry/{scene['scene_id']}.geojson"}
    from collections import Counter
    summary["candidate_status_counts"] = dict(Counter(r["status"] for r in evidence))
    dump(ROOT / summary["geometry_path"], {"type": "FeatureCollection", "features": features})
    edge_rows = [{"scene_id": scene["scene_id"], **r} for r in evidence]
    connectivity = [{"scene_id": scene["scene_id"], "variant": v, "status": m["status"],
                     **m["graph"], "added_edges": m["added_edges"],
                     "weak_component_delta_from_b0": m["graph"]["weak_components"] - metrics["B0"]["graph"]["weak_components"],
                     "eligible_entrances": len(eligible), "valid_entry_route_count": m["valid_entry_route_count"]}
                    for v, m in metrics.items()]
    if not eligible:
        access_rows.extend({"scene_id": scene["scene_id"], "variant": v,
                            "status": "NO_ELIGIBLE_ENTRY_LOCAL_TOPOLOGY_ONLY"} for v in ("B0", "B1", "B2"))
    if len(eligible) < 2:
        access_rows.append({"scene_id": scene["scene_id"], "variant": "B3", "status": selected["status"]})
    boundary_rows = [{"scene_id": scene["scene_id"], **f["properties"], "geometry": f["geometry"]}
                     for f in geometry if f["properties"]["kind"] in {"access_candidate", "boundary_candidate"}]
    return summary, edge_rows, access_rows, connectivity, boundary_rows


def main():
    contracts = read(ROOT / "runs/source_scene_contracts.json")["scenes"]
    protocol = read(ROOT / "runs/protocol_core.json")
    all_scenes, edges, entrances, connectivity, boundaries = [], [], [], [], []
    for scene in contracts:
        result, edge, entry, connect, boundary = run_scene(scene, protocol)
        all_scenes.append(result)
        edges.extend(edge)
        entrances.extend(entry)
        connectivity.extend(connect)
        boundaries.extend(boundary)
        print(scene["scene_id"], result["local_b0_frozen_replay"]["status"],
              result["source_line_candidates"], result["verified_b1_edges"], result["verified_b2_additional_edges"], flush=True)
    dump(ROOT / "runs/experiment.json", {"protocol": "runs/protocol_core.json", "scenes": all_scenes,
                                        "runtime_scope": "OSM_STRUCTURED_ENHANCEMENT", "geoapify_new_requests": 0})
    edge_columns = ["scene_id", "space_id", "edge_id", "way_id", "segment_index", "start_node", "end_node",
                    "variant", "status", "reason", "evidence", "geometry_check", "topology_check", "attachment_nodes",
                    "obstacle_ids", "length_m", "closest_boundary_distance_m", "boundary_distance_m", "geometry", "original_tags"]
    csv_file("added_edges.csv", [row for row in edges if row["status"] == "VERIFIED"], edge_columns)
    csv_file("edge_candidate_evidence.csv", edges, edge_columns)
    csv_file("boundary_candidates.csv", boundaries, ["scene_id", "space_id", "kind", "edge_id", "variant", "native_ids",
                                                    "status", "reason", "evidence", "distance_m", "reachable_from_start", "geometry"])
    csv_file("entrance_access.csv", entrances, ["scene_id", "variant", "target_native_id", "target", "status", "failure_reason",
                                               "route_end", "length_m", "target_gap_m", "baseline_nearest_network_gap_m",
                                               "obstacle_ids", "source_way_ids", "used_added_edge_ids"])
    csv_file("connectivity_changes.csv", connectivity, ["scene_id", "variant", "status", "nodes", "directed_edges",
                                                       "weak_components", "largest_weak_component", "added_edges",
                                                       "weak_component_delta_from_b0", "eligible_entrances", "valid_entry_route_count"])


if __name__ == "__main__":
    main()
