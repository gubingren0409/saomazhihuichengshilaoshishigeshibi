from experiment_core import *
from shapely.geometry import shape,box
from shapely.ops import transform
from src.frozen_scene.native_adapter import PROJECT
from src.scene_data import non_ground,restricted
import gc,zipfile

def geometry_context(prepared):
 sid=prepared['data']['scene_id'];meta=next(s for s in json.loads((RUNTIME/'data/scene_manifest.json').read_text(encoding='utf-8'))['scenes']if s['scene_id']==sid)
 raw=json.loads((RUNTIME/meta['source_path']).read_text(encoding='utf-8'))['elements'];nodes={r['id']:r for r in raw if r['type']=='node'}
 scene=json.loads((RUNTIME/'data/scenes'/sid/'frozen_scene.json').read_text(encoding='utf-8-sig'))
 building=transform(PROJECT,shape(scene['building_footprint']));roads=[];footways=[];restrictions=[]
 for r in raw:
  if r['type']!='way':continue
  tags=r.get('tags',{});ids=r.get('nodes',[])
  if len(ids)<2 or any(n not in nodes for n in ids):continue
  coords=[PROJECT(nodes[n]['lon'],nodes[n]['lat'])for n in ids];line=LineString(coords)
  ident='way/'+str(r['id'])
  if tags.get('highway')in{'motorway','motorway_link','trunk','trunk_link','primary','secondary','tertiary','unclassified','residential','service','living_street','road'}:roads.append((ident,line,tags))
  if tags.get('highway')in{'footway','path','pedestrian','steps'}and tags.get('area')!='yes':footways.append((ident,line,tags))
  if tags.get('barrier')or restricted(tags)or tags.get('natural')in{'water','wetland'}:restrictions.append((ident,line,tags))
 return scene,building,nodes,roads,footways,restrictions,meta

def entry_audit(prepared,req,context):
 scene,building,nodes,roads,footways,restrictions,meta=context;door=prepared['data']['door'];point=Point(door['xy']);node=nodes.get(int(door['id'].split('/')[1]))
 raw=json.loads((RUNTIME/meta['source_path']).read_text(encoding='utf-8'))['elements'];obj=next((r for r in raw if r['type']+'/'+str(r['id'])==scene['building_native_id']),None)
 match=bool(node and obj and int(node['id'])in obj.get('nodes',[])and all(node.get('tags',{}).get(k)==v for k,v in door['tags'].items())and math.dist(PROJECT(node['lon'],node['lat']),door['xy'])<=1e-6)
 def nearest(rows):
  if not rows:return None,None
  sid,g,_=min(rows,key=lambda r:(r[1].distance(point),r[0]));return sid,g.distance(point)
 rid,rd=nearest(roads);fid,fd=nearest(footways)
 legal=[f for f in prepared.get('faces',[])if not f['omega'].is_empty]
 face=min(legal,key=lambda f:(f['omega'].distance(point),f['source_id']))if legal else None
 nearby=[{'source_id':i,'distance_m':g.distance(point),'tags':t}for i,g,t in restrictions if g.distance(point)<=30]
 relation='BOUNDARY'if building.boundary.distance(point)<=1e-6 else'INSIDE'if building.contains(point)else'OUTSIDE'
 return dict(experiment_id=IDS['q2'],scene_id=req['scene_id'],building_id=scene['building_native_id'],entrance_id=door['id'],longitude=node['lon']if node else None,latitude=node['lat']if node else None,tags=door['tags'],purpose=req['purpose'],physical_door='UNKNOWN',current_public_opening='UNKNOWN',boundary_relation=relation,boundary_distance_m=building.boundary.distance(point),source_identity='NATIVE_OUTER_RING_AND_COORDINATES_MATCH'if match else'INVALID_ENTRANCE_IDENTITY',status='PASS'if match else'INVALID_INPUT',nearest_road_id=rid,nearest_road_distance_m=rd,nearest_native_footway_id=fid,nearest_native_footway_distance_m=fd,nearest_legal_face_id=face['source_id']if face else None,nearest_legal_face_distance_m=face['omega'].distance(point)if face else None,nearby_restrictions=nearby,source_sha256=meta['source_sha256'],distance_scope='Projected EPSG32651; frozen parseable source geometry and admitted Omega; road centerline is not road edge')

