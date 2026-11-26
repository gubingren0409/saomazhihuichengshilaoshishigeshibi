"""Independent readback of the offline map's embedded north and controlled layers."""
from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path
import re

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
XY = Transformer.from_crs(4326, 32651, always_xy=True).transform
STATE_LAYERS = {"NATIVE_WALKABLE":"state-native", "INFERRED_WALKABLE":"state-inferred",
                "RESTRICTED":"state-restricted", "UNKNOWN":"state-unknown"}
REGION_FILES = {
    "I-REGION": "north_regions.geojson",
    "I-REGION-ABL": "north_regions_I-REGION-ABL.geojson",
    "I-REGION-NET-ABL": "north_regions_I-REGION-NET-ABL.geojson",
}
MM_TOLERANCE = 0.0012


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def collection(path):
    return read(path)["features"]


def xy(geometry):
    return transform(XY,shape(geometry))


def cells_index(data, key):
    found = {key(item): item for item in data}
    if len(found) != len(data):
        raise ValueError("Duplicate displayed feature identity")
    return found


def drawn(feature, anchor):
    def point(text):
        x,y = map(float,text.split(","))
        return x+anchor[0], anchor[1]-y
    shapes = []
    for part in feature["shape"]:
        if "point" in part:
            x,y = part["point"]
            shapes.append(Point(x+anchor[0],anchor[1]-y))
            continue
        rings = [list(map(point,m.removesuffix("Z").split("L"))) for m in part["d"].split("M")[1:]]
        # Preserve individual SVG ring strokes. Unioning the rounded polygons
        # can merge nearby components and hide matching sub-millimeter strokes.
        shapes.extend(LineString(c) for c in rings)
    return unary_union(shapes)


def check_geometry(displayed, saved, anchor, geometry_is_area=False):
    raw = xy(saved["geometry"])
    draw = drawn(displayed,anchor)
    if geometry_is_area:
        raw = raw.boundary
    error = draw.hausdorff_distance(raw)
    if error > MM_TOLERANCE:
        raise ValueError(f"Displayed shape differs from source by {error:.7f} m: {displayed['props']}")
    return error


def audit(root, html):
    page = html.read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="payload">(.*?)</script>',page,re.S)
    if not match:
        raise ValueError("Offline map contains no inspectable result data")
    payload = json.loads(match.group(1))
    north = payload["north"]
    marker = next(p for p in north["points"] if p["props"]["role"] == "registered_exit")
    m = marker["props"]
    if (Point(m["wgs84"]).distance(Point(121.4706605,31.2305674)) > 1e-10 or
            m["tags"]["entrance"] != "exit"):
        raise ValueError("Displayed original exit identity changed")
    true_x,true_y = XY(*m["wgs84"])
    px,py = marker["shape"][0]["point"]
    anchor = north.get("anchor_xy", (true_x-px,true_y+py))
    if Point(true_x,true_y).distance(drawn(marker,anchor)) > MM_TOLERANCE:
        raise ValueError("Displayed exit marker does not match its raw coordinates")
    area_checks, max_error = {}, 0.
    for variant, path in REGION_FILES.items():
        key = lambda r: r["region_id"]
        display_variant = variant
        if variant == "I-REGION-NET-ABL" and variant not in north["regions"]:
            display_variant = "I-REGION"  # same frozen object; only graph is removed
        actual = cells_index(north["regions"][display_variant],lambda r:key(r["props"]))
        expected = cells_index(collection(root/"data"/path),lambda r:key(r["properties"]))
        if actual.keys() != expected.keys():
            raise ValueError(f"Displayed cells differ for {variant}")
        for ident,a in actual.items():
            ref = expected[ident]
            p = ref["properties"]
            displayed_props = dict(a["props"])
            if displayed_props.pop("variant",display_variant) != display_variant:
                raise ValueError("Incorrect display variant annotation")
            if displayed_props != p or a["layer"] != STATE_LAYERS[p["walkability_state"]]:
                raise ValueError("Displayed cell evidence or state differs from output")
            max_error = max(max_error,check_geometry(a,ref,anchor,True))
        area_checks[variant] = len(actual)
    key = lambda p: (p["variant"],p["query_id"],p["sequence"])
    actual = {key(f["props"]):f for rows in north["routes"].values() for f in rows
              if f["props"].get("role") == "route_segment"}
    expected = cells_index([f for f in collection(root/"data/north_routes.geojson") if f["properties"]["role"]=="route_segment"],
                           lambda f:key(f["properties"]))
    missing = [ident for ident in expected.keys()-actual.keys() if expected[ident]["properties"]["length_m"] > 1e-6]
    if missing or actual.keys()-expected.keys():
        raise ValueError(f"Unexpected missing/added map route rows: {missing[:8]}")
    for ident,f in actual.items():
        e = expected[ident]
        if f["props"] != e["properties"]:
            raise ValueError("Displayed route evidence differs from route GeoJSON")
        max_error = max(max_error,check_geometry(f,e,anchor))
    bench = payload.get("benchmark",{})
    bench_check = {"review_cases":len(bench),"reference_shapes":0}
    refs = root / "data/benchmark_review.geojson"
    if bench and refs.is_file():
        heldout = {"reference_area","reference_line","obstacle_reference"}
        layers = heldout | {"predicted_region"}
        def evidence_key(p):
            return p["task_id"],p["role"],p.get("walkability_state")
        source = cells_index([f for f in collection(refs) if f["properties"]["role"] in layers],
                             lambda f:evidence_key(f["properties"]))
        shown = {}
        for ident,b in bench.items():
            if any(x["props"].get("role") in layers for x in b["base"]):
                raise ValueError("Withheld or predicted area is visible in the observed-only panel")
            for x in b["right"]:
                p = x["props"]
                if p["role"] not in layers:
                    continue
                key = evidence_key(p)
                if key in shown or key not in source:
                    raise ValueError("Displayed controlled geometry key is repeated or unknown")
                ref = source[key]
                if ref["properties"] != p:
                    raise ValueError("Displayed controlled geometry attributes changed")
                is_area = ref["geometry"]["type"] in {"Polygon","MultiPolygon"}
                max_error = max(max_error,check_geometry(x,ref,b["anchor_xy"],is_area))
                shown[key] = x
        if shown.keys() != source.keys():
            raise ValueError("Displayed post-prediction reference or area census differs")
        bench_check.update(reference_shapes=sum(k[1] in heldout for k in shown),
                           predicted_area_shapes=sum(k[1]=="predicted_region" for k in shown),
                           observed_reference_shapes=0)
    return {"status":"INDEPENDENT_STATIC_DISPLAY_SOURCE_CHECK_PASS","actor":"/root/r3_s_audit",
            "html_sha256":sha(html),"area_fragments":area_checks,"nonempty_routes_drawn":len(actual),
            "zero_length_routes_not_drawn":len(expected)-len(actual),"benchmark":bench_check,
            "maximum_geometry_rounding_error_m":max_error,
            "scope":"Independent static HTML payload cross-check; browser UI separately tested by visual role"}


if __name__ == "__main__":
    p = ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--html",type=Path)
    p.add_argument("--output",type=Path,default=ROOT/"audits/display_independent.json")
    a = p.parse_args()
    result = audit(a.root,a.html or a.root/"visuals/index.html")
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,ensure_ascii=False)
        f.write("\n")
    print(result)
