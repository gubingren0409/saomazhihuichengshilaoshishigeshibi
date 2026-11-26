"""Recheck sealed inference receipts and optionally sample replay resource use."""
from collections import Counter
from hashlib import file_digest
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter, sleep

from shapely import get_coordinates
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform

from inputs.rev1.src.native_adapter import Source, PROJECT
from src.inference import INFERRED, NATIVE, run_observed

ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-5


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def frozen_derived(root, used):
    found = {}
    with (root / "inputs/rev1/data/edge_evidence.jsonl").open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["scene_id"] != "sh-huangpu-01":
                break
            if row["edge_id"] in used:
                found[row["edge_id"]] = row
    return found


def recorded_segment(line, edge, source, derived):
    if edge["kind"] == NATIVE:
        way = source.obj(edge["source_id"])
        i = edge["segment_index"]
        a, b = (source.projected[n] for n in way["nodes"][i:i + 2])
    else:
        row = derived[edge["id"]]
        assert row["source_area_id"] == edge["source_id"], edge["id"]
        a, b = row["coordinates_metric"]
    if math.dist(a, b) <= EPS:
        assert line.length <= EPS, edge["id"]
    else:
        assert LineString([a, b]).buffer(EPS).covers(line), edge["id"]


def route_checks(root):
    doc = read(root / "runs/inference.json")
    for row in doc["read_log"]:
        path = root / row["path"]
        assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], path
    source = Source(read(root / "inputs/rev1/frozen_r4/data/source/sh-huangpu-01.osm.json"))
    door_id = doc["target"]["id"]
    door_coords = source.coord(door_id)
    door_xy = Point(PROJECT(*door_coords))
    assert tuple(doc["target"]["wgs84"]) == door_coords
    assert source.nodes[int(door_id.split("/")[1])]["tags"]["entrance"] == "exit"
    assert doc["target"]["tags"]["entrance"] == "exit"
    derived = frozen_derived(root, {e["id"] for method in doc["methods"].values()
                              for e in method["route"]["edges"]
                              if e["kind"] not in {NATIVE, INFERRED}})
    masks = [(r["properties"]["source_id"], transform(PROJECT, shape(r["geometry"])))
             for r in read(root / "data/inference_context.geojson")["features"]
             if r["properties"]["role"] in {"hard", "background"}]
    result = {}
    for variant, method in doc["methods"].items():
        route = method["route"]
        edges = route["edges"]
        assert edges[0]["u"] == doc["origin_native_id"]
        assert tuple(edges[0]["wgs84"][0]) == source.coord(doc["origin_native_id"])
        assert method["entrance_role"] == "exit" and method["inbound_eligibility"] == "NOT_ELIGIBLE_EXIT"
        for a, b in zip(edges, edges[1:]):
            assert a["v"] == b["u"] and a["xy"][-1] == b["xy"][0]
        actual = Counter()
        hypotheses = []
        for edge in edges:
            line = LineString(edge["xy"])
            assert math.isclose(edge["length_m"], line.length, abs_tol=EPS)
            actual[edge["kind"]] += line.length
            if edge["kind"] == INFERRED:
                assert edge["hypothesis"] and edge["v"] == door_id
                assert tuple(edge["wgs84"][-1]) == door_coords
                assert edge["xy"][-1] == doc["target"]["xy"]
                for source_id, mask in masks:
                    contact = line.intersection(mask)
                    if source_id == doc["target"]["building_id"]:
                        assert all(door_xy.distance(Point(xy)) <= EPS for xy in get_coordinates(contact)), edge["id"]
                    else:
                        assert contact.is_empty, (edge["id"], source_id)
                hypotheses.append(edge["id"])
            else:
                recorded_segment(line, edge, source, derived)
        assert math.isclose(sum(actual.values()), route["length_m"], abs_tol=EPS)
        assert math.isclose(sum(e["cost_m"] for e in edges), route["cost_m"], abs_tol=EPS)
        assert hypotheses == route["inferred_edges_used"]
        selected = [c for c in method["candidates"] if c["route_selected"]]
        assert {f"inferred/{c['id']}" for c in selected} == set(hypotheses)
        assert not hypotheses or all(c["grade_status"] == "UNOBSERVED_CONTINUOUS_LEVEL" for c in selected)
        if method["reached_original_target"]:
            assert edges[-1]["v"] == door_id and tuple(route["end_wgs84"]) == door_coords
        else:
            assert math.isclose(Point(edges[-1]["xy"][-1]).distance(door_xy), method["residual_m"],
                                abs_tol=EPS)
        result[variant] = dict(route_edges=len(edges), selected_inferred_edges=hypotheses,
                               edge_length_metres_by_kind=dict(actual), graph=method["graph"])
    return result


def opaque_id_check(root):
    receipt = read(root / "runs/masked_predictions.json")
    predictions = {r["task_id"]: r for r in receipt["predictions"]}
    for i, row in enumerate(receipt["read_log"]):
        path = root / "data/masking" / row["path"]
        assert path.is_file() and digest(path) == row["sha256"]
        observation = read(path)
        fixed = predictions[observation["task_id"]]
        observation["task_id"] = f"opaque/{i}"
        variant = run_observed(observation, receipt["active_configuration"], methods=tuple(fixed["methods"]))
        variant["task_id"] = fixed["task_id"]
        assert json.loads(json.dumps(variant, allow_nan=False)) == fixed, row["task_id"]
    return len(predictions)


def replay_profile(root, output):
    import psutil

    output.mkdir(parents=True, exist_ok=False)
    profiles = {}
    for mode in ("natural", "masked"):
        command = [sys.executable, "-X", "utf8", "-B", "-m", "src.run_inference", mode,
                   "--output-root", str(output)]
        begin = perf_counter()
        proc = subprocess.Popen(command, cwd=root)
        observed = psutil.Process(proc.pid)
        peak_bytes = 0
        while proc.poll() is None:
            try:
                mem = observed.memory_info()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            peak_bytes = max(peak_bytes, getattr(mem, "peak_wset", mem.rss))
            sleep(0.1)
        if proc.wait(timeout=10) != 0:
            raise RuntimeError(f"Replay failed for {mode}")
        profiles[mode] = dict(elapsed_seconds=round(perf_counter() - begin, 3),
                              sampled_peak_working_set_bytes=peak_bytes,
                              sample_interval_seconds=0.1)
    for name in ("runs/inference.json", "runs/masked_predictions.json"):
        before, after = read(root / name), read(output / name)
        del before["elapsed_seconds"], after["elapsed_seconds"]
        assert before == after, name
    for name in ("inference_candidates.geojson", "inference_candidates.csv", "inference_routes.geojson",
                 "inference_context.geojson"):
        assert digest(root / "data" / name) == digest(output / "data" / name), name
    return profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "reviews/inference_author_check.json")
    parser.add_argument("--profile-dir", type=Path)
    args = parser.parse_args()
    output = dict(status="AUTHOR_CHECK_REPRODUCED", fixed_north_route_checks=route_checks(args.root),
                  opaque_id_invariant_observations=opaque_id_check(args.root),
                  opaque_id_note="P/N roles in the frozen filenames do not alter any of the computed outcomes",
                  field_validation="NOT_VERIFIED", external_requests=0)
    if args.profile_dir:
        output["profile"] = replay_profile(args.root, args.profile_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps(dict(status=output["status"], opaque_id_checks=output["opaque_id_invariant_observations"],
                         checked_variants=list(output["fixed_north_route_checks"]), profile=output.get("profile"))))


if __name__ == "__main__":
    main()
