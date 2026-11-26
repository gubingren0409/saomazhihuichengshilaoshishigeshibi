"""Independent R2 evidence replay. Does not import the production analyzer or call any service."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict, deque
from itertools import accumulate
from pathlib import Path
from zipfile import ZipFile

from geographiclib.geodesic import Geodesic
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
WGS = Geodesic.WGS84
PUBLIC = {"yes", "designated", "permissive", "official"}
RESTRICTED = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry"}
FOOT = {"footway", "pedestrian", "path", "steps"}
SHARED = {"living_street", "residential", "unclassified", "service"}
MAJOR = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
OPTIONAL = {"track", "cycleway", "bridleway", "corridor"}
SIDEWALK = {"yes", "both", "left", "right"}
PASSABLE_BARRIERS = {"no", "bollard", "block", "cycle_barrier", "cattle_grid", "kerb", "entrance"}
CONDITIONAL = {"access:conditional", "foot:conditional", "oneway:foot:conditional",
               "foot:forward:conditional", "foot:backward:conditional"}
NEAR_AXES = (654297629, 1074409256)
PLAZA_REL = 2385771
PLAZA_OUTER = 178721643
REFERENCE = 6897141353
NEAR_FOOTWAY = 178719573
SCORE_SHA = "bf9031591b4d67be39ec7e0239432116a01f3197b414e88d3e8a682a68db108a"


def sha(path_or_bytes):
    raw = path_or_bytes.read_bytes() if isinstance(path_or_bytes, Path) else path_or_bytes
    return hashlib.sha256(raw).hexdigest()


def load(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8-sig"))


def distance(a, b):
    return WGS.Inverse(a[1], a[0], b[1], b[0])["s12"]


def cumulative(coords):
    return list(accumulate((distance(a, b) for a, b in zip(coords, coords[1:])), initial=0.0))


def access(tags):
    return not (CONDITIONAL & tags.keys()
                or (tags["foot"] not in PUBLIC if "foot" in tags else tags.get("access") in RESTRICTED))


def permitted_way(tags):
    if not access(tags) or tags.get("area") == "yes" or any(tags.get(k) not in (None, "no") for k in ("indoor", "ford")):
        return False
    highway = tags.get("highway")
    if highway in FOOT:
        return True
    if highway not in SHARED | MAJOR | OPTIONAL:
        return False
    if tags.get("foot") in PUBLIC:
        return True
    if highway in SHARED | MAJOR and any(tags.get(k) in SIDEWALK for k in ("sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both")):
        return True
    return highway in SHARED and tags.get("sidewalk") not in {"separate", "no"}


def permitted_node(tags):
    return (access(tags) and tags.get("locked") != "yes"
            and (tags.get("barrier", "no") in PASSABLE_BARRIERS or tags.get("foot") in PUBLIC))


def directions(tags):
    one = tags.get("oneway:foot", tags.get("oneway") if tags.get("highway") in {"footway", "path", "steps"} else None)
    if one not in {None, "no", "false", "0", "yes", "true", "1", "-1", "reverse"}:
        return False, False
    return (one not in {"-1", "reverse"} and tags.get("foot:forward", "yes") in PUBLIC,
            one not in {"yes", "true", "1"} and tags.get("foot:backward", "yes") in PUBLIC)


def local_edges(payload, nodes, ways):
    west, south, east, north = payload["bounds_wsen"]
    permitted = {k for k, n in nodes.items() if permitted_node(n.get("tags", {}))
                 and west <= n["lon"] <= east and south <= n["lat"] <= north}
    graph, ends, segments = defaultdict(set), defaultdict(set), []
    for wid, way in ways.items():
        tags = way.get("tags", {})
        forward, backward = directions(tags)
        if not permitted_way(tags) or not (forward or backward):
            continue
        default_layer = ("1" if tags.get("bridge") not in (None, "no") else
                         "-1" if tags.get("tunnel") not in (None, "no") else "0")
        level = tags.get("level", "0")
        layer = tags.get("layer", default_layer)
        ids = way["nodes"]
        for i, (a, b) in enumerate(zip(ids, ids[1:])):
            if a not in permitted or b not in permitted or a == b or (
                nodes[a]["lon"], nodes[a]["lat"]) == (nodes[b]["lon"], nodes[b]["lat"]):
                continue
            u, v = (a, layer, level), (b, layer, level)
            if forward:
                graph[u].add(v)
            if backward:
                graph[v].add(u)
            if i == 0:
                ends[a].add(u)
            if i == len(ids)-2:
                ends[b].add(v)
            segments.append((wid, i, a, b))
    for group in ends.values():
        for a in group:
            graph[a].update(b for b in group if b != a and b[2] == a[2])
    return graph, segments


def reach(graph, node_id):
    todo = deque(key for key in graph if key[0] == node_id)
    seen = set(todo)
    while todo:
        for neighbor in graph.get(todo.popleft(), ()):
            if neighbor not in seen:
                todo.append(neighbor)
                seen.add(neighbor)
    return {key[0] for key in seen}


def prior_archive(archive, root):
    if archive is None:
        return {"archive_checked": False}
    with ZipFile(archive) as book:
        assert book.testzip() is None
        manifest = json.loads(book.read("MANIFEST.json"))["entries"]
        for row in manifest:
            raw = book.read(row["path"])
            assert len(raw) == row["bytes"] and sha(raw) == row["sha256"], row["path"]
        selected = ("data/sh-huangpu-01.osm.json", "runs/scene_contract.json", "runs/pilot_plan.json",
                    "runs/local_approach_diagnostic.geojson", "runs/local_approach_diagnostic.json",
                    "runs/local_route.json", "runs/local_route.geojson", "runs/geoapify_walk_probe_proxy.json",
                    "visuals/geoapify/sh-huangpu-01_probe_walk.geojson", "runs/local_viewports.json",
                    "runs/geoapify_static_completion.json")
        verified = [p for p in selected if (root / p).is_file()]
        assert len(verified) == len(selected)
        for p in verified:
            assert sha(root / p) == sha(book.read(p)), p
    return {"archive_checked": True, "sha256": sha(archive), "manifest_entries": len(manifest),
            "working_files_identical": verified}


def read_score(path, private_mapping=None):
    assert sha(path) == SCORE_SHA, "named user score byte SHA"
    with path.open(encoding="utf-8-sig", newline="") as source:
        [row] = list(csv.DictReader(source))
    assert [row[k] for k in ("blind_scene_id", "detail_pair_id", "context_pair_id")] == ["S-1814", "P-872C", "P-2CAE"]
    if private_mapping is not None:
        with private_mapping.open(encoding="utf-8-sig", newline="") as source:
            [mapping] = list(csv.DictReader(source))
        assert all(mapping[k] == row[k] for k in ("blind_scene_id", "detail_pair_id", "context_pair_id"))
        assert (mapping["A_provider"], mapping["B_provider"]) == ("geoapify", "osm")
    fields = ("building_outline", "building_road_separation", "pedestrian_visibility", "entrance_context",
              "occlusion", "target_identification", "detail_access", "context_detour")
    scores = {s: {"eight_map_context_fields": sum(int(row[s+"_"+k]) for k in fields),
                  "route_alignment": int(row[s+"_route_alignment"]),
                  "route_visibly_unreasonable": row[s+"_route_visibly_unreasonable"]} for s in ("A", "B")}
    for value in scores.values():
        value["nine_item_total"] = value["eight_map_context_fields"] + value["route_alignment"]
    return {"sha256": sha(path), "size": path.stat().st_size, "scene": row["blind_scene_id"],
            "pairs": [row["detail_pair_id"], row["context_pair_id"]], "scores": scores,
            "preference": row["overall_preference"], "time": row["scored_at_utc"],
            "comment_untouched": True, "mapping_checked": private_mapping is not None}


def verify(root, score=None, mapping=None, archive=None):
    provenance = prior_archive(archive, root)
    s = load(root, "runs/scene_contract.json")
    source = load(root, "data/sh-huangpu-01.osm.json")
    assert sha(root / "data/sh-huangpu-01.osm.json") == s["snapshot_sha256"]
    plan = load(root, "runs/pilot_plan.json")
    local_request = load(root, "runs/local_route.json")
    assert plan["frozen_before_routing"] is True and s["frozen_before_route"] is True
    assert plan["scene"]["path_snap_max_m"] == s["path_snap_max_m"] == local_request["max_snap_m"] == 35
    assert local_request["geometry"] is None and local_request["failure_reason"] == "TARGET_SNAP_OUTSIDE_LIMIT"
    assert load(root, "runs/local_route.geojson")["geometry"] is None

    local = load(root, "runs/local_approach_diagnostic.geojson")["geometry"]["coordinates"]
    hosted_path = "visuals/geoapify/sh-huangpu-01_probe_walk.geojson"
    hosted = load(root, hosted_path)["features"][0]["geometry"]["coordinates"]
    receipt = load(root, "runs/geoapify_walk_probe_proxy.json")
    assert sha(root / hosted_path) == receipt["geojson"]["sha256"]
    assert sha(root / "runs/scene_contract.json") == receipt["scene_contract_sha256"]
    assert receipt["receipt"]["status_code"] == 200
    assert receipt["route"]["requested_start_wgs84"] == s["start"]
    assert receipt["route"]["requested_target_wgs84"] == s["target"]
    assert receipt["route"]["entrance"] is None

    ll, hl = cumulative(local), cumulative(hosted)
    a, b = (LineString([PROJECT(*p) for p in r]) for r in (local, hosted))
    counts = {t: {r["id"]: r for r in source["elements"] if r["type"] == t}
              for t in ("node", "way", "relation")}
    nodes, ways, relations = (counts[k] for k in ("node", "way", "relation"))
    xy = {i: PROJECT(n["lon"], n["lat"]) for i, n in nodes.items()}
    lines = {i: LineString([xy[n] for n in w["nodes"]]) for i, w in ways.items()
             if len(w["nodes"]) > 1 and all(n in xy for n in w["nodes"])}

    graph, segs = local_edges(source, nodes, ways)
    assert len(segs) == local_request["graph_stats"]["eligible_segments"] == 7113
    assert len({seg[0] for seg in segs}) == local_request["graph_stats"]["eligible_ways"] == 1760
    reached = reach(graph, 476682043)
    assert REFERENCE not in reached and REFERENCE not in {i for _, _, a, b in segs for i in (a, b)}
    eligible_ways = {seg[0] for seg in segs}
    assert all(w not in eligible_ways for w in NEAR_AXES)
    crossing_nodes = ways[761403176]["nodes"]
    assert ways[761403176]["tags"]["footway"] == "crossing"
    assert all(n in reached for n in crossing_nodes)
    local_meta = load(root, "runs/local_approach_diagnostic.json")
    used = {e["osm_way_id"] for e in local_meta["segments"]}
    assert {39764601, 39764359, 165953415, 39764607, 513764740, 761403176} <= used
    assert not set(NEAR_AXES) & used
    for i, w in ((2, NEAR_AXES[0]), (3, NEAR_AXES[0]), (4, NEAR_AXES[1])):
        mid = LineString([PROJECT(*p) for p in hosted[i:i+2]]).interpolate(.5, normalized=True)
        assert lines[w].distance(mid) < .05
    assert distance(local[1], hosted[1]) < .1 and distance(local[8], hosted[6]) < .1
    first_overlap = [round(a.intersection(b.buffer(1)).length/a.length, 6),
                     round(b.intersection(a.buffer(1)).length/b.length, 6)]

    members = relations[PLAZA_REL]["members"]
    assert relations[PLAZA_REL]["tags"] == {"area": "yes", "highway": "pedestrian", "type": "multipolygon"}
    holes = [lines[m["ref"]].coords for m in members if m["role"] == "inner"]
    plaza = Polygon(lines[PLAZA_OUTER].coords, holes=holes)
    native = set(ways[PLAZA_OUTER]["nodes"])
    native_attachments = {i: sorted(native & set(ways[i]["nodes"])) for i in eligible_ways
                          if native & set(ways[i]["nodes"])}
    traversals = {i: line.intersection(plaza.buffer(-.01)).length
                  for i, line in lines.items() if i in eligible_ways and line.intersects(plaza)}
    assert all(x < .01 for x in traversals.values())
    assert native_attachments == {178737605:[1890935454], 178737608:[1890935415], 761403177:[1890745480]}
    assert REFERENCE in native and REFERENCE in ways[161090899]["nodes"]
    assert nodes[REFERENCE]["tags"] == {"entrance": "main"}
    assert nodes[6897145227]["tags"] == {"entrance": "exit"}
    assert not native & set(ways[NEAR_FOOTWAY]["nodes"])
    ref = Point(xy[REFERENCE])
    closest = min((LineString([xy[n1],xy[n2]]).distance(ref), wid, index, n1, n2)
                  for wid, index, n1, n2 in segs)
    assert closest[1:] == (178719573, 98, 1891590993, 1890732610)
    museum = Polygon(lines[161090899])
    assert museum.boundary.distance(ref) < 1e-8
    core = museum.buffer(-.25)
    chord = LineString((xy[REFERENCE], PROJECT(*local[-1])))
    chord_crossing = chord.intersection(core).length
    assert 50 < chord_crossing < 51
    route_core_lengths = [route.intersection(core).length for route in (a,b)]
    plaza_core_lengths = [route.intersection(plaza.buffer(-.25)).length for route in (a,b)]
    assert route_core_lengths == plaza_core_lengths == [0.0,0.0]

    return {
        "source_archive": provenance,
        "score_original": read_score(score, mapping) if score else {"checked": False},
        "projection_for_topology": "EPSG:32651 / WGS84 UTM 51N",
        "length_distance_basis": "GeographicLib WGS84 ellipsoid using saved raw vertices",
        "routes": {"local_vertices":len(local), "hosted_vertices":len(hosted),
                   "local_diagnostic_length_m":ll[-1], "hosted_polyline_length_m":hl[-1],
                   "hosted_provider_length_m":receipt["route"]["provider_distance_m"],
                   "local_origin_gap_m":distance(s["start"],local[0]), "hosted_origin_gap_m":distance(s["start"],hosted[0]),
                   "local_end_gap_m":distance(s["target"],local[-1]),"hosted_end_gap_m":distance(s["target"],hosted[-1]),
                   "endpoint_separation_m":distance(local[-1],hosted[-1]), "snap_gate_m":35,
                   "full_local_route":False, "overlap_length_fraction_within_1m":first_overlap,
                   "target_building_interior_route_m":route_core_lengths,
                   "plaza_interior_route_m":plaza_core_lengths,
                   "diagnostic_chord_building_interior_m":chord_crossing,
                   "hausdorff_utm_m":a.hausdorff_distance(b)},
        "origin": {"shared_departure_way":39764601,"fork_native_node":13763096985,
                   "fork_chainage_m":[ll[1],hl[1]],"rejoin_native_node":7113798201,
                   "fork_to_rejoin_m":[ll[8]-ll[1],hl[6]-hl[1]],
                   "crossing_native_way":761403176,"crossing_native_nodes":crossing_nodes,
                   "hosted_axis_spatial_matches":list(NEAR_AXES), "those_axes_eligible_local":False},
        "plaza": {"relation":PLAZA_REL,"outer":PLAZA_OUTER,"target_reference":REFERENCE,
                  "way_shared_native_attachments":native_attachments,
                  "attachments_reachable_from_local_start":{i:all(n in reached for n in ns)
                                                           for i, ns in native_attachments.items()},
                  "traversal_lengths_m":traversals, "target_is_in_local_linear_graph":False,
                  "nearest_accepted_walkway":NEAR_FOOTWAY,"closest_segment":list(closest),
                  "nearest_accepted_walkway_to_plaza_polygon_utm_m":lines[NEAR_FOOTWAY].distance(plaza)},
        "provider_raw_route_payload": "NOT_RETAINED_IN_SCOPED_ARTIFACTS",
        "provider_internal_graph": "UNKNOWN", "provider_calls":0, "site_visits":0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r1-root", required=True, type=Path)
    p.add_argument("--score", type=Path)
    p.add_argument("--mapping", type=Path)
    p.add_argument("--archive", type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    result = verify(args.r1_root, args.score, args.mapping, args.archive)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("R2 independent evidence checks passed.")


if __name__ == "__main__":
    main()
