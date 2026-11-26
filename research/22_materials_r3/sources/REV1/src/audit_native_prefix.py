"""Independent run supplement for coincident edges and alternate native-only obstacle diagnostics."""
from collections import Counter
import argparse
import math
from pathlib import Path

import networkx as nx
from .area_model import area_reason
from .native_adapter import PROJECT, Source, grounded_lines, load_frozen_engine
from .route_measure import (GAP, closest_reachable, describe, gap_evidence, key, line_feature,
                            obstacle_index, path_conflicts, prepare_weights, walk)
from .run_rev1 import MAIN, ROOT, fc, native_signature, read, write

RUN = "DIAGNOSTIC_B0_OBSTACLE_VIEW"


def geometry_audit(path):
    seen = {}
    count, duplicates = Counter(), Counter()
    with path.open(encoding="utf-8") as handle:
        import json
        for line in handle:
            row = json.loads(line)
            scene = row["scene_id"]
            key = (scene, tuple(sorted(tuple(p) for p in row["coordinates_metric"])))
            count[scene] += 1
            if key in seen:
                duplicates[(scene, seen[key], row["source_area_id"])] += 1
            seen.setdefault(key, row["source_area_id"])
    repeated = sum(duplicates.values())
    return dict(edge_records=sum(count.values()), exact_unique_segment_geometries=len(seen),
                exact_duplicate_segment_records=repeated, source_records_by_scene=dict(count),
                duplicate_pairs=[dict(scene_id=s, first_area=a, repeated_area=b, records=n)
                                 for (s, a, b), n in sorted(duplicates.items())])


def native_view(graph, index):
    blocked, reasons = set(), Counter()
    for u, v, k, row in graph.edges(keys=True, data=True):
        r = dict(row, a_xy=graph.nodes[u]["xy"], b_xy=graph.nodes[v]["xy"],
                 a=graph.nodes[u]["coord"], b=graph.nodes[v]["coord"])
        hits = path_conflicts([r], index, (0, 0), None)
        if hits:
            blocked.add((u, v, k))
            reasons.update(ident for ids in hits.values() for ident in ids)
    return nx.subgraph_view(graph, filter_edge=lambda u, v, k: (u, v, k) not in blocked), blocked, reasons


def case_geometry(route_id, source_routes, output, new_id):
    """Retain the original computed suffix, omitting only the original native prefix."""
    length = 0
    for row in source_routes:
        p = row["properties"]
        if p.get("route_id") != route_id or p["kind"] not in {
            "DERIVED_FROM_TAGGED_PEDESTRIAN_AREA", "DERIVED_TERMINAL_CONNECTOR"
        }:
            continue
        out = dict(p, run_id=RUN, route_id=new_id, source_route_id=route_id,
                   route_section=p["route_section"], status="FROZEN_FIRST_RUN_DERIVED_SUFFIX")
        output.append(dict(row, properties=out))
        length += p["length_m"]
    return length


