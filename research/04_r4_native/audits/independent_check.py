"""Independent raw-data and package audit. Does not import R4 experiment code."""
import argparse
from collections import Counter
import csv
import hashlib
from itertools import combinations, pairwise
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import networkx as nx
from geographiclib.geodesic import Geodesic
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import polygonize, transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
WGS84 = Geodesic.WGS84
UTM = Transformer.from_crs(4326, 32651, always_xy=True).transform
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
PUBLIC = {"yes", "designated", "permissive", "official"}
RESTRICTED = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry"}
WALK = {"footway", "pedestrian", "path", "steps"}
SHARED = {"living_street", "residential", "unclassified", "service"}
MAIN = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
OTHER = {"track", "cycleway", "bridleway", "corridor"}
SIDEWALK = {"yes", "both", "left", "right"}
CONDITIONAL = {"access:conditional", "foot:conditional", "oneway:foot:conditional",
               "foot:forward:conditional", "foot:backward:conditional"}
OPEN_BARRIERS = {"no", "bollard", "block", "cycle_barrier", "cattle_grid", "kerb", "entrance"}
VARIANTS = ("B0", "B1", "B2", "B3")
SCENES = ("sh-huangpu-01", "sh-wukang", "sh-tower", "sh-newworld", "sh-library", "sh-exhibition")


def read(root, name):
    return json.loads((root / name).read_text(encoding="utf-8-sig"))


