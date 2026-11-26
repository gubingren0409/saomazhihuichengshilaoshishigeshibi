"""Freeze requested matrix before reading its route outputs; no solver import."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    target=ROOT/'data/formal_requests_lock.json'
    if target.exists():raise SystemExit('LOCK_ALREADY_EXISTS; NEVER_OVERWRITE')
    modes=['FROZEN_FULL_FACE','SOURCE_COMPLETE','EXACT_STITCH','CONDITIONAL_SEAMS'];rows=[]
    base=read(ROOT/'data/baseline_requests.json')
    for q in base['positive']:
        for mode in modes:rows.append({'role':'BASELINE_POSITIVE','request':{**q,'connectivity_mode':mode,'area_routing':'FULL_FACE'}})
    for q in base['negative']:
        for mode in modes:rows.append({'role':'BASELINE_REJECTION','expected_status':q['expected_status'],'request':{**q['request'],'connectivity_mode':mode,'area_routing':'FULL_FACE'}})
    extra=read(ROOT/'data/extra_task_lock.json')['request']
    for method in ['F0','F1']:
        for mode in modes:rows.append({'role':'HISTORICAL_LONG_QUERY_NOT_SCREENSHOT_BOUND','request':{**extra,'method':method,'connectivity_mode':mode,'area_routing':'FULL_FACE','request_id':'EXTRA-'+method}})
    queries=read(ROOT/'data/connectivity/mechanism_request_endpoints_lock.json')['queries']
    for q in queries:
        for mode in modes:rows.append({'role':'SOURCE_INTERFACE_MECHANISM','request':{'mechanism_id':q['mechanism_id'],'method':'F0','connectivity_mode':mode,'seam_max_m':2.,'request_id':q['mechanism_id']+'-F0'}})
    # Two stable small-gap/constraint cases, declared before formal route results.
    for mid in ['M06','M07']:
        for threshold in [.5,5.]:
            for method in ['F0','F1']:rows.append({'role':'PRELOCKED_THRESHOLD_SENSITIVITY','request':{'mechanism_id':mid,'method':method,'connectivity_mode':'CONDITIONAL_SEAMS','seam_max_m':threshold,'request_id':mid+'-SENS-'+str(threshold)+'-'+method}})
    for mode in modes:rows.append({'role':'GAP_COST_PAIR','request':{'mechanism_id':'M06','method':'F1','connectivity_mode':mode,'seam_max_m':2.,'request_id':'M06-F1'}})
    for i,row in enumerate(rows,1):row['attempt_id']=f'FORMAL-{i:03d}'
    result={'status':'PRELOCKED_BEFORE_FORMAL_RESULTS','requests':rows,'count':len(rows),'formal_cap':128,'reserve':128-len(rows),
        'baseline_file_sha256':hashlib.sha256((ROOT/'data/baseline_requests.json').read_bytes()).hexdigest(),
        'mechanism_endpoint_lock_sha256':hashlib.sha256((ROOT/'data/connectivity/mechanism_request_endpoints_lock.json').read_bytes()).hexdigest(),
        'development_pilots':'Separately predeclared engineering diagnostics; all actual attempts disclosed, never substitute formal matrix.',
        'configurations':'4 main modes at2m, B3 .5m and5m sensitivity; all F0/F1 same unweighted graph.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'path':str(target),'count':len(rows),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
