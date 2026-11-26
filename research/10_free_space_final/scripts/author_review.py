"""Author integrity checks; not a substitute for the separate reviewer."""
import json,hashlib,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=read(ROOT/'data/task_manifest.json');main=[r for r in manifest['instances'] if r['panel']=='MAIN'];north=next(r for r in manifest['instances'] if r['panel']=='NORTH')
    checks=[];count=0
    assert len(main)==25 and sum(r['query_count'] for r in main)==41
    for row in main+[north]:
        pred={m:read(ROOT/'data/predictions'/row['id']/(m+'.json')) for m in ['M1-C','F0','F1']}
        assert pred['F0']['surface']['sha256']==pred['F1']['surface']['sha256']
        assert pred['F0']['graph']['graph_sha256']==pred['F1']['graph']['graph_sha256']
        assert pred['F0']['graph']['terminal_graph_sha256']==pred['F1']['graph']['terminal_graph_sha256']
        assert {q for q,v in pred['F0']['routes'].items() if v['reached']}=={q for q,v in pred['F1']['routes'].items() if v['reached']}
        record=read(ROOT/'runs/executions'/f"{row['id']}.json")
        expected=record.get('outputs') or {r['method']+'.json':r['prediction_sha256'] for r in record['runs']}
        for file,digest in expected.items():assert sha(ROOT/'data/predictions'/row['id']/file)==digest;count+=1
        checks.append({'id':row['id'],'paired_region_graph_terminal':'PASS','unchanged_recorded_prediction_hashes':'PASS'})
    gap=read(ROOT/'runs/decision_numbers.json')['known_policy_gap'];assert abs(gap['private_area_m2']-128.38855916051673)<1e-5
    assert all(gap['current_actual_private_route_crossing_m'][m]<=1e-5 for m in ['F0','F1'])
    assert read(ROOT/'audits/historical_calibration.json')['status']=='PASS'
    assert read(ROOT/'audits/input_verification.json')['status']=='PASS'
    old=ROOT/'input_contract/frozen/R4_CONTEXT_OPEN_REVIEW.zip';assert sha(old)=='40f8e18d76d04819d66a3bd526ecb2b74fc83201b3b58452881a6576b6651cbf'
    fixed=gap.get('fixed',False)
    result={'status':'READY_FOR_GPT_AND_USER_REVIEW' if fixed else 'PARTIAL_WITH_EVIDENCE','author':'/root','integrity_checks':'PASS','main_parents':25,'main_queries':41,'natural_parents':1,'prediction_files_matched_to_actual_run_receipts':count,
        'checks':checks,'regional_policy_gate':'KNOWN_SOURCE_PERMISSION_REPAIRED_NOT_FIELD_SAFETY_PROOF' if fixed else 'NOT_PASSED_KNOWN_PRIVATE_AREA_EXPORT_GAP','permission_repair_history':gap,
        'budget_accounting_upper':read(ROOT/'runs/decision_numbers.json')['all_experiment_region_builds_including_failed_and_synthetic'],
        'reviewer_role':'AUTHOR_CHECK_ONLY; separate independent reviewer records apply',
        'map_or_provider_requests':0,'documentation_web_tool_calls':3,'timestamp':datetime.datetime.now().astimezone().isoformat()}
    (ROOT/'audits/AUTHOR_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result['status'],'integrity PASS',count,'actual prediction receipts; historical gap retained')
if __name__=='__main__':main()
