"""Recompute this trial from raw OSM and frozen comparison inputs only."""
import argparse
import csv
from hashlib import file_digest
import json
import re
from pathlib import Path

from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import polygonize, transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
T = Transformer.from_crs(4326, 32651, always_xy=True).transform
GEOD = Geod(ellps="WGS84")
EPS = 0.001
EXIT, FOOT, PLAZA, PARK, BUILDING = 6897145227, 178719573, 2153738, 404709025, 161090899
GRADE = {"layer", "level", "repeat_on", "bridge", "tunnel", "indoor", "ele", "height",
         "min_height", "ramp", "incline", "step_count"}
WALK = {"footway", "pedestrian", "path", "steps", "living_street", "corridor"}
APPROACH = "way/178719573/110"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def choose(path, *alternatives):
    return next(p for p in (path, *alternatives) if p.is_file())


def verify(test, message):
    if not test:
        raise AssertionError(message)


def close(actual, expected, message, tol=EPS):
    verify(abs(actual - expected) <= tol, f"{message}: {actual}, {expected}")


def as_line(coords):
    return LineString([T(*xy) for xy in coords])


class Map:
    """A raw OSM index and conservative mapped-feature audit for this one location."""
    def __init__(self, path):
        self.path = path
        self.index = {kind: {} for kind in ("node", "way", "relation")}
        for obj in load(path)["elements"]:
            self.index[obj["type"]][obj["id"]] = obj
        self.positions = {idx: T(obj["lon"], obj["lat"]) for idx, obj in self.index["node"].items()}

    def coord(self, node):
        raw = self.index["node"][node]
        return [raw["lon"], raw["lat"]]

    def line(self, way):
        coords = [self.positions[node] for node in self.index["way"][way]["nodes"]]
        return LineString(coords)

    def area(self, kind, idx):
        obj = self.index[kind][idx]
        if kind == "way":
            line = self.line(idx)
            verify(line.is_closed, f"{kind}/{idx} not closed")
            return Polygon(line)
        rings = {role: [] for role in ("outer", "inner")}
        for member in obj["members"]:
            role = member["role"] or "outer"
            if member["type"] == "way" and role in rings:
                rings[role].append(self.line(member["ref"]))
        outer = unary_union(list(polygonize(rings["outer"])))
        inner = unary_union(list(polygonize(rings["inner"])))
        verify(not outer.is_empty and outer.is_valid and inner.is_valid, f"{kind}/{idx} rings not valid")
        return outer.difference(inner)

    def study(self, centerline):
        window = centerline.buffer(30)
        for kind, collection in self.index.items():
            for idx, obj in collection.items():
                tags = obj.get("tags", {})
                label = obstacle_class(tags)
                grade = {k: v for k, v in tags.items() if k in GRADE}
                if tags.get("highway") in {"steps", "elevator"}:
                    grade["highway"] = tags["highway"]
                if label is None and not grade:
                    continue
                ident = f"{kind}/{idx}"
                node_ids = ([idx] if kind == "node" else obj["nodes"] if kind == "way" else
                            [n for m in obj["members"] if m["type"] == "way"
                             for n in self.index["way"].get(m["ref"], {}).get("nodes", [])])
                points = [self.positions[n] for n in node_ids if n in self.positions]
                if not points:
                    continue
                xs, ys = zip(*points)
                extent = box(min(xs)-EPS, min(ys)-EPS, max(xs)+EPS, max(ys)+EPS)
                if not extent.intersects(window):
                    continue
                try:
                    if kind == "node":
                        geom = Point(points[0])
                    elif kind == "relation" or (kind == "way" and node_ids[0] == node_ids[-1]
                            and (label not in {None, "BARRIER"} or tags.get("area") == "yes")):
                        geom = self.area(kind, idx)
                    else:
                        geom = self.line(idx)
                    verify(geom.is_valid and not geom.is_empty, f"Unresolved geometry {ident}")
                except (AssertionError, KeyError, ValueError):
                    yield ident, "UNRESOLVED", grade, extent, tags
                    continue
                if geom.intersects(window):
                    yield ident, label, grade, geom, tags


