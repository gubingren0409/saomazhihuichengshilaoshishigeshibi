"""Run the R4-REV1 frozen regression and conditional area-edge experiments offline."""
from collections import Counter
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from time import perf_counter

import networkx as nx
from shapely.geometry import mapping
from shapely.ops import transform

from .area_model import derive
from .native_adapter import BASELINE_FIELDS, GEOD, INVERSE, PROJECT, Source, grounded_lines, load_frozen_engine, node_id
from .route_measure import (DERIVED, GAP, NATIVE, TERMINAL, area_graph, closest_reachable, describe, feature,
                            gap_evidence, key, line_feature, obstacle_index, overlay, prepare_weights,
                            statistics, walk)

ROOT = Path(__file__).resolve().parents[1]
MAIN = "R1_AREA_EDGE_MAIN"
H0 = "H0_FROZEN_B0"
H1 = "H1_R4_STRICT_LINES"
ABLATE = "R1_WITHOUT_DERIVED_EDGES"
NORTH = "NORTH_APPROACH_AUDIT"
HOSTED = "HISTORICAL_HOSTED_BASELINE"
NAMES = {3.0: MAIN, 1.0: "R1_WIDTH_1M", 5.0: "R1_WIDTH_5M"}
ARTIFACTS = ("runs/experiment.json", "runs/resource_use.json", "data/source_manifest.json",
             "data/derived_edges.geojson", "data/edge_evidence.jsonl", "data/allowed_domains.geojson",
             "data/routes.geojson", "data/entrance_approach.json")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(root, relative, data, jsonl=False):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        if jsonl:
            for row in data:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        else:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def checked_manifest(root):
    manifest = read(root / "BASELINE_MANIFEST.json")
    for entry in manifest["entries"]:
        path = root / entry["path"]
        if not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"Frozen source integrity changed: {entry['path']}")
    return manifest


def historic_route(path):
    result = read(path)
    return result["route"] if "route" in result else result


def route_ref(run, scene, door=None, contact=None):
    return ":".join([run, scene, *([door] if door else []), *([contact] if contact else [])])


def native_signature(graph):
    nodes = sorted((str(n), list(d["coord"])) for n, d in graph.nodes(data=True))
    edges = sorted((str(a), str(b), d.get("osm_way_id") or -1, d.get("segment_index") or -1,
                    d["length_m"], d["route_weight_m"]) for a, b, d in graph.edges(data=True))
    return sha256(json.dumps([nodes, edges], separators=(",", ":")).encode("utf-8")).hexdigest()


def baseline(scene, raw, engine, frozen_root, routes, snap_m):
    ident = scene["scene_id"]
    current = engine.route_osm(raw, scene["start"], scene["target"], snap_m)
    old = historic_route(frozen_root / scene["historical_local_route"])
    equal = [name for name in BASELINE_FIELDS if current.get(name) == old.get(name)]
    if len(equal) != len(BASELINE_FIELDS):
        raise ValueError(f"{ident} frozen baseline mismatch: {set(BASELINE_FIELDS) - set(equal)}")
    result = {k: current[k] for k in ("status", "failure_reason", "length_m", "route_start", "route_end", "snap_end_m")}
    result.update(scene_id=ident, matches_frozen=True, matched_fields=equal,
                  frozen_source=scene["historical_local_route"], strict_entrances={})
    if current["geometry"]:
        routes.append(feature(current["geometry"], run_id=H0, scene_id=ident, kind=NATIVE,
                              route_id=route_ref(H0, ident), status=current["status"], historical_snap=True))
    if scene.get("historical_local_diagnostic"):
        approach = historic_route(frozen_root / scene["historical_local_diagnostic"])
        if approach.get("geometry"):
            routes.append(feature(approach["geometry"], run_id=H0, scene_id=ident, kind="HISTORICAL_LOCAL_APPROACH",
                                  route_id=route_ref(H0, ident, "original-diagnostic"),
                                  status="APPROACH_WITH_GAP", length_m=approach["length_m"]))
    provider = read(frozen_root / scene["historical_hosted_route"])
    hosted = {"scene_id": ident, "status": "HISTORICAL_HOSTED_BASELINE",
              "source": scene["historical_hosted_route"], "internal_graph": "UNKNOWN",
              "area_augmentation": "NOT_EXECUTABLE_MISSING_INPUT"}
    source_parts = []
    for i, row in enumerate(provider["features"]):
        g = row["geometry"]
        source_parts.extend(g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]])
        routes.append(feature(g, run_id=HOSTED, scene_id=ident, kind=HOSTED,
                              route_id=route_ref(HOSTED, ident), route_section=i,
                              status=HOSTED, source=scene["historical_hosted_route"]))
    if source_parts:
        end = source_parts[-1][-1]
        hosted.update(endpoint=end, target_gap_m=math.dist(PROJECT(*end), PROJECT(*scene["target"])),
                      length_geodesic_m=sum(GEOD.line_length(*zip(*p)) for p in source_parts))
    return result, hosted


