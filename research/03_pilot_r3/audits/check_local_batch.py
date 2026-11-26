"""Independent-formula author check of saved local route and camera artifacts."""
import json
from hashlib import file_digest
from pathlib import Path

from PIL import Image
from geographiclib.geodesic import Geodesic


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def distance(a, b):
    return Geodesic.WGS84.Inverse(a[1], a[0], b[1], b[0])["s12"]


def measure(route, ways):
    if not route:
        return None
    if route["status"] != "PASS":
        assert route["geometry"] is None
        return {"status": route["status"], "failure": route["failure_reason"], "has_geometry": False}
    coords = route["geometry"]["coordinates"]
    assert coords[0] == route["route_start"] and coords[-1] == route["route_end"]
    assert set(route["way_ids"]).issubset(ways)
    for seg in route["segments"]:
        source_way = seg.get("osm_way_id")
        if source_way is not None:
            index = seg["segment_index"]
            assert set(seg["osm_source_node_ids"]) == set(ways[source_way][index:index+2])
    length = sum(distance(a, b) for a, b in zip(coords, coords[1:]))
    assert abs(length - route["length_m"]) < .0001
    return {"status": "PASS", "length_recomputed_m": length, "vertices": len(coords),
            "source_ways": len(route["way_ids"]),
            "gap_to_own_request_target_m": distance(coords[-1], route["requested_target"])}


def verify(root):
    lock = root / "runs/scene_contracts.json"
    scenes = {x["scene_id"]: x for x in read(lock)["scenes"]}
    runs = read(root / "runs/local_results.json")
    assert runs["scene_contracts_sha256"] == sha(lock)
    assert set(scenes) == {x["scene_id"] for x in runs["scenes"]}
    rows = []
    for run in runs["scenes"]:
        scene = scenes[run["scene_id"]]
        info = {"scene_id": scene["scene_id"], "status": run["status"], "target_role": scene["target_role"]}
        rows.append(info)
        if not run.get("route"):
            continue
        clip = root / scene["osm_clip"]
        assert sha(clip) == scene["snapshot_sha256"]
        ways = {x["id"]: x["nodes"] for x in read(clip)["elements"] if x["type"] == "way"}
        assert run["route"]["requested_start"] == scene["start"] and run["route"]["requested_target"] == scene["target"]
        info.update(route=measure(run["route"], ways), diagnostic=measure(run["diagnostic"], ways),
                    scene_clip_sha_verified=True, views={})
        for name, view in run["views"].items():
            assert view["actual_bounds"] == scene["views"][name]["bounds"]
            for role in ("base", "route"):
                path = root / view[role]
                assert sha(path) == view[role + "_sha256"]
                with Image.open(path) as image:
                    assert image.size == (1200, 900) and image.format == "PNG"
                    image.verify()
            info["views"][name] = {"shape": [1200, 900], "bounds_verified": True,
                                   "both_image_hashes_verified": True, "route_pixels_present": view["overlay_drawn"]}
    return {"status": "PASS_AUTHOR_FORMULA_CHECK", "length_formula": "GeographicLib WGS84",
            "scenes": rows, "independent_review": "SEPARATE_ROLE_REQUIRED"}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    report = verify(root)
    (root / "audits/local_artifact_check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "scenes": len(report["scenes"])}))
