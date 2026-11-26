"""Preserve sealed R0 evidence, correct a proven count error, stage an observed-only cache."""
import json,zipfile,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ID='W7a6b5a10076_G_080'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    archive=ROOT/'delivery/OPEN_REVIEW.zip'
    assert sha(archive)=='2b5154e9e80afccd8a04901e7d3e81630dddbe7f50964c6f2ba005a5ce8b595b'
    folder=ROOT/'runs/production_versions/R0_SEALED';assert not folder.exists();folder.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        files=['STATUS.json','CHECKPOINT.md','RESULTS.md','README.md','SCOPE_AND_METHOD.md','PROCESS_RECORD.md','config/contract.json',
            'src/common_constraints.py','src/free_surface.py','src/free_routing.py','src/predict_free.py','scripts/run_free.py','scripts/replay.py',
            'visuals/index.html','audits/visual_build.json','audits/visual_geometry_check.json','audits/visual_browser_check.json',
            'audits/INDEPENDENT_REVIEW.md','audits/LEAKAGE_REVIEW.md','audits/free_review_receipt.json','runs/decision_numbers.json']
        for name in files:
            p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
    baseline=read(ROOT/'data/calibration'/f'{ID}.json')
    obs=ROOT/'data/observed'/f'{ID}.json'
    old=ROOT/'frozen_context'
    assert baseline['M1']['sha256']==read(old/'data/predictions'/ID/'M1.json')['surface']['sha256']
    bindings={p:sha(old/p) for p in ['src/region.py','src/context_policy.py','config/frozen_region.json','config/methods.json']}
    cache={'observed_sha256':sha(obs),'classifier_bindings':bindings,'M0':baseline['M0'],'M1':baseline['M1']}
    dest=ROOT/'data/classifier_cache'/f'{ID}.json';assert not dest.exists();dest.write_text(json.dumps(cache,separators=(',',':')),encoding='utf8')
    saved=ROOT/'runs/superseded/W7_PRIVATE_R0';assert not saved.exists();saved.mkdir(parents=True)
    for rel in [f'data/predictions/{ID}',f'data/graphs/{ID}',f'data/constraints/{ID}.json',f'runs/executions/{ID}.json']:
        p=ROOT/rel;q=saved/rel
        assert p.resolve().is_relative_to(ROOT) and q.resolve().is_relative_to(ROOT)
        q.parent.mkdir(parents=True,exist_ok=True);p.rename(q)
    adjustment=ROOT/'runs/budget_adjustments.json';b=read(adjustment)
    proof=ROOT/'delivery/independent_budget_cache_correction_R0.json';assert proof.exists()
    trace=ROOT/'runtime/final_zip_replay/runtime/final_replay/test_receipt.json';t=read(trace)
    assert t['fixture_calls']==14 and t['synthetic_region_builds']==28 and t['tests']==12
    b['adjustments'].append({'category':'CORRECT_STATIC_SYNTHETIC_ARITHMETIC','adjustment':-2,
        'old_estimate':32,'corrected_scientific_synthetic_builds':30,
        'basis':'Initial 12 scenario contracts: fence open/closed/locked gives 3 invocations, others 11 x1 =>14 fixture invocations x2=28; targeted test11 adds2. Later assertions add no fixture. Cold trace validates current cardinality, not a fabricated original event log.',
        'actual_cold_trace_sha256':sha(trace),'independent_proof_sha256':sha(proof),'early_initial_test_file_sha':'NOT_SEPARATELY_SNAPSHOTTED; original execution history and unchanged call structure reviewed'})
    b['total_adjustment']=-4
    adjustment.write_text(json.dumps(b,indent=2),encoding='utf8')
    (saved/'parent_packet.json').write_text(json.dumps({'archive_sha256':sha(archive),'observed_sha256':sha(obs),'cache_sha256':sha(dest),'old_private_error_m2':128.38855916051605,'new_region_builds_authorized_within_original_cap':2,'budget_upper_before_repair':198,'budget_limit':200},indent=2),encoding='utf8')
    print('Preserved sealed R0 and old W7; staged pure same-observed cache; corrected upper 198, two remaining')
if __name__=='__main__':main()
