"""Unpack a review ZIP safely and re-run the fixed experiments in a new output root."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from zipfile import ZipFile

from seal_review import inspect_member, check_nested, NESTED


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def execute(cwd, args, log, timeout=240):
    start = perf_counter()
    result = subprocess.run([sys.executable, "-X", "utf8", "-B", *args], cwd=cwd, check=True,
                            text=True, encoding="utf-8", capture_output=True, timeout=timeout)
    log.append(dict(args=args, seconds=round(perf_counter()-start, 3),
                    stdout=result.stdout.strip()[-2200:], returncode=result.returncode))


def assert_equal(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return abs(a-b) <= 1e-8
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(assert_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(assert_equal(x, y) for x, y in zip(a, b))
    return a == b


def main(archive, destination, browser, receipt):
    destination.mkdir(parents=True)
    root = destination / "extracted"
    root.mkdir()
    with ZipFile(archive) as z:
        if z.testzip() or sum(x.file_size for x in z.infolist()) > 1024**3:
            raise ValueError("Package CRC or size")
        manifest = json.loads(z.read("MANIFEST.json"))
        entries = {row["path"]: row for row in manifest["entries"]}
        names = z.namelist()
        if (len({n.casefold() for n in names}) != len(names) or len(entries) != len(manifest["entries"]) or
                set(names) != {*entries, "MANIFEST.json"}):
            raise ValueError("Duplicate or inconsistent members")
        for name, row in entries.items():
            content = z.read(name)
            inspect_member(name, content)
            if len(content) != row["bytes"] or sha256(content).hexdigest() != row["sha256"]:
                raise ValueError(f"Manifest mismatch {name}")
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as out:
                out.write(content)
    check_nested({name: root / name for name in NESTED})
    out = destination / "replayed"
    log, match = [], {}
    execute(root, ["scripts/materialize_inputs.py"], log)
    execute(root, ["-m", "src.run_semantics", "--output-root", str(out)], log)
    for method in ("natural", "masked"):
        execute(root, ["-m", "src.run_inference", method, "--output-root", str(out)], log)
    execute(root, ["src/evaluate_masking.py", "--predictions", str(out / "runs/masked_predictions.json"),
                   "--output", str(out / "runs/masking_evaluation.json"),
                   "--visual", str(out / "data/masking/review_cases.geojson")], log)
    execute(root, ["src/audit_natural.py", "--output", str(out / "independent_natural.json")], log)
    execute(root, ["-m", "pytest", "-q", "tests", "-p", "no:cacheprovider"], log)
    for file in ("data/semantics_edges.csv", "data/semantics_routes.geojson", "data/inference_candidates.csv",
                 "data/inference_candidates.geojson", "data/inference_routes.geojson",
                 "data/inference_context.geojson", "data/masking/review_cases.geojson"):
        match[file] = "BYTE_IDENTICAL" if (root / file).read_bytes() == (out / file).read_bytes() else "DIFFERENT"
    for file, omit in {"semantics": {"seconds"}, "inference": {"elapsed_seconds"},
                       "masked_predictions": {"elapsed_seconds"},
                       "masking_evaluation": {"prediction_sha256"}}.items():
        relative = f"runs/{file}.json"
        clean = lambda p: {k: v for k, v in read(p).items() if k not in omit}
        match[relative] = "SEMANTICALLY_IDENTICAL" if assert_equal(clean(root / relative), clean(out / relative)) else "DIFFERENT"
    relative = "audits/independent_natural.json"
    match[relative] = "SEMANTICALLY_IDENTICAL" if assert_equal(
        read(root / relative), read(out / "independent_natural.json")) else "DIFFERENT"
    # The renderer needs frozen inputs but consumes the newly produced outputs and references.
    import os
    import shutil
    visual_root = destination / "redrawn"
    visual_root.mkdir()
    for folder in ("data", "runs"):
        shutil.copytree(out / folder, visual_root / folder)
    # Only four frozen files are read by the renderer.
    for name in ("rev1/src/build_visuals.py", "rev1/frozen_r4/data/source/sh-huangpu-01.osm.json",
                 "rev1/frozen_r4/runs/source_open_spaces.json", "north/data/constraints.geojson"):
        src, dst = root / "inputs" / name, visual_root / "inputs" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.link(src, dst)
    execute(root, ["src/build_review.py", "--root", str(visual_root)], log)
    rel = "visuals/index.html"
    match[rel] = "BYTE_IDENTICAL" if (root / rel).read_bytes() == (visual_root / rel).read_bytes() else "DIFFERENT"
    if browser:
        execute(root, ["scripts/check_browser.py", "--root", str(visual_root), "--browser", browser,
                       "--figures", str(visual_root / "visuals/figures")], log)
        for path in sorted((visual_root / "visuals/figures").glob("*.svg")):
            rel = path.relative_to(visual_root).as_posix()
            match[rel] = "BYTE_IDENTICAL" if (root / rel).read_bytes() == path.read_bytes() else "DIFFERENT"
    evaluation = read(out / "runs/masking_evaluation.json")
    covered = {r["task_id"]: dict(recovered=r["controlled_recovery"], false_connection=r["negative_false_connection"],
                                 exposed=r["exposed_control_conflicts"])
               for r in evaluation["outcomes"] if r["method"]=="I2" and r["task_id"] in {"P-newworld-02", "N-newworld-02"}}
    assert covered["P-newworld-02"]["recovered"] and not covered["N-newworld-02"]["false_connection"]
    assert covered["N-newworld-02"]["exposed"] > 0
    status = "PASS" if "DIFFERENT" not in match.values() else "DIFFERENT"
    output = dict(status=status, archive_sha256=sha256(archive.read_bytes()).hexdigest(),
                  crc="PASS", contents="PATH_AND_SHA_AND_SENSITIVE_FILE_CHECKED", members=len(entries)+1,
                  replay_cases=covered, comparison=match, commands=log,
                  browser="ACTUALLY_REDRAWN" if browser else "NOT_RUN")
    if receipt:
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(output, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps(output, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--browser")
    p.add_argument("--receipt", type=Path)
    a = p.parse_args()
    raise SystemExit(main(a.archive.resolve(), a.destination.resolve(), a.browser, a.receipt))
