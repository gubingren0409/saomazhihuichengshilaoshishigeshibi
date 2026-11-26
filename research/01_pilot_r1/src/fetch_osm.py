"""Fetch one scoped, read-only OSM vector response. No public tiles."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://overpass-api.de/api/interpreter"
QUERY_VERSION = 1
LAYERS = ("building", "highway", "landuse", "leisure", "natural", "waterway",
          "amenity", "tourism", "barrier", "railway", "public_transport", "entrance")


def query(bounds):
    w, s, e, n = bounds
    if not (121.0 < w < e < 122.0 and 30.8 < s < n < 32.0 and e - w < .05 and n - s < .05):
        raise ValueError("OSM_BOUNDS_OUTSIDE_SHANGHAI_PILOT")
    bbox = ",".join(str(v) for v in (s, w, n, e))
    areas = ("building", "landuse", "leisure", "natural", "waterway", "amenity", "tourism")
    selected = [f'way["{k}"]({bbox});' for k in LAYERS]
    selected += [f'relation["type"="multipolygon"]["{k}"]({bbox});' for k in areas]
    selected += [f'node["{k}"]({bbox});' for k in ("name", "entrance", "barrier", "highway", "railway")]
    return "[out:json][timeout:24][maxsize:67108864];(" + "".join(selected) + ");out body;>;out skel qt;"


def fetch(root=ROOT):
    plan = json.loads((root / "runs/pilot_plan.json").read_text(encoding="utf-8"))
    bounds = plan["scene"]["snapshot_query_bbox_wsen"]
    command = query(bounds)
    output = root / "data" / "sh-huangpu-01.overpass.json"
    output.parent.mkdir(exist_ok=True)
    receipt_path = root / "runs" / "osm_acquisition.json"
    if output.exists() or receipt_path.exists():
        raise ValueError("OSM_FIRST_ACQUISITION_ALREADY_RECORDED")
    receipt = {"source": ENDPOINT, "request_type": "BOUNDED_READ_ONLY_VECTOR", "bounds_wsen": bounds,
               "query": command, "query_version": QUERY_VERSION, "license": "ODbL-1.0",
               "attribution": "© OpenStreetMap contributors", "started_utc": datetime.now(timezone.utc).isoformat()}
    max_bytes = 12 * 1024 * 1024
    request = Request(ENDPOINT, data=urlencode({"data": command}).encode(),
                      headers={"User-Agent": "OSM-GEOAPIFY-PILOT-R1/1.0 (bounded university map comparison)",
                               "Accept": "application/json"})
    try:
        with urlopen(request, timeout=40) as response:
            if response.url != ENDPOINT:
                raise ValueError("OSM_UNEXPECTED_REDIRECT")
            data = response.read(max_bytes + 1)
            receipt["http_status"] = response.status
        if len(data) > max_bytes:
            raise ValueError("OSM_RESPONSE_EXCEEDS_BYTE_LIMIT")
        payload = json.loads(data)
        if payload.get("remark") or not payload.get("elements"):
            raise ValueError("OSM_PARTIAL_OR_EMPTY_RESPONSE")
        with output.open("xb") as f:
            f.write(data)
        receipt.update(status="LIVE_VECTOR_SNAPSHOT", bytes=len(data), sha256=sha256(data).hexdigest(),
                       osm_base_timestamp=payload.get("osm3s", {}).get("timestamp_osm_base"),
                       generator=payload.get("generator"), raw_elements=len(payload["elements"]),
                       data_path=output.relative_to(root).as_posix())
    except HTTPError as error:
        receipt.update(status="HTTP_ERROR", http_status=error.code, retry_after=error.headers.get("Retry-After"))
    except (URLError, TimeoutError, OSError, ValueError) as error:
        receipt.update(status="ACQUISITION_FAILED", error_type=type(error).__name__)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    try:
        result = fetch()
        print(json.dumps({k:v for k,v in result.items() if k not in {"query"}}, ensure_ascii=True))
        sys.exit(0 if result["status"] == "LIVE_VECTOR_SNAPSHOT" else 2)
    except ValueError:
        print("OSM_ACQUISITION_REFUSED")
        sys.exit(2)
