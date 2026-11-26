"""Seal the R3 review files and exact portable source archives."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

ROOT=Path(__file__).resolve().parents[1]
TOP={"README.md","SCOPE_AND_METHOD.md","RESULTS.md","REGION_RECONSTRUCTION.md","USER_REVIEW_NOTES.md",
     "STATUS.json","requirements.txt"}
FOLDERS={"audits","config","src","scripts","tests","data","runs","visuals","references"}
ARCHIVES={"references/R2_OPEN_REVIEW.zip","references/contract/evidence/R4_WALKABILITY_R2_GPT_REVIEW.zip"}
SUFFIXES={".md",".json",".jsonl",".csv",".geojson",".py",".js",".html",".svg",".png",".txt",".zip"}
BLOCKED={"cookies","login data","local state","credentials.json","secrets.json","cookies.sqlite"}
CREDENTIAL=re.compile(rb"(?:AMAP_(?:JS|WEB_SERVICE)_KEY|GEOAPIFY_API_KEY|AMAP_SECURITY_JS_CODE)\s*[:=]\s*[\"']?[A-Za-z0-9]{24,}",re.I)


def safe(name):
    p=PurePosixPath(name)
    return bool(p.parts) and not p.is_absolute() and p.as_posix()==name and all(
        not (x.startswith(".") or x.casefold() in BLOCKED or ":" in x or "\\" in x) for x in p.parts)


def inspect(name,data):
    if not safe(name) or PurePosixPath(name).suffix.lower() not in SUFFIXES:
        raise ValueError(f"Unsafe member {name}")
    if name.endswith(".zip") and name not in ARCHIVES:
        raise ValueError(f"Unbound nested archive {name}")
    if not name.endswith((".zip",".png")) and CREDENTIAL.search(data):
        raise ValueError(f"Credential-like content in {name}")


def nested(data,depth=0):
    if depth>3:
        raise ValueError("Unexpected nesting")
    with ZipFile(BytesIO(data)) as z:
        names=z.namelist()
        if z.testzip() is not None or len(set(n.casefold() for n in names))!=len(names):
            raise ValueError("Nested CRC or collision")
        for info in z.infolist():
            if not safe(info.filename) or stat.S_ISLNK(info.external_attr>>16):
                raise ValueError(f"Unsafe nested member {info.filename}")
            if info.filename.endswith(".zip"):
                nested(z.read(info),depth+1)


def seal(root,output):
    paths=[root/x for x in TOP]
    for folder in FOLDERS:
        paths.extend(p for p in (root/folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix.lower() in SUFFIXES and "frozen_archives" not in p.parts)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("xb") as f, ZipFile(f,"w") as z:
        rows=[]
        for path in sorted(paths,key=lambda x:x.relative_to(root).as_posix()):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"Unsafe source {path}")
            name=path.relative_to(root).as_posix()
            data=path.read_bytes()
            inspect(name,data)
            if name in ARCHIVES:
                nested(data)
            info=ZipInfo(name,(2026,11,10,0,0,0))
            z.writestr(info,data,ZIP_STORED if name.endswith((".zip",".png")) else ZIP_DEFLATED)
            rows.append({"path":name,"bytes":len(data),"sha256":sha256(data).hexdigest()})
        z.writestr(ZipInfo("MANIFEST.json",(2026,11,10,0,0,0)),json.dumps(
            {"artifact":"R4-WALKABILITY-R3","entries":rows},indent=2,ensure_ascii=False)+"\n",ZIP_DEFLATED)
    with ZipFile(output) as z:
        assert z.testzip() is None
        assert set(z.namelist())=={"MANIFEST.json",*(r["path"] for r in rows)}
    print(json.dumps({"path":str(output),"members":len(rows)+1,"bytes":output.stat().st_size,
                      "sha256":sha256(output.read_bytes()).hexdigest()}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"delivery/OPEN_REVIEW.zip")
    seal(ROOT,p.parse_args().output.resolve())
