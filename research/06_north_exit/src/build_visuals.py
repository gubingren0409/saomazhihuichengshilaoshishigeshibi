"""Build a standalone review from frozen map vectors and actual N0/N1/N2 outputs."""
import argparse
import csv
import json
from hashlib import file_digest
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
SCENE_ID = "sh-huangpu-01"
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform
DRAWN_LAYERS = {"grass", "water", "road", "building", "target", "walk", "fence", "gate",
                "crossing", "road_label", "building_label"}
COLORS = {"N0": "原始网络", "N1": "直线假设", "N2": "受约束假设"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def path_data(points, closed=False):
    return "M" + "L".join(f"{x:.4f},{y:.4f}" for x, y in points) + ("Z" if closed else "")


def parts(geometry, position):
    """Project the actual GeoJSON geometry and preserve interior rings."""
    kind, coords = geometry["type"], geometry.get("coordinates")
    if kind == "Point":
        return [{"point": position(coords)}]
    if kind == "MultiPoint":
        return [{"point": position(p)} for p in coords]
    if kind == "LineString":
        return [{"d": path_data(map(position, coords))}]
    if kind == "MultiLineString":
        return [{"d": path_data(map(position, line))} for line in coords]
    if kind == "Polygon":
        return [{"d": "".join(path_data(map(position, ring), True) for ring in coords), "area": True}]
    if kind == "MultiPolygon":
        return [{"d": "".join(path_data(map(position, ring), True) for ring in poly), "area": True}
                for poly in coords]
    if kind == "GeometryCollection":
        return [part for member in geometry["geometries"] for part in parts(member, position)]
    raise ValueError(f"Unexpected GeoJSON geometry {kind}")


def extent(points, padding, min_width):
    xs, ys = zip(*points)
    width = max(max(xs)-min(xs)+padding, (max(ys)-min(ys)+padding)*1.32, min_width)
    height = width / 1.32
    return [(min(xs)+max(xs)-width)/2, (min(ys)+max(ys)-height)/2, width, height]


def build(inputs, run, output):
    clip = inputs / "frozen_r4/data/source/sh-huangpu-01.osm.json"
    basemap = inputs / "visuals/scene_data.js"
    raw = read(clip)["elements"]
    nodes = {obj["id"]: (obj["lon"], obj["lat"]) for obj in raw if obj["type"] == "node"}
    objects = {f"{obj['type']}/{obj['id']}": obj for obj in raw}
    js = basemap.read_text(encoding="utf-8")
    old = json.JSONDecoder().raw_decode(js[js.index("{"):])[0]
    scene = next(row for row in old["scenes"] if row["id"] == SCENE_ID)
    if scene["source_sha256"] != sha(clip):
        raise ValueError("Frozen backdrop does not reference this raw OSM clip")
    bld = objects[scene["building_id"]]
    centroid = Polygon([PROJECT(*nodes[n]) for n in bld["nodes"]]).centroid

    def position(point):
        x, y = PROJECT(*point)
        return [x-centroid.x, centroid.y-y]

    route_file = run / "data/route_variants.geojson"
    constraint_file = run / "data/constraints.geojson"
    result = read(run / "runs/experiment.json")
    routes = read(route_file)["features"]
    constraints = read(constraint_file)["features"]
    features = [row for row in scene["features"] if row["layer"] in DRAWN_LAYERS]
    for row in features:
        native_id = row["props"].get("native_id")
        if native_id in objects:
            row["props"].setdefault("tags", objects[native_id].get("tags", {}))

    roles = {"N2_corridor": "corridor", "N2_search_strip": "search_strip", "park": "park",
             "pedestrian_area": "plaza", "building": "target", "obstacle": "obstacle",
             "gap": "gap", "level": "grade"}
    for item in constraints:
        props = item["properties"]
        role = props["role"]
        if role not in roles or not item.get("geometry"):
            continue
        native_id = props.get("source_id") or props.get("native_id")
        meta = dict(props)
        if native_id in objects:
            meta.update(native_id=native_id)
            meta.setdefault("tags", objects[native_id].get("tags", {}))
        features.append({"layer": roles[role], "shape": parts(item["geometry"], position), "props": meta})
    # The raw building polygon in the constraints layer and the frozen target describe one object.
    if any(item["properties"].get("role") == "building" for item in constraints):
        features = [row for row in features if row["layer"] != "target" or row["props"].get("role") == "building"]

    level_rows = table(run / "data/level_evidence.csv")
    for row in level_rows:
        native_id = row["source_id"]
        if row["variant"] != "N2" or row["section"] != "CANDIDATE" or row["level_status"] != "EXPLICIT_TAGS":
            continue
        raw_node = objects.get(native_id)
        if raw_node and raw_node["type"] == "node":
            tags = json.loads(row["tags"])
            features.append({
                "layer": "grade_point",
                "shape": [{"point": position(nodes[raw_node["id"]])}],
                "props": {"native_id": native_id, "tags": raw_node["tags"],
                          "label": " / ".join(f"{k}={v}" for k, v in tags.items()) + " · 邻近",
                          "level_status": row["relation"] + " · " + row["distance_m"] + " m"},
            })

    drawn_routes = []
    for item in routes:
        props = item["properties"]
        role = props["role"]
        if role not in {"native_approach", "connector", "approach_point", "exit", "route"}:
            continue
        if role == "route":
            # The route is assembled from the separately styled native and hypothesis sections.
            continue
        drawn_routes.append({"layer": role, "shape": parts(item["geometry"], position), "props": props})
    frozen = next((r for r in routes if r["properties"].get("variant") == "N0"
                   and r["properties"].get("role") == "native_approach"), None)
    if frozen is None:
        frozen = next(r for r in routes if r["properties"]["role"] == "native_approach")
    if frozen["geometry"]["type"] != "LineString":
        raise ValueError("Expected a single connected frozen approach geometry")
    prefix = frozen["geometry"]["coordinates"]
    door_coord = nodes[6897145227]
    route_exit = next(r["geometry"]["coordinates"] for r in routes if r["properties"]["role"] == "exit")
    if tuple(route_exit) != door_coord:
        raise ValueError("Map terminal does not match the original exit coordinate")
    start, snap, door = (position(p) for p in (prefix[0], prefix[-1], door_coord))
    payload = {
        "features": features, "route_features": drawn_routes, "variants": result["variants"],
        "sensitivities": result["sensitivity"], "case_labels": COLORS,
        "source_geometry": result["source_geometry"], "comparison": result["comparison"],
        "viewboxes": {"near": extent([snap, door], 30, 45), "full": extent([position(p) for p in prefix]+[door], 65, 90)},
        "points": {"start": start, "snap": snap, "exit": door},
        "exit_coord": door_coord,
        "evidence": {
            "segments": table(run / "data/segment_evidence.csv"),
            "obstacles": table(run / "data/obstacle_intersections.csv"),
            "levels": level_rows,
        },
        "sha256": {"map": sha(basemap), "clip": sha(clip), "route": sha(route_file),
                   "constraints": sha(constraint_file)},
    }
    template = Path(__file__).with_name("north_access_map.html").read_text(encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # Raw text in a script tag must never contain an HTML closing tag.
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    output.parent.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name("north_access_map.js").read_text(encoding="utf-8")
    page = template.replace("__NORTH_ACCESS_PAYLOAD__", encoded).replace("__NORTH_ACCESS_SCRIPT__", script)
    output.write_text(page, encoding="utf-8")
    print(json.dumps({"output": str(output), "base_features": len(features),
                      "route_features": len(drawn_routes), "route_sha256": payload["sha256"]["route"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=ROOT / "inputs/source")
    parser.add_argument("--run-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "visuals/index.html")
    options = parser.parse_args()
    build(options.input_root.resolve(), options.run_root.resolve(), options.output.resolve())
