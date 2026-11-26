"""Replay S0/S1 on all frozen clips, then route to fixed northern and southern targets."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
from time import perf_counter

import networkx as nx
from shapely.geometry import LineString, Point, mapping
from shapely.ops import transform

from inputs.rev1.src.native_adapter import GEOD, INVERSE, PROJECT
from inputs.rev1.src.route_measure import DERIVED, NATIVE, TERMINAL, key, overlay, statistics, walk
from .semantics import EPS, KEEP, build_native, load_area_graph, read, segment_decision

ROOT = Path(__file__).resolve().parents[1]
MUSEUM = "sh-huangpu-01"
REGRESSION_WAYS = {178722057, 178723091, 178725152, 178725158}
REGRESSION_GRASS = "way/178732700"
UNCHANGED_WAYS = (654297629, 1074409256)
SOUTH_AREA = "relation/2385771"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def geo_feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def geo_line(points, **properties):
    return geo_feature({"type": "LineString", "coordinates": points}, **properties)


def split_native_edge(graph, way, segment, pos):
    """Insert the fixed comparison point on its exact source edge, preserving direction."""
    xy = PROJECT(*pos)
    matches = [(u, v, k, a) for u, v, k, a in graph.edges(keys=True, data=True)
               if a.get("osm_way_id") == way and a.get("segment_index") == segment]
    if not matches:
        return graph, None
    sample_u, sample_v, _, _ = matches[0]
    for n in (sample_u, sample_v):
        if math.dist(xy, graph.nodes[n]["xy"]) <= EPS:
            return graph, n
    seg = LineString((graph.nodes[sample_u]["xy"], graph.nodes[sample_v]["xy"]))
    if seg.distance(Point(xy)) > EPS:
        raise ValueError("Fixed baseline point lies off its frozen source edge")
    new = graph.copy()
    target = ("frozen_north_query_point", way, segment)
    new.add_node(target, xy=xy, coord=tuple(pos))
    for u, v, k, attrs in matches:
        new.remove_edge(u, v, k)
        for a, b in ((u, target), (target, v)):
            original = dict(attrs)
            original["route_weight_m"] = math.dist(new.nodes[a]["xy"], new.nodes[b]["xy"])
            original["length_m"] = GEOD.inv(*new.nodes[a]["coord"], *new.nodes[b]["coord"])[2]
            new.add_edge(a, b, **original)
    return new, target


def recheck_native(rows, build, mode):
    for edge in rows:
        way = edge.get("osm_way_id")
        if edge["kind"] != NATIVE or way is None or edge["route_weight_m"] == 0:
            continue
        obj = build.source.ways[way]
        nodes = edge["osm_source_node_ids"]
        tags = tuple(build.source.nodes[n].get("tags", {}) for n in nodes)
        line = LineString((edge["a_xy"], edge["b_xy"]))
        candidates = [build.obstacles[i] for i in build.obstacle_index.query(line, predicate="intersects")]
        result = segment_decision(line, obj.get("tags", {}), candidates, mode,
                                  native_nodes=nodes, endpoint_tags=tags)
        if result["status"] != KEEP:
            raise ValueError(f"Routed native edge failed consistent recheck: {way}, {result}")


def summarize_route(graph, origin, target, coordinates, mode, role, build, features):
    rows = walk(graph, origin, target) if target is not None else None
    if not rows:
        return {"status": "NO_ROUTE", "length_m": None, "target_wgs84": list(coordinates),
                "end_wgs84": None, "native_m": 0, "derived_m": 0,
                "failure": "ENDPOINT_NOT_REACHABLE_IN_THIS_GRAPH"}
    recheck_native(rows, build, mode)
    lengths = defaultdict(float)
    groups = []
    points = [rows[0]["a"]]
    for edge in rows:
        if points[-1] != edge["a"]:
            raise ValueError(f"Discontinuous route in {mode}/{role}")
        points.append(edge["b"])
        if edge["route_weight_m"] == 0:
            continue
        kind = edge["kind"]
        lengths[kind] += edge["route_weight_m"]
        if not groups or kind != groups[-1]["kind"]:
            groups.append({"kind": kind, "coords": [edge["a"]], "length_m": 0, "edge_sources": []})
        group = groups[-1]
        group["coords"].append(edge["b"])
        group["length_m"] += edge["route_weight_m"]
        group["edge_sources"].append(edge.get("edge_id") or f"way/{edge['osm_way_id']}/{edge['segment_index']}")
    if math.dist(PROJECT(*points[-1]), PROJECT(*coordinates)) > EPS:
        raise ValueError(f"Endpoint moved for {mode}/{role}")
    total = sum(lengths.values())
    projected = LineString([PROJECT(*p) for p in points]).length
    if abs(total - projected) > EPS:
        raise ValueError(f"Geometric and graph weights disagree in {mode}/{role}")
    features.append(geo_line(points, role="route", target=role, variant=mode, length_m=total,
                             start_wgs84=points[0], end_wgs84=points[-1]))
    for i, group in enumerate(groups):
        features.append(geo_line(group["coords"], role="route_section", target=role, variant=mode,
                                 sequence=i, kind=group["kind"], length_m=group["length_m"],
                                 source_ids=group["edge_sources"]))
    return {"status": "REACHED_FIXED_ENDPOINT", "length_m": total, "projected_geometry_length_m": projected,
            "geodesic_m": GEOD.line_length(*zip(*points)), "native_m": lengths[NATIVE],
            "derived_m": lengths[DERIVED] + lengths[TERMINAL], "inferred_m": 0.0,
            "target_wgs84": list(coordinates), "end_wgs84": list(points[-1]), "target_residual_m": 0.0,
            "section_lengths_m": dict(lengths), "segment_count": len(rows),
            "recheck": "ALL_NATIVE_EDGES_USE_SAME_RULE", "source_edge_ids": [
                edge.get("edge_id") or f"way/{edge['osm_way_id']}/{edge.get('segment_index')}"
                for edge in rows if edge["route_weight_m"] > 0
            ]}


def compare_audits(builds):
    audit = [{(x["way_id"], x["segment_index"]): x for x in b.audit} for b in builds]
    rows = []
    for way, index in sorted(audit[0].keys() | audit[1].keys()):
        old, new = audit[0].get((way, index)), audit[1].get((way, index))
        ref = old or new
        raw_geometry = LineString([PROJECT(*c) for c in ref["coordinates_wgs84"]])
        grass_ids = sorted({c["source_id"] for row in (old, new) if row for c in row["contacts"]
                            if c["kind"] == "BACKGROUND_GRASS"})
        grass = [o["geometry"] for o in builds[0].obstacles if o["id"] in grass_ids]
        overlap = 0.0
        if grass:
            from shapely.ops import unary_union
            overlap = raw_geometry.intersection(unary_union(grass)).length
        old_status, new_status = (r["status"] if r else KEEP for r in (old, new))
        rows.append({"scene_id": ref["scene_id"], "source_id": f"way/{way}", "way_id": way,
                     "segment_index": index, "native_nodes": ref["native_nodes"], "length_m": ref["length_m"],
                     "background_overlap_m": overlap, "source_grass_ids": grass_ids,
                     "coordinates_wgs84": ref["coordinates_wgs84"], "tags": ref["tags"],
                     "layer_key": ref["layer_key"], "level_key": ref["level_key"],
                     "native_evidence": ref["native_evidence"],
                     "S0_status": old_status, "S1_status": new_status,
                     "S0_reasons": old["reasons"] if old else [], "S1_reasons": new["reasons"] if new else [],
                     "S0_contacts": old["contacts"] if old else [], "S1_contacts": new["contacts"] if new else [],
                     "directions": ref["directions"], "restored": old_status != KEEP and new_status == KEEP})
    return rows


def aggregate(rows):
    restored = [x for x in rows if x["restored"]]
    return dict(audited_segments=len(rows), grass_contact_segments=sum(bool(x["source_grass_ids"]) for x in rows),
                restored_segments=len(restored), restored_native_length_m=sum(x["length_m"] for x in restored),
                restored_grass_overlap_m=sum(x["background_overlap_m"] for x in restored),
                restored_directed_arcs=sum(len(x["directions"]) for x in restored),
                s0_blocked_audited_segments=sum(x["S0_status"] != KEEP for x in rows),
                s1_blocked_audited_segments=sum(x["S1_status"] != KEEP for x in rows),
                s1_reasons=dict(Counter(r for x in rows if x["S1_status"] != KEEP for r in x["S1_reasons"])))


def save_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, separators=(",", ":")) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def execute(root, output=None):
    t0 = perf_counter()
    output = root if output is None else output
    rev = root / "inputs/rev1"
    frozen = rev / "frozen_r4"
    scenes = read(frozen / "runs/source_scene_contracts.json")["scenes"]
    hist_approach = read(rev / "data/entrance_approach.json")
    old_north = read(root / "inputs/north/runs/experiment.json")
    source_binding = old_north["source_geometry"]
    pos = source_binding["approach_wgs84"]
    way = int(source_binding["footway_id"].split("/")[1])
    segment = source_binding["footway_segment_index"]
    results = {}
    rows, features, reports = [], [], []
    museum_rows = None
    for scene in scenes:
        sid = scene["scene_id"]
        builds = [build_native(frozen, scene, mode) for mode in ("S0", "S1")]
        differences = compare_audits(builds)
        rows.extend(differences)
        origin = key(scene["start_native_id"])
        summary = dict(scene_id=sid, **aggregate(differences),
                       graph={mode: {**b.raw_stats, **statistics(b.graph, origin)}
                              for mode, b in zip(("S0", "S1"), builds)})
        reports.append(summary)
        print(sid, "restored", summary["restored_segments"], "blocked",
              summary["s0_blocked_audited_segments"], summary["s1_blocked_audited_segments"], flush=True)
        if sid != MUSEUM:
            continue
        museum_rows = differences
        south_graph = load_area_graph(rev, sid, {SOUTH_AREA})
        source = builds[0].source
        raw_south = hist_approach["south"]["original_door"]
        raw_north = hist_approach["north"]["original_door"]
        source_grass = source.area(REGRESSION_GRASS)
        features.append(geo_feature(mapping(transform(INVERSE, source_grass)), role="source_grass",
                                    source_id=REGRESSION_GRASS, variant="SOURCE", tags=source.obj(REGRESSION_GRASS)["tags"]))
        for way_id in sorted(REGRESSION_WAYS):
            obj = source.ways[way_id]
            features.append(geo_line([source.coord(f"node/{n}") for n in obj["nodes"]], role="source_walkway",
                                     variant="SOURCE", source_id=f"way/{way_id}", tags=obj["tags"]))
        for x in differences:
            if x["way_id"] in REGRESSION_WAYS and x["restored"]:
                features.append(geo_line(x["coordinates_wgs84"], role="restored_edge", variant="S1",
                                         source_id=x["source_id"], segment_index=x["segment_index"],
                                         S0_status=x["S0_status"], S1_status=x["S1_status"], tags=x["tags"],
                                         length_m=x["length_m"], background_overlap_m=x["background_overlap_m"]))
        for mode, build in zip(("S0", "S1"), builds):
            trial, near = split_native_edge(build.graph, way, segment, pos)
            north = summarize_route(trial, origin, near, pos, mode, "north_fixed", build, features)
            south = summarize_route(overlay(build.graph, [south_graph]), origin, key(raw_south["native_id"]),
                                    raw_south["original_coordinate"], mode, "south", build, features)
            north_exit = summarize_route(build.graph, origin, key(raw_north["native_id"]),
                                         raw_north["original_coordinate"], mode, "north_exit", build, features)
            north_exit.update(entrance_role="exit", inbound_eligibility="NOT_ELIGIBLE_EXIT")
            results[mode] = dict(north_fixed=north, south=south, north_exit=north_exit)
        reports[-1]["unchanged_road_policy"] = [
            dict(source_id=f"way/{wid}", tags=source.ways[wid]["tags"],
                 directed_arcs={mode: sum(a.get("osm_way_id") == wid for _, _, a in b.graph.edges(data=True))
                                for mode, b in zip(("S0", "S1"), builds)})
            for wid in UNCHANGED_WAYS
        ]
    if museum_rows is None:
        raise ValueError("Missing frozen museum scene")
    for mode in ("S0", "S1"):
        assert results[mode]["north_fixed"]["status"] == "REACHED_FIXED_ENDPOINT"
        assert results[mode]["south"]["status"] == "REACHED_FIXED_ENDPOINT"
        assert results[mode]["north_exit"]["status"] == "NO_ROUTE"
    dedup = {}
    unique_source = {}
    for row in rows:
        geom = tuple(sorted(map(tuple, row["coordinates_wgs84"])))
        identity = (row["way_id"], row["segment_index"], geom)
        existing = unique_source.get(identity)
        if existing and existing["restored"] != row["restored"]:
            raise ValueError(f"Identical source segment differs across clips: {identity[:2]}")
        unique_source.setdefault(identity, row)
        # A coincident exact segment from a different way is still not independent geometry.
        policy_key = (geom, row["S0_status"], row["S1_status"])
        dedup.setdefault(policy_key, row)
    four = {}
    for way_id in sorted(REGRESSION_WAYS):
        hits = [x for x in museum_rows if x["way_id"] == way_id and REGRESSION_GRASS in x["source_grass_ids"]]
        four[f"way/{way_id}"] = aggregate(hits)
    north_s0 = results["S0"]["north_fixed"]["length_m"]
    north_s1 = results["S1"]["north_fixed"]["length_m"]
    historical = dict(previous_north_r1_n0_m=old_north["variants"]["N0"]["length_m"],
                      rev1_main_north_approach_m=hist_approach["north"]["main"]["length_m"],
                      rev1_selected_south_m=hist_approach["south"]["selected"]["length_m"])
    status = dict(status="PASS", variants=results, historical=historical,
                  fixed_north_approach_improvement_m=north_s0 - north_s1,
                  old_r1_prefix_reproduced=abs(north_s0 - historical["previous_north_r1_n0_m"]) < EPS,
                  south_endpoint_preserved=all(results[m]["south"]["target_residual_m"] == 0 for m in results),
                  four_grass_ways=four, scenes=reports, raw_clip_totals=aggregate(rows),
                  source_identity_dedup=aggregate(list(unique_source.values())),
                  spatial_geometry_policy_dedup=aggregate(list(dedup.values())),
                  units="EPSG:32651 metres", seconds=perf_counter() - t0,
                  external_requests=0, field_checks=0)
    save_csv(output / "data/semantics_edges.csv", rows)
    save_json(output / "data/semantics_routes.geojson", {"type": "FeatureCollection", "features": features})
    save_json(output / "runs/semantics.json", status)
    print(json.dumps({"north_S0_m": north_s0, "north_S1_m": north_s1,
                      "south_S0_m": results["S0"]["south"]["length_m"],
                      "south_S1_m": results["S1"]["south"]["length_m"],
                      "restored_unique_geometry": status["spatial_geometry_policy_dedup"]["restored_segments"],
                      "seconds": status["seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--output-root", type=Path, help="write a fresh replay without overwriting sealed results")
    options = cli.parse_args()
    execute(options.root.resolve(), options.output_root)