def entrance_result(scene, entry, rows, run, routes, idx, contact_id=None):
    ident = scene["scene_id"]
    native = entry["native_id"]
    result = describe(rows, entry["coordinate"], route_ref(run, ident, native, contact_id),
                      ident, run, native, routes, idx, scene["building_native_id"], contact_id)
    result.update(exterior_approach=result["status"], entrance_role=entry["entrance_type"],
                  inbound_eligibility=("ELIGIBLE_CONDITIONAL" if result["status"] == "EXTERIOR_REACHED_CONDITIONAL"
                                       else "REGISTERED_ROLE_SUITABLE_ROUTE_REQUIRED") if entry["eligible"]
                  else ("NOT_ELIGIBLE_EXIT" if entry["entrance_type"] == "exit" else "NOT_CONFIRMED"),
                  original_source=entry["native_id"], source_tags=entry["tags"],
                  entrance_coordinate_unchanged=True, physical_access="UNKNOWN")
    return result


def north_result(graph, source, scene, entry, origin, north_area, allowed_areas, native_lines,
                 obstacles, idx, run, routes):
    exact = walk(graph, origin, key(entry["native_id"]))
    result = entrance_result(scene, entry, exact, run, routes, idx)
    raw_shape = source.area(north_area)
    result["north_source_area_id"] = north_area
    result["source_face_gap_m"] = raw_shape.distance(source_point(source, entry)) if raw_shape else None
    if exact:
        return result
    closest = closest_reachable(graph, source, origin, entry["coordinate"], north_area)
    if closest is None:
        return result
    prefix, coords, attrs = closest
    rid = route_ref(run, scene["scene_id"], entry["native_id"], "approach")
    approached = describe(prefix, entry["coordinate"], rid, scene["scene_id"], run, entry["native_id"],
                          routes, idx, scene["building_native_id"], forced_status="APPROACH_WITH_GAP")
    for field in ("status", "route_id", "origin", "endpoint", "gap_m", "gap_geodesic_m", "length_m",
                  "length_geodesic_m", "section_lengths_m", "route_sections", "obstacle_conflicts", "continuous"):
        result[field] = approached.get(field)
    result.update(status="APPROACH_WITH_GAP", exterior_approach="APPROACH_WITH_GAP",
                  support_status="GAP_UNSUPPORTED", reachable_network_position=coords,
                  reachable_edge=attrs.get("edge_id") or f"way/{attrs['osm_way_id']}",
                  north_source_area_id=north_area)
    gap = gap_evidence(source, entry["coordinate"], coords, north_area, allowed_areas, native_lines, obstacles)
    result["gap_evidence"] = gap
    routes.append(line_feature([coords, entry["coordinate"]], run_id=run, scene_id=scene["scene_id"], route_id=rid,
                               kind=GAP, entrance_id=entry["native_id"], length_m=gap["length_m"],
                               status="GAP_UNSUPPORTED", routable=False, source_area_id=north_area))
    return result


