"""New read-only geometry/evidence audit; no route solver or graph search imported."""
from pathlib import Path
from io import BytesIO,StringIO
import csv,json,gzip,hashlib,math,datetime,zipfile,sys,collections,time
from shapely.geometry import Point,LineString,shape
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q6-LOCAL-MAP-CONSISTENCY-R1';RT=ROOT/'frozen_runtime'
P=Transformer.from_crs(4326,32651,always_xy=True).transform
manifest=json.loads((RT/'data/scene_manifest.json').read_text(encoding='utf-8'))
STAGES=['WALKABILITY-R2','WALKABILITY-R3','FREE-SPACE-R1-FINAL','PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED','PED-AREA-CONNECTIVITY-R1','PED-AREA-CONNECTIVITY-R2']
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def csvout(name,rows,fields=None):
 with (D/name).open('w',encoding='utf-8-sig',newline='')as f:
  fields=fields or list(dict.fromkeys(k for row in rows for k in row));w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in r.items()})
provenance=[];archives={}
defs=json.loads((ROOT.parent/'PG1_RESEARCH_MATERIALS_HANDOFF_R1/working/methods_history.json').read_text(encoding='utf-8'))['archives']
for stage in STAGES:
 a=next(x for x in defs if x['round']==stage);chain=a['archive_chain'];b=Path(chain[0]).read_bytes()
 for member in chain[1:]:
  with zipfile.ZipFile(BytesIO(b))as z:b=z.read(member)
 assert sha(b)==a['sha256'];archives[stage]=zipfile.ZipFile(BytesIO(b))
 provenance.append({'stage':stage,'role':'FROZEN_STAGE_ARCHIVE_READ_ONLY','archive_chain':chain,'sha256':a['sha256'],'bytes':len(b)})
 print('SOURCE_ARCHIVE_VERIFIED',stage,flush=True)
def read(stage,name):
 b=archives[stage].read(name);provenance.append({'stage':stage,'role':'ACTUALLY_READ_MEMBER','member':name,'sha256':sha(b),'bytes':len(b)})
 return json.loads(gzip.decompress(b)if name.endswith('.gz')else b)
def readcsv(stage,name):
 b=archives[stage].read(name);provenance.append({'stage':stage,'role':'ACTUALLY_READ_MEMBER','member':name,'sha256':sha(b),'bytes':len(b)});return list(csv.DictReader(b.decode('utf-8-sig').splitlines()))
raw_by_scene={};source_by_scene={}
sys.path.insert(0,str(RT));from src.frozen_scene.native_adapter import Source
for s in manifest['scenes']:
 p=RT/s['source_path'];b=p.read_bytes();assert sha(b)==s['source_sha256'];j=json.loads(b)
 raw_by_scene[s['scene_id']]={f"{r['type']}/{r['id']}":r for r in j['elements']};source_by_scene[s['scene_id']]=Source(j)
 provenance.append({'stage':'CURRENT_SOURCE','member':s['source_path'],'sha256':sha(b),'bytes':len(b)})

