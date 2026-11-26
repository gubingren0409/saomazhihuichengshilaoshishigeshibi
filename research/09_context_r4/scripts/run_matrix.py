"""Run locked observed instances in fresh directories, without exposing references to workers."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
CODE=("src/region.py","src/region_routing.py","src/context_policy.py","src/predict.py")


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def combined(paths):
    return sha256("".join(sha(p) for p in paths).encode()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_members(root,row):
    seen={}
    for role,field in (("observed","observed"),("query","query")):
        path=root/row[field]
        if not path.resolve().is_relative_to(root/"data") or path.is_symlink() or sha(path)!=row[field+"_sha256"]:
            raise ValueError(f"{role} member invalid: {row['id']}")
        seen[role]=path
    return seen


def process(root,out,row,method,code,conf):
    started=perf_counter()
    actual=read_members(root,row)
    output=out/"data/predictions"/row["id"]/(method+".json")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    workers=root/"runtime/workers"
    workers.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="case_",dir=workers) as tmp:
        work=Path(tmp)
        for dest,source in {"observed.json":actual["observed"],"query.json":actual["query"],
                            "local_config.json":root/"config/frozen_region.json",
                            "methods.json":root/"config/methods.json"}.items():
            shutil.copyfile(source,work/dest)
        if method=="M1":
            m0=load(output.parent/"M0.json")
            if m0["observed_sha256"]!=row["observed_sha256"]:
                raise ValueError("M0 cache is not from this observed input")
            (work/"m0_surface.json").write_text(json.dumps(
                {"observed_sha256":m0["observed_sha256"],"surface":m0["surface"]},
                ensure_ascii=False,separators=(",",":")),encoding="utf8")
        if row.get("natural"):
            path=root/row["route_graph"]
            if sha(path)!=row["route_graph_sha256"]:
                raise ValueError("E5 route-only graph changed")
            shutil.copyfile(path,work/"route_graph.json")
        cmd=[sys.executable,"-X","utf8","-B",str(root/"src/predict.py"),"--input-id",row["id"],"--method",method,
             "--radius",str(row["context_radius_m"]),"--config-sha",conf,"--code-sha",code]
        if row.get("natural"):
            cmd.append("--natural")
        done=subprocess.run(cmd,cwd=work,encoding="utf8",capture_output=True,timeout=180)
        if done.returncode:
            raise RuntimeError(f"{row['id']} {method}: {done.stderr}")
        with (work/"prediction.json").open("rb") as stream, output.open("xb") as target:
            shutil.copyfileobj(stream,target)
    print(f"{row['id']} {method} {perf_counter()-started:.2f} s",flush=True)
    return {"id":row["id"],"method":method,"elapsed_s":perf_counter()-started,"prediction_sha256":sha(output)}


def main(args):
    root=args.root.resolve()
    out=args.out.resolve()
    manifest=args.manifest or root/"data/task_manifest.json"
    data=load(manifest)
    code=combined([root/f for f in CODE])
    conf=combined([root/"config/frozen_region.json",root/"config/methods.json"])
    locked=load(root/"config/methods.json")["M0"]
    for key,file in (("region_sha256","src/region.py"),("routing_sha256","src/region_routing.py"),
                     ("config_sha256","config/frozen_region.json")):
        if sha(root/file)!=locked[key]:
            raise ValueError(f"Frozen M0 {file} changed")
    rows=[r for r in data["instances"] if (not args.ids or r["id"] in args.ids) and
          (not args.modes or r["masking_mode"] in args.modes) and
          not (args.method=="M1" and "ORIGINAL" in r["id"])]
    if not rows or args.ids and set(args.ids)!={r["id"] for r in rows}:
        raise ValueError("Empty or incomplete requested set")
    if args.resume:
        rows=[r for r in rows if not (out/"data/predictions"/r["id"]/(args.method+".json")).exists()]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results=list(pool.map(lambda r:process(root,out,r,args.method,code,conf),rows))
    receipt=out/"runs"/f"execution_{args.receipt}_{args.method}.json"
    receipt.parent.mkdir(parents=True,exist_ok=True)
    with receipt.open("x",encoding="utf8") as f:
        json.dump({"method":args.method,"manifest_sha256":sha(manifest),"code_sha256":code,
                   "config_sha256":conf,"new_runs":len(results),"runs":results},f,indent=2)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--method",choices=("M0","M1"),required=True)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=ROOT)
    p.add_argument("--manifest",type=Path)
    p.add_argument("--ids",nargs="+")
    p.add_argument("--modes",nargs="+")
    p.add_argument("--jobs",type=int,default=4,choices=range(1,7))
    p.add_argument("--receipt",required=True)
    p.add_argument("--resume",action="store_true")
    main(p.parse_args())
