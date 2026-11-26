"""Seal only the approved pilot code, ODbL clip, images and review records."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from .geoapify import read_api_key

ROOT = Path(__file__).resolve().parents[1]
TOP = (".env.example", ".gitignore", "README.md", "STATUS.json", "requirements.txt",
       "01_SOURCE_AND_PERMISSION_AUDIT.md", "02_SAMPLE_AND_VIEWPORT_CONTRACT.md",
       "03_API_AND_RENDER_IMPLEMENTATION.md", "04_EXPERIMENT_RESULTS.md",
       "05_HUMAN_REVIEW_GUIDE.md", "06_USER_SCORE_SHEET.csv", "08_DECISION_AND_NEXT_STEPS.md")
RUNTIME_DIRS = ("src", "tests", "runs", "audits", "data", "visuals/blind_review", "visuals/osm",
                "visuals/route_comparisons", "visuals/revealed", "visuals/failure_cases")
FILE_TYPES = {".py", ".json", ".geojson", ".md", ".csv", ".html", ".js", ".css", ".png", ".txt"}


def entries(root):
    yield from (root / name for name in TOP)
    for group in RUNTIME_DIRS:
        for path in sorted((root / group).rglob("*")):
            relative = path.relative_to(root)
            if path.is_file() and path.suffix.lower() in FILE_TYPES and all(not part.startswith(".") for part in relative.parts):
                yield path


def completed_assets(root):
    completion = json.loads((root / "runs/geoapify_static_completion.json").read_text(encoding="utf-8"))
    if (completion["status"] != "READY_FOR_USER_VISUAL_REVIEW"
            or set(completion["views"]) != {"detail", "context"}):
        raise ValueError("AB_COMPLETION_NOT_VERIFIED")
    assets = [(completion["route_geojson"]["path"], completion["route_geojson"]["sha256"])]
    for view in completion["views"].values():
        if not all(view.get(k) is True for k in ("bounds_match", "human_display_verified", "local_retention_verified")):
            raise ValueError("HOSTED_ASSET_NOT_ADMITTED")
        assets.extend((view[k], view[k + "_sha256"]) for k in ("base", "route"))
    if len({p for p, _ in assets}) != 5:
        raise ValueError("HOSTED_ASSET_SET_MISMATCH")
    for name, expected in assets:
        path = (root / name).resolve()
        if (path.parent != (root / "visuals/geoapify").resolve()
                or sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError("HOSTED_ASSET_SHA_OR_LOCATION_MISMATCH")
        yield root / name
    yield root / "visuals/geoapify/ATTRIBUTION.md"
    yield root / "09_AB_COMPLETION_RESULTS.md"


def seal(root=ROOT, *, completed=False):
    name = "OPEN_REVIEW_AB_COMPLETION.zip" if completed else "OPEN_REVIEW.zip"
    destination = root / "delivery" / name
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        raise FileExistsError("REVIEW_ARCHIVE_ALREADY_SEALED")
    key = read_api_key(root)
    secrets = set() if not key else {key.encode(), quote(key, safe="").encode(), key.upper().encode()}
    with (root / "06_USER_SCORE_SHEET.csv").open(encoding="utf-8-sig", newline="") as score:
        id_fields = {"blind_scene_id", "detail_pair_id", "context_pair_id"}
        if any(value for row in csv.DictReader(score) for field, value in row.items() if field not in id_fields):
            raise ValueError("USER_SCORES_MUST_STAY_PRIVATE")
    files = {}
    paths = list(entries(root))
    if completed:
        paths.extend(completed_assets(root))
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if relative in files or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("PACKAGE_SOURCE_OUT_OF_SCOPE")
        content = path.read_bytes()
        if any(secret in content for secret in secrets):
            raise ValueError("CREDENTIAL_SCAN_FAILED_FOR_" + relative)
        files[relative] = content
    manifest = {"scope": "OPEN_REVIEW_AB_COMPLETION" if completed else "OPEN_REVIEW_OSM_PARTIAL",
                "status": "READY_FOR_USER_VISUAL_REVIEW" if completed else "PARTIAL_WITH_EVIDENCE",
                "credential_scan": "PASS", "configured_key_checked": bool(key),
                "manifest_excludes_itself": True, "hosted_images_and_routes": "ATTRIBUTED_LIVE" if completed else "ABSENT",
                "entries": [{"path": name, "bytes": len(content), "sha256": sha256(content).hexdigest()}
                            for name,content in sorted(files.items())]}
    with TemporaryDirectory(dir=destination.parent) as work:
        temp = Path(work) / destination.name
        with ZipFile(temp, "x", ZIP_DEFLATED, compresslevel=8) as z:
            for name, content in sorted(files.items()):
                z.writestr(name, content)
            z.writestr("MANIFEST.json",json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
        with ZipFile(temp) as z:
            if z.testzip() or set(z.namelist()) != {*files, "MANIFEST.json"}:
                raise ValueError("ZIP_CRC_OR_MEMBER_CHECK_FAILED")
            for member in manifest["entries"]:
                if sha256(z.read(member["path"])).hexdigest() != member["sha256"]:
                    raise ValueError("ZIP_CONTENT_SHA_FAILED")
        with destination.open("xb") as stream:
            stream.write(temp.read_bytes())
    print(json.dumps({"archive": destination.name, "bytes": destination.stat().st_size,
                      "members": len(files)+1, "sha256": sha256(destination.read_bytes()).hexdigest(),
                      "credential_scan": "PASS", "crc": "PASS"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed", action="store_true")
    seal(completed=parser.parse_args().completed)