restored=[];all_sem=readcsv('WALKABILITY-R2','data/semantics_edges.csv');seen=set()
for r in all_sem:
 if r['restored'].lower()!='true':continue
 source=source_by_scene[r['scene_id']];obj=source.ways.get(int(r['way_id']));nodes=json.loads(r['native_nodes']);coordinates=json.loads(r['coordinates_wgs84']);idx=int(r['segment_index'])
 match=bool(obj and obj.get('nodes',[])[idx:idx+2]==nodes and all(n in source.nodes for n in nodes))
 if match:match=all(math.dist(source.coord('node/'+str(n)),p)<=1e-12 for n,p in zip(nodes,coordinates))
 length=LineString([P(*p)for p in coordinates]).length
 tags=json.loads(r['tags']);tag_match=obj is not None and obj.get('tags',{})==tags
 identity=(r['source_id'],idx,tuple(nodes),r['layer_key'],r['level_key'],json.dumps(coordinates,separators=(',',':')))
 if identity in seen:continue
 seen.add(identity);directions=json.loads(r['directions'])
 restored.append({'source_id':r['source_id'],'source_version':obj.get('version')if obj else None,'segment_index':idx,'native_nodes':nodes,'native_coordinate_match':match,'tags_match':tag_match,'layer_key':r['layer_key'],'level_key':r['level_key'],'declared_directions':directions,'arcs':len(directions),'old_length_m':float(r['length_m']),'recomputed_length_m':length,'length_error_m':length-float(r['length_m']),'status':'PASS'if match and tag_match and abs(length-float(r['length_m']))<=1e-6 else'FAIL','result':'RESTORED_NATIVE_EDGE'if match else'UNSUPPORTED_DERIVED_EDGE','whole_grass_area_granted':False,'scope':'Explicit native source segment only; directions are frozen-policy declarations, not field same-level verification'})
csvout('restored_native_edges.csv',restored)
print('RESTORED_SEGMENTS_AUDITED',len(restored),flush=True)

newfaces=read('PED-AREA-CONNECTIVITY-R1','data/connectivity/global_source_identity.json')
selection=read('PED-AREA-CONNECTIVITY-R1','data/connectivity/source_selection_lock.json')
old_ids={i for s in selection['scenes']for i in s['old_area_ids']}
identities=[o for o in newfaces['objects']if o['source_id']not in old_ids]
relevance=readcsv('PED-AREA-CONNECTIVITY-R2','NEW_FACE_ROUTE_RELEVANCE.csv');usage=[]
for obj in identities:
 sid=obj['source_id'];raw_matches=[]
 for scene in obj['scenes']:
  raw=raw_by_scene[scene].get(sid);raw_matches.append(bool(raw and raw.get('version')==obj.get('version')))
 evidence=[r for r in relevance if r['source_area_id']==sid and r['global_unique_new']=='True']
 in_pool=any(r['in_query_scene']=='True'for r in evidence)
 usage.append({'source_id':sid,'version':obj['version'],'source_snapshot_time':obj['source_timestamp'],'source_scenes':obj['scenes'],'raw_identity_match':all(raw_matches),'in_business_face_pool':in_pool,'business_case_evidence':[{k:r[k]for k in ['case','method','record_scene_id','present_in_query_namespace','owned_node_count','component_labels','in_start_component','in_goal_component','reason','intersects_route','slack_lower_bound_m']}for r in evidence],'any_archived_route_geometry_intersection':any(r['intersects_route']=='True'for r in evidence),'reason_set':sorted({r['reason']for r in evidence}),'status':'PASS'if all(raw_matches)and evidence else'INCONCLUSIVE','evidence_scope':'New source-ID/version audit + saved directed-component/owner/alternative evidence; no new SCC or route solve'})
csvout('added_face_usage.csv',usage)

# Exact source-object lineage reconciliation, not a new admission algorithm.
foundation=ROOT.parent/'SMART_CITY_WALKABILITY_FOUNDATION_PG1/delivery/PG1_FOUNDATION_REVIEW.zip'
assert sha(foundation.read_bytes())=='7c9ed58766177e8906defc257555b0d7ba0d92c8e97129a691f9f6e72dffef7c'
trace_fields=['scene_id','source_id','source_version','discovered_in_raw','source_tags_match','parsed_geometry_in_saved_adapter','geometry_valid_in_saved_adapter','native_kept_segments','native_rejected_segments','rejection_reasons','native_edges_generated','face_status','derived_or_assumption_generation','route_usage','status','scope']
trace_stats=collections.Counter();route_uses=collections.Counter()
primary=readcsv('PED-AREA-CONNECTIVITY-R1','results/sample_results.csv')
app_documents=[];response_bindings=[]
for rec in primary:
 f=rec.get('file')or rec.get('output_file')or rec.get('response_file')
 if not f:
  f=next((v for k,v in rec.items()if str(v).startswith('runs/')and str(v).endswith('.json')),None)
 if not f:continue
 doc=read('PED-AREA-CONNECTIVITY-R1',f)
 expected=rec.get('response_sha256')or rec.get('sha256')
 actual=sha(archives['PED-AREA-CONNECTIVITY-R1'].read(f))
 response_bindings.append({'stage':'PED-AREA-CONNECTIVITY-R1','attempt_id':rec.get('attempt_id'),'file':f,'expected_sha256':expected,'actual_sha256':actual,'status':'PASS'if expected==actual else'FAIL'})
 app_documents.append(('PED-AREA-CONNECTIVITY-R1',f,doc))
 if rec.get('role')=='BASELINE_POSITIVE':
  for seg in doc.get('route',{}).get('segments',[]):route_uses[(doc.get('input',{}).get('scene_id'),seg.get('source_area_id',seg.get('source_id')))]+=1
