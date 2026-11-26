"""R3 Geoapify capture. One walking request and four attributed static-map requests per frozen scene."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from ipaddress import ip_address
import json
from pathlib import Path
import re
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, build_opener, getproxies, proxy_bypass

from PIL import Image
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import transform

from .hosted_support.complete_geoapify_static import circle, control_points, overlay_geometry
from .hosted_support.geoapify import (
    ROUTING_URL, STATIC_URL, Geoapify, GeoapifyError, NoRedirect, read_api_key,
)
from .hosted_support.scene import FORWARD, GEOD
from .hosted_support.verify_geoapify_views import controls_and_stability, fit_viewport, route_support

ROOT = Path(__file__).resolve().parents[1]
R1 = ROOT.parent / "OSM_GEOAPIFY_PILOT_R1"
SCENES = Path("runs/scene_contracts.json")
RESULTS = Path("runs/hosted_results.json")
LOCK = Path("runs/hosted_capture.lock")
MAX_LIVE_REQUESTS = 25
MIN_SPACING_S = 1.10
TERMINAL_HTTP = {401, 402, 403, 407, 429}
ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")
QUOTA_HEADER = re.compile(r"(?:x-)?(?:ratelimit|rate-limit|quota|credits?|geoapify-credits?)(?:-[a-z]{1,20}){0,4}|retry-after")
SECRET_FIELDS = {"apikey", "authorization", "cookie", "setcookie", "accesstoken", "refreshtoken", "clientsecret"}
HOSTED_ATTRIBUTION = "© OpenStreetMap contributors · © OpenMapTiles · Powered by Geoapify"


def utc():
    return datetime.now(timezone.utc).isoformat()


def put(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def artifact(root, relative, payload):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(payload)
    return {"path": relative.as_posix(), "sha256": sha256(payload).hexdigest(), "bytes": len(payload)}


def allowed_raw(body, key):
    """Reject credentials in literals, escaped JSON values, and credential-shaped field names."""
    try:
        document = json.loads(body)
    except (ValueError, UnicodeError):
        return False
    def safe(value):
        if isinstance(value, dict):
            return all(re.sub(r"[^a-z]", "", name.lower()) not in SECRET_FIELDS and safe(item)
                       and (not key or key not in name) for name, item in value.items())
        if isinstance(value, list):
            return all(safe(item) for item in value)
        return not isinstance(value, str) or not key or key not in value
    return isinstance(document, dict) and safe(document)


def local_proxy():
    """Only the pre-existing loopback proxy verified by R1 is eligible."""
    prior = json.loads((R1 / "runs/geoapify_walk_probe_proxy.json").read_text(encoding="utf-8-sig"))
    if prior.get("status") != "LIVE_ROUTE_RETURNED" or prior.get("transport") != "EXISTING_LOCAL_HTTPS_PROXY":
        raise RuntimeError("R1_LOOPBACK_PROXY_EVIDENCE_REQUIRED")
    proxy = getproxies().get("https", "")
    if not proxy or any(proxy_bypass(urlsplit(url).hostname) for url in (ROUTING_URL, STATIC_URL)):
        raise RuntimeError("NO_ELIGIBLE_LOCAL_PROXY")
    parsed = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
        raise RuntimeError("NO_ELIGIBLE_LOCAL_PROXY")
    if parsed.hostname != "localhost" and not ip_address(parsed.hostname).is_loopback:
        raise RuntimeError("NO_ELIGIBLE_LOCAL_PROXY")
    return proxy


class JournaledOpener:
    """Per-request durable reservation, safe numeric quota metadata, and bounded serial transport."""

    def __init__(self, opener, state, path):
        self.opener, self.state, self.path = opener, state, path
        self.row = None
        self.last = None
        self.header_names = []
        self.numeric_headers = {}

    def open(self, request, *, timeout):
        if self.row is None or self.row.get("started_utc") is not None:
            raise RuntimeError("HOSTED_REQUEST_REUSE_REFUSED")
        if self.state["requests_attempted"] >= MAX_LIVE_REQUESTS:
            raise RuntimeError("R3_LIVE_REQUEST_BUDGET_EXHAUSTED")
        endpoint = request.full_url.split("?", 1)[0]
        if endpoint not in {ROUTING_URL, STATIC_URL}:
            raise RuntimeError("HOSTED_ENDPOINT_NOT_ALLOWLISTED")
        if self.last is not None:
            sleep(max(0, MIN_SPACING_S - (monotonic() - self.last)))
        self.row.update(started_utc=utc(), execution="LIVE", endpoint=endpoint)
        self.state["requests_attempted"] += 1
        put(self.path, self.state)
        self.last = monotonic()
        try:
            response = self.opener.open(request, timeout=timeout)
        except HTTPError as error:
            self.record_headers(error.headers)
            raise
        self.record_headers(response.headers)
        return response

    def record_headers(self, headers):
        if headers is None:
            return
        for name in headers.keys():
            lower = name.lower()
            if QUOTA_HEADER.fullmatch(lower):
                self.header_names.append(lower)
                text = headers.get(name, "").strip()
                if re.fullmatch(r"[0-9]{1,12}", text):
                    self.numeric_headers[lower] = int(text)


class CaptureClient(Geoapify):
    """Reuse R1 parsing and keep the exact successful route response in memory until audited."""

    def _request(self, endpoint, params, accept):
        data, receipt = super()._request(endpoint, params, accept)
        if endpoint == ROUTING_URL:
            self.route_body = data
        return data, receipt


def plan(root):
    raw = (root / SCENES).read_bytes()
    obj = json.loads(raw)
    scenes = obj["scenes"]
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 5:
        raise ValueError("R3_FROZEN_SCENE_COUNT_OUT_OF_SCOPE")
    seen = set()
    for row in scenes:
        id_ = row["scene_id"]
        if id_ in seen or not isinstance(id_, str) or not ID_PATTERN.fullmatch(id_):
            raise ValueError("R3_SCENE_ID_INVALID")
        seen.add(id_)
        if row["contract_status"] == "READY" and (
                row.get("frozen_before_route") is not True or set(row["views"]) != {"detail", "context"}):
            raise ValueError("R3_READY_CONTRACT_NOT_FROZEN")
        for view in row.get("views", {}).values():
            if (view["width"], view["height"]) != (1200, 900):
                raise ValueError("R3_VIEWPORT_DIMENSIONS_OUT_OF_SCOPE")
    return scenes, sha256(raw).hexdigest()


def route_measure(line):
    coords = [list(zip(*points)) for points in line]
    return sum(abs(GEOD.line_length(lon,lat)) for lon,lat in coords)


def overlay_for_view(lines, view, target, *, clipped=False):
    controls = control_points(view)
    if clipped:
        clip = box(*view["bounds"])
        selected = []
        for source in lines:
            original = LineString(source)
            cut = original.intersection(clip)
            for part in getattr(cut, "geoms", [cut]):
                if part.geom_type == "LineString" and part.length > 0:
                    points = list(part.coords)
                    if original.project(Point(points[0])) > original.project(Point(points[-1])):
                        points.reverse()
                    selected.append(points)
        lines = selected
    if lines and target is not None:
        return overlay_geometry(lines, controls, target), controls
    values = [circle(item["wgs84"], item["color"], 4) for item in controls]
    if target is not None:
        values.append(circle(target, "#8c4a27", 6))
    return "|".join(values), controls


def align_images(root, view, base_path, overlay_path, controls, lines, footprint):
    with Image.open(root / base_path) as base, Image.open(root / overlay_path) as overlay:
        if base.size != overlay.size or base.size != (view["width"], view["height"]):
            raise ValueError("STATIC_PAIR_SIZE_MISMATCH")
        a, b = base.convert("RGB"), overlay.convert("RGB")
        observed, unchanged = controls_and_stability(a, b, controls)
        align = fit_viewport(view, observed, unchanged)
        align["route_support"] = None
        if align["extent_3857"] is not None:
            if lines:
                align["route_support"] = route_support(a, b, lines, view, align)
            if footprint:
                projected = transform(FORWARD, shape(footprint))
                camera = box(*align["extent_3857"])
                aw, bs, ae, bn = camera.bounds
                w, s, e, n = projected.bounds
                align.update(target_footprint_pixel_size=[(e-w)*a.width/(ae-aw), (n-s)*a.height/(bn-bs)],
                             target_footprint_area_ratio=projected.intersection(camera).area / camera.area,
                             target_footprint_method="FROZEN_OSM_FOOTPRINT_PROJECTED_ON_CALIBRATED_CAMERA")
    return align


def capture_scene(root, scene, record, state, path, proxy, key):
    transport = JournaledOpener(build_opener(ProxyHandler({"https": proxy}), NoRedirect()),
                                state, path)
    client = CaptureClient(key, confirmed_free=True, opener=transport)

    def request(label, perform):
        if any(old["operation"] == label and old.get("execution") == "LIVE" for old in record["requests"]):
            raise RuntimeError("R3_ALREADY_ATTEMPTED_NO_RETRY")
        row = {"operation": label, "execution": "NOT_REQUESTED", "status": "RESERVED"}
        record["requests"].append(row)
        transport.row = row
        transport.header_names, transport.numeric_headers = [], {}
        put(path, state)
        try:
            result = perform()
        except GeoapifyError as error:
            row.update(status=error.code, receipt=error.receipt)
            status = (error.receipt or {}).get("status_code")
            if status in TERMINAL_HTTP:
                state["halt_reason"] = error.code
            result = None
        else:
            row.update(status="HTTP_200_PARSED", receipt=result.receipt)
        row.update(quota_header_names=sorted(set(transport.header_names)),
                   numeric_quota_headers=transport.numeric_headers)
        if any(transport.numeric_headers.get(n) == 0 for n in
               ("x-credits-remaining", "x-geoapify-credits-remaining", "x-quota-remaining")):
            state["halt_reason"] = "SERVICE_REPORTS_NO_REMAINING_QUOTA"
        put(path, state)
        return result, row

    record["status"] = "IN_PROGRESS"
    lines = []
    if scene.get("start") is not None and scene.get("target") is not None:
        res, row = request("route", lambda: client.walk_route(scene["start"], scene["target"]))
        if res:
            data = dict(res.data)
            line = data.pop("geojson")
            line["attribution"] = data["attribution"]
            lines = [f["geometry"]["coordinates"] for f in line["features"]]
            route = artifact(root, Path("hosted") / f"{scene['scene_id']}_route.geojson",
                             (json.dumps(line, ensure_ascii=False, indent=2) + "\n").encode())
            raw = None
            body = client.route_body
            if allowed_raw(body, key):
                raw = artifact(root, Path("hosted") / f"{scene['scene_id']}_routing_response.json", body)
            data.update(status="LIVE_ROUTE_RETURNED", receipt=res.receipt, geometry_path=route["path"],
                        geometry_sha256=route["sha256"], raw_response_path=raw["path"] if raw else None,
                        raw_response_sha256=raw["sha256"] if raw else None,
                        raw_response_status="RETAINED_REDACTED_CHECKED" if raw else "NOT_RETAINED_CREDENTIAL_GUARD",
                        geometry_length_m_wgs84=route_measure(lines), provider_graph_availability="UNKNOWN")
            record["route"] = data
        else:
            record["route"] = {"status":row["status"], "receipt":row["receipt"], "geometry_path":None}
        put(path,state)
    else:
        record["route"] = {"status":"SKIPPED_ENDPOINT_UNKNOWN", "geometry_path":None}
    for view_name in ("detail","context"):
        if state.get("halt_reason"):
            break
        view = scene["views"][view_name]
        spec = {"width":view["width"], "height":view["height"]}
        view_record = {"status":"BASE_PENDING", "base":None, "overlay":None,
                       "bounds_match":None, "actual_bounds":None,
                       "attribution":HOSTED_ATTRIBUTION, "attribution_burned_in":"UNVERIFIED",
                       "source_type":"HOSTED_RENDERED_ONLY"}
        record["views"][view_name] = view_record
        res, row = request(view_name+"_base", lambda: client.static_map(view["bounds"], **spec))
        if not res:
            view_record["status"] = row["status"]
            continue
        relative = Path("visuals/geoapify") / f"{scene['scene_id']}_{view_name}_base.png"
        saved = artifact(root,relative,res.data)
        view_record.update(base=saved["path"], base_sha256=saved["sha256"], base_bytes=saved["bytes"],
                           width=view["width"],height=view["height"],status="LIVE_BASE")
        if state.get("halt_reason"):
            break
        geom,controls = overlay_for_view(lines,view,scene.get("target"))
        # Clip the display geometry only if the GET contract is too long. This is not a second API request.
        if len(geom)>1700 or len(urlencode({"geometry":geom}))>1700:
            geom, controls = overlay_for_view(lines,view,scene.get("target"),clipped=True)
            view_record["route_overlay_geometry"] = "CLIPPED_FOR_DISPLAY_ONLY"
        else:
            view_record["route_overlay_geometry"] = "FULL_PROVIDER_ROUTE" if lines else "NO_ROUTE_CONTROLS_ONLY"
        over, row = request(view_name+"_overlay", lambda: client.static_map(view["bounds"],geometry=geom,**spec))
        if not over:
            view_record["status"] = "LIVE_BASE_"+row["status"]
            continue
        relative = Path("visuals/geoapify") / f"{scene['scene_id']}_{view_name}_route.png"
        saved = artifact(root,relative,over.data)
        view_record.update(overlay=saved["path"],overlay_sha256=saved["sha256"],overlay_bytes=saved["bytes"],
                           status="LIVE_BASE_AND_OVERLAY", controls=controls)
        try:
            alignment = align_images(root,view,view_record["base"],view_record["overlay"],controls,lines,
                                     scene.get("building_footprint"))
        except (ValueError,OSError,ZeroDivisionError):
            view_record["status"] = "LIVE_IMAGES_ALIGNMENT_UNKNOWN"
        else:
            view_record.update(alignment=alignment,bounds_match=alignment["bounds_match"],
                               actual_bounds=alignment["actual_bounds"],
                               meters_per_pixel=alignment["meters_per_pixel"])
        put(path,state)
    record["status"] = "LIVE_SCENE_PROCESSED" if not state.get("halt_reason") else "STOPPED_BY_SERVICE"
    put(path,state)


def execute(root, selection):
    scenes, contract_sha = plan(root)
    path = root / RESULTS
    path.parent.mkdir(parents=True,exist_ok=True)
    if not (root / "01_SOURCE_AND_PERMISSION_AUDIT.md").is_file():
        raise RuntimeError("R3_PERMISSION_AUDIT_REQUIRED")
    if selection == "remaining":
        wanted = [s for s in scenes if s["contract_status"] == "READY"]
    else:
        wanted = [s for s in scenes if s["scene_id"] == selection and s["contract_status"] == "READY"]
        if len(wanted)!=1:
            raise ValueError("R3_REQUESTED_SCENE_NOT_READY")
    proxy,key = local_proxy(),read_api_key(R1)
    with (root / LOCK).open("x",encoding="utf-8") as lock:
        lock.write(utc()+"\n")
    try:
        if path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
            if state["scene_contract_sha256"] != contract_sha:
                raise ValueError("R3_FROZEN_CONTRACT_HASH_CHANGED")
        else:
            state = {"state":"READY", "scene_contract_sha256":contract_sha,
                     "request_cap":MAX_LIVE_REQUESTS,"requests_attempted":0,"halt_reason":None,
                     "free_plan_documented_credits_per_day":3000,"account_balance_observed":False,
                     "billing_upgrade_or_purchase":False,"scenes":[
                         {"scene_id":s["scene_id"],"status":"NOT_RUN" if s["contract_status"]=="READY" else "SKIPPED_UNFROZEN_OR_UNAVAILABLE",
                          "route":None,"views":{},"requests":[]} for s in scenes]}
            put(path,state)
        if state.get("halt_reason"):
            return state
        by_id = {row["scene_id"]:row for row in state["scenes"]}
        for scene in wanted:
            record = by_id[scene["scene_id"]]
            if record["status"] != "NOT_RUN":
                continue
            capture_scene(root,scene,record,state,path,proxy,key)
            if state.get("halt_reason"):
                break
        state["state"] = "HALTED" if state.get("halt_reason") else "JOURNALED"
        state["last_finished_utc"] = utc()
        put(path,state)
        return state
    finally:
        (root / LOCK).unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", required=True, metavar="FROZEN_SCENE_ID_OR_REMAINING")
    options=parser.parse_args()
    try:
        result=execute(ROOT, options.live)
    except (GeoapifyError, OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        code=str(error)
        print(code if re.fullmatch(r"[A-Z0-9_]{4,100}",code) else "R3_HOSTED_EXECUTION_FAILED_CHECK_RECEIPT")
        raise SystemExit(2) from None
    print(json.dumps({"state":result["state"], "requests_attempted":result["requests_attempted"],
        "halt_reason":result.get("halt_reason"), "scenes":[
            {"scene_id":r["scene_id"],"status":r["status"],
             "route":(r["route"] or {}).get("status"),
             "views":{v:{"status":i.get("status"),"bounds_match":i.get("bounds_match")}
                      for v,i in r["views"].items()}} for r in result["scenes"]]}))
