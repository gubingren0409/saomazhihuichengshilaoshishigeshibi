"""Final ZIP empty-directory replay, two predeclared fresh calls, own PID only.

Run only after the root's final-archive notification. The receipt is outside
the ZIP and binds its actual bytes; no original project/service is modified.
"""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OLD = [(244836, 53431), (178908, 53421)]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def file_sha(path):
    with Path(path).open("rb") as stream:
        value = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
        return value.hexdigest()


def http(url, body=None, timeout=10):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()


def old_snapshot():
    script = "$rows = @(Get-Process -Id 244836,178908 | ForEach-Object { [ordered]@{ pid = $_.Id; start_utc = $_.StartTime.ToUniversalTime().ToString('o'); executable = $_.Path } }); $rows | ConvertTo-Json -Compress"
    p = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    if p.returncode:
        raise RuntimeError("OLD_SERVICE_PROCESS_INSPECTION_FAILED:" + p.stderr)
    processes = json.loads(p.stdout)
    rows = []
    for pid, port in OLD:
        actual = next((r for r in processes if r["pid"] == pid), None)
        if actual is None:
            raise RuntimeError("OLD_SERVICE_PID_NOT_PRESENT:" + str(pid))
        status, content = http(f"http://127.0.0.1:{port}/")
        rows.append({**actual, "port": port, "http_status": status, "homepage_sha256": sha256(content).hexdigest(), "homepage_bytes": len(content)})
    return sorted(rows, key=lambda r: r["pid"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--request-plan", type=Path, default=ROOT / "audits/independent_live_request_plan.json")
    ap.add_argument("--min-tests", type=int, default=72)
    ap.add_argument("--work-root", type=Path, help="Optional existing-volume scratch parent for the unique empty unpack directory")
    ap.add_argument("--output", type=Path)
    a = ap.parse_args()
    archive = a.archive.resolve(); archive_sha = file_sha(archive)
    work_parent = (a.work_root or ROOT / "audits").resolve()
    work_parent.mkdir(parents=True, exist_ok=True)
    work = work_parent / ("independent_clean_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + archive_sha[:10] + "_" + uuid4().hex[:6])
    work.mkdir(parents=False, exist_ok=False)
    unpacked = work / "unpacked"; unpacked.mkdir(exist_ok=False)
    output = a.output or ROOT / "audits" / ("independent_final_replay_" + archive_sha[:12] + ".json")
    checks, responses = [], []
    service, service_url, own_stopped = None, None, False
    shipped = {}
    old_before = None
    started = time.perf_counter()
    result = {"reviewer": "/root/connectivity_review", "role": "INDEPENDENT_FINAL_EMPTY_DIRECTORY_ZIP_REPLAY", "archive": str(archive), "archive_sha256": archive_sha,
              "archive_bytes": archive.stat().st_size, "work_directory": str(work), "receipt_outside_archive": True, "checks": checks,
              "actual_new_independent_solver_invocations": 0, "new_route_POST_attempts": 0, "external_map_API_requests": 0,
              "request_plan_sha256": file_sha(a.request_plan), "script_sha256": file_sha(Path(__file__)), "user_observation": "PENDING_USER_OBSERVATION"}
    def record(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(name + ": " + ("PASS" if passed else "REQUIRES_INSPECTION"), flush=True)
    try:
        old_before = old_snapshot(); result["old_services_before"] = old_before
        with zipfile.ZipFile(archive) as z:
            info = z.infolist(); names = [r.filename for r in info]
            safe = len(names) == len(set(names))
            for member in info:
                p = PurePosixPath(member.filename)
                safe = safe and not p.is_absolute() and ".." not in p.parts and "\\" not in member.filename and ":" not in member.filename and ((member.external_attr >> 16) & 0o170000) != 0o120000
            if not safe:
                raise ValueError("UNSAFE_OR_DUPLICATE_ZIP_MEMBER")
            bad_crc = z.testzip()
            manifest_names = [name for name in ("MANIFEST.json", "MANIFEST_SHA256.json") if name in names]
            if len(manifest_names) != 1:
                raise ValueError("EXACTLY_ONE_DECLARED_MEMBER_MANIFEST_REQUIRED")
            manifest_name = manifest_names[0]
            manifest = json.loads(z.read(manifest_name))
            if manifest_name == "MANIFEST_SHA256.json" and manifest.get("schema") != "RELATIVE_MEMBER_SHA256_V1":
                raise ValueError("UNRECOGNIZED_FINAL_MEMBER_MANIFEST_SCHEMA")
            entries = manifest["files" if manifest_name == "MANIFEST_SHA256.json" else "entries"]
            files = {r.filename for r in info if not r.is_dir()}
            expected = {r["path"] for r in entries}
            errors = []
            if files != expected | {manifest_name} or len(entries) != len(expected):
                errors.append("EXACT_MANIFEST_MEMBER_SET")
            for entry in entries:
                data = z.read(entry["path"])
                if sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["bytes"]:
                    errors.append("MEMBER_HASH_OR_BYTES:" + entry["path"])
            for name in files:
                shipped[name] = sha256(z.read(name)).hexdigest()
            record("CRC_SAFE_PATH_EXACT_MANIFEST_ALL_MEMBER_HASHES", bad_crc is None and not errors,
                {"archive_entries": len(info), "regular_files": len(files), "manifest_name": manifest_name, "manifest_sha256": sha256(z.read(manifest_name)).hexdigest(), "manifest_entries": len(entries), "bad_crc": bad_crc, "errors": errors})
            if bad_crc or errors:
                raise ValueError("FINAL_ARCHIVE_CONTENT_VERIFICATION_FAILED")
            required = {"index.html", "app/index.html", "app/app.js", "app/app.css", "app/diagnosis.html", "app/diagnosis.js", "app/diagnostics.html", "app/diagnostics.js", "scripts/serve_app.py", "src/planner.py", "src/connectivity.py", "config/frozen_region.json", "data/scene_manifest.json"}
            missing = sorted(required - files)
            record("REQUIRED_APP_SERVER_SOURCE_AND_DIAGNOSIS_MEMBERS_PRESENT", not missing, {"required": sorted(required), "missing": missing})
            if missing:
                raise ValueError("MISSING_SHIPPED_APP_OR_SERVER_MEMBER")
            mutable_states = [name for name in files if name in {"runs/service.json", "runs/server_error.json", "runs/formal_latest.json"} or name.startswith("runs/progress/")]
            record("NO_SHIPPED_REPLACEABLE_SERVICE_OR_PROGRESS_STATE", not mutable_states, mutable_states)
            if mutable_states:
                raise ValueError("LIVE_RUNTIME_STATE_WOULD_BE_OVERWRITTEN_DURING_FRESH_REPLAY")
            z.extractall(unpacked)
        record("EXTRACTED_INTO_NEW_EMPTY_DIRECTORY", True, str(unpacked))
        env = dict(os.environ); env["PYTHONDONTWRITEBYTECODE"] = "1"
        cmd = [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]
        tested = subprocess.run(cmd, cwd=unpacked, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        text = tested.stdout + tested.stderr
        (work / "unittest_discover.txt").write_text(text, encoding="utf-8")
        count_match = re.search(r"Ran (\d+) tests?", text)
        count = int(count_match.group(1)) if count_match else 0
        passed = tested.returncode == 0 and count >= a.min_tests
        record("CLEAN_SHIPPED_TEST_SUITE_REAL_EXECUTION", passed, {"tests": count, "minimum": a.min_tests, "returncode": tested.returncode, "log": str(work / "unittest_discover.txt")})
        if not passed:
            raise ValueError("CLEAN_TEST_SUITE_FAILED")
        changed_by_tests = [name for name, expected in shipped.items() if not (unpacked / name).is_file() or file_sha(unpacked / name) != expected]
        record("SHIPPED_FILES_STILL_IMMUTABLE_BEFORE_ANY_NEW_POST", not changed_by_tests, changed_by_tests)
        if changed_by_tests:
            raise ValueError("TESTS_CHANGED_SHIPPED_INPUTS_BEFORE_ANY_ROUTE_REQUEST")
        plan = read(a.request_plan)
        fixed = plan["fixed_fields"]
        declarations = plan["final_clean_calls"]
        if len(declarations) != 2 or {r["method"] for r in declarations} != {"F0", "F1"}:
            raise ValueError("FINAL_REQUEST_PLAN_NOT_TWO_FIXED_METHODS")
        frozen_starts = set()
        for folder in (unpacked / "runs/app", unpacked / "runs/mechanisms"):
            for path in folder.glob("*.json"):
                body = read(path)
                if body.get("route"):
                    r = body.get("normalized_request", body.get("input", {}))
                    if r.get("scene_id") == fixed["scene_id"]:
                        frozen_starts.add(r.get("start_id"))
        if any(r["start_id"] in frozen_starts for r in declarations):
            raise ValueError("DECLARED_CLEAN_START_ALREADY_HAS_SHIPPED_ROUTE_ANSWER")
        logfile = (work / "temporary_service.log").open("w", encoding="utf-8")
        service = subprocess.Popen([sys.executable, "-X", "utf8", "-B", "scripts/serve_app.py", "--port", "0"], cwd=unpacked, env=env,
            stdout=logfile, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        state_path = unpacked / "runs/service.json"
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if service.poll() is not None:
                raise ValueError("CLEAN_TEMP_SERVICE_EXITED:" + str(service.returncode))
            if state_path.exists():
                try:
                    state = read(state_path)
                    if state.get("pid") == service.pid and state.get("running"):
                        service_url = state["url"]
                        break
                except (ValueError, json.JSONDecodeError):
                    pass
            time.sleep(.1)
        if not service_url:
            raise ValueError("NO_OWN_NEW_CLEAN_SERVICE_STATE")
        status, health = http(service_url + "api/health"); health = json.loads(health)
        is_own = health.get("pid") == service.pid and urlparse(service_url).hostname == "127.0.0.1" and urlparse(service_url).port not in {53431, 53421, 53441}
        record("NEW_TEMPORARY_LOOPBACK_SERVICE_OWN_PID", is_own, {"pid": service.pid, "url": service_url, "health": health})
        if not is_own:
            raise ValueError("CLEAN_REPLAY_MUST_NOT_REUSE_EXISTING_DEMO")
        asset_checks = []
        for route, member in [("", "app/index.html"), ("app.js", "app/app.js"), ("app.css", "app/app.css"), ("diagnosis", "app/diagnosis.html"), ("diagnosis.js", "app/diagnosis.js"), ("diagnostics", "app/diagnostics.html"), ("diagnostics.js", "app/diagnostics.js"), ("review", "index.html")]:
            asset_status, asset = http(service_url + route, timeout=30)
            asset_checks.append({"route": route or "/", "shipped_member": member, "http_status": asset_status, "sha256": sha256(asset).hexdigest(), "matches_shipped_member": sha256(asset).hexdigest() == shipped[member]})
        record("OWN_CLEAN_SERVICE_SERVES_REAL_APP_AND_DIAGNOSIS_BYTES", all(r["http_status"] == 200 and r["matches_shipped_member"] for r in asset_checks), asset_checks)
        if not all(r["http_status"] == 200 and r["matches_shipped_member"] for r in asset_checks):
            raise ValueError("CLEAN_APP_STATIC_ASSET_MISMATCH_BEFORE_ANY_NEW_POST")
        _, source = http(service_url + "api/scene?scene_id=" + fixed["scene_id"] + "&door_id=" + fixed["door_id"], timeout=180)
        source = json.loads(source)
        starts = {r["id"] for r in source["starts"]}
        if any(r["start_id"] not in starts for r in declarations):
            raise ValueError("DECLARED_NEW_NATIVE_START_NOT_IN_ACTUAL_CLEAN_CATALOG")
        for declared in declarations:
            request = {**fixed, **{k: declared[k] for k in ("start_id", "method", "connectivity_mode")}, "request_id": "INDEPENDENT-CLEAN-" + uuid4().hex}
            print("Sending predeclared fresh " + declared["method"] + " request to own clean PID", flush=True)
            result["new_route_POST_attempts"] += 1
            _, data = http(service_url + "api/plan", request, timeout=1200)
            body = json.loads(data)
            destination = work / ("fresh_" + declared["method"] + ".json")
            destination.write_bytes(data)
            result["actual_new_independent_solver_invocations"] += int(body.get("solver", {}).get("invoked", False))
            responses.append({"case_id": declared["case_id"], "path": str(destination), "sha256": file_sha(destination), "request": request,
                "run_id": body.get("run_id"), "status": body.get("status"), "solver": body.get("solver"), "graph": body.get("graph"), "body": body})
            record("FRESH_" + declared["method"] + "_REAL_UNCACHED_SOLVER", body.get("route") is not None and body.get("solver", {}).get("invoked") and body.get("route_answer_cache") == {"enabled": False, "hit": False} and body.get("input") == request,
                {"run_id": body.get("run_id"), "request_id": body.get("request_id"), "status": body.get("status"), "response_sha256": file_sha(destination)})
        command = [sys.executable, "-X", "utf8", "-B", str(unpacked / "scripts/independent_connectivity_responses.py"), *[r["path"] for r in responses],
                   "--root", str(unpacked), "--output", str(work / "independent_response_measurement.json")]
        measured = subprocess.run(command, cwd=unpacked, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        (work / "independent_measurement_log.txt").write_text(measured.stdout + measured.stderr, encoding="utf-8")
        review = read(work / "independent_response_measurement.json") if (work / "independent_response_measurement.json").exists() else {}
        record("INDEPENDENT_RAW_LENGTH_COST_ENDPOINT_PARENT_AND_OMEGA_REMEASUREMENT", measured.returncode == 0 and review.get("status") == "PASS_FOR_REPORTED_RESPONSE_SCOPE", {"report": str(work / "independent_response_measurement.json"), "status": review.get("status")})
        records = [r["body"] for r in responses]
        record("FIRST_CLEAN_B3_COLD_PREP_SECOND_METHOD_SHARED_WARM_PREP", len(records) == 2 and records[0].get("preprocessing_cache", {}).get("hit") is False and records[1].get("preprocessing_cache", {}).get("hit") is True and records[0]["preprocessing_cache"]["key"] == records[1]["preprocessing_cache"]["key"],
            [r.get("preprocessing_cache") for r in records])
        record("TWO_METHODS_SAME_UNWEIGHTED_GRAPH_DISTINCT_RUN_AND_SOLVER", len({r["graph"]["unweighted_sha256"] for r in records}) == 1 and len({r["run_id"] for r in records}) == 2 and len({r["solver"]["invocation_id"] for r in records}) == 2)
    except Exception as error:
        result["exception"] = repr(error)
        record("NO_UNRESOLVED_REPLAY_EXCEPTION", False, repr(error))
    finally:
        if service is not None:
            try:
                if service_url and service.poll() is None:
                    http(service_url + "api/stop", {"pid": service.pid})
                    service.wait(timeout=20)
                own_stopped = service.poll() is not None
            except Exception as error:
                result["temporary_stop_exception"] = repr(error)
                if service.poll() is None:
                    service.terminate(); service.wait(timeout=15)
                own_stopped = service.poll() is not None
            record("ONLY_NEW_TEMPORARY_SERVICE_STOPPED", own_stopped, {"pid": service.pid, "exit_code": service.poll()})
        changed = [name for name, expected in shipped.items() if not (unpacked / name).is_file() or file_sha(unpacked / name) != expected]
        record("ALL_ORIGINAL_SHIPPED_FILES_IMMUTABLE_AFTER_REPLAY", not changed, {"checked_members": len(shipped), "changed": changed})
        try:
            old_after = old_snapshot(); result["old_services_after"] = old_after
            record("OLD_SERVICE_PIDS_START_TIMES_AND_HOMEPAGES_UNCHANGED", old_before is not None and old_after == old_before)
        except Exception as error:
            record("OLD_SERVICE_PIDS_START_TIMES_AND_HOMEPAGES_UNCHANGED", False, repr(error))
        record("FINAL_ARCHIVE_BYTES_UNCHANGED", file_sha(archive) == archive_sha)
        result["fresh_responses"] = [{k: v for k, v in r.items() if k != "body"} for r in responses]
        result["elapsed_s"] = time.perf_counter() - started
        result["status"] = "PASS_FOR_FINAL_ZIP_CLEAN_REPLAY_SCOPE" if checks and all(r["passed"] for r in checks) and result["actual_new_independent_solver_invocations"] == 2 else "REQUIRES_INSPECTION"
        result["limits"] = ["Package replay and technical geometry checks are not user acceptance or field verification", "Full original research history need not be self-contained beyond the declared package", "New runtime files are permitted; every original shipped member is separately required unchanged"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": result["status"], "archive_sha256": archive_sha, "receipt": str(output), "new_independent_solver_calls": result["actual_new_independent_solver_invocations"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
