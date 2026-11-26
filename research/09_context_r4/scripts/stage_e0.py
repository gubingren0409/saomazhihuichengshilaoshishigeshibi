"""Bind exact archival observations and queries for the fixed E0 replay subset."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
PARENTS=("Wc4183046a70","W6daddd19fdb","W745941f0f92","W0440b97497a")


def main():
    original=ROOT/"frozen_r3/data/benchmark"
    frozen={r["task_id"]:r for r in json.loads((original/"inventory.json").read_text(encoding="utf8"))["tasks"]}
    target=ROOT/"data/e0"
    target.mkdir(exist_ok=True)
    rows=[]
    for parent in PARENTS:
        base=frozen[parent]
        row={"id":parent+"_H0_ORIGINAL_EXPORT","parent_task_id":parent,"masking_mode":"H0_ORIGINAL_EXPORT",
             "context_radius_m":40,"group":base["group"],"kind":base["kind"],"label":base["label"],"split":base["split"]}
        for dst,src in (("observed","observed"),("query","queries"),("reference","reference")):
            old=original/src/(parent+".json")
            new=target/src/old.name
            new.parent.mkdir(exist_ok=True)
            shutil.copyfile(old,new)
            row[dst]=new.relative_to(ROOT).as_posix()
            row[dst+"_sha256"]=sha256(new.read_bytes()).hexdigest()
        rows.append(row)
    with (target/"task_manifest.json").open("x",encoding="utf8") as stream:
        json.dump({"status":"FROZEN_EXACT_E0_SUBSET","instances":rows},stream,indent=2)


if __name__=="__main__":
    main()
