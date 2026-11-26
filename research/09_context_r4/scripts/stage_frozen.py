"""Verify and extract exact archived R3 and its portable historical dependencies."""
from hashlib import file_digest
import json
from pathlib import Path,PurePosixPath
import shutil
import stat
import subprocess
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/"input_contract/frozen/WALKABILITY_R3_OPEN_REVIEW.zip"
EXPECTED="d623af231c6eabeace1d3c8e284787a51b7d83782c6c8f7990d16b27f5c0cd0e"


def main():
    subprocess.run([sys.executable,"-X","utf8","-B","verify_inputs.py"],cwd=ROOT/"input_contract",check=True)
    with ARCHIVE.open("rb") as f:
        if file_digest(f,"sha256").hexdigest()!=EXPECTED:
            raise ValueError("Archived R3 differs from frozen hash")
    folder=ROOT/"frozen_r3"
    folder.mkdir()
    with ZipFile(ARCHIVE) as z:
        rows=json.loads(z.read("MANIFEST.json"))["entries"]
        if z.testzip() is not None or set(z.namelist())!={"MANIFEST.json",*(r["path"] for r in rows)}:
            raise ValueError("Archived R3 manifest or CRC")
        for info in z.infolist():
            name=info.filename
            p=PurePosixPath(name)
            if (not p.parts or p.is_absolute() or p.as_posix()!=name or ".." in p.parts or "\\" in name or
                    ":" in name or stat.S_ISLNK(info.external_attr>>16)):
                raise ValueError("Invalid frozen path")
            target=folder/name
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as f,z.open(info) as stream:
                shutil.copyfileobj(stream,f)
    subprocess.run([sys.executable,"-X","utf8","-B","scripts/stage_inputs.py"],cwd=folder,check=True)


if __name__=="__main__":
    main()
