"""Historical source-only south route; no free-space shortcuts or new APP sample."""
from pathlib import Path
import argparse,json,math,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.planner import _prepare,_weighted_route,put
from src.common_constraints import edge_conflicts
from shapely.geometry import LineString

def main(args):
    tick=time.perf_counter()
    # Historical regression fixture IDs identify a test, never permission rules.
    prepared,hit,seconds=_prepare('sh-huangpu-01','node/6897141353')
    graph=prepared['source'];start='node/476682043';door='node/6897141353'
    route,failure,solver=_weighted_route(graph,start,door,1)
    checks=[];prior=graph.nodes[start]['xy'];lengths={k:0 for k in ('native','derived','inferred','unknown')}
    if route:
        for n,s in enumerate(route['segments']):
            reasons=edge_conflicts(LineString(s['xy']),prepared['full_parsed'],native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
            gap=math.dist(prior,s['xy'][0]);prior=s['xy'][-1];lengths[s['layer']]+=s['length_m']
            checks.append({'segment':n,'source_id':s.get('source_id'),'gap_m':gap,'conflicts':reasons})
    result={'namespace':'HISTORICAL_SOURCE_ROUTE_REGRESSION','role':'SOUTH_OLD_QUERY_NOT_NEW_APP_ACCEPTANCE',
            'query':{'source':start,'target':door,'purpose':'APPROACH_OUTSIDE'},'route_answer_cache':False,'solver':solver,
            'status':'ROUTED'if route else'NO_PATH','route':route,'failure':failure,'layer_lengths_m':lengths,
            'length_m':sum(lengths.values())if route else None,'historical_length_m':1067.371390401112,
            'end_residual_m':math.dist(prior,prepared['data']['door']['xy'])if route else None,
            'checks':checks,'source':prepared['data']['source_info'],'code_sha256':prepared['code_sha'],'source_graph_only':True,'free_region_used':False,
            'elapsed_s':time.perf_counter()-tick}
    put(ROOT/'runs/benchmark'/args.run_name/'result.json',result)
    print(json.dumps({k:result[k]for k in ('status','length_m','historical_length_m','end_residual_m','elapsed_s')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-name',default='SOUTH_source_R1');main(p.parse_args())
