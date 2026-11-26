"""Independent fixed ZIP and actual unpack/replay receipt verification.

Streams all manifest members and nested archives. This checker does not import
the author's seal/replay routines or consume their PASS as sufficient evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CASES={"Wc4183046a70_G_080","W6daddd19fdb_G_080","W745941f0f92_G_080","W0440b97497a_N_080","W7a6b5a10076_G_080","NORTH_160"}
REQUIRED={"README.md","RESULTS.md","SCOPE_AND_METHOD.md","STATUS.json","visuals/index.html",
          "config/contract.json","data/task_manifest.json","runs/paired_metrics.csv","runs/query_outcomes.csv",
          "audits/INDEPENDENT_REVIEW.md","audits/LEAKAGE_REVIEW.md","scripts/replay.py","scripts/serve_review.py"}
REQUIRED.update({"data/access_area_interpretations.json","audits/closed_access_D30_independent.json","audits/source_access_graph_impact.json"})


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda:f.read(1024*1024),b""):h.update(data)
    return h.hexdigest()


def stream_hash(stream):
    h=hashlib.sha256();size=0
    for chunk in iter(lambda:stream.read(1024*1024),b""):
        size+=len(chunk);h.update(chunk)
    return size,h.hexdigest()


def safe(name):
    path=PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and ":" not in name and "\\" not in name,
            "Unsafe archive path: "+name)
    require(name and str(path) not in {".",""},"Empty archive path")


def archive_check(handle,label,depth=0,*,unpacked=None):
    require(depth<=8,"Nested archive recursion exceeded approved bound")
    with zipfile.ZipFile(handle) as z:
        infos=z.infolist();names={i.filename for i in infos}
        require(len(infos)==len(names),"Duplicate archive member")
        require(sum(v.file_size for v in infos)<2*1024**3,"Unexpectedly large archive expansion")
        for info in infos:
            safe(info.filename)
            require(not stat.S_ISLNK(info.external_attr>>16) and not info.flag_bits&1,"Symlink/encrypted input not allowed")
        bad=z.testzip();require(bad is None,"Archive CRC failure: "+str(bad))
        files={i.filename:i for i in infos if not i.is_dir()}
        candidates=[n for n in ("MANIFEST.json","MANIFEST_SHA256.json") if n in files]
        require(len(candidates)==1,"No unique root content manifest")
        manifest_name=candidates[0]
        if depth==0 and unpacked is not None:
            require((unpacked/manifest_name).read_bytes()==z.read(manifest_name),"Unpacked root manifest bytes changed")
        obj=json.loads(z.read(manifest_name).decode("utf-8-sig"))
        entries=obj if isinstance(obj,list) else obj["entries"]
        manifest={row["path"]:row for row in entries}
        require(len(manifest)==len(entries) and set(manifest)==set(files)-{manifest_name},"Manifest membership mismatch")
        scans=[];nested=[];changed=[]
        for name,row in sorted(manifest.items()):
            safe(name)
            with z.open(name) as f:size,digest=stream_hash(f)
            require(size==row["bytes"] and digest==row["sha256"],"Member size/SHA mismatch: "+name)
            lower=name.lower()
            require(not any(token in lower for token in ("browser_profile","security_code","cookie","credential")),
                    "Sensitive filename in fixed package")
            require(not PurePosixPath(lower).name.startswith(".env"),"Environment file packaged")
            if files[name].file_size<2*1024**2 and PurePosixPath(name).suffix.lower() in {".json",".md",".py",".html",".js",".csv"}:
                data=z.read(name).decode("utf-8-sig",errors="replace")
                # Heuristic only; hashes and benign placeholders are not keys.
                hit=re.search(r'''(?im)["']?(?:api[_-]?key|security[_-]?code|secret|password)["']?\s*[:=]\s*["']([0-9a-f]{24,48})["']''',data)
                require(hit is None,"Possible literal credential assignment: "+name)
                url_hit=re.search(r'''(?i)(?:[?&])(?:apiKey|api_key|key|jscode)=([0-9a-f]{24,48})(?:[&#"'\s]|$)''',data)
                require(url_hit is None,"Possible literal credential URL parameter: "+name)
                scans.append(name)
            if depth==0 and unpacked is not None:
                path=(unpacked/name).resolve()
                require(path.is_relative_to(unpacked.resolve()) and path.is_file(),"Unpacked member missing/unsafe: "+name)
                if sha(path)!=digest:changed.append(name)
            if name.lower().endswith(".zip"):
                with tempfile.SpooledTemporaryFile(max_size=8*1024**2) as tmp:
                    with z.open(name) as source:
                        for chunk in iter(lambda:source.read(1024*1024),b""):tmp.write(chunk)
                    tmp.seek(0);nested.append(archive_check(tmp,name,depth+1))
        if depth==0:require(REQUIRED<=set(files),"Required delivery members missing: "+str(sorted(REQUIRED-set(files))))
        return {"archive":label,"members":len(infos),"uncompressed_bytes":sum(v.file_size for v in infos),
                "manifest_entries":len(entries),"crc":"PASS","paths":"PASS","member_sha256":"PASS",
                "credential_assignment_heuristic_scanned_files":len(scans),"nested":nested,
                "unpacked_members_differing_after_replay":changed}


def replay_check(unpacked,receipt,archive_sha):
    result=json.loads(receipt.read_text(encoding="utf8"))
    require(result.get("archive_sha256")==archive_sha,"Replay receipt is for another archive")
    rows=result["cases"]
    require({r["id"] for r in rows}==CASES,"Replay did not cover original four controlled, unsafe W7, and north")
    work=unpacked/"runtime/final_replay"
    tests=(work/"tests.txt").read_text(encoding="utf8")
    match=re.search(r"Ran (\d+) tests? in",tests)
    require(match and int(match[1])==12 and re.search(r"^OK\s*$",tests,re.M),"Actual unpacked unittest output is not 12 successful tests")
    checks=[]
    def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    for row in rows:
        ident=row["id"]
        methods={v["method"] for v in row["methods"]}
        require({"M1-C","F0","F1"}<=methods,"Replay omitted a main arm")
        for method in methods:
            new=json.loads((work/ident/(method+".prediction.json")).read_text(encoding="utf8"))
            old=json.loads((unpacked/"data/predictions"/ident/(method+".json")).read_text(encoding="utf8"))
            equality={k:digest(new[k])==digest(old[k]) for k in ("surface","routes","base_routes")}
            equality["unweighted_graph"]=new["graph"]["graph_sha256"]==old["graph"]["graph_sha256"]
            equality["terminal_graph"]=new["graph"]["terminal_graph_sha256"]==old["graph"]["terminal_graph_sha256"]
            require(all(equality.values()),"Actual replay geometry/route mismatch, independent of receipt PASS")
            checks.append({"id":ident,"method":method,"canonical_checks":equality})
    require(any(r["method"] in {"F1-L1p5","F1-L3","F1-L5"} for r in checks),"No finite-cost sensitivity actually replayed")
    from shapely import union_all
    from shapely.geometry import shape
    gaps=json.loads((unpacked/"audits/closed_access_D30_independent.json").read_text(encoding="utf8"))["eligible_independent_area_assumed_overlaps"]
    gap=next((g for g in gaps if g["id"]=="W7a6b5a10076_G_080"),None)
    registry=json.loads((unpacked/"data/access_area_interpretations.json").read_text(encoding="utf8"))["areas"]
    source_id=gap["source_id"] if gap else "way/178730989"
    area=shape(next(a for a in registry if a["source_id"]==source_id)["geometry"])
    private_checks=[]
    for method in ("F0","F1"):
        actual=json.loads((work/"W7a6b5a10076_G_080"/(method+".prediction.json")).read_text(encoding="utf8"))
        assumed=union_all([shape(c["geometry"]) for c in actual["surface"]["cells"] if c["walkability_state"]=="INFERRED_WALKABLE"])
        overlap=assumed.intersection(area).area
        expected=area.intersection(shape(actual["surface"]["domain"])).area
        restricted=union_all([shape(c["geometry"]) for c in actual["surface"]["cells"] if c["walkability_state"]=="RESTRICTED"])
        blocked=restricted.intersection(area).area
        if gap:
            require(overlap>1e-5 and abs(overlap-gap["assumed_overlap_m2"])<=1e-5,"R0 replay no longer reproduces registered unsafe source-area expansion")
        else:
            require(overlap<=1e-5 and expected>1e-5 and abs(blocked-expected)<=1e-5,
                    "Repaired replay still opens, or fails to block, the original private area")
        private_checks.append({"method":method,"source_id":source_id,"private_area_overlap_m2":overlap,
                               "private_area_in_fixed_domain_m2":expected,"source_private_area_restricted_m2":blocked})
    return {"status":"PASS","actual_tests":int(match[1]),"actual_case_count":len(rows),"actual_method_runs":len(checks),
            "checks":checks,"scope":"FIXED_SIX_REPLAY_CASES; NOT_WHOLE_25_PARENT_MATRIX_REEXECUTION",
            "private_area_replay_checks":private_checks,
            "policy_check":"R0_KNOWN_UNSAFE_AREA_REPRODUCED_NOT_POLICY_PASS" if gap else "W7_SOURCE_ACCESS_GAP_REPAIR_CONFIRMED_IN_FIXED_SCOPE_USER_REVIEW_PENDING",
            "comparison":"CANONICAL_GEOMETRY_GRAPH_ROUTES_EXACT; WHOLE_JSON_VOLATILE_METADATA_NOT_BYTE_CLAIMED"}


def main(args):
    archive=args.archive.resolve();digest=sha(archive)
    result=archive_check(archive,archive.name,unpacked=args.unpacked)
    if args.unpacked:
        require(not result["unpacked_members_differing_after_replay"],"Unpacked packaged files changed beyond byte-identical visual rebuild")
    if args.receipt:
        require(args.unpacked is not None,"--receipt requires actual --unpacked directory")
        result["actual_replay_check"]=replay_check(args.unpacked,args.receipt,digest)
    result.update(status="PASS_SCOPED",reviewer="/root/free_evaluation",archive_sha256=digest,
                  limits=["Credential content scan is heuristic, not a general privacy proof",
                          "Only the frozen six representative cases were rerun; full matrix was independently geometrically scored separately",
                          "No external field walkability/public access evidence was acquired"])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({k:result[k] for k in ("status","archive_sha256","members","uncompressed_bytes")},ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--unpacked",type=Path)
    p.add_argument("--receipt",type=Path)
    p.add_argument("--out",type=Path,default=ROOT/"delivery/independent_package_check.json")
    main(p.parse_args())
