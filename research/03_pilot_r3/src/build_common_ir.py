"""Produce replayable R3 adapter bundles from retained artifacts, with no network."""
import argparse
import hashlib
import json
from pathlib import Path

from .common_ir import adapt_geoapify, adapt_osm, comparable_route_subset, validate

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def reference(scope, root, path):
    relative = path.resolve().relative_to(root.resolve())
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"scope": scope, "path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": digest}


def retained(root, relative):
    if not isinstance(relative, str):
        return None
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("SOURCE_REFERENCE_OUTSIDE_ARTIFACT_ROOT")
    return path if path.is_file() else None


def image_refs(scope, root, views):
    refs = []
    for view in (views or {}).values():
        for field in ("base", "route", "overlay"):
            path = retained(root, view.get(field))
            if path:
                ref = reference(scope, root, path)
                expected = view.get(field + "_sha256")
                if expected and ref["sha256"] != expected:
                    raise ValueError("RETAINED_PNG_SHA_MISMATCH")
                refs.append(ref)
            elif view.get(field):
                raise ValueError("RETAINED_VIEW_FILE_MISSING")
    return refs


def frozen_r1(r1):
    def read(relative):
        return read_json(r1 / relative)
    scene_path = "runs/scene_contract.json"
    snapshot_path = "data/sh-huangpu-01.osm.json"
    local_path = "runs/local_route.json"
    diag_path = "runs/local_approach_diagnostic.json"
    local_views_path = "runs/local_viewports.json"
    probe_path = "runs/geoapify_walk_probe_proxy.json"
    hosted_views_path = "runs/geoapify_static_completion.json"
    scene = read(scene_path)
    local = {"route": read(local_path), "diagnostic": read(diag_path)}
    probe = read(probe_path)
    geo_path = probe["geojson"]["path"]
    frozen = reference("R1", r1, r1 / snapshot_path)
    geo_ref = reference("R1", r1, r1 / geo_path)
    scene_ref = reference("R1", r1, r1 / scene_path)
    if (frozen["sha256"] != scene["snapshot_sha256"] or
            geo_ref["sha256"] != probe["geojson"]["sha256"] or
            scene_ref["sha256"] != probe["scene_contract_sha256"]):
        raise ValueError("R1_RETAINED_EVIDENCE_SHA_MISMATCH")
    local_views = read(local_views_path)["views"]
    hosted_views = read(hosted_views_path)["views"]
    local_refs = [scene_ref, frozen, *[reference("R1", r1, r1 / p) for p in
                 (local_path, diag_path, local_views_path)], *image_refs("R1", r1, local_views)]
    hosted_refs = [scene_ref, geo_ref, *[reference("R1", r1, r1 / p) for p in
                  (probe_path, hosted_views_path)], *image_refs("R1", r1, hosted_views)]
    hosted = {"route": {**probe["route"], "status": probe["status"], "receipt": probe["receipt"],
                        "geometry_length_metric": "R1_SPHERICAL_RECOMPUTATION"}}
    return (adapt_osm(scene, read(snapshot_path), local, local_refs, frozen, actual_views=local_views),
            adapt_geoapify(scene, hosted, read(geo_path), hosted_refs, actual_views=hosted_views))


def index(root, filename):
    path = retained(root, filename)
    if not path:
        return {}, None
    payload = read_json(path)
    return {row["scene_id"]: row for row in payload["scenes"]}, reference("R3", root, path)


def r3_pairs(root):
    path = retained(root, "runs/scene_contracts.json")
    if not path:
        return
    contract = read_json(path)
    scene_ref = reference("R3", root, path)
    local_index, local_ref = index(root, "runs/local_results.json")
    hosted_index, hosted_ref = index(root, "runs/hosted_results.json")
    for scene in contract["scenes"]:
        id_ = scene["scene_id"]
        if id_ == "sh-huangpu-01" and scene.get("role") == "CALIBRATION_ONLY":
            continue
        local = local_index.get(id_, {})
        hosted = hosted_index.get(id_, {})
        snapshot_path = retained(root, scene.get("osm_clip"))
        frozen = reference("R3", root, snapshot_path) if snapshot_path else None
        if frozen and scene.get("snapshot_sha256") and frozen["sha256"] != scene["snapshot_sha256"]:
            raise ValueError("R3_FROZEN_OSM_SHA_MISMATCH")
        local_refs = [r for r in [scene_ref, local_ref, frozen] if r] + image_refs("R3", root, local.get("views"))
        route_record = hosted.get("route") or {}
        geometry_path = retained(root, route_record.get("geometry_path"))
        raw_path = retained(root, route_record.get("raw_response_path"))
        hosted_refs = [r for r in [scene_ref, hosted_ref] if r] + image_refs("R3", root, hosted.get("views"))
        for asset, hash_field in ((geometry_path, "geometry_sha256"), (raw_path, "raw_response_sha256")):
            if asset:
                ref = reference("R3", root, asset)
                if route_record.get(hash_field) and ref["sha256"] != route_record[hash_field]:
                    raise ValueError("R3_HOSTED_RESPONSE_SHA_MISMATCH")
                hosted_refs.append(ref)
        yield (adapt_osm(scene, read_json(snapshot_path) if snapshot_path else None, local, local_refs,
                         frozen, actual_views=local.get("views")),
               adapt_geoapify(scene, hosted, read_json(geometry_path) if geometry_path else None,
                               hosted_refs, actual_views=hosted.get("views")))


def write(path, obj):
    data = (json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    temp = path.with_suffix(".tmp")
    temp.write_bytes(data)
    temp.replace(path)
    return {"path": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build(r1, r3, *, r1_only=False):
    if r1.resolve() == r3.resolve():
        raise ValueError("R1_CANNOT_BE_OUTPUT_ROOT")
    out = r3 / "runs/common_ir"
    out.mkdir(parents=True, exist_ok=True)
    pairs = [frozen_r1(r1)]
    if not r1_only:
        pairs.extend(r3_pairs(r3))
    summary = {"schema": "schema/common_ir.schema.json", "scenes": []}
    for local, hosted in pairs:
        local, hosted = validate(local), validate(hosted)
        id_ = local["scene"]["scene_id"]
        if any(row["scene_id"] == id_ for row in summary["scenes"]):
            raise ValueError("DUPLICATE_SCENE_ID")
        summary["scenes"].append({
            **comparable_route_subset(local, hosted),
            "evidence": "HISTORICAL_R1_REPLAY" if id_ == "sh-huangpu-01" else "R3_RETAINED_ARTIFACTS",
            "local_feature_counts": {k: len(v) for k, v in local["features"].items()},
            "hosted_feature_availability": hosted["feature_availability"],
            "local_ir": write(out / f"{id_}.local.json", local),
            "hosted_ir": write(out / f"{id_}.hosted.json", hosted),
        })
    write(out / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--r3", type=Path, default=ROOT)
    parser.add_argument("--r1", type=Path)
    parser.add_argument("--r1-only", action="store_true")
    args = parser.parse_args()
    r1 = args.r1 or args.r3 / "inputs/r1"
    report = build(r1, args.r3, r1_only=args.r1_only)
    print(json.dumps({"scenes": [{"scene_id": s["scene_id"],
                                "same_request": s["same_request_coordinates_and_mode"],
                                "local_route": s["local_target_route_status"],
                                "hosted_route": s["hosted_target_route_status"],
                                "local_features": s["local_feature_counts"]} for s in report["scenes"]]},
                     ensure_ascii=False))
