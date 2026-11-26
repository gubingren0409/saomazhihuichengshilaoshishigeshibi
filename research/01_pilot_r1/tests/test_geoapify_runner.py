"""First-scene orchestration with a mock client. No provider calls."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.geoapify import ATTRIBUTION, STATIC_STYLE, GeoapifyError, Result
from src.run_geoapify import AUDIT_PATH, IMAGE_DIR, RUN_PATH, SCENE_ID, SOURCE_LINKS, execute


class GeoapifyRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "runs").mkdir()
        views = {"width": 1200, "height": 900, "bounds": [121.46, 31.22, 121.48, 31.24]}
        spec = {"scene_id": SCENE_ID, "start": [121.47, 31.23], "target": [121.471, 31.231],
                "views": {"detail": views, "context": views}}
        (self.root / "runs" / "scene_contract.json").write_text(json.dumps(spec), encoding="utf-8")
        (self.root / AUDIT_PATH).write_text("\n".join(SOURCE_LINKS), encoding="utf-8")
        self.client = Mock()

    def test_missing_key_creates_only_not_run_receipt(self):
        with patch.dict(os.environ, {}, clear=True):
            state = execute(self.root)
        self.assertEqual("GEOAPIFY_KEY_MISSING", state["branch_status"])
        self.assertFalse((self.root / IMAGE_DIR).exists())
        self.assertEqual([], state["requests"])
        self.assertEqual(state, json.loads((self.root / RUN_PATH).read_text(encoding="utf-8")))

    def test_requests_once_and_never_promotes_unknown_bbox(self):
        self.client.walk_route.return_value = Result({"geojson": {"type": "FeatureCollection", "features": []}}, {})
        self.client.static_map.return_value = Result(b"MOCK_PNG", {
            "parameters": {"style": STATIC_STYLE, "attribution": "default"},
            "attribution": list(ATTRIBUTION),
            "actual_bounds_wgs84": None,
        })
        with patch("src.run_geoapify.Geoapify.from_env", return_value=self.client):
            state = execute(self.root, confirmed_free=True)
            with self.assertRaisesRegex(GeoapifyError, "FIRST_LIVE_ATTEMPT_ALREADY_RESERVED"):
                execute(self.root, confirmed_free=True)
        self.assertEqual(1, self.client.walk_route.call_count)
        self.assertEqual(2, self.client.static_map.call_count)
        self.assertEqual("VIEWPORT_NOT_VERIFIED", state["view_pair_status"])
        self.assertEqual("PENDING_VERIFIED_BOUNDS", state["route_on_provider_image"])
        self.assertEqual("LIVE_RESULTS_AWAITING_VIEWPORT_QA", state["branch_status"])
        self.assertEqual(3, state["saved_asset_count"])
        self.assertEqual(b"MOCK_PNG", (self.root / IMAGE_DIR / f"{SCENE_ID}_detail_base.png").read_bytes())

    def test_unauthorized_response_stops_other_requests(self):
        self.client.walk_route.side_effect = GeoapifyError("UPSTREAM_HTTP_401", {"status_code": 401})
        with patch("src.run_geoapify.Geoapify.from_env", return_value=self.client):
            state = execute(self.root, confirmed_free=True)
        self.assertEqual("LIVE_INCOMPLETE", state["branch_status"])
        self.assertEqual(0, state["saved_asset_count"])
        self.assertEqual(1, len(state["requests"]))
        self.client.static_map.assert_not_called()


if __name__ == "__main__":
    unittest.main()

