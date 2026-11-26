"""Trace actual controlled data reads in a minimal scratch view and change the queries."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from shutil import copyfile
import sys

ROOT = Path(__file__).resolve().parents[1]
TYPES = {".json", ".geojson", ".jsonl", ".zip", ".csv", ".gpkg", ".pbf", ".osm"}


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def isolated(case, scratch, output):
    from src.run_regions import controlled

    control = ROOT / "data/benchmark"
    inventory = read(control / "inventory.json")
    task = next(r for r in inventory["tasks"] if r["task_id"] == case)
    cfg = read(ROOT / "config/region.json")
    cfg["case_variants"] = ["I-REGION"]
    legacy = read(ROOT / "config/inference.json")["main"]
    scratch.mkdir(parents=True)
    observed = scratch / "observed" / f"{case}.json"
    queries = scratch / "queries" / f"{case}.json"
    changed = scratch / "changed" / "queries" / f"{case}.json"
    for path in (observed, queries, changed):
        path.parent.mkdir(parents=True, exist_ok=True)
    copyfile(control / "observed" / observed.name, observed)
    copyfile(control / "queries" / queries.name, queries)
    assert digest(observed) == task["observed_sha256"] and digest(queries) == task["queries_sha256"]
    query_doc = read(queries)
    if len(query_doc["queries"]) < 2:
        raise ValueError("Use an observed case with several distinct query pairs")
    # A subset and opposite direction are fixed independently of route success.
    q = query_doc["queries"][-1]
    q["source"],q["target"] = q["target"],q["source"]
    q["query_id"] = "ISOLATION-REVERSED-CONTROL"
    changed.write_text(json.dumps({"task_id":case,"queries":[q]}) + "\n", encoding="utf-8")
    attempts = []
    active = [False]
    allowed = {observed.resolve(), queries.resolve(), changed.resolve()}
    work = [(queries,scratch/"locked"),(changed,scratch/"alternate")]

    def access(event, args):
        if not active[0] or event != "open":
            return
        raw, mode, flags = args
        if not isinstance(raw,(str,bytes,os.PathLike)):
            return
        path = Path(os.fsdecode(raw)).resolve()
        if path.suffix.lower() not in TYPES:
            return
        reading = (int(flags) & (os.O_WRONLY | os.O_RDWR)) != os.O_WRONLY
        writing = (int(flags) & (os.O_WRONLY | os.O_RDWR)) != os.O_RDONLY
        generated = any(path.is_relative_to(out) for _,out in work)
        attempts.append(dict(path=path.relative_to(scratch).as_posix() if path.is_relative_to(scratch) else str(path),
                             access="read_write" if reading and writing else "read" if reading else "write"))
        if (reading and path not in allowed and not generated) or (writing and not generated):
            raise PermissionError(f"Unapproved controlled data access: {path}")
    sys.addaudithook(access)
    active[0] = True
    try:
        for query, out in work:
            controlled(observed,query,out,cfg,legacy,False)
    finally:
        active[0] = False
    a,b = [read(out/"runs/benchmark"/f"{case}.json") for _,out in work]
    locked_surface=a["variants"]["I-REGION"]["surface"]["sha256"]
    changed_surface=b["variants"]["I-REGION"]["surface"]["sha256"]
    stage_file=Path(a["read_log"][1]["path"])
    assert locked_surface==changed_surface
    assert (work[0][1]/stage_file).read_bytes()==(work[1][1]/stage_file).read_bytes()
    assert any(t["path"]=="queries/"+queries.name and t["access"]=="read" for t in attempts)
    assert any(t["path"]=="changed/queries/"+queries.name and t["access"]=="read" for t in attempts)
    assert all(r["read_log"][0]["role"]=="observed" and r["read_log"][-1]["role"]=="queries" for r in [a,b])
    for attempt in attempts:
        if "reference" in attempt["path"].split("/") or "inputs" in attempt["path"].split("/"):
            raise ValueError("Historical reference unexpectedly read")
    result=dict(status="PASS",task_id=case,scope="Python open audit hook and minimal input data mirror; not OS isolation",
                originals=task["query_count"],alternate=1,surface_sha256=locked_surface,
                surface_byte_identical=True,data_reads_and_writes=attempts,
                actual_reference_reads=0,external_requests=0)
    with output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("task")
    p.add_argument("--scratch",type=Path,default=ROOT/"runtime/benchmark_observed_replay")
    p.add_argument("--output",type=Path,default=ROOT/"audits/observed_isolation_replay.json")
    a=p.parse_args()
    isolated(a.task,a.scratch.resolve(),a.output.resolve())
