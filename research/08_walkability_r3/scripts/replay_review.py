"""Check a fixed R3 ZIP, then rebuild results from its frozen sources in an empty directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from time import perf_counter
from zipfile import ZipFile

from seal_review import ARCHIVES, inspect, nested


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract(path,destination):
    destination.mkdir(parents=True)
    with ZipFile(path) as z:
        members=z.namelist()
        if z.testzip() is not None or len({n.casefold() for n in members})!=len(members) or sum(
                i.file_size for i in z.infolist())>1024**3:
            raise ValueError("Invalid archive CRC, paths or size")
        rows=json.loads(z.read("MANIFEST.json"))["entries"]
        if set(members)!={"MANIFEST.json",*(r["path"] for r in rows)} or len(rows)+1!=len(members):
            raise ValueError("ZIP member list differs from manifest")
        for row in rows:
            name=row["path"]
            if stat.S_ISLNK(z.getinfo(name).external_attr>>16):
                raise ValueError("Symbolic link is not allowed")
            data=z.read(name)
            inspect(name,data)
            if name in ARCHIVES:
                nested(data)
            if (len(data),sha256(data).hexdigest())!=(row["bytes"],row["sha256"]):
                raise ValueError(f"Manifest mismatch: {name}")
            target=destination/name
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as f:
                f.write(data)
        return len(members)


def call(root, command, log, timeout=300):
    start=perf_counter()
    result=subprocess.run([sys.executable,"-X","utf8","-B",*command],cwd=root,encoding="utf-8",
                          capture_output=True,timeout=timeout)
    row={"command":command,"seconds":round(perf_counter()-start,3),"exit_code":result.returncode,
         "stdout_tail":result.stdout[-950:]}
    log.append(row)
    if result.returncode:
        print(result.stderr,file=sys.stderr)
        result.check_returncode()
    print(f"OK {command[0:3]} {row['seconds']} s",flush=True)


def normalize(value):
    transient={"seconds","elapsed_s","peak_working_set_bytes","route_seconds","browser_pid"}
    if isinstance(value,dict):
        return {k:normalize(v) for k,v in value.items() if k not in transient}
    if isinstance(value,list):
        return [normalize(v) for v in value]
    return value


def equivalent(a,b):
    if isinstance(a,float) and isinstance(b,(int,float)):
        return abs(a-b)<=1e-7
    if type(a) is not type(b):
        return False
    if isinstance(a,dict):
        return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list):
        return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    return a==b


def compare(frozen,new,path,results):
    a,b=frozen/path,new/path
    if not a.is_file() or not b.is_file():
        results[path]="MISSING"
    elif a.read_bytes()==b.read_bytes():
        results[path]="BYTE_IDENTICAL"
    elif a.suffix in {".json",".geojson"} and equivalent(normalize(read(a)),normalize(read(b))):
        results[path]="SEMANTIC_EQUIVALENCE_1E-7"
    else:
        results[path]="DIFFERENT"


def main(args):
    work=args.destination.resolve()
    archive=args.archive.resolve()
    frozen=work/"extracted"
    count=extract(archive,frozen)
    root=work/"replayed"
    for folder in ("src","scripts","config","tests"):
        shutil.copytree(frozen/folder,root/folder)
    (root/"audits").mkdir()
    benchmark_protocol=root/"config/benchmark.json"
    if benchmark_protocol.exists():
        benchmark_protocol.rename(root/"config/benchmark_packaged.json")
    log=[]
    call(root,["scripts/stage_inputs.py","--archive",str(frozen/"references/R2_OPEN_REVIEW.zip")],log)
    call(root,["-m","src.run_semantics"],log)
    call(root,["src/audit_s.py"],log)
    call(root,["src/prepare_benchmark.py"],log)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[
            pool.submit(call,root,["-m","src.run_regions","north"],log),
            pool.submit(call,root,["scripts/run_benchmark.py"],log,600),
        ]
        for setting in ("grid_1p5m","proximity_8m"):
            output=root/"runtime/sensitivity"/setting
            jobs.append(pool.submit(call,root,["scripts/run_benchmark.py","--sensitivity",setting,"--out",str(output)],log))
        for job in jobs:
            job.result()
    call(root,["src/score_benchmark.py"],log)
    for setting in ("grid_1p5m","proximity_8m"):
        output=root/"runtime/sensitivity"/setting
        call(root,["src/score_benchmark.py","--prediction-root",str(output),"--split","development",
                   "--no-audit","--no-visual","--output",str(root/"runs"/f"benchmark_sensitivity_{setting}.json")],log)
    call(root,["src/audit_region_independent.py"],log)
    call(root,["src/build_visuals.py"],log)
    call(root,["src/audit_display_independent.py"],log)
    call(root,["-m","pytest","-q","tests","-p","no:cacheprovider"],log)
    checks={}
    for path in ("data/semantics_edges.csv","data/semantics_routes.geojson","runs/semantics.json",
                 "data/benchmark/inventory.json","config/benchmark.json","data/north_regions.geojson",
                 "data/north_regions_I-REGION-ABL.geojson","data/north_regions_I-REGION-NET-ABL.geojson",
                 "data/north_surface_freeze.json","data/north_domain.geojson",
                 "data/north_interfaces.geojson","data/north_routes.geojson","data/north_queries.json",
                 "runs/north.json","audits/region_independent.json","runs/benchmark_evaluation.json",
                 "data/benchmark_review.geojson","runs/benchmark_review.json","audits/display_independent.json",
                 "runs/benchmark_sensitivity_grid_1p5m.json","runs/benchmark_sensitivity_proximity_8m.json",
                 "visuals/index.html"):
        compare(frozen,root,path,checks)
    for folder,pattern in (("runs/benchmark","*.json"),("data/benchmark_predictions","*.geojson"),
                           ("data/benchmark","*/*json")):
        for path in sorted((frozen/folder).glob(pattern)):
            compare(frozen,root,path.relative_to(frozen).as_posix(),checks)
    if args.browser:
        call(root,["scripts/check_visuals.py","--browser",args.browser,
                   "--receipt",str(root/"audits/browser_replay.json")],log)
        for path in sorted((frozen/"visuals/figures").glob("*")):
            if path.suffix in {".svg",".png"}:
                compare(frozen,root,path.relative_to(frozen).as_posix(),checks)
    status="PASS" if all(v not in {"DIFFERENT","MISSING"} for v in checks.values()) else "DIFFERENT"
    result={"status":status,"archive_sha256":sha256(archive.read_bytes()).hexdigest(),
            "member_count":count,"member_safety_crc_sha":"PASS","checks":checks,"commands":log,
            "browser":"ACTUALLY_REPLAYED" if args.browser else "NOT_RUN"}
    if args.receipt:
        with args.receipt.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,ensure_ascii=False)
    print(json.dumps({"status":status,"checks":len(checks),
                      "differences":{k:v for k,v in checks.items() if v in {"DIFFERENT","MISSING"}}}))
    return 0 if status=="PASS" else 1


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive",type=Path)
    p.add_argument("destination",type=Path)
    p.add_argument("--browser")
    p.add_argument("--receipt",type=Path)
    raise SystemExit(main(p.parse_args()))
