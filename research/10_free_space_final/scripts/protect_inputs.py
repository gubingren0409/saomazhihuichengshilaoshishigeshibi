"""Read-only hashes/status of precisely used historical dependencies and Git.

No git mutation, index refresh, checkout, reset or cleanup is performed.
"""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sign(path):
    h=sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def git_state(path):
    out={"path":str(path)}
    for key,args in (("head",["rev-parse","HEAD"]),
                     ("tracked_status",["status","--porcelain=v1","-uno"]),
                     ("git_dir",["rev-parse","--absolute-git-dir"])):
        r=subprocess.run(["git","--no-optional-locks","-C",str(path),*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
        out[key]=r.stdout.strip();out[key+"_code"]=r.returncode
    if out['git_dir_code']==0:
        idx=Path(out['git_dir'])/'index'
        out['index_sha256']=sign(idx) if idx.is_file() else None
    return out


def snapshot(prior,repos):
    mf=json.loads((prior/'data/task_manifest.json').read_text(encoding='utf-8'))
    selected=[r for r in mf['instances'] if r['masking_mode'] in {'G','N'} and r['context_radius_m']==80]
    files={prior/'data/task_manifest.json',prior/'data/mask_dependency_ledger.jsonl',prior/'data/context_inventory.jsonl'}
    for r in selected:
        for key in ('observed','query','reference'):files.add(prior/r[key])
        files.add(prior/'data/predictions'/r['id']/'M1.json')
    files.update(prior/p for p in ('src/region.py','src/context_policy.py','src/region_routing.py','src/predict.py','config/frozen_region.json','config/methods.json','delivery/OPEN_REVIEW.zip','data/e5/task_manifest.json','data/e5/observed/NORTH_160.json','data/e5/queries/NORTH.json','data/e5/north_route_graph.json'))
    files.update(prior.glob('frozen_r3/inputs/rev1/frozen_r4/data/source/*osm.json'))
    items=[]
    for p in sorted(files,key=str):
        if not p.is_file():raise FileNotFoundError(p)
        items.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sign(p)})
    return {'scope':'EXACT_USED_HISTORICAL_FILES_AND_TWO_GIT_REPOSITORIES_NOT_WHOLE_WORKSPACE',
            'files':items,'git':[git_state(r) for r in repos]}


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['before','after']);p.add_argument('--prior',type=Path,default=ROOT.parent/'OSM_GEOAPIFY_R4_WALKABILITY_R4_CONTEXT')
    p.add_argument('--repo',action='append',type=Path,required=True);args=p.parse_args()
    doc=snapshot(args.prior,args.repo)
    dest=ROOT/'audits'/('protection_'+args.mode+'.json')
    if args.mode=='after':
        before=json.loads((ROOT/'audits/protection_before.json').read_text(encoding='utf-8'))
        doc['files_unchanged']=before['files']==doc['files'];doc['git_unchanged']=before['git']==doc['git']
        doc['status']='PASS' if doc['files_unchanged'] and doc['git_unchanged'] else 'FAIL'
    else:doc['status']='BASELINE_RECORDED'
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x',encoding='utf-8') as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':doc['status'],'files':len(doc['files']),'git_repos':len(doc['git'])}))


if __name__=='__main__':main()
