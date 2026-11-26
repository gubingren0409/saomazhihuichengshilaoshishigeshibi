"""Explicitly reuse only frozen observed-only classifier surfaces, never old routes."""
import json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
old=ROOT/'frozen_context';a=read(old/'data/predictions/NORTH_160/M0.json');b=read(old/'data/predictions/NORTH_160/M1.json')
assert a['observed_sha256']==b['observed_sha256']==sha(ROOT/'data/e5/observed/NORTH_160.json')
assert digest(a['surface'])==digest(b['surface'])
bindings={p:sha(old/p) for p in ['src/region.py','src/context_policy.py','config/frozen_region.json','config/methods.json']}
for p,target in [('src/region.py','src/region.py'),('src/context_policy.py','src/context_policy.py'),('config/frozen_region.json','config/frozen_region.json'),('config/methods.json','config/historical_methods.json')]:assert bindings[p]==sha(ROOT/target)
cache=dict(observed_sha256=b['observed_sha256'],classifier_bindings=bindings,M0=a['surface'],M1=b['surface'])
dst=ROOT/'data/classifier_cache/NORTH_160.json';dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(cache,separators=(',',':')),encoding='utf8')
# Preserve the stopped-batch upper bound; add a source-stage justified correction.
receipt=ROOT/'runs/superseded/R1_partition_defect/runs/executions/W71107d26ecd_G_080_7p_zah9i_INTERRUPTED.json'
work=ROOT/'runs/superseded/R1_partition_defect/interrupted_workers/W71107d26ecd_G_080_7p_zah9i'
assert set(p.name for p in work.iterdir())=={'observed.json','query.json','config.json','historical_methods.json','guards.json'}
adjust={'original_receipt':receipt.relative_to(ROOT).as_posix(),'original_receipt_sha256':sha(receipt),'original_conservative_upper':4,'revised_stage_upper':2,'adjustment':-2,
        'basis':'Frozen R1 source writes constraints.json after M0/M1 and before MC/F0; stopped complete preserved worker has only five inputs, no constraints or freeze. Independent source-stage review confirms upper bound, not exact count.',
        'preserved_worker_inputs':{p.name:sha(p) for p in work.iterdir()},'historical_cache':dst.relative_to(ROOT).as_posix(),'cache_sha256':sha(dst),'cache_role':'NATURAL_UNMASKED_OBSERVED_ONLY_CLASSIFIER_SURFACE_NOT_QUERY_OR_REFERENCE',
        'classifier_executed_anew_for_north':False,'new_north_region_builds':2}
(ROOT/'runs/budget_adjustments.json').write_text(json.dumps({'adjustments':[adjust],'total_adjustment':-2},indent=2),encoding='utf8')
backup=ROOT/'runs/production_versions/MAIN_R4';backup.mkdir(parents=True,exist_ok=True)
for p in ['src/predict_free.py','scripts/run_free.py','config/predictor_binding.json']:shutil.copyfile(ROOT/p,backup/Path(p).name)
print('cache',dst,'budget stage correction -2; old upper-bound receipt unchanged')
