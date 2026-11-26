"""Metric, provider-neutral tagged pedestrian area edge-band graph."""
from collections import Counter
from math import ceil, floor

import networkx as nx
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

AREA_EDGE = "DERIVED_FROM_TAGGED_PEDESTRIAN_AREA"
TERMINAL_EDGE = "DERIVED_TERMINAL_CONNECTOR"
METHOD = "EDGE_BAND_GRID_V1"
SURFACE_ASSUMPTION = "ORDINARY_OUTDOOR_SURFACE_NO_KNOWN_LAYER_CONFLICT"
DEFAULT = dict(width_m=3.0, grid_step_m=0.5, clearance_m=0.25,
               tolerance_m=0.001, port_max_m=1.0)
WALK_AREA = {"pedestrian", "footway", "path"}
WALK_PERMISSION = {"yes", "public", "permissive", "designated", "official"}
FLAT_FALSE = {None, "no", "false", "0"}


def model_config(config):
    out = {key: float(config.get(key, value)) for key, value in DEFAULT.items()}
    if (out["width_m"] not in {1.0, 3.0, 5.0}
            or not 0 < out["grid_step_m"] <= .5
            or out["clearance_m"] != .25
            or not 0 < out["tolerance_m"] <= .001
            or not 0 < out["port_max_m"] <= 1):
        raise ValueError("R4-REV1 geometry configuration outside the frozen contract")
    return out


def area_reason(tags, geometry):
    if not (tags.get("area:highway") in WALK_AREA
            or tags.get("area") == "yes" and tags.get("highway") in WALK_AREA):
        return "SOURCE_NOT_EXPLICIT_PEDESTRIAN_AREA"
    if restricted_access(tags):
        return "RESTRICTED_OR_CONDITIONAL_AREA"
    if not compatible_surface(tags):
        return "NON_GROUND_OR_UNRESOLVED_LAYER"
    if geometry is None or geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
        return "UNRESOLVED_SOURCE_AREA_GEOMETRY"
    return None


def restricted_access(tags):
    return any(k in tags and tags[k] not in WALK_PERMISSION for k in ("access", "foot", "pedestrian")) or any(
        k in tags for k in ("access:conditional", "foot:conditional", "pedestrian:conditional"))


def compatible_surface(tags):
    return (all(tags.get(k) in (None, "", "0", 0) for k in ("layer", "level"))
            and all(tags.get(k) in FLAT_FALSE for k in ("bridge", "tunnel", "indoor", "ford")))


def polygon_parts(shape):
    return [shape] if shape.geom_type == "Polygon" else [
        p for p in getattr(shape, "geoms", ()) if p.geom_type == "Polygon"]


def gate_intersections(line, barrier, tolerance):
    intersection = line.intersection(barrier["geometry"])
    if intersection.is_empty:
        return []
    points = [intersection] if intersection.geom_type == "Point" else (
        list(intersection.geoms) if intersection.geom_type == "MultiPoint" else None)
    if points is None:
        return None
    gate_ids = []
    for p in points:
        gate = next((g for g in barrier.get("gates", ())
                     if g.get("allowed") is True
                     and barrier["geometry"].distance(Point(g["xy"])) <= tolerance
                     and p.distance(Point(g["xy"])) <= tolerance), None)
        if gate is None:
            return None
        gate_ids.append(gate["id"])
    return gate_ids


def _obstacles(area_id, polygon, band, obstacles):
    nearby = [dict(row) for row in obstacles if not row["geometry"].is_empty
              and row["geometry"].distance(band) <= .25]
    for i, part in enumerate(polygon_parts(polygon)):
        for j, ring in enumerate(part.interiors):
            hole = Polygon(ring)
            if hole.distance(band) <= .25 and not any(
                    row["kind"] == "AREA" and hole.equals(row["geometry"]) for row in nearby):
                nearby.append({"id": f"{area_id}:inner/{i}/{j}", "kind": "AREA",
                               "geometry": hole})
    return nearby


def _numeric_building_endpoint_only(line, obstacle, endpoint, tolerance):
    if not line.relate_pattern(obstacle, "F********"):
        return False
    inter = line.intersection(obstacle)
    return inter.geom_type == "Point" and inter.distance(endpoint) <= tolerance


