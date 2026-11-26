"""Independently audit the six-clip S0/S1 change using frozen OSM and graph inputs."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import file_digest
import json
import math
from pathlib import Path
import sys

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
WALK = {"footway", "path", "steps", "pedestrian"}
ALLOW = {"yes", "official", "designated", "permissive"}
DENY = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural",
        "forestry", "restricted"}
WATER = {"water", "wetland"}
MUSEUM = "sh-huangpu-01"
REGRESSION = {"way/178722057", "way/178723091", "way/178725152", "way/178725158"}
GRASS = "way/178732700"
EPS = 1e-5


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def assert_close(a, b, label):
    if abs(a - b) > EPS:
        raise ValueError(f"{label}: {a} vs {b}")


def permitted(tags):
    foot = tags.get("foot")
    return (tags.get("locked") != "yes"
            and not any(k.endswith(":conditional") and k.split(":")[0] in {"foot", "access", "oneway"}
                        for k in tags)
            and (foot in ALLOW if foot is not None else tags.get("access") not in DENY))


def layers(tags, first, last):
    values = [{z.strip() for z in t["level"].split(";")} for t in (tags, first, last)
              if t.get("level")]
    if len(values) >= 2 and not set.intersection(*values):
        ramp = tags.get("ramp") not in {None, "", "no", "0", "false"}
        if tags.get("highway") not in {"steps", "elevator"} and not ramp:
            return False
    bridge, tunnel = [tags.get(k) not in {None, "", "no", "0", "false"} for k in ("bridge", "tunnel")]
    try:
        level = float(tags["layer"])
    except (KeyError, ValueError):
        level = None
    return not (bridge and tunnel or level is not None and (bridge and level < 0 or tunnel and level > 0))


def grass_hazard(obj):
    t = obj["tags"]
    return obj["kind"] == "AREA" and permitted(t) and (t.get("landuse") == "grass" or t.get("landcover") == "grass")


def hard_contact(line, row, tags, node_ids):
    g = row["geometry"]
    hit = line.intersection(g)
    if hit.is_empty or grass_hazard(row):
        return False
    if row["kind"] != "BARRIER" and g.geom_type in {"Polygon", "MultiPolygon"} and line.relate_pattern(g, "F********"):
        return False
    if row["kind"] == "BARRIER" and hit.geom_type == "Point":
        for gate in row.get("gates", []):
            if int(gate["id"].split("/")[1]) in node_ids and gate["allowed"] and hit.distance(Point(gate["xy"])) < EPS:
                return False
    t = row["tags"]
    structure = any(tags.get(k) not in {None, "", "no", "0", "false"} for k in ("bridge", "tunnel"))
    if structure and (t.get("natural") in WATER or t.get("water") or
                      t.get("waterway") == "riverbank" or t.get("landuse") in {"reservoir", "basin"}):
        return False
    if structure and row["kind"] in {"BUILDING", "BARRIER"}:
        try:
            if float(t["layer"]) != float(tags["layer"]):
                return False
        except (KeyError, ValueError):
            pass
    return True


def source_key(ident):
    return (int(ident[5:]), "0", "0") if ident.startswith("node/") else ident


def graph_counts(graph, origin):
    components = list(nx.weakly_connected_components(graph))
    return dict(nodes=len(graph), directed_edges=graph.number_of_edges(), weak_components=len(components),
                largest_weak_component=max(map(len, components), default=0),
                reachable_nodes=len(nx.descendants(graph, origin)) + 1 if origin in graph else 0)


def add_frozen_face(graph, evidence_path):
    for line in evidence_path.open(encoding="utf-8-sig"):
        item = json.loads(line)
        if item["scene_id"] != MUSEUM:
            break
        if item["source_area_id"] != "relation/2385771":
            continue
        u, v = (source_key(item[key]) for key in ("u", "v"))
        for node, xy in zip((u, v), item["coordinates_metric"]):
            if node in graph:
                assert_close(math.dist(graph.nodes[node]["xy"], xy), 0, "frozen south connection")
            graph.add_node(node, xy=xy)
        attrs = dict(w=item["length_m"])
        graph.add_edge(u, v, **attrs)
        if item["direction"] == "BIDIRECTIONAL":
            graph.add_edge(v, u, **attrs)


def add_fixed_approach(graph, source_binding):
    way_id = int(source_binding["footway_id"].split("/")[1])
    seg_index = source_binding["footway_segment_index"]
    xy = PROJECT(*source_binding["approach_wgs84"])
    target = "fixed_approach"
    graph.add_node(target, xy=xy)
    edges = [(u, v, key) for u, v, key, e in graph.edges(keys=True, data=True)
             if (e.get("osm_way_id"), e.get("segment_index")) == (way_id, seg_index)]
    if not edges:
        raise ValueError("Historical north approach has no eligible original source edge")
    for u, v, key in edges:
        a, b = [graph.nodes[n]["xy"] for n in (u, v)]
        assert_close(LineString([a, b]).distance(Point(xy)), 0, "frozen north approach")
        graph.remove_edge(u, v, key)
        graph.add_edge(u, target, w=math.dist(a, xy))
        graph.add_edge(target, v, w=math.dist(b, xy))
    return target


def audit_grass(seg, source, obstacles, grass, tree, hard_tree, row, scene):
    a, b = seg.a[0], seg.b[0]
    line = LineString([source.projected[a], source.projected[b]])
    hit = [grass[i] for i in tree.query(line, predicate="intersects")
           if not line.relate_pattern(grass[i]["geometry"], "F********")]
    if not hit:
        if row and row["source_grass_ids"]:
            raise ValueError(f"False reported grass overlap: {scene}/{seg.key}")
        return None
    if row is None or sorted(x["id"] for x in hit) != sorted(row["source_grass_ids"]):
        raise ValueError(f"Unrecorded/different grass contact: {scene}/{seg.key}")
    tags = source.ways[seg.way]["tags"]
    endpoint_tags = [source.nodes[x].get("tags", {}) for x in (a, b)]
    explicit = tags.get("highway") in WALK or tags.get("foot") in ALLOW
    hard = [obstacles[i]["id"] for i in hard_tree.query(line, predicate="intersects")
            if hard_contact(line, obstacles[i], tags, (a, b))]
    allow = (explicit and not hard and permitted(tags)
             and all(map(permitted, endpoint_tags)) and layers(tags, *endpoint_tags))
    if allow != (row["S1_status"] == "KEEP_NATIVE") or row["S0_status"] == "KEEP_NATIVE":
        raise ValueError(f"Independent S policy disagrees: {scene}/{seg.key} {hard} {tags}")
    for field, actual in {
        "native_nodes": [a, b], "coordinates_wgs84": [list(seg.p), list(seg.q)],
        "tags": tags, "directions": list(seg.directions),
    }.items():
        if row[field] != actual:
            raise ValueError(f"Frozen identity, tags, or direction mismatch: {scene}/{seg.key}/{field}")
    for direction in seg.directions:
        oneway = tags.get("oneway:foot", tags.get("oneway") if tags.get("highway") in {"footway", "path", "steps"} else None)
        flag = "foot:forward" if direction == 1 else "foot:backward"
        if (tags.get(flag, "yes") not in ALLOW
                or direction == 1 and oneway in {"-1", "reverse"}
                or direction == -1 and oneway in {"yes", "true", "1"}):
            raise ValueError(f"Impermissible direction: {scene}/{seg.key}")
    overlap = line.intersection(unary_union([r["geometry"] for r in hit])).length
    assert_close(line.length, row["length_m"], f"raw length {scene}/{seg.key}")
    assert_close(overlap, row["background_overlap_m"], f"grass overlap {scene}/{seg.key}")
    return dict(scene_id=scene, source_id=f"way/{seg.way}", segment_index=seg.index,
                original_nodes=[a,b], original_tags=tags, directions=list(seg.directions),
                geometry_wgs84=[list(seg.p), list(seg.q)], length_m=line.length,
                grass_overlap_m=overlap, grass_evidence=[dict(id=r["id"], tags=r["tags"]) for r in hit],
                S0_status=row["S0_status"], S1_status=row["S1_status"], S0_reasons=row["S0_reasons"],
                S1_reasons=row["S1_reasons"], independent_known_hard_conflicts=hard,
                restored=allow)


def apply_decisions(graph, rows, mode):
    graph = graph.copy()
    for _, attrs in graph.nodes(data=True):
        attrs["xy"] = PROJECT(*attrs["coord"])
    remove = []
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        row = rows.get((attrs["osm_way_id"], attrs.get("segment_index")))
        if row and row[mode+"_status"] != "KEEP_NATIVE":
            remove.append((u, v, key))
        else:
            attrs["w"] = math.dist(graph.nodes[u]["xy"], graph.nodes[v]["xy"])
    graph.remove_edges_from(remove)
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph


def control_counts(rows):
    keys = ("MAPPED_BARRIER_CONFLICT", "MAPPED_BUILDING_CONFLICT", "MAPPED_WATER_CONFLICT",
            "MAPPED_FLOWERBED_CONFLICT", "MAPPED_RESTRICTED_AREA_CONFLICT", "EXPLICIT_LEVEL_CONFLICT",
            "NO_MAPPED_WALKWAY_OVER_GRASS", "FOOT_NOT_PERMITTED")
    summary = Counter()
    for row in rows:
        for reason in row["S1_reasons"]:
            if reason not in keys:
                continue
            if row["S1_status"] == "KEEP_NATIVE":
                raise ValueError(f"Known conflict was not blocked: {row['source_id']} {reason}")
            summary[reason] += 1
    return dict(summary)


def main(root, out):
    rev = root / "inputs/rev1"
    frozen = rev / "frozen_r4"
    # Reuse the frozen parser and native topology rules, not the S author decision functions.
    sys.path.insert(0, str(root))
    from inputs.rev1.src.native_adapter import Source, load_frozen_engine
    old_path = root / "inputs/north/runs/experiment.json"
    previous = read(old_path)
    north = previous["source_geometry"]
    south = read(rev / "data/entrance_approach.json")["south"]["original_door"]
    registry = frozen / "runs/source_scene_contracts.json"
    replay_path = root / "runs/semantics.json"
    csv_path = root / "data/semantics_edges.csv"
    replay = read(replay_path)
    scenes = {r["scene_id"]: r for r in replay["scenes"]}
    by_scene = defaultdict(dict)
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for key in ("native_nodes", "source_grass_ids", "coordinates_wgs84", "tags", "directions",
                        "S0_reasons", "S1_reasons"):
                row[key] = json.loads(row[key])
            for key in ("length_m", "background_overlap_m"):
                row[key] = float(row[key])
            key = int(row["way_id"]), int(row["segment_index"])
            by_scene[row["scene_id"]][key] = row
    summaries, all_records, geometry_routes = [], [], {}
    for scene in read(registry)["scenes"]:
        sid = scene["scene_id"]
        path = frozen / scene["osm_clip"]
        raw = read(path)
        source = Source(raw)
        engine = load_frozen_engine(frozen)
        segments, endings, _ = engine._segments(raw)
        native, _ = engine._build_graph(segments, endings, ())
        obstacles, unlocated = source.obstacles([])
        grasses = [r for r in obstacles if grass_hazard(r)]
        grass_tree = STRtree([r["geometry"] for r in grasses])
        hard_tree = STRtree([r["geometry"] for r in obstacles])
        rows = by_scene[sid]
        grass_audit = [rec for seg in segments if (
            rec := audit_grass(seg, source, obstacles, grasses, grass_tree, hard_tree, rows.get(seg.key), sid))]
        all_records.extend(grass_audit)
        origin = source_key(scene["start_native_id"])
        graphs = {}
        for mode in ("S0", "S1"):
            graph = apply_decisions(native, rows, mode)
            counts = graph_counts(graph, origin)
            for key, value in counts.items():
                if scenes[sid]["graph"][mode][key] != value:
                    raise ValueError(f"Independent directed topology mismatch {sid}/{mode}/{key}")
            graphs[mode] = counts
            if sid != MUSEUM:
                continue
            for wid in (654297629, 1074409256):
                if any(attrs["osm_way_id"] == wid for _, _, attrs in graph.edges(data=True)):
                    raise ValueError("North Huangpi Road policy was altered")
            exit_id = source_key(north["exit_id"])
            assert list(source.coord(north["exit_id"])) == north["exit_wgs84"]
            assert source.nodes[exit_id[0]]["tags"]["entrance"] == "exit"
            assert exit_id not in graph or not nx.has_path(graph, origin, exit_id)
            target = add_fixed_approach(graph, north)
            length = nx.shortest_path_length(graph, origin, target, weight="w")
            assert_close(length, replay["variants"][mode]["north_fixed"]["length_m"], mode+" fixed north")
            if mode == "S0":
                assert_close(length, previous["variants"]["N0"]["length_m"], "historical B0/N0")
            add_frozen_face(graph, rev / "data/edge_evidence.jsonl")
            s = nx.shortest_path_length(graph, origin, source_key(south["native_id"]), weight="w")
            assert_close(s, replay["variants"][mode]["south"]["length_m"], mode+" fixed south")
            geometry_routes[mode] = dict(north_fixed_m=length, south_m=s, exit_reached=False,
                                         start_native_id=scene["start_native_id"],
                                         start_wgs84=source.coord(scene["start_native_id"]),
                                         fixed_approach_wgs84=north["approach_wgs84"], south_native_id=south["native_id"],
                                         north_exit_native_id=north["exit_id"], north_exit_tags=north["exit_tags"],
                                         north_exit_wgs84=north["exit_wgs84"])
        summaries.append(dict(scene_id=sid, raw_clip=scene["osm_clip"], raw_clip_bytes=path.stat().st_size,
                              raw_clip_sha256=sha(path), native_candidate_segments=len(segments),
                              independently_detected_grass_overlap_segments=len(grass_audit),
                              admissible_grass_walkway_segments=sum(r["restored"] for r in grass_audit),
                              retained_admissible_grass_walkway_segments=sum(r["restored"] for r in grass_audit),
                              grass_restricted_segments=sum(not r["restored"] for r in grass_audit),
                              hard_reason_rows_from_replayed_audit=control_counts(rows.values()),
                              unmapped_obstacle_ids_no_coordinates=len(unlocated), graph=graphs))
        print(sid, "raw segment", len(segments), "grass contacts", len(grass_audit),
              "recomputed S0→S1 reach", graphs["S0"]["reachable_nodes"], graphs["S1"]["reachable_nodes"], flush=True)
    restored = [r for r in all_records if r["restored"]]
    dedup = {tuple(sorted(map(tuple, r["geometry_wgs84"]))): r for r in restored}
    by_raw_id = {(r["source_id"], r["segment_index"], tuple(sorted(map(tuple, r["geometry_wgs84"])))) for r in restored}
    old_aggregate = replay["spatial_geometry_policy_dedup"]
    assert len(dedup) == old_aggregate["restored_segments"]
    assert len(restored) == replay["raw_clip_totals"]["restored_segments"]
    assert_close(sum(r["length_m"] for r in dedup.values()), old_aggregate["restored_native_length_m"], "six-clip dedup restored length")
    assert_close(sum(r["grass_overlap_m"] for r in dedup.values()), old_aggregate["restored_grass_overlap_m"], "six-clip dedup grass overlap")
    routes_path = root / "data/semantics_routes.geojson"
    for item in read(routes_path)["features"]:
        attrs = item["properties"]
        if attrs["role"] != "route":
            continue
        g = item["geometry"]["coordinates"]
        stats = geometry_routes[attrs["variant"]]
        end = stats["fixed_approach_wgs84"] if attrs["target"] == "north_fixed" else south["original_coordinate"]
        assert_close(math.dist(PROJECT(*g[0]), PROJECT(*stats["start_wgs84"])), 0, "exported start")
        assert_close(math.dist(PROJECT(*g[-1]), PROJECT(*end)), 0, "exported endpoint")
        assert_close(LineString([PROJECT(*p) for p in g]).length, stats[attrs["target"]+"_m"], "exported path metric")
    four = {}
    for wid in sorted(REGRESSION):
        matched = [r for r in restored if r["scene_id"] == MUSEUM and r["source_id"] == wid
                   and any(e["id"] == GRASS for e in r["grass_evidence"])]
        four[wid] = dict(segment_count=len(matched), grass_overlap_m=sum(r["grass_overlap_m"] for r in matched))
    hard_controls = Counter()
    for scene in summaries:
        hard_controls.update(scene["hard_reason_rows_from_replayed_audit"])
    result = dict(status="S1_FROZEN_INDEPENDENT_CHECK_PASS", crs="EPSG:32651",
                  actor="/root/r3_s_audit", original_policy_replay="R2 src.run_semantics --output-root in R3 only",
                  read_method="frozen OSM parser + frozen pre-S native graph builder; independent grass/hard/permission classifier and directed topology reconstruction",
                  graph_scope="Non-grass S0/S1 decisions replayed from S table; every independently found eligible grass intersection recomputed",
                  source_hashes={p.relative_to(root).as_posix(): sha(p) for p in
                      (old_path, registry, replay_path, csv_path, routes_path, root / "src/semantics.py",
                       root / "src/run_semantics.py", frozen / "src/frozen_r1/local_route.py")},
                  scenes=summaries, four_raw_source_ways=four, verified_raw_grass_contacts=len(all_records),
                  clip_restored_rows=len(restored), original_identity_dedup=len(by_raw_id),
                  geometry_dedup=len(dedup), restored_native_m=sum(r["length_m"] for r in dedup.values()),
                  restored_grass_overlap_m=sum(r["grass_overlap_m"] for r in dedup.values()),
                  recovered_directed_arcs_dedup=sum(len(r["directions"]) for r in dedup.values()),
                  known_conflict_rejections_in_replayed_table=dict(hard_controls),
                  source_ground_caveat="grass exception does not imply free walking through grass; accepted structures retain native elevations",
                  B0_and_S1_same_endpoint_recomputed=geometry_routes,
                  fixed_north_reduction_m=geometry_routes["S0"]["north_fixed_m"]-geometry_routes["S1"]["north_fixed_m"],
                  field_verified=0, external_requests=0)
    with out.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with (out.parent / "S_FREEZE_GRASS_RECORDS.jsonl").open("x", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":"))+"\n")
    print(result["status"], result["geometry_dedup"], result["fixed_north_reduction_m"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "audits/S_FREEZE.json")
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve())
