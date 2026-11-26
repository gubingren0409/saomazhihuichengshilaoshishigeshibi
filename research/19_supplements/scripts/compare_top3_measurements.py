from pathlib import Path
import json,csv,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1';results=[]
def raw(p):return[json.loads(x)for x in p.read_text(encoding='utf-8').splitlines()if x.strip()]
data={'A1_VALID_TOTAL_TIMING_NO_PHASE_SPLIT':raw(D/'secondary_results/top3_A1_uninstrumented_raw_results.jsonl'),'A2_PHASE_INSTRUMENTED_PRIMARY':[r for r in raw(D/'raw_results.jsonl')if r.get('query_type')=='TOP3_EXPERIMENTAL_ADAPTER']}
for version,rows in data.items():
 matrix=list(csv.DictReader((D/('top3_benchmark_matrix.csv'if version.startswith('A1')else'top3_phased_benchmark_matrix.csv')).open(encoding='utf-8-sig')))
 for temp,metric in [('HOT_PROCESS','end_to_end_worker_ms'),('HOT_PROCESS','topk_ms'),('COLD_PROCESS','cold_process_end_to_end_ms')]:
  rr=[r for r in rows if not r['warmup']and r['temperature']==temp];values=[float(next(m['manager_wall_ms']for m in matrix if m['temperature']==temp and int(m['repeat'])==r['repeat']))if metric.startswith('cold_')else r[metric]for r in rr];a=np.array(values);results.append({'measurement_version':version,'temperature':temp,'timing_scope':metric,'n':len(a),'p50_ms':float(np.percentile(a,50)),'p90_ms':float(np.percentile(a,90)),'p95_ms':float(np.percentile(a,95)),'p99_ms':float(np.percentile(a,99)),'min_ms':float(a.min()),'max_ms':float(a.max()),'mean_ms':float(a.mean()),'std_population_ms':float(a.std()),'one_second_p95_and_max':bool(np.percentile(a,95)<=1000 and a.max()<=1000),'graph_sha256':sorted({r['unweighted_graph_sha256']for r in rr}),'version_role':'Valid secondary overall timing, not discarded by speed'if version.startswith('A1')else'Primary because phase coverage added, not selected by latency','not_method_speedup_or_independent_sample':True})
with(D/'top3_measurement_versions.csv').open('w',encoding='utf-8-sig',newline='')as f:
 w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader()
 for r in results:w.writerow({k:json.dumps(v)if isinstance(v,list)else v for k,v in r.items()})
print([(r['measurement_version'],r['timing_scope'],round(r['p95_ms'],2),round(r['max_ms'],2),r['one_second_p95_and_max'])for r in results])
