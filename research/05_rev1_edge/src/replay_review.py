"""Extract the fixed review ZIP, run the bundled experiment, and redraw offline."""
import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter
from zipfile import ZipFile

from .seal_review import manifest_check

VOLATILE = {"elapsed_s", "elapsed_seconds", "duration_s", "runtime_s", "runtime_seconds", "compute_seconds",
            "wall_time_s", "wall_seconds", "started_at", "finished_at", "created_at", "time_utc", "timestamp_utc",
            "input_root", "output_root", "run_root", "working_directory", "timings"}


def normalized(value):
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items() if key not in VOLATILE}
    return value


def checksum(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def call(root, args, limit=420):
    before = perf_counter()
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    proc = subprocess.run([sys.executable, "-X", "utf8", "-B", "-m", *args], cwd=root, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=limit, check=False)
    output = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode:
        raise RuntimeError(f"{args[0]} failed ({proc.returncode})\n{output[-6500:]}")
    return {"module": args[0], "exit_code": proc.returncode, "wall_seconds": round(perf_counter() - before, 3),
            "last_output": output[-1800:]}


def replay(archive, fresh, receipt_path, browser=True):
    if receipt_path.exists():
        raise FileExistsError(f"Replay receipt already exists: {receipt_path}")
    integrity = manifest_check(archive)
    fresh.mkdir(parents=True)
    restored = fresh / "unpacked"
    restored.mkdir()
    with ZipFile(archive) as z:
        for name in z.namelist():
            dest = restored.joinpath(*name.split("/"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as inp, dest.open("xb") as out:
                shutil.copyfileobj(inp, out)

    verification = []
    result_root = fresh / "rerun"
    verification.append(call(restored, ["src.run_rev1", "--input-root", str(restored / "frozen_r4"),
                                        "--output-root", str(result_root), "--config", str(restored / "config/rev1_main.json")]))
    diagnostics = ("data/native_prefix_diagnostic.json", "data/native_prefix_diagnostic.geojson",
                   "runs/edge_geometry_audit.json")
    if (restored / diagnostics[0]).is_file():
        verification.append(call(restored, ["src.audit_native_prefix", "--input-root", str(restored / "frozen_r4"),
                                            "--result-root", str(result_root), "--output-root", str(result_root)]))
    else:
        diagnostics = ()
    comparisons = {}
    required = ("data/source_manifest.json", "data/derived_edges.geojson", "data/edge_evidence.jsonl",
                "data/allowed_domains.geojson", "data/routes.geojson", "data/entrance_approach.json",
                "runs/experiment.json", *diagnostics)
    for rel in required:
        before, after = restored / rel, result_root / rel
        if checksum(before) == checksum(after):
            comparisons[rel] = "EXACT_SHA256"
            continue
        if before.suffix in {".geojson", ".json"}:
            a = normalized(json.loads(before.read_text(encoding="utf-8-sig")))
            b = normalized(json.loads(after.read_text(encoding="utf-8-sig")))
            if a == b:
                comparisons[rel] = "EXACT_SEMANTIC_EXCEPT_DECLARED_PATH_OR_TIMING_FIELDS"
                continue
        raise ValueError(f"Replay result differs: {rel}")

    verification.append(call(restored, ["pytest", "-q", "-p", "no:cacheprovider", "tests"], limit=180))
    verification.append(call(restored, ["src.report_rev1", "--root", str(result_root)], limit=30))
    visual_root = result_root / "visuals"
    visual_args = ["src.build_visuals", "--input-root", str(restored / "frozen_r4"),
                   "--run-root", str(result_root), "--output-root", str(visual_root)]
    verification.append(call(restored, visual_args + (["--browser"] if browser else []), limit=200))
    if not (visual_root / "index.html").is_file():
        raise ValueError("Rebuilt review page is missing")
    old_svgs = {path.relative_to(restored / "visuals").as_posix(): path
                for path in (restored / "visuals").rglob("*.svg")}
    new_svgs = {path.relative_to(visual_root).as_posix(): path for path in visual_root.rglob("*.svg")}
    if browser and (not old_svgs or old_svgs.keys() != new_svgs.keys()):
        raise ValueError("Regenerated SVG inventory differs")
    for name in old_svgs.keys() & new_svgs.keys():
        if checksum(old_svgs[name]) != checksum(new_svgs[name]):
            raise ValueError(f"Regenerated vector figure differs: {name}")
    receipt = {"status": "PASS", "identity": "ARCHIVE_EXTRACTION_AND_REAL_OFFLINE_REPLAY",
               "archive": integrity, "geometry_and_results": comparisons, "svg_exact_replay": len(new_svgs),
               "browser_requested": browser, "commands": verification,
               "scope": "Six-case experiment including three south routes, north gap, sensitivity, ablation and cross-case; tests and redrawn HTML",
               "provider_requests": 0, "field_checks": 0}
    with receipt_path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--zip", type=Path, required=True)
    cli.add_argument("--work-root", type=Path, required=True)
    cli.add_argument("--receipt", type=Path, required=True)
    cli.add_argument("--no-browser", action="store_true")
    options = cli.parse_args()
    print(json.dumps(replay(options.zip.resolve(), options.work_root.resolve(),
                            options.receipt.resolve(), not options.no_browser), ensure_ascii=False))
