"""Freeze exact historical inputs and audit native geometry before R4 path runs."""
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import os
from zipfile import ZipFile

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import polygonize, transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
OLD = {key: BASE / f"OSM_GEOAPIFY_PILOT_{key}" for key in ("R1", "R2", "R3")}
ZIP_PATHS = {
    "R1": "delivery/OPEN_REVIEW_AB_COMPLETION.zip",
    "R2": "delivery/OPEN_REVIEW.zip",
    "R3": "delivery/OPEN_REVIEW.zip",
}
ZIP_SHA = {
    "R1": "a4b902b530163477bdfd1092d7a88441c11e76950ee394cfb440213eb4453c12",
    "R2": "50e147fba6cec20db02bf2aed8a00c679ad1d8ca2ca5f45c2a5a0db1c89518a2",
    "R3": "13ffb6be75ca0b26710dd3d68bba2951e99539fa06eb51ab4d8195ea487e8c30",
}
INPUT_ZIP = Path.home() / "Downloads/OSM_GEOAPIFY_R4_CODEX_INPUTS.zip"
INPUT_SHA = "706f776ad62e71348ecd39e69df2ebb8cf5e8e16f85c6beaee3f244cb81a2b7e"
PBF_SHA = "e4b83f15cc358d347c47708239f8c556d9819a69f43ff32f42a23c405733e8f6"
MUSEUM = "sh-huangpu-01"
SOUTH = "relation/2385771"
FOCUS_M = 150
CRS = "EPSG:32651"
PROJECT = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
DATASET = "Geofabrik Shanghai 2026-11-08T21:21:00Z / replication 840 / ODbL 1.0"


