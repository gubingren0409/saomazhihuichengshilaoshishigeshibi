"""Build the offline R4 review from frozen native clips and machine geometry."""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
CRS = "EPSG:32651"
TO_LOCAL = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
WIDTH, HEIGHT = 1000, 630
EDGE_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
VARIANTS = ("B0", "B1", "B2", "B3")
OSM_WALK = {"footway", "path", "pedestrian", "steps", "living_street", "corridor"}
FENCE = {"fence", "wall", "hedge", "guard_rail", "retaining_wall", "chain"}
EXTRA_KINDS = {
    "open_space": "plaza", "boundary_candidate": "candidate", "edge_added": "added",
    "access_candidate": "contact", "b0_network": "network", "network": "network",
    "edge_evidence": "rejected", "obstacle": "obstacle",
    "route": "route", "entry": "entry", "origin": "origin", "route_end": "end",
}
SOURCE_PREVIEW = {
    "building": "周边建筑原生轮廓", "grass": "草地、绿地或花坛源图层",
    "water": "水体源图层", "fence": "原生围栏或墙体",
    "walk": "带步行属性的原生线。步行图接纳状态另看 B0 图层。",
    "crossing": "带过街标签的原生要素，当前安全性未核实。",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def make_feature(layer, geometry, **props):
    return (layer, geometry, props)


def observed_osm(document, focus_bounds):
    """Retain actual OSM objects for context without expanding the route graph."""
    rows = document["elements"]
    nodes = {r["id"]: (r["lon"], r["lat"]) for r in rows if r["type"] == "node"}
    features = []
    for row in rows:
        tags = row.get("tags", {})
        native_id = f"{row['type']}/{row['id']}"
        if row["type"] == "node" and tags.get("highway") == "crossing":
            p = Point(nodes[row["id"]])
            if focus_bounds.intersects(p):
                features.append(make_feature("crossing", transform(TO_LOCAL, p),
                                             native_ids=[native_id], tags=tags, evidence="OBSERVED",
                                             reason=SOURCE_PREVIEW["crossing"]))
        if row["type"] != "way":
            continue
        if not tags or len(row["nodes"]) < 2 or any(n not in nodes for n in row["nodes"]):
            continue
        coords = [nodes[n] for n in row["nodes"]]
        line = LineString(coords)
        if not line.intersects(focus_bounds):
            continue
        layers = {}
        if tags.get("barrier") in FENCE:
            layers["fence"] = line
        if tags.get("footway") == "crossing" or tags.get("highway") == "crossing":
            layers["crossing"] = line
        if (tags.get("highway") in OSM_WALK or tags.get("foot") in {"yes", "designated", "permissive"}) and tags.get("area") != "yes":
            layers["walk"] = line
        if len(coords) >= 4 and line.is_ring:
            polygon = Polygon(coords)
            if polygon.is_valid:
                if tags.get("building") not in {None, "no"}:
                    layers["building"] = polygon
                if (tags.get("landuse") in {"grass", "meadow"} or tags.get("natural") == "grassland"
                        or tags.get("leisure") == "garden" or tags.get("landcover") == "grass"
                        or tags.get("landuse") == "flowerbed"):
                    layers["grass"] = polygon
                if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
                    layers["water"] = polygon
        for layer, geom in layers.items():
            features.append(make_feature(layer, transform(TO_LOCAL, geom), native_ids=[native_id],
                                         tags=tags, evidence="OBSERVED", reason=SOURCE_PREVIEW[layer]))
    return features


def observed_output(doc):
    for f in doc["features"]:
        p = f["properties"]
        layer = EXTRA_KINDS.get(p.get("kind"))
        if layer == "rejected" and p.get("status") == "ALREADY_IN_B0":
            layer = "baseline_evidence"
        if layer and f.get("geometry"):
            geom = shape(f["geometry"])
            if not geom.is_empty:
                props = {**p, **({"wgs84": list(geom.coords[0])} if geom.geom_type == "Point" else {})}
                yield make_feature(layer, transform(TO_LOCAL, geom), **props)
                if layer == "added" and geom.geom_type == "LineString":
                    for ident, coord in zip(p["native_ids"][-2:], (geom.coords[0], geom.coords[-1])):
                        yield make_feature("added_node", transform(TO_LOCAL, Point(coord)), **{
                            **p, "native_ids": [ident], "wgs84": list(coord), "reason": "已接纳边的原生端点。"
                        })


def compose_bounds(boxes, padding, min_width):
    x0 = min(b[0] for b in boxes) - padding
    x1 = max(b[2] for b in boxes) + padding
    y0 = min(b[1] for b in boxes) - padding
    y1 = max(b[3] for b in boxes) + padding
    width = max(min_width, x1 - x0, (y1 - y0) * WIDTH / HEIGHT)
    height = width * HEIGHT / WIDTH
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return box(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def expanded_bounds(geom, amount):
    x0, y0, x1, y1 = geom.bounds
    return box(x0 - amount, y0 - amount, x1 + amount, y1 + amount)


def geometry_commands(geometry, bounds):
    """Encode clipped native points, lines and rings in the shared metric viewport."""
    if geometry.is_empty:
        return []
    x0, y0, x1, y1 = bounds
    scale = WIDTH / (x1 - x0)

    def xy(coord):
        return round((coord[0] - x0) * scale, 1), round((y1 - coord[1]) * scale, 1)

    def line(coords, closed=False):
        positions = "L".join(f"{x},{y}" for x, y in map(xy, coords))
        return "M" + positions + ("Z" if closed else "")

    if geometry.geom_type == "Point":
        return [{"point": xy(geometry.coords[0])}]
    if geometry.geom_type == "LineString":
        return [{"d": line(geometry.coords)}]
    if geometry.geom_type == "Polygon":
        rings = (geometry.exterior, *geometry.interiors)
        return [{"d": "".join(line(r.coords, True) for r in rings), "area": True}]
    return [command for geom in getattr(geometry, "geoms", []) for command in geometry_commands(geom, bounds)]


def map_view(features, bounds):
    projected = []
    for layer, geom, props in features:
        if not geom.intersects(bounds):
            continue
        commands = geometry_commands(geom.intersection(bounds), bounds.bounds)
        if commands:
            projected.append({"layer": layer, "geometry": commands, "properties": props})
    width_m = bounds.bounds[2] - bounds.bounds[0]
    scale_bar_m = next(n for n in [250, 200, 100, 50, 25, 10] if n <= width_m / 4)
    return {
        "features": projected, "bbox_local": bounds.bounds, "meters_per_pixel": width_m / WIDTH,
        "scale_bar_m": scale_bar_m, "layer_counts": dict(Counter(x["layer"] for x in projected)),
    }


def has_entry(features, native_id):
    return any(layer == "entry" and native_id in (props.get("native_ids") or []) for layer, _, props in features)


def build_scene(root, scene, result):
    scene_id = scene["scene_id"]
    geojson = root / f"runs/geometry/{scene_id}.geojson"
    geo_doc = read_json(geojson)
    features = list(observed_output(geo_doc))
    building = transform(TO_LOCAL, shape(scene["building_footprint"]))
    features.append(make_feature("target_building", building, native_ids=[scene["building_native_id"]],
                                 tags=scene.get("building_tags", {}), status="FROZEN_BUILDING",
                                 evidence="OBSERVED", reason="冻结目标建筑轮廓。"))
    origin = transform(TO_LOCAL, Point(scene["start"]))
    if not any(layer == "origin" for layer, _, _ in features):
        features.append(make_feature("origin", origin, native_ids=[scene["start_native_id"]],
                                     evidence="OBSERVED", reason="冻结请求起点。"))
    for entry in scene.get("r4_entrances", []):
        if not has_entry(features, entry["native_id"]):
            features.append(make_feature("entry", transform(TO_LOCAL, Point(entry["coordinate"])),
                                         native_ids=[entry["native_id"]], status="ELIGIBLE" if entry["eligible"] else "EXCLUDED",
                                         **{k: v for k, v in entry.items() if k not in {"native_id"}}))
    if not scene.get("r4_entrances") and scene.get("target"):
        features.append(make_feature("proxy", transform(TO_LOCAL, Point(scene["target"])),
                                     status="PROXY_OR_UNCERTAIN", evidence="OBSERVED",
                                     reason="原冻结代理请求点。仅展示局部路网诊断。"))

    # The initial camera emphasizes the audited boundary. The context camera includes actual routes.
    focus_shapes = [g for layer, g, _ in features if layer in {"target_building", "plaza", "entry", "proxy"}]
    detail = compose_bounds([g.bounds for g in focus_shapes], 42, 360)
    context_shapes = [detail, origin] + [g for layer, g, _ in features if layer == "route"]
    context = compose_bounds([g.bounds for g in context_shapes], 48, 560)
    x0, y0, x1, y1 = expanded_bounds(context, 1).bounds
    inverse = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    geographic = box(*inverse.transform_bounds(x0, y0, x1, y1))
    clip = root / scene["osm_clip"]
    features = observed_osm(read_json(clip), geographic) + features
    variant_summary = result["variants"]
    return {
        "id": scene_id, "label": scene["label"], "category": scene.get("category", scene.get("use")),
        "native_building_id": scene["building_native_id"], "focus_space_ids": scene.get("r4_focus_space_ids", []),
        "entrances": scene.get("r4_entrances", []), "start": scene["start"],
        "source_clip": scene["osm_clip"], "machine_geometry": geojson.relative_to(root).as_posix(),
        "machine_geometry_sha256": sha256(geojson.read_bytes()).hexdigest(),
        "variants": {v: without_geometry(variant_summary.get(v, {})) for v in VARIANTS},
        "extra": without_geometry({k: v for k, v in result.items() if k != "variants"}),
        "maps": {"detail": map_view(features, detail), "context": map_view(features, context)},
    }


def without_geometry(value):
    """Leave detailed metric evidence in place while the preprojected views own geometry."""
    if isinstance(value, list):
        return [without_geometry(row) for row in value]
    if isinstance(value, dict):
        return {k: without_geometry(v) for k, v in value.items()
                if k not in {"geometry", "coordinates", "native_geometry"}}
    return value


def write_payload(root):
    contracts = read_json(root / "runs/source_scene_contracts.json")
    experiment = read_json(root / "runs/experiment.json")
    results = {item["scene_id"]: item for item in experiment["scenes"]}
    scenes = [build_scene(root, scene, results[scene["scene_id"]]) for scene in contracts["scenes"]]
    assert {s["id"] for s in scenes} == set(results)
    payload = {"crs": CRS, "width": WIDTH, "height": HEIGHT, "scenes": scenes}
    out = root / "visuals"
    out.mkdir(exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    (out / "scene_data.js").write_text("window.R4_DATA=" + text + ";\n", encoding="utf-8")
    return {
        "scenes": len(scenes), "projection": CRS, "data_bytes": (out / "scene_data.js").stat().st_size,
        "feature_counts": {s["id"]: {v: m["layer_counts"] for v, m in s["maps"].items()} for s in scenes},
    }


def browser_review(root, static):
    from playwright.sync_api import sync_playwright

    out = root / "visuals"
    urls, errors = [], []
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=str(EDGE_PATH) if EDGE_PATH.is_file() else None,
                                         headless=True, args=["--disable-background-networking", "--no-first-run"])
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
        page.route("http://**/*", lambda route: (urls.append("HTTP"), route.abort()))
        page.route("https://**/*", lambda route: (urls.append("HTTPS"), route.abort()))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((out / "index.html").as_uri(), wait_until="load")
        page.wait_for_selector("#map svg [data-feature]")
        checks = page.evaluate("""() => {
          const values = {};
          for (const scene of R4_DATA.scenes) {
            values[scene.id] = {};
            for (const v of ['B0', 'B1', 'B2', 'B3']) {
              R4_REVIEW.select(scene.id, v, 'detail');
              values[scene.id][v] = Number(document.querySelectorAll('#map svg [data-feature]').length);
            }
          }
          return values;
        }""")
        assert len(checks) == 6 and all(all(k > 0 for k in v.values()) for v in checks.values())
        page.evaluate("() => R4_REVIEW.select('sh-huangpu-01', 'B1', 'detail')")
        assert page.locator("#route-table tbody tr").count() > 0
        selected = page.locator("#map svg [data-layer='contact'] [data-feature]").first
        if selected.count() == 0:
            selected = page.locator("#map svg [data-layer='entry'] [data-feature]").first
        selected.focus()
        selected.press("Enter")
        assert page.locator("#inspector table tr").count() > 1
        before = page.locator("#map svg [data-layer='building'] [data-feature]").count()
        page.locator("#layer-building").uncheck()
        after = page.locator("#map svg [data-layer='building'] [data-feature]").count()
        assert before > 0 and after == 0
        page.locator("#layer-building").check()
        with page.expect_download() as downloaded:
            page.locator("#export").click()
        export = downloaded.value.path().read_text(encoding="utf-8")
        assert "<svg" in export and "sh-huangpu-01" in export and "OpenStreetMap" in export
        page.locator("#scene").select_option("sh-newworld")
        page.locator('input[name="variant"][value="B2"]+span').click()
        page.locator("#layer-walk").uncheck()
        assert page.locator("#map svg[data-scene=sh-newworld][data-variant=B2]").count() == 1
        assert page.locator("#map [data-layer=rejected] [data-status=REJECTED]").count() > 0
        assert page.locator("#map [data-layer=baseline_evidence] [data-status=ALREADY_IN_B0]").count() > 0
        with page.expect_download() as changed:
            page.locator("#export").click()
        import xml.etree.ElementTree as ET
        changed_svg = ET.parse(changed.value.path()).getroot()
        assert changed_svg.get("data-scene") == "sh-newworld" and changed_svg.get("data-variant") == "B2"
        assert not any(e.get("data-layer") == "walk" for e in changed_svg.iter())
        page.locator("#layer-walk").check()
        if static:
            fig_dir = out / "figures"
            fig_dir.mkdir(exist_ok=True)
            requests = [
                ("01_museum_overview.svg", "sh-huangpu-01", "B0", "detail", "default"),
                ("02_museum_boundary.svg", "sh-huangpu-01", "B1", "detail", "topology"),
                ("03_museum_internal.svg", "sh-huangpu-01", "B2", "detail", "topology"),
                ("04_museum_entrances.svg", "sh-huangpu-01", "B3", "detail", "default"),
                ("05_museum_route_comparison.svg", "sh-huangpu-01", "B3", "context", "routes"),
                ("06_library_topology.svg", "sh-library", "B2", "detail", "topology"),
                ("07_failed_boundary.svg", "sh-huangpu-01", "B1", "detail", "failure"),
                ("11_newworld_layer_refusal.svg", "sh-newworld", "B2", "detail", "conflict"),
            ]
            for name, scene, variant, view, preset in requests:
                svg = page.evaluate("(args) => R4_REVIEW.staticSVG(...args)", [scene, variant, view, preset])
                (fig_dir / name).write_text(svg, encoding="utf-8")
            for name, method in (("08_cross_scene.svg", "matrixSVG"), ("09_connectivity_and_lengths.svg", "resultsSVG")):
                svg = page.evaluate("name => R4_REVIEW[name]()", method)
                (fig_dir / name).write_text(svg, encoding="utf-8")
            page.evaluate("() => R4_REVIEW.select('sh-huangpu-01', 'B1', 'detail')")
            page.locator(".workbench").screenshot(path=str(fig_dir / "10_interactive_preview.png"))
        assert not urls and not errors, (urls, errors)
        browser.close()
    return {"status": "PASS", "scenes_and_variants": checks, "external_requests": len(urls),
            "svg_download": "PASS_MUSEUM_B1_AND_NEW_WORLD_B2", "layer_toggle": "PASS",
            "source_evidence_status_layers": "PASS_BASELINE_PRESENT_AND_REJECTED_SEPARATE",
            "keyboard_feature_inspection": "PASS",
            "browser": "Microsoft Edge" if EDGE_PATH.is_file() else "Chromium",
            "identity": "AUTHOR_BROWSER_TECHNICAL_QA_NO_HUMAN_OR_FIELD_CHECK"}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--render", action="store_true", help="Open page in local Edge and save review figures")
    parser.add_argument("--browser-only", action="store_true", help="Check the fixed offline viewer without rebuilding")
    args = parser.parse_args()
    root = args.root.resolve()
    result = {} if args.browser_only else {"payload": write_payload(root)}
    if args.render or args.browser_only:
        result["browser"] = browser_review(root, static=args.render)
        if not args.browser_only:
            (root / "audits").mkdir(exist_ok=True)
            (root / "audits/visual_browser_qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
