"""Seal and safely unpack the independent north-access review."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path, PurePosixPath
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("audits", "config", "data", "inputs", "runs", "src", "tests", "visuals")
ALLOWED = {".md", ".txt", ".csv", ".geojson", ".json", ".py", ".html", ".css", ".js", ".svg", ".png"}
REQUIRED = {
    "README.md", "01_INPUT_AUDIT.md", "02_NORTH_FRONTAGE_EVIDENCE.md", "03_N1_N2_METHODS.md",
    "04_RESULTS.md", "05_LIMITATIONS_AND_DECISION.md", "data/segment_evidence.csv", "data/route_variants.geojson",
    "data/obstacle_intersections.csv", "data/level_evidence.csv", "audits/INDEPENDENT_REVIEW.md",
    "visuals/index.html", "runs/experiment.json", "config/frontage.json",
}


def sha(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    return (bool(p.parts) and p.as_posix() == name and not p.is_absolute()
            and "\\" not in name and ":" not in name
            and all(not x.startswith(".") and x not in {"runtime", "__pycache__", "private_local"} for x in p.parts))


def verify(path, extract=None):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len({n.casefold() for n in names}) or not all(safe_name(n) for n in names):
            raise ValueError("Unsafe ZIP path")
        if archive.testzip() is not None:
            raise ValueError("CRC failure")
        entries = json.loads(archive.read("MANIFEST.json"))["entries"]
        if set(names) != {"MANIFEST.json", *(e["path"] for e in entries)} or len(names) != len(entries) + 1:
            raise ValueError("Manifest membership mismatch")
        for row in entries:
            n = row["path"]
            with archive.open(n) as f:
                if archive.getinfo(n).file_size != row["bytes"] or file_digest(f, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError(f"ZIP member hash differs: {n}")
        if extract:
            extract.mkdir(parents=True)
            for name in names:
                target = extract.joinpath(*name.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
    return dict(path=path.name, bytes=path.stat().st_size, sha256=sha(path), members=len(names),
                manifest_hashes=len(entries), crc="PASS", path_safety="PASS", extracted=bool(extract))


def seal():
    dest = ROOT / "delivery"
    dest.mkdir(exist_ok=True)
    output = dest / "OPEN_REVIEW.zip"
    if output.exists():
        raise FileExistsError("Fixed archive already exists")
    candidates = [p for p in ROOT.iterdir() if p.is_file()]
    for group in GROUPS:
        candidates.extend(p for p in (ROOT / group).rglob("*") if p.is_file())
    files = {}
    for p in candidates:
        name = p.relative_to(ROOT).as_posix()
        if p.suffix.lower() not in ALLOWED or not safe_name(name):
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(ROOT.resolve()) or name in files:
            raise ValueError(f"Unsafe review member: {name}")
        files[name] = p
    if REQUIRED - files.keys():
        raise ValueError(f"Missing required artifacts: {sorted(REQUIRED - files.keys())}")
    rows = [dict(path=n, bytes=p.stat().st_size, sha256=sha(p)) for n, p in sorted(files.items())]
    with TemporaryDirectory(dir=dest) as folder:
        draft = Path(folder) / output.name
        with ZipFile(draft, "x", ZIP_DEFLATED, compresslevel=6) as z:
            for row in rows:
                z.write(files[row["path"]], row["path"])
            z.writestr("MANIFEST.json", json.dumps(dict(scope="OSM_GEOAPIFY_R4_NORTH_ACCESS_R1", entries=rows),
                                                  ensure_ascii=False, indent=2) + "\n")
        result = verify(draft)
        draft.rename(output)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify", type=Path)
    p.add_argument("--extract", type=Path)
    a = p.parse_args()
    print(json.dumps(verify(a.verify, a.extract) if a.verify else seal(), ensure_ascii=False))
