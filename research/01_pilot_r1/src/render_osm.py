"""North-up local OSM map rendering at a fixed Web Mercator viewport."""
from collections import Counter
from functools import lru_cache
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely import LineString, Point, Polygon, box, make_valid
from shapely.ops import polygonize, unary_union

from .scene import FORWARD, HEIGHT, WIDTH, index, xy

LAND = {"park", "garden", "grass", "recreation_ground", "forest", "wood", "village_green",
        "meadow", "grassland", "cemetery", "scrub", "pitch", "playground"}
FOOT = {"footway", "path", "pedestrian", "steps", "living_street", "bridleway"}
ROAD = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "track"}
PALETTE = {"land": "#dce8cc", "water": "#b6d7e3", "building": "#d9c6b7",
           "pedestrian_area": "#ede5d5"}
ROAD_W = {"motorway": 17, "trunk": 16, "primary": 14, "secondary": 12, "tertiary": 10,
          "residential": 8, "unclassified": 7, "service": 5, "track": 4}
INK = "#263949"


def role(tags):
    if tags.get("building") not in (None, "no"):
        return "building"
    if tags.get("natural") in {"water", "wetland", "bay"} or tags.get("waterway") == "riverbank" or "water" in tags:
        return "water"
    if any(tags.get(k) in LAND for k in ("leisure", "landuse", "natural")):
        return "land"
    if tags.get("highway") == "pedestrian" and tags.get("area") == "yes":
        return "pedestrian_area"
    if tags.get("highway") in FOOT:
        return "foot"
    if tags.get("highway", "").removesuffix("_link") in ROAD:
        return "road"
    if tags.get("waterway") in {"river", "stream", "canal", "ditch", "drain"}:
        return "stream"
    return None


def pieces(geom, accepted):
    if geom.is_empty:
        return
    if geom.geom_type == accepted:
        yield geom
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield from pieces(part, accepted)


def prepare(snapshot):
    nodes, ways, rels = index(snapshot)
    projected = {key: FORWARD(*xy(value)) for key, value in nodes.items()}
    lines = {key: LineString([projected[i] for i in value["nodes"]]) for key, value in ways.items()
             if len(value["nodes"]) >= 2 and all(i in projected for i in value["nodes"])}
    features, points, incorporated = [], [], set()
    unmatched_relations = 0
    for key, rel in rels.items():
        tags = rel.get("tags", {})
        kind = role(tags)
        if kind not in PALETTE:
            continue
        members = rel["members"]
        if any(m["ref"] not in lines or m["role"] not in {"outer", "inner", ""} for m in members):
            unmatched_relations += 1
            continue
        outer = list(polygonize(unary_union([lines[m["ref"]] for m in members if m["role"] != "inner"])))
        if not outer:
            unmatched_relations += 1
            continue
        inner = list(polygonize(unary_union([lines[m["ref"]] for m in members if m["role"] == "inner"])))
        geometry = unary_union(outer).difference(unary_union(inner))
        features.append((kind, tags, geometry, f"relation/{key}"))
        incorporated.update((kind, m["ref"]) for m in members)
    for key, way in ways.items():
        tags = way.get("tags", {})
        kind, line = role(tags), lines.get(key)
        if not kind or line is None or (kind, key) in incorporated:
            continue
        if kind in PALETTE:
            if not line.is_closed or len(line.coords) < 4:
                continue
            geom = make_valid(Polygon(line.coords))
        else:
            geom = line
        if not geom.is_empty:
            features.append((kind, tags, geom, f"way/{key}"))
    for key, node in nodes.items():
        tags = node.get("tags", {})
        label = tags.get("name:zh") or tags.get("name") or tags.get("name:en")
        if label and (set(tags) & {"amenity", "tourism", "public_transport", "leisure", "railway", "shop"}):
            points.append((Point(projected[key]), label, key))
    return features, points, unmatched_relations


