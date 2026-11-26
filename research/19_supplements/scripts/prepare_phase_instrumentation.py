from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1';records=[]
for name in('benchmark_topk_worker.py','benchmark_joint_worker.py'):
 p=ROOT/'scripts'/name;before=p.read_bytes()
 if b'install_phase_timers'in before:continue
 if name=='benchmark_topk_worker.py':(ROOT/'audit/EXECUTED_TOP3_WORKER_A1.py').write_bytes(before)
 s=before.decode('utf-8').replace('from experiment_core import *','from experiment_core import *\nfrom phase_timers import install_phase_timers\nphases=install_phase_timers()')
 s=s.replace('def execute(rep,warmup=False):','def execute(rep,warmup=False):\n phases.clear()')
 if name=='benchmark_topk_worker.py':
  s=s.replace('Q8-TOP3-ADAPTER-','Q8-TOP3-A2-PHASED-ADAPTER-')
  s=s.replace("row.update(query_type=","row.update(building_id=prepared['data']['door']['building_id'],read_ms=phases.get('read_ms',0.),index_ms=phases.get('index_ms',0.),phase_timing_scope='Path read methods and STRtree constructors only; nested; gzip/internal I/O not separately isolated',query_type=")
 else:
  s=s.replace('read_ms=None,index_ms=None,',"read_ms=phases.get('read_ms',0.),index_ms=phases.get('index_ms',0.),phase_timing_scope='Path read methods and STRtree constructors only; nested; gzip/internal I/O not separately isolated',")
 p.write_text(s,encoding='utf-8');records.append({'script':name,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
manager=(ROOT/'scripts/run_topk_benchmark.py').read_text(encoding='utf-8').replace("run=f'TOP3_","run=f'TOP3_PHASED_").replace('outputs/top3_protocol.json','outputs/top3_phased_protocol.json').replace('top3_benchmark_matrix.csv','top3_phased_benchmark_matrix.csv').replace('outputs/top3_progress.json','outputs/top3_phased_progress.json')
(ROOT/'scripts/run_topk_phased_benchmark.py').write_text(manager,encoding='utf-8')
record={'timestamp':datetime.datetime.now().astimezone().isoformat(),'reason':'Top3 A1 measured total/solver/validation but did not split Path reads and STRtree construction. Re-measure same inputs/cost/core with delegating phase timers; selection not based on latency','core_changed':False,'frozen_inputs_changed':False,'script_revisions':records,'old_43_rows_to_be_retained_as_secondary_not_discarded':True,'new_primary_top3_id_prefix':'Q8-TOP3-A2-PHASED-ADAPTER','K2_was_not_started_before_this_instrumentation':True}
(D/'outputs/phase_instrumentation_protocol.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(record)
