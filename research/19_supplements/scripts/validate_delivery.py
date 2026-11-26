"""Author checks in a separate process; no independent-person/field claim."""
from pathlib import Path
from html.parser import HTMLParser
import json,csv,hashlib,datetime,collections,math,sys,zipfile,io
from shapely.geometry import LineString,shape
ROOT=Path(__file__).resolve().parents[1];checks=[]
if not(ROOT/'audit/validation.json').exists():(ROOT/'audit/validation.json').write_text(json.dumps({'status':'INCONCLUSIVE','note':'Author validation is now running; final result replaces this progress record.'}),encoding='utf-8')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def table(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig')))
def check(name,ok,details=None):checks.append({'check':name,'status':'PASS'if ok else'FAIL','details':details});print(name,ok)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=read(ROOT/'audit/FROZEN_RUNTIME_MANIFEST.json');bad=[m['member']for m in manifest['members']if sha(ROOT/'frozen_runtime'/m['member'])!=m['sha256']]
check('49 byte-frozen source/code/input members unchanged',not bad,{'count':len(manifest['members']),'mismatches':bad})
archive=Path(manifest['archive']);check('Original primary ZIP SHA unchanged',archive.exists()and sha(archive)==manifest['archive_sha256'],{'path':str(archive),'expected':manifest['archive_sha256']})
old=[]
for r in table(ROOT/'Q6-LOCAL-MAP-CONSISTENCY-R1/provenance.csv'):
 if r.get('role')!='FROZEN_STAGE_ARCHIVE_READ_ONLY':continue
 chain=json.loads(r['archive_chain']);data=Path(chain[0]).read_bytes()
 for member in chain[1:]:
  with zipfile.ZipFile(io.BytesIO(data))as z:data=z.read(member)
 old.append({'stage':r['stage'],'matched':hashlib.sha256(data).hexdigest()==r['sha256'],'sha256':r['sha256']})
check('Six read historical archive chains still match their initial binding',len(old)==6 and all(r['matched']for r in old),old)
required=set('experiment_id run_id scene_id building_id entrance_id method input_version status result failure_reason route_length_m assumption_length_m runtime_ms source_edge_count derived_edge_count assumption_edge_count output_file'.split());allowed={'PASS','FAIL','NO_PATH','INVALID_INPUT','NOT_APPLICABLE','BLOCKED_BY_MISSING_INPUT','INCONCLUSIVE','RUNTIME_ERROR'}
allrows={};index=[]
for p in ROOT.glob('Q*/raw_results.jsonl'):
 if '--geometry-only'in sys.argv and p.parent.name=='Q8-SCALE-LATENCY-BENCHMARK-R1':continue
 rows=[json.loads(z)for z in p.read_text(encoding='utf-8').splitlines()if z.strip()];allrows[p.parent.name]=rows;errors=[]
 for i,r in enumerate(rows,1):
  if not required<=r.keys()or r['status']not in allowed:errors.append({'line':i,'missing':sorted(required-r.keys()),'status':r.get('status')})
  index.append({'experiment_id':p.parent.name,'run_id':r['run_id'],'scene_id':r['scene_id'],'building_id':r.get('building_id'),'entrance_id':r.get('entrance_id'),'status':r['status'],'raw_file':p.relative_to(ROOT).as_posix(),'raw_line_1based':i,'output_file':r['output_file'],'raw_record_sha256':hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
 check('Raw schema/status '+p.parent.name,not errors,errors)
 check('Unique current raw IDs '+p.parent.name,len({r['run_id']for r in rows})==len(rows),{'n':len(rows)})
with(ROOT/'audit/RUN_INDEX.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
q2=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';targets=table(q2/'target_definition_comparison.csv');identity=table(q2/'entry_identity_audit.csv');check('Q2 fixed 3 native identities and 9 targets',len(identity)==3 and all(r['status']=='PASS'for r in identity)and len(targets)==9)
q2errors=[]
for r in targets:
 x=read(q2/r['output_file'])
 if r['status']=='PASS':
  length=sum(LineString(s['xy']).length for s in x['route']['segments'])
  if not x['validation']['passed']or abs(length-float(r['route_length_m']))>1e-6:q2errors.append(r['run_id'])
check('Q2 PASS routes whole checks and independent geometric sums',not q2errors,q2errors)
current_identity=read(q2/'outputs/identity_recheck_A1.json');check('Corrected A1 scalar identity audit in projected metres',len(current_identity)==3 and all(r['status']=='PASS'and r['result']['boundary_distance_m']<=1e-6 for r in current_identity))
superseded=read(ROOT/'audit/Q2_SUPERSESSION_MAP.json');q2ids={r['run_id']for r in allrows[q2.name]};check('All six invalidated scalar-audit rows retained and replaced with linked A1 IDs',len(superseded)==6 and all(r['original_run_id']in q2ids and r['replacement_run_id']in q2ids for r in superseded))
q6=ROOT/'Q6-LOCAL-MAP-CONSISTENCY-R1';rest=table(q6/'restored_native_edges.csv');faces=table(q6/'added_face_usage.csv');rep=table(q6/'replay_comparison.csv');audit=table(q6/'route_constraint_audit.csv')
check('377 segments / 754 declared arcs / no whole-grass grant',len(rest)==377 and sum(int(r['arcs'])for r in rest)==754 and all(r['status']=='PASS'and r['whole_grass_area_granted']=='False'for r in rest))
check('Current frozen grass policy exact 377 re-evaluations and 4 counterexamples',read(q6/'outputs/grass_policy_recheck_summary.json')['status']=='PASS'and len(table(q6/'grass_policy_recheck.csv'))==377 and all(r['status']=='PASS'for r in read(q6/'outputs/grass_policy_unit_tests.json')))
check('82 source faces / 36 saved business pool',len(faces)==82 and sum(r['in_business_face_pool']=='True'for r in faces)==36)
check('353 saved geometry groups within frozen 1e-6 length epsilon',len(rep)==353 and all(float(r['absolute_length_error_m'])<=1e-6 for r in rep),{'groups':len(rep),'segments':sum(int(r['segments'])for r in rep)})
check('Q6 uncertainty preserved, not silently passed',collections.Counter(r['status']for r in audit)=={'PASS':316,'INCONCLUSIVE':37},{'status_counts':dict(collections.Counter(r['status']for r in audit)),'unassociated_scene_rows':sum(not r['scene_id']for r in audit)})
check('104 saved original response SHA bindings',len(table(q6/'response_binding_audit.csv'))==104 and all(r['status']=='PASS'for r in table(q6/'response_binding_audit.csv')))
field=ROOT/'Q6-FIELD-TRUTH-COMPARISON-R1';check('No fabricated field labels or field metric denominators',read(field/'summary.json')['status']=='BLOCKED_BY_MISSING_INPUT'and not table(field/'field_truth_segment_labels.csv'),{'planned_unfilled_slots':len(table(field/'route_level_comparison.csv'))})
q7=ROOT/'Q7-DYNAMIC-CLOSURE-SIMULATION-R1';rows=allrows[q7.name]
if(q7/'outputs/primary_result_ids.json').exists():primary_ids=set(read(q7/'outputs/primary_result_ids.json'));rows=[r for r in rows if r['run_id']in primary_ids]
adapter=[r for r in rows if r.get('control_variant')=='STATE_INJECTION_ADAPTER'];controls=[r for r in rows if r.get('control_variant')=='UNMODIFIED_PUBLIC_APP_INTERFACE'];cases=read(q7/'dynamic_scenarios.json')['cases'];errors=[]
source_types=[]
for case in cases:
 baseline=next(r for r in adapter if r['scene_id']==case['scene_id']and r['state']=='S0'and r['repeat']==0);doc=read(q7/baseline['output_file']);selected=next(s for s in doc['route']['segments']if s.get('edge_id')==case['selected_native_edge_id']);source_types.append({'scene_id':case['scene_id'],'source_id':selected['source_id'],'highway':selected['tags'].get('highway')})
check('Q7 selected closures are actual tagged walkways, not road axes',all(r['highway']in('footway','path','pedestrian','steps')for r in source_types),source_types)
for r in adapter:
 case=next(c for c in cases if c['scene_id']==r['scene_id']);out=read(q7/r['output_file']);segments=out['route']['segments']if out.get('route')else[]
 if r['state']in('S1','S4')and segments:errors.append((r['run_id'],'closed door still routed'))
 if r['state']in('S2','S4')and any(s.get('edge_id')==case['selected_native_edge_id']for s in segments):errors.append((r['run_id'],'closed edge used'))
 if r['state']=='S3'and any(LineString(s['xy']).intersection(shape(case['obstacle'])).length>1e-6 for s in segments):errors.append((r['run_id'],'simulated obstacle interior used'))
 if r['state']=='S5'and not r['restored_to_S0']:errors.append((r['run_id'],'restoration mismatch'))
check('Q7 complete 2 x 6 x 3 state attempt table',len(adapter)==36 and all(sum(r['state']==state and r['scene_id']==scene for r in adapter)==3 for scene in('sh-huangpu-01','sh-library')for state in('S0','S1','S2','S3','S4','S5')))
check('Q7 separate geometry/arithmetic check of closures and restoration by same author',not errors,errors)
check('Original APP unsupported closure failures retained',len(controls)==2 and all(r['status']=='FAIL'for r in controls))
if '--geometry-only'in sys.argv:
 receipt={'timestamp':datetime.datetime.now().astimezone().isoformat(),'identity':'AUTHOR_GEOMETRY_PREFLIGHT_NOT_INDEPENDENT_REVIEWER','status':'PASS'if all(c['status']=='PASS'for c in checks)else'FAIL','checks':checks,'performance_readiness_not_checked':True};(ROOT/'audit/geometry_preflight.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print('GEOMETRY_PREFLIGHT',receipt['status']);raise SystemExit(0 if receipt['status']=='PASS'else 1)
q8=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1';rows=allrows[q8.name];normal=table(q8/'observations_normalized.csv');groups=collections.defaultdict(list)
for r in rows:groups[(r['scale'],r['query_type'],r['mode'],r['method'])].append(r)
count_errors=[]
for key,rs in groups.items():
 hot=10 if key[1].startswith('MULTI_ENTRANCE_K2')else 30
 n=collections.Counter((r['temperature'],bool(r['warmup']))for r in rs)
 if n!={('HOT_PROCESS',True):3,('HOT_PROCESS',False):hot,('COLD_PROCESS',False):10}:count_errors.append({'key':key,'counts':str(n)})
check('Every measured configuration has predeclared repetitions and 3 excluded warmups',len(groups)==11 and not count_errors,{'configurations':len(groups),'errors':count_errors,'raw':len(rows),'formal':len(normal)})
check('Every cold observation bound to exactly one process wall-clock record',all(r['cold_manager_binding_matches']=='1'for r in normal if r['temperature']=='COLD_PROCESS'))
hashes=collections.defaultdict(set)
for r in rows:
 if r['query_type']=='SINGLE_SHORTEST_PATH':hashes[(r['scale'],r['mode'])].add(r['unweighted_graph_sha256'])
check('F0/F1 same unweighted graph across hot/cold processes',all(len(h)==1 for h in hashes.values()),{str(k):list(v)for k,v in hashes.items()})
check('No route answer cache enabled in formal benchmark',all(not r.get('route_answer_cache')for r in rows))
check('Top-3 is explicitly new and first route matches single-route geometry length',all(abs(r['route_length_m']-180.58111866323975)<1e-6 and r['result']['adapter_added_this_round']and r['result']['all_routes_constraint_checked']for r in rows if r['query_type']=='TOP3_EXPERIMENTAL_ADAPTER'))
check('K2 outside-only retains original exit identity and exactly two real solver calls',all(r['candidate_count']==2 and r['solver_call_count']==2 and r['result']['exit_not_used_as_inbound']and r['result']['purpose']=='APPROACH_OUTSIDE'for r in rows if r['query_type'].startswith('MULTI_ENTRANCE_K2')))
for p in(ROOT/'scripts').glob('*.py'):
 try:compile(p.read_text(encoding='utf-8'),str(p),'exec')
 except Exception as e:check('Python source compilation '+p.name,False,str(e))
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  for k,v in attrs:
   if k in('src','href')and v:self.links.append(v)
l=Links();l.feed((ROOT/'index.html').read_text(encoding='utf-8'));missing=[]
for link in l.links:
 if link.startswith(('http:','https:','data:','#')):continue
 if not(ROOT/link.split('#')[0]).exists():missing.append(link)
check('Offline HTML relative image/document links resolve',not missing,missing)
b=read(ROOT/'audit/browser_check.json');check('Actual Chrome check matches final HTML bytes',b['status']=='PASS'and b['html_sha256']==sha(ROOT/'index.html'),{'tested_choices':len(b['checks']),'javascript_errors':b['javascript_errors']})
receipt={'timestamp':datetime.datetime.now().astimezone().isoformat(),'identity':'AUTHOR_VALIDATION_SEPARATE_PROCESS_NOT_INDEPENDENT_PERSON','status':'PASS'if all(c['status']=='PASS'for c in checks)else'FAIL','checks':checks,'field_truth_verified':False,'entire_historical_graphs_rebuilt':False,'whole_archive_replay':'Performed later on final ZIP; see external delivery receipt'}
(ROOT/'audit/validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print('DELIVERY_AUTHOR_VALIDATION',receipt['status'])
if receipt['status']!='PASS':raise SystemExit(1)