with zipfile.ZipFile(foundation)as z,(D/'source_to_graph_trace.csv').open('w',encoding='utf-8-sig',newline='')as out:
 writer=csv.DictWriter(out,fieldnames=trace_fields);writer.writeheader()
 for scene,raw in raw_by_scene.items():
  name=f'phase1/data/{scene}/object_lineage.jsonl.gz';b=z.read(name);provenance.append({'stage':'PG1_SOURCE_TRACE','member':name,'sha256':sha(b),'bytes':len(b)})
  with gzip.open(BytesIO(b),'rt',encoding='utf-8')as f:
   for line in f:
    r=json.loads(line);obj=raw.get(r['source_id']);tags_match=bool(obj is not None and obj.get('tags',{})==r['raw']['tags']);routing=r['routing'];status='PASS'if tags_match else'FAIL'
    row=dict(scene_id=scene,source_id=r['source_id'],source_version=r.get('source_version'),discovered_in_raw=obj is not None,source_tags_match=tags_match,parsed_geometry_in_saved_adapter=r['raw'].get('geometry_type')is not None,geometry_valid_in_saved_adapter=r['raw'].get('geometry_valid'),native_kept_segments=routing['native_kept_segments'],native_rejected_segments=routing['native_rejected_segments'],rejection_reasons=json.dumps(routing.get('native_rejection_reasons'),ensure_ascii=False),native_edges_generated=routing['native_kept_segments']>0,face_status=routing.get('face_status'),derived_or_assumption_generation='SAVED_FACE_OR_LOCAL_DOMAIN_EVIDENCE_ONLY; NO FULL_VG_REBUILD',route_usage=route_uses[(scene,r['source_id'])],status=status,scope='Raw identity freshly compared; stage admission is verified saved trace, not rerun old parser/controlled masking')
    writer.writerow(row);trace_stats[status]+=1;trace_stats['rows']+=1
  print('SOURCE_TRACE_COMPLETE',scene,trace_stats['rows'],flush=True)

