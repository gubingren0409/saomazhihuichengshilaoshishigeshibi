"""Verify a sealed ZIP, then rebuild three G tasks and one real obstacle in a fresh directory."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from time import perf_counter
from zipfile import ZipFile

from seal_context import FROZEN, inspect, check_nested

SAMPLE=("Wc4183046a70_G_080","W6daddd19fdb_G_160","W745941f0f92_G_080","W0440b97497a_N_080")
PARENTS=tuple(ident.split("_")[0] for ident in SAMPLE)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def extract(path,out):
    out.mkdir(parents=True)
    with ZipFile(path) as z:
        names=z.namelist()
        if z.testzip() is not None or len(set(n.casefold() for n in names))!=len(names) or sum(
                i.file_size for i in z.infolist())>2*1024**3:
            raise ValueError("CRC or archive capacity check failed")
        rows=json.loads(z.read("MANIFEST.json"))["entries"]
        if set(names)!={"MANIFEST.json",*(r["path"] for r in rows)} or len(rows)+1!=len(names):
            raise ValueError("Archive membership mismatch")
        for row in rows:
            path=row["path"]
            if stat.S_ISLNK(z.getinfo(path).external_attr>>16):
                raise ValueError("Symbolic links are not permitted")
            data=z.read(path)
            inspect(path,data)
            if path==FROZEN:
                check_nested(data)
            if (row["bytes"],row["sha256"])!=(len(data),sha256(data).hexdigest()):
                raise ValueError(f"Manifest checksum failed: {path}")
            target=out/path
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as f:
                f.write(data)
    return len(names)


def cmd(root,args,logs,timeout=240):
    t=perf_counter()
    proc=subprocess.run([sys.executable,"-X","utf8","-B",*args],cwd=root,encoding="utf8",
                        capture_output=True,timeout=timeout)
    logs.append({"args":args,"seconds":perf_counter()-t,"returncode":proc.returncode,"stdout":proc.stdout[-1200:]})
    if proc.returncode:
        print(proc.stderr,file=sys.stderr)
        proc.check_returncode()
    print(f"PASS {args[0]} {perf_counter()-t:.1f}s",flush=True)


def normalize(v):
    ignored={"elapsed_s","peak_working_set_bytes","prediction_sha256"}
    if isinstance(v,dict):
        return {k:normalize(w) for k,w in v.items() if k not in ignored}
    if isinstance(v,list):
        return [normalize(w) for w in v]
    return v


def keyed(rows):
    return {(r["id"],r["method"]):normalize(r) for r in rows if r["id"] in SAMPLE}


def main(args):
    root=args.destination.resolve()/"extracted"
    archive=args.archive.resolve()
    members=extract(archive,root)
    logs=[]
    cmd(root,["scripts/stage_frozen.py"],logs)
    cmd(root,["src/build_observed.py","--output","data/replay_export","--parents",*PARENTS],logs)
    regenerated={r["id"]:r for r in read(root/"data/replay_export/task_manifest.json")["instances"]}
    official={r["id"]:r for r in read(root/"data/task_manifest.json")["instances"]}
    frozen_keys=("observed_sha256","query_sha256","reference_sha256","mask_sha256",
                 "prediction_domain_sha256","evaluation_domain_sha256","grid_sha256")
    observations={}
    for ident in SAMPLE:
        observations[ident]=all(regenerated[ident][key]==official[ident][key] for key in frozen_keys)
    if not all(observations.values()):
        raise ValueError("Replay observed geometry or invariant hash mismatch")
    replay=root/"runtime/replay_results"
    for method in ("M0","M1"):
        cmd(root,["scripts/run_matrix.py","--manifest","data/replay_export/task_manifest.json","--ids",*SAMPLE,
                   "--method",method,"--out",str(replay),"--receipt","sealed","--jobs","3"],logs)
    subset_predictions={}
    for ident in SAMPLE:
        for method in ("M0","M1"):
            name=f"data/predictions/{ident}/{method}.json"
            a,b=root/name,replay/name
            subset_predictions[f"{ident}/{method}"]=normalize(read(a))==normalize(read(b))
    if not all(subset_predictions.values()):
        raise ValueError("Replayed classification, provenance, or routes differ")
    score=replay/"runs/replayed_metrics.json"
    cmd(root,["src/score_context.py","--predictions",str(replay/"data/predictions"),"--out",str(score),
              *[arg for p in PARENTS for arg in ("--task",p)]],logs)
    compare_score=keyed(read(score)["rows"])==keyed(read(root/"runs/context_metrics.json")["rows"])
    if not compare_score:
        raise ValueError("Independently rescored metrics differ")
    # Overlay only the checked replay outputs on the extracted review copy before redrawing.
    for ident in SAMPLE:
        for method in ("M0","M1"):
            name=f"data/predictions/{ident}/{method}.json"
            shutil.copyfile(replay/name,root/name)
    visual_root=root/"runtime/redrawn"
    html=visual_root/"visuals/index.html"
    cmd(root,["src/build_context_visuals.py","--output",str(html)],logs,timeout=300)
    cmd(root,["scripts/check_context_payload.py","--html",str(html)],logs)
    html_identical=digest(html)==digest(root/"visuals/index.html")
    if not html_identical:
        raise ValueError("Redrawn HTML differs from the sealed page")
    images={}
    if args.browser:
        figures=visual_root/"visuals/figures"
        cmd(root,["scripts/check_context_visuals.py","--root",str(visual_root),"--figures",str(figures),
                  "--browser",args.browser,"--receipt",str(visual_root/"browser.json")],logs,timeout=240)
        for f in sorted(figures.iterdir()):
            same=root/"visuals/figures"/f.name
            images[f.name]=same.is_file() and digest(f)==digest(same)
        if not all(images.values()):
            raise ValueError("Redrawn figure differs from the sealed page")
    receipt={"status":"PASS","scope":"THREE_REVISED_G_AND_ONE_REAL_NEGATIVE_SAMPLE_NOT_FULL_MATRIX_REPLAY",
             "archive_sha256":digest(archive),"members":members,"zip_crc_sha_safe_members":"PASS",
             "observed_and_reference_hashes":observations,"predictions_routes_and_evidence":subset_predictions,
             "independent_rescoring_matches":compare_score,"redrawn_html_matches":html_identical,
             "browser":"ACTUALLY_REPLAYED" if args.browser else "NOT_RUN",
             "redrawn_figures":images,"commands":logs}
    if args.receipt:
        with args.receipt.open("x",encoding="utf8") as f:
            json.dump(receipt,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k!="commands"},ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive",type=Path)
    p.add_argument("destination",type=Path)
    p.add_argument("--browser")
    p.add_argument("--receipt",type=Path)
    main(p.parse_args())
