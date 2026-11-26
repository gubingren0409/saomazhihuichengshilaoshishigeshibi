"""Create the R4-only review ZIP after checking its member and credential boundaries."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
MEMBER_GROUPS = ("audits", "data", "inputs", "runs", "src", "tests", "visuals")
SUFFIXES = {".csv", ".geojson", ".json", ".md", ".py", ".txt", ".css", ".js", ".html", ".png", ".svg"}
EXCLUDED = {"__pycache__", "runtime", "private_local", "node_modules", "browser_cache", "checkouts"}
SECRET = re.compile(rb"""(?:api[_-]?key|security[_-]?code|authorization|cookie)["']?\s*[:=]\s*["']?[0-9a-fA-F]{32}(?![0-9a-fA-F])""", re.I)
REQUIRED = {
    "README.md", "01_RESEARCH_CONTRACT_AND_SCOPE.md", "02_OPEN_SPACE_FEATURE_AUDIT.md",
    "03_EDGE_CONNECTION_METHOD.md", "04_EXPERIMENT_RESULTS.md", "05_DUAL_PATH_INPUT_CAPABILITY.md",
    "06_LIMITATIONS_AND_NEXT_DECISIONS.md", "audits/INDEPENDENT_REVIEW.md",
    "data/manifest.csv", "data/added_edges.csv", "data/entrance_access.csv",
    "data/connectivity_changes.csv", "runs/experiment.json", "runs/dual_paths.json", "visuals/index.html",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    pure = PurePosixPath(name)
    return (not pure.is_absolute() and pure.as_posix() == name and "\\" not in name and ":" not in name
            and all(not part.startswith(".") and part not in EXCLUDED for part in pure.parts))


def verify(archive_path):
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not all(safe_path(name) for name in names):
            raise ValueError("Unsafe archive members")
        if archive.testzip() is not None:
            raise ValueError("CRC verification failed")
        entries = json.loads(archive.read("MANIFEST.json"))["entries"]
        if set(names) != {*(row["path"] for row in entries), "MANIFEST.json"}:
            raise ValueError("Manifest does not cover the ZIP")
        for row in entries:
            data = archive.read(row["path"])
            if len(data) != row["bytes"] or sha(data) != row["sha256"]:
                raise ValueError(f"Archive hash mismatch: {row['path']}")
    return dict(path=archive_path.name, members=len(names), bytes=archive_path.stat().st_size,
                sha256=sha(archive_path.read_bytes()), crc="PASS", manifest_hashes="PASS")


def seal(root=ROOT):
    delivery = root / "delivery"
    delivery.mkdir(exist_ok=True)
    output = delivery / "OPEN_REVIEW.zip"
    if output.exists():
        raise FileExistsError("The fixed R4 review ZIP already exists")
    candidates = [x for x in root.iterdir() if x.is_file()]
    for group in MEMBER_GROUPS:
        candidates.extend(path for path in (root / group).rglob("*") if path.is_file())
    members = {}
    for path in sorted(candidates):
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() not in SUFFIXES or not safe_path(rel):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Unexpected external member: {rel}")
        data = path.read_bytes()
        if SECRET.search(data):
            raise ValueError(f"Credential-shaped member: {rel}")
        members[rel] = data
    if REQUIRED - members.keys():
        raise ValueError(f"Required files missing: {sorted(REQUIRED - members.keys())}")
    manifest = dict(scope="OSM_GEOAPIFY_R4", excludes_itself=True, credential_shape_scan="PASS",
                    entries=[dict(path=path, bytes=len(data), sha256=sha(data)) for path, data in members.items()])
    with TemporaryDirectory(dir=delivery) as temporary:
        draft = Path(temporary) / output.name
        with ZipFile(draft, "x", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
            archive.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        receipt = verify(draft)
        with output.open("xb") as handle:
            handle.write(draft.read_bytes())
    return receipt


if __name__ == "__main__":
    print(json.dumps(seal(), ensure_ascii=False))
