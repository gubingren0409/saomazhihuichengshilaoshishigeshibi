"""Safely unpack the completed A/B archive and rerun independent checks in isolation."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from verify_review_archive import member_path


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def verify_members(archive, target):
    with ZipFile(archive) as z:
        assert z.testzip() is None
        paths, names = {}, set()
        for info in z.infolist():
            path = member_path(info)
            name = path.as_posix()
            assert info.file_size < 32 * 1024 * 1024 and name.lower() not in names
            paths[name] = path
            names.add(name.lower())
        assert sum(i.file_size for i in z.infolist()) < 100 * 1024 * 1024
        manifest = "MANIFEST.json"
        rows = json.loads(z.read(manifest))["entries"]
        assert len(rows) == len(paths) - 1
        assert {row["path"] for row in rows} == set(paths) - {manifest}
        for row in rows:
            data = z.read(row["path"])
            assert len(data) == row["bytes"] and sha256(data).hexdigest() == row["sha256"]
        template = z.read(".env.example").decode("utf-8-sig")
        assert re.fullmatch(r"\s*GEOAPIFY_API_KEY\s*=\s*", template)
        for name, path in paths.items():
            local = target.joinpath(*path.parts)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(z.read(name))
    return {"member_count": len(paths), "manifest_entry_count": len(rows), "crc": "PASS",
            "zip_sha256": digest(archive), "zip_bytes": archive.stat().st_size, "private_files": "ABSENT",
            "empty_env_example": True}


def run_python(args, cwd, env, timeout=150):
    result = subprocess.run([sys.executable, "-X", "utf8", "-B", *args], cwd=cwd, env=env, text=True,
                            encoding="utf-8", capture_output=True, timeout=timeout, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--viewer", action="store_true")
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in ("GEOAPIFY_API_KEY", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    with TemporaryDirectory(dir=args.scratch) as temp:
        extracted = Path(temp)
        report = verify_members(args.archive, extracted)
        commands = ["audits/independent_geoapify.py", "--root", ".", "--out", "independent_hosted.json"]
        if args.browser:
            commands.append("--browser")
        if args.viewer:
            commands.append("--viewer")
        report["independent_artifact_verification"] = run_python(commands, extracted, env)
        report["hosted_and_gallery"] = json.loads((extracted / "independent_hosted.json").read_text(encoding="utf-8"))
        report["offline_tests"] = run_python(["-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp",
                                              str(extracted / "test_scratch"), "tests"], extracted, env)
        report["sealed_archive_modified"] = False
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {report['member_count']} safe archive members and completed hosted artifact checks.")
    print(report["offline_tests"])


if __name__ == "__main__":
    main()