def execute(input_root, output_root, result_root):
    outputs = ("data/native_prefix_diagnostic.json", "data/native_prefix_diagnostic.geojson",
               "runs/edge_geometry_audit.json")
    if any((output_root / name).exists() for name in outputs):
        raise FileExistsError("Preserve first diagnostic; choose a new output root.")
    experiment = read(result_root / "runs/experiment.json")
    approach = read(result_root / "data/entrance_approach.json")
    model_routes = read(result_root / "data/routes.geojson")["features"]
    scope = experiment["config"]["museum"]
    scene = next(s for s in experiment["case_catalog"] if s["scene_id"] == scope["scene_id"])
    engine = load_frozen_engine(input_root)
    raw = read(input_root / scene["osm_clip"])
    source = Source(raw)
    segments, endings, _ = engine._segments(raw)
    graph, _ = engine._build_graph(segments, endings, ())
    prepare_weights(graph)
    before = native_signature(graph)
    obstacles, _ = source.obstacles([])
    idx = obstacle_index(obstacles)
    filtered, blocked, reasons = native_view(graph, idx)
    origin = key(scene["start_native_id"])
    records, features = [], []
    by_obstacle = {x["id"]: x["tags"] for x in obstacles}
    for result in approach["south"]["all_contacts"]:
        if not result["obstacle_conflicts"]:
            continue
        contact = result["contact_id"]
        rid = f"{RUN}:{contact}"
        rows = walk(filtered, origin, key(contact))
        new = describe(rows, result["contact_coordinate"], rid, scene["scene_id"], RUN, contact, features, idx,
                       scene["building_native_id"], contact_id=contact)
        suffix = case_geometry(result["route_id"], model_routes, features, rid) if rows else None
        records.append(dict(
            subject="SOUTH_CONTACT", contact_id=contact, first_run_route=result["route_id"],
            first_run_full_length_m=result["length_m"], first_run_obstacle_ids=result["obstacle_conflicts"],
            first_run_obstacle_tags={ident: by_obstacle[ident] for ids in result["obstacle_conflicts"].values() for ident in ids},
            alternate_native_prefix=new, unchanged_derived_suffix_m=suffix,
            total_m=new["length_m"] + suffix if rows else None,
            original_registered_entrance=result["original_coordinate"],
            comparison="DIAGNOSTIC_ONLY_NATIVE_FILTER_RETAINS_FIRST_RUN_SELECTION"))
    north = approach["north"]["main"]
    original_door = approach["north"]["original_door"]
    target = original_door["original_coordinate"]
    prefix_result = closest_reachable(filtered, source, origin, target, scope["north_area"])
    eligible = []
    areas = []
    for ident in (scope["south_area"], scope["north_area"]):
        geom = source.area(ident)
        reason = area_reason(source.obj(ident).get("tags", {}), geom)
        eligible.append(dict(source_area_id=ident, passes_source_semantics=reason is None, reason=reason))
        if not reason:
            areas.append((ident, geom))
    if prefix_result:
        rows, point, edge = prefix_result
        rid = f"{RUN}:NORTH"
        alt = describe(rows, target, rid, scene["scene_id"], RUN, original_door["native_id"], features,
                       idx, scene["building_native_id"], forced_status="APPROACH_WITH_GAP")
        gap = gap_evidence(source, target, point, scope["north_area"], areas, grounded_lines(source, segments), obstacles)
        alt.update(gap_evidence=gap, reachable_edge=f"way/{edge['osm_way_id']}",
                   inbound_eligibility="NOT_ELIGIBLE_EXIT",
                   same_nearest_point_within_1mm=math.dist(PROJECT(*point), PROJECT(*north["endpoint"])) <= 0.001)
        features.append(line_feature([point, target], run_id=RUN, scene_id=scene["scene_id"], route_id=rid, kind=GAP,
                                     entrance_id=original_door["native_id"], routable=False, status="GAP_UNSUPPORTED",
                                     source_area_id=scope["north_area"], length_m=gap["length_m"]))
    else:
        alt = dict(status="NO_CONFLICT_FREE_PREFIX", inbound_eligibility="NOT_ELIGIBLE_EXIT")
    records.append(dict(subject="NORTH_APPROACH", first_run_route=north["route_id"],
                        first_run_obstacle_ids=north["obstacle_conflicts"],
                        first_run_obstacle_tags={ident: by_obstacle[ident] for ids in north["obstacle_conflicts"].values() for ident in ids},
                        alternate=alt, source_area_semantics=eligible))
    after = native_signature(graph)
    if before != after:
        raise ValueError("Frozen native graph was changed by diagnostics")
    result = dict(id=RUN, study_type="DIAGNOSTIC_ONLY_NOT_BASELINE_OR_GEOMETRY_CONFIG",
                  selection_unchanged=True, removed_from_query_view_only=len(blocked),
                  frozen_graph_signature_before=before, frozen_graph_signature_after=after,
                  obstacle_match_counts=dict(reasons), records=records)
    write(output_root, outputs[0], result)
    write(output_root, outputs[1], fc(features))
    write(output_root, outputs[2], geometry_audit(result_root / "data/edge_evidence.jsonl"))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-root", type=Path, default=ROOT / "frozen_r4")
    p.add_argument("--result-root", type=Path, default=ROOT)
    p.add_argument("--output-root", type=Path, required=True)
    a = p.parse_args()
    execute(a.input_root.resolve(), a.output_root.resolve(), a.result_root.resolve())


if __name__ == "__main__":
    main()
