"""One prelocked historical task, then same-graph concurrent cost views."""
import json,time,urllib.request,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:53431/'
def put(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
def call(q):
    t=time.perf_counter();req=urllib.request.Request(URL+'api/plan',data=json.dumps(q).encode(),headers={'Content-Type':'application/json'})
    d=json.loads(urllib.request.urlopen(req,timeout=600).read());print(q['request_id'],d['status'],d.get('route',{}).get('length_m'),flush=True)
    return d,time.perf_counter()-t
def main():
    folder=ROOT/'runs/extra_and_concurrency_R1'
    if folder.exists():raise FileExistsError('Preserve previous run')
    folder.mkdir(parents=True);lock=json.loads((ROOT/'data/extra_task_lock.json').read_text(encoding='utf-8'));records=[]
    for mode in ('EDGE_BAND','FULL_FACE'):
        for method in ('F0','F1'):
            q={**lock['request'],'area_routing':mode,'method':method,'request_id':'EXTRA-HISTORICAL-'+mode+'-'+method}
            r,elapsed=call(q);put(folder/(q['request_id']+'.json'),r);records.append({'type':'EXISTING_LOG_SIMILAR_DEMONSTRATION','request':q,'run_id':r['run_id'],'elapsed_s':elapsed,'length_m':r.get('route',{}).get('length_m')})
    q=json.loads((ROOT/'data/example_request.json').read_text(encoding='utf-8'));pairs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
        for repetition in range(2):
            qs=[{**q,'method':m,'request_id':f'CONCURRENT-{repetition}-{m}'}for m in ('F0','F1')]
            futures=[pool.submit(call,item)for item in qs]
            results=[f.result()for f in futures]
            for item,(r,elapsed)in zip(qs,results):put(folder/(item['request_id']+'.json'),r);records.append({'type':'REAL_CONCURRENT','request':item,'run_id':r['run_id'],'elapsed_s':elapsed})
            a,b=[r for r,_ in results];pairs.append({'repetition':repetition,'same_graph':a['graph']['unweighted_sha256']==b['graph']['unweighted_sha256'],
                'different_runs':a['run_id']!=b['run_id'],'both_solver_invoked':a['solver']['invoked']and b['solver']['invoked'],
                'both_actual_method':a['normalized_request']['method']=='F0'and b['normalized_request']['method']=='F1',
                'route_answer_cache_disabled':not a['route_answer_cache']['enabled']and not b['route_answer_cache']['enabled']})
    put(folder/'summary.json',{'calls':len(records),'records':records,'concurrent_checks':pairs,'screenshot_binding':lock['screenshot_binding'],
        'status':'PASS'if all(all(v for k,v in p.items()if k!='repetition')for p in pairs)else'CHECK','historical_task_count':1})
if __name__=='__main__':main()
