"""Actually rebuild S0/S1 grass exceptions and fixed south route, read-only upstream.

The trusted historical implementation runs in its own Python process and writes
only into this task's fresh runtime directory. Required code and data are first
matched byte-for-byte with the nested frozen archives.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--historical-root',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'runtime/s1_regression_actual')
    p.add_argument('--receipt',type=Path,default=ROOT/'audits/s1_regression_actual.json')
    args=p.parse_args();old=args.historical_root.resolve();out=args.output.resolve()
    if not out.is_relative_to(ROOT) or out.exists():raise ValueError('Use a new output directory inside the new task')
    start=perf_counter();arch=ROOT/'frozen_context/input_contract/frozen/WALKABILITY_R3_OPEN_REVIEW.zip'
    if sign(arch)!='d623af231c6eabeace1d3c8e284787a51b7d83782c6c8f7990d16b27f5c0cd0e':raise ValueError('Wrong R3 archive')
    z3=ZipFile(arch);z2=ZipFile(io.BytesIO(z3.read('references/R2_OPEN_REVIEW.zip')))
    zrev=ZipFile(io.BytesIO(z2.read('references/frozen_archives/R4_REV1_OPEN_REVIEW.zip')))
    znorth=ZipFile(io.BytesIO(z2.read('references/frozen_archives/NORTH_ACCESS_R1_OPEN_REVIEW.zip')))
    bindings=[]
    def match(path,archive,name):
        b=archive.read(name)
        if path.read_bytes()!=b:raise ValueError(('Unfrozen dependency',str(path),name))
        bindings.append({'historical_relative_path':path.relative_to(old).as_posix(),'member':name,'sha256':sha256(b).hexdigest(),'bytes':len(b)})
    for member in ('src/run_semantics.py','src/semantics.py'):
        match(old/member,z3,member)
    for member in ('src/native_adapter.py','src/route_measure.py','data/edge_evidence.jsonl','data/entrance_approach.json',
                   'frozen_r4/runs/source_scene_contracts.json','frozen_r4/src/frozen_r1/local_route.py'):
        match(old/'inputs/rev1'/member,zrev,member)
    scenes=read(old/'inputs/rev1/frozen_r4/runs/source_scene_contracts.json')['scenes']
    for scene in scenes:
        match(old/'inputs/rev1/frozen_r4'/scene['osm_clip'],zrev,'frozen_r4/'+scene['osm_clip'])
    match(old/'inputs/north/runs/experiment.json',znorth,'runs/experiment.json')
    # No imports from this task's src namespace are performed by the child.
    child='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from src.run_semantics import execute;execute(Path(sys.argv[1]),Path(sys.argv[2]))'
    out.mkdir(parents=True)
    cmd=[sys.executable,'-X','utf8','-B','-c',child,str(old),str(out)]
    done=subprocess.run(cmd,cwd=out,capture_output=True,text=True,encoding='utf-8',timeout=900)
    (out/'stdout.txt').write_text(done.stdout,encoding='utf-8');(out/'stderr.txt').write_text(done.stderr,encoding='utf-8')
    if done.returncode:
        print(done.stderr,file=sys.stderr);raise RuntimeError('Actual S0/S1 replay failed')
    result=read(out/'runs/semantics.json');frozen_result=json.loads(z3.read('runs/semantics.json'))
    checks={}
    for member in ('data/semantics_edges.csv','data/semantics_routes.geojson'):
        checks[member]={'byte_identical':(out/member).read_bytes()==z3.read(member),
                        'sha256':sign(out/member),'bytes':(out/member).stat().st_size}
    def select(d):
        return {'restored_unique_segments':d['spatial_geometry_policy_dedup']['restored_segments'],
            'restored_directed_arcs':d['spatial_geometry_policy_dedup']['restored_directed_arcs'],
            'restored_native_length_m':d['spatial_geometry_policy_dedup']['restored_native_length_m'],
            'restored_grass_overlap_m':d['spatial_geometry_policy_dedup']['restored_grass_overlap_m'],
            'routes':{mode:{role:{k:d['variants'][mode][role][k] for k in ('status','length_m','target_residual_m') if k in d['variants'][mode][role]}
                            for role in ('north_fixed','south','north_exit')}for mode in ('S0','S1')}}
    actual,expected=select(result),select(frozen_result)
    doc={'status':'PASS' if actual==expected and all(r['byte_identical']for r in checks.values()) else 'FAIL',
        'role':'FREE_CONSTRAINTS_DATA_ROLE_ACTUAL_FROZEN_PURE_FUNCTION_REGRESSION',
        'scope':'S0_AND_S1_REBUILT_SIX_CLIPS_AND_FIXED_SOUTH_ROUTE; NOT_A_NEW_REGION_RECOVERY_EXPERIMENT',
        'historical_code_reused':True,'main_F0_or_F1_code_called':False,
        'actually_executed_subprocess':True,'subprocess_exit_code':done.returncode,'source_bindings':bindings,
        'actual':actual,'frozen_comparison':expected,'artifact_checks':checks,
        'output_relative_path':out.relative_to(ROOT).as_posix(),'elapsed_s':perf_counter()-start,
        'external_requests':0,'region_builds':0,'reference_recovery_or_public_access_claim':False}
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    with args.receipt.open('x',encoding='utf-8') as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(done.stdout)
    print(json.dumps({'status':doc['status'],'actual':actual,'elapsed_s':doc['elapsed_s']},ensure_ascii=False))


if __name__=='__main__':main()