def rows(root, name):
    with (root / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def native(value):
    return int(value.rsplit("/", 1)[-1])


def coord(row):
    return (row["lon"], row["lat"])


def dist(a, b):
    return WGS84.Inverse(a[1], a[0], b[1], b[0])["s12"]


def points(geometry):
    if geometry["type"] == "LineString":
        return [geometry["coordinates"]]
    assert geometry["type"] == "MultiLineString"
    return geometry["coordinates"]


def length(geometry):
    return sum(dist(a, b) for part in points(geometry) for a, b in pairwise(part))


def approx(a, b, tol=1e-6):
    assert abs(a - b) <= tol, (a, b)


def node_allowed(t):
    foot = t.get("foot")
    return (t.get("locked") != "yes" and not CONDITIONAL.intersection(t)
            and (foot in PUBLIC or foot is None and t.get("access") not in RESTRICTED
                 and t.get("barrier", "no") in OPEN_BARRIERS))


def walking_class(t):
    foot, highway = t.get("foot"), t.get("highway")
    if (t.get("area") == "yes" or t.get("indoor") not in (None, "no")
            or t.get("ford") not in (None, "no") or CONDITIONAL.intersection(t)
            or not (foot in PUBLIC or foot is None and t.get("access") not in RESTRICTED)):
        return None
    if highway in WALK:
        return "MAPPED"
    if highway not in SHARED | MAIN | OTHER:
        return None
    if foot in PUBLIC:
        return "EXPLICIT"
    if highway in SHARED | MAIN and any(t.get(k) in SIDEWALK for k in
                                       ("sidewalk", "sidewalk:left", "sidewalk:right", "sidewalk:both")):
        return "AXIS"
    return "SHARED" if highway in SHARED and t.get("sidewalk") not in {"separate", "no"} else None


def directions(t):
    one = t.get("oneway:foot")
    if one is None and t.get("highway") in {"footway", "path", "steps"}:
        one = t.get("oneway")
    if one not in {None, "no", "false", "0", "yes", "true", "1", "-1", "reverse"}:
        return ()
    return tuple(i for i, field, denied in ((1, "foot:forward", {"-1", "reverse"}),
                                           (-1, "foot:backward", {"yes", "true", "1"}))
                 if one not in denied and t.get(field, "yes") in PUBLIC)


def rebuild(clip, nodes, ways):
    """Independent directed graph reconstruction from original raw members."""
    g, segs, endpoints = nx.MultiDiGraph(), {}, {}
    w, s, e, n = clip["bounds_wsen"]
    allowed = {key for key, node in nodes.items() if node_allowed(node.get("tags", {}))
               and w <= node["lon"] <= e and s <= node["lat"] <= n}
    for way, obj in ways.items():
        tags, nd = obj.get("tags", {}), obj["nodes"]
        kind, forward = walking_class(tags), directions(tags)
        if kind is None or not forward:
            continue
        inferred = "1" if tags.get("bridge") not in (None, "no") else "-1" if tags.get("tunnel") not in (None, "no") else "0"
        layer, level = tags.get("layer", inferred), tags.get("level", "0")
        for i, (a, b) in enumerate(pairwise(nd)):
            if a == b or a not in allowed or b not in allowed:
                continue
            p, q = coord(nodes[a]), coord(nodes[b])
            if p == q:
                continue
            u, v = (a, layer, level), (b, layer, level)
            segs[(way, i)] = (kind, u, v)
            g.add_node(u, coordinate=p)
            g.add_node(v, coordinate=q)
            for sign in forward:
                x, y = (u, v) if sign > 0 else (v, u)
                g.add_edge(x, y, weight=dist(p, q))
            for key, boundary in ((u, i == 0), (v, i == len(nd)-2)):
                if boundary:
                    endpoints.setdefault(key[0], set()).add(key)
    for keys in endpoints.values():
        for a, b in combinations(keys, 2):
            if a[2] == b[2]:
                g.add_edge(a, b, weight=0)
                g.add_edge(b, a, weight=0)
    return g, segs


def geometry_by_variant(doc, variant, kind):
    return [f for f in doc["features"] if f["properties"].get("kind") == kind
            and f["properties"].get("variant") == variant]


def walk_museum(nodes, ways, relation, segment_index, graph, origin):
    assert relation["tags"]["highway"] == "pedestrian" and relation["tags"]["area"] == "yes"
    outer, holes = [], []
    for member in relation["members"]:
        assert member["type"] == "way"
        if member["role"] == "outer":
            outer.append(member["ref"])
        else:
            assert member["role"] == "inner"
            holes.append(member["ref"])
    assert outer == [178721643] and sorted(holes) == [178721634, 178721647]
    assert not ways[outer[0]].get("tags", {}).get("highway")
    assert all(ways[k]["tags"]["landuse"] == "grass" for k in holes)
    def ring(way):
        return [UTM(*coord(nodes[k])) for k in ways[way]["nodes"]]
    polygon = Polygon(ring(outer[0]), [ring(k) for k in holes])
    assert polygon.is_valid and len(polygon.interiors) == 2
    contacts, interior, boundary = set(), 0, 0
    ring_nodes = set(ways[outer[0]]["nodes"])
    core, band = polygon.buffer(-.25), polygon.exterior.buffer(.25)
    for (way, i), (kind, a, b) in segment_index.items():
        if kind not in {"MAPPED", "EXPLICIT"} or a[1:] != ("0", "0"):
            continue
        contacts.update({a[0], b[0]} & ring_nodes)
        line = LineString(ring(way)[i:i+2])
        interior += line.intersection(core).length > .05
        boundary += line.intersection(band).length > .25 and band.covers(line)
    assert sorted(contacts) == [1890745480, 1890935415, 1890935454]
    assert 6897141353 in ring_nodes and (6897141353, "0", "0") not in graph
    assert all(nx.has_path(graph, origin, (key, "0", "0")) for key in contacts)
    assert interior == boundary == 0
    return dict(focus_id="relation/2385771", projected_area_m2=polygon.area, inner_grass_way_ids=holes,
                reachable_native_contacts=sorted(contacts), explicitly_tagged_interior_segments=interior,
                boundary_collinear_segments=boundary)


def audit_obstacles(route, nodes, ways, relations):
    line = transform(UTM, shape(route))
    near = line.envelope.buffer(1)
    endpoint_disk = Point(line.coords[0]).buffer(.01).union(Point(line.coords[-1]).buffer(.01))
    examined, hits = 0, []
    barrier = {"fence", "wall", "hedge", "retaining_wall", "gate", "lift_gate", "turnstile", "block"}
    def way_line(obj):
        ids = obj["nodes"]
        if len(ids) < 2 or any(key not in nodes for key in ids):
            return None
        w = LineString([UTM(*coord(nodes[key])) for key in ids])
        return w
    def area_tags(t):
        return (t.get("building") not in (None, "no") or t.get("natural") in {"water", "wetland"}
                or t.get("water") or t.get("waterway") == "riverbank"
                or t.get("landuse") in {"reservoir", "basin", "grass", "flowerbed", "flower_bed"}
                or t.get("leisure") == "flowerbed" or t.get("landcover") in {"grass", "flowerbed"}
                or t.get("barrier") in {"flower_bed", "planter"} or t.get("garden:type") == "flower_bed")
    def check(native_id, geom, hard):
        nonlocal examined
        if geom is None or geom.is_empty or not geom.is_valid or not near.intersects(geom.envelope):
            return
        examined += 1
        overlap = line.intersection(geom)
        if hard:
            conflict = not overlap.is_empty
        else:
            conflict = overlap.difference(endpoint_disk).length > .25 or line.relate(geom)[0] != "F"
        if conflict:
            hits.append(native_id)
    for key, obj in nodes.items():
        t = obj.get("tags", {})
        if t.get("barrier") in barrier and not (t.get("foot") in PUBLIC and node_allowed(t)):
            check(f"node/{key}", Point(*UTM(*coord(obj))), True)
    for key, obj in ways.items():
        t = obj.get("tags", {})
        if t.get("barrier") in barrier:
            check(f"way/{key}", way_line(obj), True)
        if area_tags(t):
            raw = way_line(obj)
            if raw is not None and raw.is_ring:
                check(f"way/{key}", Polygon(raw), False)
    for key, obj in relations.items():
        if not area_tags(obj.get("tags", {})):
            continue
        rings = {"outer": [], "inner": []}
        for m in obj["members"]:
            role = m.get("role") or "outer"
            if m["type"] != "way" or role not in rings or m["ref"] not in ways:
                break
            segment = way_line(ways[m["ref"]])
            if segment is None:
                break
            rings[role].append(segment)
        else:
            outer = unary_union(list(polygonize(rings["outer"])))
            inner = unary_union(list(polygonize(rings["inner"])))
            if not outer.is_empty and (not rings["inner"] or not inner.is_empty) and outer.covers(inner) or (not outer.is_empty and inner.is_empty and not rings["inner"]):
                check(f"relation/{key}", outer.difference(inner), False)
    return dict(nearby_valid_raw_obstacle_objects=examined, hits=sorted(set(hits)))


def validate_sources(root):
    checks = {}
    for path, rel_field in (("data/manifest.csv", "r4_path"), ("audits/ir_evidence.csv", "retained")):
        checked = 0
        for item in rows(root, path):
            if item[rel_field]:
                artifact = root / item[rel_field]
                assert artifact.stat().st_size == int(item["bytes"]) and digest(artifact) == item["sha256"], artifact
                checked += 1
        checks[path] = checked
    return checks


def verify(root):
    contracts = read(root, "runs/source_scene_contracts.json")["scenes"]
    experiment = read(root, "runs/experiment.json")
    result = {row["scene_id"]: row for row in experiment["scenes"]}
    old = read(root, "data/source/historical/r3_local_results.json")
    old = {row["scene_id"]: row["route"] for row in old["scenes"]}
    old["sh-huangpu-01"] = read(root, "data/source/historical/sh-huangpu-01_local_route.json")
    dual = read(root, "runs/dual_paths.json")
    gates = {row["scene_id"]: row for row in dual["scenes"]}
    assert tuple(result) == SCENES and tuple(old.keys()) == (*SCENES[1:], SCENES[0])
    assert experiment["geoapify_new_requests"] == dual["new_geoapify_requests"] == 0
    assert not dual["shared_auxiliary_osm_input"]
    assert dual["core_protocol_sha256"] == digest(root / experiment["protocol"])
    candidates_path = "data/edge_candidate_evidence.csv" if (root / "data/edge_candidate_evidence.csv").exists() else "data/added_edges.csv"
    candidates = rows(root, candidates_path)
    connectivity = {(r["scene_id"], r["variant"]): r for r in rows(root, "data/connectivity_changes.csv")}
    entries_csv = rows(root, "data/entrance_access.csv")
    strict_pass, edge_counts, findings, museum, library_obstacles = Counter(), Counter(), {}, None, None
    assert not rows(root, 'data/added_edges.csv')
    assert len(rows(root, 'data/boundary_candidates.csv')) == 228
    for item in contracts:
        scene = item["scene_id"]
        check = result[scene]
        raw = read(root, item["osm_clip"])
        nodes, ways, relations = ({r["id"]: r for r in raw["elements"] if r["type"] == kind}
                                  for kind in ("node", "way", "relation"))
        assert digest(root / item["osm_clip"]) == check["clip_sha256"]
        graph, segs = rebuild(raw, nodes, ways)
        weak = list(nx.weakly_connected_components(graph))
        graph_counts = dict(nodes=graph.number_of_nodes(), directed_edges=graph.number_of_edges(),
                            weak_components=len(weak), largest_weak_component=max(map(len, weak)))
        frozen = check["local_b0_frozen_replay"]
        original = old[scene]
        assert frozen["match"] is True
        for report_key, original_key in (("status", "status"), ("length_m", "length_m"),
                                         ("failure_reason", "failure_reason"), ("graph_stats", "graph_stats"),
                                         ("target_gap_m", "snap_end_m"), ("start_gap_m", "snap_start_m"),
                                         ("target_snap", "snap_end")):
            assert frozen[report_key] == original[original_key], (scene, report_key)
        assert item["start"] == original["requested_start"] and item["target"] == original["requested_target"]
        origin = (native(item["start_native_id"]), "0", "0")
        assert tuple(item["start"]) == coord(nodes[origin[0]])
        approx(dist(item["target"], original["snap_end"]["position"]), frozen["target_gap_m"])
        drawn = read(root, check["geometry_path"])
        frozen_draw = geometry_by_variant(drawn, "B0_FROZEN", "route")
        if original["geometry"]:
            assert [f["geometry"] for f in frozen_draw] == [original["geometry"]]
            approx(length(original["geometry"]), frozen["length_m"])
        else:
            assert not frozen_draw
        eligible = []
        building = item["building_native_id"]
        if building.startswith("way/"):
            perimeter = set(ways[native(building)]["nodes"])
        else:
            perimeter = {n for member in relations[native(building)]["members"]
                         if member["role"] in ("", "outer") and member["type"] == "way"
                         for n in ways[member["ref"]]["nodes"]}
        assert {native(r["native_id"]) for r in item["r4_entrances"]} == {k for k in perimeter if nodes[k].get("tags",{}).get("entrance") not in (None,"no")}
        for ref in item["r4_entrances"]:
            key = native(ref["native_id"])
            assert key in perimeter and nodes[key]["tags"] == ref["tags"]
            assert tuple(ref["coordinate"]) == coord(nodes[key])
            if ref["eligible"]:
                assert ref["tags"]["entrance"] in {"yes", "main"} and ref["entrance_grade"] == "OSM_TAGGED"
                eligible.append(ref["native_id"])
            else:
                assert ref["tags"]["entrance"] == "exit"
        assert len(eligible) == check["eligible_entrance_count"]
        for stage in VARIANTS:
            report = check["variants"][stage]
            conn = connectivity[scene, stage]
            assert report["graph"] == graph_counts and report["added_edges"] == 0
            assert all(int(conn[k]) == v for k, v in graph_counts.items())
            assert int(conn["weak_component_delta_from_b0"]) == 0
            assert {r["target_native_id"] for r in report["routes"]} == (set(eligible) if stage != "B3" else set())
            for route in report["routes"]:
                native_id = route["target_native_id"]
                target = (native(native_id), "0", "0")
                assert tuple(route["target"]) == coord(nodes[target[0]])
                csv_route = next(r for r in entries_csv if r["scene_id"] == scene and r["variant"] == stage
                                 and r["target_native_id"] == native_id)
                assert csv_route["status"] == route["status"]
                if route["status"] == "NO_ROUTE":
                    assert target not in graph or not nx.has_path(graph, origin, target)
                    assert route["geometry"] is None
                else:
                    assert route["status"] == "MAPPED_ENTRY_REACHED"
                    assert route["route_end"] == route["target"]
                    approx(length(route["geometry"]), route["length_m"])
                    approx(nx.shortest_path_length(graph, origin, target, weight="weight"), route["length_m"])
                    assert not route["obstacle_ids"] and not route["used_added_edge_ids"]
                    assert [f["geometry"] for f in geometry_by_variant(drawn, stage, "route")] == [route["geometry"]]
                    strict_pass[stage] += 1
                    if stage == "B0":
                        library_obstacles = audit_obstacles(route["geometry"], nodes, ways, relations)
                        assert not library_obstacles["hits"]
            assert report["valid_entry_route_count"] == (None if stage == "B3" else int(scene == "sh-library"))
        for record in [r for r in candidates if r["scene_id"] == scene]:
            way, i = native(record["way_id"]), int(record["segment_index"])
            node_a, node_b = ways[way]["nodes"][i:i+2]
            assert (node_a, node_b) == (native(record["start_node"]), native(record["end_node"]))
            assert ways[way]["tags"] == json.loads(record["original_tags"])
            geo = json.loads(record["geometry"])
            assert list(map(tuple, geo["coordinates"])) == [coord(nodes[node_a]), coord(nodes[node_b])]
            approx(length(geo), float(record["length_m"]))
            if record["status"] == "ALREADY_IN_B0":
                assert (way, i) in segs
            else:
                assert record["status"] == "REJECTED" and record["reason"] == "NON_GROUND_OR_UNRESOLVED_LAYER"
                assert ways[way]["tags"].get("layer", "0") != "0" or record["space_id"] == "way/182520941"
            edge_counts[record["status"]] += 1
        for sensitivity in check["sensitivity"]:
            assert sensitivity["tolerance_m"] in (.1, .5)
            assert sensitivity["verified_b1"] == sensitivity["verified_b2_additional"] == 0
        r = gates[scene]
        hosted, local = r["hosted"], r["local"]
        assert r["same_frozen_task"] and hosted["shared_request_origin"] == local["shared_request_origin"] == item["start"]
        assert hosted["shared_request_target"] == local["shared_request_target"] == item["target"]
        assert hosted["shared_core_gate"] == local["shared_core_gate"]
        assert hosted["shared_core_gate"]["status"] == "NOT_EXECUTABLE_MISSING_INPUT"
        assert hosted["provider_native_topology"] == hosted["provider_snap"] == "UNKNOWN"
        assert set(hosted["provider_native_features"].values()) == {"UNKNOWN"}
        assert hosted["shared_reference"] == local["shared_reference"]
        hosted_route = read(root, item["historical_hosted_route"])
        host_geometry = hosted_route["features"][0]["geometry"]
        assert [f["geometry"] for f in geometry_by_variant(drawn, "HOSTED", "route")] == [host_geometry]
        approx(length(host_geometry), hosted["route_length_m"])
        endpoint = points(host_geometry)[-1][-1]
        assert endpoint == hosted["geometry_end"]
        approx(dist(item["target"], endpoint), hosted["target_gap_m"])
        assert not geometry_by_variant(drawn, "B1", "edge_added")
        assert not geometry_by_variant(drawn, "B2", "edge_added")
        if scene == "sh-huangpu-01":
            museum = walk_museum(nodes, ways, relations[2385771], segs, graph, origin)
            assert sorted(native(row["native_ids"][1]) for row in check["boundary_contacts"]) == museum["reachable_native_contacts"]
            museum.update(local_gap_m=frozen["target_gap_m"], hosted_gap_m=hosted["target_gap_m"])
        findings[scene] = dict(b0_status=frozen["status"], **graph_counts, eligible=eligible,
                               hosted_length_m=hosted["route_length_m"], hosted_gap_m=hosted["target_gap_m"])
    assert strict_pass == Counter(B0=1, B1=1, B2=1)
    assert edge_counts == Counter(ALREADY_IN_B0=25, REJECTED=8), edge_counts
    return dict(status="PASS", scope="INDEPENDENT_RAW_GRAPH_GEODESIC_PROVENANCE", scenes=findings,
                sources=validate_sources(root), strict_pass=dict(strict_pass), edge_records=dict(edge_counts),
                museum=museum, library_obstacles=library_obstacles, field_checks=0, human_visual_status="PENDING_USER_REVIEW")


def browser_check(root):
    from playwright.sync_api import sync_playwright

    request_attempts, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(EDGE) if EDGE.exists() else None, headless=True,
                                     args=["--disable-background-networking", "--no-first-run"])
        page = browser.new_page(accept_downloads=True, viewport=dict(width=1380, height=1000))
        page.route(re.compile(r"^https?://"), lambda req: (request_attempts.append("external"), req.abort()))
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto((root / "visuals/index.html").as_uri())
        assert page.locator("#scene option").count() == 6
        combos = 0
        for scene in SCENES:
            page.locator("#scene").select_option(scene)
            for variant in VARIANTS:
                page.locator(f'input[name="variant"][value="{variant}"]').check()
                assert page.locator("#map svg [data-feature]").count() > 0
                assert page.locator("#mode-caption").inner_text().startswith(variant)
                assert page.locator("#route-table tbody tr").count() >= 1
                combos += 1
        page.locator("#scene").select_option("sh-huangpu-01")
        page.locator('input[name="variant"][value="B1"]').check()
        page.locator('input[name="view"][value="context"]').check()
        assert "node/6897141353" in page.locator("#entry-table").inner_text()
        assert "6897145227" in page.locator("#entry-table").inner_text()
        marker = page.locator("#map svg [data-layer='entry'] [data-feature]").first
        marker.focus()
        marker.press("Enter")
        assert "689714" in page.locator("#inspector").inner_text()
        building = page.locator("#map svg [data-layer='building'] [data-feature]")
        assert building.count() > 0
        page.locator("#layer-building").uncheck()
        assert building.count() == 0
        with page.expect_download() as event:
            page.locator("#export").click()
        svg = event.value.path().read_text(encoding="utf-8")
        assert "<svg" in svg and "sh-huangpu-01" in svg and "OpenStreetMap" in svg
        figures = page.locator(".downloads a").evaluate_all("(all)=>all.map(x=>x.getAttribute('href'))")
        assert len(figures) >= 9
        for name in figures:
            assert "<svg" in (root / "visuals" / name).read_text(encoding="utf-8")[:512], name
        browser.close()
    assert request_attempts == errors == []
    return dict(status="PASS", browser="Microsoft Edge" if EDGE.exists() else "Chromium",
                scene_variant_combinations=combos, standalone_svgs=len(figures), remote_requests=0,
                inspector_keyboard="PASS", layer_toggle="PASS", svg_export="PASS")


