"""Orchestrate fixed opaque task IDs; predictors receive no inventory or reference path."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main(args):
    data=args.root/"data/benchmark"
    inventory=data/"inventory.json"
    lock=read(inventory)
    if lock["status"]!="FROZEN_BEFORE_PREDICTION":
        raise ValueError("Benchmark must be frozen")
    cases=[r for r in lock["tasks"] if (not args.only or r["task_id"] in args.only) and
           (not args.sensitivity or r["split"]=="development")]
    if not cases or args.only and len(cases)!=len(set(args.only)):
        raise ValueError("No complete requested frozen task set")
    report=[]
    for task in cases:
        ident=task["task_id"]
        observed=data/"observed"/f"{ident}.json"
        queries=data/"queries"/f"{ident}.json"
        for key,file in (("observed",observed),("queries",queries)):
            if sha256(file.read_bytes()).hexdigest()!=task[key+"_sha256"]:
                raise ValueError(f"Frozen {key} changed: {ident}")
        cmd=[sys.executable,"-X","utf8","-B","-m","src.run_regions","controlled","--root",str(args.root),
             "--out",str(args.out),"--observed",str(observed),"--queries",str(queries)]
        if task["split"]=="confirmation":
            cmd.append("--confirmation")
        if args.sensitivity:
            cmd.extend(["--sensitivity",args.sensitivity])
        start=perf_counter()
        subprocess.run(cmd,cwd=args.root,check=True,timeout=240,capture_output=True,encoding="utf-8")
        report.append({"task_id":ident,"seconds":perf_counter()-start,
                       "method_scope":"FROZEN_I_LINE_AND_I_REGION_PLUS_S1" if task["split"]=="confirmation" else "DEVELOPMENT"})
        print(f"{ident} finished in {report[-1]['seconds']:.2f}s",flush=True)
    path=args.out/"runs/benchmark_run_registry.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as f:
        json.dump({"inventory_sha256":sha256(inventory.read_bytes()).hexdigest(),
                   "sensitivity":args.sensitivity,"tasks":report},f,indent=2)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=ROOT)
    p.add_argument("--only",nargs="+")
    p.add_argument("--sensitivity")
    a=p.parse_args()
    a.root=a.root.resolve()
    a.out=a.out.resolve()
    try:
        main(a)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr,file=sys.stderr)
        raise
