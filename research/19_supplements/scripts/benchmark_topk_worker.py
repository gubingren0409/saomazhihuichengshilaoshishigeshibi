"""Explicit supplemental Top-3 adapter, NOT an existing feature of the frozen APP."""
from experiment_core import *
from phase_timers import install_phase_timers
phases=install_phase_timers()
import argparse,itertools,gc
ap=argparse.ArgumentParser();ap.add_argument('--temperature',required=True);ap.add_argument('--repeat',type=int,default=0);args=ap.parse_args();D=ROOT/IDS['q8']
req=next(r for r in fixed_requests()if r['scene_id']=='sh-library');req['method']='F1'
def execute(rep,warmup=False):
 phases.clear()
 run_id='Q8-TOP3-A2-PHASED-ADAPTER-'+args.temperature+'-'+('WARMUP'if warmup else'FORMAL')+f'-{rep:03d}';t0=time.perf_counter()
 with MemorySample()as memory:
  t=time.perf_counter();prepared,hit,_=prepare(req,'FULL_FACE');prep=(time.perf_counter()-t)*1000
  g,a,b,end,bindings=bind_graph(prepared,req)
  def weight(u,v,data):return P._option_key(P._winning_option(data,2),2)[0]
  t=time.perf_counter();paths=[]
  try:
   generator=nx.shortest_simple_paths(g,a,b,weight=weight)
   for node_path in itertools.islice(generator,3):
    segments=[]
    for u,v in zip(node_path,node_path[1:]):
     for s in P._winning_option(g[u][v],2):segments.append({**s,'u':u,'v':v,'xy':[list(x)for x in s['xy']],'cost_m':s['length_m']*(2 if s['layer']in('inferred','unknown','assumed')else 1)})
    paths.append({'segments':segments,'node_sequence':node_path,'length_m':sum(s['length_m']for s in segments),'cost_m':sum(s['cost_m']for s in segments),'assumption_m':sum(s['length_m']for s in segments if s['layer']in('inferred','unknown','assumed'))})
  except nx.NetworkXNoPath:pass
  topk_ms=(time.perf_counter()-t)*1000;t=time.perf_counter()
  for path in paths:path['validation']=validate(prepared,{'segments':path['segments']},g.nodes[a]['xy'],end['xy'])
  valid=all(p['validation']['passed']for p in paths);checks_ms=(time.perf_counter()-t)*1000
 elapsed=(time.perf_counter()-t0)*1000;first=paths[0]if paths else None
 row=base_row(IDS['q8'],run_id,req['scene_id'],req['door_id'],'F1','PASS'if len(paths)==3 and valid else'FAIL'if not valid else'NO_PATH'if not paths else'INCONCLUSIVE')
 row.update(building_id=prepared['data']['door']['building_id'],read_ms=phases.get('read_ms',0.),index_ms=phases.get('index_ms',0.),phase_timing_scope='Path read methods and STRtree constructors only; nested; gzip/internal I/O not separately isolated',query_type='TOP3_EXPERIMENTAL_ADAPTER',mode='FULL_FACE',temperature=args.temperature,repeat=rep,warmup=warmup,scale='SMALL_FROZEN_LIBRARY_ONLY',candidate_count=1,graph_nodes=len(g),graph_arcs=g.number_of_edges(),topk_count=len(paths),topk_ms=topk_ms,solver_ms=None,validation_ms=checks_ms,graph_preprocessing_ms=prep,end_to_end_worker_ms=elapsed,runtime_ms=elapsed,sampled_peak_rss_bytes=memory.peak,preprocessing_cache_hit=hit,route_answer_cache=False,solver_invoked=True,source_edge_count=sum(s['layer']=='native'for s in first['segments'])if first else None,derived_edge_count=sum(s['layer']=='derived'for s in first['segments'])if first else None,assumption_edge_count=sum(s['layer']in('inferred','unknown','assumed')for s in first['segments'])if first else None,route_length_m=first['length_m']if first else None,assumption_length_m=first['assumption_m']if first else None,unweighted_graph_sha256=prepared['graph_sha'],input_version=prepared['graph_sha'],output_file=f'outputs/{run_id}.json',result={'adapter_added_this_round':True,'frozen_APP_top3_support':False,'algorithm':'networkx shortest_simple_paths (Yen on frozen weighted DiGraph)','distinctness':'Distinct node sequences, NOT distinct real approach corridors','single_path_internal_invocations':'NOT_INSTRUMENTED; do not count generator as 3 Dijkstra calls','all_routes_constraint_checked':valid,'top3_lengths_m':[p['length_m']for p in paths]})
 write(D/row['output_file'],{'row':row,'routes':paths,'bindings':bindings});append(IDS['q8'],row);print(json.dumps({'event':'TOPK_RESULT','row':row},ensure_ascii=False),flush=True);del g;gc.collect()
if args.temperature=='COLD_PROCESS':execute(args.repeat)
else:
 for i in range(3):execute(i,True)
 for i in range(30):execute(i,False)