def review_archive(path):
    with ZipFile(path) as z, TemporaryDirectory(prefix="r4_independent_unpack_", dir=path.parent) as td:
        names = z.namelist()
        assert z.testzip() is None and len(names) == len(set(names))
        for name in names:
            member = PurePosixPath(name)
            assert (not member.is_absolute() and member.as_posix() == name and ":" not in name
                    and "\\" not in name and all(not part.startswith(".") for part in member.parts)), name
        manifest = json.loads(z.read("MANIFEST.json"))
        index = {row["path"]: row for row in manifest["entries"]}
        assert set(names) == set(index) | {"MANIFEST.json"}
        folder = Path(td)
        z.extractall(folder)
        for name, row in index.items():
            file = folder / name
            assert file.stat().st_size == row["bytes"] and digest(file) == row["sha256"]
        verified = verify(folder)
        browser = browser_check(folder)
        return dict(status="PASS", identity="INDEPENDENT_CODEX_AGENT_R4_REVIEW", bytes=path.stat().st_size,
                    sha256=digest(path), members=len(names), sha_checked=len(index), crc="PASS",
                    path_safety="PASS", independent_extraction="PASS", browser=browser, evidence=verified)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--browser", action="store_true")
    arg = parser.parse_args()
    result = review_archive(arg.archive.resolve()) if arg.archive else verify(ROOT)
    if arg.browser and not arg.archive:
        result["browser"] = browser_check(ROOT)
    message = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if arg.out:
        arg.out.write_text(message, encoding="utf-8")
    print(message)