# Build an independent raw-source 2D geometry index. Level uncertainty stays explicit.
negative_indexes={}
DENIED={'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
for scene,source in source_by_scene.items():
 records=[]
 for kind,objects in [('way',source.ways),('relation',source.relations)]:
  for num,obj in objects.items():
   tags=obj.get('tags',{});sid=f'{kind}/{num}';category='BUILDING'if tags.get('building')not in(None,'no')else'PERMISSION'if tags.get('foot',tags.get('access'))in DENIED else'WATER'if tags.get('natural')in('water','wetland')or tags.get('water')else'BARRIER'if tags.get('barrier')in('wall','fence','hedge','retaining_wall','chain','city_wall','jersey_barrier')else None
   if not category:continue
   geometry=None
   try:
    geometry=source.area(sid)if category!='BARRIER'else None
    if geometry is None and kind=='way':
     ns=obj.get('nodes',[])
     if len(ns)>=2 and all(n in source.projected for n in ns):geometry=LineString([source.projected[n]for n in ns])
   except(KeyError,ValueError):pass
   if geometry is not None and not geometry.is_empty:
    records.append({'id':sid,'kind':category,'tags':tags,'geometry':geometry,'gate_points':[Point(source.projected[n])for n in obj.get('nodes',[])if n in source.nodes and source.nodes[n].get('tags',{}).get('barrier')in('gate','entrance','lift_gate','swing_gate','bollard')]})
 negative_indexes[scene]=(records,STRtree([r['geometry']for r in records]))

replay=[];constraints=[];segments_audited=0;unknown_scene=0
def infer_scene(doc,default=None):
 inp=doc.get('input',{});return inp.get('scene_id')or doc.get('scene_id')or('sh-library'if doc.get('case')=='library'else'sh-huangpu-01'if doc.get('case')else default)
def audit_route(stage,source_file,ident,segments,stored_length,scene,method='',source_status='',record_role='ROUTE'):
 global segments_audited,unknown_scene
 aggregated=any('layer'not in s and'hypothesis_m'in s for s in segments)
 computed=0.;stored_sum=0.;conflicts=[];uncertain=[];counts=collections.Counter();lens=collections.Counter();previous=None;maxgap=0.
 for i,s in enumerate(segments):
  xy=s.get('xy')or s.get('coordinates')
  if not xy or len(xy)<2:continue
  line=LineString(xy);computed+=line.length;stored_sum+=float(s.get('length_m',line.length));layer=s.get('layer','AGGREGATED_DECLARED_SOURCE'if'hypothesis_m'in s else'UNKNOWN');counts[layer]+=1;lens[layer]+=line.length;segments_audited+=1
  if previous is not None:maxgap=max(maxgap,math.dist(previous,xy[0]))
  previous=xy[-1]
  if scene in negative_indexes:
   records,index=negative_indexes[scene]
   for j in index.query(line,predicate='intersects'):
    rec=records[j];g=rec['geometry'];tags=s.get('tags',{});vertical=any(tags.get(k)not in(None,'','0','no','false')for k in('bridge','tunnel','layer','level','indoor'))or any(rec['tags'].get(k)not in(None,'','0','no','false')for k in('bridge','tunnel','layer','level','indoor'))
    if rec['kind']=='BARRIER':
     hit=line.intersection(g)
     if hit.is_empty:continue
     points=[hit]if hit.geom_type=='Point'else list(hit.geoms)if hit.geom_type=='MultiPoint'else[]
     if points and all(any(q.distance(p)<=1e-6 for p in rec['gate_points'])for q in points):continue
     if hit.length<=1e-6:
      uncertain.append({'segment':i,'object':rec['id'],'reason':'BARRIER_POINT_CONTACT_NO_VERIFIED_OPENING_WIDTH'});continue
     overlap=hit.length
    else:
     if g.geom_type not in('Polygon','MultiPolygon'):continue
     overlap=line.intersection(g.buffer(-1e-7)).length
     if overlap<=1e-6:continue
    issue={'segment':i,'object':rec['id'],'kind':rec['kind'],'overlap_m':overlap,'route_tags':tags,'source_tags':rec['tags']}
    (uncertain if vertical else conflicts).append(issue)
  else:unknown_scene+=1
 error=None if stored_length is None else computed-float(stored_length)
 status='FAIL'if conflicts or counts['UNKNOWN']or(error is not None and abs(error)>1e-6)or(maxgap>1e-6 and record_role=='ROUTE')else'INCONCLUSIVE'if uncertain or scene not in negative_indexes or not segments or aggregated else'PASS'
 run='Q6-REPLAY-'+hashlib.sha256((stage+source_file+ident).encode()).hexdigest()[:16]
 replay.append({'experiment_id':'Q6-LOCAL-MAP-CONSISTENCY-R1','run_id':run,'stage':stage,'source_file':source_file,'original_run_or_query':ident,'sample_unit':record_role,'scene_id':scene,'method':method,'original_algorithm_status':source_status,'status':status,'stored_length_m':stored_length,'stored_segment_sum_m':stored_sum,'recomputed_length_m':computed,'absolute_length_error_m':abs(error)if error is not None else None,'strict_1e_8_match':abs(error)<=1e-8 if error is not None else None,'constraint_and_length_epsilon_m':1e-6,'tolerance_basis':'Frozen common_constraints EPS and planner continuity contract; strict numerical error also separately reported, never edit old numbers','segments':len(segments),'native_m':None if aggregated else lens['native'],'derived_m':None if aggregated else lens['derived'],'assumption_m':sum(s.get('hypothesis_m',0)for s in segments)if aggregated else sum(lens[k]for k in('inferred','unknown','assumed')),'max_continuity_gap_m':maxgap,'new_2D_conflicts':len(conflicts),'level_or_barrier_uncertainties':len(uncertain),'source_composition_status':'AGGREGATED_NATIVE_DERIVED_UNSPLIT'if aggregated else'EXPLICIT_LAYERS'})
 constraints.append({'run_id':run,'stage':stage,'source_file':source_file,'scene_id':scene,'status':status,'raw_source_2D_conflicts':conflicts,'uncertainties':uncertain,'assumption_label_missing':counts['UNKNOWN'],'road_axis_and_native_sidewalk_distinction':'Tags remain explicit; source native class may include declared shared-road-axis assumption','level_status':'No 2D crossing promoted to same-level fact','field_truth':'NOT_AVAILABLE','audit_scope':'Independent raw source planar contacts; not exact historical clearance-policy replay or field truth'})

for stage,file,doc in app_documents:
 route=doc.get('route')
 if route and route.get('segments'):audit_route(stage,file,doc.get('run_id',file),route['segments'],route.get('length_m'),infer_scene(doc),doc.get('normalized_request',{}).get('method',''),doc.get('status',''))
for file in archives['PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED'].namelist():
 if file.startswith('runs/main_matrix_R2/')and file.endswith('.json'):
  doc=read('PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED',file);r=doc.get('route')
  if r:audit_route('PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED',file,doc['run_id'],r['segments'],r['length_m'],infer_scene(doc),doc['input'].get('method',''),doc['status'])
for file in archives['PED-AREA-CONNECTIVITY-R2'].namelist():
 if file.startswith('runs/')and file.endswith('.json')and 'provenance'not in file:
  doc=read('PED-AREA-CONNECTIVITY-R2',file);r=doc.get('minimum',{});segs=r.get('segments',r.get('edges',[]))
  if segs:audit_route('PED-AREA-CONNECTIVITY-R2',file,doc['invocation_id'],segs,r.get('length_m'),infer_scene(doc),doc.get('method',''),'SAVED_DIAGNOSTIC_MINIMUM')
free_manifest=read('FREE-SPACE-R1-FINAL','data/task_manifest.json')
free_scenes={r['id']:r.get('group',r.get('scene_id'))for r in free_manifest['instances']}
free_scenes['NORTH_160']='sh-huangpu-01'
for file in archives['FREE-SPACE-R1-FINAL'].namelist():
 if file.startswith('data/routes/')and file.endswith('.json.gz'):
  doc=read('FREE-SPACE-R1-FINAL',file)
  for ident,r in doc.get('routes',{}).items():
   segs=r.get('edges',[])
   if segs or r.get('reached'):audit_route('FREE-SPACE-R1-FINAL',file,ident,segs,r.get('length_m'),free_scenes.get(doc.get('input_id')),doc.get('method',''),r.get('status',''))
for stage,files in [('WALKABILITY-R2',['data/semantics_routes.geojson','data/inference_routes.geojson']),('WALKABILITY-R3',['data/semantics_routes.geojson','data/north_routes.geojson'])]:
 for file in files:
  doc=read(stage,file);groups=collections.defaultdict(list)
  for f in doc.get('features',[]):
   props=f.get('properties',{});g=f.get('geometry',{})
   if props.get('role')!='route_segment'or g.get('type')!='LineString':continue
   xy=[P(*p)for p in g['coordinates']]
   layer=props.get('layer')or('native'if props.get('kind')=='NATIVE_LINEAR'else'inferred'if props.get('hypothesis')else'derived')
   ident=str(props.get('variant',''))+'|'+str(props.get('query_id',''))
   groups[ident].append({**props,'xy':xy,'layer':layer})
  for ident,segs in groups.items():
   segs.sort(key=lambda s:s.get('sequence',0));audit_route(stage,file,ident,segs,sum(s.get('length_m',0)for s in segs),'sh-huangpu-01',ident,record_role='ROUTE_GEOJSON_GROUP')

csvout('replay_comparison.csv',replay)
csvout('route_constraint_audit.csv',constraints)
csvout('response_binding_audit.csv',response_bindings)
csvout('provenance.csv',provenance)
write(D/'outputs/route_constraint_details.json',constraints)
summary={'status':'FAIL'if any(r['status']=='FAIL'for r in restored)or trace_stats['FAIL']else'INCONCLUSIVE','fresh_audit_started_at':datetime.datetime.now().astimezone().isoformat(),'frozen_stages_covered':STAGES,'source_trace_records':trace_stats['rows'],'source_identity_tag_mismatches':trace_stats['FAIL'],'restored_unique_native_segments':len(restored),'restored_directed_arc_declarations':sum(r['arcs']for r in restored),'restored_identity_failures':sum(r['status']=='FAIL'for r in restored),'added_unique_faces':len(usage),'new_faces_in_business_pool':sum(r['in_business_face_pool']for r in usage),'new_face_identity_inconclusive_or_failures':sum(r['status']!='PASS'for r in usage),'saved_route_groups_recomputed':len(replay),'saved_segments_recomputed':segments_audited,'route_audit_status_counts':dict(collections.Counter(r['status']for r in replay)),'geometry_recompute_tolerance_m':1e-6,'new_graph_or_path_searches':0,'field_truth_compared':False,'limitations':['Saved admission traces and directed-component labels verified against raw identities; historical controlled-masking graphs not rebuilt','Raw-source 2D building/private/water/barrier contacts are not the exact historical allowance/clearance policy; contact findings must be reviewed before calling historical algorithm wrong','Some controlled-task route files do not carry raw scene association; those constraint checks remain INCONCLUSIVE rather than inventing the scene','This re-audits saved geometry; it is not a new route experiment or a field truth comparison']}
write(D/'summary.json',summary)
with(D/'raw_results.jsonl').open('a',encoding='utf-8')as f:
 for stage in STAGES:
  subset=[r for r in replay if r['stage']==stage]
  f.write(json.dumps({'experiment_id':'Q6-LOCAL-MAP-CONSISTENCY-R1','run_id':'Q6-AUDIT-'+stage,'scene_id':'FROZEN_MULTI_SCENE','building_id':'MULTIPLE_OR_CONTROLLED_TASK','entrance_id':'NOT_ALL_ROWS_ARE_DOOR_TASKS','method':'READ_ONLY_GEOMETRY_AND_IDENTITY_RECOMPUTE','input_version':next(a['sha256']for a in defs if a['round']==stage),'status':'INCONCLUSIVE'if any(r['status']!='PASS'for r in subset)or not subset else'PASS','result':{'route_groups':len(subset),'constraints_status_counts':dict(collections.Counter(r['status']for r in subset))},'failure_reason':'See per-route limitations; no exact historical full-policy reconstruction','route_length_m':None,'assumption_length_m':None,'runtime_ms':None,'source_edge_count':None,'derived_edge_count':None,'assumption_edge_count':None,'output_file':'replay_comparison.csv'},ensure_ascii=False)+'\n')
print(json.dumps(summary,ensure_ascii=False),flush=True)
