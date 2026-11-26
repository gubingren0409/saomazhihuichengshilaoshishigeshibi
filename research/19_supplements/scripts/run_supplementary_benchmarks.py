"""Sequential supplemental tests; no simultaneous benchmark workers."""
from pathlib import Path
import sys,json,subprocess,time,datetime,csv
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1'
main=json.loads((D/'outputs/manager_progress.json').read_text(encoding='utf-8'))
assert main['completed_workers']==44,'Do not overlap main benchmark'
source=(ROOT/'scripts/benchmark_worker.py').read_text(encoding='utf-8')
source=source.replace('from experiment_core import *','from experiment_core import *\nfrom medium_adapter import activate_medium\nactivate_medium()')
source=source.replace('Q8-A1-','Q8-MEDIUM-').replace("scale='SMALL_FROZEN_LIBRARY_ONLY'","scale='MEDIUM_TWO_OVERLAPPING_FROZEN_CROPS'")
worker=ROOT/'scripts/benchmark_medium_worker.py';worker.write_text(source,encoding='utf-8')
protocol={'locked_at':datetime.datetime.now().astimezone().isoformat(),'scope':'Supplement to original 4 small configurations, not a replacement','medium':'Exact identity/compatible-missing-metadata union of library and overlapping Wukang crops; union coverage, no new road or door','medium_configs':'EDGE_BAND/FULL_FACE x F0/F1','medium_hot':30,'medium_warmup':3,'medium_cold':10,'top3':'Explicit new Yen adapter; not an existing original APP feature','single_worker_only':True,'cold_timeout_s':600,'hardware_concurrency_other_desktop_processes':'Uncontrolled','no_route_answer_cache':True}
(D/'outputs/supplementary_benchmark_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
result=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/run_topk_benchmark.py')],timeout=6600)
print('TOP3_MANAGER_RETURN',result.returncode,flush=True)
rows=[]
for mode in ('EDGE_BAND','FULL_FACE'):
 for method in ('F0','F1'):
  for temperature,repeat in [('HOT_PROCESS',0)]+[('COLD_PROCESS',i)for i in range(10)]:
   run=f'MEDIUM_{mode}_{method}_{temperature}_{repeat}';log=D/'logs'/f'{run}.log';tick=time.perf_counter()
   with log.open('w',encoding='utf-8')as f:
    try:
     result=subprocess.run([sys.executable,'-X','utf8','-B',str(worker),'--mode',mode,'--method',method,'--temperature',temperature,'--repeat',str(repeat)],stdout=f,stderr=subprocess.STDOUT,timeout=600);code=result.returncode;reason=''if code==0 else'WORKER_ERROR'
    except subprocess.TimeoutExpired:code=-9;reason='DECLARED_TIMEOUT'
   row={'scale':'MEDIUM_TWO_OVERLAPPING_FROZEN_CROPS','query_type':'SINGLE_SHORTEST_PATH','mode':mode,'method':method,'temperature':temperature,'repeat':repeat,'manager_wall_ms':(time.perf_counter()-tick)*1000,'returncode':code,'status':'PASS'if code==0 else'RUNTIME_ERROR','failure_reason':reason,'log':'logs/'+log.name}
   rows.append(row)
   with(D/'medium_benchmark_matrix.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows(rows)
   (D/'outputs/medium_progress.json').write_text(json.dumps({'completed_workers':len(rows),'latest':row},ensure_ascii=False,indent=2),encoding='utf-8')
   print(json.dumps(row,ensure_ascii=False),flush=True)
