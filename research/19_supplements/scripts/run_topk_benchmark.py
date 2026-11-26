from pathlib import Path
import sys,json,subprocess,time,datetime,csv
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1';worker=ROOT/'scripts/benchmark_topk_worker.py'
protocol={'locked_at':datetime.datetime.now().astimezone().isoformat(),'scope':'Additional explicitly new Top-3 experiment adapter, not frozen APP capability and not historical algorithm replacement','question':'Can the same frozen weighted graph yield 3 node-distinct, whole-route-checked alternatives, and at what cost?','input':'Fixed library F1 FULL_FACE, same current source/constraints; no entrance generation','methods':'NetworkX shortest_simple_paths enumeration on existing DiGraph; frozen graph/binding/cost/validation functions unchanged','warmup':3,'hot':30,'cold':10,'timeout_s':600,'route_answer_cache':False,'selection_after_single_route_pilot':'YES, unblinded supplementary engineering test, no model selection','alternative_diversity_limit':'Node-distinct does not guarantee distinct physical approach directions','historical_source_or_metrics_changed':False}
(D/'outputs/top3_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
rows=[]
for temperature,repeat in [('HOT_PROCESS',0)]+[('COLD_PROCESS',i)for i in range(10)]:
 run=f'TOP3_{temperature}_{repeat}';log=D/'logs'/f'{run}.log';t=time.perf_counter()
 with log.open('w',encoding='utf-8')as f:
  try:result=subprocess.run([sys.executable,'-X','utf8','-B',str(worker),'--temperature',temperature,'--repeat',str(repeat)],stdout=f,stderr=subprocess.STDOUT,timeout=600);code=result.returncode;reason=''if code==0 else'WORKER_ERROR'
  except subprocess.TimeoutExpired:code=-9;reason='DECLARED_TIMEOUT'
 row={'query_type':'TOP3_EXPERIMENTAL_ADAPTER','mode':'FULL_FACE','method':'F1','temperature':temperature,'repeat':repeat,'manager_wall_ms':(time.perf_counter()-t)*1000,'returncode':code,'status':'PASS'if code==0 else'RUNTIME_ERROR','failure_reason':reason,'log':'logs/'+log.name}
 rows.append(row)
 with(D/'top3_benchmark_matrix.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows(rows)
 (D/'outputs/top3_progress.json').write_text(json.dumps({'completed_workers':len(rows),'latest':row},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(row,ensure_ascii=False),flush=True)
