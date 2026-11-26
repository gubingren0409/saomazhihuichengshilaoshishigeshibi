"""Serial current-request matrix with append-only receipts and bounded budget."""
from pathlib import Path
import sys,json,time,traceback,gc,hashlib,argparse,urllib.request
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.planner import plan,put,code_identity
from src.mechanism import plan_mechanism
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url');args=ap.parse_args()
    lockfile=ROOT/'data/formal_requests_lock.json';lock=json.loads(lockfile.read_text(encoding='utf-8'))
    path=ROOT/'results/formal_registry.jsonl';path.parent.mkdir(exist_ok=True)
    existing=[json.loads(x)for x in path.read_text(encoding='utf-8').splitlines()]if path.exists()else[]
    completed={r['attempt_id']for r in existing};active=[r for r in lock['requests']if r['attempt_id']not in completed]
    status=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8'));deadline=datetime.fromisoformat(status['budget_started_at']).timestamp()+14400
    # Stable grouping shares immutable source/face preprocessing across methods.
    scene_for={q['mechanism_id']:q['scene_id']for q in json.loads((ROOT/'data/connectivity/mechanism_request_endpoints_lock.json').read_text())['queries']}
    active.sort(key=lambda r:(r['request'].get('scene_id',scene_for.get(r['request'].get('mechanism_id'),'')),r['request'].get('door_id','NO_DOOR'),r['attempt_id']))
    previous_group=None
    for row in active:
        if time.time()>=deadline:print('RESEARCH_BUDGET_CUTOFF',flush=True);break
        if len(completed)>=128:raise RuntimeError('FORMAL_CAP_REACHED')
        group=(row['request'].get('scene_id',scene_for.get(row['request'].get('mechanism_id'),'')),row['request'].get('door_id','NO_DOOR'))
        if not args.url and previous_group is not None and group!=previous_group:
            from src import planner
            for cache_name in ('CACHE','PREPARED_INDEX','AREA_CACHE','CONNECTIVITY_CACHE'):
                getattr(planner,cache_name).clear()
            if group[0]!=previous_group[0]:
                for cache_name in ('SOURCE_CACHE','FACE_CACHE','COMPLETE_FACE_CACHE'):getattr(planner,cache_name).clear()
            gc.collect()
        previous_group=group
        tick=time.perf_counter();q={**row['request'],'run_purpose':'FORMAL_PRELOCKED_MATRIX'}
        put(ROOT/'runs/formal_latest.json',{'attempt_id':row['attempt_id'],'request':q,'started_at':datetime.now().astimezone().isoformat(),'code_sha256':code_identity()})
        try:
            if args.url:
                endpoint='/api/mechanism'if q.get('mechanism_id')else'/api/plan'
                req=urllib.request.Request(args.url.rstrip('/')+endpoint,data=json.dumps(q).encode(),headers={'Content-Type':'application/json'},method='POST')
                with urllib.request.urlopen(req,timeout=900)as response:result=json.load(response)
            else:result=(plan_mechanism if q.get('mechanism_id')else plan)(q)
            record={**row,'run_id':result['run_id'],'status':result['status'],'solver_invoked':result.get('solver',{}).get('invoked',False),
                'path':('runs/mechanisms/'if q.get('mechanism_id')else'runs/app/')+result['run_id']+'.json',
                'result_sha256':hashlib.sha256((ROOT/('runs/mechanisms/'if q.get('mechanism_id')else'runs/app/')/(result['run_id']+'.json')).read_bytes()).hexdigest(),
                'length_m':result.get('route',{}).get('length_m'),'cost_m':result.get('route',{}).get('cost_weighted_m'),
                'validation_passed':result.get('validation',{}).get('passed'),'elapsed_s':time.perf_counter()-tick,
                'expected_matches':result['status']==row.get('expected_status')if row.get('expected_status')else None}
        except Exception as exc:
            record={**row,'status':'ENGINEERING_EXCEPTION','error':str(exc),'traceback':traceback.format_exc(),'elapsed_s':time.perf_counter()-tick}
            put(ROOT/'results/errors'/f"{row['attempt_id']}.json",record)
        with path.open('a',encoding='utf-8')as stream:stream.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
        completed.add(row['attempt_id']);print(json.dumps({k:record.get(k)for k in('attempt_id','status','length_m','cost_m','elapsed_s')},ensure_ascii=False),flush=True)
        put(ROOT/'results/formal_progress.json',{'completed':len(completed),'total':len(lock['requests']),'last':record,'code_sha256':code_identity(),'lock_sha256':hashlib.sha256(lockfile.read_bytes()).hexdigest()})
        status.update(status='FORMAL_RUNNING',formal_completed=len(completed),formal_total=len(lock['requests']),last_checkpoint=datetime.now().astimezone().isoformat());put(ROOT/'STATUS.json',status)
        gc.collect()
    print('FORMAL_MATRIX_WORKER_FINISHED',flush=True)
if __name__=='__main__':main()
