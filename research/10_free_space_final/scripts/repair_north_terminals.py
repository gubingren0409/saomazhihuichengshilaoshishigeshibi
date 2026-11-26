"""Route-only correctness repair; rehydrate existing surfaces/graphs, zero classifications."""
import json,gzip,sys,shutil,time
from pathlib import Path
from hashlib import sha256
import networkx as nx
from shapely.geometry import shape,Point
from shapely.strtree import STRtree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.region import NATIVE,INFERRED,union,digest
from src.region_routing import RegionGraph,native_graph
from src.predict_free import unpack_cache
from src.free_routing import reweight,queries_on_graph,build_graph,graph_record
ROOT=Path(__file__).resolve().parents[1]
READS=[]
def read(p):
    b=p.read_bytes()
    role=('ROUTE_ONLY_RESUME_PREVIOUS_PREDICTION_WITH_OLD_ROUTES_UNUSED_BY_NEW_ROUTER' if 'predictions' in p.parts else
          'ORIGINAL_FIXED_QUERY_AFTER_PREEXISTING_SURFACE_FREEZE' if 'queries' in p.parts else
          'ORIGINAL_ROUTE_ONLY_FULL_GRAPH' if p.name=='north_route_graph.json' else 'FROZEN_ROUTE_RESUME_INPUT')
    READS.append(dict(sequence=len(READS)+1,path=p.relative_to(ROOT).as_posix(),sha256=sha256(b).hexdigest(),role=role,event='ACTUAL_READ_BYTES'))
    return json.loads(b)
def sha(p):return sha256(p.read_bytes()).hexdigest()
def main():
    start=time.perf_counter();ident='NORTH_160';out=ROOT/'data/predictions'/ident
    saved=ROOT/'runs/superseded/NORTH_R0_terminal_defect'
    first=not saved.exists()
    if first:
        saved.mkdir(parents=True);shutil.copytree(out,saved/'predictions');shutil.copyfile(ROOT/'runs/executions/NORTH_160.json',saved/'original_execution_receipt.json')
    else:
        count=len(list((ROOT/'runs/superseded').glob('NORTH_R*_route_resume')))
        intermediate=ROOT/'runs/superseded'/f'NORTH_R{count+1}_route_resume';assert not intermediate.exists();intermediate.mkdir()
        shutil.copytree(out,intermediate/'predictions');shutil.copyfile(ROOT/'runs/executions/NORTH_160.json',intermediate/'receipt.json')
    # Count the original two surfaces exactly once in the original budget ledger.
    receipt=saved/'executions/NORTH_160.json'
    if first:receipt.parent.mkdir();shutil.copyfile(ROOT/'runs/executions/NORTH_160.json',receipt)
    cfg=read(ROOT/'config/frozen_region.json');cfg.update(inference_cost_multiplier=1,unknown_penalty_per_m=1,unknown_fixed_penalty_m=0)
    obs=read(ROOT/'data/e5/observed/NORTH_160.json');source=read(ROOT/'data/e5/north_route_graph.json')
    base=native_graph(source);visible=native_graph(obs)
    common=read(ROOT/'data/constraints/NORTH_160.json');queries=read(ROOT/'data/e5/queries/NORTH.json')['queries']
    for q in queries:
        for field in ('source','target'):
            if q[field]['id']==obs['registered_entrance']['id']:q[field].update(role='REGISTERED_EXIT',tags=obs['registered_entrance']['tags'])
    results=[]
    for arm in ('M1-C','F0'):
        old=read(saved/'predictions'/(arm+'.json'))
        with gzip.open(ROOT/old['graph']['graph_path'],'rt',encoding='utf8') as f:record=json.load(f)
        READS.append(dict(sequence=len(READS)+1,path=old['graph']['graph_path'],sha256=sha(ROOT/old['graph']['graph_path']),role='FROZEN_UNWEIGHTED_REGION_GRAPH',event='ACTUAL_GZIP_JSON_READ'))
        # Exact checked-native graph from the frozen run: do not silently restore rejections.
        for rejected in record['native_rejected']:
            for graph in (base,visible):
                if graph.has_edge(rejected['u'],rejected['v']):graph.remove_edge(rejected['u'],rejected['v'])
        s=unpack_cache(old['surface'],obs,cfg)
        # Rebuild only adjacency from the already-frozen geometry. This preserves
        # the production insertion order for equal-cost Dijkstra ties, unlike
        # loading the sorted interchange edge list. No cell is reclassified.
        rg=build_graph(s,visible,cfg,common,arm);g=rg.internal
        assert digest(graph_record(g))==old['graph']['graph_sha256'],'Frozen graph changed during route-only repair'
        names=['M1-C'] if arm=='M1-C' else ['F0','F1','F1-L1','F1-L1p5','F1-L3','F1-L5']
        for name in names:
            p=read(saved/'predictions'/(name+'.json'));weight=p['lambda_value'];reweight(g,weight)
            routes,terminals=queries_on_graph(base,rg,queries,cfg,common,arm,weight,visible_source=visible)
            canonical=[dict(query_id=r['query_id'],id=r['id'],attach=r['attach'],xy=r['xy'],segments=[{k:v for k,v in s.items() if k!='cost_m'} for s in r['segments']]) for r in terminals]
            p['routes']=routes;p['graph']['terminals']=canonical;p['graph']['terminal_graph_sha256']=digest(canonical)
            p['graph']['terminal_authorization']=[{k:v for k,v in r.items() if k!='segments'} for r in terminals]
            p['routing_repair']={'id':'VISIBLE_OBSERVED_QUERY_TERMINALS_V1','parent_prediction_sha256':sha(saved/'predictions'/(name+'.json')),'surface_rebuilt':False,'region_graph_changed':False,'query_changed':False,'new_region_builds':0}
            p['read_log_role']='INHERITED_CLASSIFICATION_AND_FIRST_ROUTING_LOG_NOT_THIS_RESUME_EXECUTION'
            p['route_only_read_log']=list(READS)
            p['route_only_isolation']='POST_FREEZE_RESUME_WITH_PREVIOUS_PREDICTION_METADATA; OLD_ROUTES_NOT_USED_FOR_NEW_CANDIDATES_OR_ROUTING; NOT_AN_OBSERVED_ONLY_CLASSIFIER_RUN'
            p['code_sha256']=sha256(''.join(sha(x) for x in sorted((ROOT/'src').glob('*.py'))).encode()).hexdigest()
            path=out/(name+'.json');path.write_text(json.dumps(p,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf8')
            results.append(dict(method=name,old_reached=sum(v['reached'] for v in old['routes'].values()),new_reached=sum(v['reached'] for v in routes.values()),surface_sha256=s.sha256,graph_sha256=p['graph']['graph_sha256'],prediction_sha256=sha(path)))
    rec={'input_id':ident,'panel':'NORTH','status':'ROUTE_ONLY_REPAIR_COMPLETED','region_builds':0,'wall_s':time.perf_counter()-start,'runs':results,
        'parent_region_receipt':receipt.relative_to(ROOT).as_posix(),'surface_reclassification':False,'actual_resume_read_log':READS,'algorithm_change':'Authorized exact visible-source query binding after freeze, same old tolerance and whole segment checks; no endpoint or source identity changes'}
    (ROOT/'runs/executions/NORTH_160.json').write_text(json.dumps(rec,indent=2),encoding='utf8')
    (ROOT/'audits/north_terminal_repair.json').write_text(json.dumps(rec,indent=2),encoding='utf8');print(json.dumps(rec))
if __name__=='__main__':main()
