"""Seal the bounded review payload with a path and byte manifest."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path,PurePosixPath
import re
import stat
from zipfile import ZipFile,ZipInfo,ZIP_STORED,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
TOP={"README.md","SCOPE_AND_METHOD.md","RESULTS.md","USER_REVIEW_NOTES.md","STATUS.json","requirements.txt"}
DIRS={"src","scripts","tests","data","runs","visuals","audits","config","input_contract"}
TYPES={".py",".js",".html",".md",".json",".jsonl",".csv",".geojson",".png",".svg",".txt",".zip"}
FROZEN="input_contract/frozen/WALKABILITY_R3_OPEN_REVIEW.zip"
CREDENTIAL=re.compile(rb"(?:AMAP_(?:JS|WEB_SERVICE)_KEY|GEOAPIFY_API_KEY|AMAP_SECURITY_JS_CODE)\s*[:=]\s*[\"']?[A-Za-z0-9]{24,}",re.I)


def safe(name):
    p=PurePosixPath(name)
    blocked={"cookies","cookie","login data","credentials.json","secrets.json","local state"}
    return bool(p.parts) and not p.is_absolute() and p.as_posix()==name and all(
        not (q.startswith(".") or ":" in q or "\\" in q or q.casefold() in blocked) for q in p.parts)


def inspect(name,data):
    if not safe(name) or PurePosixPath(name).suffix.lower() not in TYPES or name.endswith(".zip") and name!=FROZEN:
        raise ValueError(f"Unexpected path: {name}")
    if not name.endswith((".zip",".png")) and CREDENTIAL.search(data):
        raise ValueError(f"Credential-shaped content in {name}")


def check_nested(data,depth=0):
    if depth>4:
        raise ValueError("Archive nesting exceeds frozen binding")
    with ZipFile(BytesIO(data)) as z:
        names=z.namelist()
        if z.testzip() is not None or len(set(x.casefold() for x in names))!=len(names):
            raise ValueError("Nested CRC or duplicate case-insensitive path")
        for f in z.infolist():
            if not safe(f.filename) or stat.S_ISLNK(f.external_attr>>16):
                raise ValueError(f"Invalid nested member: {f.filename}")
            if f.filename.endswith(".zip"):
                check_nested(z.read(f),depth+1)


def paths(root):
    result=[root/p for p in TOP]
    for folder in DIRS:
        result.extend(p for p in (root/folder).rglob("*") if p.is_file() and p.suffix.lower() in TYPES
                      and "__pycache__" not in p.parts and not p.is_relative_to(root/"data/pilot"))
    return sorted(result,key=lambda p:p.relative_to(root).as_posix())


def seal(root,dest):
    rows=[]
    with dest.open("xb") as stream,ZipFile(stream,"w",compresslevel=5) as z:
        for f in paths(root):
            if f.is_symlink() or not f.resolve().is_relative_to(root):
                raise ValueError(f"Out-of-tree review file {f}")
            name=f.relative_to(root).as_posix()
            data=f.read_bytes()
            inspect(name,data)
            if name==FROZEN:
                check_nested(data)
            z.writestr(ZipInfo(name,(2026,11,11,0,0,0)),data,
                       ZIP_STORED if name.endswith((".png",".zip")) else ZIP_DEFLATED)
            rows.append({"path":name,"bytes":len(data),"sha256":sha256(data).hexdigest()})
        z.writestr(ZipInfo("MANIFEST.json",(2026,11,11,0,0,0)),
                   json.dumps({"artifact":"R4-WALKABILITY-R4-CONTEXT","entries":rows},indent=2,ensure_ascii=False)+"\n",
                   ZIP_DEFLATED)
    with ZipFile(dest) as z:
        assert z.testzip() is None
        assert set(z.namelist())=={"MANIFEST.json",*(r["path"] for r in rows)}
    print(json.dumps({"path":str(dest),"sha256":sha256(dest.read_bytes()).hexdigest(),
                      "members":len(rows)+1,"bytes":dest.stat().st_size}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"delivery/OPEN_REVIEW.zip")
    seal(ROOT,p.parse_args().output.resolve())
