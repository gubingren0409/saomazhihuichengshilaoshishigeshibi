from pathlib import Path
import json,sys,time,subprocess,datetime,csv,hashlib
ROOT=Path(__file__).resolve().parents[1];EID='Q8-SCALE-LATENCY-BENCHMARK-R1';D=ROOT/EID
def stamp():return datetime.datetime.now().astimezone().isoformat()
def csvout(name,rows):
 fields=list(dict.fromkeys(k for row in rows for k in row))
 with (D/name).open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(dict,list))else v for k,v in row.items()})
manifest=json.loads((ROOT/'frozen_runtime/data/scene_manifest.json').read_text(encoding='utf-8'))
catalog=[]
for scene in manifest['scenes']:
 data=json.loads((ROOT/'frozen_runtime/data/scenes'/scene['scene_id']/'frozen_scene.json').read_text(encoding='utf-8-sig'))
 for door in data.get('r4_entrances',[]):catalog.append({'scene_id':scene['scene_id'],'door_id':door['native_id']})
assert sorted(catalog,key=lambda x:x['door_id'])[0]['scene_id']=='sh-library'
protocol={'experiment_id':EID,'locked_at':stamp(),'selection_rule':'Lexicographic native registered-door ID selection was declared earlier. Library pilot latency was observed before the execution lock; this is unblinded engineering timing, not representative of all six scenes.','selected_scene':'sh-library','parent_preflight_B3_abort':'Nonprimary museum construction diagnostic retained separately; not a timed completion','scales':{'SMALL':'Frozen library scene and one registered door','MEDIUM':'Existing adjacent clips available; merged scene/constraint/graph adapter not part of frozen input contract, not implemented here','LARGE':'No domain-compatible city-scale current input; unrelated NYC historical network not substituted'},'configs':[{'mode':m,'method':f}for m in ['EDGE_BAND','FULL_FACE']for f in ['F0','F1']],'warmup':3,'hot_formal':30,'cold_formal':10,'cold_definition':'Fresh Python process, no in-memory preprocessing; uncontrolled OS disk cache; manager wall time includes process/import/prepare/bind/solve/validation/write/exit','cold_count_rationale':'Use allowed minimum 10 because cold preprocessing already measured above 100s in separate museum diagnostic; all ten retained, no after-result deletions','request_timeout_s':600,'timeout_handling':'RUNTIME_ERROR; right-censored at timeout, never counted as quick failure or omitted from denominator','measurement_scope':'Experiment CLI core adapter, NOT HTTP/UI/production SLA; Path read and STRtree constructor timers delegate unchanged; nested phases, overhead not subtracted','one_second_rule':'Only report per-config satisfaction if p95 AND max <=1000ms; any missing or timed-out mandatory scope precludes overall one-second claim','missing_requested_functions':['TOP3_ROUTE_ENUMERATION','MULTI_ENTRANCE_JOINT_SELECTION','10_OR_100_VALID_REGISTERED_TARGETS','MERGED_SCENE_INPUT_CONTRACT','DOMAIN_COMPATIBLE_CITY_NETWORK'],'no_new_map_downloads':True,'route_answer_cache':False}
(D/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
matrix=[];worker=ROOT/'scripts/benchmark_worker.py'
def execute(mode,method,temp,rep):
 cmd=[sys.executable,'-X','utf8','-B',str(worker),'--mode',mode,'--method',method,'--temperature',temp,'--repeat',str(rep)]
 label=f'{mode}_{method}_{temp}_{rep}';log=D/'logs'/f'{label}.log';tick=time.perf_counter()
 with log.open('w',encoding='utf-8')as f:
  try:result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=600);code=result.returncode;reason=''if code==0 else'WORKER_NONZERO_EXIT'
  except subprocess.TimeoutExpired:code=-9;reason='DECLARED_600_SECOND_TIMEOUT'
 elapsed=(time.perf_counter()-tick)*1000
 row={'mode':mode,'method':method,'temperature':temp,'repeat':rep,'manager_wall_ms':elapsed,'returncode':code,'failure_reason':reason,'status':'PASS'if code==0 else'RUNTIME_ERROR','log':'logs/'+log.name,'timestamp':stamp()}
 if code==0:
  records=[json.loads(line)['row']for line in log.read_text(encoding='utf-8').splitlines()if line.startswith('{')and 'BENCHMARK_RESULT' in line]
  row['observations']=len(records)
  if temp=='COLD_PROCESS':row['run_id']=records[0]['run_id'];row['child_status']=records[0]['status']
 else:
  bad={'experiment_id':EID,'run_id':'Q8-ERROR-'+label,'scene_id':'sh-library','building_id':'way/293434188','entrance_id':'node/11300000483','method':method,'input_version':'Frozen Connectivity-R1','status':'RUNTIME_ERROR','result':row,'failure_reason':reason,'route_length_m':None,'assumption_length_m':None,'runtime_ms':elapsed,'source_edge_count':None,'derived_edge_count':None,'assumption_edge_count':None,'output_file':row['log'],'mode':mode,'temperature':temp,'warmup':False,'repeat':rep}
  with (D/'raw_results.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(bad,ensure_ascii=False)+'\n')
 matrix.append(row);csvout('benchmark_matrix.csv',matrix);(D/'outputs/manager_progress.json').write_text(json.dumps({'timestamp':stamp(),'completed_workers':len(matrix),'latest':row},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'event':'BENCHMARK_WORKER_COMPLETED',**row},ensure_ascii=False),flush=True)
for mode in ['EDGE_BAND','FULL_FACE']:
 for method in ['F0','F1']:
  execute(mode,method,'HOT_PROCESS',0)
  for repeat in range(10):execute(mode,method,'COLD_PROCESS',repeat)
print('BENCHMARK_MATRIX_COMPLETE',flush=True)
