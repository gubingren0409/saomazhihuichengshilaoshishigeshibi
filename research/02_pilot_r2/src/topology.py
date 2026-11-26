"""Read-only topology diagnostics on the frozen R1 network and route artifacts."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

import networkx as nx
from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True).transform
GEOD = Geod(ellps="WGS84")
KEY_TAGS = {
    "access", "area", "area:highway", "barrier", "bicycle", "bridge", "building",
    "cycleway", "entrance", "foot", "footway", "highway", "indoor", "landuse",
    "layer", "leisure", "level", "lit", "locked", "name", "name:en", "oneway",
    "oneway:foot", "pedestrian", "service", "sidewalk", "surface", "tunnel", "type",
    "crossing", "traffic_signals", "wheelchair", "opening_hours",
}
SPLIT = 13763096985
ROAD_CONTACT = 476682036
SIGNAL = 477568284
REJOIN = 7113798201
START = 476682043
THEATRE = 39763758
ENTRANCE = 6897141353
EXIT = 6897145227
BUILDING = 161090899
NETWORK_ENDPOINT = 1890732610
CROSSING = 761403176
PLAZA = 2385771
PLAZA_OUTER = 178721643
PLAZA_HOLES = [178721634, 178721647]
BYPASS = [39764359, 165953415, 39764607, 513764740]
HOSTED_CANDIDATES = [39764601, 654297629, 1074409256, 513764740]
HOSTED_AXIS = [654297629, 1074409256]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def snapshot_module(path):
    spec = importlib.util.spec_from_file_location("_r2_frozen_local_route", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def dump(path, item):
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def geometry_length(coords):
    lon, lat = zip(*coords)
    return GEOD.line_length(lon, lat)


def projected(coords):
    return LineString([PROJECT(*point) for point in coords])


def distance(a, b):
    return GEOD.inv(*a, *b)[2]


def tags(item):
    return {k: v for k, v in item.get("tags", {}).items()
            if k in KEY_TAGS or k.endswith(":conditional") or k.startswith("sidewalk:")}


def geometry(kind, coordinates):
    return {"type": kind, "coordinates": coordinates}


def feature(kind, item, coordinates, role, evidence="OBSERVED"):
    return {"type": "Feature", "geometry": geometry(kind, coordinates),
            "properties": {"id": f"{item['type']}/{item['id']}", "role": role,
                           "tags": tags(item), "evidence": evidence,
                           "source": "R1 bounded Geofabrik OSM vector clip"}}


def source_default(root):
    bundled = root / "inputs/r1"
    return bundled if (bundled / "data/sh-huangpu-01.osm.json").is_file() else root.parent / "OSM_GEOAPIFY_PILOT_R1"


def main(r1, root, profile_source=None):
    scene = read(r1 / "runs/scene_contract.json")
    assert scene["scene_id"] == "sh-huangpu-01"
    data_path = r1 / "data/sh-huangpu-01.osm.json"
    assert sha256(data_path.read_bytes()).hexdigest() == scene["snapshot_sha256"]
    data = read(data_path)
    nodes = {row["id"]:row for row in data["elements"] if row["type"]=="node"}
    ways = {row["id"]:row for row in data["elements"] if row["type"]=="way"}
    relations = {row["id"]:row for row in data["elements"] if row["type"]=="relation"}
    pos = lambda node: (nodes[node]["lon"], nodes[node]["lat"])
    coords = lambda way: [pos(node) for node in ways[way]["nodes"]]
    line = lambda way: projected(coords(way))
    nodepoint = lambda node: Point(*PROJECT(*pos(node)))
    gallery = (r1 / "visuals/blind_review/index.html").read_text(encoding="utf-8-sig")
    scene_label, = re.findall(r"S-[A-Z0-9]{4}", gallery)
    hosted_pair_ids = re.findall(r'<figure><h4>A 侧</h4>.*?(P-[A-Z0-9]{4})-A-base[.]png.*?</figure>', gallery)
    assert len(hosted_pair_ids) == 2
    hosted_panels = [panel for panel in re.findall(r"<figure>.*?</figure>", gallery)
                     if "<h4>A 侧</h4>" in panel]
    local_panels = [panel for panel in re.findall(r"<figure>.*?</figure>", gallery)
                    if "<h4>B 侧</h4>" in panel]
    assert all("Powered by Geoapify" in panel for panel in hosted_panels)
    assert all("Powered by Geoapify" not in panel for panel in local_panels)
    blind = {"blind_scene_id":scene_label,"detail_pair_id":hosted_pair_ids[0],
             "context_pair_id":hosted_pair_ids[1]}
    profile = profile_source or r1 / "src/local_route.py"
    local_module = snapshot_module(profile)
    local = read(r1 / "runs/local_approach_diagnostic.json")
    failure = read(r1 / "runs/local_route.json")
    hosted_path = r1 / "visuals/geoapify/sh-huangpu-01_probe_walk.geojson"
    hosted_receipt = read(r1 / "runs/geoapify_walk_probe_proxy.json")
    assert sha256(hosted_path.read_bytes()).hexdigest() == hosted_receipt["geojson"]["sha256"]
    a, = [obj["geometry"]["coordinates"] for obj in read(hosted_path)["features"]]
    b = local["geometry"]["coordinates"]
    assert tuple(b[0]) == pos(START) and tuple(b[1]) == pos(SPLIT) and tuple(b[8]) == pos(REJOIN)
    assert max(distance(a[i], pos(key)) for i,key in ((0,START),(1,SPLIT),(2,ROAD_CONTACT),(4,SIGNAL),(6,REJOIN))) < .10
    segments, endings, graph_summary = local_module._segments(data)
    graph, _ = local_module._build_graph(segments, endings, [])
    assert graph_summary == failure["graph_stats"]
    eligible = defaultdict(list)
    for item in segments:
        eligible[item.way].append(item)
    origin_key = (START, "0", "0")
    reached = nx.descendants(graph, origin_key) | {origin_key}
    reach_native = {k[0] for k in reached}
    graph_native = {k[0] for k in graph}
    by_native = defaultdict(set)
    for item in segments:
        by_native[item.a[0]].add(item.way)
        by_native[item.b[0]].add(item.way)
    assert all(not eligible[key] for key in HOSTED_AXIS)
    assert set(graph[(ROAD_CONTACT,"0","0")]) == {(SPLIT,"0","0")}
    assert failure["max_snap_m"] == 35 and failure["status"] == "NO_ROUTE"
    assert failure["snap_end"]["way_id"] == 178719573

    a_line, b_line = projected(a), projected(b)
    a_tail, b_tail = projected(a[6:]), projected(b[8:])
    plaza = Polygon(line(PLAZA_OUTER), [line(w).coords for w in PLAZA_HOLES])
    assert plaza.is_valid
    plaza_core = plaza.buffer(-.25)
    assert plaza_core.is_valid
    plaza_nodes = {node for w in [PLAZA_OUTER,*PLAZA_HOLES] for node in ways[w]["nodes"]}
    contacts = [{"node_id":key, "wgs84":pos(key), "way_ids":sorted(by_native[key]),
                 "reachable_from_origin":key in reach_native}
                for key in sorted(plaza_nodes & graph_native)]
    assert {item["node_id"] for item in contacts} == {1890935454,1890935415,1890745480}
    assert ENTRANCE in plaza_nodes and ENTRANCE in ways[BUILDING]["nodes"]
    assert ENTRANCE not in graph_native
    nearby = {i for i in eligible if line(i).distance(plaza)<=45}
    interior_lengths = [projected([item.p,item.q]).intersection(plaza_core).length
                        for i in nearby for item in eligible[i]]
    assert max(interior_lengths, default=0) < 1e-6
    assert max(a_line.intersection(plaza_core).length,b_line.intersection(plaza_core).length) < 1e-6

    route_diff = []
    source_waylines = {key: line(key) for key,obj in ways.items()
                       if "highway" in obj.get("tags", {}) and all(n in nodes for n in obj["nodes"])}
    def row(side, index, p, q, way, max_residual, evidence):
        native = ways[way]
        return {"r1_side":side, "segment_index_0based":index,
                "from_wgs84":json.dumps(p), "to_wgs84":json.dumps(q),
                "length_wgs84_m":round(distance(p,q),6), "osm_way_id":f"way/{way}",
                "matching_basis":("RECORDED_NATIVE_ID" if side=="B" else "GEOMETRIC_CANDIDATE_ONLY"),
                "native_way_tags":json.dumps(tags(native),ensure_ascii=False,sort_keys=True),
                "local_graph_admitted_segments":len(eligible[way]),
                "max_three_sample_residual_epsg32651_m":"" if max_residual is None else round(max_residual,6),
                "evidence":evidence}

    for i,(p,q) in enumerate(zip(a[:13], a[1:14])):
        ln=projected([p,q])
        checks=[ln.interpolate(k,normalized=True) for k in (.2,.5,.8)]
        residual,key=min((max(pt.distance(edge) for pt in checks),way)
                         for way,edge in source_waylines.items())
        route_diff.append(row("A",i,p,q,key,residual,"RECOMPUTED"))
    for i,segment in enumerate(local["segments"][:15]):
        route_diff.append(row("B",i,segment["start"],segment["end"],segment["osm_way_id"],None,"OBSERVED"))
    assert {int(x["osm_way_id"].split("/")[1]) for x in route_diff if x["r1_side"]=="A" and int(x["segment_index_0based"])<6} == set(HOSTED_CANDIDATES)
    assert all(float(x["max_three_sample_residual_epsg32651_m"])<.10 for x in route_diff if x["r1_side"]=="A")

    def replay(p,q):
        first,last = local_module._snap(p,segments),local_module._snap(q,segments)
        new,keys = local_module._build_graph(segments,endings,[first,last])
        route = nx.shortest_path(new,*keys,weight="length_m",method="dijkstra")
        return {"length_m":nx.shortest_path_length(new,*keys,weight="length_m",method="dijkstra"),
                "first_after_split_native_id":route[2][0],
                "start_snap_m":first[3],"end_snap_m":last[3],
                "start_snap_way_id":first[0].way,"end_snap_way_id":last[0].way}
    on_local_snap=replay(b[0],b[-1])
    on_host_snap=replay(a[0],a[-1])
    assert on_local_snap["first_after_split_native_id"]==on_host_snap["first_after_split_native_id"]==13763096984
    assert abs(on_local_snap["length_m"]-local["length_m"])<1e-6

    footprint=Polygon(projected(scene["building_footprint"]["coordinates"][0]))
    theatre=Polygon(line(THEATRE))
    clearance=projected([b[-1],scene["target"]])
    origin_roles={THEATRE:"origin_building",39764601:"common_prefix",39764359:"local_detour",
                  165953415:"local_detour",39764607:"local_detour",513764740:"origin_sidewalk",
                  CROSSING:"shared_crossing",654297629:"hosted_axis_candidate",
                  1074409256:"hosted_axis_candidate",39838520:"residential_junction",
                  39763700:"crossed_road_axis",24576922:"crossed_road_axis",1303211752:"after_crossing",
                  161086369:"crossed_cycleway"}
    plaza_roles={PLAZA_OUTER:"plaza_outer",PLAZA_HOLES[0]:"plaza_inner_grass",
                 PLAZA_HOLES[1]:"plaza_inner_grass",178719573:"nearest_network_way",
                 BUILDING:"museum_building",178699056:"wusheng_road"}
    contact_ways={i for row in contacts for i in row["way_ids"]}
    for i in sorted(nearby):
        plaza_roles.setdefault(i,"plaza_perimeter_walk_edge" if i in contact_ways else "plaza_nearby_walk_edge")
    roles={**origin_roles,**plaza_roles}
    role_nodes={START:"origin",SPLIT:"divergence",ROAD_CONTACT:"local_dead_end",
                SIGNAL:"traffic_signal",REJOIN:"rejoin",7113798199:"crossing_road_node",
                7113798198:"crossing_road_node",1890935445:"crossing_end",
                ENTRANCE:"entrance_reference",EXIT:"mapped_exit",NETWORK_ENDPOINT:"local_network_endpoint",
                **{item["node_id"]:"plaza_perimeter_contact" for item in contacts}}
    items=[]
    for i,role in roles.items():
        polygon=(role in {"origin_building","museum_building","plaza_inner_grass"})
        items.append(feature("Polygon" if polygon else "LineString", ways[i],
                             [coords(i)] if polygon else coords(i),role))
    for i,role in role_nodes.items():
        items.append(feature("Point",nodes[i],pos(i),role))
    items.append(feature("Polygon",relations[PLAZA],
                         [coords(PLAZA_OUTER), *[coords(i) for i in PLAZA_HOLES]], "south_plaza"))
    items.append({"type":"Feature","geometry":None,"properties":{
        "id":"relation/2153738","role":"broader_people_square_distinct_area",
        "tags":tags(relations[2153738]),"evidence":"OBSERVED","source":"R1 bounded Geofabrik OSM vector clip"}})
    result={
        "scene_id":scene["scene_id"],
        "analysis_crs":"EPSG:32651 (geometry correspondence only); WGS84 ellipsoid for lengths",
        "feature_coordinates_crs":"EPSG:4326 longitude, latitude",
        "mapping":{"A":"Geoapify","B":"本地 OSM","blind_scene_id":blind["blind_scene_id"],
                   "detail_pair_id":blind["detail_pair_id"],"context_pair_id":blind["context_pair_id"]},
        "source":{
            "clip":"data/sh-huangpu-01.osm.json",
            "snapshot_sha256":scene["snapshot_sha256"],"replication":data.get("osm3s",{}),
            "r1_profile_sha256":sha256(profile.read_bytes()).hexdigest(),
            "local_profile":failure["profile"],"local_engine":failure["engine"],
            "local_graph_stats":graph_summary,"hosted_request":hosted_receipt["receipt"]["parameters"],
            "hosted_internal_graph_version":"UNKNOWN", "hosted_native_edge_ids":"UNKNOWN",
            "hosted_snap_rules_and_penalties":"UNKNOWN"},
        "origin":{
            "split_node_id":SPLIT,"split_wgs84":pos(SPLIT),"common_way_id":39764601,
            "shared_prefix_m":geometry_length(b[:2]),"local_dead_end_node_id":ROAD_CONTACT,
            "local_dead_end_wgs84":pos(ROAD_CONTACT),"local_dead_end_graph_neighbors":[SPLIT],
            "signal_node_id":SIGNAL,"signal_wgs84":pos(SIGNAL),
            "rejoin_node_id":REJOIN,"rejoin_wgs84":pos(REJOIN),
            "hosted_rejoin_offset_m":distance(a[6],pos(REJOIN)),
            "crossing_way_id":CROSSING,"crossing_node_ids":ways[CROSSING]["nodes"],
            "crossing_road_way_ids":[39763700,24576922],"crossing_road_node_ids":[7113798199,7113798198],
            "local_detour_way_ids":BYPASS,"hosted_candidate_way_ids":HOSTED_CANDIDATES,
            "hosted_candidate_road_axis_way_ids":HOSTED_AXIS,"origin_building_way_id":THEATRE,
            "hosted_split_rejoin_m":geometry_length(a[1:7]),"local_split_rejoin_m":geometry_length(b[1:9]),
            "hosted_shared_crossing_m":geometry_length(a[6:12]),"local_shared_crossing_m":geometry_length(b[8:14]),
            "local_theatre_interior_crossing_m_projected":b_line.intersection(theatre.buffer(-.25)).length,
            "hosted_theatre_interior_crossing_m_projected":a_line.intersection(theatre.buffer(-.25)).length,
            "after_rejoin_2m_overlap_fraction_hosted":a_tail.intersection(b_tail.buffer(2)).length/a_tail.length,
            "after_rejoin_2m_overlap_fraction_local":b_tail.intersection(a_tail.buffer(2)).length/b_tail.length,
            "counterfactual_local_original_returned_coords":on_local_snap,
            "counterfactual_local_hosted_returned_coords":on_host_snap,
            "hosted_same_graph_counterfactual":"UNKNOWN; provider graph unavailable"},
        "plaza":{
            "relation_id":PLAZA,"outer_way_id":PLAZA_OUTER,"inner_way_ids":PLAZA_HOLES,
            "geometry":geometry("Polygon",[coords(PLAZA_OUTER), *[coords(i) for i in PLAZA_HOLES]]),
            "relations_distinct_from_south":[2153738],"relation_tags":tags(relations[PLAZA]),
            "area_projected_m2":plaza.area,"connections":contacts,
            "nearby_eligible_way_ids":sorted(nearby),"nearby_band_m":45,
            "interior_eligible_edge_segments":sum(length>1e-6 for length in interior_lengths),
            "interior_exclusion_boundary_band_m":.25,"target_node_admitted":ENTRANCE in graph_native,
            "target_node_id":ENTRANCE,"target_shared_source_way_ids":[BUILDING,PLAZA_OUTER],
            "target_on_boundary":plaza.boundary.distance(nodepoint(ENTRANCE))<1e-6,
            "closest_eligible_to_plaza_from_nearest_network_way_m_projected":plaza.distance(line(178719573)),
            "nearest_eligible_target_way_id":178719573,
            "A_route_inside_plaza_m":a_line.intersection(plaza_core).length,
            "B_route_inside_plaza_m":b_line.intersection(plaza_core).length,
            "geoapify_area_routing_support":"UNKNOWN","current_onsite_access":"UNKNOWN"},
        "gap_context":{
            "reference_id":ENTRANCE,"reference_tags":tags(nodes[ENTRANCE]),
            "separate_exit_node_id":EXIT,"separate_exit_tags":tags(nodes[EXIT]),
            "local_end_way_id":178719573,"local_end_way_segment_index":failure["snap_end"]["segment_index"],
            "local_end_native_node_id":NETWORK_ENDPOINT,
            "direct_diagnostic_chord_crosses_museum_interior_m_projected":clearance.intersection(footprint.buffer(-.25)).length,
            "interior_rim_buffer_m_projected":.25,
            "diagnostic_chord_not_walkable":True},
        "features":{"type":"FeatureCollection","features":items},
    }
    out=root / "analysis"
    out.mkdir(parents=True,exist_ok=True)
    dump(out/"topology.json",result)
    write_csv(root/"route_segment_differences.csv",route_diff)
    features_rows = []
    for item in items:
        meta=item["properties"]; k,sid=meta["id"].split("/")
        features_rows.append({"native_id":meta["id"],"role":meta["role"],"evidence":meta["evidence"],
                              "relevant_source_tags":json.dumps(meta["tags"],ensure_ascii=False,sort_keys=True),
                              "local_eligible_segments":len(eligible[int(sid)]) if k=="way" else "",
                              "local_native_node_admitted":str(int(sid) in graph_native).lower() if k=="node" else "",
                              "source_file":"data/sh-huangpu-01.osm.json"})
    write_csv(root/"osm_feature_inventory.csv",features_rows)
    plaza_rows=[
        {"item":f"relation/{PLAZA}", "quantity":round(plaza.area,3), "unit":"EPSG:32651 m2",
         "local_topology":"SOURCE_AREA_NO_INTERIOR_GRAPH_SEGMENTS","details":"outer 178721643, grass inner 178721634/178721647",
         "evidence":"RECOMPUTED"},
        *[{"item":f"node/{c['node_id']}","quantity":len(c["way_ids"]), "unit":"eligible way count",
           "local_topology":"REACHABLE_SOURCE_SHARED_PERIMETER_NODE","details":json.dumps(c["way_ids"]),
           "evidence":"RECOMPUTED"} for c in contacts],
        {"item":f"node/{ENTRANCE}","quantity":0,"unit":"eligible graph nodes","local_topology":"ENTRANCE_NO_ELIGIBLE_EDGE",
         "details":"shared building outline way/161090899 and plaza outer way/178721643", "evidence":"RECOMPUTED"},
        {"item":"Geoapify southern plaza conversion","quantity":"","unit":"","local_topology":"UNKNOWN",
         "details":"Returned route has zero overlap with plaza interior; provider graph is not present in stored evidence",
         "evidence":"UNKNOWN"},
    ]
    write_csv(root/"plaza_connectivity_audit.csv",plaza_rows)
    print(json.dumps({"features":len(items),"plaza_contacts":len(contacts),
                      "plaza_inside_eligible_segments":result["plaza"]["interior_eligible_edge_segments"],
                      "hosted_split_rejoin_m":result["origin"]["hosted_split_rejoin_m"],
                      "local_split_rejoin_m":result["origin"]["local_split_rejoin_m"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--r1", type=Path)
    parser.add_argument("--profile-source", type=Path)
    opt = parser.parse_args()
    main(opt.r1 or source_default(opt.root),opt.root,opt.profile_source)