def digest(value):
    return sha256(value).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def write_fixed(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == data, f"Frozen destination differs: {path}"
    else:
        with path.open("xb") as f:
            f.write(data)


def write_json(path, data):
    write_fixed(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def write_csv(path, rows):
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    write_fixed(path, buffer.getvalue().encode("utf-8-sig"))


class Evidence:
    def __init__(self):
        self.records = []
        self.archive = {}
        for stage, name in ZIP_PATHS.items():
            raw = self.track(OLD[stage] / name, stage, "SEALED_ORIGINAL_ZIP", expected=ZIP_SHA[stage])
            assert digest(raw) == ZIP_SHA[stage]
            zip_ = ZipFile(OLD[stage] / name)
            assert zip_.testzip() is None
            self.archive[stage] = (zip_, {r["path"]: r for r in json.loads(zip_.read("MANIFEST.json"))["entries"]})

    def track(self, path, stage, role, dest=None, expected=None, source=""):
        if not path.is_file():
            self.records.append(dict(stage=stage, role=role, source=source, original_path=str(path),
                r4_path=dest or "", bytes="", sha256="", status="MISSING"))
            if expected:
                raise FileNotFoundError(path)
            return None
        data = path.read_bytes()
        actual = digest(data)
        if expected:
            assert actual == expected, f"Protected input differs: {path}"
        if dest:
            write_fixed(ROOT / dest, data)
        self.records.append(dict(stage=stage, role=role, source=source, original_path=str(path),
            r4_path=dest or "", bytes=len(data), sha256=actual,
            status="HASH_VERIFIED" if expected else "HASH_RECORDED"))
        return data

    def member(self, stage, name, role, dest=None, source=""):
        archive, manifest = self.archive[stage]
        row = manifest[name]
        raw = self.track(OLD[stage] / name, stage, role, dest, row["sha256"], source)
        assert len(raw) == row["bytes"] and raw == archive.read(name), f"Original/ZIP mismatch: {name}"
        return raw

    def load_member(self, stage, name, role, dest=None, source=""):
        return json.loads(self.member(stage, name, role, dest, source))

    def close(self):
        for archive, _ in self.archive.values():
            archive.close()


def open_class(tags):
    if (tags.get("highway") == "pedestrian" and tags.get("area") == "yes") or tags.get("area:highway") == "pedestrian":
        return "PEDESTRIAN_AREA"
    if tags.get("place") in {"square", "courtyard"} or tags.get("leisure") == "courtyard":
        return "SQUARE_OR_COURTYARD_TAG_WITHOUT_PEDESTRIAN_AREA"
    if tags.get("leisure") in {"park", "garden"} or tags.get("landuse") in {"village_green", "recreation_ground"}:
        return "PARK_GARDEN_OR_RECREATION"
    if tags.get("landuse") in {"grass", "flowerbed"} or tags.get("leisure") == "flowerbed" or tags.get("natural") in {"grassland", "water"} or tags.get("waterway") == "riverbank":
        return "CONTEXT_GRASS_FLOWERBED_WATER"
    return None


def index(raw):
    return {kind: {e["id"]: e for e in raw["elements"] if e["type"] == kind}
            for kind in ("node", "way", "relation")}


def coord(node):
    return [node["lon"], node["lat"]]


def way_line(way, idx):
    return LineString([coord(idx["node"][node_id]) for node_id in way["nodes"]])


def rings(way_ids, idx):
    lines = [way_line(idx["way"][i], idx) for i in way_ids]
    if not lines:
        return None
    # Refuse area geometry if any member segment is not represented in a closed ring.
    outline = unary_union(lines)
    polygons = list(polygonize(outline))
    if not polygons:
        return None
    merged = unary_union(polygons)
    if outline.difference(unary_union([p.boundary for p in polygons])).length > 1e-12:
        return None
    return merged


def area(obj, idx):
    if obj["type"] == "way":
        native = obj.get("nodes", [])
        if len(native) < 4 or native[0] != native[-1]:
            return None, [], []
        polygon = Polygon(way_line(obj, idx).coords)
        return (polygon if polygon.is_valid and not polygon.is_empty else None), [obj["id"]], []
    if obj.get("tags", {}).get("type") != "multipolygon":
        return None, [], []
    outer = [m["ref"] for m in obj["members"] if m["type"] == "way" and m["role"] in {"", "outer"}]
    inner = [m["ref"] for m in obj["members"] if m["type"] == "way" and m["role"] == "inner"]
    exterior, holes = rings(outer, idx), rings(inner, idx)
    if exterior is None or (inner and (holes is None or not exterior.covers(holes))):
        return None, outer, inner
    polygon = exterior.difference(holes) if holes is not None else exterior
    return (polygon if polygon.is_valid and not polygon.is_empty else None), outer, inner


def feature_rows(scene, idx):
    building_kind, building_id = scene["building_native_id"].split("/")
    building = idx[building_kind][int(building_id)]
    outer = [building["id"]] if building_kind == "way" else [
        m["ref"] for m in building["members"] if m["role"] in {"", "outer"} and m["type"] == "way"
    ]
    footprint = transform(PROJECT, shape(scene["building_footprint"]))
    boundary_ids = {n for way in outer for n in idx["way"][way]["nodes"]}
    entries = []
    for node_id in sorted(boundary_ids):
        node = idx["node"][node_id]
        tags = node.get("tags", {})
        if "entrance" not in tags:
            continue
        entrance = tags["entrance"]
        xy = coord(node)
        distance = transform(PROJECT, Point(xy)).distance(footprint.boundary)
        eligible = (entrance in {"yes", "main", "entrance"} and distance <= 0.01
                    and tags.get("access") not in {"no", "private", "restricted"}
                    and tags.get("foot") not in {"no", "private", "restricted"})
        reason = "NATIVE_OUTER_RING_OSM_TAGGED_INBOUND_REFERENCE" if eligible else (
            "EXIT_INBOUND_APPLICABILITY_UNKNOWN" if entrance == "exit" else "INBOUND_APPLICABILITY_UNCONFIRMED_OR_RESTRICTED")
        entries.append(dict(native_id=f"node/{node_id}", coordinate=xy, tags=tags, entrance_grade="OSM_TAGGED",
                            eligible=eligible, reason=reason, original_coordinate=xy, entrance_type=entrance,
                            target_building_native_id=scene["building_native_id"], boundary_distance_m=round(distance, 7),
                            physical_access="UNKNOWN", public_access="UNKNOWN", entrance_field_verified=False))
    if scene.get("entry_native_id"):
        ref = next(e for e in entries if e["native_id"] == scene["entry_native_id"])
        assert ref["coordinate"] == scene["target"], scene["scene_id"]
    inventory = []
    incomplete = Counter()
    for kind in ("way", "relation"):
        for obj in idx[kind].values():
            tags = obj.get("tags", {})
            category = open_class(tags)
            if not category:
                continue
            try:
                polygon, shell_ids, hole_ids = area(obj, idx)
            except (KeyError, ValueError):
                polygon = None
            if polygon is None:
                incomplete[category] += 1
                continue
            metric = transform(PROJECT, polygon)
            distance = metric.distance(footprint)
            if distance > FOCUS_M:
                continue
            native_id = f"{kind}/{obj['id']}"
            selected = (native_id == SOUTH if scene["scene_id"] == MUSEUM else category == "PEDESTRIAN_AREA")
            inventory.append(dict(scene_id=scene["scene_id"], native_id=native_id, tags=tags,
                category=category, geometry=mapping(polygon), crs="EPSG:4326", analysis_crs=CRS,
                distance_to_target_footprint_m=round(distance, 4), area_m2=round(metric.area, 4),
                outer_way_ids=shell_ids, inner_way_ids=hole_ids, layer=tags.get("layer", "UNSPECIFIED"),
                eligibility="FOCUS_AREA_INVENTORY" if selected else "CONTEXT_ONLY",
                access_evidence="UNKNOWN_NO_AREA_ONLY_ROUTING", geometry_status="SOURCE_RINGS_RECONSTRUCTED"))
    return entries, sorted(inventory, key=lambda x: (x["distance_to_target_footprint_m"], x["native_id"])), dict(incomplete)


def process_prompt(ev):
    raw = ev.track(INPUT_ZIP, "R4", "USER_INSTRUCTION_ZIP", expected=INPUT_SHA)
    assert raw
    with ZipFile(INPUT_ZIP) as z:
        assert z.testzip() is None
        prefix = "OSM_GEOAPIFY_R4_CODEX_INPUTS/"
        files = json.loads(z.read(prefix + "MANIFEST_SHA256.json"))
        assert {i["path"] for i in files} == {n[len(prefix):] for n in z.namelist() if not n.endswith("MANIFEST_SHA256.json")}
        for entry in files:
            raw = z.read(prefix + entry["path"])
            assert len(raw) == entry["bytes"] and digest(raw) == entry["sha256"]
            write_fixed(ROOT / "inputs/prompt" / entry["path"], raw)


def git_state():
    roots = [Path("E:/智慧城市和位置服务"), Path("E:/智慧城市和位置服务/project/Smart_Cities_and_Location_Services")]
    output = []
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    for root in roots:
        def git(*args):
            return subprocess.run(["git", "-C", str(root), *args], env=env, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode("utf-8").strip("\n")
        try:
            head = git("rev-parse", "HEAD").strip()
            index_path = (root / git("rev-parse", "--git-path", "index").strip()).resolve()
            worktree = git("status", "--porcelain=v1", "--untracked-files=no")
        except subprocess.CalledProcessError:
            continue
        output.append(dict(worktree=str(root), head=head, index_path=str(index_path),
                           index_sha256=digest(index_path.read_bytes()),
                           tracked_status_counts=dict(Counter(line[:2] for line in worktree.splitlines()))))
    return output


def prepare():
    ev = Evidence()
    process_prompt(ev)
    write_json(ROOT / "audits/old_git_before.json", git_state())
    ev.track(OLD["R1"] / "runtime/shanghai-261108.osm.pbf", "R1", "SHANGHAI_FULL_PBF_READ_ONLY",
             expected=PBF_SHA, source=DATASET)
    r3 = ev.load_member("R3", "runs/scene_contracts.json", "R3_FROZEN_SCENE_CONTRACTS", "data/source/historical/r3_scene_contracts.json")
    old_museum = ev.load_member("R3", "inputs/r1/runs/scene_contract.json", "R1_MUSEUM_FROZEN_CONTRACT",
                                "data/source/historical/r1_scene_contract.json")
    ev.member("R1", "runs/scene_contract.json", "R1_MUSEUM_ORIGINAL_CONTRACT")
    ev.member("R3", "runs/comparison.json", "R3_FROZEN_COMPARISON", "data/source/historical/r3_comparison.json")
    for n in ("05_DECISION_ON_TWO_PATHS.md", "08_COMMON_INTERMEDIATE_REPRESENTATION.md", "09_DUAL_PATH_ALGORITHM_ROADMAP.md"):
        ev.member("R3", n, "R3_STUDY_CONTEXT", "data/source/historical/r3_" + n)
    for n in ("01_ROUTE_DIFFERENCE_DIAGNOSIS.md", "analysis/topology.json", "analysis/endpoint_metrics.json",
              "plaza_connectivity_audit.csv", "route_segment_differences.csv"):
        ev.member("R2", n, "R2_SOURCE_DIAGNOSIS", "data/source/historical/r2_" + Path(n).name)
    for n in ("inputs/user_scores_20261109T110307129Z.csv", "07_USER_SCORE_SHEET.csv"):
        ev.member("R3", n, "HISTORICAL_USER_SCORE" if n.startswith("inputs") else "R3_BLANK_SCORE_TEMPLATE")
    downloads = Path.home() / "Downloads"
    score_names = [p.name for p in downloads.iterdir() if p.is_file() and
                   any(x in p.name.lower() for x in ("score", "评分"))]
    score_records = [{"file_name": p, "bytes": (downloads / p).stat().st_size,
                      "sha256": digest((downloads / p).read_bytes())} for p in sorted(score_names)]
    blank = list(csv.DictReader((OLD["R3"] / "07_USER_SCORE_SHEET.csv").open(encoding="utf-8-sig", newline="")))
    ids = {r["blind_scene_id"] for r in blank}
    matches = []
    for rec in score_records:
        if not rec["file_name"].endswith(".csv"):
            continue
        with (downloads / rec["file_name"]).open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        fields = {"blind_scene_id", "detail_pair_id", "context_pair_id", "submitted_utc"}
        if any(r.get("blind_scene_id") in ids and any(v for k, v in r.items() if k not in fields) for r in rows):
            matches.append(rec["file_name"])
    write_json(ROOT / "audits/r3_score_availability.json", {
        "status": "R3_USER_SCORE_PRESENT" if matches else "PENDING_USER_REVIEW",
        "searched_directories": [str(downloads), str(OLD["R3"])],
        "checked_downloads": score_records, "matches_r3_frozen_ids_with_scores": matches,
        "r3_template_empty_fields": all(not v for r in blank for k,v in r.items() if k not in
                                        {"blind_scene_id","detail_pair_id","context_pair_id"}),
        "historical_r1_scores_kept_separate": True})
    focus_rows, entrance_rows, all_areas, scenes = [], [], [], []
    raw_idx = None
    for source_scene in [old_museum, *r3["scenes"]]:
        s = dict(source_scene)
        sid = s["scene_id"]
        path = f"data/source/{sid}.osm.json"
        if sid == MUSEUM:
            raw = ev.load_member("R3", "inputs/r1/data/sh-huangpu-01.osm.json", "R1_MUSEUM_OSM_CLIP", path, DATASET)
            ev.member("R1", f"data/{sid}.osm.json", "R1_MUSEUM_ORIGINAL_OSM_CLIP", source=DATASET)
        else:
            raw = ev.load_member("R3", source_scene["osm_clip"], "R3_FROZEN_OSM_CLIP", path, DATASET)
        assert digest((ROOT / path).read_bytes()) == s["snapshot_sha256"]
        idx = index(raw)
        if sid == MUSEUM:
            raw_idx = idx
        entries, features, incomplete = feature_rows(s, idx)
        all_areas.extend(features)
        entrance_rows.extend(dict(scene_id=sid, **e) for e in entries)
        foci = [f["native_id"] for f in features if f["eligibility"] == "FOCUS_AREA_INVENTORY"]
        focus_rows.append(dict(scene_id=sid, building=s["label"], building_native_id=s["building_native_id"],
                               nearby_focus_count=len(foci), focus_native_ids="|".join(foci),
                               context_feature_count=len(features)-len(foci), registered_outer_ring_count=len(entries),
                               eligible_inbound_count=sum(x["eligible"] for x in entries),
                               target_role=s["target_role"], unclosed_or_invalid_clipwide=json.dumps(incomplete, sort_keys=True),
                               source_timestamp=raw["osm3s"]["timestamp_osm_base"]))
        s.update(osm_clip=path, r4_focus_space_ids=foci, r4_entrances=entries,
                 snapshot_time=raw["osm3s"]["timestamp_osm_base"],
                 snapshot_bounds_wsen=raw["bounds_wsen"],
                 historical_local_route=f"data/source/historical/{sid}_local_route.json",
                 historical_hosted_route=f"data/source/historical/{sid}_hosted_route.geojson",
                 historical_local_diagnostic=(f"data/source/historical/{sid}_local_approach_diagnostic.json" if sid==MUSEUM else None))
        scenes.append(s)
    write_json(ROOT / "runs/source_scene_contracts.json", dict(
        execution="R4_PROTECTED_NATIVE_INPUTS", selection_phase="NATIVE_GEOMETRY_BEFORE_R4_ROUTE", source_crs="EPSG:4326",
        analysis_crs=CRS, focus_footprint_distance_m=FOCUS_M, museum_focus_native_id=SOUTH,
        source_scene_policy="R1 frozen museum + every R3 frozen scene; no routing-based exclusion",
        entrance_policy="Native tagged exact target outer-ring nodes, inbound known label, excludes exit and access restriction",
        scenes=scenes))
    write_json(ROOT / "runs/source_open_spaces.json", dict(crs="EPSG:4326", analysis_crs=CRS, features=all_areas))
    write_csv(ROOT / "data/source_scene_inventory.csv", focus_rows)
    write_csv(ROOT / "data/registered_entrances.csv", entrance_rows)
    write_csv(ROOT / "data/open_space_inventory.csv", [{k:v for k,v in row.items() if k!="geometry"} for row in all_areas])
    baseline = ev.load_member("R3", "runs/local_results.json", "R3_FROZEN_B0_RECORDS", "data/source/historical/r3_local_results.json")
    for s in scenes:
        sid = s["scene_id"]
        if sid == MUSEUM:
            for name, dest in (("local_route.json", s["historical_local_route"]),
                               ("local_approach_diagnostic.json", s["historical_local_diagnostic"])):
                ev.member("R3", f"inputs/r1/runs/{name}", "HISTORICAL_LOCAL_MUSEUM", dest)
            ev.member("R3", f"inputs/r1/visuals/geoapify/{sid}_probe_walk.geojson", "HISTORICAL_HOSTED_ROUTE", s["historical_hosted_route"])
        else:
            record = next(x for x in baseline["scenes"] if x["scene_id"] == sid)
            write_json(ROOT / s["historical_local_route"], record["route"])
            ev.member("R3", record["route_artifact"], "FROZEN_B0_GEOJSON", f"data/source/historical/{sid}_local_route.geojson")
            ev.member("R3", f"hosted/{sid}_route.geojson", "HISTORICAL_HOSTED_ROUTE", s["historical_hosted_route"])
    ev.member("R3", "src/frozen_r1/local_route.py", "FROZEN_ROUTING_PROFILE_READ_ONLY")
    write_csv(ROOT / "data/manifest.csv", ev.records)
    ev.close()
    assert raw_idx
    huangpi(raw_idx)
    print(json.dumps({"scenes":len(scenes), "open_space_inventory_rows":len(all_areas),
                      "registered_entrances":len(entrance_rows), "source_records":len(ev.records)}, ensure_ascii=False))


def huangpi(idx):
    history = read_json(ROOT / "data/source/historical/r2_topology.json")["origin"]
    axes = history["hosted_candidate_road_axis_way_ids"]
    ids = [history["common_way_id"], *axes, history["crossing_way_id"], *history["local_detour_way_ids"]]
    def evidence(kind, native):
        item = idx[kind][native]
        tags = item.get("tags", {})
        return dict(native_id=f"{kind}/{native}", original_tags=tags,
                    foot=tags.get("foot", "UNKNOWN"), sidewalk=tags.get("sidewalk", "UNKNOWN"),
                    access=tags.get("access", "UNKNOWN"), crossing=tags.get("crossing", "UNKNOWN"),
                    layer=tags.get("layer", "UNKNOWN"), coords=coord(item) if kind=="node" else None,
                    source_node_ids=item.get("nodes"), decision="AXIS_FILTERED_BY_FROZEN_PROFILE"
                    if kind=="way" and native in axes else "SOURCE_CONTEXT_ONLY",
                    explicit_crossing_evidence=(tags.get("highway")=="crossing" or tags.get("footway")=="crossing"))
    way_records = [evidence("way", n) for n in dict.fromkeys(ids)]
    node_ids = [history[k] for k in ("split_node_id","local_dead_end_node_id","signal_node_id","rejoin_node_id")]
    node_records = [evidence("node", n) for n in dict.fromkeys(node_ids + history["crossing_node_ids"])]
    write_json(ROOT / "runs/huangpi_crossing_diagnostic.json", dict(
        status="DIAGNOSTIC_ONLY_NO_CONNECTION_ADDED", source_timestamp="2026-11-08T21:21:00Z",
        evidence="OBSERVED_RAW_OSM_TAGS; HISTORICAL_RECOMPUTED_R2_ROUTE_CORRESPONDENCE",
        hosted_internal_topology="UNKNOWN", actual_walking_permission="UNKNOWN",
        ways=way_records, nodes=node_records, historical_r2_alignment=history))
    write_csv(ROOT / "data/huangpi_crossing_diagnostic.csv", way_records + node_records)


if __name__ == "__main__":
    prepare()