def target_experiments(prepared,req,context,index):
 scene,building,*_=context;door=prepared['data']['door']
 candidates=[(math.dist(r['xy'],door['xy']),n,r)for n,r in prepared['source'].nodes(data=True)if str(n).startswith('node/')and not non_ground(r.get('tags',{}))and not restricted(r.get('tags',{}))and not building.contains(Point(r['xy']))and any(s['layer']=='native'for _,_,e in list(prepared['source'].in_edges(n,data=True))+list(prepared['source'].out_edges(n,data=True))for s in e['segments'])]
 if not candidates:raise ValueError('NO_NATIVE_OUTSIDE_APPROACH_POINT')
 dist,n,r=min(candidates,key=lambda x:(x[0],x[1]))
 targets=[('REGISTERED_DOOR',None),('BUILDING_CENTROID',dict(id='control/centroid/'+scene['building_native_id'],xy=list(building.centroid.coords)[0],tags={},role='CONTROL_INTERIOR_POINT')),('NATIVE_OUTSIDE_APPROACH_POINT',dict(id=n,xy=r['xy'],tags=r.get('tags',{}),role='EXISTING_NATIVE_NODE_NOT_NEW_ENTRANCE'))]
 write(ROOT/IDS['q2']/f'outputs/targets_locked_{index}.json',{'selection_before_new_target_route_tests':True,'targets':targets,'outer_rule':'Nearest ground eligible native graph node not inside building, stable ID tie; may coincide with door; not a physical door reference','nearest_native_distance_m':dist})
 rows=[];registered=None;registered_graph=None
 for kind,target in targets:
  tick=time.perf_counter();g,a,b,end,bindings=bind_graph(prepared,req,target);out=solve(prepared,g,a,b,end['xy'],req['method'])
  run=f'Q2-TARGET-{index}-{kind}';row=base_row(IDS['q2'],run,req['scene_id'],req['door_id'],req['method']);row['building_id']=scene['building_native_id']
  complete_row(row,out,(time.perf_counter()-tick)*1000)
  row.update(target_definition=kind,target_id=b,target_xy=end['xy'],endpoint_to_registered_door_m=math.dist(end['xy'],prepared['data']['door']['xy']),target_is_registered_door=kind=='REGISTERED_DOOR',source_context_hash=prepared['graph_sha'],source_start_id=a,preprocessing_cache=True,output_file=f'outputs/{run}.json')
  write(ROOT/IDS['q2']/row['output_file'],{'row':row,'route':out.get('route'),'bindings':bindings,'validation':out.get('validation')});append(IDS['q2'],row);rows.append(row)
  if kind=='REGISTERED_DOOR':registered=out;registered_graph=g
  else:del g
  print(json.dumps({'event':'TARGET_RESULT','run':run,'status':row['status'],'length':row['route_length_m']},ensure_ascii=False),flush=True)
 return rows,registered,registered_graph

def dynamic_graph(graph,closed_nodes,edge_id,obstacle):
 out=nx.DiGraph();out.add_nodes_from((n,r)for n,r in graph.nodes(data=True)if n not in closed_nodes);changes=[]
 for u,v,row in graph.edges(data=True):
  if u in closed_nodes or v in closed_nodes:continue
  options=[]
  for option in row.get('routing_alternatives',[row['segments']]):
   reasons=[]
   if edge_id and any(s.get('edge_id')==edge_id for s in option):reasons.append('SIMULATED_SOURCE_EDGE_REMOVAL')
   if obstacle is not None and any(LineString(s['xy']).intersection(obstacle).length>1e-6 for s in option):reasons.append('SIMULATED_TEMP_OBSTACLE_INTERIOR')
   if reasons:changes.append({'u':u,'v':v,'source_ids':[s.get('source_id')for s in option],'edge_ids':[s.get('edge_id')for s in option],'reason':reasons})
   else:options.append(option)
  if options:
   primary=min(options,key=lambda o:P._option_key(o,1));out.add_edge(u,v,**{**row,'segments':primary,'routing_alternatives':options})
 return out,changes