def obstacle_class(t):
    if t.get("barrier") not in {None, "no", "kerb", "bollard"}:
        return "BARRIER"
    if t.get("building") not in {None, "no"} or t.get("building:part") not in {None, "no"}:
        return "BUILDING"
    if (t.get("natural") in {"water", "wetland"} or "water" in t
            or t.get("waterway") == "riverbank" or t.get("landuse") in {"reservoir", "basin"}):
        return "WATER"
    if (t.get("landuse") in {"grass", "flowerbed", "flower_bed"}
            or t.get("leisure") == "flowerbed" or t.get("landcover") in {"grass", "flowerbed"}
            or t.get("barrier") in {"flower_bed", "planter"} or t.get("garden:type") == "flower_bed"):
        return "PLANTING"
    if t.get("access") in {"no", "private"} or t.get("foot") in {"no", "private"}:
        return "RESTRICTED"
    return None


def overlaps(line, geom, tol=1e-6):
    return line.intersection(geom).length if line.distance(geom) <= tol else 0.0


def segment_scan(line, raw_features, exit_pt):
    obstacles, grades, terminal = [], [], []
    for ident, label, grade, geom, _ in raw_features:
        if not geom.intersects(line):
            continue
        shared = geom.intersection(line)
        if grade:
            grades.append({"id": ident, "grade": grade, "intersection_m": shared.length})
        if not label:
            continue
        if (ident == f"way/{BUILDING}" and shared.geom_type == "Point"
                and shared.distance(exit_pt) <= EPS):
            terminal.append(ident)
        else:
            obstacles.append({"id": ident, "kind": label, "intersection_m": shared.length})
    return {"obstacles": obstacles, "grade_intersections": grades, "terminal_only": terminal}


