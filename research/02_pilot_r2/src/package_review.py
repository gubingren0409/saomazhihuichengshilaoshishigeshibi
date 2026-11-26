"""Seal the R2 diagnostic artifacts and exact licensed inputs in one local archive."""
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=("analysis","audits","figures","inputs","src","web")
SUFFIXES={".py",".md",".json",".geojson",".csv",".png",".html",".js",".css",".txt"}
TOP=("README.md","STATUS.json","requirements.txt","01_ROUTE_DIFFERENCE_DIAGNOSIS.md",
     "02_MAP_VISUAL_VS_ROUTE_QUALITY.md","03_USER_FEEDBACK_TRACEABILITY.md","04_NEXT_EXPERIMENT_DECISIONS.md",
     "route_segment_differences.csv","osm_feature_inventory.csv","plaza_connectivity_audit.csv",
     "endpoint_gap_audit.csv","coordinate_and_snap_audit.csv","figure_manifest.csv","source_evidence_index.csv")
CREDENTIAL=re.compile(rb"(?:GEOAPIFY_API_KEY|AMAP_WEB_SERVICE_KEY|AMAP_JS_KEY|AMAP_JS_SECURITY_CODE|apiKey)\s*=\s*['\"]?[0-9a-fA-F]{32}(?![0-9a-fA-F])")


def paths(root):
    yield from (root/f for f in TOP)
    for folder in DIRECTORIES:
        for path in sorted((root/folder).rglob("*")):
            if (path.is_file() and path.suffix.lower() in SUFFIXES
                    and not any(x.startswith(".") or x in {"__pycache__","runtime","private_local",
                                                           "07_BLIND_REVEAL_MAP_PRIVATE.csv"}
                                for x in path.relative_to(root).parts)):
                yield path


def seal(root=ROOT):
    output=root/"delivery"
    output.mkdir(exist_ok=True)
    target=output/"OPEN_REVIEW.zip"
    if target.exists():
        raise FileExistsError("R2_REVIEW_ALREADY_SEALED")
    files={}
    for path in paths(root):
        name=path.relative_to(root).as_posix()
        if name in files or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("UNSAFE_ARCHIVE_INPUT")
        data=path.read_bytes()
        if CREDENTIAL.search(data):
            raise ValueError("SUSPECTED_SECRET_IN_"+name)
        files[name]=data
    manifest={"scope":"R2_READ_ONLY_DIAGNOSTIC_AND_VISUAL_REVIEW","manifest_excludes_itself":True,
              "status":"READY_FOR_USER_REVIEW","source_scope":"VERIFIED_FROZEN_R1_CLIP_AND_ATTRIBUTED_IMAGES",
              "sensitive_config":"EXCLUDED","entries":[{"path":k,"bytes":len(v),"sha256":sha256(v).hexdigest()}
                                                        for k,v in sorted(files.items())]}
    with TemporaryDirectory(dir=output) as scratch:
        intermediate=Path(scratch)/target.name
        with ZipFile(intermediate,"x",ZIP_DEFLATED,compresslevel=8) as archive:
            for name,data in sorted(files.items()):
                archive.writestr(name,data)
            archive.writestr("MANIFEST.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        with ZipFile(intermediate) as archive:
            assert archive.testzip() is None and set(archive.namelist())=={*files,"MANIFEST.json"}
            assert all(sha256(archive.read(row["path"])).hexdigest()==row["sha256"] for row in manifest["entries"])
        with target.open("xb") as handle:
            handle.write(intermediate.read_bytes())
    print(json.dumps({"archive":target.name,"sha256":sha256(target.read_bytes()).hexdigest(),
                      "members":len(files)+1,"bytes":target.stat().st_size,"crc":"PASS"}))


if __name__=="__main__":
    seal()
