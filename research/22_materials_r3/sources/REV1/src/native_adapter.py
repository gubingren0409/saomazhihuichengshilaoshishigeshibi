"""Read the six frozen OSM clips and construct auditable metric inputs."""
from collections import defaultdict
import importlib.util
import sys
from pathlib import Path

from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, box
from shapely.ops import polygonize, unary_union

PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
INVERSE = Transformer.from_crs(32651, 4326, always_xy=True).transform
GEOD = Geod(ellps="WGS84")
GROUND_LEVELS = {None, "", "0"}
LEVEL_TAGS = {"bridge", "tunnel", "ford", "indoor", "covered"}
GATE_TAGS = {"gate", "lift_gate", "swing_gate", "turnstile", "kissing_gate"}
FENCE_TAGS = {"wall", "fence", "hedge", "retaining_wall", "chain", "city_wall", "jersey_barrier"}
STRUCTURAL_BARRIERS = FENCE_TAGS | GATE_TAGS
ANCHOR_EVIDENCE = {"MAPPED_PEDESTRIAN_WAY", "EXPLICIT_FOOT_ON_WAY_AXIS"}
PUBLIC = {"yes", "designated", "permissive", "official"}
RESTRICTED = {"no", "private", "customers", "destination", "delivery", "permit", "agricultural", "forestry", "restricted"}
BASELINE_FIELDS = ("status", "failure_reason", "geometry", "length_m", "snap_start_m", "snap_end_m",
                   "snap_start", "snap_end", "way_ids", "node_ids", "segments", "profile", "graph_stats")


