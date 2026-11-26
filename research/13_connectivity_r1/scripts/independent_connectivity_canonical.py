"""Verify 104 locked requests + all 16 prespecified replacements, then measure.

Original responses remain immutable; selection never uses route success or gain.
This driver only reads saved evidence and optionally calls the independent
geometry measurer. It never invokes an APP/route solver.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from independent_connectivity_source import ROOT, read, write, digest


def registry(path):
    raw = path.read_bytes(); complete = raw[:raw.rfind(b"\n") + 1]
    assert complete == raw, "REGISTRY_HAS_UNFINISHED_TRAILING_RECORD"
    return [json.loads(line) for line in complete.splitlines() if line.strip()], hashlib.sha256(complete).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()
    primary, primary_sha = registry(ROOT / "results/formal_registry.jsonl")
    replay, replay_sha = registry(ROOT / "results/formal_replay_registry.jsonl")
    lock_path = ROOT / "data/formal_requests_lock.json"
    replay_lock_path = ROOT / "data/performance_replay_lock.json"
    locked = {r["attempt_id"]: r for r in read(lock_path)["requests"]}
    locked_replays = {r["attempt_id"]: r for r in read(replay_lock_path)["entries"]}
    errors = []; bodies = {}; original = {}; replacements = {}
    for row in primary:
        if row["attempt_id"] in original:
            errors.append("DUPLICATE_PRIMARY_ATTEMPT:" + row["attempt_id"])
        original[row["attempt_id"]] = row
        if row["attempt_id"] not in locked or row["request"] != locked[row["attempt_id"]]["request"]:
            errors.append("PRIMARY_REQUEST_LOCK_MISMATCH:" + row["attempt_id"])
    for row in replay:
        supersedes = row["supersedes_attempt_id"]
        if supersedes in replacements:
            errors.append("DUPLICATE_REPLAY:" + supersedes)
        replacements[supersedes] = row
        if supersedes not in locked_replays or supersedes not in original:
            errors.append("UNLOCKED_REPLAY:" + supersedes); continue
        old = original[supersedes]; before = locked_replays[supersedes]
        if row["request"] != old["request"] or row["request"] != before["request"] or row["supersedes_response_sha256"] != old["result_sha256"] or old["result_sha256"] != before["result_sha256"]:
            errors.append("REPLAY_CHANGED_REQUEST_OR_ORIGINAL_HASH:" + supersedes)
        if row["run_id"] == old["run_id"] or row["path"] == old["path"]:
            errors.append("REPLAY_REUSED_OR_OVERWROTE_OLD_RUN:" + supersedes)
    frozen_code = read(ROOT / "audits/backend_freeze_r2.json")["code_sha256"]
    for name, rows, purpose in (("primary", primary, "FORMAL_PRELOCKED_MATRIX"), ("replay", replay, "FORMAL_PERFORMANCE_FIX_REPLAY")):
        for row in rows:
            path = ROOT / row["path"]; body = read(path); bodies[row["run_id"]] = body
            if digest(path) != row["result_sha256"] or body["run_id"] != row["run_id"] or body.get("input") != {**row["request"], "run_purpose": purpose}:
                errors.append("RAW_RESPONSE_SHA_OR_EXACT_ENVELOPE:" + row["attempt_id"])
            if body.get("route_answer_cache") != {"enabled": False, "hit": False} or bool(body.get("solver", {}).get("invoked")) != row["solver_invoked"]:
                errors.append("ANSWER_CACHE_OR_INVOCATION_RECORD:" + row["attempt_id"])
            if name == "replay" and body.get("solver", {}).get("invoked") and body.get("versions", {}).get("code_sha256") != frozen_code:
                errors.append("REPLAY_NOT_FROZEN_R2:" + row["attempt_id"])
    if set(original) != set(locked) or len(primary) != 104:
        errors.append("PRIMARY_NOT_EXACT_104_LOCKED_ATTEMPTS")
    if set(replacements) != set(locked_replays) or len(replay) != 16:
        errors.append("REPLAY_NOT_EXACT_16_PRELOCKED_AFFECTED_ATTEMPTS")
    canonical = [replacements.get(ident, original[ident]) for ident in sorted(locked) if ident in original]
    if any(row["request"]["connectivity_mode"] not in {"EXACT_STITCH", "CONDITIONAL_SEAMS"} for row in replay):
        errors.append("REPLAY_WIDENED_BEYOND_PRELOCKED_MODES")
    interrupted = sorted((ROOT / "results").glob("interrupted_formal_*.json"))
    actual = len(primary) + len(replay) + len(interrupted)
    if actual > 128 or actual != 121:
        errors.append("FORMAL_ACTUAL_COUNT_OR_CAP")
    all_solvers = [b["solver"]["invocation_id"] for b in bodies.values() if b.get("solver", {}).get("invoked")]
    if len(all_solvers) != len(set(all_solvers)):
        errors.append("SOLVER_INVOCATION_ID_REUSED")
    output = ROOT / "audits/independent_canonical_registry.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in canonical), encoding="utf-8")
    result = {"reviewer": "/root/connectivity_review", "scope": "Exact prelocked primary/replay selection and every raw response SHA/input/version; originals retained; no outcome-driven selection",
        "APP_solver_calls": 0, "primary_registry_sha256": primary_sha, "replay_registry_sha256": replay_sha,
        "formal_lock_sha256": digest(lock_path), "performance_replay_lock_sha256": digest(replay_lock_path),
        "primary_completed": len(primary), "prelocked_replays_completed": len(replay), "interrupted_actual_attempts": len(interrupted),
        "formal_actual_requests_including_interruption": actual, "formal_actual_solver_invocations": len(all_solvers), "formal_cap": 128,
        "independent_live_solver_calls_separate": 6, "independent_clean_calls_reserved_separate": 2,
        "canonical_requests": len(canonical), "canonical_solver_invocations": sum(row["solver_invoked"] for row in canonical),
        "canonical_role_counts": dict(Counter(row["role"] for row in canonical)), "canonical_status_counts": dict(Counter(row["status"] for row in canonical)),
        "canonical_registry": str(output.relative_to(ROOT)), "canonical_registry_sha256": digest(output), "errors": errors,
        "status": "PASS_FOR_LOCKED_104_PLUS_16_CANONICAL_SELECTION" if not errors else "REQUIRES_INSPECTION"}
    write(ROOT / "audits/independent_canonical_review.json", result)
    print(json.dumps({k: result[k] for k in ("status", "formal_actual_requests_including_interruption", "formal_actual_solver_invocations", "canonical_requests", "canonical_solver_invocations")}), flush=True)
    if args.measure:
        if errors:
            raise ValueError("CANONICAL_SELECTION_NOT_VERIFIED")
        report = ROOT / "audits/independent_canonical_response_measurement.json"
        command = [sys.executable, "-X", "utf8", "-B", str(ROOT / "scripts/independent_connectivity_responses.py"),
            *[str(ROOT / row["path"]) for row in canonical], "--output", str(report)]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=600)
        (ROOT / "audits/independent_canonical_measurement_log.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        print(completed.stdout, end="", flush=True)
        if completed.returncode or read(report)["status"] != "PASS_FOR_REPORTED_RESPONSE_SCOPE":
            raise ValueError("CANONICAL_GEOMETRY_MEASUREMENT_REQUIRES_INSPECTION")


if __name__ == "__main__":
    main()
