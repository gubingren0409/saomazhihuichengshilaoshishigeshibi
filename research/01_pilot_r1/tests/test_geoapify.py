"""Unit fixtures only. No HTTP requests or authentic images."""

from email.message import Message
import json
import os
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from zlib import compress, crc32

from src.geoapify import Geoapify, GeoapifyError, NoRedirect, credential_status


KEY = "fictional_mock_key_01234"
START = (121.47, 31.23)
TARGET = (121.471, 31.231)
BOUNDS = (121.46, 31.22, 121.48, 31.24)


def response(body, content_type):
    headers = Message()
    headers["Content-Type"] = content_type
    mock = Mock(headers=headers, status=200)
    mock.read.return_value = body
    holder = Mock()
    holder.__enter__ = Mock(return_value=mock)
    holder.__exit__ = Mock(return_value=False)
    return holder


def mock_route(coordinates, **overrides):
    return json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"distance": 190, "time": 120, "distance_units": "meters", **overrides},
            "geometry": {"type": "MultiLineString", "coordinates": coordinates},
        }],
    }).encode()


class GeoapifyTests(unittest.TestCase):
    def client(self, body, content_type):
        opener = Mock()
        opener.open.return_value = response(body, content_type)
        return Geoapify(KEY, confirmed_free=True, opener=opener), opener

    def test_only_explicit_free_use_and_exact_project_credentials(self):
        with self.assertRaisesRegex(GeoapifyError, "ZERO_COST_QUOTA_NOT_CONFIRMED"):
            Geoapify(KEY, confirmed_free=False)
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp, patch.dict(os.environ, {}, clear=True):
            root = Path(temp)
            self.assertEqual("MISSING", credential_status(root))
            (root / ".env").write_text("GEOAPIFY_API_KEY=\n", encoding="utf-8")
            self.assertEqual("MISSING", credential_status(root))
            (root / ".env").write_text("GEOAPIFY_API_KEY=" + KEY + "\n", encoding="utf-8")
            self.assertEqual("PRESENT", credential_status(root))
            self.assertNotIn(KEY, repr(Geoapify.from_env(root, confirmed_free=True)))

    def test_static_sends_header_and_preserves_native_png(self):
        def chunk(kind, payload):
            return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc32(kind + payload))

        header = struct.pack(">IIBBBBB", 1200, 900, 8, 0, 0, 0, 0)
        image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                 + chunk(b"IDAT", compress(bytes(1201 * 900))) + chunk(b"IEND", b""))
        client, opener = self.client(image, "image/png")
        result = client.static_map(BOUNDS)
        self.assertEqual(image, result.data)
        self.assertEqual([1200, 900], result.receipt["actual_dimensions_px"])
        self.assertIsNone(result.receipt["actual_bounds_wgs84"])
        self.assertIsNone(result.receipt["actual_credits"])
        request = opener.open.call_args.args[0]
        params = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(["rect:121.460000000,31.220000000,121.480000000,31.240000000"], params["area"])
        self.assertEqual(["default"], params["attribution"])
        self.assertEqual(KEY, dict((k.lower(), v) for k, v in request.header_items())["x-api-key"])
        self.assertNotIn(KEY, request.full_url)
        self.assertNotIn(KEY, repr(result))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, None, "https://elsewhere.invalid"))

    def test_walk_keeps_segments_and_lonlat(self):
        lines = [
            [START, (121.4703, 31.2303)],
            [(121.4705, 31.2305), TARGET],
        ]
        client, opener = self.client(mock_route(lines), "application/geo+json")
        result = client.walk_route(START, TARGET)
        features = result.data["geojson"]["features"]
        self.assertEqual(2, len(features))
        self.assertEqual([list(p) for p in lines[1]], features[1]["geometry"]["coordinates"])
        self.assertGreater(result.data["segment_gaps_m"][0], 1)
        self.assertEqual(list(TARGET), result.data["route_endpoint_wgs84"])
        self.assertEqual("UNKNOWN", result.data["entrance_identity"])
        params = parse_qs(urlsplit(opener.open.call_args.args[0].full_url).query)
        self.assertEqual(["walk"], params["mode"])
        self.assertEqual(["lonlat:121.470000000,31.230000000|lonlat:121.471000000,31.231000000"], params["waypoints"])

    def test_failure_receipt_uses_status_only(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("https://test.invalid/" + KEY, 401, KEY, {}, None)
        client = Geoapify(KEY, confirmed_free=True, opener=opener)
        with self.assertRaises(GeoapifyError) as error:
            client.static_map(BOUNDS)
        self.assertEqual("UPSTREAM_HTTP_401", str(error.exception))
        self.assertEqual(401, error.exception.receipt["status_code"])
        self.assertNotIn(KEY, json.dumps(error.exception.receipt))

    def test_malformed_units_and_secret_echo_fail_closed(self):
        client, _ = self.client(mock_route([[START, TARGET]], distance_units=1), "application/json")
        with self.assertRaisesRegex(GeoapifyError, "UNEXPECTED_ROUTING_UNITS"):
            client.walk_route(START, TARGET)
        client, _ = self.client(KEY.encode(), "application/json")
        with self.assertRaisesRegex(GeoapifyError, "UNSAFE_RESPONSE_BODY"):
            client.walk_route(START, TARGET)

    def test_single_request_budget_does_not_spend_on_rejected_request(self):
        client, opener = self.client(mock_route([[START, TARGET]]), "application/geo+json")
        with patch("src.geoapify.MAX_REQUESTS", 1):
            client.walk_route(START, TARGET)
            with self.assertRaises(GeoapifyError) as error:
                client.walk_route(START, TARGET)
        self.assertEqual("PILOT_REQUEST_LIMIT", error.exception.code)
        self.assertEqual("NOT_REQUESTED", error.exception.receipt["execution"])
        self.assertEqual(1, opener.open.call_count)

    def test_malformed_png_and_non_urban_request_are_rejected(self):
        client, opener = self.client(b"not a png", "image/png")
        with self.assertRaisesRegex(GeoapifyError, "INVALID_PNG"):
            client.static_map(BOUNDS)
        with self.assertRaisesRegex(GeoapifyError, "OUTSIDE_URBAN_ROUTE_DISTANCE_LIMIT"):
            client.walk_route(START, (0, 0))
        self.assertEqual(1, opener.open.call_count)


if __name__ == "__main__":
    unittest.main()

