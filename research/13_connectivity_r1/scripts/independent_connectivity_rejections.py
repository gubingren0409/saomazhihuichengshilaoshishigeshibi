"""Derive explicit negative-request expectations from raw IDs/tags, not statuses."""
import math
import re
from independent_connectivity_source import ROOT, RawGeometry, digest, read, write


def main():
    lock_path = ROOT / "data/formal_requests_lock.json"
    declared = [r for r in read(lock_path)["requests"] if r["role"] == "BASELINE_REJECTION"]
    combinations = {(r["request"]["request_id"], r["request"]["connectivity_mode"]): r for r in declared}
    manifest = {r["scene_id"]: r for r in read(ROOT / "data/scene_manifest.json")["scenes"]}
    sources, rows = {}, []
    raw_registry = (ROOT / "results/formal_registry.jsonl").read_bytes()
    complete = raw_registry[:raw_registry.rfind(b"\n") + 1]
    for line in complete.splitlines():
        registry = __import__("json").loads(line); request = registry["request"]
        ident = (request.get("request_id"), request.get("connectivity_mode"))
        if ident not in combinations:
            continue
        body_path = ROOT / registry["path"]; body = read(body_path)
        errors = []; sid = request["scene_id"]
        reason, expected, raw_evidence = None, None, {}
        if sid not in manifest:
            expected, reason = "INVALID_REQUEST", "Scene is not one of six acquired/frozen scene IDs"
        else:
            if sid not in sources:
                entry = manifest[sid]
                assert digest(ROOT / entry["source_path"]) == entry["source_sha256"]
                sources[sid] = RawGeometry(read(ROOT / entry["source_path"]))
            src = sources[sid]
            door_id = request.get("door_id", "")
            match = re.fullmatch(r"node/(\d+)", door_id)
            if not match:
                expected, reason = "NO_ELIGIBLE_REGISTERED_ENTRANCE", "No original native registered door ID is requested; no entrance may be generated"
                building = src.objects[("way", int(manifest[sid]["building_native_id"].split("/")[1]))]
                raw_evidence["building_raw_entrance_nodes"] = [n for n in building["nodes"] if src.objects[("node", n)].get("tags", {}).get("entrance")]
            else:
                raw_door = src.objects[("node", int(match.group(1)))]
                raw_evidence["original_door_tags"] = raw_door.get("tags", {})
                if request["purpose"] == "ENTER_BUILDING" and raw_door.get("tags", {}).get("entrance") == "exit":
                    expected, reason = "REJECTED_ENTRANCE_ROLE", "Original node remains entrance=exit; inbound request must be rejected"
                else:
                    start_match = re.fullmatch(r"node/(\d+)", request["start_id"])
                    if not start_match or ("node", int(start_match.group(1))) not in src.objects:
                        expected, reason = "INVALID_START", "Requested start is not an acquired original native node"
                    elif "start_xy" in request and (len(request["start_xy"]) != 2 or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in request["start_xy"])):
                        expected, reason = "INVALID_REQUEST", "Start coordinate values are not two finite numbers"
                        raw_evidence["original_start_xy"] = src.xy[int(start_match.group(1))]
        if expected is None:
            errors.append("NEGATIVE_NOT_DERIVED_BY_INDEPENDENT_RAW_RULE")
        if body.get("status") != expected or body.get("route") is not None or body.get("solver", {}).get("invoked"):
            errors.append("REFUSAL_STATUS_ROUTE_OR_SOLVER_CONTRADICTS_RAW_RULE")
        if body.get("input") != {**request, "run_purpose": "FORMAL_PRELOCKED_MATRIX"}:
            errors.append("FROZEN_NEGATIVE_REQUEST_ENVELOPE_CHANGED")
        if digest(body_path) != registry["result_sha256"]:
            errors.append("SAVED_NEGATIVE_RESPONSE_SHA")
        rows.append({"formal_attempt_id": registry["attempt_id"], "run_id": body["run_id"], "request_id": ident[0],
            "mode": ident[1], "independently_expected_status": expected, "actual_status": body.get("status"),
            "raw_rule": reason, "raw_evidence": raw_evidence, "response_sha256": digest(body_path), "errors": errors})
    observed = {(r["request_id"], r["mode"]) for r in rows}
    result = {"reviewer": "/root/connectivity_review", "scope": "Five explicit refusal classes at four modes, derived from raw frozen scene/native-node/door-role/coordinate requirements; no graph no-path proof",
        "APP_solver_calls": 0, "formal_lock_sha256": digest(lock_path), "complete_registry_snapshot_sha256": __import__("hashlib").sha256(complete).hexdigest(),
        "expected_unique_negative_combinations": len(combinations), "observed_unique_negative_combinations": len(observed),
        "saved_response_records_checked_including_replays": len(rows), "rows": rows,
        "status": "PASS_FOR_ALL_TWENTY_EXPLICIT_REFUSAL_COMBINATIONS" if observed == set(combinations) and all(not r["errors"] for r in rows) else "PARTIAL_EXPLICIT_REFUSAL_COMBINATIONS_CHECKED" if all(not r["errors"] for r in rows) else "REQUIRES_INSPECTION",
        "limits": ["Unknown or disconnected whole-network path failures are not proved impossible by this audit", "Repeated old/replay records are counted separately from the twenty unique prescribed combinations"]}
    write(ROOT / "audits/independent_explicit_rejections.json", result)
    print(__import__("json").dumps({k: result[k] for k in ("status", "observed_unique_negative_combinations", "saved_response_records_checked_including_replays")}))


if __name__ == "__main__":
    main()
