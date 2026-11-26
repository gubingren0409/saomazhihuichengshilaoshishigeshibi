from pathlib import Path
import sys,json,subprocess,time,datetime,csv
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1';worker=ROOT/'scripts/benchmark_joint_worker.py'
protocol={'locked_at':datetime.datetime.now().astimezone().isoformat(),'scope':'Explicit new experimental K=2 sequential candidate route-cost selection, not original APP feature','candidates':'The two frozen museum door IDs, shared original start, BOTH APPROACH_OUTSIDE. Original north exit coordinate/role preserved','candidate_selection':'All available registered target-building doors eligible for outside approach; stable native ID ordering; no new entrance generation','cache':'2 separately versioned prepared objects retained; no route answers cached','warmup':3,'hot_formal':10,'cold_formal':10,'repeat_rationale':'Allowed minimum 10 due museum preprocessing already >100s in earlier diagnostic; no result-based row deletion','worker_timeout_s':600,'algorithm':'Original per-door solve followed by cost/native-ID sort; ranking only 2 values, not a scalable joint graph method','comparison_limit':'Different site/purpose from library K=1; no causal candidate-count speedup curve permitted','no_inbound_claim_for_exit':True}
(D/'outputs/joint_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8');rows=[]
for temperature,repeat in [('HOT_PROCESS',0)]+[('COLD_PROCESS',i)for i in range(10)]:
 log=D/'logs'/f'JOINT_K2_{temperature}_{repeat}.log';tick=time.perf_counter()
 with log.open('w',encoding='utf-8')as f:
  try:r=subprocess.run([sys.executable,'-X','utf8','-B',str(worker),'--temperature',temperature,'--repeat',str(repeat)],stdout=f,stderr=subprocess.STDOUT,timeout=600);code=r.returncode;reason=''if code==0 else'WORKER_ERROR'
  except subprocess.TimeoutExpired:code=-9;reason='DECLARED_TIMEOUT'
 row={'scale':'SMALL_FROZEN_MUSEUM_TWO_DOORS','query_type':'MULTI_ENTRANCE_K2_SEQUENTIAL_COST_SELECTION_ADAPTER','mode':'FULL_FACE','method':'F1','temperature':temperature,'repeat':repeat,'manager_wall_ms':(time.perf_counter()-tick)*1000,'returncode':code,'status':'PASS'if code==0 else'RUNTIME_ERROR','failure_reason':reason,'log':'logs/'+log.name};rows.append(row)
 with(D/'joint_benchmark_matrix.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows(rows)
 (D/'outputs/joint_progress.json').write_text(json.dumps({'completed_workers':len(rows),'latest':row},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(row,ensure_ascii=False),flush=True)
