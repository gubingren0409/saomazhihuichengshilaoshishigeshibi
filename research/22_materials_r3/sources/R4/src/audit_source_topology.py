"""Inventory native contacts and independently measure retained route geometry."""
import json

from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.ops import transform

from .prepare_sources import ROOT, PROJECT, coord, index, read_json, way_line, write_csv, write_json

GEOD = Geod(ellps="WGS84")
INTERIOR_BUFFER_M = 0.25
FOOT_TYPES = {"footway", "path", "pedestrian", "steps", "corridor"}
WALK_VALUES = {"yes", "designated", "permissive"}
ACCESS_RESTRICTIONS = {"private", "no", "restricted", "customers"}


def source_lines(idx, polygon):
    bounds = polygon.bounds
    for way in idx["way"].values():
        tags = way.get("tags", {})
        if (tags.get("area") == "yes" or tags.get("highway") is None
            or not (tags.get("highway") in FOOT_TYPES or tags.get("foot") in WALK_VALUES)
            or tags.get("foot") in ACCESS_RESTRICTIONS or tags.get("access") in ACCESS_RESTRICTIONS):
            continue
        try:
            line = way_line(way, idx)
        except (KeyError, ValueError):
            continue
        if line.bounds[0]>bounds[2] or line.bounds[1]>bounds[3] or line.bounds[2]<bounds[0] or line.bounds[3]<bounds[1]:
            continue
        yield way, transform(PROJECT, line)


def audit_space(feature, idx, entrances):
    polygon = shape(feature["geometry"])
    metric = transform(PROJECT, polygon)
    outer_ids = {node for way_id in feature["outer_way_ids"] for node in idx["way"][way_id]["nodes"]}
    outer_boundary = metric.exterior if metric.geom_type == "Polygon" else metric.boundary
    interior = metric.buffer(-INTERIOR_BUFFER_M)
    contacts, exact, internals, overlaps = [], set(), [], []
    for way, line in source_lines(idx, polygon):
        native_id = f"way/{way['id']}"
        shared = sorted(outer_ids.intersection(way["nodes"]))
        exact.update(shared)
        edge_length = line.intersection(outer_boundary).length
        inside_length = line.intersection(interior).length
        touching = line.intersects(outer_boundary)
        if touching or shared:
            contacts.append(dict(native_way_id=native_id, tags=way.get("tags", {}),
                shared_outer_nodes=shared, geometry_intersects_outer=touching,
                native_topology="SHARED_NODE" if shared else "NO_SHARED_OUTER_NODE",
                line_distance_m=round(line.distance(outer_boundary), 4),
                line_overlap_m=round(edge_length, 4)))
        if inside_length > 0:
            internals.append(dict(native_way_id=native_id, tags=way.get("tags", {}),
                                  geometry_inside_m=round(inside_length, 4), source_node_ids=way["nodes"]))
        if edge_length > 0.25:
            overlaps.append(native_id)
    memberships = [
        {"native_id":e["native_id"], "eligible":e["eligible"],
         "shared_outer_node":int(e["native_id"].split("/")[-1]) in outer_ids,
         "distance_to_area_boundary_m":round(transform(PROJECT, Point(e["coordinate"])).distance(metric.boundary),4)}
        for e in entrances
    ]
    return dict(scene_id=feature["scene_id"], space_native_id=feature["native_id"], near_area_foot_way_contacts=contacts,
                explicit_shared_outer_nodes=sorted(exact), area_inner_line_objects=internals,
                explicit_boundary_line_geometry_overlap_ids=overlaps, registered_entrance_relations=memberships,
                source_layer=feature["layer"], interpretation="GEOMETRIC_INVENTORY_ONLY_REQUIRES_CORE_TOPOLOGY_AND_LAYER_GATES")


def lines(doc):
    if doc is None:
        return []
    kind = doc.get("type")
    if kind == "FeatureCollection":
        return [line for f in doc["features"] for line in lines(f)]
    if kind == "Feature":
        return lines(doc["geometry"])
    if kind == "LineString":
        return [doc["coordinates"]]
    if kind == "MultiLineString":
        return doc["coordinates"]
    return []


def measure(parts, target):
    if not parts:
        return None, None
    distance = sum(GEOD.line_length(*zip(*part)) for part in parts)
    gap = GEOD.inv(*parts[-1][-1], *target)[2]
    return round(distance, 6), round(gap, 6)


def main():
    scenes = read_json(ROOT / "runs/source_scene_contracts.json")["scenes"]
    features = read_json(ROOT / "runs/source_open_spaces.json")["features"]
    output, b0rows = [], []
    for s in scenes:
        sid = s["scene_id"]
        idx = index(read_json(ROOT / s["osm_clip"]))
        for f in features:
            if f["scene_id"] == sid and f["native_id"] in s["r4_focus_space_ids"]:
                output.append(audit_space(f, idx, s["r4_entrances"]))
        local = read_json(ROOT / s["historical_local_route"])
        distance, gap = measure(lines(local.get("geometry")), s["target"])
        if distance is not None:
            assert abs(distance-local["length_m"])<0.002, (sid, distance, local["length_m"])
        historical_diagnostic = s["historical_local_diagnostic"]
        diagnostic = read_json(ROOT / historical_diagnostic) if historical_diagnostic else {}
        diag_distance, diag_gap = measure(lines(diagnostic.get("geometry")), s["target"])
        hosted = read_json(ROOT / s["historical_hosted_route"])
        hosted_distance, hosted_gap = measure(lines(hosted), s["target"])
        b0rows.append(dict(scene_id=sid, frozen_target_role=s["target_role"], local_status=local["status"],
                           local_reason=local["failure_reason"], local_reported_m=local["length_m"],
                           local_geodesic_recomputed_m=distance, local_end_to_target_m=gap,
                           local_historical_target_snap_m=local["snap_end_m"],
                           diagnostic_recomputed_m=diag_distance, diagnostic_gap_m=diag_gap,
                           hosted_baseline_geometry_m=hosted_distance, hosted_baseline_target_gap_m=hosted_gap,
                           interpretation="RETAINED_ROUTE_GEOMETRY_NOT_FIELD_TRUTH"))
    write_json(ROOT / "runs/source_focus_contact_audit.json", dict(
        scope="OBSERVED_RAW_GEOMETRY_AND_TAGS_RECOMPUTED_METRIC_CONTACTS",
        analysis_crs="EPSG:32651", interior_exclusion_band_m=INTERIOR_BUFFER_M, focus_spaces=output))
    write_csv(ROOT / "data/source_focus_contacts.csv", [
        dict(scene_id=r["scene_id"], space_native_id=r["space_native_id"],
            perimeter_way_contacts=len(r["near_area_foot_way_contacts"]),
            shared_native_outer_nodes=len(r["explicit_shared_outer_nodes"]),
            raw_internal_tagged_ways=len(r["area_inner_line_objects"]),
            raw_boundary_overlap_ways=len(r["explicit_boundary_line_geometry_overlap_ids"]),
            source_layer=r["source_layer"], interpretation=r["interpretation"])
        for r in output])
    write_csv(ROOT / "data/historical_b0_recomputed.csv", b0rows)
    print(json.dumps({"audit_focus_objects":len(output),"historical_b0_scenes":len(b0rows)}, ensure_ascii=False))


if __name__=="__main__":
    main()
