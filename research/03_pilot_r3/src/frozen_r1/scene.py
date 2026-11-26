"""Freeze the shared requests before the first local or hosted route calculation."""
from hashlib import sha256
import json
import math
from pathlib import Path

from pyproj import Geod, Transformer
from shapely import LineString, Point, Polygon
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")
FORWARD = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
INVERSE = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
WORLD = 2 * math.pi * 6378137
WIDTH, HEIGHT = 1200, 900
DENY = {"no", "private", "customers", "permit"}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def distance(a, b):
    return GEOD.inv(*a, *b)[2]


def index(payload):
    nodes, ways, rels = {}, {}, {}
    tables = {"node": nodes, "way": ways, "relation": rels}
    for item in payload["elements"]:
        table = tables.get(item["type"])
        if table is not None:
            previous = table.get(item["id"])
            if previous is None or len(item.get("tags", {})) > len(previous.get("tags", {})):
                table[item["id"]] = item
    return nodes, ways, rels


def xy(node):
    return node["lon"], node["lat"]


def viewport(center, zoom):
    cx, cy = FORWARD(*center)
    scale = WORLD / (256 * 2**zoom)
    w, s, e, n = cx-WIDTH/2*scale, cy-HEIGHT/2*scale, cx+WIDTH/2*scale, cy+HEIGHT/2*scale
    west, south = INVERSE(w, s)
    east, north = INVERSE(e, n)
    meters = distance(INVERSE(w, cy), INVERSE(e, cy)) / WIDTH
    return {"center": list(center), "bounds": [west, south, east, north], "extent_3857": [w, s, e, n],
            "width": WIDTH, "height": HEIGHT, "bearing": 0, "pitch": 0, "zoom": zoom,
            "tile_css_size": 256, "dpr": 1, "meters_per_pixel": meters,
            "projected_units_per_pixel": scale, "crs": "EPSG:3857", "bounds_crs": "EPSG:4326"}


def freeze(snapshot, plan):
    choice = plan["scene"]
    nodes, ways, _ = index(snapshot)
    building = ways[int(choice["target_building"].split("/")[-1])]
    tags = building["tags"]
    names = "/".join(tags.get(k, "") for k in ("name", "name:en", "name:zh"))
    refs = building["nodes"]
    if tags.get("building") in (None, "no") or refs[0] != refs[-1] or not any(
            label in names for label in ("上海博物馆", "Shanghai Museum")):
        raise ValueError("FIXED_TARGET_BUILDING_IDENTITY_NOT_CONFIRMED")
    ring = [xy(nodes[i]) for i in refs]
    poly = Polygon([FORWARD(*p) for p in ring])
    if poly.is_empty or not poly.is_valid or poly.area <= 0:
        raise ValueError("FIXED_TARGET_GEOMETRY_INVALID")
    w, s, e, n = poly.bounds
    center_x, center_y = (w+e)/2, (s+n)/2
    center = INVERSE(center_x, center_y)
    guide = LineString([(center_x, s-1), (center_x, n+1)])
    facade = poly.boundary.intersection(guide)
    facade_point = min((g for g in facade.geoms if g.geom_type == "Point"), key=lambda g: g.y, default=None) if hasattr(facade, "geoms") else facade
    if facade_point is None or facade_point.geom_type != "Point":
        raise ValueError("SOUTH_FACADE_TARGET_UNRESOLVED")
    entrances = []
    for i in set(refs):
        node = nodes[i]
        tag = node.get("tags", {})
        x, y = FORWARD(*xy(node))
        if (y <= s+(n-s)/3 and tag.get("entrance") in {"yes", "main", "entrance", "public"}
                and tag.get("access") not in DENY and tag.get("foot") not in DENY):
            entrances.append((Point(x, y).distance(facade_point), i))
    if entrances:
        entrance_id = min(entrances)[1]
        target = xy(nodes[entrance_id])
        role = "OSM_TAGGED_BUILDING_ENTRANCE_REFERENCE"
    else:
        entrance_id = None
        target = INVERSE(facade_point.x, facade_point.y)
        role = "SOUTH_FACADE_DIAGNOSTIC_POINT"
    path_nodes = set()
    for way in ways.values():
        tag = way.get("tags", {})
        if (tag.get("highway") in {"footway", "pedestrian", "path", "steps", "living_street"}
                and tag.get("area") != "yes" and tag.get("indoor") != "yes"
                and tag.get("access") not in DENY and tag.get("foot") not in DENY
                and tag.get("level") in (None, "0") and tag.get("layer") in (None, "0")):
            path_nodes.update(way["nodes"])
    options = []
    for i in path_nodes:
        node = nodes.get(i)
        if not node:
            continue
        lon, lat = xy(node)
        if lon < center[0] and 240 <= distance((lon, lat), center) <= 440:
            options.append((distance((lon, lat), choice["nominal_start"]), i))
    if not options:
        raise ValueError("NO_RULE_ELIGIBLE_MAP_QUERY_START")
    start_id = min(options)[1]
    views = {kind: viewport(center, zoom) for kind, zoom in (("detail", 18), ("context", 16))}
    return {
        "scene_id": choice["scene_id"].lower(), "label": choice["label"], "role": choice["role"], "use": choice["use"],
        "building_native_id": choice["target_building"], "building_name_evidence": names,
        "building_footprint": mapping(Polygon(ring)), "institution_source": choice["institution_source"],
        "start": list(xy(nodes[start_id])), "start_native_id": f"node/{start_id}",
        "start_role": "DECLARED_MAP_QUERY_ORIGIN", "target": list(target), "target_role": role,
        "entry_native_id": f"node/{entrance_id}" if entrance_id else None,
        "entry_scope": "Building entrance map reference; on-site state unverified" if entrance_id else
                       "Official institution specifies south side; physical door coordinate unverified",
        "poi_search_location": None, "poi_search_status": "NOT_REQUESTED_FIXED_GEOMETRY",
        "access_reference_status": "SOURCE_REFERENCE_ONLY", "endpoint_rule": choice["target_selection"],
        "path_snap_max_m": choice["path_snap_max_m"], "frozen_before_route": True, "views": views,
    }


if __name__ == "__main__":
    plan = json.loads((ROOT / "runs/pilot_plan.json").read_text(encoding="utf-8"))
    clip = ROOT / "data/sh-huangpu-01.osm.json"
    result = freeze(json.loads(clip.read_text(encoding="utf-8")), plan)
    result["snapshot_sha256"] = sha256(clip.read_bytes()).hexdigest()
    path = ROOT / "runs/scene_contract.json"
    if path.exists():
        raise SystemExit("FROZEN_SCENE_ALREADY_EXISTS")
    dump(path, result)
    print(json.dumps({k:v for k,v in result.items() if k != "building_footprint"}, ensure_ascii=True))
