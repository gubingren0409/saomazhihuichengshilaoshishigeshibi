"""Read-only comparison of original archive, live source bindings and Git state."""
import argparse
from hashlib import file_digest, sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as f:
        return file_digest(f,"sha256").hexdigest()


def verify(entry):
    p=Path(entry["path"])
    return p.is_file() and p.stat().st_size==entry["bytes"] and digest(p)==entry["sha256"]


def main(out):
    inventory=json.loads((ROOT/"audits/INPUT_INVENTORY.json").read_text(encoding="utf-8"))
    rows=[inventory["r3_attachment"]]
    for record in inventory["original_workspaces"].values():
        rows.append(record["archive"])
        rows.extend(record["live_engine_and_data_checks"])
    failed=[r["path"] for r in rows if not verify(r)]
    git={}
    for folder,old in inventory["git"].items():
        def run(*args):
            return subprocess.check_output(["git","--no-optional-locks","-C",folder,*args])
        git[folder]={"head":run("rev-parse","HEAD").decode().strip()==old["head"],
                     "index":verify(old["index"]),
                     "tracked_status":sha256(run("status","--porcelain=v1","-z","-uno")).hexdigest()==old["status_sha"]}
    clean=not failed and all(all(v.values()) for v in git.values())
    with out.open("x",encoding="utf8") as f:
        json.dump({"status":"PASS" if clean else "CHANGED","protected_files":len(rows),
                   "changed_files":failed,"git":git},f,ensure_ascii=False,indent=2)
    print(f"Protected files: {len(rows)}; status: {'PASS' if clean else 'CHANGED'}")
    return 0 if clean else 1


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"audits/PROTECTION_AFTER.json")
    raise SystemExit(main(p.parse_args().output))
