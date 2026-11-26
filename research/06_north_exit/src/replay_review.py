"""Replay from an actual fresh extraction, comparing published outputs by bytes."""
import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import subprocess
import sys

from seal_review import verify

OUTPUTS = ("runs/experiment.json", "data/route_variants.geojson", "data/constraints.geojson",
           "data/segment_evidence.csv", "data/obstacle_intersections.csv", "data/level_evidence.csv",
           "visuals/index.html")


def sha(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def replay(archive, work, receipt):
    if receipt.exists():
        raise FileExistsError("Replay receipt already exists")
    extracted = work / "extracted"
    reproduced = work / "reproduced"
    pack = verify(archive, extracted)
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    commands = [
        ["src/run_experiment.py", "--output-root", str(reproduced)],
        ["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        ["src/build_visuals.py", "--run-root", str(reproduced), "--output", str(reproduced / "visuals/index.html")],
    ]
    logs = []
    for args in commands:
        proc = subprocess.run([sys.executable, "-X", "utf8", "-B", *args], cwd=extracted, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, timeout=180)
        logs.append(dict(entry=args[0] if args[0] != "-m" else args[1],
                         output=proc.stdout.decode("utf-8", errors="replace")[-1200:]))
    same = {}
    for name in OUTPUTS:
        old, new = sha(extracted / name), sha(reproduced / name)
        if old != new:
            raise ValueError(f"Reproduced output differs: {name}")
        same[name] = old
    result = dict(status="PASS", archive=pack, reproduced_sha256=same, commands=logs,
                  external_requests=0, field_checks=0)
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zip", type=Path, required=True)
    p.add_argument("--work-root", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    result = replay(a.zip.resolve(), a.work_root.resolve(), a.receipt.resolve())
    print(json.dumps(dict(status=result["status"], archive=result["archive"],
                          identical_output_count=len(result["reproduced_sha256"])), ensure_ascii=False))
