"""Seal a self-contained R3 review archive with no account data or blind mapping."""
import csv
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from urllib.parse import quote
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
GROUPS=("src","data","tests","schema","inputs","visuals","runs","hosted","audits")
FILE_TYPES={".md",".py",".csv",".json",".geojson",".png",".html",".css",".js",".txt"}
EXCLUDE={"__pycache__",".pytest_cache",".git","runtime","private_local"}
SECRET_SHAPE=re.compile(rb"(?:apiKey|api_key|GEOAPIFY_API_KEY|AMAP_WEB_SERVICE_KEY)\s*[:=]\s*['\"]?[0-9a-fA-F]{32}(?![0-9a-fA-F])")


def digest(data):
    return sha256(data).hexdigest()


def historical_checks(root=ROOT):
    with (root/"audits/historical_sources.csv").open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    same=0
    for row in rows:
        if "::" in row["source"]:
            continue
        path=Path(row["source"])
        assert path.stat().st_size==int(row["bytes"]) and digest(path.read_bytes())==row["sha256"]
        same+=1
    return same


def generate_data_manifest(root=ROOT):
    contracts=json.loads((root/"runs/scene_contracts.json").read_text(encoding="utf-8"))
    hosted_path=root/"runs/hosted_results.json"
    hosted=json.loads(hosted_path.read_text(encoding="utf-8")) if hosted_path.exists() else {"scenes":[]}
    records=[]
    def add(path,scene,role,source,snapshot):
        if not path:
            return
        p=root/path
        if not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError("EVIDENCE_MANIFEST_PATH_MISSING")
        d=p.read_bytes()
        records.append({"scene_id":scene,"role":role,"path":path,"source":source,"snapshot":snapshot,
                        "bytes":len(d),"sha256":digest(d)})
    for c in contracts["scenes"]:
        add(c.get("osm_clip"),c["scene_id"],"BOUNDED_VECTOR_CLIP","Geofabrik Shanghai date-stamped OSM PBF",
            c.get("snapshot_time","2026-11-08T21:21:00Z"))
    for s in hosted["scenes"]:
        route=s.get("route") or {}
        add(route.get("geometry_path"),s["scene_id"],"HOSTED_ROUTE_GEOMETRY","Geoapify Routing","UNKNOWN_HOSTED")
        add(route.get("raw_response_path"),s["scene_id"],"HOSTED_RESPONSE_SAFE","Geoapify Routing","UNKNOWN_HOSTED")
        for name,v in (s.get("views") or {}).items():
            add(v.get("base"),s["scene_id"],name+"_HOSTED_BASE_PNG","Geoapify Static Maps","UNKNOWN_HOSTED")
            add(v.get("overlay"),s["scene_id"],name+"_HOSTED_ROUTE_PNG","Geoapify Static Maps","UNKNOWN_HOSTED")
    for path in sorted((root/"visuals/osm").glob("*.png")):
        add(path.relative_to(root).as_posix(),path.name.split("_",1)[0],"LOCAL_RENDER","Frozen local OSM render",
            "2026-11-08T21:21:00Z")
    with (root/"data/manifest.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]) if records else
                              ["scene_id","role","path","source","snapshot","bytes","sha256"])
        writer.writeheader();writer.writerows(records)
    return len(records)


def seal(root=ROOT):
    out=root/"delivery";out.mkdir(exist_ok=True)
    final=out/"OPEN_REVIEW.zip"
    if final.exists():
        raise FileExistsError("FIXED_R3_ARCHIVE_ALREADY_EXISTS")
    with (root/"07_USER_SCORE_SHEET.csv").open(encoding="utf-8-sig",newline="") as f:
        id_fields={"blind_scene_id","detail_pair_id","context_pair_id"}
        if any(v for row in csv.DictReader(f) for k,v in row.items() if k not in id_fields):
            raise ValueError("NEW_USER_REVIEW_SCORES_ARE_PRIVATE")
    # Compare only in memory. The local configuration never enters the archive.
    secret_file=root.parent/"OSM_GEOAPIFY_PILOT_R1/.env"
    secret_values=set()
    if secret_file.is_file():
        for line in secret_file.read_text(encoding="utf-8-sig").splitlines():
            key,sep,value=line.partition("=")
            val=value.strip().strip("'\"")
            if sep and key.strip()=="GEOAPIFY_API_KEY" and val:
                secret_values.update((val.encode(),quote(val,safe="").encode()))
    selected=[x for x in root.iterdir() if x.is_file() and x.suffix.lower() in FILE_TYPES and not x.name.startswith(".")]
    for group in GROUPS:
        for path in sorted((root/group).rglob("*")):
            if (path.is_file() and path.suffix.lower() in FILE_TYPES
                    and all(not p.startswith(".") and p not in EXCLUDE for p in path.relative_to(root).parts)):
                selected.append(path)
    files={}
    for p in selected:
        rel=p.relative_to(root).as_posix()
        if (rel in files or p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or
                ":" in rel or "BLIND_REVEAL_MAP_PRIVATE" in rel.upper()):
            raise ValueError("UNSAFE_REVIEW_MEMBER")
        data=p.read_bytes()
        if SECRET_SHAPE.search(data) or any(v in data for v in secret_values):
            raise ValueError("CREDENTIAL_LIKE_CONTENT_"+rel)
        files[rel]=data
    manifest={"scope":"OSM_GEOAPIFY_PILOT_R3","manifest_excludes_itself":True,"credential_scan":"PASS",
              "entries":[{"path":k,"bytes":len(v),"sha256":digest(v)} for k,v in sorted(files.items())]}
    with TemporaryDirectory(dir=out) as tmp:
        zip_path=Path(tmp)/final.name
        with ZipFile(zip_path,"x",ZIP_DEFLATED,compresslevel=6) as z:
            for k,v in sorted(files.items()):
                z.writestr(k,v)
            z.writestr("MANIFEST.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        with ZipFile(zip_path) as z:
            assert z.testzip() is None
            assert set(z.namelist())=={*files,"MANIFEST.json"}
            assert all(digest(z.read(r["path"]))==r["sha256"] for r in manifest["entries"])
        with final.open("xb") as f:
            f.write(zip_path.read_bytes())
    print(json.dumps({"path":final.name,"sha256":digest(final.read_bytes()),"members":len(files)+1,
                      "bytes":final.stat().st_size,"crc":"PASS"}))


if __name__=="__main__":
    checked=historical_checks()
    m=generate_data_manifest()
    print(json.dumps({"originals_rehashed":checked,"data_manifest_rows":m}))
    seal()
