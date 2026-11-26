"""Append-only stage-bound review; never rewrite the interrupted producer receipt."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def main():
    archived=ROOT/'runs/superseded/R1_partition_defect'
    worker=archived/'interrupted_workers/W71107d26ecd_G_080_7p_zah9i'
    receipt=archived/'runs/executions/W71107d26ecd_G_080_7p_zah9i_INTERRUPTED.json'
    source=archived/'code/predict_free.py';code=source.read_text(encoding='utf-8')
    required=["m0=build_surface(obs,cfg)","m1,features=enhance(m0,obs,cfg,methods['M1'])",
              "put('constraints.json',common)","mc=build_free_surface(m1,common,default=False)",
              "f0=build_free_surface(m1,common,default=True)"]
    pos=[code.index(x) for x in required]
    files=sorted(p.name for p in worker.iterdir())
    input_names=['config.json','guards.json','historical_methods.json','observed.json','query.json']
    assertions={'source_call_order':pos==sorted(pos),'preserved_directory_has_only_five_inputs':files==input_names,
        'constraints_marker_absent':not(worker/'constraints.json').exists(),
        'archived_worker_has_no_output_deletion_call':all(t not in code for t in ('.unlink(','.remove(','.rmdir(','shutil.rmtree(')),
        'original_receipt_retains_four':read(receipt)['region_builds']==4}
    old=ROOT/'frozen_context';a=read(old/'data/predictions/NORTH_160/M0.json');b=read(old/'data/predictions/NORTH_160/M1.json')
    binding=[('src/region.py','src/region.py'),('src/context_policy.py','src/context_policy.py'),
             ('config/frozen_region.json','config/frozen_region.json'),('config/methods.json','config/historical_methods.json')]
    byte_binding=[{'frozen':x,'current':y,'sha256':sign(old/x),'byte_identical':(old/x).read_bytes()==(ROOT/y).read_bytes()} for x,y in binding]
    query_open=min(r['sequence'] for r in b['read_log']if r['role']=='QUERY')
    freeze=min(r['sequence']for r in b['read_log']if r['role']=='SURFACE_FROZEN')
    checks={'M0_M1_entire_surface_equal':a['surface']==b['surface'],
        'M0_M1_observed_sha_equal':a['observed_sha256']==b['observed_sha256'],
        'actual_current_observed_sha_matches':sign(ROOT/'data/e5/observed/NORTH_160.json')==b['observed_sha256'],
        'old_freeze_preceded_query':freeze<query_open,
        'frozen_algorithm_config_exact':all(r['byte_identical']for r in byte_binding)}
    doc={'status':'SUPPORTED_WITH_LIMITS' if all(assertions.values()) and all(checks.values()) else 'NOT_SUPPORTED',
        'reviewer':'/root/free_constraints different context from main implementation',
        'stage_evidence':{'archived_worker_source_sha256':sign(source),'original_interrupted_receipt_sha256':sign(receipt),
            'files':[{"name":name,"sha256":sign(worker/name)}for name in files],
            'checks':assertions,'original_charged_upper_bound':4,'revised_charged_upper_bound':2,
            'append_only_adjustment':-2,'actual_started_or_completed_builds':'UNKNOWN_0_TO_2; NOT_ASSERTING_TWO_COMPLETED',
            'reason':'M1-C and F0 construction occur strictly after an unconditional constraints.json write. Preserved full worker contains no such file.',
            'limitation':'Relies on preserved directory being the complete stopped worker and no external deletion. No independent OS event log. Worker source contains no output deletion.'},
        'cache_review':{'checks':checks,'bindings':byte_binding,'observed_sha256':b['observed_sha256'],
            'historical_surface_sha256':b['surface']['sha256'],
            'source_prediction_sha256':{'M0':sign(old/'data/predictions/NORTH_160/M0.json'),'M1':sign(old/'data/predictions/NORTH_160/M1.json')},
            'allowed_payload':['surface','observed_sha256','algorithm_and_config_bindings'],
            'forbidden_payload':['routes','base_routes','query','reference','features','read_log','old_route_graph'],
            'status':'SOURCE_IDENTITY_AND_PRE_QUERY_ORIGIN_VERIFIED; ACTUAL_NEW_CACHE_PAYLOAD_NOT_YET_CHECKED',
            'conditions':['Predictor may read only the stripped allowlisted surface cache, not complete old prediction or nested archive',
                          'Rehydrate raw contexts solely from the exact same observed with frozen context_layers',
                          'M1-C/F0 adapted region builds still count two; finite F1 route weights do not count new region builds',
                          'Final worker read log must still freeze current adapted regions before query/full route-only graph reads']}}
    dest=ROOT/'audits/budget_stage_cache_review.json'
    with dest.open('x',encoding='utf-8')as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':doc['status'],'stage_bound':doc['stage_evidence']['revised_charged_upper_bound'],'cache_identity':checks}))


if __name__=='__main__':main()
