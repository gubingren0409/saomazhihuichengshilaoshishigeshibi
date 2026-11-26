from experiment_core import *
from medium_adapter import activate_medium
activate_medium()
import argparse,gc
parser=argparse.ArgumentParser();parser.add_argument('--mode',required=True);parser.add_argument('--method',required=True);parser.add_argument('--temperature',required=True);parser.add_argument('--repeat',type=int,default=0);args=parser.parse_args()
eid=IDS['q8'];req=next(r for r in fixed_requests()if r['scene_id']=='sh-library');req['method']=args.method
# Explicit current-core adapter for both modes; not a claim of HTTP-service SLA.
phases={}
# Timing-only delegating hooks: preserve inputs, return values and frozen files.
original_bytes=Path.read_bytes;original_text=Path.read_text
def timed_bytes(self,*a,**kw):
 t=time.perf_counter()
 try:return original_bytes(self,*a,**kw)
 finally:phases['read_ms']=phases.get('read_ms',0)+(time.perf_counter()-t)*1000
def timed_text(self,*a,**kw):
 t=time.perf_counter()
 try:return original_text(self,*a,**kw)
 finally:phases['read_ms']=phases.get('read_ms',0)+(time.perf_counter()-t)*1000
Path.read_bytes=timed_bytes;Path.read_text=timed_text
from shapely.strtree import STRtree
original_index_init=STRtree.__init__
def timed_index(self,*a,**kw):
 t=time.perf_counter()
 try:return original_index_init(self,*a,**kw)
 finally:phases['index_ms']=phases.get('index_ms',0)+(time.perf_counter()-t)*1000
STRtree.__init__=timed_index

def run(repeat,warmup=False):
 phases.clear();run_id=f'Q8-MEDIUM-{args.mode}-{args.method}-{args.temperature}-'+('WARMUP'if warmup else'FORMAL')+f'-{repeat:03d}'
 tick=time.perf_counter()
 with MemorySample()as mem:
  t=time.perf_counter();prepared,hit,_=prepare(req,args.mode);prep_ms=(time.perf_counter()-t)*1000
  t=time.perf_counter();g,a,b,end,bindings=bind_graph(prepared,req);bind_ms=(time.perf_counter()-t)*1000
  out=solve(prepared,g,a,b,end['xy'],args.method)
 elapsed=(time.perf_counter()-tick)*1000
 row=base_row(eid,run_id,req['scene_id'],req['door_id'],args.method);complete_row(row,out,elapsed)
 row.update(building_id=prepared['data']['door']['building_id'],mode=args.mode,temperature=args.temperature,repeat=repeat,warmup=warmup,scale='MEDIUM_TWO_OVERLAPPING_FROZEN_CROPS',candidate_count=1,query_type='SINGLE_SHORTEST_PATH',graph_nodes=len(g),graph_arcs=g.number_of_edges(),read_ms=phases.get('read_ms',0.),graph_preprocessing_ms=prep_ms,index_ms=phases.get('index_ms',0.),index_timing_reason='Delegating STRtree constructor timer; nested within preparation; instrumentation overhead not subtracted',binding_and_graph_compose_ms=bind_ms,solver_ms=out['solver_ms'],validation_ms=out['validation_ms'],candidate_ranking_ms=None,topk_ms=None,unsupported_phase_reason='Current frozen interface has no multi-entrance joint ranking or Top-k path enumeration',end_to_end_worker_ms=elapsed,sampled_peak_rss_bytes=mem.peak,preprocessing_cache_hit=hit,route_answer_cache=False,solver_invoked=out['solver']['invoked'],input_version=prepared['graph_sha'],unweighted_graph_sha256=prepared['graph_sha'],measure_scope='NEW_EXPERIMENT_CLI_CORE_ADAPTER; frozen prepare/bind/solver/whole-route-constraints; NOT HTTP latency',OS_disk_cache='UNCONTROLLED',phase_times_are_nested=True,output_file=f'outputs/{run_id}.json')
 write(ROOT/eid/row['output_file'],{'row':row,'route':out.get('route'),'validation':out.get('validation'),'bindings':bindings})
 append(eid,row);print(json.dumps({'event':'BENCHMARK_RESULT','row':row},ensure_ascii=False),flush=True)
 del g;gc.collect()

if args.temperature=='COLD_PROCESS':run(args.repeat)
else:
 for i in range(3):run(i,True)
 for i in range(30):run(i,False)
