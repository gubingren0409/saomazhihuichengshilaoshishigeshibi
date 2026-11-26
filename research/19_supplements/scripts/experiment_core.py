"""Experiment controls around byte-frozen core functions; not an algorithm replacement."""
from pathlib import Path
import csv,datetime,hashlib,json,math,sys,time,threading
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'frozen_runtime'
sys.path.insert(0,str(RUNTIME))
from src import planner as P
from src.free_routing import bind
from src.region_routing import bidirectional
from src.common_constraints import edge_conflicts
import networkx as nx
from shapely.geometry import Point,LineString,mapping
import psutil

IDS={'q2':'Q2-LOCAL-ENTRY-AUDIT-R1','q6':'Q6-LOCAL-MAP-CONSISTENCY-R1','field':'Q6-FIELD-TRUTH-COMPARISON-R1','q7':'Q7-DYNAMIC-CLOSURE-SIMULATION-R1','q8':'Q8-SCALE-LATENCY-BENCHMARK-R1'}
def stamp():return datetime.datetime.now().astimezone().isoformat()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def write(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def csvout(p,rows,fields=None):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 fields=fields or list(dict.fromkeys(k for row in rows for k in row))
 with p.open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
  for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(dict,list))else v for k,v in row.items()})
def append(eid,row):
 with (ROOT/eid/'raw_results.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
def base_row(eid,run_id,scene,door,method,status='INCONCLUSIVE'):
 return dict(experiment_id=eid,run_id=run_id,timestamp=stamp(),scene_id=scene,building_id='',entrance_id=door,method=method,input_version=P.IMPORTED_CODE_SHA,status=status,result={},failure_reason='',route_length_m=None,assumption_length_m=None,runtime_ms=None,source_edge_count=None,derived_edge_count=None,assumption_edge_count=None,output_file='')
def fixed_requests():
 lock=json.loads((RUNTIME/'data/formal_requests_lock.json').read_text(encoding='utf-8'))
 result=[]
 for app in ['APP-01','APP-03','APP-07']:
  req=next(r['request']for r in lock['requests']if r['request'].get('request_id')==app and r['request']['connectivity_mode']=='CONDITIONAL_SEAMS').copy()
  req['method']='F1';req['connectivity_mode']='FROZEN_FULL_FACE';req['source_historical_request_id']=app;result.append(req)
 return result
def prepare(req,mode='FULL_FACE'):
 if mode=='FULL_FACE':return P.prepare_connectivity(req['scene_id'],req['door_id'],'FROZEN_FULL_FACE',2.)
 P._activate_preprocessing_group(req['scene_id'],req['door_id'])
 return P.prepare_area(req['scene_id'],req['door_id'],'EDGE_BAND')
def bind_graph(prepared,req,target=None):
 g=P.compose_prepared(prepared);source=prepared['source'];a=req['start_id']
 if a not in source:raise ValueError('START_NOT_IN_FROZEN_ELIGIBLE_SOURCE_GRAPH')
 door=prepared['data']['door'];end=target or dict(id=door['id'],xy=door['xy'],tags=door['tags'],role=door['role'])
 terminals=[dict(id=a,xy=source.nodes[a]['xy'],tags=source.nodes[a].get('tags',{})),end];bindings=[]
 for t in terminals:
  node,stitch=bind(t,prepared['region'],prepared['cfg'],prepared['parsed'],'F0',verified_source=source.nodes.get(t['id']))
  if stitch:
   attach,measured=stitch
   if node not in g:g.add_node(node,xy=tuple(t['xy']),tags=t.get('tags',{}))
   bidirectional(g,node,attach,measured);bindings.append(dict(id=node,attach=attach,segments=measured))
 return g,a,end['id'],end,bindings
def validate(prepared,route,start_xy,end_xy,temporary_obstacle=None):
 checks=[];previous=start_xy;gap=0.;faces={f['source_id']:f for f in prepared.get('faces',[])}
 for i,s in enumerate(route['segments']):
  line=LineString(s['xy']);kind=s.get('geometry_kind');is_source=s['layer']in('native','derived')and not str(s.get('source_id','')).startswith('cell/')
  connectivity=kind in('SOURCE_SUPPORTED_INTERFACE','CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')
  common=prepared['full_parsed']if is_source or connectivity else prepared['parsed']
  conflicts=edge_conflicts(line,common,native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
  if connectivity:
   from src.connectivity import validate_connectivity_segment
   conflicts+=validate_connectivity_segment(s,prepared.get('faces',[]),prepared['full_parsed'],prepared.get('connectivity_evidence',{}))
  if kind=='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE':
   from src.face_geometry import face_edge_conflicts
   f=faces.get(s.get('source_area_id',s.get('source_id')))
   conflicts+=face_edge_conflicts(line,f,prepared['full_parsed'])if f else['MISSING_MAPPED_FACE_GEOMETRY']
  if temporary_obstacle is not None and line.intersection(temporary_obstacle).length>1e-6:conflicts+=['SIMULATED_TEMPORARY_OBSTACLE_INTERIOR']
  d=math.dist(previous,s['xy'][0]);gap=max(gap,d);previous=s['xy'][-1]
  checks.append(dict(segment_index=i,source_id=s.get('source_id'),edge_id=s.get('edge_id'),constraint_conflicts=conflicts,continuity_gap_m=d))
 residual=math.dist(previous,end_xy)
 return dict(passed=not any(x['constraint_conflicts']for x in checks)and max(gap,residual)<=1e-6,max_gap_m=gap,end_residual_m=residual,segment_checks=checks)
def solve(prepared,g,a,b,end_xy,method,temporary_obstacle=None):
 tick=time.perf_counter();route,failure,solver=P._weighted_route(g,a,b,1 if method=='F0'else 2)
 search_ms=(time.perf_counter()-tick)*1000
 if route is None:return dict(status='NO_PATH',route=None,solver=solver,failure=failure,solver_ms=search_ms,validation_ms=0.)
 t=time.perf_counter();check=validate(prepared,route,g.nodes[a]['xy'],end_xy,temporary_obstacle)
 seg=route['segments'];lengths={k:sum(s['length_m']for s in seg if s['layer']==k)for k in ['native','derived','inferred','unknown','assumed']}
 return dict(status='PASS'if check['passed']else'FAIL',route=route,validation=check,layer_lengths_m=lengths,route_length_m=sum(lengths.values()),assumption_length_m=sum(lengths[k]for k in ['inferred','unknown','assumed']),cost_m=sum(s['cost_m']for s in seg),source_edge_count=sum(s['layer']=='native'for s in seg),derived_edge_count=sum(s['layer']=='derived'for s in seg),assumption_edge_count=sum(s['layer']in('inferred','unknown','assumed')for s in seg),solver=solver,failure=None if check['passed']else'WHOLE_ROUTE_CONSTRAINT_FAILURE',solver_ms=search_ms,validation_ms=(time.perf_counter()-t)*1000,geometry_signature=digest([(s['source_id'],s['xy'],s['layer'])for s in seg]))
def complete_row(row,out,elapsed_ms):
 for k in ['status','route_length_m','assumption_length_m','source_edge_count','derived_edge_count','assumption_edge_count']:row[k]=out.get(k)
 row.update(runtime_ms=elapsed_ms,failure_reason=out.get('failure')or'',result={k:v for k,v in out.items()if k!='route'})
 return row
class MemorySample:
 def __enter__(self):
  self.stop=threading.Event();self.peak=psutil.Process().memory_info().rss
  def sample():
   while not self.stop.wait(.01):self.peak=max(self.peak,psutil.Process().memory_info().rss)
  self.thread=threading.Thread(target=sample,daemon=True);self.thread.start();return self
 def __exit__(self,*args):self.stop.set();self.thread.join();self.peak=max(self.peak,psutil.Process().memory_info().rss)
