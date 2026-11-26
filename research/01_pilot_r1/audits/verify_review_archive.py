"""Verify the fixed OPEN_REVIEW archive and re-run its offline checks in isolation."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

PRIVATE_PARTS = {"runtime", "private_local", ".git", "__pycache__", ".pytest_cache", "delivery"}
PRIVATE_NAMES = {"07_blind_reveal_map_private.csv", "private_review.zip"}
PRIVATE_SUFFIXES = {".pbf", ".har", ".sqlite", ".lock", ".pyc", ".zip"}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def member_path(info):
    name = info.filename
    path = PurePosixPath(name)
    assert name == path.as_posix()
    assert not path.is_absolute() and ".." not in path.parts and "." not in path.parts
    assert not any(":" in part or "\\" in part or part.rstrip(". ") != part
                   or part.split(".", 1)[0].upper() in {"CON", "AUX", "PRN", "NUL", "COM1", "LPT1"}
                   for part in path.parts)
    assert not stat.S_ISLNK(info.external_attr >> 16) and not info.is_dir()
    lowered = set(part.lower() for part in path.parts)
    assert not lowered & PRIVATE_PARTS and path.name.lower() not in PRIVATE_NAMES
    assert path.suffix.lower() not in PRIVATE_SUFFIXES
    assert not any(part.startswith(".env") and part != ".env.example" for part in lowered)
    return path


def verify(archive, destination):
    with ZipFile(archive) as z:
        assert z.testzip() is None
        members = {}
        lowered = set()
        for info in z.infolist():
            path = member_path(info)
            assert info.file_size < 32 * 1024 * 1024
            assert path.as_posix().lower() not in lowered
            lowered.add(path.as_posix().lower())
            members[path.as_posix()] = info
        assert sum(info.file_size for info in members.values()) < 100 * 1024 * 1024
        manifest = "MANIFEST.json"
        entries = json.loads(z.read(manifest))["entries"]
        assert len(entries) == len(members) - 1
        assert {row["path"] for row in entries} == set(members) - {manifest}
        for row in entries:
            data = z.read(row["path"])
            assert len(data) == row["bytes"] and sha256(data).hexdigest() == row["sha256"]
        template = z.read(".env.example").decode("utf-8-sig")
        assert re.fullmatch(r"\s*GEOAPIFY_API_KEY\s*=\s*", template)
        assert not any(name.startswith("visuals/geoapify/") and
                       name.lower().endswith((".png", ".jpg", ".jpeg", ".geojson")) for name in members)
        # Only verified relative, non-link members are copied.
        for name in members:
            output = destination.joinpath(*PurePosixPath(name).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(z.read(name))
    return {"zip_sha256": digest(archive), "zip_bytes": archive.stat().st_size,
            "member_count": len(members), "manifest_entry_count": len(entries), "crc": "PASS",
            "private_files": "ABSENT", "empty_env_example": True}


def run_command(cmd, root, environment):
    result = subprocess.run([sys.executable, "-X", "utf8", "-B", *cmd], cwd=root, env=environment,
                            check=False, text=True, encoding="utf-8", capture_output=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for name in ("GEOAPIFY_API_KEY", "PYTHONPATH"):
        environment.pop(name, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    with TemporaryDirectory(dir=args.scratch) as temp:
        root = Path(temp)
        output = verify(args.archive, root)
        output["offline_tests"] = run_command(["-m", "pytest", "-q", "-p", "no:cacheprovider",
                                               "--basetemp", str(root / "pytest_runtime"), "tests"], root, environment)
        output["geometry_replay"] = run_command([
            "audits/independent_geometry.py", "--source", "data/sh-huangpu-01.osm.json",
            "--contract", "runs/scene_contract.json", "--route", "runs/local_route.json",
            "--geojson", "runs/local_route.geojson",
            "--diagnostic", "runs/local_approach_diagnostic.json",
            "--diagnostic-geojson", "runs/local_approach_diagnostic.geojson",
            "--qa", "runs/local_viewports.json", "--basemaps", "visuals/osm",
            "--out", "geometry_replay.json",
        ], root, environment)
        output["geometry_replay_report"] = json.loads((root / "geometry_replay.json").read_text(encoding="utf-8"))
        output["geometry_replay_report"].get("diagnostic", {}).pop("native_nodes_checked", None)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {output['member_count']} members and ran offline tests and geometry replay.")
    print(output["offline_tests"])


if __name__ == "__main__":
    main()