def _port_check(line, port, band, obstacles, margin, tolerance):
    if not band.covers(line):
        return "PORT_SEGMENT_OUTSIDE_SOURCE_BAND", [], []
    endpoint = Point(port["xy"])
    gate_ids, exceptions = [], []
    for obj in obstacles:
        geom = obj["geometry"]
        if obj["kind"] == "BARRIER":
            result = gate_intersections(line, obj, tolerance)
            if result is None:
                return "BARRIER_INTERSECTION", [], []
            gate_ids.extend(result)
        elif line.distance(geom) < margin:
            if (port["kind"] == "REGISTERED_ENTRANCE" and obj["kind"] == "BUILDING"
                    and obj["id"] == port.get("building_id")
                    and _numeric_building_endpoint_only(line, geom, endpoint, tolerance)):
                exceptions.append(obj["id"])
            else:
                return "LOCAL_UNKNOWN_OBSTACLE" if obj["kind"] == "UNKNOWN" else "AREA_CLEARANCE", [], []
    return None, gate_ids, exceptions


def _grid(domain, step):
    xmin, ymin, xmax, ymax = domain.bounds
    xs = np.arange(ceil(xmin / step), floor(xmax / step) + 1)
    ys = np.arange(ceil(ymin / step), floor(ymax / step) + 1)
    ii, jj = np.meshgrid(xs, ys, indexing="ij")
    grid_points = shapely.points(np.column_stack((ii.ravel(), jj.ravel())) * step)
    interior = shapely.contains(domain, grid_points).reshape(ii.shape)
    coord = lambda i, j: (float(xs[i] * step), float(ys[j] * step))
    keys = {(int(i), int(j)): (int(xs[i]), int(ys[j])) for i, j in np.argwhere(interior)}
    nodes = {key: coord(*ij) for ij, key in keys.items()}
    pairs = [(u, keys[v]) for (i, j), u in keys.items()
             for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1))
             if (v := (i + dx, j + dy)) in keys]
    return nodes, pairs


def _intersection_matches(tree, lines):
    results = {}
    if tree is not None and len(lines):
        ix, iy = tree.query(lines, predicate="intersects")
        for i, j in zip(ix, iy):
            results.setdefault(int(i), []).append(int(j))
    return results


def _duplicate_matches(lines, native_tree):
    matches = _intersection_matches(native_tree, lines)
    return {i for i, indices in matches.items()
            if unary_union([native_tree.geometries[j] for j in indices]).covers(lines[i])}


