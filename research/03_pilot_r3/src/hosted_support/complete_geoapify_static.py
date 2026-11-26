"""Fetch the two frozen Geoapify views and their source-rendered overlays."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from .geoapify import Geoapify, GeoapifyError, NoRedirect, read_api_key
from .probe_geoapify import eligible_local_proxy
from .scene import INVERSE, ROOT

COLORS = ("#f410c9", "#0ee8ec", "#ff6b01", "#55ea04")
LINE_COLOR = "#195eae"
CONTRACT = Path("runs/scene_contract.json")
PROBE = Path("runs/geoapify_walk_probe_proxy.json")
RECEIPT = Path("runs/geoapify_static_requests.json")
IMAGE_DIR = Path("visuals/geoapify")


def control_points(view):
    w, s, e, n = view["extent_3857"]
    positions = ((.16,.16),(.84,.16),(.16,.84),(.84,.84))
    return [{"wgs84": INVERSE(w + u*(e-w), n - v*(n-s)),
             "expected_px":[u*view["width"],v*view["height"]], "color":color}
            for (u,v),color in zip(positions,COLORS)]


def encode_polyline6(line):
    previous = [0, 0]
    encoded = []
    for lon, lat in line:
        for index, value in enumerate((lat, lon)):
            scaled = round(value * 1_000_000)
            diff = scaled - previous[index]
            previous[index] = scaled
            value = ~(diff << 1) if diff < 0 else diff << 1
            while value >= 32:
                encoded.append(chr(((value & 31) | 32) + 63))
                value >>= 5
            encoded.append(chr(value + 63))
    return "".join(encoded)


def circle(point, color, radius):
    lon, lat = point
    return (f"circle:{lon:.9f},{lat:.9f},{radius};linecolor:{color};linewidth:1;"
            f"fillcolor:{color};lineopacity:1;fillopacity:1")


def overlay_geometry(segments, controls, entrance):
    values = [f"polyline6:{encode_polyline6(line)};linecolor:{LINE_COLOR};linewidth:5;lineopacity:1"
              for line in segments]
    values.extend((circle(segments[0][0], "#2f6b4a", 6),
                   circle(segments[-1][-1], LINE_COLOR, 7), circle(entrance, "#8c4a27", 6)))
    values.extend(circle(item["wgs84"], item["color"], 4) for item in controls)
    return "|".join(values)


def atomic_write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def execute(root=ROOT):
    raw = (root / CONTRACT).read_bytes()
    scene = json.loads(raw)
    probe = json.loads((root / PROBE).read_text(encoding="utf-8"))
    if probe["status"] != "LIVE_ROUTE_RETURNED" or probe["scene_contract_sha256"] != sha256(raw).hexdigest():
        raise ValueError("ROUTE_AND_FROZEN_SCENE_MUST_MATCH")
    route_path = root / probe["geojson"]["path"]
    route_bytes = route_path.read_bytes()
    if sha256(route_bytes).hexdigest() != probe["geojson"]["sha256"]:
        raise ValueError("ROUTE_SHA_MISMATCH")
    features = json.loads(route_bytes)["features"]
    if not features or any(item["geometry"]["type"] != "LineString" for item in features):
        raise ValueError("FROZEN_ROUTE_LINESTRINGS_REQUIRED")
    lines = [item["geometry"]["coordinates"] for item in features]
    audit = (root/"01_SOURCE_AND_PERMISSION_AUDIT.md").read_text(encoding="utf-8")
    if not all(url in audit for url in ("https://www.geoapify.com/static-maps-api/",
                                         "https://apidocs.geoapify.com/docs/maps/static/#attribution")):
        raise ValueError("STATIC_MAP_PERMISSION_AUDIT_REQUIRED")
    proxy = eligible_local_proxy()
    client = Geoapify(read_api_key(root), confirmed_free=True,
                      opener=build_opener(ProxyHandler({"https": proxy}), NoRedirect()))
    path = root / RECEIPT
    state = {"scene_id": scene["scene_id"],"scene_contract_sha256": sha256(raw).hexdigest(),
             "route_geojson":probe["geojson"],"status":"RESERVED","requests":[],
             "authorization":"USER_REQUESTED_BLANK_SIDE_COMPLETION_WITHIN_FREE_PLAN_ASSUMPTION",
             "transport":"EXISTING_LOCAL_HTTPS_PROXY","request_budget":4,
             "scope":"TWO_BASE_AND_TWO_ROUTE_OVERLAY_STATIC_MAPS","route_requests":0,
             "account_credits_independently_verified":False,
             "started_utc":datetime.now(timezone.utc).isoformat()}
    for name in scene["views"]:
        for kind in ("base","route"):
            if (root/IMAGE_DIR/f"{scene['scene_id']}_{name}_{kind}.png").exists():
                raise ValueError("STATIC_ARTIFACT_ALREADY_EXISTS")
    with path.open("x", encoding="utf-8") as file:
        json.dump(state,file,indent=2)
    (root / IMAGE_DIR).mkdir(parents=True,exist_ok=True)
    for name,view in scene["views"].items():
        for kind in ("base","route"):
            controls = control_points(view) if kind == "route" else []
            row = {"view":name,"kind":kind,"status":"REQUEST_STARTED","controls":controls}
            state["requests"].append(row)
            atomic_write(path,state)
            try:
                result=client.static_map(view["bounds"],width=view["width"],height=view["height"],
                    geometry=overlay_geometry(lines,controls,scene["target"]) if controls else None)
            except GeoapifyError as error:
                row.update(status=error.code,receipt=error.receipt)
                state["status"]="STATIC_REQUEST_INCOMPLETE"
                atomic_write(path,state)
                return state
            filename=IMAGE_DIR/f"{scene['scene_id']}_{name}_{kind}.png"
            with (root/filename).open("xb") as file:
                file.write(result.data)
            row.update(status="LIVE_SAVED",receipt=result.receipt,asset={
                "path":filename.as_posix(),"sha256":sha256(result.data).hexdigest(),"bytes":len(result.data)})
            atomic_write(path,state)
    state["status"]="FOUR_LIVE_STATIC_IMAGES"
    state["finished_utc"]=datetime.now(timezone.utc).isoformat()
    atomic_write(path,state)
    return state


if __name__ == "__main__":
    try:
        state=execute()
        print(json.dumps({"status":state["status"],
                          "requests":[{k:r.get(k) for k in ("view","kind","status")} |
                                      {"http":r.get("receipt",{}).get("status_code")}
                                      for r in state["requests"]]}))
    except (GeoapifyError, OSError, ValueError, RuntimeError, KeyError):
        print("STATIC_COMPLETION_NOT_STARTED_OR_STOPPED_CHECK_RECEIPT")
        raise SystemExit(2) from None
