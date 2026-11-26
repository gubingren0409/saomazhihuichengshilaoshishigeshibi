"""Materialize only verified local archives into the new work directory."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from materialize_inputs import materialize

ROOT = Path(__file__).resolve().parents[1]
R2_HASH = "277f1cfac82ec04335262444dcfc3ef1080c2c93d8e481dd8dac42db65ecbf72"


def stage(archive, destination):
    with archive.open("rb") as f:
        if file_digest(f, "sha256").hexdigest() != R2_HASH:
            raise ValueError("Unexpected R2 archive hash")
    destination.mkdir(exist_ok=True)
    with ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("R2 CRC failed")
        manifest = json.loads(z.read("MANIFEST.json"))
        rows = manifest["entries"]
        if set(z.namelist()) != {"MANIFEST.json", *(row["path"] for row in rows)}:
            raise ValueError("R2 archive membership changed")
        folder = destination / "r2"
        for row in rows:
            name = row["path"]
            p = PurePosixPath(name)
            if p.as_posix()!=name or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
                raise ValueError("Unsafe R2 archive path")
            data = z.read(name)
            if (len(data), sha256(data).hexdigest()) != (row["bytes"], row["sha256"]):
                raise ValueError("R2 archive member changed")
            out = folder / name
            out.parent.mkdir(parents=True,exist_ok=True)
            with out.open("xb") as f:
                f.write(data)
    existing = (destination / "rev1").exists()
    return materialize(folder / "references/frozen_archives", destination, verify_only=existing)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,default=ROOT/"references/R2_OPEN_REVIEW.zip")
    p.add_argument("--destination",type=Path,default=ROOT/"inputs")
    args = p.parse_args()
    print(json.dumps({"status":"PASS","archives":stage(args.archive,args.destination)}))
