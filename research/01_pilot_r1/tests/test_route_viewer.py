import json
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from route_viewer import write_viewer


def scene(image=None):
    return [{"scene_id": "FIXTURE", "label": "fixture </script> text",
             "viewports": {"detail": {"bounds": [121.1, 31.1, 121.2, 31.2], "image": image}},
             "routes": {"local": {"geometry": {"type": "LineString",
                                              "coordinates": [[121.1, 31.1], [121.2, 31.2]]}},
                        "geoapify": None}}]


def test_viewer_preserves_local_route_and_missing_provider(tmp_path):
    output = write_viewer(scene(), tmp_path / "index.html", tmp_path)
    html = output.read_text(encoding="utf-8")
    match = re.search(r'<script id="cases" type="application/json">(.*?)</script>', html)
    assert match
    payload = json.loads(match.group(1))[0]
    assert payload["label"] == "fixture </script> text"
    assert payload["routes"]["geoapify"] is None
    assert payload["routes"]["local"]["coordinates"] == [[121.1, 31.1], [121.2, 31.2]]
    assert "© OpenStreetMap contributors" in html


@pytest.mark.parametrize("invalid", ["https://example.invalid/map.png", "../forbidden.png", "map.png?apiKey=fixture"])
def test_image_paths_cannot_reference_network_or_leave_root(tmp_path, invalid):
    with pytest.raises(ValueError):
        write_viewer(scene(invalid), tmp_path / "index.html", tmp_path)



def test_failed_route_keeps_diagnostic_points_separate_from_line(tmp_path):
    data = scene()
    data[0]["routes"]["local"] = {
        "status": "NO_ROUTE", "geometry": None, "requested_start": [121.1, 31.1],
        "requested_target": [121.2, 31.2], "snap_end": {"position": [121.199, 31.2]},
    }
    output = write_viewer(data, tmp_path / "index.html", tmp_path)
    match = re.search(r'<script id="cases" type="application/json">(.*?)</script>', output.read_text(encoding="utf-8"))
    payload = json.loads(match.group(1))[0]
    assert payload["routes"]["local"] is None
    assert [f["properties"]["role"] for f in payload["diagnostics"]] == ["start", "target", "network_candidate"]
    assert all(f["geometry"]["type"] == "Point" for f in payload["diagnostics"])
