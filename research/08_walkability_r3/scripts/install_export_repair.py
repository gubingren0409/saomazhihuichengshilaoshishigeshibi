"""Install verified serialization-only re-exports, preserving the first prediction receipts."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sign(path):
    return sha256(path.read_bytes()).hexdigest()


def run(root):
    all_records=[]
    changes=[]
    base=root/"runtime/export_repair_v2"
    for run in ("main","grid_1p5m","proximity_8m"):
        repaired=base/run
        current=root if run=="main" else root/"runtime/sensitivity"/run
        saved=root/"runtime/export_before"/run
        inventory=load(repaired/"runs/benchmark_run_registry.json")
        for task in inventory["tasks"]:
            task=task["task_id"]
            rel=Path("runs/benchmark")/(task+".json")
            old,new=load(current/rel),load(repaired/rel)
            def semantic(value):
                return {k:{a:b for a,b in v.items() if a!="route_seconds"}
                        for k,v in value["variants"].items()}
            if old["queries"]!=new["queries"] or semantic(old)!=semantic(new):
                raise ValueError(f"Export repair changed prediction or queries: {task}")
            relpaths=[rel]
            for file in sorted((repaired/"data/benchmark_predictions").glob(task+"_*.geojson")):
                path=file.relative_to(repaired)
                if sign(repaired/path)!=sign(current/path):
                    relpaths.append(path)
            record={"run":run,"task_id":task,"predictions_identical":True,"updated_members":[]}
            for path in relpaths:
                old_file,new_file=current/path,repaired/path
                backup=saved/path
                if backup.exists() or not all(p.resolve().is_relative_to(root) for p in (old_file,new_file,backup)):
                    raise ValueError("Invalid or already installed repair path")
                record["updated_members"].append({"path":path.as_posix(),"old_sha256":sign(old_file),
                                                 "new_sha256":sign(new_file)})
                changes.append((old_file,new_file,backup))
            all_records.append(record)
    for old_file,new_file,backup in changes:
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(old_file,backup)
        shutil.copy2(new_file,old_file)
    with (root/"audits/export_repair.json").open("x",encoding="utf8") as f:
        json.dump({"status":"TOPOLOGY_SERIALIZATION_ONLY","metric_authority":"EPSG:32651",
                   "tasks":all_records},f,ensure_ascii=False,indent=2)
    print(f"{len(all_records)} task runs checked and installed; {len(changes)} receipts/files preserved and updated")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    run(p.parse_args().root.resolve())
