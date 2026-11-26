"""Independent subprocess proof of input order, reference denial and query invariance."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.context_audit_common import ROOT, hash_file, read, require, write

PROBE = r"""
import json, os, runpy, sys
from pathlib import Path

work=Path.cwd().resolve()
experiment_root=Path(sys.argv[1]).resolve()
entry=experiment_root/'src/predict.py'
sys.argv=[str(entry),*sys.argv[2:]]
attempts=[]
outside=[]
def inspect(event,args):
    if event != 'open' or not isinstance(args[0],(str,bytes,os.PathLike)):
        return
    path=Path(os.fsdecode(args[0])).resolve()
    if path.parent==work:
        writing=bool(args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        attempts.append({'path':path.name,'operation':'WRITE' if writing else 'READ_ATTEMPT'})
    elif path.is_relative_to(experiment_root) and any(part in path.parts for part in ('data','frozen_r3','reference')):
        outside.append(str(path))
sys.addaudithook(inspect)
runpy.run_path(str(entry),run_name='__main__')
print(json.dumps({'scratch_attempts':attempts,'outside_data_attempts':outside},separators=(',',':')))
"""


def probe(root, row, method, official):
    files={
        "observed.json":root/row["observed"],
        "local_config.json":root/"config/frozen_region.json",
        "methods.json":root/"config/methods.json",
    }
    queries=read(root/row["query"])
    original=[q["query_id"] for q in queries["queries"]]
    require(len(original)>=2,"Independent permutation needs at least two locked queries")
    queries["queries"]=list(reversed(queries["queries"]))
    with tempfile.TemporaryDirectory(prefix="independent_context_",dir=root/"runtime") as tmp:
        scratch=Path(tmp)
        for name, path in files.items():
            shutil.copy2(path,scratch/name)
        (scratch/"query.json").write_text(json.dumps(queries,ensure_ascii=False),encoding="utf8")
        # A harmless decoy proves application denial rather than a missing-file error.
        # This contains no case data, labels, geometry or actual reference bytes.
        (scratch/"reference.json").write_text('{"sentinel":"NO_CASE_DATA"}',encoding="utf8")
        if method=="M1":
            m0=read(root/"data/predictions"/row["id"]/"M0.json")
            (scratch/"m0_surface.json").write_text(json.dumps(
                {"observed_sha256":m0["observed_sha256"],"surface":m0["surface"]},
                ensure_ascii=False,separators=(",",":")),encoding="utf8")
        argv=[sys.executable,"-X","utf8","-B","-c",PROBE,str(root),"--method",method,
              "--input-id",row["id"],"--radius",str(row["context_radius_m"]),
              "--config-sha",official["config_sha256"],"--code-sha",official["code_sha256"]]
        call=subprocess.run(argv,cwd=scratch,encoding="utf8",capture_output=True,timeout=180)
        require(call.returncode==0, f"Independent predictor probe failed: {call.stderr}")
        trace=json.loads(call.stdout.strip().splitlines()[-1])
        prediction=read(scratch/"prediction.json")
        require(not trace["outside_data_attempts"],"Predictor attempted to open source or reference outside its scratch")
        actions=[(r["path"],r["operation"]) for r in trace["scratch_attempts"]]
        require(actions.count(("reference.json","READ_ATTEMPT"))==1 and
                actions.count(("query.json","READ_ATTEMPT"))==2, "Missing negative read attempt")
        stage=actions.index(("surface.freeze","WRITE"))
        require([i for i,x in enumerate(actions) if x==("query.json","READ_ATTEMPT")][1]>stage,
                "Independent file-open hook saw query loaded before surface")
        denied={r["role"] for r in prediction["read_log"] if r["event"]=="DENIED_OPEN"}
        require(denied=={"DENIED_REFERENCE_PROBE","DENIED_EARLY_QUERY_PROBE"},
                "Application-level denied-read roles differ")
        require(prediction["surface"]==official["surface"] and prediction["routes"]==official["routes"],
                "Surface/route changed after query order permutation")
        return {"status":"PASS","method":method,"input_id":row["id"],"query_count":len(original),
                "query_order_before":original,"query_order_after":[q["query_id"] for q in queries["queries"]],
                "reference_decoy_only":True,"same_authoritative_surface":True,"same_fixed_query_route_geometry":True,
                "surface_sha256":prediction["surface"]["sha256"],"external_requests":0,
                "observed_sha256":hash_file(files["observed.json"]),"independent_actual_file_open_trace":trace,
                "worker_read_events":prediction["read_log"],
                "scope":"INDEPENDENT PYTHON OPEN-HOOK PLUS WORKER ALLOWLIST, NOT OS SANDBOX"}


def main(args):
    root=args.root.resolve()
    row=next(r for r in read(root/"data/task_manifest.json")["instances"] if r["id"]==args.id)
    official=read(root/"data/predictions"/row["id"]/(args.method+".json"))
    result=probe(root,row,args.method,official)
    write(args.out or root/"audits/context_isolation_probe.json",result)
    print(f"Independent isolation probe: {args.id} {args.method}, same frozen surface and fixed routes")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id")
    parser.add_argument("--method",choices=("M0","M1"),default="M1")
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path)
    main(parser.parse_args())
