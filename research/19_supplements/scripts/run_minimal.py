from pathlib import Path
import sys,json,time,datetime,psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'frozen_runtime'))
from src import planner
lock=json.loads((ROOT/'frozen_runtime/data/formal_requests_lock.json').read_text(encoding='utf-8'))
req=next(x['request'] for x in lock['requests'] if x['request'].get('request_id')=='APP-01' and x['request'].get('connectivity_mode')=='CONDITIONAL_SEAMS').copy()
req.update(request_id='Q2-MINIMAL-LIVE-001',run_purpose='NEW_SUPPLEMENTARY_REAL_SOLVER_NOT_HISTORICAL_REPLAY')
d=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1'
(d/'outputs/minimal_live_request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'event':'SOLVER_START','time':datetime.datetime.now().astimezone().isoformat(),'request':req,'initial_rss':psutil.Process().memory_info().rss},ensure_ascii=False),flush=True)
t=time.perf_counter();out=planner.plan(req);seconds=time.perf_counter()-t
(d/'outputs/minimal_live_response.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
row={'experiment_id':'Q2-LOCAL-ENTRY-AUDIT-R1','run_id':out['run_id'],'scene_id':req['scene_id'],'building_id':out.get('door',{}).get('building_id'),'entrance_id':req['door_id'],'method':req['method'],'input_version':out.get('versions',{}),'status':'PASS' if out.get('validation',{}).get('passed') else 'FAIL' if out.get('validation',{}).get('conflicts') else 'NO_PATH' if out.get('solver',{}).get('invoked') else 'INVALID_INPUT','result':{'role':'MINIMAL_RUNTIME_SMOKE_NEW_RUN','original_algorithm_status':out['status'],'solver':out['solver']},'failure_reason':out.get('failure'),'route_length_m':out.get('route',{}).get('length_m'),'assumption_length_m':sum(out.get('route',{}).get('layer_lengths_m',{}).get(k,0) for k in ['inferred','unknown','assumed']),'runtime_ms':seconds*1000,'source_edge_count':sum(s['layer']=='native' for s in out.get('route',{}).get('segments',[])),'derived_edge_count':sum(s['layer']=='derived' for s in out.get('route',{}).get('segments',[])),'assumption_edge_count':sum(s['layer']in['inferred','unknown','assumed'] for s in out.get('route',{}).get('segments',[])),'output_file':'outputs/minimal_live_response.json'}
with (d/'raw_results.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
print(json.dumps({'event':'SOLVER_FINISH','status':row['status'],'time_s':seconds,'route_length_m':row['route_length_m'],'solver_invoked':out['solver'].get('invoked'),'rss':psutil.Process().memory_info().rss},ensure_ascii=False),flush=True)
