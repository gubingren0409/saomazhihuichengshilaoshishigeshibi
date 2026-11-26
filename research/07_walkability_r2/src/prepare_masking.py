"""Build controlled held-out tasks from frozen raw OSM, before prediction."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

from shapely.geometry import LineString, Point, mapping, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
CROP_M = 65
SITE_RANGE_M = 500
SPACING_M = 27
MAX_POS_PER_SITE = 4
MAX_NEG_PER_SITE = 2
SHADOW_M = .05
WALK = {"MAPPED_PEDESTRIAN_WAY", "EXPLICIT_FOOT_ON_WAY_AXIS"}
SPLITS = {"sh-huangpu-01": "development", "sh-library": "development",
          "sh-tower": "selection", "sh-wukang": "selection",
          "sh-newworld": "confirmation", "sh-exhibition": "confirmation"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def sign(path):
    return sha256(path.read_bytes()).hexdigest()


def rank(text):
    return sha256(("WALKABILITY_R2_MASKS_V1:" + str(text)).encode()).hexdigest()


def node_key(key):
    base = f"node/{key[0]}"
    return base if key[1:] == ("0", "0") else f"{base}@{key[1]}:{key[2]}"


def ground_node(raw):
    return all(raw.get(k) in (None, "", "0", "no") for k in ("layer", "level", "bridge", "tunnel", "indoor"))


def permission(tags):
    if any(k.startswith(("foot:", "access:")) and "conditional" in k for k in tags):
        return False
    allowed = {"yes", "designated", "permissive", "official"}
    return tags["foot"] in allowed if "foot" in tags else tags.get("access") not in {
        "no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry", "restricted"}


class Clip:
    def __init__(self, frozen, scene, engine, source_class):
        self.scene = scene
        self.path = frozen / scene["osm_clip"]
        raw = read(self.path)
        self.source = source_class(raw)
        self.segs, _, _ = engine._segments(raw)
        self.points = self.source.projected
        self.lines = [LineString([self.points[e.a[0]], self.points[e.b[0]]]) for e in self.segs]
        self.line_tree = STRtree(self.lines)
        self.byway = defaultdict(list)
        self.walk_at = defaultdict(set)
        self.native_nodes = {}
        for idx, e in enumerate(self.segs):
            self.byway[e.way].append(idx)
            for n in (e.a, e.b):
                self.native_nodes[n[0]] = self.points[n[0]]
                if e.evidence in WALK and n[1:] == ("0", "0"):
                    self.walk_at[n[0]].add(e.way)
        self.node_ids = sorted(self.walk_at)
        self.node_tree = STRtree([Point(self.points[n]) for n in self.node_ids])
        self.hard, self.bg, self.support = self._areas()
        self.hard_tree = STRtree([f["geometry"] for f in self.hard])
        self.refs = Counter(n for w in self.source.ways.values() for n in set(w["nodes"]))
        self.rel_members = {m["ref"] for rel in self.source.relations.values() for m in rel["members"]
                            if m["type"] == "way"}

    def _areas(self):
        hard, background, support = [], [], []
        obstacles, _ = self.source.obstacles([])
        for obj in obstacles:
            tags = obj.get("tags", {})
            typ = obj["kind"]
            if typ == "AREA" and (tags.get("landuse") == "grass" or tags.get("landcover") == "grass"):
                if permission(tags):
                    background.append(dict(obj, kind="GRASS"))
                    continue
            if typ == "AREA":
                if tags.get("natural") in {"water", "wetland"} or tags.get("water") or tags.get("waterway") == "riverbank":
                    typ = "WATER"
                elif not permission(tags):
                    typ = "RESTRICTED"
                else:
                    typ = "FLOWERBED"
            hard.append(dict(obj, kind=typ))
        for kind, items in (("way", self.source.ways), ("relation", self.source.relations)):
            for k, raw in items.items():
                tags = raw.get("tags", {})
                if tags.get("highway") == "pedestrian" and tags.get("area") == "yes":
                    typ = "PEDESTRIAN_AREA"
                elif tags.get("leisure") in {"park", "garden"} and permission(tags):
                    typ = "PARK"
                elif tags.get("surface") in {"paved", "paving_stones", "concrete", "asphalt"} and tags.get("area") == "yes" and tags.get("amenity") != "parking" and permission(tags):
                    typ = "PAVING"
                else:
                    if kind == "way" and tags.get("highway") and not permission(tags):
                        coords = self.source.known_coords(raw)
                        if len(coords) > 1:
                            hard.append(dict(id=f"way/{k}", kind="RESTRICTED", geometry=LineString(coords), tags=tags))
                    continue
                ident = f"{kind}/{k}"
                polygon = self.source.area(ident)
                if polygon is not None:
                    support.append(dict(id=ident, kind=typ, geometry=polygon, tags=tags))
        return hard, background, support

    def blockers(self, line, target=None):
        result = []
        for i in self.hard_tree.query(line, predicate="intersects"):
            obj = self.hard[int(i)]
            g = obj["geometry"]
            crossed = line.intersection(g)
            if target and obj["id"] == target["building_id"] and crossed.equals(Point(target["xy"])):
                continue
            if g.geom_type in {"Polygon", "MultiPolygon"} and obj["kind"] == "BUILDING":
                if line.relate_pattern(g, "F********"):
                    continue
            result.append(obj)
        return result

    def positives(self, center):
        doors = {int(e["native_id"].split("/")[-1]): e for e in self.scene.get("r4_entrances", [])}
        rows = []
        for way, ids in self.byway.items():
            raw = self.source.ways[way]
            tags, ns = raw.get("tags", {}), raw["nodes"]
            if (len(ids) != len(ns)-1 or len(ns) < 2 or ns[0] == ns[-1]
                    or way in self.rel_members or not ground_node(tags) or not permission(tags)
                    or any(self.segs[i].evidence not in WALK or self.segs[i].directions != (1, -1)
                           or self.segs[i].a[1:] != ("0", "0") or self.segs[i].b[1:] != ("0", "0") for i in ids)
                    or any(self.refs[n] > 1 for n in ns[1:-1])):
                continue
            line = LineString([self.points[n] for n in ns])
            if not 5 <= line.length <= 28 or line.distance(center) > SITE_RANGE_M:
                continue
            for origin, target in [(ns[0], ns[-1]), (ns[-1], ns[0])]:
                entry = doors.get(target)
                if not self.walk_at[origin] - {way} or (entry is None and not self.walk_at[target] - {way}):
                    continue
                if not permission(self.source.nodes[target].get("tags", {})):
                    continue
                target_rec = self.target(target, entry)
                if self.blockers(line, target_rec):
                    continue
                masked = self.shadows(line, way)
                hidden = {self.segs[i].way for i in masked}
                if not self.walk_at[origin] - hidden or (entry is None and not self.walk_at[target] - hidden):
                    continue
                if any(f["id"] in {f"way/{x}" for x in hidden} for f in self.support + self.hard + self.bg):
                    continue
                rows.append(dict(way=way, origin=origin, target=target_rec, line=line, masked=masked,
                                 hidden_intermediate=ns[1:-1], label="POSITIVE", obstacle_ids=[]))
                break
        return sorted(rows, key=lambda r: (not r["target"]["registered"], rank(r["way"])))

    def target(self, n, entry=None):
        return dict(id=f"node/{n}", xy=self.points[n], tags=self.source.nodes[n].get("tags", {}),
                    registered=entry is not None,
                    building_id=entry["target_building_native_id"] if entry else None)

    def shadows(self, line, way):
        # The masking reference removes all direct duplicates, including parallel records
        # where all of a source subsegment lies in the 5 cm numerical shadow.
        band = line.buffer(SHADOW_M, cap_style="flat")
        return set(self.byway[way]) | {
            int(i) for i in self.line_tree.query(band, predicate="intersects")
            if self.lines[int(i)].length > .001 and band.covers(self.lines[int(i)])}

    def negatives(self, center):
        rows = []
        nodes = [n for n in self.node_ids if Point(self.points[n]).distance(center) <= SITE_RANGE_M]
        for n in sorted(nodes, key=rank):
            a = Point(self.points[n])
            if any(obj["geometry"].covers(a) for obj in self.hard if obj["kind"] in {"WATER", "BUILDING"} and
                   obj["geometry"].distance(a) < .01):
                continue
            for raw in self.node_tree.query(a.buffer(24), predicate="intersects"):
                t = self.node_ids[int(raw)]
                if t <= n or t == n or self.walk_at[n] & self.walk_at[t]:
                    continue
                b = Point(self.points[t])
                line = LineString([a, b])
                if not 7 <= line.length <= 24:
                    continue
                ob = [x for x in self.blockers(line) if
                      (x["kind"] in {"BUILDING", "WATER"} and
                       line.intersection(x["geometry"]).length > 1 and
                       not (x["geometry"].covers(a) or x["geometry"].covers(b)))
                      or x["kind"] == "BARRIER" and line.crosses(x["geometry"])]
                if not ob:
                    continue
                # Omit candidate pairs where raw mapped approaches already use a gate,
                # bridge, or mapped segment through the exact blocker.
                if any(any(self.lines[int(i)].intersects(x["geometry"]) and
                           (self.lines[int(i)].crosses(x["geometry"])
                            or self.lines[int(i)].intersection(x["geometry"]).length > 1)
                           for x in ob) for i in self.line_tree.query(line.buffer(2), predicate="intersects")):
                    continue
                rows.append(dict(way=None, origin=n, target=self.target(t), line=line, masked=set(),
                                 hidden_intermediate=[], label="NEGATIVE",
                                 obstacle_ids=sorted({x["id"] for x in ob})))
            if len(rows) >= 100:
                break
        return sorted(rows, key=lambda r: rank((r["origin"], r["target"]["id"])))

    def export(self, row, task_id):
        target = row["target"]
        crop = Point(target["xy"]).buffer(CROP_M)
        nodes, edges = {}, []
        drop_nodes = set(row["hidden_intermediate"])
        for i in sorted(self.line_tree.query(crop, predicate="intersects")):
            i = int(i)
            seg = self.segs[i]
            if i in row["masked"] or seg.a[0] in drop_nodes or seg.b[0] in drop_nodes:
                continue
            # Cropping by graph segment retains visible boundary vertices without any
            # path reconstruction or access to the previously exported route.
            for raw_id in (seg.a, seg.b):
                n = raw_id[0]
                key = node_key(raw_id)
                nodes[key] = dict(id=key, xy=self.points[n], tags=self.source.nodes[n].get("tags", {}))
            for direction in seg.directions:
                a, b = (seg.a, seg.b) if direction == 1 else (seg.b, seg.a)
                edges.append(dict(id=f"way/{seg.way}/{seg.index}:{direction}", u=node_key(a), v=node_key(b),
                                  tags=self.source.ways[seg.way].get("tags", {}), kind="NATIVE_LINEAR"))
        origin = f"node/{row['origin']}"
        if origin not in nodes:
            raise ValueError(f"Origin not observed in {task_id}")
        if not target["registered"] and target["id"] not in nodes:
            raise ValueError(f"Network query target not observed in {task_id}")
        context = {key: [dict(id=f["id"], kind=f["kind"], geometry=mapping(f["geometry"]), tags=f.get("tags", {}))
                         for f in items if f["geometry"].intersects(crop)]
                   for key, items in (("hard", self.hard), ("background", self.bg), ("support", self.support))}
        kind = "REGISTERED_DOOR_TASK" if target["registered"] else "NETWORK_GAP_TASK"
        observed = dict(task_id=task_id, kind=kind, crs="EPSG:32651", origin=origin, target=target,
                        nodes=list(nodes.values()), edges=edges, context=context)
        masked = [self.segs[i] for i in sorted(row["masked"])]
        refs = dict(task_id=task_id, kind=kind, crs="EPSG:32651", label=row["label"],
                    group=self.scene["scene_id"], split=SPLITS[self.scene["scene_id"]],
                    geometry=mapping(row["line"]), source_geometry_length_m=row["line"].length,
                    source_clip=self.path.name, source_clip_sha256=sign(self.path),
                    original_way_id=f"way/{row['way']}" if row["way"] else None,
                    hidden_edges=[f"way/{e.way}/{e.index}" for e in masked],
                    hidden_intermediate_nodes=[f"node/{n}" for n in sorted(drop_nodes)],
                    negative_obstacle_ids=row["obstacle_ids"],
                    positive_observed_support_ids=[f["id"] for f in self.support if f["geometry"].intersection(row["line"]).length > .5],
                    origin=origin, target_id=target["id"])
        return observed, refs


def occupied(row, selected):
    ends = (row["line"].coords[0], row["line"].coords[-1])
    return any(
        (row["way"] is not None and row["way"] == old["way"])
        or row["line"].distance(old["line"]) < SPACING_M
        or (old["group"] != row["group"] and math.dist(row["target"]["xy"], old["target"]["xy"]) < 2*CROP_M)
        or any(math.dist(x, y) < 1 for x in ends for y in (old["line"].coords[0], old["line"].coords[-1]))
        for old in selected)


def check_leak(observed, ref):
    if set(observed) != {"task_id", "kind", "crs", "origin", "target", "nodes", "edges", "context"}:
        raise ValueError("Observed schema contains unapproved fields")
    hidden = set(ref["hidden_edges"])
    hidden_nodes = set(ref["hidden_intermediate_nodes"])
    if any(e["id"].split(":")[0] in hidden or (ref["original_way_id"] and e["id"].startswith(ref["original_way_id"]+"/"))
           for e in observed["edges"]):
        raise ValueError("Hidden edge, including reverse record, leaked")
    if any(n["id"].split("@")[0] in hidden_nodes for n in observed["nodes"]):
        raise ValueError("Hidden intermediate node leaked")
    if ref["original_way_id"] and any(f["id"] == ref["original_way_id"] for block in observed["context"].values() for f in block):
        raise ValueError("Hidden raw way leaked through context")
    if ref["label"] == "POSITIVE":
        line = shape(ref["geometry"])
        band = line.buffer(SHADOW_M, cap_style="flat")
        points = {n["id"]: n["xy"] for n in observed["nodes"]}
        for e in observed["edges"]:
            segment = LineString([points[e["u"]], points[e["v"]]])
            if segment.length > .001 and band.covers(segment):
                raise ValueError("Independently checked geometric shadow leaked")


def run(frozen, out, config):
    sys.path.insert(0, str(frozen.parent))
    from src.native_adapter import PROJECT, Source, load_frozen_engine

    engine = load_frozen_engine(frozen)
    scenes = read(frozen / "runs/source_scene_contracts.json")["scenes"]
    # Preserve the existing registered entrance when a valid reference is available.
    scenes.sort(key=lambda s: (s["scene_id"] != "sh-library", s["scene_id"]))
    selected, catalog = [], []
    for scene in scenes:
        clip = Clip(frozen, scene, engine, Source)
        center = Point(PROJECT(*scene["target"]))
        group = scene["scene_id"]
        for label, pool, limit in (("P", clip.positives(center), MAX_POS_PER_SITE),
                                   ("N", clip.negatives(center), MAX_NEG_PER_SITE)):
            counter = 0
            for row in pool:
                row["group"] = group
                if occupied(row, selected):
                    continue
                task_id = f"{label}-{group[3:]}-{counter+1:02d}"
                observed, ref = clip.export(row, task_id)
                check_leak(observed, ref)
                op = out / "observed" / f"{task_id}.json"
                rp = out / "reference" / f"{task_id}.json"
                write(op, observed)
                write(rp, ref)
                catalog.append(dict(task_id=task_id, group=group, split=ref["split"], label=ref["label"],
                                    kind=ref["kind"], observed=f"observed/{op.name}", observed_sha256=sign(op),
                                    reference=f"reference/{rp.name}", reference_sha256=sign(rp)))
                selected.append(row)
                counter += 1
                if counter >= limit:
                    break
            print(group, label, len(pool), "selected", counter, flush=True)
    write(out / "inventory.json", dict(status="FROZEN_BEFORE_PREDICTION", tasks=catalog))
    write(config, dict(status="LOCKED_BEFORE_PREDICTION", group_rule="Frozen building scene plus pairwise source-way/endpoints/spatial checks",
                       splits=SPLITS, crop_m=CROP_M, site_range_m=SITE_RANGE_M, spacing_m=SPACING_M,
                       shadow_m=SHADOW_M, max_positive=MAX_POS_PER_SITE*len(scenes),
                       max_negative=MAX_NEG_PER_SITE*len(scenes), endpoint_tolerance_m=2,
                       reference_buffer_m=2, minimum_reference_coverage=.70, max_inferred_ratio=1.5,
                       field_truth=False, no_external_requests=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, default=ROOT / "inputs/rev1/frozen_r4")
    parser.add_argument("--output", type=Path, default=ROOT / "data/masking")
    parser.add_argument("--config", type=Path, default=ROOT / "config/masking.json")
    args = parser.parse_args()
    run(args.frozen.resolve(), args.output.resolve(), args.config.resolve())