@lru_cache(maxsize=16)
def font(size):
    for path in (Path("C:/Windows/Fonts/msyh.ttc"),
                 Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def pixel(x, y, view):
    w, s, e, n = view["extent_3857"]
    return (x-w)/(e-w)*WIDTH, (n-y)/(n-s)*HEIGHT


def polygon(draw, poly, view, color, outline, cutout):
    draw.polygon([pixel(x,y,view) for x,y in poly.exterior.coords], fill=color, outline=outline, width=1)
    for hole in poly.interiors:
        draw.polygon([pixel(x,y,view) for x,y in hole.coords], fill=cutout, outline=outline, width=1)


def caption(draw, text, where, size, *, anchor="lt", fill=INK, halo=2):
    draw.text(where, text, anchor=anchor, font=font(size), fill=fill,
              stroke_width=halo, stroke_fill="#faf9f4")


def frame(draw, view):
    target = 100 if view["zoom"] == 18 else 250
    scale_px = target / view["meters_per_pixel"]
    x, y = 27, HEIGHT-31
    draw.rounded_rectangle((15, HEIGHT-65, x+scale_px+20, HEIGHT-13), 7, fill="#faf9f4", outline="#e2ded2")
    draw.line((x, y, x+scale_px, y), fill=INK, width=3)
    for ex in (x, x+scale_px):
        draw.line((ex, y-5, ex, y+5), fill=INK, width=2)
    caption(draw, f"{target} m", (x+scale_px/2, y-11), 15, anchor="ms", halo=0)
    draw.rounded_rectangle((WIDTH-65, 15, WIDTH-15, 87), 7, fill="#faf9f4", outline="#e2ded2")
    caption(draw, "N", (WIDTH-40, 26), 16, anchor="mt", halo=0)
    draw.polygon([(WIDTH-40,46),(WIDTH-49,72),(WIDTH-40,66),(WIDTH-31,72)], fill=INK)
    credits = "© OpenStreetMap contributors  ·  ODbL"
    left = WIDTH-26-draw.textlength(credits,font=font(15))
    draw.rounded_rectangle((left-10, HEIGHT-52, WIDTH-15, HEIGHT-15),7,fill="#faf9f4",outline="#e2ded2")
    caption(draw, credits, (WIDTH-25, HEIGHT-32),15, anchor="rm", halo=0)
    return {"visible": True, "bar_meters": target, "bar_css_pixels": scale_px}


def base_map(features, points, scene, view):
    clip = box(*view["extent_3857"])
    im = Image.new("RGB", (WIDTH, HEIGHT), "#f6f3eb")
    draw = ImageDraw.Draw(im)
    counts, widths, labels, skipped = Counter(), {}, [], 0
    grouped = {kind: [] for kind in (*PALETTE, "road", "foot", "stream")}
    for kind, tags, geom, ref in features:
        if clip.intersects(geom):
            clipped = geom.intersection(clip)
            if clipped.is_empty:
                continue
            grouped[kind].append((tags, clipped, ref))
    for kind in ("land","water","pedestrian_area","stream","road","building","foot"):
        ordered = sorted(grouped[kind], key=lambda v: (v[1].area, v[2]), reverse=True) if kind in PALETTE else grouped[kind]
        for tags, shape, ref in ordered:
            if kind in PALETTE:
                parts = list(pieces(shape, "Polygon"))
                if not parts:
                    continue
                for part in parts:
                    polygon(draw, part, view, PALETTE[kind], "#b4a297" if kind=="building" else PALETTE[kind], "#f6f3eb")
                label_point = max(parts, key=lambda a:a.area).representative_point()
                width = None
            else:
                parts = list(pieces(shape, "LineString"))
                if not parts:
                    continue
                detail = view["zoom"]==18
                klass = tags.get("highway","").removesuffix("_link")
                if kind == "road":
                    width=max(2, round(ROAD_W.get(klass,5) * (1 if detail else .63)))
                    color="#fffdf9" if klass in {"residential","unclassified","service","track"} else "#fff8de"
                    stroke="#cabda9"
                elif kind=="foot":
                    width = 3 if detail else 2
                    color = "#ae755d" if tags.get("footway")=="crossing" else "#b0987d"
                    stroke = "#f5efe4"
                else:
                    width=3 if detail else 2
                    color=stroke="#a2ccdc"
                widths.setdefault(kind, set()).add(width)
                for part in parts:
                    pts=[pixel(x,y,view) for x,y in part.coords]
                    draw.line(pts, fill=stroke, width=width+2, joint="curve")
                    draw.line(pts, fill=color, width=width, joint="curve")
                label_point=max(parts,key=lambda a:a.length).interpolate(.5,normalized=True)
            counts[kind]+=1
            label=tags.get("name:zh") or tags.get("name") or tags.get("name:en")
            if label and kind in {"land","water","building","road"}:
                priority=0 if ref==scene["building_native_id"] else {"land":2,"water":2,"building":3,"road":4}[kind]
                labels.append((priority,ref,label,label_point))
    for point,label,key in points:
        if clip.contains(point):
            labels.append((5, f"node/{key}",label,point))
    occupied=[(0,HEIGHT-68,WIDTH,HEIGHT),(WIDTH-70,0,WIDTH,95)]
    names=set()
    for priority, ref, text, point in sorted(labels,key=lambda i:(i[0],i[1])):
        if text in names:
            continue
        x,y=pixel(point.x,point.y,view)
        size = 19 if priority==0 else (15 if view["zoom"]==18 else 14)
        bounds=draw.textbbox((x,y),text,font=font(size),anchor="mm",stroke_width=2)
        bounds=(bounds[0]-6,bounds[1]-4,bounds[2]+6,bounds[3]+4)
        if (bounds[0]<9 or bounds[1]<9 or bounds[2]>WIDTH-9 or bounds[3]>HEIGHT-9
                or any(bounds[0]<b[2] and bounds[2]>b[0] and bounds[1]<b[3] and bounds[3]>b[1] for b in occupied)):
            skipped+=1
            continue
        caption(draw, text, (x,y), size, anchor="mm", fill="#314b52" if priority<3 else "#535d5c")
        names.add(text)
        occupied.append(bounds)
    scale=frame(draw, view)
    return im, {"feature_counts":dict(counts), "render_stroke_css_pixels":{k:sorted(v) for k,v in widths.items()},
                "physical_road_width": "UNKNOWN_NOT_INFERRED_FROM_STYLE", "visible_unique_labels":len(names),
                "decluttered_labels":skipped, "scale":scale,"attribution":"© OpenStreetMap contributors · ODbL"}


def route_overlay(base, scene, view, route):
    image = base.copy()
    draw = ImageDraw.Draw(image)
    clip = box(*view["extent_3857"])
    footprint = Polygon([FORWARD(*p) for p in scene["building_footprint"]["coordinates"][0]])
    draw.line([pixel(x,y,view) for x,y in footprint.exterior.coords],fill="#985126",width=3,joint="curve")
    geometry=route.get("geometry")
    shown=False
    if geometry and geometry["type"]=="LineString":
        line=LineString([FORWARD(*p) for p in geometry["coordinates"]])
        visible=list(pieces(line.intersection(clip),"LineString"))
        for part in visible:
            pts=[pixel(x,y,view) for x,y in part.coords]
            draw.line(pts,fill="#ffffff",width=9,joint="curve")
            draw.line(pts,fill="#1b5b93",width=5,joint="curve")
        shown=bool(visible)
    for key, point, color in (
        ("起",scene["start"],"#305c4a"),("网" if route.get("remaining_gap_to_original_target_m") is not None else "终",route.get("route_end"),"#1b5b93"),
        ("参",scene["target"],"#9a4e31"),
    ):
        if point is None:
            continue
        x,y=pixel(*FORWARD(*point),view)
        if not 0<=x<WIDTH or not 0<=y<HEIGHT:
            continue
        draw.ellipse((x-7,y-7,x+7,y+7),fill=color,outline="#ffffff",width=2)
        off=(17,-12) if key=="参" else (-17,-12)
        caption(draw,key,(x+off[0],y+off[1]),15,anchor="mm",fill=color)
    frame(draw,view)
    gap = route.get("remaining_gap_to_original_target_m")
    if gap is not None:
        text = f"局部诊断路线 · 到步网连接点 · 距入口参考仍差 {gap:.1f} m"
        width = draw.textlength(text, font=font(17))
        draw.rounded_rectangle((15, 14, 41+width, 52), 7, fill="#f8f5eb", outline="#acb9ba")
        caption(draw,text,(27,23),17,halo=0)
    return image, shown
