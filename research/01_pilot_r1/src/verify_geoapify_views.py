"""Verify source-rendered static map dimensions, synthetic controls and viewport match."""
from hashlib import sha256
import json
from math import hypot
from pathlib import Path
from statistics import linear_regression

from PIL import Image, ImageChops, ImageColor
from shapely import LineString, Polygon, box

from .complete_geoapify_static import CONTRACT, PROBE, RECEIPT, atomic_write
from .scene import FORWARD, INVERSE, ROOT, distance

OUTPUT = Path("runs/geoapify_static_completion.json")
EPSILON_PX = 1.0
ATTRIBUTION = "© OpenStreetMap contributors · © OpenMapTiles · Powered by Geoapify"


def image_pair(root, row):
    asset = row["asset"]
    path = root / asset["path"]
    if path.stat().st_size != asset["bytes"] or sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
        raise ValueError("STATIC_PNG_SHA_MISMATCH")
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError("STATIC_IMAGE_FORMAT_MISMATCH")
        return image.convert("RGB")


def controls_and_stability(base, overlay, controls):
    colors = {ImageColor.getrgb(item["color"]): [] for item in controls}
    rgb0, rgb1 = base.getdata(), overlay.getdata()
    unchanged = 0
    for i,(before,after) in enumerate(zip(rgb0,rgb1)):
        if before == after:
            unchanged += 1
        elif after in colors:
            colors[after].append((i % base.width + .5, i // base.width + .5))
    measured = []
    for row in controls:
        cells = colors[ImageColor.getrgb(row["color"])]
        if not (6 <= len(cells) <= 110):
            raise ValueError("CONTROL_MARK_NOT_ISOLATED")
        center = [sum(p[k] for p in cells)/len(cells) for k in (0,1)]
        if any(max(p[k] for p in cells)-min(p[k] for p in cells)>10 for k in (0,1)):
            raise ValueError("CONTROL_MARK_NOT_ISOLATED")
        measured.append({**row,"observed_px":center,"control_color_pixels":len(cells)})
    return measured, unchanged/(base.width*base.height)


def fit_viewport(view, controls, fraction):
    x = linear_regression([p["expected_px"][0] for p in controls],[p["observed_px"][0] for p in controls])
    y = linear_regression([p["expected_px"][1] for p in controls],[p["observed_px"][1] for p in controls])
    if min(x.slope, y.slope) <= 0:
        raise ValueError("STATIC_CAMERA_SCALE_INVALID")
    residuals = [hypot(p["observed_px"][0] - (x.slope*p["expected_px"][0]+x.intercept),
                       p["observed_px"][1] - (y.slope*p["expected_px"][1]+y.intercept)) for p in controls]
    w,s,e,n = view["extent_3857"]
    width,height = view["width"],view["height"]
    actual = (w + (-x.intercept/x.slope)*(e-w)/width,
              n - ((height-y.intercept)/y.slope)*(n-s)/height,
              w + ((width-x.intercept)/x.slope)*(e-w)/width,
              n - (-y.intercept/y.slope)*(n-s)/height)
    aw,bs,ae,bn = actual
    west,south = INVERSE(aw,bs)
    east,north = INVERSE(ae,bn)
    ground = distance(INVERSE(aw,(bs+bn)/2),INVERSE(ae,(bs+bn)/2))/width
    corner = max(hypot((x.slope-1)*i + x.intercept, (y.slope-1)*j + y.intercept)
                 for i in (0,width) for j in (0,height))
    valid = max(residuals) <= EPSILON_PX and fraction >= .90 and abs(x.slope/y.slope-1) <= .005
    return {"actual_bounds":[west,south,east,north] if valid else None,
            "extent_3857":list(actual) if valid else None,"meters_per_pixel":ground if valid else None,
            "bounds_match":valid and corner <= EPSILON_PX, "max_corner_error_css_px":corner,
            "control_max_fit_error_css_px":max(residuals),
            "base_overlay_identical_pixel_fraction":fraction, "control_points":controls}


def route_support(base, overlay, segments, view, alignment):
    w,s,e,n=alignment["extent_3857"]
    width,height = overlay.size
    color = ImageColor.getrgb("#195eae")
    mask = ImageChops.difference(base, overlay)
    probes = []
    for coords in segments:
        pixels=[((x-w)/(e-w)*width,(n-y)/(n-s)*height) for x,y in (FORWARD(*p) for p in coords)]
        line=LineString(pixels).intersection(box(4,4,width-4,height-4))
        parts = [line] if line.geom_type == "LineString" else getattr(line,"geoms",[])
        for part in parts:
            if part.geom_type == "LineString" and part.length > 0:
                probes.extend(part.interpolate(i+.5) for i in range(0,int(part.length),6))
    before,after = mask.load(),overlay.load()
    hits=0
    for p in probes:
        x,y=round(p.x),round(p.y)
        if any(before[u,v]!=(0,0,0) and after[u,v]==color
               for u in range(x-3,x+4) for v in range(y-3,y+4)
               if 0<=u<width and 0<=v<height):
            hits+=1
    return {"route_color_samples_matched":hits,"visible_route_color_samples":len(probes),
            "route_overlay_verified":len(probes)>8 and hits/len(probes)>=.95}


def verify(root=ROOT):
    requests=json.loads((root/RECEIPT).read_text(encoding="utf-8"))
    scene_raw=(root/CONTRACT).read_bytes()
    scene=json.loads(scene_raw)
    probe=json.loads((root/PROBE).read_text(encoding="utf-8"))
    route_ref=probe["geojson"]
    route_raw=(root/route_ref["path"]).read_bytes()
    if (requests["scene_contract_sha256"]!=sha256(scene_raw).hexdigest()
            or route_ref["sha256"]!=sha256(route_raw).hexdigest()):
        raise ValueError("FROZEN_REPLAY_HASH_MISMATCH")
    lines=[row["geometry"]["coordinates"] for row in json.loads(route_raw)["features"]]
    state={"scene_id":scene["scene_id"],"views":{},"route_geojson":route_ref,
           "route_display_verified":True,"status":"PARTIAL_WITH_EVIDENCE",
           "route_provider_distance_m":probe["route"]["provider_distance_m"],
           "route_target_offset_m":probe["route"]["target_offset_m"],
           "real_static_requests":sum(r.get("receipt",{}).get("execution")=="LIVE" for r in requests["requests"]),
           "actual_credits":None,"new_route_requests":0,"manual_visual_review":"PENDING_USER_REVIEW",
           "field_verification":0,"source_permission":"ALLOWED_WITH_CONDITIONS_RETAIN_ATTRIBUTION"}
    by_key={(r["view"],r["kind"]):r for r in requests["requests"]}
    footprint=Polygon([FORWARD(*p) for p in scene["building_footprint"]["coordinates"][0]])
    for name,view in scene["views"].items():
        clean=by_key.get((name,"base"),{})
        over=by_key.get((name,"route"),{})
        if clean.get("status")!="LIVE_SAVED":
            state["views"][name]={"status":clean.get("status","NOT_RUN")}
            continue
        record={"status":"VIEWPORT_NOT_VERIFIED","base":clean["asset"]["path"],"base_sha256":clean["asset"]["sha256"],
                "pixel_size":[view["width"],view["height"]],"human_display_verified":True,
                "local_retention_verified":True,"attribution_burned_in":False,"attribution":ATTRIBUTION}
        state["views"][name]=record
        if over.get("status")!="LIVE_SAVED":
            continue
        base,image=image_pair(root,clean),image_pair(root,over)
        if base.size!=image.size or base.size!=(view["width"],view["height"]):
            raise ValueError("STATIC_PAIR_SIZE_MISMATCH")
        measures,fraction=controls_and_stability(base,image,over["controls"])
        align=fit_viewport(view,measures,fraction)
        record.update(alignment=align,actual_bounds=align["actual_bounds"],
                      meters_per_pixel=align["meters_per_pixel"],bounds_match=align["bounds_match"],
                      max_corner_error_css_px=align["max_corner_error_css_px"])
        if align["extent_3857"] is not None:
            coverage=box(*align["extent_3857"])
            pw,ps,pe,pn=footprint.bounds
            aw,bs,ae,bn=coverage.bounds
            record.update(target_pixel_size=[(pe-pw)*base.width/(ae-aw),(pn-ps)*base.height/(bn-bs)],
                          target_area_ratio=footprint.intersection(coverage).area/coverage.area,
                          target_pixel_measurement="FROZEN_OSM_FOOTPRINT_PROJECTED_ON_VERIFIED_CAMERA")
            record["status"]="LOCAL_REAL" if align["bounds_match"] else "VIEWPORT_MISMATCH"
            support=route_support(base,image,lines,view,align)
            record["overlay_qa"]=support
            if support["route_overlay_verified"]:
                record.update(route=over["asset"]["path"],route_sha256=over["asset"]["sha256"],
                              route_identity="GEOAPIFY_ROUTING_ROUTE",
                              route_target_offset_m=probe["route"]["target_offset_m"],route_control_points=4)
    if all(v.get("bounds_match") and v.get("route") for v in state["views"].values()):
        state["status"]="READY_FOR_USER_VISUAL_REVIEW"
    atomic_write(root/OUTPUT,state)
    return state


if __name__=="__main__":
    results=verify()
    print(json.dumps({"status":results["status"],"views":{
        k:{"match":v.get("bounds_match"),"meters_per_pixel":v.get("meters_per_pixel"),
           "overlay":v.get("overlay_qa"),"corner_error_px":v.get("max_corner_error_css_px"),
           "identical_pixel_fraction":v.get("alignment",{}).get("base_overlay_identical_pixel_fraction")}
        for k,v in results["views"].items()}}))
