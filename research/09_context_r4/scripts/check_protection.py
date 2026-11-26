"""Recheck original file digests and Git stage/status without writing old workspaces."""
import argparse
from hashlib import file_digest,sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sig(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()


def check(r):
    path=Path(r["path"])
    return path.is_file() and path.stat().st_size==r["bytes"] and sig(path)==r["sha256"]


def main(output):
    before=json.loads((ROOT/"audits/protection_before.json").read_text(encoding="utf8"))
    items=[before["attachment"],before["r3_package"],*before["live_r3_checks"]]
    changed=[r["path"] for r in items if not check(r)]
    states={}
    for work,receipt in before["git"].items():
        def git(*args):
            return subprocess.check_output(["git","--no-optional-locks","-C",work,*args])
        states[work]={"head_unchanged":git("rev-parse","HEAD").decode().strip()==receipt["head"],
                      "index_unchanged":check(receipt["index"]),
                      "tracked_status_unchanged":sha256(git("status","--porcelain=v1","-z","-uno")).hexdigest()==receipt["status_sha256"]}
    status="PASS" if not changed and all(all(v.values()) for v in states.values()) else "CHANGED"
    with output.open("x",encoding="utf8") as f:
        json.dump({"status":status,"protected_files":len(items),"changed":changed,"git":states},f,indent=2,ensure_ascii=False)
    print(status,len(items))
    return 0 if status=="PASS" else 1


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"audits/protection_after.json")
    raise SystemExit(main(p.parse_args().output))
