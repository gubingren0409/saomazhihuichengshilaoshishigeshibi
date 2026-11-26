"""Verify and extract the two exact frozen input archives into a fresh directory."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "rev1": ("R4_REV1_OPEN_REVIEW.zip", "f2de5326ffbffe1e62c0fa5d622cec6645582342824ea1ae13716789d5af5ee0"),
    "north": ("NORTH_ACCESS_R1_OPEN_REVIEW.zip", "ac829ec6bbb0d8b35f50fba4b424bbca264cbec873a7fa985da71d722d781147"),
}


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verify_members(folder, entries):
    for row in entries:
        target = folder / row["path"]
        if (not target.is_file() or target.stat().st_size != row["bytes"] or sha(target) != row["sha256"]):
            raise ValueError(f"Extracted source differs: {row['path']}")


def safe(name):
    path = PurePosixPath(name)
    return bool(path.parts) and path.as_posix() == name and not path.is_absolute() and ".." not in path.parts and ":" not in name and "\\" not in name


def materialize(archives, output, verify_only=False):
    if not verify_only:
        output.mkdir(parents=True, exist_ok=True)
    receipt = []
    for key, (name, expected_sha) in ARCHIVES.items():
        path = archives / name
        if sha(path) != expected_sha:
            raise ValueError(f"Source archive SHA differs: {name}")
        with ZipFile(path) as z:
            members = z.namelist()
            if not all(safe(x) for x in members) or len(set(m.casefold() for m in members)) != len(members):
                raise ValueError("Unsafe or duplicate source archive paths")
            if sum(x.file_size for x in z.infolist()) > 1024**3:
                raise ValueError("Source archive exceeds extraction budget")
            manifest = json.loads(z.read("MANIFEST.json"))
            entries = manifest["entries"] if isinstance(manifest, dict) else manifest
            if set(members) != {"MANIFEST.json", *(row["path"] for row in entries)}:
                raise ValueError("Source member set differs")
            folder = output / key
            if not verify_only:
                for member in members:
                    target = folder.joinpath(*member.split("/"))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as stream, target.open("xb") as file:
                        shutil.copyfileobj(stream, file)
            verify_members(folder, entries)
            if (folder / "MANIFEST.json").read_bytes() != z.read("MANIFEST.json"):
                raise ValueError("Extracted source manifest differs")
        receipt.append(dict(name=name, sha256=expected_sha, members=len(members), directory=key))
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archives", type=Path, default=ROOT / "references/frozen_archives")
    p.add_argument("--output", type=Path, default=ROOT / "inputs")
    p.add_argument("--verify-only", action="store_true")
    a = p.parse_args()
    print(json.dumps({"status": "PASS", "archives": materialize(a.archives.resolve(), a.output.resolve(), a.verify_only)}))
