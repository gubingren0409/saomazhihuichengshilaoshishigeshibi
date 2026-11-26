"""One actual solver call; unique output, no saved route answer lookup."""
from experiment_core import *
import argparse,uuid
ap=argparse.ArgumentParser();ap.add_argument('--case',choices=['south','north','library'],default='library');ap.add_argument('--method',choices=['F0','F1'],default='F1');ap.add_argument('--mode',choices=['FULL_FACE','EDGE_BAND'],default='FULL_FACE');ap.add_argument('--medium',action='store_true');args=ap.parse_args()
if args.medium:
 assert args.case=='library','Merged contract retains library target identity'
 from medium_adapter import activate_medium
 activate_medium()
req=fixed_requests()[['south','north','library'].index(args.case)];req['method']=args.method;run='REPLAY-'+uuid.uuid4().hex;folder=ROOT/'replay_runs'/run
tick=time.perf_counter();prepared,hit,_=prepare(req,args.mode);g,a,b,end,bindings=bind_graph(prepared,req);out=solve(prepared,g,a,b,end['xy'],req['method']);row=base_row('SUPPLEMENTARY_CLEAN_REPLAY',run,req['scene_id'],req['door_id'],req['method']);complete_row(row,out,(time.perf_counter()-tick)*1000);row.update(building_id=prepared['data']['door']['building_id'],input_version=prepared['graph_sha'],route_answer_cache=False,preprocessing_cache_hit=hit,source_request=req,mode=args.mode,medium=args.medium,output_file=str(folder/'result.json'))
write(folder/'result.json',{'row':row,'route':out.get('route'),'validation':out.get('validation'),'bindings':bindings});print(json.dumps(row,ensure_ascii=False))
if row['status']!='PASS':raise SystemExit(2)