def base_checks(root, osm=None, trial_json=None, trial_geo=None):
    old = BASE / "OSM_GEOAPIFY_R4_REV1"
    trial = BASE / "OSM_GEOAPIFY_R4_REV1_NORTH_GAP_TRIAL"
    osm = osm or choose(root / "inputs/source/frozen_r4/data/source/sh-huangpu-01.osm.json",
                        old / "frozen_r4/data/source/sh-huangpu-01.osm.json")
    prior_json = trial_json or choose(root / "inputs/prior_trial/trial.json", trial / "public/trial.json")
    prior_geo = trial_geo or choose(root / "inputs/prior_trial/trial.geojson", trial / "public/trial.geojson")
    prior = load(prior_json)
    features = {f["properties"]["role"]: f for f in load(prior_geo)["features"]}
    m = Map(osm)
    source_exit = m.coord(EXIT)
    tags = m.index["node"][EXIT].get("tags", {})
    verify(source_exit == prior["entrance_coordinate"] == features["exit"]["geometry"]["coordinates"],
           "Frozen exit position or prior result differs")
    verify(tags.get("entrance") == "exit" and prior["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT",
           "Exit role changed")
    start = prior["approach_coordinate"]
    verify(start == features["approach_point"]["geometry"]["coordinates"], "Frozen approach position differs")
    connector = as_line(features["candidate"]["geometry"]["coordinates"])
    verify(features["candidate"]["geometry"]["coordinates"] == [start, source_exit],
           "Prior gap endpoints differ")
    native_geo = features["native_approach"]["geometry"]["coordinates"]
    native = as_line(native_geo)
    verify(native_geo[-1] == start, "Native prefix endpoint differs")
    raw_edge_refs = features["native_approach"]["properties"]["source_edges"]
    verify(len(raw_edge_refs) == len(native_geo)-1 and raw_edge_refs[-1] == APPROACH,
           "Prior native source edges incomplete or endpoint source mismatch")
    native_grades, shared_streets = [], []
    for idx, (ref, p, q) in enumerate(zip(raw_edge_refs, native_geo, native_geo[1:]), 1):
        kind, way, sub = ref.split("/")
        verify(kind == "way", f"Unexpected prior native ref {ref}")
        way, sub = int(way), int(sub)
        obj = m.index["way"][way]
        ns = obj["nodes"][sub:sub+2]
        verify(len(ns) == 2, f"Missing OSM segment {ref}")
        segment = LineString([m.positions[n] for n in ns])
        verify(max(segment.distance(Point(T(*xy))) for xy in (p, q)) <= EPS,
               f"Native prefix is off source edge {idx}, {ref}")
        source_tags = obj.get("tags", {})
        if source_tags.get("highway") not in WALK and source_tags.get("foot") not in {"yes", "designated", "permissive"}:
            shared_streets.append({"segment": idx, "source": ref, "highway": source_tags.get("highway")})
        g = {k: v for k, v in source_tags.items() if k in GRADE}
        if g:
            native_grades.append({"segment": idx, "source": ref, "grade": g})
    foot = m.line(FOOT)
    door = Point(T(*source_exit))
    approach = Point(T(*start))
    near_segs = []
    for idx, (x, y) in enumerate(zip(foot.coords, list(foot.coords)[1:])):
        near_segs.append((LineString([x, y]).distance(door), idx))
    nearest_foot, foot_idx = min(near_segs)
    verify(foot_idx == 110 and foot.distance(approach) <= EPS,
           "Nearest recorded footway segment is inconsistent")
    nearest_node = min((door.distance(Point(m.positions[idx])), idx)
                       for idx in m.index["way"][FOOT]["nodes"])
    nearby_foot_segments = []
    for way, obj in m.index["way"].items():
        t = obj.get("tags", {})
        if (not (t.get("highway") in WALK or t.get("foot") in {"yes", "designated", "permissive"})
                or t.get("area") == "yes" or obstacle_class(t) in {"RESTRICTED", "BARRIER"}
                or any(k in GRADE and v not in {"0", "no"} for k, v in t.items())):
            continue
        for idx, (a, b) in enumerate(zip(obj["nodes"], obj["nodes"][1:])):
            if a in m.positions and b in m.positions and m.positions[a] != m.positions[b]:
                seg = LineString([m.positions[a], m.positions[b]])
                if door.distance(seg) <= 30:
                    nearby_foot_segments.append((door.distance(seg), way, idx))
    verify(min(nearby_foot_segments) == (nearest_foot, FOOT, 110),
           "Nearest eligible raw segment in the local search changed")
    native_contacts = []
    for ident, label, grade, geom, _ in m.study(native):
        inter = geom.intersection(native)
        if inter.is_empty:
            continue
        if label and geom.geom_type in {"Polygon", "MultiPolygon"}:
            verify(native.relate_pattern(geom, "F********"), f"Frozen native route intersects obstacle interior {ident}")
        elif label:
            verify(False, f"Frozen native route intersects a mapped barrier or unresolved object {ident}")
        native_contacts.append({"source": ident, "category": label, "length_m": inter.length,
                                "classification": "BOUNDARY_ONLY" if label else "GRADE_OBJECT_POINT_CONTACT",
                                "grade_tags": grade})
    raw_ped = m.area("relation", PLAZA)
    park = m.area("way", PARK)
    build = m.area("way", BUILDING)
    verify(m.index["relation"][PLAZA]["tags"].get("highway") == "pedestrian", "Pedestrian polygon lost semantics")
    verify(m.index["way"][PARK]["tags"].get("leisure") == "park", "Park polygon lost semantics")
    verify(m.index["way"][FOOT]["tags"].get("highway") == "footway", "Raw footway lost semantics")
    verify(park.covers(connector), "Prior connector no longer inside native park")
    close(connector.length, 7.952217589612693, "Prior connector length")
    close(native.length, prior["baseline_approach_m"], "Prior native prefix length")
    close(native.length + connector.length, prior["hypothetical_total_m"], "Prior hypothetical total length")
    raw_features = list(m.study(connector))
    intersections = segment_scan(connector, raw_features, door)
    verify(intersections == {"obstacles": [], "grade_intersections": [], "terminal_only": [f"way/{BUILDING}"]},
           "Prior candidate conflicts or wall contact differ")
    verified_facts = {
        "raw_sha256": sha(osm), "prior_json_sha256": sha(prior_json), "prior_geojson_sha256": sha(prior_geo),
        "exit": {"source": f"node/{EXIT}", "coordinate": source_exit, "tags": tags},
        "approach_coordinate": start, "footway": f"way/{FOOT}/{foot_idx}",
        "length_epsg32651_m": connector.length,
        "length_wgs84_ellipsoid_m": GEOD.line_length(*zip(*features["candidate"]["geometry"]["coordinates"])),
        "pedestrian_area_boundary_distance_m": raw_ped.boundary.distance(door),
        "nearest_eligible_footway_segment_m": nearest_foot,
        "nearest_footway_native_node": {"id": nearest_node[1], "distance_m": nearest_node[0]},
        "building_overlap_m": overlaps(connector, build),
        "pedestrian_polygon_overlap_m": overlaps(connector, raw_ped),
        "native_footway_overlap_m": overlaps(connector, foot),
        "park_overlap_m": overlaps(connector, park),
        "same_source_membership_between_exit_and_footway": EXIT in m.index["way"][FOOT]["nodes"],
        "native_prefix_length_m": native.length,
        "native_prefix_geodesic_m": GEOD.line_length(*zip(*native_geo)),
        "native_prefix_segment_count": len(raw_edge_refs),
        "native_prefix_explicit_grade_tags": native_grades,
        "native_prefix_shared_street_segments": shared_streets,
        "native_prefix_mapped_contacts": native_contacts,
        "candidate_intersections": intersections,
        "nearby_obstacle_count": sum(bool(x[1]) for x in raw_features),
        "candidate_level": "UNKNOWN",
        "inbound_eligibility": "NOT_ELIGIBLE_EXIT",
    }
    context = dict(map=m, prior_geo=features, native=native, exit=door, park=park, plaza=raw_ped,
                   footway=foot, building=build, raw_features=raw_features, native_coords=native_geo,
                   approach=approach, prior_connector=connector)
    return verified_facts, context


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def projected(feature):
    return transform(T, shape(feature["geometry"]))


def recompute_domain(ctx, params):
    """Build the frontage independently using a flat-ended metric line buffer."""
    cap = ctx["exit"].buffer(params["radius_m"], quad_segs=16)
    window = ctx["prior_connector"].buffer(params["half_width_m"], cap_style="flat").intersection(cap)
    masks = [ctx["building"]]
    for ident, label, _, geom, _ in ctx["raw_features"]:
        if (label and ident != f"way/{BUILDING}"
                and geom.distance(window) <= params["obstacle_clearance_m"] + 1e-6):
            masks.append(geom.buffer(params["obstacle_clearance_m"], quad_segs=8))
    return window, ctx["park"].intersection(window).difference(unary_union(masks))


def experiment_checks(root, facts, ctx):
    results = load(root / "runs/experiment.json")
    config = load(root / "config/frontage.json")
    verify(sha(root / "config/frontage.json") == results["config_sha256"], "Configuration hash mismatch")
    verify(config["status"] == "LOCKED_BEFORE_FORMAL_ROUTE_COMPARISON", "Missing frozen configuration")
    verify(results["source_geometry"]["exit_wgs84"] == facts["exit"]["coordinate"], "Experiment moves exit")
    verify(results["source_geometry"]["exit_tags"] == facts["exit"]["tags"], "Experiment changes exit role")
    verify(results["external_requests"] == 0 and results["field_checks"] == 0, "Wrong run scope")
    verify(not results["comparison"]["admitted_as_verified_walkway"], "Hypothesis promoted into verified walkway")
    verify(not results["evidence_summary"]["positive_connector_walkability_evidence"], "Park mislabeled as walkway")
    for name, expected in (("exit_to_pedestrian_boundary_m", facts["pedestrian_area_boundary_distance_m"]),
                           ("exit_to_nearest_eligible_edge_m", facts["nearest_eligible_footway_segment_m"]),
                           ("prior_line_recomputed_m", facts["length_epsg32651_m"]),
                           ("park_coverage_m", facts["park_overlap_m"]),
                           ("explicit_walkway_coverage_m", facts["pedestrian_polygon_overlap_m"]),
                           ("building_interior_intersection_m", 0)):
        close(results["source_geometry"][name], expected, name)
    shapes = load(root / "data/route_variants.geojson")["features"]
    by = {(f["properties"]["variant"], f["properties"]["role"]): f for f in shapes}
    verify(len(by) == len(shapes), "Duplicate variant geometry role")
    masks = {f["properties"]["role"]: f for f in load(root / "data/constraints.geojson")["features"]
             if f["properties"]["role"] != "obstacle"}
    window, domain = recompute_domain(ctx, config["main"])
    close(projected(masks["N2_search_strip"]).symmetric_difference(window).area, 0, "Search strip geometry", 1e-4)
    close(projected(masks["N2_corridor"]).symmetric_difference(domain).area, 0, "Frontage corridor geometry", 1e-4)
    for name, expected in (("park", ctx["park"]), ("pedestrian_area", ctx["plaza"]), ("building", ctx["building"])):
        close(projected(masks[name]).symmetric_difference(expected).area, 0, f"Displayed {name} source geometry", 1e-4)
    verify(domain.area < ctx["park"].area * .01, "Whole park promoted to local domain")

    table = csv_rows(root / "data/segment_evidence.csv")
    level = csv_rows(root / "data/level_evidence.csv")
    obstacles = csv_rows(root / "data/obstacle_intersections.csv")
    verified = {}
    for name in ("N0", "N1", "N2"):
        result = results["variants"][name]
        route = by[name, "route"]["geometry"]["coordinates"]
        native = by[name, "native_approach"]["geometry"]["coordinates"]
        verify(native == ctx["native_coords"], f"{name} changes frozen prefix")
        verify(by[name, "exit"]["geometry"]["coordinates"] == facts["exit"]["coordinate"],
               f"{name} exit GeoJSON moved")
        verify(by[name, "exit"]["properties"]["tags"] == facts["exit"]["tags"], f"{name} exit tag changed")
        verify(by[name, "route_end"]["geometry"]["coordinates"] == route[-1] == result["end_wgs84"],
               f"{name} route end inconsistent")
        verify(result["entrance_role"] == "exit" and result["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT",
               f"{name} promoted exit to inbound")
        close(as_line(route).length, result["length_m"], f"{name} UTM length")
        close(GEOD.line_length(*zip(*route)), result["geodesic_length_m"], f"{name} WGS84 length")
        close(as_line(native).length, result["native_m"], f"{name} native length")
        close(Point(T(*route[-1])).distance(ctx["exit"]), result["residual_m"], f"{name} residual")
        native_rows = [x for x in table if x["variant"] == name and x["section"] == "FROZEN_NATIVE_APPROACH"]
        verify(len(native_rows) == len(native) - 1, f"{name} missing native evidence rows")
        unknown = {x["segment"] for x in facts["native_prefix_shared_street_segments"]}
        for i, (a, b, row, ref) in enumerate(zip(native, native[1:], native_rows,
                     ctx["prior_geo"]["native_approach"]["properties"]["source_edges"]), 1):
            verify(json.loads(row["start_wgs84"]) == a and json.loads(row["end_wgs84"]) == b,
                   f"{name} native row {i} differs from geometry")
            verify(json.loads(row["source_ids"]) == [ref.rsplit("/", 1)[0]]
                   and int(row["source_segment_index"]) == int(ref.split("/")[-1]),
                   f"{name} native row {i} source reference differs")
            close(float(row["length_m"]), as_line([a, b]).length, f"{name} native row {i} length")
            status = "UNKNOWN" if i in unknown else "NATIVE_MAPPED_WALKWAY"
            verify(row["evidence_status"] == status and row["field_status"] == "NOT_VERIFIED",
                   f"{name} native row {i} overstates source evidence")
        conn_rows = [x for x in table if x["variant"] == name and x["section"] == "HYPOTHETICAL_CONNECTOR"]
        native_contacts = [o for o in obstacles if o["variant"] == name and o["section"] == "FROZEN_NATIVE_APPROACH"]
        verify(len(native_contacts) == 12 and all(o["status"] == "NATIVE_SOURCE_BOUNDARY_CONTACT_ONLY" for o in native_contacts),
               f"{name} original boundary contacts not preserved")
        close(sum(float(o["intersection_m"]) for o in native_contacts if o["source_id"] == "way/178732703"),
              next(x["length_m"] for x in facts["native_prefix_mapped_contacts"] if x["source"] == "way/178732703"),
              f"{name} native grass-boundary length")
        contacts = [o for o in obstacles if o["variant"] == name and o["section"] in ("GAP_DIAGNOSTIC", "CANDIDATE")]
        verify(len(contacts) == 1 and contacts[0]["status"] == "ORIGINAL_EXIT_BOUNDARY_TOUCH_ONLY",
               f"{name} mapped obstacle contact was omitted or mischaracterized")
        verify(all(x["explicit_conflict"] == "False" for x in level if x["variant"] == name),
               f"{name} grade/access conflict not reflected in candidate")
        if name == "N0":
            gap_rows = [r for r in table if r["variant"] == name and r["section"] == "GAP_DIAGNOSTIC"]
            verify(len(gap_rows) == 1 and gap_rows[0]["evidence_status"] == "UNKNOWN", "N0 gap diagnostic missing")
            verify((name, "connector") not in by and not conn_rows and route == native
                   and result["status"] == "APPROACH_WITH_GAP" and result["residual_m"] > 0
                   and result["topology_status"] == "NO_NATIVE_EXIT_CONNECTION",
                   "N0 has an added exit connection")
            verified[name] = {"length_m": as_line(route).length, "residual_m": result["residual_m"],
                              "connector_segments": 0}
            continue
        geom = by[name, "connector"]
        candidate = geom["geometry"]["coordinates"]
        line = as_line(candidate)
        verify(candidate[0] == native[-1] and candidate[-1] == facts["exit"]["coordinate"]
               and route == native + candidate[1:], f"{name} path not actually continuous")
        verify(result["status"] == "HYPOTHETICAL_EXTERIOR_REACH"
               and result["connector_evidence"] == "HYPOTHETICAL_NOT_VERIFIED"
               and result["topology_status"] == "CONTINUOUS_IN_HYPOTHESIS_QUERY_ONLY"
               and result["level_status"].startswith("UNKNOWN")
               and geom["properties"]["routable_in_frozen_graph"] is False,
               f"{name} hypothesis/grade/native eligibility overclaim")
        if name == "N1":
            verify(candidate == ctx["prior_geo"]["candidate"]["geometry"]["coordinates"],
                   "N1 does not reproduce prior trial geometry")
        if name == "N2":
            verify(domain.buffer(1e-6).covers(line), "N2 leaves independently reconstructed local corridor")
            verify(geom["properties"]["source_scope_grade"] == "DERIVED_FROM_MAPPED_PARK_AREA",
                   "N2 source scope misclassified")
        verify(len(conn_rows) == len(candidate)-1, f"{name} missing candidate evidence rows")
        for idx, (a, b, row) in enumerate(zip(candidate, candidate[1:], conn_rows), 1):
            segment = as_line([a, b])
            scan = segment_scan(segment, ctx["raw_features"], ctx["exit"])
            verify(not scan["obstacles"] and not scan["grade_intersections"], f"{name} segment {idx} conflicts")
            verify(json.loads(row["start_wgs84"]) == a and json.loads(row["end_wgs84"]) == b,
                   f"{name} evidence segment {idx} geometry mismatch")
            close(float(row["length_m"]), segment.length, f"{name} evidence segment {idx} length")
            close(float(row["mapped_pedestrian_coverage_m"]), overlaps(segment, ctx["plaza"]), f"{name} evidence pedestrian area")
            close(float(row["mapped_park_coverage_m"]), overlaps(segment, ctx["park"]), f"{name} evidence park area")
            verify(row["evidence_status"] == "HYPOTHETICAL_NOT_VERIFIED"
                   and row["walkability_status"] == "NO_POSITIVE_COVERAGE"
                   and row["field_status"] == "NOT_VERIFIED", f"{name} evidence segment {idx} overclaim")
        close(line.length, result["connector_m"], f"{name} connector length")
        close(line.length, result["hypothesis_m"], f"{name} hypothesis length")
        verify(ctx["park"].buffer(1e-6).covers(line), f"{name} park containment lost")
        close(overlaps(line, ctx["plaza"]), 0, f"{name} mapped pedestrian area coverage")
        verified[name] = {"length_m": as_line(route).length, "residual_m": result["residual_m"],
                          "connector_m": line.length, "connector_segments": len(conn_rows),
                          "corridor_positive_walkability_m": 0.0,
                          "grade_unknown": True, "connector_geometry": candidate}

    verify(verified["N1"]["connector_geometry"] == verified["N2"]["connector_geometry"],
           "N1/N2 geometry comparison is inconsistent")
    sensitivity = []
    for actual, cfg in zip(results["sensitivity"], [config["main"], *config["sensitivity"]], strict=True):
        verify(all(actual[k] == v for k, v in cfg.items()), "Sensitivity uses an unlocked setting")
        if cfg is not config["main"]:
            verify(sum(config["main"][k] != v for k, v in cfg.items() if k != "id") == 1,
                   "Sensitivity is not one-factor")
        _, mask = recompute_domain(ctx, cfg)
        close(actual["corridor_area_m2"], mask.area, f"{cfg['id']} area")
        verify(mask.buffer(1e-6).covers(ctx["prior_connector"]), f"{cfg['id']} does not admit straight witness")
        # The covered straight witness attains the universal Euclidean distance lower bound.
        close(actual["connector_m"], ctx["prior_connector"].length, f"{cfg['id']} shortest path length")
        verify(actual["status"] == "HYPOTHETICAL_CANDIDATE"
               and actual["evidence_status"] == "HYPOTHETICAL_NOT_VERIFIED",
               f"{cfg['id']} sensitivity overclaim")
        sensitivity.append({"id": cfg["id"], "area_m2": mask.area, "straight_lower_bound_attained": True})
    visual = visual_checks(root, results, by, facts)
    return {"variants": verified, "sensitivity": sensitivity, "segment_rows": len(table),
            "visual_consistency": visual,
            "corridor_area_m2": domain.area, "park_area_m2": ctx["park"].area,
            "frozen_configuration_sha256": results["config_sha256"],
            "status": "PASS_INDEPENDENT_NO_VERIFIED_WALKABILITY_UPGRADE"}


def visual_checks(root, results, by, facts):
    html = (root / "visuals/index.html").read_text(encoding="utf-8")
    payload = json.loads(re.search(r'<script[^>]+id="payload"[^>]*>(.*?)</script>', html, re.S).group(1))
    verify(payload["variants"] == results["variants"] and payload["sensitivities"] == results["sensitivity"]
           and payload["source_geometry"] == results["source_geometry"], "Visual report results diverge")
    verify(payload["sha256"]["route"] == sha(root / "data/route_variants.geojson")
           and payload["sha256"]["constraints"] == sha(root / "data/constraints.geojson")
           and payload["sha256"]["clip"] == facts["raw_sha256"], "Visual geometry fingerprints diverge")
    exit_map = payload["points"]["exit"]
    exit_m = T(*facts["exit"]["coordinate"])
    checked = 0
    for f in payload["route_features"]:
        props = f["props"]
        source = by[props["variant"], props["role"]]["geometry"]
        if source["type"] == "LineString":
            seq = re.findall(r"[ML](-?[\d.]+),(-?[\d.]+)", f["shape"][0]["d"])
            actual = [[float(x), float(y)] for x, y in seq]
            if props["role"] == "connector":
                verify(props["evidence_status"] == "HYPOTHETICAL_NOT_VERIFIED", "Visual promotes hypothesis")
        else:
            actual = [f["shape"][0]["point"]]
        coords = source["coordinates"] if source["type"] == "LineString" else [source["coordinates"]]
        verify(len(actual) == len(coords), f"Visual vertex count differs for {props['variant']} {props['role']}")
        for shown, point in zip(actual, coords):
            x, y = T(*point)
            close(shown[0] - exit_map[0], x - exit_m[0], "Visual projected x coordinate")
            close(shown[1] - exit_map[1], exit_m[1] - y, "Visual projected y coordinate")
            checked += 1
    verify(not any(x["props"]["variant"] == "N0" and x["props"]["role"] == "connector"
                   for x in payload["route_features"]), "Visual N0 adds connector")
    verify(payload["exit_coord"] == facts["exit"]["coordinate"], "Visual moves exact registered exit")
    return {"status": "PASS", "visual_projected_vertices": checked, "html_sha256": sha(root / "visuals/index.html")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--osm", type=Path)
    parser.add_argument("--prior-json", type=Path)
    parser.add_argument("--prior-geojson", type=Path)
    parser.add_argument("--raw-only", action="store_true")
    parser.add_argument("--output", type=Path)
    a = parser.parse_args()
    facts, ctx = base_checks(a.root, a.osm, a.prior_json, a.prior_geojson)
    result = {"status": "PASS", "role": "independent_raw_osm_no_author_imports", "raw": facts}
    if not a.raw_only:
        result["experiment"] = experiment_checks(a.root, facts, ctx)
    if a.output:
        with a.output.open("x", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
