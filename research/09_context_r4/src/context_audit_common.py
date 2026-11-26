"""Read-only spatial evidence utilities. Does not import or run the predictor."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json
import math
import re

from pyproj import Transformer
from shapely import union_all
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import polygonize

ROOT = Path(__file__).resolve().parents[1]
FORWARD = Transformer.from_crs(4326, 32651, always_xy=True).transform
SOURCE = re.compile(r"^(node|way|relation)/([0-9]+)")
SEGMENT = re.compile(r"^way/([0-9]+)/([0-9]+):(-?1)(?:$|/)")
STATES = ("NATIVE_WALKABLE", "INFERRED_WALKABLE", "RESTRICTED", "UNKNOWN")
AREA_TOL = 0.01
LENGTH_TOL = 0.0001
ALIGNMENT_TOL = 0.00001


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def error(message):
    raise ValueError(message)


def require(condition, message):
    if not condition:
        error(message)


def source_id(name):
    match = SOURCE.match(str(name))
    return f"{match[1]}/{match[2]}" if match else str(name)


def item_id(row):
    return source_id(row.get("source_id", row["id"]))


def line_pieces(value):
    if value.geom_type in {"LineString", "LinearRing"}:
        if value.length > LENGTH_TOL:
            yield value
    elif value.geom_type in {"GeometryCollection", "MultiLineString"}:
        for child in value.geoms:
            yield from line_pieces(child)


class RawClip:
    """Minimal independent reconstruction of named original geometries."""
    def __init__(self, path):
        self.path = path
        self.sha256 = hash_file(path)
        raw = read(path)
        self.objects = {f"{v['type']}/{v['id']}":v for v in raw["elements"]}
        self.xy = {
            v["id"]:FORWARD(v["lon"], v["lat"])
            for v in raw["elements"] if v["type"] == "node"
        }
        self._areas = {}

    def node(self, name):
        return self.xy[int(name.split("/")[1])]

    def line(self, name):
        way = self.objects[name]
        return LineString([self.xy[n] for n in way["nodes"]])

    def segment(self, name, index):
        way = self.objects[name]
        a, b = way["nodes"][index:index+2]
        return LineString((self.xy[a], self.xy[b]))

    def area(self, name):
        if name not in self._areas:
            obj = self.objects[name]
            if obj["type"] == "way":
                coords = [self.xy[n] for n in obj["nodes"]]
                result = Polygon(coords) if len(coords) >= 4 and coords[0] == coords[-1] else None
            else:
                rings = defaultdict(list)
                for member in obj.get("members", []):
                    if member["type"] == "way" and member.get("role","") in {"","outer","inner"}:
                        rings[member["role"] or "outer"].append(self.line(f"way/{member['ref']}"))
                result = union_all(list(polygonize(rings["outer"]))).difference(
                    union_all(list(polygonize(rings["inner"])))
                )
            self._areas[name] = result if result is not None and result.is_valid and not result.is_empty else None
        return self._areas[name]

    def replay_reference(self, reference):
        expected = shape(reference["geometry"])
        window = shape(reference["domain_geometry"])
        ids = reference["source_ids"]
        if reference["kind"].startswith("LINE_"):
            require(self.line(ids[0]).hausdorff_distance(expected) < ALIGNMENT_TOL,
                    f"Reference does not equal source centerline: {ids[0]}")
        else:
            faces = [self.area(ident) for ident in ids]
            require(all(g is not None for g in faces), f"Reference source has no valid area: {ids}")
            original = union_all(faces).intersection(window)
            require(original.symmetric_difference(expected).area < AREA_TOL,
                    f"Reference does not equal source footprint in evaluation domain: {ids}")
        return expected.intersection(window)


def source_way_segment(row):
    """Legacy H0 includes original IDs; normalized records have explicit provenance."""
    ident = item_id(row)
    match = SEGMENT.match(row["id"])
    ix = row.get("source_segment_index", row.get("segment_index"))
    sign = row.get("source_direction", row.get("direction"))
    if ix is None and match:
        ix = int(match[2])
    if sign is None and match:
        sign = int(match[3])
    return ident, int(ix) if ix is not None else None, int(sign) if sign is not None else None


def visible_lines(obs):
    nodes = {v["id"]:v for v in obs["nodes"]}
    for e in obs["edges"]:
        line = LineString([nodes[e["u"]]["xy"], nodes[e["v"]]["xy"]])
        yield e, line


def known_masks(obs):
    hard_polygons, hard_lines, grass = [], [], []
    for group, rows in obs["context"].items():
        for row in rows:
            g = shape(row["geometry"])
            tags = row.get("tags", {})
            restriction = any(tags.get(k) in {"no", "private", "restricted", "military"} for k in ("foot","access"))
            limited = tags.get("layer", tags.get("level")) not in {None, "", "0", 0}
            if group == "background" and row["kind"] in {"GRASS", "BACKGROUND_GRASS", "FLOWERBED", "MEADOW"}:
                grass.append((row["id"], g))
            elif group == "hard" or restriction or limited:
                (hard_polygons if g.area else hard_lines).append((row["id"],g))
    return hard_polygons, hard_lines, grass


def district_band(distance):
    return "0-40" if distance <= 40 + LENGTH_TOL else "40-80" if distance <= 80 + LENGTH_TOL else "80-160"


def write_relative(path, root=ROOT):
    return path.resolve().relative_to(root.resolve()).as_posix()
