"""Prelocked affected-mode replay; preserve originals, never reset request cap."""
from pathlib import Path
import sys,json,time,hashlib,urllib.request,argparse,datetime
ROOT=Path(__file__).resolve().parents[1]
def main():
    a=argparse.ArgumentParser();a.add_argument('--url',required=True);args=a.parse_args()
    lock=json.loads((ROOT/'data/performance_replay_lock.json').read_text());target=ROOT/'results/formal_replay_registry.jsonl'
    previous=[json.loads(x)for x in target.read_text().splitlines()]if target.exists()else[]
    done={r['supersedes_attempt_id']for r in previous}
    for old in lock['entries']:
        if old['attempt_id']in done:continue
        main_count=len((ROOT/'results/formal_registry.jsonl').read_text().splitlines())
        interrupted=len(list((ROOT/'results').glob('interrupted_formal_*.json')))
        if main_count+len(done)+interrupted>=128:raise RuntimeError('FORMAL_ACTUAL_REQUEST_CAP_REACHED')
        q={**old['request'],'run_purpose':'FORMAL_PERFORMANCE_FIX_REPLAY'};t=time.perf_counter()
        endpoint='/api/mechanism'if q.get('mechanism_id')else'/api/plan'
        req=urllib.request.Request(args.url.rstrip('/')+endpoint,data=json.dumps(q).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=900)as response:d=json.load(response)
        path=('runs/mechanisms/'if q.get('mechanism_id')else'runs/app/')+d['run_id']+'.json'
        r={**old,'attempt_id':'REPLAY-'+old['attempt_id'],'supersedes_attempt_id':old['attempt_id'],'supersedes_response_sha256':old['result_sha256'],
            'run_id':d['run_id'],'path':path,'status':d['status'],'result_sha256':hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
            'solver_invoked':d.get('solver',{}).get('invoked',False),'length_m':d.get('route',{}).get('length_m'),'cost_m':d.get('route',{}).get('cost_weighted_m'),
            'elapsed_s':time.perf_counter()-t,'validation_passed':d.get('validation',{}).get('passed'),'same_inputs_except_run_purpose':True}
        r['expected_matches']=d['status']==old['expected_status']if old.get('expected_status')else None
        with target.open('a',encoding='utf-8')as f:f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')
        done.add(old['attempt_id']);print(json.dumps({k:r[k]for k in('attempt_id','status','length_m','cost_m','elapsed_s')}),flush=True)
if __name__=='__main__':main()