def closure_experiments(prepared,req,graph,baseline,index):
 if baseline['status']!='PASS':return [dict(experiment_id=IDS['q7'],run_id=f'Q7-{index}-BLOCKED',scene_id=req['scene_id'],status='BLOCKED_BY_MISSING_INPUT',failure_reason='NO_VALID_BASELINE_ROUTE_FOR_STATE_SELECTION')]
 natives=[s for s in baseline['route']['segments']if s['layer']=='native'and s.get('edge_id')and s['length_m']>1]
 if not natives:raise ValueError('NO_NATIVE_EDGE_FOR_REGISTERED_DYNAMIC_CASE')
 chosen=natives[len(natives)//2];line=LineString(chosen['xy']);center=line.interpolate(.5,normalized=True);radius=min(1.,line.length/4);obstacle=box(center.x-radius,center.y-radius,center.x+radius,center.y+radius)
 states=[('S0',False,False,False),('S1',True,False,False),('S2',False,True,False),('S3',False,False,True),('S4',True,True,False),('S5',False,False,False)]
 config={'scene_id':req['scene_id'],'request':req,'baseline_geometry_signature':baseline['geometry_signature'],'selected_native_edge_id':chosen['edge_id'],'selected_source_id':chosen['source_id'],'obstacle':mapping(obstacle),'state_selection_rule':'Before any closure route: middle native baseline segment; 2m-or-smaller square centered at segment midpoint; no outcomes used','states':states,'prepared_graph_sha256':prepared['graph_sha'],'adapter_scope':'NEW_EXPERIMENT_STATE_INJECTION_WRAPPER; frozen solver unchanged; not existing APP automatic dynamic perception'}
 write(ROOT/IDS['q7']/f'outputs/dynamic_scenarios_{index}.json',config)
 rows=[];change_rows=[];forbidden=[]
 for state,close,remove,block in states:
  tick=time.perf_counter();g,changes=dynamic_graph(graph,{req['door_id']}if close else set(),chosen['edge_id']if remove else None,obstacle if block else None);build_ms=(time.perf_counter()-tick)*1000
  version=digest({'graph_sha':prepared['graph_sha'],'closed_door':req['door_id']if close else None,'edge':chosen['edge_id']if remove else None,'obstacle':mapping(obstacle)if block else None})
  change_rows.extend({'scene_id':req['scene_id'],'state':state,**c}for c in changes)
  for repeat in range(3):
   tick=time.perf_counter();out=solve(prepared,g,req['start_id'],req['door_id'],prepared['data']['door']['xy'],req['method'],obstacle if block else None)
   used=bool(out.get('route')and((remove and any(s.get('edge_id')==chosen['edge_id']for s in out['route']['segments']))or(close and out['status']=='PASS')or(block and any(LineString(s['xy']).intersection(obstacle).length>1e-6 for s in out['route']['segments']))))
   if used:out['status']='FAIL';out['failure']='FORBIDDEN_SIMULATED_OBJECT_USED'
   run=f'Q7-{index}-{state}-{repeat}';row=base_row(IDS['q7'],run,req['scene_id'],req['door_id'],req['method']);complete_row(row,out,(time.perf_counter()-tick)*1000+(build_ms if repeat==0 else 0))
   row.update(building_id=prepared['data']['door']['building_id'],state=state,repeat=repeat,control_variant='STATE_INJECTION_ADAPTER',state_version=version,graph_nodes=len(g),graph_arcs=g.number_of_edges(),state_overlay_build_ms=build_ms if repeat==0 else 0.,preprocessing_cache=True,state_overlay_cache=repeat>0,route_answer_cache=False,process_cold_start=False,solver_invoked=out['solver']['invoked'],forbidden_object_used=used,restored_to_S0=(out.get('geometry_signature')==baseline['geometry_signature'])if state in('S0','S5')else None,output_file=f'outputs/{run}.json')
   write(ROOT/IDS['q7']/row['output_file'],{'row':row,'route':out.get('route'),'validation':out.get('validation')});append(IDS['q7'],row);rows.append(row)
  del g;gc.collect()
  print(json.dumps({'event':'DYNAMIC_STATE_DONE','case':index,'state':state,'status':rows[-1]['status'],'closure_edges':len(changes)},ensure_ascii=False),flush=True)
 # Negative control: current public APP has no dynamic-state input contract.
 req2={**req,'request_id':f'Q7-NATIVE-API-CONTROL-{index}','dynamic_state':{'closed_doors':[req['door_id']]}}
 tick=time.perf_counter();native=P.plan(req2);elapsed=(time.perf_counter()-tick)*1000
 ignores=native.get('validation',{}).get('passed')and native.get('door',{}).get('id')==req['door_id']
 row=base_row(IDS['q7'],f'Q7-NATIVE-API-CONTROL-{index}',req['scene_id'],req['door_id'],req['method'],'FAIL'if ignores else'INCONCLUSIVE')
 row.update(runtime_ms=elapsed,control_variant='UNMODIFIED_PUBLIC_APP_INTERFACE',state='S1',failure_reason='DYNAMIC_CLOSURE_PARAMETER_IGNORED_UNSUPPORTED'if ignores else'NO_DYNAMIC_INTERFACE_CONTRACT',result={'algorithm_status':native['status'],'solver':native['solver'],'native_dynamic_state_support':False},output_file=f'outputs/Q7-NATIVE-API-CONTROL-{index}.json')
 write(ROOT/IDS['q7']/row['output_file'],native);append(IDS['q7'],row);rows.append(row)
 return rows,change_rows

def main():
 identity=[];target_rows=[];dynamic=[];changes=[];requests=fixed_requests()
 write(ROOT/IDS['q2']/'outputs/fixed_requests_before_execution.json',requests)
 for i,req in enumerate(requests):
  print(json.dumps({'event':'CASE_PREPARATION_START','case':i,'request':req,'timestamp':stamp()},ensure_ascii=False),flush=True)
  t=time.perf_counter();prepared,hit,seconds=prepare(req);print(json.dumps({'event':'PREPARED','case':i,'seconds':time.perf_counter()-t,'cache_hit':hit},ensure_ascii=False),flush=True)
  context=geometry_context(prepared);audit=entry_audit(prepared,req,context);identity.append(audit);csvout(ROOT/IDS['q2']/'entry_identity_audit.csv',identity)
  if audit['status']!='PASS':
   append(IDS['q2'],{**base_row(IDS['q2'],f'Q2-IDENTITY-{i}',req['scene_id'],req['door_id'],req['method'],'INVALID_INPUT'),'result':audit});continue
  rows,out,g=target_experiments(prepared,req,context,i);target_rows+=rows;csvout(ROOT/IDS['q2']/'target_definition_comparison.csv',target_rows)
  if i in(0,2):
   d,c=closure_experiments(prepared,req,g,out,i);dynamic+=d;changes+=c;csvout(ROOT/IDS['q7']/'dynamic_route_results.csv',dynamic);csvout(ROOT/IDS['q7']/'closure_edge_changes.csv',changes,['scene_id','state','u','v','source_ids','edge_ids','reason'])
  del g,prepared;gc.collect()
  write(ROOT/'audit/entry_dynamic_checkpoint.json',{'completed_cases':i+1,'identity_count':len(identity),'target_rows':len(target_rows),'dynamic_rows':len(dynamic),'timestamp':stamp()})
 write(ROOT/IDS['q2']/'summary.json',{'identity_cases':len(identity),'identity_valid':sum(r['status']=='PASS'for r in identity),'target_definition_queries':len(target_rows),'by_target_status':{k:sum(r['status']==k for r in target_rows)for k in ['PASS','FAIL','NO_PATH','INVALID_INPUT']},'field_facts':'UNKNOWN','status':'PASS'if all(r['status']=='PASS'for r in identity)and not any(r['status']=='FAIL'for r in target_rows)else'FAIL'})
 write(ROOT/IDS['q7']/'summary.json',{'status':'FAIL'if any(r['control_variant']=='UNMODIFIED_PUBLIC_APP_INTERFACE'and r['status']=='FAIL'for r in dynamic)else'INCONCLUSIVE','adapter_rows':sum(r['control_variant']=='STATE_INJECTION_ADAPTER'for r in dynamic),'native_interface_negative_controls':sum(r['control_variant']=='UNMODIFIED_PUBLIC_APP_INTERFACE'for r in dynamic),'forbidden_route_violations_in_adapter':sum(r.get('forbidden_object_used',False)for r in dynamic),'restoration_rows':sum(r.get('state')=='S5'for r in dynamic),'limitation':'Unmodified current APP lacks dynamic closure contract; adapter tests do not claim deployed functionality. First state overlay vs hot reuse is not process cold start.'})
 csvout(ROOT/IDS['q7']/'forbidden_object_usage.csv',[{k:r.get(k)for k in ['run_id','scene_id','control_variant','state','status','forbidden_object_used','restored_to_S0']}for r in dynamic])
 csvout(ROOT/IDS['q7']/'fallback_route_comparison.csv',dynamic)
 write(ROOT/IDS['q7']/'dynamic_scenarios.json',{'cases':[json.loads(p.read_text(encoding='utf-8'))for p in sorted((ROOT/IDS['q7']/'outputs').glob('dynamic_scenarios_*.json'))]})
 print('ENTRY_AND_DYNAMIC_COMPLETE',flush=True)
if __name__=='__main__':main()
