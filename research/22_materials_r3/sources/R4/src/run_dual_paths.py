"""Execute the shared read-only diagnostic and the graph input gate on both adapters."""
import csv
from hashlib import sha256
import json
from pathlib import Path

from pyproj import Geod

from .prepare_ir import SCENES

ROOT = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")
STRUCTURE = ("open_space_geometry", "native_pedestrian_geometry",
             "native_node_topology", "obstacle_geometry")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def target_entry(bundle):
    request = next(row for row in bundle["route_requests"] if row["role"] == "TARGET_REQUEST")
    result = next(row for row in bundle["route_results"] if row["request_id"] == request["id"])
    reference = next(row for row in bundle["entrances"] if row["selected_for_request"])
    if reference["coordinate"] != request["target"]:
        raise ValueError("Route request/reference identity changed")
    return request, result, reference


def line_parts(geometry):
    if geometry is None:
        return []
    if geometry["type"] == "LineString":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiLineString":
        return geometry["coordinates"]
    raise ValueError("Invalid route geometry type")


def distance(left, right):
    return GEOD.inv(*left, *right)[2] if left is not None and right is not None else None


def diagnostics(request, result):
    parts = line_parts(result["geometry"])
    if not parts:
        return dict(line_available=False, route_length_m=None, start_offset_m=None,
                    target_gap_m=None, max_component_gap_m=None, geometry_end=None)
    length = sum(GEOD.line_length(*zip(*part)) for part in parts if len(part) >= 2)
    end = parts[-1][-1]
    if result["route_end"] != end:
        raise ValueError("Frozen route end does not match retained geometry")
    return dict(line_available=True, route_length_m=length,
                start_offset_m=distance(request["origin"], parts[0][0]),
                target_gap_m=distance(request["target"], end),
                max_component_gap_m=max((distance(a[-1], b[0]) for a, b in zip(parts, parts[1:])), default=0.0),
                geometry_end=end)


def run(root=ROOT):
    from .core import capability

    paired = []
    compact = []
    for scene in SCENES:
        bundles = {side: read(root / "data/ir" / f"{scene}.{side}.json") for side in ("local", "hosted")}
        local_request, _, local_ref = target_entry(bundles["local"])
        side_results = {}
        common_fields = dict.fromkeys(STRUCTURE, "UNKNOWN")
        for side, bundle in bundles.items():
            request, result, reference = target_entry(bundle)
            if (request["origin"] != local_request["origin"] or request["target"] != local_request["target"]
                    or reference["id"] != local_ref["id"] or reference["grade"] != local_ref["grade"]):
                raise ValueError(f"Non-comparable frozen task {scene}")
            gate = capability(common_fields)
            measured = diagnostics(request, result)
            native = {key: bundle["feature_availability"][key] for key in ("buildings", "pedestrian", "open_spaces")}
            entry = dict(source="FROZEN_SHARED_TASK", provider_native_identity="UNKNOWN",
                         id=reference["id"], grade=reference["grade"], coordinate=reference["coordinate"],
                         physical_validation=reference["physical_validation"])
            side_results[side] = dict(
                provider=bundle["scene"]["source"]["provider"], shared_request_origin=request["origin"],
                shared_request_target=request["target"], shared_reference=entry, route_state=result["status"],
                route_profile_observed=request["profile"], result_source=result["source"]["provider"],
                route_end_role=result["route_end_role"], provider_reported_m=result["distance"]["reported_m"],
                provider_snap=result["snap_target"]["status"], provider_native_features=native,
                provider_native_topology=bundle["topology_availability"],
                shared_core_gate=gate, shared_declared_fields=common_fields,
                **measured)
            compact.append(dict(scene_id=scene, side=side, route_state=result["status"],
                                target_reference_grade=reference["grade"],
                                graph_variant_status="NOT_EXECUTABLE_MISSING_INPUT",
                                route_length_m=measured["route_length_m"], target_gap_m=measured["target_gap_m"],
                                provider_topology=bundle["topology_availability"]))
        if side_results["local"]["shared_core_gate"] != side_results["hosted"]["shared_core_gate"]:
            raise ValueError("Unequal shared core parameters")
        paired.append(dict(scene_id=scene, same_frozen_task=True, comparison="COMMON_INPUT_READ_ONLY",
                           hosted_baseline="OBSERVED_FROZEN_PROVIDER_RESPONSE",
                           osm_augmented="RUNS_EXPERIMENT_JSON", **side_results))

    result = dict(contract="R3_IR_COMPATIBLE_R4_GRAPH_CAPABILITY", shared_auxiliary_osm_input=False,
                  graph_variants="NOT_EXECUTABLE_MISSING_INPUT", shared_diagnostic="RECOMPUTED_WGS84",
                  core_protocol_sha256=sha256((root / "runs/protocol_core.json").read_bytes()).hexdigest(),
                  new_geoapify_requests=0, scenes=paired)
    with (root / "data/dual_path_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(compact[0]))
        writer.writeheader()
        writer.writerows(compact)
    (root / "runs/dual_paths.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(dict(common_inputs_executed=len(result["scenes"]) * 2,
                          graph_variants=result["graph_variants"], new_geoapify_requests=0)))