def load_frozen_engine(root):
    path = root / "src/frozen_r1/local_route.py"
    spec = importlib.util.spec_from_file_location("r4_rev1_frozen_baseline", path)
    if spec is None:
        raise ValueError("Missing frozen local routing engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # In-memory source execution avoids writing bytecode into the protected subset.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def restricted(tags):
    return any(key.endswith(":conditional") and key.split(":")[0] in {"access", "foot", "oneway"}
               for key in tags) or tags.get("access") in RESTRICTED or tags.get("foot") in RESTRICTED


def ground(tags):
    return (all(tags.get(key) in (None, "", "no") for key in LEVEL_TAGS)
            and tags.get("layer") in GROUND_LEVELS and tags.get("level") in GROUND_LEVELS)


def node_id(value):
    return f"node/{value}"


def node_number(value):
    kind, ident = value.split("/")
    if kind != "node":
        raise ValueError(f"Expected native node: {value}")
    return int(ident)


def lonlat(node):
    return (node["lon"], node["lat"])


class Source:
    def __init__(self, raw):
        idx = {kind: {} for kind in ("node", "way", "relation")}
        for row in raw["elements"]:
            idx[row["type"]][row["id"]] = row
        self.nodes, self.ways, self.relations = (idx[k] for k in idx)
        self.projected = {k: PROJECT(*lonlat(v)) for k, v in self.nodes.items()}

    def coord(self, ident):
        return lonlat(self.nodes[node_number(ident)])

    def obj(self, ident):
        kind, number = ident.split("/")
        return (self.ways if kind == "way" else self.relations)[int(number)]

    def outline(self, ident):
        obj = self.obj(ident)
        if obj["type"] == "way":
            return set(obj["nodes"])
        return {n for m in obj["members"] if m["type"] == "way" and m["role"] in ("", "outer")
                for n in self.ways[m["ref"]]["nodes"]}

    def rings(self, ident):
        obj = self.obj(ident)
        if obj["type"] == "way":
            return [obj], []
        grouped = {"outer": [], "inner": []}
        for m in obj["members"]:
            role = m["role"] or "outer"
            if m["type"] != "way" or role not in grouped or m["ref"] not in self.ways:
                return None
            grouped[role].append(self.ways[m["ref"]])
        return grouped["outer"], grouped["inner"]

    def area(self, ident):
        rings = self.rings(ident)
        if rings is None:
            return None
        areas = []
        for ways in rings:
            if any(len(w["nodes"]) < 2 or any(n not in self.projected for n in w["nodes"]) for w in ways):
                return None
            lines = [LineString([self.projected[n] for n in w["nodes"]]) for w in ways]
            area = unary_union(list(polygonize(lines)))
            if lines and (area.is_empty or any(line.difference(area.boundary.buffer(1e-7)).length > 1e-6
                                               for line in lines)):
                return None
            areas.append(area)
        outer, inner = areas
        if outer.is_empty or (not inner.is_empty and not outer.covers(inner)):
            return None
        area = outer.difference(inner)
        return area if not area.is_empty and area.is_valid and area.geom_type in {"Polygon", "MultiPolygon"} else None

    def known_coords(self, obj):
        if obj["type"] == "way":
            return [self.projected[n] for n in obj["nodes"] if n in self.projected]
        return [self.projected[n] for m in obj["members"] if m["type"] == "way" and m["ref"] in self.ways
                for n in self.ways[m["ref"]]["nodes"] if n in self.projected]

    def obstacles(self, active_areas):
        """Keep complete hazards and local extents of unresolvable hazards."""
        study = unary_union(active_areas).buffer(30)
        rows, unlocated = [], []
        for kind, objects in (("way", self.ways), ("relation", self.relations)):
            for number, obj in objects.items():
                tags = obj.get("tags", {})
                is_barrier = kind == "way" and tags.get("barrier") in STRUCTURAL_BARRIERS
                if tags.get("building") not in (None, "no") or tags.get("building:part") not in (None, "no"):
                    classification = "BUILDING"
                elif (tags.get("natural") in {"water", "wetland"} or tags.get("water")
                      or tags.get("waterway") == "riverbank" or tags.get("landuse") in {"reservoir", "basin", "grass", "flowerbed", "flower_bed"}
                      or tags.get("leisure") == "flowerbed" or tags.get("landcover") in {"grass", "flowerbed"}
                      or tags.get("barrier") in {"flower_bed", "planter"} or tags.get("garden:type") == "flower_bed"
                      or (restricted(tags) and (tags.get("area") == "yes" or tags.get("type") == "multipolygon"))):
                    classification = "AREA"
                elif is_barrier:
                    classification = "BARRIER"
                else:
                    continue
                ident = f"{kind}/{number}"
                coords = self.known_coords(obj)
                if not coords:
                    unlocated.append(ident)
                    continue
                xs, ys = zip(*coords)
                footprint = box(min(xs), min(ys), max(xs), max(ys)).buffer(0.01)
                if not study.is_empty and not footprint.intersects(study):
                    continue
                gates = []
                if classification == "BARRIER" and len(coords) == len(obj["nodes"]) and len(coords) > 1:
                    shape = LineString(coords)
                    for n in obj["nodes"]:
                        gate_tags = self.nodes[n].get("tags", {})
                        if (gate_tags.get("barrier") in GATE_TAGS and ground(gate_tags) and not restricted(gate_tags)
                                and gate_tags.get("locked") != "yes"
                                and (gate_tags.get("foot") in PUBLIC or gate_tags.get("access") in PUBLIC)):
                            gates.append({"id": node_id(n), "xy": self.projected[n], "allowed": True, "tags": gate_tags})
                else:
                    shape = self.area(ident) if classification != "BARRIER" else None
                if shape is None:
                    shape, classification = footprint, "UNKNOWN"
                rows.append(dict(id=ident, kind=classification, geometry=shape, gates=gates, tags=tags))
        for n, obj in self.nodes.items():
            tags = obj.get("tags", {})
            barrier = tags.get("barrier")
            is_allowed_gate = (barrier in GATE_TAGS and ground(tags) and not restricted(tags)
                               and tags.get("locked") != "yes"
                               and (tags.get("foot") in PUBLIC or tags.get("access") in PUBLIC))
            if barrier in STRUCTURAL_BARRIERS and not is_allowed_gate:
                p = Point(self.projected[n])
                if study.is_empty or study.covers(p):
                    rows.append(dict(id=node_id(n), kind="BARRIER", geometry=p, gates=[], tags=tags))
        return rows, unlocated

    def ports(self, area, segments, entries, base):
        outer = self.outline(area)
        source_way_ids = defaultdict(set)
        ignored = defaultdict(set)
        for seg in segments:
            if seg.evidence not in ANCHOR_EVIDENCE:
                continue
            for end in (seg.a, seg.b):
                if end[0] not in outer:
                    continue
                ways = source_way_ids if end[1:] == ("0", "0") and ground(self.ways[seg.way].get("tags", {})) else ignored
                ways[end[0]].add(f"way/{seg.way}")
        ports = []
        entrances = {node_number(e["native_id"]): e for e in entries}
        for n, ways in sorted(source_way_ids.items()):
            ident = node_id(n)
            if n in entrances or (n, "0", "0") not in base:
                continue
            tags = self.nodes[n].get("tags", {})
            if restricted(tags) or not ground(tags):
                ignored[n].update(ways)
                continue
            ports.append(dict(id=ident, xy=self.projected[n], kind="NATIVE_CONTACT",
                              source_node_id=ident, source_way_ids=sorted(ways), tags=tags,
                              layer=tags.get("layer"), layer_compatible=True))
        for n, e in sorted(entrances.items()):
            xy = self.projected[n]
            point = Point(xy)
            shape = self.area(area)
            # Registered doors can lie strictly inside a pedestrian face, but a door
            # outside it has no unsupported gap connector. Never infer or move a door.
            if n not in outer and (shape is None or not shape.covers(point)):
                continue
            tags = self.nodes[n].get("tags", {})
            if restricted(tags):
                continue
            ports.append(dict(id=e["native_id"], xy=xy, kind="REGISTERED_ENTRANCE", source_node_id=e["native_id"],
                              source_way_ids=[], tags=tags, building_id=e["target_building_native_id"],
                              layer=tags.get("layer"), layer_compatible=ground(tags)))
        return ports, {node_id(n): sorted(ways) for n, ways in sorted(ignored.items())}


def grounded_lines(source, segments):
    return [(f"way/{s.way}/{s.index}", LineString([source.projected[s.a[0]], source.projected[s.b[0]]]))
            for s in segments if s.a[1:] == s.b[1:] == ("0", "0") and ground(source.ways[s.way].get("tags", {}))]
