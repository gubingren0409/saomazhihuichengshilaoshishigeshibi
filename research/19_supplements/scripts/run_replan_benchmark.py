"""Declared fixed-edge replan timing; NO_PATH is retained as an outcome."""
from pathlib import Path
import sys,json,subprocess,time,datetime,csv
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1'
source=(ROOT/'scripts/benchmark_worker.py').read_text(encoding='utf-8')
source=source.replace('from experiment_core import *','from experiment_core import *\nfrom run_entries_and_closures import dynamic_graph\ncase=next(c for c in json.loads((ROOT/IDS["q7"]/"dynamic_scenarios.json").read_text(encoding="utf-8"))["cases"]if c["scene_id"]=="sh-library")')
source=source.replace('g,a,b,end,bindings=bind_graph(prepared,req);bind_ms=', 'g,a,b,end,bindings=bind_graph(prepared,req);g,removed=dynamic_graph(g,set(),case["selected_native_edge_id"],None);bind_ms=')
source=source.replace('Q8-A1-','Q8-REPLAN-').replace("query_type='SINGLE_SHORTEST_PATH'","query_type='REPLAN_AFTER_FIXED_NATIVE_EDGE_REMOVAL',closed_edge_id=case['selected_native_edge_id'],removed_options=len(removed)")
worker=ROOT/'scripts/benchmark_replan_worker.py';worker.write_text(source,encoding='utf-8')
protocol={'locked_at':datetime.datetime.now().astimezone().isoformat(),'query':'Frozen library start/door F1 FULL_FACE, delete the previously fixed Q7 native directed edge, solve again','edge_id':'Q7 dynamic_scenarios.json library selected_native_edge_id','outcome_already_observed_in_Q7':'NO_PATH; unblinded engineering measurement, no alternate route success assumed','warmup':3,'hot':30,'cold':10,'route_answer_cache':False,'new_state_injection_adapter':True,'not_existing_APP_closure_support':True}
(D/'outputs/replan_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8');rows=[]
for temperature,repeat in [('HOT_PROCESS',0)]+[('COLD_PROCESS',i)for i in range(10)]:
 run=f'REPLAN_{temperature}_{repeat}';log=D/'logs'/f'{run}.log';tick=time.perf_counter()
 with log.open('w',encoding='utf-8')as f:
  try:result=subprocess.run([sys.executable,'-X','utf8','-B',str(worker),'--mode','FULL_FACE','--method','F1','--temperature',temperature,'--repeat',str(repeat)],stdout=f,stderr=subprocess.STDOUT,timeout=600);code=result.returncode;reason=''if code==0 else'WORKER_ERROR'
  except subprocess.TimeoutExpired:code=-9;reason='DECLARED_TIMEOUT'
 row={'scale':'SMALL_FROZEN_LIBRARY_ONLY','query_type':'REPLAN_AFTER_FIXED_NATIVE_EDGE_REMOVAL','mode':'FULL_FACE','method':'F1','temperature':temperature,'repeat':repeat,'manager_wall_ms':(time.perf_counter()-tick)*1000,'returncode':code,'status':'PASS'if code==0 else'RUNTIME_ERROR','failure_reason':reason,'log':'logs/'+log.name};rows.append(row)
 with(D/'replan_benchmark_matrix.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows(rows)
 (D/'outputs/replan_progress.json').write_text(json.dumps({'completed_workers':len(rows),'latest':row},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(row,ensure_ascii=False),flush=True)
