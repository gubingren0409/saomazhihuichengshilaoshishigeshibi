"""Independent audit of a local OSM route, declared viewports and optional PNGs."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import atan, cos, degrees, exp, hypot, isfinite, log, pi, radians, sin, tan
from pathlib import Path

from geographiclib.geodesic import Geodesic
from PIL import Image, ImageChops
from shapely.geometry import LineString, Polygon, box

EARTH = 6378137.0
GEOD = Geodesic.WGS84
TOL = 0.05
FOOT_PERMIT = {"yes", "designated", "permissive", "official"}
ACCESS_EXCLUDE = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry"}
RELEVANT_CONDITIONS = {"access:conditional", "foot:conditional", "oneway:foot:conditional",
                       "foot:forward:conditional", "foot:backward:conditional"}


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def lonlat(value):
    assert len(value) == 2 and all(isfinite(v) for v in value)
    x, y = value
    assert -180 <= x <= 180 and -85.05113 < y < 85.05113
    return float(x), float(y)


def distance(a, b):
    lon_a, lat_a = lonlat(a)
    lon_b, lat_b = lonlat(b)
    return GEOD.Inverse(lat_a, lon_a, lat_b, lon_b)["s12"]


def path_length(points):
    return sum(distance(a, b) for a, b in zip(points, points[1:]))


def mercator(point):
    lon, lat = lonlat(point)
    return EARTH * radians(lon), EARTH * log(tan(pi / 4 + radians(lat) / 2))


def inverse(x, y):
    return degrees(x / EARTH), degrees(2 * atan(exp(y / EARTH)) - pi / 2)


def approximately(observed, expected, limit=TOL):
    return abs(observed - expected) <= limit


def no_explicit_exclusion(tags):
    if RELEVANT_CONDITIONS.intersection(tags):
        return False
    foot = tags.get("foot")
    return foot in FOOT_PERMIT if foot is not None else tags.get("access") not in ACCESS_EXCLUDE


def allows_way(tags):
    group = tags.get("highway")
    if not no_explicit_exclusion(tags) or tags.get("area") == "yes":
        return False
    if tags.get("indoor", "no") != "no" or tags.get("ford", "no") != "no":
        return False
    footway = {"footway", "pedestrian", "path", "steps"}
    street = {"living_street", "residential", "unclassified", "service"}
    main = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
    optional = {"track", "cycleway", "bridleway", "corridor"}
    permitted_sidewalks = {"yes", "both", "left", "right"}
    if group not in footway | street | main | optional:
        return False
    if group not in footway and tags.get("foot") not in FOOT_PERMIT:
        sidewalk = any(tags.get(k) in permitted_sidewalks for k in
                       ("sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both"))
        if not ((group in street | main and sidewalk)
                or (group in street and tags.get("sidewalk") not in {"separate", "no"})):
            return False
    oneway = tags.get("oneway:foot")
    if oneway is None and group in {"footway", "path", "steps"}:
        oneway = tags.get("oneway")
    if oneway not in {None, "no", "false", "0", "yes", "true", "1", "-1", "reverse"}:
        return False
    return ((oneway not in {"-1", "reverse"} and tags.get("foot:forward", "yes") in FOOT_PERMIT)
            or (oneway not in {"yes", "true", "1"} and tags.get("foot:backward", "yes") in FOOT_PERMIT))


def allows_node(tags):
    if tags.get("locked") == "yes" or not no_explicit_exclusion(tags):
        return False
    return (tags.get("barrier", "no") in {"no", "bollard", "block", "cycle_barrier", "cattle_grid", "kerb", "entrance"}
            or tags.get("foot") in FOOT_PERMIT)


def nearest_gap(point, nodes, ways, positions, bounds):
    # GeographicLib inverse, then azimuthal-equidistant Cartesian coordinates around the query.
    center_x, center_y = lonlat(point)
    w, s, e, n = bounds
    near = {}
    for key, (x, y) in positions.items():
        if not (w <= x <= e and s <= y <= n) or not allows_node(nodes[key].get("tags", {})):
            continue
        pair = GEOD.Inverse(center_y, center_x, y, x)
        angle = radians(pair["azi1"])
        near[key] = (pair["s12"] * sin(angle), pair["s12"] * cos(angle))
    best = None
    for way in ways.values():
        if not allows_way(way.get("tags", {})):
            continue
        ids = way["nodes"]
        for i, (a, b) in enumerate(zip(ids, ids[1:])):
            if a not in near or b not in near:
                continue
            x, y = near[a]
            u, v = near[b]
            dx, dy = u - x, v - y
            norm_sq = dx * dx + dy * dy
            if norm_sq == 0:
                continue
            fraction = max(0.0, min(1.0, -(x * dx + y * dy) / norm_sq))
            result = (hypot(x + fraction * dx, y + fraction * dy), way["id"], i)
            if best is None or result < best:
                best = result
    assert best is not None
    return best


def audit_snap(meta, requested, nodes, ways, positions):
    native = ways[meta["way_id"]]
    a, b = native["nodes"][meta["segment_index"]:meta["segment_index"] + 2]
    assert [a, b] == meta["source_node_ids"] and allows_way(native.get("tags", {}))
    assert all(allows_node(nodes[x].get("tags", {})) for x in (a, b))
    p, q, candidate = positions[a], positions[b], lonlat(meta["position"])
    assert approximately(distance(p, candidate) + distance(candidate, q), distance(p, q))
    gap = distance(candidate, requested)
    assert approximately(gap, meta["distance_m"])
    return {"verified_gap_m": gap, "way_id": native["id"], "segment_index": meta["segment_index"],
            "candidate_position": list(candidate), "native_nodes": [a, b]}


def support(source, route):
    elements = source["elements"]
    nodes = {row["id"]: row for row in elements if row["type"] == "node"}
    ways = {row["id"]: row for row in elements if row["type"] == "way"}
    positions = {key: lonlat((row["lon"], row["lat"])) for key, row in nodes.items()}
    valid = 0
    transitions = 0
    source_path = []
    if route.get("status") != "PASS":
        assert route.get("geometry") is None
        return nodes, ways, positions, {
            "status": "NO_PATH_TO_AUDIT",
            "declared_failure": route.get("failure_reason"),
        }

    geometry = route["geometry"]
    assert geometry["type"] == "LineString"
    coords = [lonlat(c) for c in geometry["coordinates"]]
    assert len(coords) >= 2 and not any(a == b for a, b in zip(coords, coords[1:]))
    assert coords[0] == lonlat(route["route_start"])
    assert coords[-1] == lonlat(route["route_end"])
    length = path_length(coords)
    assert approximately(length, route["length_m"])
    assert route["max_snap_m"] == 35
    assert approximately(distance(coords[0], route["requested_start"]), route["snap_start_m"])
    assert approximately(distance(coords[-1], route["requested_target"]), route["snap_end_m"])
    assert max(route["snap_start_m"], route["snap_end_m"]) <= route["max_snap_m"]
    previous = None
    observed_ways = []
    used_nodes = set()
    for seg in route["segments"]:
        p, q = lonlat(seg["start"]), lonlat(seg["end"])
        assert previous is None or p == previous
        if not source_path:
            source_path.append(p)
        if source_path[-1] != q:
            source_path.append(q)
        if seg["osm_way_id"] is None:
            node = seg["source_node_transition"]
            assert p == q == positions[node]
            assert seg["length_m"] == 0
            used_nodes.add(node)
            transitions += 1
        else:
            way = ways[seg["osm_way_id"]]
            a, b = way["nodes"][seg["segment_index"]:seg["segment_index"] + 2]
            assert [a, b] == seg["osm_source_node_ids"]
            native_a, native_b = positions[a], positions[b]
            native_length = distance(native_a, native_b)
            for candidate in (p, q):
                assert approximately(distance(native_a, candidate) + distance(candidate, native_b), native_length)
            assert approximately(distance(p, q), seg["length_m"])
            tags = way.get("tags", {})
            assert tags.get("highway") and tags.get("area") != "yes"
            assert tags.get("foot") != "no" and (tags.get("access") not in {"private", "no"}
                                                 or tags.get("foot") in {"yes", "designated", "permissive", "official"})
            forward = distance(native_a, p) <= distance(native_a, q)
            foot_direction = tags.get("oneway:foot")
            if foot_direction is None and tags.get("highway") in {"footway", "path", "steps"}:
                foot_direction = tags.get("oneway")
            assert foot_direction not in ({"-1", "reverse"} if forward else {"yes", "1", "true"})
            if way["id"] not in observed_ways:
                observed_ways.append(way["id"])
            used_nodes.update((a, b))
            valid += 1
        previous = q

    assert coords == source_path and observed_ways == route["way_ids"]
    assert approximately(sum(s["length_m"] for s in route["segments"]), length)
    return nodes, ways, positions, {
        "status": "PASS",
        "length_m": length,
        "start_offset_m": distance(coords[0], route["requested_start"]),
        "target_offset_m": distance(coords[-1], route["requested_target"]),
        "route_start_wgs84": list(coords[0]),
        "route_endpoint_wgs84": list(coords[-1]),
        "n_vertices": len(coords),
        "native_segments_checked": valid,
        "native_transition_nodes_checked": transitions,
        "native_ways_checked": observed_ways,
        "native_nodes_checked": sorted(used_nodes),
        "evidence_counts": dict(Counter(s["evidence"] for s in route["segments"])),
    }


def viewport(view, footprint, route):
    width, height = view["width"], view["height"]
    west, south, east, north = view["bounds"]
    left, bottom = mercator((west, south))
    right, top = mercator((east, north))
    assert (width, height) == (1200, 900) and right > left and top > bottom
    mx, my = (left + right) / 2, (top + bottom) / 2
    span_x, span_y = (right - left) / width, (top - bottom) / height
    nominal = 2 * pi * EARTH / (256 * 2 ** view["zoom"])
    assert approximately(span_x, span_y, 0.0001)
    assert approximately(span_x, nominal, 0.0001)
    measured_center = inverse(mx, my)
    if "center" in view:
        assert distance(measured_center, view["center"]) < 0.1
    geom = Polygon([mercator(p) for p in footprint])
    assert geom.is_valid and geom.area > 0
    lx, ly, ux, uy = geom.bounds
    assert left < lx < ux < right and bottom < ly < uy < top
    result = {
        "bounds_wsen": view["bounds"],
        "projected_m_per_px": [span_x, span_y],
        "ground_m_per_px_xy_at_center": [
            distance(inverse(mx - span_x / 2, my), inverse(mx + span_x / 2, my)),
            distance(inverse(mx, my - span_y / 2), inverse(mx, my + span_y / 2)),
        ],
        "building_px_wh": [(ux - lx) / span_x, (uy - ly) / span_y],
        "building_pixel_area_fraction": geom.area / (span_x * span_y * width * height),
    }
    if route.get("geometry"):
        coords = route["geometry"]["coordinates"]
        result["route_start_px"] = [(mercator(coords[0])[0] - left) / span_x, (top - mercator(coords[0])[1]) / span_y]
        result["route_end_px"] = [(mercator(coords[-1])[0] - left) / span_x, (top - mercator(coords[-1])[1]) / span_y]
        result["route_end_inside_view"] = 0 <= result["route_end_px"][0] < width and 0 <= result["route_end_px"][1] < height
    return result


def raster(base_path, overlay_path, expected=(1200, 900)):
    with Image.open(base_path) as base_raw, Image.open(overlay_path) as overlay_raw:
        assert base_raw.size == overlay_raw.size == expected
        base, overlay = base_raw.convert("RGB"), overlay_raw.convert("RGB")
        colors = base.getcolors(maxcolors=expected[0] * expected[1])
        assert colors and len(colors) > 25
        changed = ImageChops.difference(base, overlay)
        diff_pixels = sum(1 for value in changed.getdata() if value != (0, 0, 0))
        assert 0 < diff_pixels < (expected[0] * expected[1]) / 4
        return {"size_px": list(base.size), "distinct_base_colors": len(colors),
                "changed_overlay_pixels": diff_pixels, "changed_overlay_bbox": changed.getbbox(),
                "sha256_base": digest(base_path), "sha256_overlay": digest(overlay_path)}


def raw_pbf(path, nodes, ways, selected_way_ids, selected_node_ids):
    import osmium

    nids, wids = set(selected_node_ids), set(selected_way_ids)
    seen_nodes, seen_ways = set(), set()
    for object in osmium.FileProcessor(str(path)):
        kind = object.type_str()
        if kind == "n" and object.id in nids:
            expect = nodes[object.id]
            assert object.location.valid() and approximately(object.lon, expect["lon"], 1e-7)
            assert approximately(object.lat, expect["lat"], 1e-7)
            expect_tags = expect.get("tags", {})
            assert all(object.tags.get(key) == val for key, val in expect_tags.items())
            seen_nodes.add(object.id)
        elif kind == "w" and object.id in wids:
            expect = ways[object.id]
            assert [n.ref for n in object.nodes] == expect["nodes"]
            assert all(object.tags.get(key) == val for key, val in expect.get("tags", {}).items())
            seen_ways.add(object.id)
        if nids == seen_nodes and wids == seen_ways:
            break
    assert seen_nodes == nids and seen_ways == wids
    return {"status": "PASS", "pbf_bytes": Path(path).stat().st_size, "pbf_sha256": digest(path),
            "n_native_nodes": len(seen_nodes), "n_native_ways": len(seen_ways)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("source", "contract", "route", "out"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--pbf", type=Path)
    parser.add_argument("--geojson", type=Path)
    parser.add_argument("--diagnostic", type=Path)
    parser.add_argument("--diagnostic-geojson", type=Path)
    parser.add_argument("--qa", type=Path)
    parser.add_argument("--basemaps", type=Path)
    parser.add_argument("--target-way", type=int, default=161090899)
    args = parser.parse_args()
    source, contract, route = map(json_file, (args.source, args.contract, args.route))
    nodes, ways, positions, status = support(source, route)
    assert lonlat(contract["start"]) == lonlat(route["requested_start"])
    assert lonlat(contract["target"]) == lonlat(route["requested_target"])
    target = ways[args.target_way]
    footprint = [positions[node] for node in target["nodes"]]
    assert [lonlat(p) for p in contract["building_footprint"]["coordinates"][0]] == footprint
    assert contract["snapshot_sha256"] == digest(args.source)
    assert contract["frozen_before_route"] is True
    assert contract["building_native_id"] == f"way/{args.target_way}"
    start_native = int(contract["start_native_id"].rsplit("/", 1)[-1])
    assert positions[start_native] == lonlat(contract["start"])
    entry_native = int(contract["entry_native_id"].rsplit("/", 1)[-1]) if contract["entry_native_id"] else None
    if entry_native is not None:
        assert entry_native in target["nodes"] and positions[entry_native] == lonlat(contract["target"])
        assert nodes[entry_native].get("tags", {}).get("entrance") in {"yes", "main", "entrance", "public"}
    if args.geojson:
        exported = json_file(args.geojson)
        assert exported["type"] == "Feature" and exported["geometry"] == route.get("geometry")
    assert target.get("tags", {}).get("building") and footprint[0] == footprint[-1]
    output = {"source_sha256": digest(args.source), "contract_sha256": digest(args.contract),
              "route_sha256": digest(args.route), "target_way": args.target_way,
              "unique_nodes": len(nodes), "unique_ways": len(ways), "route": status, "views": {},
              "start_native_node": start_native, "entrance_native_node": entry_native,
              "geojson_sha256": digest(args.geojson) if args.geojson else None}
    for slot in ("start", "end"):
        if route.get("snap_" + slot):
            endpoint = contract["start"] if slot == "start" else contract["target"]
            audit = audit_snap(route["snap_" + slot], endpoint, nodes, ways, positions)
            assert approximately(audit["verified_gap_m"], route[f"snap_{slot}_m"])
            if slot == "end":
                shortest = nearest_gap(endpoint, nodes, ways, positions, source["bounds_wsen"])
                assert approximately(audit["verified_gap_m"], shortest[0])
                audit["independent_nearest"] = list(shortest)
            output["route"]["snap_" + slot] = audit
    if route["failure_reason"] == "TARGET_SNAP_OUTSIDE_LIMIT":
        assert route["snap_start_m"] <= route["max_snap_m"] < route["snap_end_m"]
    overlay = route
    diagnostic = None
    if args.diagnostic:
        diagnostic = json_file(args.diagnostic)
        assert diagnostic["identity"] == "PARTIAL_DIAGNOSTIC_TO_NEAREST_MAPPED_SEGMENT"
        assert diagnostic["parent_failure"] == route["failure_reason"] and diagnostic["missing_segment_drawn"] is False
        assert diagnostic["requested_start"] == contract["start"]
        assert diagnostic["requested_target"] == diagnostic["route_end"] == route["snap_end"]["position"]
        assert approximately(distance(diagnostic["route_end"], contract["target"]),
                             diagnostic["remaining_gap_to_original_target_m"])
        if args.diagnostic_geojson:
            exported = json_file(args.diagnostic_geojson)
            assert exported["type"] == "Feature" and exported["geometry"] == diagnostic["geometry"]
        output["diagnostic"] = support(source, diagnostic)[3]
        output["diagnostic"]["remaining_gap_m"] = distance(diagnostic["route_end"], contract["target"])
        output["diagnostic"]["missing_segment_drawn"] = False
        overlay = diagnostic
    if overlay.get("geometry"):
        footprint_m = Polygon([mercator(p) for p in footprint])
        line_m = LineString([mercator(p) for p in overlay["geometry"]["coordinates"]])
        checked_outlines, invalid_outlines, crossed_outlines = 0, 0, []
        for row in ways.values():
            if not row.get("tags", {}).get("building") or row["nodes"][0] != row["nodes"][-1]:
                continue
            ring = [mercator(positions[key]) for key in row["nodes"] if key in positions]
            if len(ring) < 4:
                continue
            building = Polygon(ring)
            if not building.is_valid:
                invalid_outlines += 1
                continue
            checked_outlines += 1
            intersection = line_m.intersection(building.buffer(-.5)).length
            if intersection > 0:
                crossed_outlines.append({"way_id": row["id"], "projected_m": intersection})
        output["diagnostic" if diagnostic else "route"].update(
            target_building_interior_intersection_mercator_m=line_m.intersection(footprint_m.buffer(-.05)).length,
            closed_building_tagged_ways_checked=checked_outlines,
            invalid_closed_building_tagged_ways=invalid_outlines,
            crossed_closed_building_tagged_ways=crossed_outlines,
        )
    lx, ly, ux, uy = Polygon([mercator(p) for p in footprint]).bounds
    center = inverse((lx + ux) / 2, (ly + uy) / 2)
    assert set(contract["views"]) == {"detail", "context"}
    qa = json_file(args.qa)["views"] if args.qa else {}
    for key, view in contract["views"].items():
        assert view["zoom"] == {"detail": 18, "context": 16}[key]
        assert view["dpr"] == 1 and view["pitch"] == view["bearing"] == 0
        assert distance(center, view["center"]) < 0.1
        output["views"][key] = viewport(view, footprint, overlay)
        if overlay.get("geometry"):
            output["views"][key]["overlay_route_projected_fraction_inside"] = (
                line_m.intersection(box(*view["extent_3857"])).length / line_m.length)
        actual_ground = output["views"][key]["ground_m_per_px_xy_at_center"][0]
        assert approximately(actual_ground, view["meters_per_pixel"], 0.001)

        if key in qa:
            measured = output["views"][key]
            assert qa[key]["pixel_size"] == [1200, 900] and qa[key]["building_fully_inside"]
            assert qa[key]["actual_bounds"] == view["bounds"]
            assert approximately(qa[key]["target_area_ratio"], measured["building_pixel_area_fraction"], 0.00001)
            assert all(approximately(x, y, 1) for x, y in zip(qa[key]["target_pixel_size"], measured["building_px_wh"]))
            if overlay.get("geometry"):
                assert all(approximately(x, y, 1) for x, y in zip(qa[key]["rendered_route_end_pixel"], measured["route_end_px"]))
        if args.basemaps:
            stem = contract["scene_id"].lower() + "_" + key
            output["views"][key]["png"] = raster(args.basemaps / (stem + "_base.png"),
                                                  args.basemaps / (stem + "_route.png"))
    if args.pbf:
        line_evidence = output.get("diagnostic", status)
        snap_evidence = [value for key, value in output["route"].items() if key.startswith("snap_")]
        output["pbf_crosscheck"] = raw_pbf(
            args.pbf, nodes, ways,
            [args.target_way, *line_evidence.get("native_ways_checked", []), *(x["way_id"] for x in snap_evidence)],
            [start_native, *target["nodes"], *line_evidence.get("native_nodes_checked", []),
             *(node for x in snap_evidence for node in x["native_nodes"])])
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Independent OSM geometry verification completed.")


if __name__ == "__main__":
    main()