def derive(area_id, tags, shape_metric, obstacles, ports, config, native_segments=()):
    """Return auditable graph deltas, with precise caller-provided native identities."""
    config = model_config(config)
    width = config["width_m"]
    step = config["grid_step_m"]
    margin = config["clearance_m"]
    tolerance = config["tolerance_m"]
    max_port = config["port_max_m"]
    native_segments = [x[1] if isinstance(x, tuple) else x for x in native_segments]
    port_results = {}
    rejected = Counter()
    outcome = dict(source_area_id=area_id, source_tags=tags, method_version=METHOD,
                   nodes={}, edges=[], domain=Polygon(), port_results=port_results, rejected=rejected,
                   deduplicated=0, obstacles=[], area_status="EVALUATED",
                   candidate_graph_nodes=0, candidate_graph_edges=0, retained_components=0)
    reason = area_reason(tags, shape_metric)
    if reason:
        outcome["area_status"] = reason
        rejected[reason] += 1
        return outcome
    outer = unary_union([part.exterior for part in polygon_parts(shape_metric)])
    band = shape_metric.intersection(outer.buffer(width, quad_segs=16))
    nearby = _obstacles(area_id, shape_metric, band, obstacles)
    areal = [obj for obj in nearby if obj["kind"] != "BARRIER"]
    barriers = [obj for obj in nearby if obj["kind"] == "BARRIER"]
    masks = unary_union([obj["geometry"].buffer(margin, quad_segs=16) for obj in areal])
    domain = band.difference(masks)
    outcome["domain"] = domain
    outcome["obstacles"] = [{"id": o["id"], "kind": o["kind"]} for o in nearby]
    if domain.is_empty or domain.area <= 0:
        outcome["area_status"] = "NO_ALLOWED_EDGE_DOMAIN"
        rejected[outcome["area_status"]] += 1
        return outcome
    shapely.prepare(domain)
    ground = []
    for port in ports:
        xy = tuple(port["xy"])
        point = Point(xy)
        row = dict(port, xy=xy, status="REJECTED", edge_ids=[], source_outer_distance_m=outer.distance(point))
        port_results[port["id"]] = row
        if (port["kind"] not in {"NATIVE_CONTACT", "REGISTERED_ENTRANCE"}
                or not port.get("source_node_id")
                or not port.get("layer_compatible", True) or not compatible_surface(port)
                or not compatible_surface(port.get("tags", {}))):
            reason = "UNSUPPORTED_NATIVE_PORT_IDENTITY_OR_LAYER"
        elif restricted_access(port.get("tags", {})):
            reason = "RESTRICTED_OR_CONDITIONAL_PORT"
        elif port["kind"] == "NATIVE_CONTACT" and (
                not shape_metric.covers(point) or not band.covers(point)
                or row["source_outer_distance_m"] > tolerance or port.get("native_membership", True) is not True):
            reason = "NO_NATIVE_SHARED_OUTER_BOUNDARY"
        elif port["kind"] == "REGISTERED_ENTRANCE" and not band.covers(point):
            reason = "REGISTERED_DOOR_OUTSIDE_SUPPORTED_EDGE_BAND"
        elif port["kind"] == "REGISTERED_ENTRANCE" and not any(
                o["kind"] == "BUILDING" and o["id"] == port.get("building_id")
                and o["geometry"].boundary.distance(point) <= tolerance for o in nearby):
            reason = "NO_SOURCE_BUILDING_BOUNDARY_FOR_REGISTERED_DOOR"
        else:
            ground.append(row)
            continue
        row["reason"] = reason
        rejected[reason] += 1
    if not any(p["kind"] == "NATIVE_CONTACT" for p in ground):
        outcome["area_status"] = "NO_ELIGIBLE_NATIVE_NETWORK_PORT"
        rejected[outcome["area_status"]] += 1
        for p in ground:
            p["reason"] = outcome["area_status"]
        return outcome

    coords, pairs = _grid(domain, step)
    outcome["candidate_graph_nodes"] = len(coords)
    outcome["candidate_graph_edges"] = len(pairs)
    all_lines = shapely.linestrings(np.asarray([[coords[u], coords[v]] for u, v in pairs])) if pairs else []
    valid = shapely.covers(domain, all_lines) if pairs else []
    fence_tree = STRtree([obj["geometry"] for obj in barriers]) if barriers else None
    fence_matches = _intersection_matches(fence_tree, all_lines)
    nearby_native = [line for line in native_segments if line.distance(band) <= tolerance]
    native_tree = STRtree([line.buffer(tolerance, cap_style="flat") for line in nearby_native]) if nearby_native else None
    duplicate = _duplicate_matches(all_lines, native_tree)
    ids = {k: f"grid/{area_id}/{k[0]}/{k[1]}" for k in coords}
    nodes = {ids[k]: xy for k, xy in coords.items()}
    candidate_graph = nx.Graph()
    accepted = []
    for i, (u, v) in enumerate(pairs):
        if not valid[i]:
            rejected["SEGMENT_NOT_COVERED_BY_EDGE_DOMAIN"] += 1
            continue
        gates = [gate_intersections(all_lines[i], barriers[j], tolerance)
                 for j in fence_matches.get(i, [])]
        if any(gate is None for gate in gates):
            rejected["BARRIER_INTERSECTION"] += 1
            continue
        if i in duplicate:
            rejected["NATIVE_GEOMETRY_DUPLICATE"] += 1
            outcome["deduplicated"] += 1
            continue
        a, b = ids[u], ids[v]
        accepted.append((a, b, all_lines[i], AREA_EDGE, None, [g for row in gates for g in row], []))
        candidate_graph.add_edge(a, b)

    # An explicitly allowed gate can sit between lattice points. Connect it locally
    # without cutting the remainder of its source barrier.
    for obj in barriers:
        for gate in obj.get("gates", []):
            p = Point(gate["xy"])
            if gate.get("allowed") is True and band.covers(p) and obj["geometry"].distance(p) <= tolerance:
                gate_id = f"gate/{area_id}/{gate['id']}"
                if gate_id not in port_results:
                    row = dict(id=gate_id, xy=tuple(gate["xy"]), kind="EXPLICIT_GATE",
                               source_node_id=gate["id"], status="REJECTED", edge_ids=[])
                    ground.append(row)
                    port_results[gate_id] = row

    for port in ground:
        xy = port["xy"]
        node = port["id"]
        nodes[node] = xy
        near = [(key, ids[key], coords[key])
                for i in range(ceil((xy[0] - max_port) / step), floor((xy[0] + max_port) / step) + 1)
                for j in range(ceil((xy[1] - max_port) / step), floor((xy[1] + max_port) / step) + 1)
                if (key := (i, j)) in coords]
        near.sort(key=lambda item: (Point(xy).distance(Point(item[2])), item[0]))
        candidates = []
        failures = Counter()
        for _, grid_id, target in near:
            segment = LineString([xy, target])
            if segment.length <= tolerance or segment.length > max_port:
                continue
            reason, gates, exceptions = _port_check(segment, port, band, nearby, margin, tolerance)
            if not reason and _duplicate_matches(np.asarray([segment]), native_tree):
                reason = "NATIVE_GEOMETRY_DUPLICATE"
                outcome["deduplicated"] += 1
            if reason:
                failures[reason] += 1
                continue
            if port["kind"] == "REGISTERED_ENTRANCE":
                a, b = grid_id, node
                segment = LineString([target, xy])
            else:
                a, b = node, grid_id
                candidate_graph.add_edge(a, b)
            edge_kind = TERMINAL_EDGE if port["kind"] == "REGISTERED_ENTRANCE" else AREA_EDGE
            candidates.append((a, b, segment, edge_kind, port, gates, exceptions))
        rejected.update(failures)
        port["local_rejections"] = dict(failures)
        port["reason"] = "NO_LOCAL_PORT_WITHIN_MAX_LENGTH" if not candidates else "PORT_PENDING_REACHABILITY"
        if not candidates:
            rejected[port["reason"]] += 1
        accepted.extend(candidates)

    contacts = {p["id"] for p in ground if p["kind"] == "NATIVE_CONTACT" and p["id"] in candidate_graph}
    reachable = set()
    for contact in sorted(contacts):
        if contact not in reachable:
            reachable |= nx.node_connected_component(candidate_graph, contact)
            outcome["retained_components"] += 1
    retained = [r for r in accepted if r[0] in reachable and (
                r[1] in reachable or (r[4] is not None and r[4]["kind"] == "REGISTERED_ENTRANCE"))]
    rejected["NO_COMPONENT_WITH_NATIVE_CONTACT"] += len(accepted) - len(retained)
    if not retained:
        outcome["area_status"] = "NO_ATTACHED_EDGE_COMPONENT"

    retained_nodes = {n for r in retained for n in r[:2]}
    outcome["nodes"] = {k: v for k, v in nodes.items() if k in retained_nodes}
    all_obstacles = STRtree([obj["geometry"] for obj in nearby]) if nearby else None
    distances = {}
    if retained and all_obstacles is not None:
        ix, ds = all_obstacles.query_nearest([r[2] for r in retained], return_distance=True, all_matches=False)
        distances = {int(i): (float(d), nearby[int(j)]["id"]) for i, j, d in zip(ix[0], ix[1], ds)}
    for i, (u, v, segment, kind, port, gates, exceptions) in enumerate(retained):
        edge_id = f"{area_id}:edge/{i+1:06d}"
        if port is not None:
            port["edge_ids"].append(edge_id)
            port["status"] = "ATTACHED"
            port["reason"] = "FULL_SEGMENT_VALIDATED"
        measured, nearest = distances.get(i, (None, None))
        outcome["edges"].append(dict(
            edge_id=edge_id, u=u, v=v, kind=kind,
            direction="U_TO_V" if port and port["kind"] == "REGISTERED_ENTRANCE" else "BIDIRECTIONAL",
            source_area_id=area_id, source_tags=tags, coordinates_metric=list(segment.coords),
            length_m=segment.length, clearance_m=measured, nearest_obstacle_id=nearest,
            obstacle_ids=list(exceptions), gate_ids=sorted(set(gates)), model_assumption=SURFACE_ASSUMPTION,
            method_version=METHOD, coverage="FULL_SEGMENT_IN_SOURCE_BAND" if port else "FULL_SEGMENT_IN_ALLOWED_DOMAIN",
            native_port_id=port.get("source_node_id") if port else None,
            native_port_kind=port.get("kind") if port else None,
            native_port_original_xy=port.get("xy") if port else None,
            native_port_source_way_ids=port.get("source_way_ids", []) if port else [],
            clearance_rule_m=margin, clearance_exception=bool(exceptions),
            clearance_exception_rule="ONLY_ORIGINAL_REGISTERED_DOOR_AT_OWN_BUILDING_BOUNDARY" if exceptions else None,
            edge_band_width_m=width))
    for port in ground:
        if port["reason"] == "PORT_PENDING_REACHABILITY":
            port["reason"] = "NO_COMPONENT_WITH_NATIVE_CONTACT"
    outcome["rejected"] = {key: count for key, count in sorted(rejected.items()) if count}
    return outcome
