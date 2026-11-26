"""Seal and verify a portable R4-REV1 review ZIP without replacing an existing seal."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("audits", "config", "contract", "data", "frozen_r4", "runs", "src", "tests", "visuals")
ALLOWED = {".csv", ".geojson", ".json", ".jsonl", ".md", ".py", ".txt", ".css", ".js", ".html", ".png", ".svg", ".gz"}
EXCLUDED = {"__pycache__", "runtime", "private_local", "node_modules", "browser_cache", "checkouts", "replays"}
SECRET = re.compile(rb"""(?:api[_-]?key|security[_-]?code|authorization|cookie)["']?\s*[:=]\s*["']?[0-9a-fA-F]{32}(?![0-9a-fA-F])""", re.I)
REQUIRED = {
    "README.md", "SCOPE_AND_METHOD.md", "RESULTS.md", "USER_REVIEW_NOTES.md", "requirements.txt",
    "data/source_manifest.json", "data/derived_edges.geojson", "data/edge_evidence.jsonl", "data/entrance_approach.json",
    "src/run_rev1.py", "visuals/index.html", "audits/AUTHOR_CHECK.md", "audits/INDEPENDENT_REVIEW.md",
}


def safe_name(name):
    path = PurePosixPath(name)
    return (bool(path.parts) and path.as_posix() == name and not path.is_absolute() and "\\" not in name and ":" not in name
            and all(not x.startswith(".") and x not in EXCLUDED for x in path.parts))


def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def manifest_check(path):
    with ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or not all(safe_name(name) for name in names):
            raise ValueError("Duplicate or unsafe ZIP path")
        if z.testzip() is not None:
            raise ValueError("CRC check failed")
        entries = json.loads(z.read("MANIFEST.json"))["entries"]
        if set(names) != {"MANIFEST.json", *(r["path"] for r in entries)} or len(entries) + 1 != len(names):
            raise ValueError("Manifest membership mismatch")
        for row in entries:
            with z.open(row["path"]) as f:
                checksum = file_digest(f, "sha256").hexdigest()
            if z.getinfo(row["path"]).file_size != row["bytes"] or checksum != row["sha256"]:
                raise ValueError(f"Manifest hash mismatch: {row['path']}")
    return dict(archive=path.name, bytes=path.stat().st_size, sha256=digest(path),
                members=len(names), manifest_hashes=len(entries), crc="PASS", safe_paths="PASS")


def credential_scan(path):
    if path.suffix in {".png", ".gz"}:
        return
    with path.open("rb") as f:
        for line in f:
            if SECRET.search(line):
                raise ValueError(f"Credential-like field in package member: {path.name}")


def seal(root=ROOT):
    delivery = root / "delivery"
    delivery.mkdir(exist_ok=True)
    final = delivery / "OPEN_REVIEW.zip"
    if final.exists():
        raise FileExistsError("Fixed R4-REV1 ZIP already exists")
    paths = [p for p in root.iterdir() if p.is_file()]
    for group in GROUPS:
        paths.extend(p for p in (root / group).rglob("*") if p.is_file())
    items = {}
    for path in paths:
        name = path.relative_to(root).as_posix()
        if path.suffix.lower() not in ALLOWED or not safe_name(name):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or name in items:
            raise ValueError(f"Unsafe package candidate: {name}")
        credential_scan(path)
        items[name] = path
    missing = REQUIRED - items.keys()
    if missing:
        raise ValueError(f"Missing delivery files: {sorted(missing)}")
    with TemporaryDirectory(dir=delivery) as folder:
        draft = Path(folder) / final.name
        rows = [dict(path=n, bytes=p.stat().st_size, sha256=digest(p)) for n, p in sorted(items.items())]
        with ZipFile(draft, "x", ZIP_DEFLATED, compresslevel=5) as z:
            for row in rows:
                z.write(items[row["path"]], row["path"])
            z.writestr("MANIFEST.json", json.dumps(dict(scope="OSM_GEOAPIFY_R4_REV1", manifest_excludes_itself=True,
                                                     entries=rows), ensure_ascii=False, indent=2) + "\n")
        receipt = manifest_check(draft)
        draft.rename(final)
    return receipt


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--verify", type=Path)
    options = cli.parse_args()
    print(json.dumps(manifest_check(options.verify) if options.verify else seal(), ensure_ascii=False))
