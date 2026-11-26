"""Bounded Geoapify Static Maps and walking Routing adapter.

Uses only approved provider hosts. Outputs never include credentials or raw
upstream error text. Callers decide where to persist permitted artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from math import asin, cos, isfinite, radians, sin, sqrt
import os
from pathlib import Path
import re
import struct
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zlib import crc32


API_KEY_NAME = "GEOAPIFY_API_KEY"
STATIC_URL = "https://maps.geoapify.com/v1/staticmap"
ROUTING_URL = "https://api.geoapify.com/v1/routing"
STATIC_STYLE = "osm-bright-smooth"
MAX_REQUESTS = 18  # Two views and one route for each of up to six buildings.
MAX_BODY = 8 * 1024 * 1024
ATTRIBUTION = (
    "© OpenStreetMap contributors",
    "© OpenMapTiles",
    "Powered by Geoapify",
)
KEY_SHAPE = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")


class GeoapifyError(RuntimeError):
    def __init__(self, code, receipt=None):
        super().__init__(code)
        self.code = code
        self.receipt = receipt


@dataclass(frozen=True)
class Result:
    data: bytes | dict = field(repr=False)
    receipt: dict


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def read_api_key(root: Path) -> str:
    """Read the process slot or the exact project-local .env file."""
    value = os.environ.get(API_KEY_NAME, "")
    path = Path(root) / ".env"
    if not value and path.is_file():
        try:
            if path.stat().st_size > 16_384:
                raise GeoapifyError("ENV_TOO_LARGE")
            values = []
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                name, sep, item = line.partition("=")
                if sep and name.strip() == API_KEY_NAME:
                    values.append(item.strip())
            if len(values) > 1:
                raise GeoapifyError("DUPLICATE_GEOAPIFY_KEY")
            value = values[0] if values else ""
        except (OSError, UnicodeError):
            raise GeoapifyError("ENV_UNREADABLE") from None
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        value = value[1:-1]
    if value and not KEY_SHAPE.fullmatch(value):
        raise GeoapifyError("INVALID_GEOAPIFY_KEY_FORMAT")
    return value


def credential_status(root: Path) -> str:
    try:
        return "PRESENT" if read_api_key(root) else "MISSING"
    except GeoapifyError as error:
        return error.code


def _number(value) -> bool:
    return type(value) in {float, int} and abs(value) <= 1e12 and isfinite(value)


def _lonlat(point):
    if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(map(_number, point)):
        raise GeoapifyError("INVALID_WGS84_COORDINATES")
    lon, lat = point
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise GeoapifyError("INVALID_WGS84_COORDINATES")
    return [lon, lat]


def _haversine(a, b):
    lon1, lat1, lon2, lat2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2)**2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2)**2
    return 2 * 6371008.8 * asin(sqrt(min(1, max(0, h))))


def _png_dimensions(data: bytes):
    if (len(data) < 45 or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
            or data[-12:] != b"\x00\x00\x00\x00IEND\xaeB`\x82"):
        raise GeoapifyError("INVALID_PNG")
    offset, has_image = 8, False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            break
        chunk = data[offset + 4:chunk_end - 4]
        if crc32(chunk) != struct.unpack_from(">I", data, chunk_end - 4)[0]:
            break
        if chunk[:4] == b"IDAT" and length:
            has_image = True
        if chunk == b"IEND":
            if has_image and chunk_end == len(data):
                return struct.unpack(">II", data[16:24])
            break
        offset = chunk_end
    raise GeoapifyError("INVALID_PNG")


def _route_result(document, start, target):
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise GeoapifyError("INVALID_ROUTING_RESPONSE")
    features = document.get("features")
    if not isinstance(features, list):
        raise GeoapifyError("INVALID_ROUTING_RESPONSE")
    if not features:
        raise GeoapifyError("NO_ROUTE")
    route = features[0]
    if not isinstance(route, dict) or route.get("type") != "Feature":
        raise GeoapifyError("INVALID_ROUTING_RESPONSE")
    properties = route.get("properties")
    geometry = route.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise GeoapifyError("INVALID_ROUTING_RESPONSE")
    units = properties.get("distance_units", "meters")
    if not isinstance(units, str) or units.lower() != "meters":
        raise GeoapifyError("UNEXPECTED_ROUTING_UNITS")
    distance, duration = properties.get("distance"), properties.get("time")
    if not all(_number(x) and x >= 0 for x in (distance, duration)):
        raise GeoapifyError("INVALID_ROUTING_MEASUREMENTS")
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "LineString":
        coordinates = [coordinates]
    elif geometry.get("type") != "MultiLineString":
        raise GeoapifyError("INVALID_ROUTING_GEOMETRY")
    if not isinstance(coordinates, list) or not coordinates:
        raise GeoapifyError("INVALID_ROUTING_GEOMETRY")
    if not all(isinstance(line, list) and len(line) >= 2 for line in coordinates):
        raise GeoapifyError("INVALID_ROUTING_GEOMETRY")
    segments = [[_lonlat(point) for point in line] for line in coordinates]
    first, last = segments[0][0], segments[-1][-1]
    # Preserve leg breaks. Never bridge a route gap with an invented segment.
    route_features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": segment},
            "properties": {"segment_index": i, "source": "Geoapify Routing API"},
        }
        for i, segment in enumerate(segments)
    ]
    return {
        "source": "Geoapify Routing API",
        "attribution": list(ATTRIBUTION[::2]),
        "crs": "EPSG:4326",
        "mode": "walk",
        "provider_distance_m": distance,
        "provider_duration_s": duration,
        "geometry_length_m": sum(
            _haversine(a, b) for segment in segments for a, b in zip(segment, segment[1:])
        ),
        "requested_start_wgs84": start,
        "requested_target_wgs84": target,
        "route_start_wgs84": first,
        "route_endpoint_wgs84": last,
        "start_offset_m": _haversine(start, first),
        "target_offset_m": _haversine(target, last),
        "segment_gaps_m": [_haversine(a[-1], b[0]) for a, b in zip(segments, segments[1:])],
        "provider_geometry_type": geometry["type"],
        "provider_feature_count": len(features),
        "geojson": {"type": "FeatureCollection", "features": route_features},
        "entrance": None,
        "entrance_identity": "UNKNOWN",
    }


class Geoapify:
    def __init__(self, key: str, *, confirmed_free: bool, opener=None):
        if not key:
            raise GeoapifyError("GEOAPIFY_KEY_MISSING")
        if not isinstance(key, str) or not KEY_SHAPE.fullmatch(key):
            raise GeoapifyError("INVALID_GEOAPIFY_KEY_FORMAT")
        if confirmed_free is not True:
            raise GeoapifyError("ZERO_COST_QUOTA_NOT_CONFIRMED")
        self._key = key
        self._opener = opener or build_opener(ProxyHandler({}), NoRedirect())
        self._lock = Lock()
        self._requests = 0
        self._last_start = None

    @classmethod
    def from_env(cls, root: Path, *, confirmed_free: bool = False):
        return cls(read_api_key(root), confirmed_free=confirmed_free)

    def _request(self, endpoint, params, accept):
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        receipt = {
            "provider": "Geoapify",
            "execution": "NOT_REQUESTED",
            "endpoint": endpoint,
            "parameters": params,
            "started_utc": started,
            "status_code": None,
            "actual_credits": None,
        }
        request = Request(
            endpoint + "?" + urlencode(params),
            headers={"X-API-Key": self._key, "Accept": accept, "User-Agent": "OSM-Geoapify-Pilot-R1/1.0"},
        )
        with self._lock:
            if self._requests >= MAX_REQUESTS:
                raise GeoapifyError("PILOT_REQUEST_LIMIT", receipt)
            if self._last_start is not None:
                sleep(max(0, 1 - (monotonic() - self._last_start)))
            self._requests += 1
            receipt["execution"] = "LIVE"
            receipt["started_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._last_start = monotonic()
            elapsed_start = self._last_start
            try:
                with self._opener.open(request, timeout=25) as response:
                    receipt["status_code"] = response.status
                    data = response.read(MAX_BODY + 1)
                    content_type = response.headers.get_content_type()
            except HTTPError as error:
                receipt["status_code"] = error.code
                error.close()
                raise GeoapifyError("UPSTREAM_HTTP_" + str(error.code), receipt) from None
            except (URLError, OSError):
                raise GeoapifyError("UPSTREAM_TRANSPORT_ERROR", receipt) from None
            finally:
                receipt["elapsed_s"] = round(monotonic() - elapsed_start, 3)
        if receipt["status_code"] != 200:
            raise GeoapifyError("UNEXPECTED_HTTP_STATUS", receipt)
        if len(data) > MAX_BODY or self._key.encode("ascii") in data:
            raise GeoapifyError("UNSAFE_RESPONSE_BODY", receipt)
        if content_type not in {"image/png", "application/json", "application/geo+json"}:
            raise GeoapifyError("UNEXPECTED_CONTENT_TYPE", receipt)
        receipt.update(content_type=content_type, response_bytes=len(data))
        return data, receipt

    def static_map(self, bounds, *, width=1200, height=900, geometry=None):
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 4:
            raise GeoapifyError("INVALID_VIEWPORT_BOUNDS")
        west, south = _lonlat(bounds[:2])
        east, north = _lonlat(bounds[2:])
        if not (0 < east - west <= 0.05 and 0 < north - south <= 0.05 and -85 < south < north < 85):
            raise GeoapifyError("INVALID_VIEWPORT_BOUNDS")
        if type(width) is not int or type(height) is not int or not (128 <= width <= 1200 and 128 <= height <= 900):
            raise GeoapifyError("INVALID_VIEWPORT_DIMENSIONS")
        params = {
            "style": STATIC_STYLE,
            "width": width,
            "height": height,
            "area": "rect:" + ",".join(f"{v:.9f}" for v in (west, south, east, north)),
            "bearing": 0,
            "pitch": 0,
            "scaleFactor": 1,
            "attribution": "default",
            "format": "png",
        }
        if geometry is not None:
            if not isinstance(geometry, str) or not geometry or len(geometry) > 1700:
                raise GeoapifyError("INVALID_STATIC_GEOMETRY")
            params["geometry"] = geometry
            if len(STATIC_URL) + 1 + len(urlencode(params)) > 2048:
                raise GeoapifyError("STATIC_GEOMETRY_URL_LIMIT")
        data, receipt = self._request(STATIC_URL, params, "image/png")
        receipt.update(
            attribution=list(ATTRIBUTION),
            viewport_status="REQUESTED_AREA_NOT_INDEPENDENTLY_VERIFIED",
            actual_bounds_wgs84=None,
            estimated_credits=round(1 + width * height / (256 * 256 * 4), 3),
        )
        try:
            actual_size = _png_dimensions(data)
        except GeoapifyError as error:
            raise GeoapifyError(error.code, receipt) from None
        receipt["actual_dimensions_px"] = list(actual_size)
        if receipt["content_type"] != "image/png" or actual_size != (width, height):
            raise GeoapifyError("VIEWPORT_DIMENSIONS_MISMATCH", receipt)
        return Result(data, receipt)

    def walk_route(self, start_lonlat, target_lonlat):
        start, target = _lonlat(start_lonlat), _lonlat(target_lonlat)
        if not 0 < _haversine(start, target) <= 5000:
            raise GeoapifyError("OUTSIDE_URBAN_ROUTE_DISTANCE_LIMIT")
        params = {
            "waypoints": "|".join("lonlat:" + ",".join(f"{v:.9f}" for v in point) for point in (start, target)),
            "mode": "walk",
            "type": "balanced",
            "units": "metric",
            "format": "geojson",
        }
        body, receipt = self._request(ROUTING_URL, params, "application/geo+json, application/json")
        receipt["estimated_credits"] = 1
        try:
            if receipt["content_type"] not in {"application/json", "application/geo+json"}:
                raise GeoapifyError("UNEXPECTED_ROUTING_CONTENT_TYPE")
            result = _route_result(json.loads(body), start, target)
        except GeoapifyError as error:
            raise GeoapifyError(error.code, receipt) from None
        except (UnicodeError, ValueError):
            raise GeoapifyError("INVALID_ROUTING_RESPONSE", receipt) from None
        return Result(result, receipt)