def source_point(source, entry):
    from shapely.geometry import Point
    return Point(PROJECT(*entry["coordinate"]))


def ablate(graph, base, origin):
    cleaned = graph.copy()
    added = [(u, v, k) for u, v, k, e in cleaned.edges(keys=True, data=True) if e["kind"] != NATIVE]
    cleaned.remove_edges_from(added)
    cleaned.remove_nodes_from(n for n in list(cleaned) if n not in base)
    left, right = native_signature(base), native_signature(cleaned)
    if left != right or statistics(cleaned, origin) != statistics(base, origin):
        raise ValueError("Ablation failed to restore frozen graph")
    return cleaned, dict(removed_directed_edges=len(added), native_signature_before=left, native_signature_after=right,
                         same_topology_and_native_weights=True)


def execute(input_root, output_root, config_path):
    existing = [name for name in ARTIFACTS if (output_root / name).exists()]
    if existing:
        raise FileExistsError(f"Output run already exists at {output_root}: {', '.join(existing)}")
    if output_root == input_root or output_root.is_relative_to(input_root):
        raise ValueError("Run output must be outside the protected input root")
    started = perf_counter()
    source_manifest = checked_manifest(input_root)
    hashes = {row["path"]: row["sha256"] for row in source_manifest["entries"]}
    config = read(config_path)
    if config["phase"] != "LOCKED_BEFORE_REAL_ROUTE_EVALUATION" or config["widths_m"] != [3.0, 1.0, 5.0]:
        raise ValueError("Expected locked three-configuration protocol")
    run_timings = []
    source_contract = read(input_root / "runs/source_scene_contracts.json")
    cases = source_contract["scenes"]
    legacy = {s["scene_id"]: s for s in read(input_root / "runs/experiment.json")["scenes"]}
    engine = load_frozen_engine(input_root)
    runs = {H0: {"scenes": []}, H1: {"scenes": []}, **{r: {"scenes": []} for r in NAMES.values()},
            ABLATE: {"scenes": []}, NORTH: {"scenes": []}, HOSTED: {"scenes": []}}
    routes, domains, added_edges, edge_evidence = [], [], [], []
    museum = config["museum"]
    approach_report = {}
    for scene in cases:
        t0 = perf_counter()
        scene_id = scene["scene_id"]
        source_raw = read(input_root / scene["osm_clip"])
        source = Source(source_raw)
        old, hosted = baseline(scene, source_raw, engine, input_root, routes, config["baseline_snap_m"])
        runs[H0]["scenes"].append(old)
        runs[HOSTED]["scenes"].append(hosted)
        h1 = legacy[scene_id]
        if h1["verified_b1_edges"] != 0 or h1["verified_b2_additional_edges"] != 0:
            raise ValueError("Old R4 comparison is no longer the sealed zero-addition run")
        runs[H1]["scenes"].append(dict(scene_id=scene_id, status="OBSERVED_FROZEN_R4_STRICT_LINES",
                                      source="runs/experiment.json", added_edges=0,
                                      variants=h1["variants"], focus_space_ids=h1["focus_space_ids"]))
        segments, endings, _ = engine._segments(source_raw)
        base, _ = engine._build_graph(segments, endings, ())
        prepare_weights(base)
        origin = key(scene["start_native_id"])
        if origin not in base or list(base.nodes[origin]["coord"]) != scene["start"]:
            raise ValueError(f"Frozen origin not exact on source graph: {scene_id}")
        entries = scene["r4_entrances"]
        for entry in entries:
            if list(source.coord(entry["native_id"])) != entry["original_coordinate"]:
                raise ValueError("Registered door coordinates changed")
        focus = list(scene["r4_focus_space_ids"]) + config["focus_additions"].get(scene_id, [])
        shapes = {area: source.area(area) for area in focus}
        obstacles, unlocated = source.obstacles([])
        idx = obstacle_index(obstacles)
        source_native_lines = grounded_lines(source, segments)
        permitted_shapes = [(a, p) for a, p in shapes.items() if p is not None and source.obj(a)["tags"].get("highway") == "pedestrian"
                            and source.obj(a)["tags"].get("layer") in (None, "", "0")]
        original_ports = {area: source.ports(area, segments, entries, base) for area in focus if shapes[area] is not None}
        base_stats = statistics(base, origin)
        old.update(graph=base_stats, native_signature=native_signature(base))
        north_entry = next((e for e in entries if scene_id == museum["scene_id"] and e["native_id"] == museum["north_entrance"]), None)
        north_base = None
        for entry in entries:
            if entry is north_entry:
                north_base = north_result(base, source, scene, entry, origin, museum["north_area"], permitted_shapes,
                                          source_native_lines, obstacles, idx, H0, routes)
                old["strict_entrances"][entry["native_id"]] = north_base
            else:
                old["strict_entrances"][entry["native_id"]] = entrance_result(
                    scene, entry, walk(base, origin, key(entry["native_id"])), H0, routes, idx)
        for width in config["widths_m"]:
            t1 = perf_counter()
            run = NAMES[width]
            active = dict(config, width_m=width)
            graphs, models, area_summaries = {}, {}, []
            for area in focus:
                shape = shapes[area]
                if shape is None:
                    area_summaries.append(dict(area_id=area, status="UNRESOLVED_SOURCE_AREA_GEOMETRY",
                                               graph_edges_unique=0, graph_edges_directed=0))
                    continue
                port_list, ignored = original_ports[area]
                tags = source.obj(area).get("tags", {})
                nearby = shape.buffer(30)
                area_obs = [obj for obj in obstacles if obj["geometry"].intersects(nearby)]
                model = derive(area, tags, shape, area_obs, port_list, active, source_native_lines)
                models[area] = model
                graph = area_graph(source, model)
                graphs[area] = graph
                domain = model["domain"]
                if not domain.is_empty:
                    domains.append(feature(mapping(transform(INVERSE, domain)), run_id=run, width_m=width,
                                           scene_id=scene_id, kind="ALLOWED_EDGE_BAND", source_area_id=area,
                                           source_tags=tags, area_m2=domain.area))
                status_counts = dict(Counter(row["kind"] for row in model["edges"]))
                native_port_status = model["port_results"]
                area_summaries.append(dict(
                    area_id=area, status=model["area_status"], source_tags=tags, band_area_m2=domain.area,
                    source_area_m2=shape.area, candidate_graph_nodes=model["candidate_graph_nodes"], candidate_graph_edges=model["candidate_graph_edges"], retained_components=model["retained_components"], graph_nodes=graph.number_of_nodes(),
                    graph_edges_unique=len(model["edges"]), graph_edges_directed=graph.number_of_edges(),
                    edge_kind_counts=status_counts, rejected=dict(model["rejected"]),
                    deduplicated=model["deduplicated"], ports=native_port_status, incompatible_layer_contacts=ignored,
                    known_obstacle_ids=[obj["id"] for obj in area_obs],
                    local_unknown_obstacle_ids=[obj["id"] for obj in area_obs if obj["kind"] == "UNKNOWN"],
                    globally_unlocated_obstacle_ids=unlocated,
                    base_reachable_native_contacts=sum(nx.has_path(base, origin, key(p["id"]))
                                                       for p in port_list if p["kind"] == "NATIVE_CONTACT"),
                    derived_attached_native_contacts=sum(key(p["id"]) in graph and graph.degree(key(p["id"])) > 0
                                                         for p in port_list if p["kind"] == "NATIVE_CONTACT"),
                ))
                if run == MAIN:
                    for edge in model["edges"]:
                        payload = dict(edge, run_id=run, width_m=width, scene_id=scene_id,
                                       qualified_id=f"{scene_id}:{edge['edge_id']}",
                                       parent_input_sha256=hashes[scene["osm_clip"]],
                                       method_version=config["contract"],
                                       model_assumptions=["TAGGED_PEDESTRIAN_FACE_CONDITIONAL", "OUTDOOR_SURFACE_IF_UNTAGGED"])
                        del payload["coordinates_metric"]
                        coords = [source.coord(k) if k.startswith("node/") else INVERSE(*xy)
                                  for k, xy in zip((edge["u"], edge["v"]), edge["coordinates_metric"])]
                        residual = max(math.dist(PROJECT(*ll), xy) for ll, xy in zip(coords, edge["coordinates_metric"]))
                        if residual > config["tolerance_m"]:
                            raise ValueError("Output CRS round-trip exceeds the frozen tolerance")
                        payload["crs_roundtrip_residual_m"] = residual
                        edge_evidence.append(dict(payload, coordinates_wgs84=coords,
                                                  coordinates_metric=edge["coordinates_metric"]))
                        keys = ("edge_id", "qualified_id", "run_id", "width_m", "scene_id", "kind",
                                "source_area_id", "length_m", "direction", "native_port_id",
                                "clearance_m", "model_assumptions", "source_tags", "u", "v", "gate_ids")
                        added_edges.append(line_feature(coords, **{k: payload.get(k) for k in keys}))
            augmented = overlay(base, graphs.values())
            summary = dict(scene_id=scene_id, run_id=run, width_m=width, areas=area_summaries,
                           graph=statistics(augmented, origin), native_graph=base_stats,
                           truly_added_edges_unique=sum(a["graph_edges_unique"] for a in area_summaries),
                           truly_added_edges_directed=sum(a["graph_edges_directed"] for a in area_summaries),
                           entrances={}, south_contacts=[])
            runs[run]["scenes"].append(summary)
            for entry in entries:
                door = entry["native_id"]
                if scene_id == museum["scene_id"] and door == museum["south_entrance"]:
                    south_area = museum["south_area"]
                    model = models.get(south_area)
                    derived = graphs.get(south_area)
                    native_contacts = [p for p in original_ports[south_area][0] if p["kind"] == "NATIVE_CONTACT"]
                    ids = [p["id"] for p in native_contacts]
                    if sorted(ids) != sorted(museum["expected_south_contacts"]):
                        raise ValueError(f"South native boundary contacts disagree with source contract: {ids}")
                    for port in native_contacts:
                        contact = port["id"]
                        before = walk(base, origin, key(contact))
                        after = walk(derived, key(contact), key(door)) if derived is not None else None
                        joined = before + after if before is not None and after is not None else None
                        result = entrance_result(scene, entry, joined, run, routes, idx, contact)
                        result.update(native_origin_contact_reachable=before is not None,
                                      contact_coordinate=source.coord(contact), contact_source_way_ids=port["source_way_ids"],
                                      derived_contact_to_door_connected=after is not None,
                                      contact_port_status=model["port_results"].get(contact) if model else None,
                                      terminal_port_status=model["port_results"].get(door) if model else None,
                                      failure_reason=(None if joined else "NO_NATIVE_PREFIX" if before is None else "NO_DERIVED_PATH_CONTACT_TO_DOOR"))
                        summary["south_contacts"].append(result)
                    successful = [r for r in summary["south_contacts"] if r["status"] == "EXTERIOR_REACHED_CONDITIONAL"]
                    selected = min(successful, key=lambda row: (row["length_m"], row["contact_id"]), default=None)
                    summary["entrances"][door] = dict(selected, selected_from=ids) if selected else entrance_result(
                        scene, entry, None, run, routes, idx)
                    if run == MAIN:
                        approach_report["south"] = dict(selected=selected, all_contacts=summary["south_contacts"],
                                                        area_id=south_area, original_door=entry)
                elif entry is north_entry:
                    result = north_result(augmented, source, scene, entry, origin, museum["north_area"],
                                          permitted_shapes, source_native_lines, obstacles, idx, run, routes)
                    summary["entrances"][door] = result
                    if run == MAIN:
                        north = dict(scene_id=scene_id, old=north_base, main=result, original_door=entry,
                                     area=next(a for a in area_summaries if a["area_id"] == museum["north_area"]))
                        runs[NORTH]["scenes"].append(north)
                        approach_report["north"] = north
                else:
                    result = entrance_result(scene, entry, walk(augmented, origin, key(door)), run, routes, idx)
                    summary["entrances"][door] = result
                    if run == MAIN:
                        approach_report["library"] = dict(old=old["strict_entrances"][door], main=result)
            if run == MAIN:
                cleaned, deletion = ablate(augmented, base, origin)
                deletion.update(scene_id=scene_id, graph=statistics(cleaned, origin), entrances={})
                for entry in entries:
                    door = entry["native_id"]
                    result = (north_result(cleaned, source, scene, entry, origin, museum["north_area"], permitted_shapes,
                                           source_native_lines, obstacles, idx, ABLATE, routes) if entry is north_entry
                              else entrance_result(scene, entry, walk(cleaned, origin, key(door)), ABLATE, routes, idx))
                    expected = old["strict_entrances"][door]
                    if any(result[k] != expected[k] for k in ("status", "endpoint", "gap_m", "length_m")):
                        raise ValueError(f"Ablation changed strict baseline route {scene_id} {door}")
                    deletion["entrances"][door] = result
                deletion["same_strict_entrances"] = True
                runs[ABLATE]["scenes"].append(deletion)
            run_timings.append(dict(scene_id=scene_id, run_id=run, elapsed_s=round(perf_counter()-t1, 6)))
        run_timings.append(dict(scene_id=scene_id, run_id="SCENE_TOTAL", elapsed_s=round(perf_counter()-t0, 6)))
        print(json.dumps(dict(scene_id=scene_id, baseline=old["status"], figures=len(routes),
                              added_main=runs[MAIN]["scenes"][-1]["truly_added_edges_unique"]), ensure_ascii=False), flush=True)
    if checked_manifest(input_root) != source_manifest:
        raise ValueError("Frozen baseline changed during execution")
    experiment = dict(status="EXECUTED_MAP_CONDITIONAL", method_version=config["contract"], config=config,
                      config_sha256=digest(config_path), source_archive_sha256=source_manifest["original_archive_sha256"],
                      source_inputs_verified=len(source_manifest["entries"]), case_catalog=cases,
                      runs=runs, route_weight_unit="EPSG:32651_METRES_WITH_WGS84_GEODESIC_RECOMPUTATION",
                      external_requests=0, field_checks=0, user_review="PENDING_NATURAL_LANGUAGE_REVIEW",
                      code="src/run_rev1.py", edge_export_scope="MAIN_3M_ALL_FORMAL_EDGES")
    write(output_root, "data/source_manifest.json", source_manifest)
    write(output_root, "data/derived_edges.geojson", fc(added_edges))
    write(output_root, "data/edge_evidence.jsonl", edge_evidence, jsonl=True)
    write(output_root, "data/allowed_domains.geojson", fc(domains))
    write(output_root, "data/routes.geojson", fc(routes))
    write(output_root, "data/entrance_approach.json", approach_report)
    write(output_root, "runs/resource_use.json", dict(elapsed_s=round(perf_counter()-started, 6), per_scene_variant=run_timings,
                                                       note="Timing is runtime-specific and is excluded from deterministic hashes."))
    write(output_root, "runs/experiment.json", experiment)
    return experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=ROOT / "frozen_r4")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/rev1_main.json")
    args = parser.parse_args()
    execute(args.input_root.resolve(), args.output_root.resolve(), args.config.resolve())


if __name__ == "__main__":
    main()
