"""New K=2 cost-selection test adapter, outside approach only, no old APP modification."""
from experiment_core import *
from phase_timers import install_phase_timers
phases=install_phase_timers()
import argparse,gc
ap=argparse.ArgumentParser();ap.add_argument('--temperature',required=True);ap.add_argument('--repeat',type=int,default=0);args=ap.parse_args();D=ROOT/IDS['q8'];prepared_cache={}
requests=sorted([dict(r,purpose='APPROACH_OUTSIDE',method='F1')for r in fixed_requests()if r['scene_id']=='sh-huangpu-01'],key=lambda r:r['door_id'])
assert len(requests)==2 and len({r['start_id']for r in requests})==1
def input_binding(req):
 manifest_path=RUNTIME/'data/scene_manifest.json';manifest_bytes=manifest_path.read_bytes();manifest=json.loads(manifest_bytes);meta=next(r for r in manifest['scenes']if r['scene_id']==req['scene_id']);code=P.code_identity()
 if code!=P.IMPORTED_CODE_SHA:raise ValueError('CODE_CHANGED_RESTART_REQUIRED')
 hashes={}
 for path_key,sha_key in(('source_path','source_sha256'),('mapped_edges_path','mapped_edges_sha256')):
  hashes[path_key]=hashlib.sha256((RUNTIME/meta[path_key]).read_bytes()).hexdigest()
  if hashes[path_key]!=meta[sha_key]:raise ValueError('INPUT_CHANGED_RESTART_REQUIRED')
 hashes.update(code=code,manifest=hashlib.sha256(manifest_bytes).hexdigest(),scene_contract=hashlib.sha256((RUNTIME/'data/scenes'/req['scene_id']/'frozen_scene.json').read_bytes()).hexdigest(),face_population=hashlib.sha256((RUNTIME/'data/face_selection_lock.json').read_bytes()).hexdigest(),door_id=req['door_id'])
 return digest(hashes)
def execute(rep,warmup=False):
 phases.clear()
 run='Q8-JOINT-K2-'+args.temperature+'-'+('WARMUP'if warmup else'FORMAL')+f'-{rep:03d}';tick=time.perf_counter();candidate_rows=[];routes=[];prep_ms=0.;binding_ms=0.;solver_ms=0.;validation_ms=0.
 with MemorySample()as memory:
  for req in requests:
   t=time.perf_counter();version=input_binding(req);key=(req['door_id'],version);hit=key in prepared_cache
   if not hit:prepared_cache[key]=prepare(req,'FULL_FACE')[0]
   prepared=prepared_cache[key];prep_ms+=(time.perf_counter()-t)*1000
   assert prepared['data']['door']['building_id']=='way/161090899'
   assert'APPROACH_OUTSIDE'in prepared['data']['door']['eligible_purposes']
   t=time.perf_counter();g,a,b,end,bindings=bind_graph(prepared,req);binding_ms+=(time.perf_counter()-t)*1000;out=solve(prepared,g,a,b,end['xy'],'F1');solver_ms+=out['solver_ms'];validation_ms+=out['validation_ms']
   candidate_rows.append({'door_id':req['door_id'],'role':end['role'],'purpose':req['purpose'],'status':out['status'],'cost_m':out.get('cost_m'),'length_m':out.get('route_length_m'),'graph_sha256':prepared['graph_sha'],'prepared_input_version_key':version,'source_and_code_bindings_rechecked':True,'nodes':len(g),'arcs':g.number_of_edges(),'preprocessing_cache_hit':hit,'solver':out['solver'],'validation':out.get('validation')});routes.append(out);del g
  t=time.perf_counter();eligible=[i for i,c in enumerate(candidate_rows)if c['status']=='PASS'];ranking=sorted(eligible,key=lambda i:(candidate_rows[i]['cost_m'],candidate_rows[i]['door_id']));rank_ms=(time.perf_counter()-t)*1000;winner=ranking[0]if ranking else None
 elapsed=(time.perf_counter()-tick)*1000;out=routes[winner]if winner is not None else{'status':'FAIL'if any(c['status']=='FAIL'for c in candidate_rows)else'NO_PATH','failure':'NO_VALID_CANDIDATE_ROUTE'}
 row=base_row(IDS['q8'],run,'sh-huangpu-01',requests[winner]['door_id']if winner is not None else'','F1');complete_row(row,out,elapsed);row.update(building_id='way/161090899',query_type='MULTI_ENTRANCE_K2_SEQUENTIAL_COST_SELECTION_ADAPTER',scale='SMALL_FROZEN_MUSEUM_TWO_DOORS',mode='FULL_FACE',temperature=args.temperature,repeat=rep,warmup=warmup,candidate_count=2,graph_nodes=max(c['nodes']for c in candidate_rows),graph_arcs=max(c['arcs']for c in candidate_rows),read_ms=phases.get('read_ms',0.),index_ms=phases.get('index_ms',0.),phase_timing_scope='Path read methods and STRtree constructors only; nested; gzip/internal I/O not separately isolated',graph_preprocessing_ms=prep_ms,binding_and_graph_compose_ms=binding_ms,solver_ms=solver_ms,validation_ms=validation_ms,candidate_ranking_ms=rank_ms,topk_ms=None,end_to_end_worker_ms=elapsed,sampled_peak_rss_bytes=memory.peak,route_answer_cache=False,solver_invoked=any(c['solver']['invoked']for c in candidate_rows),solver_call_count=sum(c['solver']['invoked']for c in candidate_rows),preprocessing_cache_hit=all(c['preprocessing_cache_hit']for c in candidate_rows),input_version=digest([c['graph_sha256']for c in candidate_rows]),unweighted_graph_sha256=digest([c['graph_sha256']for c in candidate_rows]),output_file=f'outputs/{run}.json',result={'adapter_added_this_round':True,'original_public_APP_joint_selector':False,'candidate_results':candidate_rows,'ranking_indices':ranking,'shared_start_id':requests[0]['start_id'],'purpose':'APPROACH_OUTSIDE','exit_not_used_as_inbound':True,'cache_scope':'Two separately keyed original door preprocessing objects held by experiment adapter; no route cache','not_global_multi_target_shortest_path_algorithm':True})
 write(D/row['output_file'],{'row':row,'candidate_results':candidate_rows,'routes':[o.get('route')for o in routes]});append(IDS['q8'],row);print(json.dumps({'event':'JOINT_RESULT','row':row},ensure_ascii=False),flush=True);gc.collect()
if args.temperature=='COLD_PROCESS':execute(args.repeat)
else:
 for i in range(3):execute(i,True)
 for i in range(10):execute(i,False)
