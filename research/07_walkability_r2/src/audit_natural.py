"""Cross-check published S and I geometry against raw source and frozen face edges."""
import argparse
import csv
from collections import Counter
from hashlib import file_digest
import json
import math
from pathlib import Path
import sys

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "inputs/rev1"))
from src.native_adapter import Source

PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
EPS = 1e-5
MUSEUM = "sh-huangpu-01"
GRASS = "way/178732700"
WALKWAYS = {178722057, 178723091, 178725152, 178725158}
NATIVE = "NATIVE_LINEAR"
INFERRED = "INFERRED_ALLOWED"
ALLOWED = {"yes", "designated", "official", "permissive"}
DENIED = {"no", "private", "customers", "destination", "delivery", "permit",
          "agricultural", "forestry", "restricted"}
NO = {None, "", "0", "no", "false"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def close(a, b, label):
    if abs(a - b) > EPS:
        raise ValueError(f"{label}: {a} vs {b}")


def check_semantics(root, source, start, north, south):
    out = read(root / "runs/semantics.json")
    collection = read(root / "data/semantics_routes.geojson")
    grass = source.area(GRASS)
    unique = set()
    clip_total = 0
    rows_per_way = Counter()
    overlap = Counter()
    with (root / "data/semantics_edges.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["restored"] != "True":
                continue
            coords = json.loads(row["coordinates_wgs84"])
            wid = int(row["way_id"])
            n = int(row["segment_index"])
            unique.add((wid, n, tuple(sorted(map(tuple, coords)))))
            clip_total += 1
            if row["scene_id"] != MUSEUM or wid not in WALKWAYS:
                continue
            way = source.ways[wid]
            expected = [list(source.coord(f"node/{k}")) for k in way["nodes"][n:n+2]]
            if coords != expected or way["tags"].get("highway") not in {"footway", "path", "pedestrian", "steps"}:
                raise ValueError(f"Restored segment is not an original mapped walking line: {wid}/{n}")
            l = LineString([PROJECT(*xy) for xy in coords])
            covered = l.intersection(grass).length
            close(l.length, float(row["length_m"]), f"original walk length {wid}/{n}")
            close(covered, float(row["background_overlap_m"]), f"raw grass overlap {wid}/{n}")
            if GRASS not in json.loads(row["source_grass_ids"]) or row["S1_status"] != "KEEP_NATIVE":
                raise ValueError(f"Raw grass was not recorded as the changed source: {wid}/{n}")
            if row["S0_status"] == "KEEP_NATIVE" or "MAPPED_PATH_OVER_LANDCOVER" not in json.loads(row["S1_reasons"]):
                raise ValueError("No recorded S0/S1 policy change on source path")
            rows_per_way[wid] += 1
            overlap[wid] += covered
    if len(unique) != out["source_identity_dedup"]["restored_segments"] or clip_total != out["raw_clip_totals"]["restored_segments"]:
        raise ValueError("Restored table count mismatch")
    routes = {}
    for f in collection["features"]:
        p = f["properties"]
        if p["role"] != "route":
            continue
        xy = f["geometry"]["coordinates"]
        end = north if p["target"] == "north_fixed" else south
        if xy[0] != start or math.dist(PROJECT(*xy[-1]), PROJECT(*end)) > EPS:
            raise ValueError("S route did not preserve original endpoints")
        total = LineString([PROJECT(*v) for v in xy]).length
        close(total, out["variants"][p["variant"]][p["target"]]["length_m"], "S route total")
        routes[p["variant"] + "/" + p["target"]] = total
    if len(routes) != 4 or any(out["variants"][v]["north_exit"]["status"] != "NO_ROUTE" for v in ("S0", "S1")):
        raise ValueError("Unexpected fixed-route extent")
    return dict(restored_clip_rows=clip_total, restored_unique_source_segments=len(unique),
                museum_four_raw_counts=dict(rows_per_way), museum_four_raw_overlap_m=dict(overlap),
                museum_four_total_overlap_m=sum(overlap.values()), independently_measured_routes_m=routes,
                north_exit_unreached_in_exported_strict_variants=True)


def direction_of(node_id):
    if not node_id.startswith("node/"):
        return None
    return int(node_id.split("/")[1].split("@")[0])


def access_denied(tags):
    return (tags.get("locked") == "yes" or tags.get("foot") in DENIED
            or tags.get("foot") is None and tags.get("access") in DENIED
            or any(k in tags for k in ("access:conditional", "foot:conditional", "oneway:conditional")))


def verify_native(edge, source, line):
    wid = int(edge["source_id"].split("/")[1])
    way = source.ways[wid]
    n = edge["segment_index"]
    a, b = way["nodes"][n:n+2]
    expected = LineString([source.projected[a], source.projected[b]])
    if line.difference(expected.buffer(EPS)).length > EPS:
        raise ValueError(f"Routed segment leaves frozen way {wid}/{n}")
    if way["tags"] != edge["tags"]:
        raise ValueError(f"Native path tags changed: {wid}/{n}")
    na, nb = direction_of(edge["u"]), direction_of(edge["v"])
    if (na is not None and na not in (a, b)) or (nb is not None and nb not in (a, b)):
        raise ValueError("Directed route does not connect the raw nodes or exact interior split")
    forward = expected.project(Point(line.coords[0])) < expected.project(Point(line.coords[-1]))
    oneway = way["tags"].get("oneway:foot")
    direct_access = way["tags"].get("foot:forward" if forward else "foot:backward")
    if access_denied(way["tags"]) or direct_access in DENIED or (oneway in {"yes", "1", "true"} and not forward) or (oneway == "-1" and forward):
        raise ValueError("Raw source shows explicitly unavailable route direction")
    for nd in (na, nb):
        if nd is not None and access_denied(source.nodes[nd].get("tags", {})):
            raise ValueError("Native source has an explicitly restricted node")
    return {k for k in (na, nb) if k is not None}


def frozen_edges(path, ids):
    if not ids:
        return {}
    found = {}
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            if MUSEUM not in line:
                continue
            first = line.partition('"edge_id":"')[2].partition('"')[0]
            if first in ids:
                item = json.loads(line)
                found[first] = item
                if ids <= found.keys():
                    return found
    raise ValueError(f"Missing frozen area edge IDs {sorted(ids - found.keys())[:8]}")


def evidence_id(edge_id):
    return edge_id.removesuffix("/reverse")


def audit_contacts(line, edge, obstacles, index, source_nodes, door):
    flags = []
    permitted = []
    for i in index.query(line, predicate="intersects"):
        row = obstacles[i]
        kind = row["kind"]
        tags = row["tags"]
        if tags.get("landuse") == "grass" or tags.get("landcover") == "grass":
            continue
        obj = row["geometry"]
        touch = obj.intersection(line)
        if touch.is_empty or obj.geom_type in {"Polygon", "MultiPolygon"} and line.relate_pattern(obj, "F********"):
            continue
        e_tags = edge["tags"]
        structure = e_tags.get("bridge") not in NO or e_tags.get("tunnel") not in NO
        water = tags.get("natural") in {"water", "wetland"} or tags.get("water") or tags.get("waterway") == "riverbank"
        distinct = e_tags.get("layer") is not None and tags.get("layer") is not None and e_tags["layer"] != tags["layer"]
        gate = touch.geom_type == "Point" and any(
            int(g["id"].split("/")[1]) in source_nodes and touch.distance(Point(g["xy"])) <= EPS
            for g in row.get("gates", ()) if g["allowed"]
        )
        if gate or structure and (water or distinct and kind in {"BUILDING", "BARRIER"}):
            permitted.append(row["id"])
        elif (edge["kind"] == INFERRED and touch.length <= EPS
              and all(Point(x).distance(door) <= EPS for x in getattr(touch, "coords", ()))):
            # Line approaches the exterior facade and may meet it at the unchanged exit coordinate.
            if kind == "BUILDING" and row["id"] == "way/161090899" and not obj.buffer(-EPS).intersects(line):
                continue
            flags.append(row["id"])
        else:
            flags.append(row["id"])
    return flags, permitted


def check_candidate(c, source, door, window, domain, park, face, cfg, obstacles, index, model):
    line = LineString(c["candidate_xy"])
    admitted = c["status"] == INFERRED
    flags, _ = audit_contacts(line, dict(kind=INFERRED, tags={}), obstacles, index, set(), door)
    if admitted:
        if not c["source_tags"] or access_denied(c["source_tags"]):
            raise ValueError("Inferred candidate uses an unavailable source edge")
        if line.difference(window.buffer(EPS)).length > EPS or line.difference(domain.buffer(EPS)).length > EPS:
            raise ValueError("Inferred candidate escapes the independently defined search area")
        if flags or line.length > cfg["max_length_m"] + EPS or line.length < cfg["min_length_m"] - EPS:
            raise ValueError("Admitted candidate breaks mapped obstacles or distance limits")
        if Point(line.coords[0]).distance(Point(c["xy"])) > EPS or Point(line.coords[-1]).distance(door) > EPS:
            raise ValueError("Candidate does not join its anchor and fixed door")
        if c["grade_status"] != "UNOBSERVED_CONTINUOUS_LEVEL":
            raise ValueError("Observed grade was incorrectly asserted on an unsupported segment")
        close(line.length, c["length_m"], "candidate geometry")
        close(c["cost_m"], line.length + cfg["level_assumption_penalty_m"] + cfg["inference_penalty_m"], "candidate penalty")
        support = park.union(face).intersection(line).length
        close(support / line.length, c["context"]["coverage_ratio"], "candidate source context coverage")
        if model != "ABL-C" and not (support >= cfg["context_overlap_fraction"] * line.length - EPS
                                    or c["context"]["cues"]):
            raise ValueError("Admitted connection has no context")
        if c["source_id"].startswith("way/"):
            way = source.obj(c["source_id"])
            n = c["source_segment_index"]
            coords = [source.projected[i] for i in way["nodes"][n:n+2]]
            if LineString(coords).distance(Point(c["xy"])) > EPS:
                raise ValueError("Native candidate anchor does not lie on its declared edge")
        elif c["source_id"] == "relation/2153738":
            if face.distance(Point(c["xy"])) > EPS:
                raise ValueError("Area-derived candidate anchor escapes its frozen tagged pedestrian face")
    return dict(id=c["id"], status=c["status"], reason=c["reason"], source=c["source_id"],
                length_m=line.length, context_coverage_m=park.union(face).intersection(line).length,
                mapped_hazard_contacts=flags, selected=c["route_selected"])


def check_natural(root, source, start, exit_point):
    data = read(root / "runs/inference.json")
    old = read(root / "inputs/north/runs/experiment.json")["source_geometry"]
    layers = read(root / "data/inference_routes.geojson")["features"]
    target = data["target"]
    door = Point(PROJECT(*exit_point))
    if target["id"] != old["exit_id"] or target["wgs84"] != exit_point or target["tags"] != {"entrance": "exit"}:
        raise ValueError("Original fixed exit source identity changed")
    map_exit = [f for f in layers if f["properties"]["role"] == "registered_exit"]
    if len(map_exit) != 1 or map_exit[0]["geometry"]["coordinates"] != exit_point:
        raise ValueError("Published map moved the original exit")
    obstacles, unlocated = source.obstacles([])
    index = STRtree([r["geometry"] for r in obstacles])
    edge_ids = {evidence_id(e["id"]) for m in data["methods"].values() if m["route"]
                for e in m["route"]["edges"] if e["kind"] not in {NATIVE, INFERRED}}
    area_evidence = frozen_edges(root / "inputs/rev1/data/edge_evidence.jsonl", edge_ids)
    results = {}
    park = source.area(old["park_id"])
    face = source.area(old["pedestrian_area_id"])
    window, domain = shape(data["window"]), shape(data["domain"])
    for method, model in data["methods"].items():
        route = model["route"]
        if not route:
            raise ValueError("Expected a route to a fixed endpoint or to its closest mapped approach")
        if route["edges"][0]["wgs84"][0] != start or route["edges"][0]["u"] != data["origin_native_id"]:
            raise ValueError("The route origin moved")
        plotted = [f for f in layers if f["properties"]["role"] == "route_segment" and
                   f["properties"]["variant"] == method]
        if len(plotted) != len(route["edges"]):
            raise ValueError("Map route segment count differs from the run")
        for n, (feature, edge) in enumerate(zip(plotted, route["edges"])):
            p = feature["properties"]
            if (p["sequence"] != n or p["edge_id"] != edge["id"] or p["hypothesis"] != edge["hypothesis"]
                    or feature["geometry"]["coordinates"] != edge["wgs84"]):
                raise ValueError("Map geometry/evidence differs from the run")
        total = Counter()
        checked = Counter()
        raw_conflicts = []
        allowed_contacts = Counter()
        tail = None
        selected = []
        for edge in route["edges"]:
            if tail and (tail["v"] != edge["u"] or math.dist(tail["xy"][-1], edge["xy"][0]) > EPS):
                raise ValueError("Published route geometry or directed sequence is discontinuous")
            tail = edge
            line = LineString(edge["xy"])
            geo = LineString([PROJECT(*p) for p in edge["wgs84"]])
            close(line.length, edge["length_m"], "segment length")
            if geo.hausdorff_distance(line) > EPS:
                raise ValueError("Published WGS84 route differs from metric route")
            kind = edge["kind"]
            nodes = set()
            if kind == NATIVE:
                nodes = verify_native(edge, source, line)
            elif kind == INFERRED:
                if not edge["hypothesis"] or edge["v"] != old["exit_id"]:
                    raise ValueError("Inferred path lost evidence label or fixed exit node")
                selected.append(edge["id"])
            else:
                original = area_evidence[evidence_id(edge["id"])]
                mapped = LineString(original["coordinates_metric"])
                if line.difference(mapped.buffer(EPS)).length > EPS:
                    raise ValueError("Published area path differs from its frozen geometry")
                if original["source_area_id"] != edge["source_id"] or original["direction"] != "BIDIRECTIONAL":
                    raise ValueError("Published area path lost frozen area identity or permissions")
            flags, allowed = audit_contacts(line, edge, obstacles, index, nodes, door)
            if flags:
                raw_conflicts.append(dict(edge_id=edge["id"], source=edge["source_id"], kind=kind, hazards=flags))
            allowed_contacts.update(allowed)
            total[kind] += line.length
            checked[kind] += 1
        close(sum(total.values()), route["length_m"], "route total")
        close(door.distance(Point(tail["xy"][-1])), model["residual_m"], "original exit residual")
        if selected != route["inferred_edges_used"] or len(selected) != model["used_inferred_edges"]:
            raise ValueError("Selected connectors are not the graph edge sequence")
        if model["reached_original_target"] and (tail["v"] != old["exit_id"] or tail["wgs84"][-1] != exit_point):
            raise ValueError("Reached route did not terminate at unchanged exit")
        if model["inbound_eligibility"] != "NOT_ELIGIBLE_EXIT" or model["field_validation"] != "NOT_VERIFIED":
            raise ValueError("Conditional exterior route was upgraded")
        candidates = model["candidates"]
        picked = next((r for r in candidates if r["route_selected"]), None)
        nearest = min(candidates, key=lambda r: r["gap_m"], default=None)
        candidates_checked = [check_candidate(c, source, door, window, domain, park, face, data["configuration"],
                                              obstacles, index, method) for c in candidates]
        if sum(r["status"] == INFERRED for r in candidates_checked) != model["admitted_edges"]:
            raise ValueError("Candidate count differs from published admission")
        chosen_report = None
        if picked:
            lp = LineString(picked["candidate_xy"])
            if lp.hausdorff_distance(LineString(tail["xy"])) > EPS:
                raise ValueError("Selected candidate feature is not the routed terminal edge")
            chosen_report = dict(anchor_id=picked["id"], source_id=picked["source_id"], length_m=lp.length,
                                 park_overlap_m=park.intersection(lp).length, tagged_pedestrian_overlap_m=face.intersection(lp).length,
                                 continuous_level="UNOBSERVED")
        results[method] = dict(status=model["status"], residual_m=door.distance(Point(tail["xy"][-1])),
                               lengths_m=dict(total), segment_counts=dict(checked),
                               mapped_hazard_contacts=raw_conflicts, mapped_gate_or_structure_contacts=dict(allowed_contacts),
                               candidates_rechecked=candidates_checked,
                               chosen_candidate=chosen_report, nearest_candidate=None if nearest is None else
                               dict(anchor_id=nearest["id"], source_id=nearest["source_id"], gap_m=nearest["gap_m"]))
    return dict(unchanged_exit=dict(id=old["exit_id"], coordinate=exit_point, tags=target["tags"]),
                raw_unlocated_hazards=unlocated, raw_context_geometries=len(obstacles), variants=results)


def main(output):
    root = ROOT
    scene_path = root / "inputs/rev1/frozen_r4/runs/source_scene_contracts.json"
    scene = next(s for s in read(scene_path)["scenes"] if s["scene_id"] == MUSEUM)
    clip = root / "inputs/rev1/frozen_r4" / scene["osm_clip"]
    source = Source(read(clip))
    old = read(root / "inputs/north/runs/experiment.json")["source_geometry"]
    start = list(source.coord(scene["start_native_id"]))
    south_id = read(root / "inputs/rev1/data/entrance_approach.json")["south"]["original_door"]["native_id"]
    south = list(source.coord(south_id))
    exit_point = list(source.coord(old["exit_id"]))
    result = dict(status="INDEPENDENT_GEOMETRY_RECOMPUTED", source_clip_sha256=digest(clip),
                  source_contract_sha256=digest(scene_path), crs="EPSG:32651",
                  semantics=check_semantics(root, source, start, old["approach_wgs84"], south),
                  natural=check_natural(root, source, start, exit_point), field_checks=0, external_requests=0)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "audits/independent_natural.json")
    main(parser.parse_args().output)
