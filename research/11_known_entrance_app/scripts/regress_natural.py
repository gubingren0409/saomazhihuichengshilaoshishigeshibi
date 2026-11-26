"""Historical NORTH eight-query regression, separate from new APP requests.

The stored observed-only M0/M1 classifier is a checked preprocessing cache;
neither historical routes nor reference files are provided to the solver.
"""
from pathlib import Path
import argparse, gzip, hashlib, json, os, shutil, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_regression import read,write,sha,version,Guard

class NaturalGuard(Guard):
    def event(self,event,args):
        if event=='open'and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve()
            writing=bool(args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_APPEND|os.O_TRUNC))
            if p.parent==self.work and not writing and p.name in {'classifier_cache.json','route_graph.json'}:
                if p.name=='route_graph.json'and self.phase!='AFTER_FREEZE':raise PermissionError('NATURAL_ROUTE_GRAPH_BEFORE_FREEZE')
                self.log.append({'file':p.name,'phase':self.phase,'event':'ACTUAL_OPEN'});return
        return super().event(event,args)

def worker(work):
    import networkx as nx
    from shapely.geometry import mapping,shape
    from src.region import Surface,STATES,union,context_layers,digest
    from src.free_surface import build_free_surface
    from src.common_constraints import build_contract
    from src.free_routing import checked_native,build_graph,queries_on_graph,reweight,graph_record
    t=time.perf_counter();g=NaturalGuard(work);sys.addaudithook(g.event)
    obs=g.load('observed.json');guards=g.load('guards.json');cfg=g.load('config.json');code=g.load('version.json');methods=g.load('methods.json');cache=g.load('classifier_cache.json')
    assert cache['observed_sha256']==next(r['sha256']for r in g.log if r['file']=='observed.json')
    expected={
        'src/region.py':code['src/region.py'],'src/context_policy.py':code['src/context_policy.py'],
        'config/frozen_region.json':next(r['sha256']for r in g.log if r['file']=='config.json'),
        'config/methods.json':next(r['sha256']for r in g.log if r['file']=='methods.json')}
    assert expected==cache['classifier_bindings'],'classifier binding differs'
    p=cache['M1'];assert digest(p['cells'])==p['sha256']
    cells=[dict(c,g=shape(c['geometry']),ij=tuple(c['ij']))for c in p['cells']];domain=shape(p['domain'])
    m1=Surface(domain,cells,{s:union(c['g']for c in cells if c['walkability_state']==s)for s in STATES},context_layers(obs,domain,cfg),p['sha256'],p['area_m2'],p['statistics'],p['grid_m'])
    common=build_contract(obs,guards,cfg,domain=mapping(domain))
    surfaces={'M1-C':build_free_surface(m1,common,default=False),'F0':build_free_surface(m1,common,default=True)}
    freeze={'surfaces':{k:v.sha256 for k,v in surfaces.items()},'common_sha256':digest(common)};write(work/'freeze.json',freeze);g.phase='AFTER_FREEZE'
    queries=g.load('query.json')['queries'];route_graph=g.load('route_graph.json')
    for q in queries:
        for side in ('source','target'):
            end=q[side];door=obs.get('registered_entrance')
            if door and end['id']==door['id']:end.update(role='REGISTERED_EXIT'if door['tags'].get('entrance')=='exit'else'REGISTERED_DOOR',tags=door['tags'])
    cfg={**cfg,'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
    base,rejected=checked_native(route_graph,common);observed,obs_rejected=checked_native(obs,common);reweight(base,1)
    outcomes={}
    for arm,surface in surfaces.items():
        rg=build_graph(surface,observed,cfg,common,arm);graphsha=digest(graph_record(rg.internal))
        for name,weight in ([('M1-C',1)]if arm=='M1-C'else[('F0',1),('F1',2)]):
            reweight(rg.internal,weight);routes,terminals=queries_on_graph(base,rg,queries,cfg,common,arm,weight,visible_source=observed)
            outcomes[name]={'routes':routes,'terminals':terminals,'surface_sha256':surface.sha256,'graph_sha256':graphsha,'common_sha256':digest(common),'stats':rg.stats}
    write(work/'result.json',{'namespace':'HISTORICAL_NATURAL_REGRESSION','actual_solver_calls':len(queries)*3,'route_answer_cache':False,
                            'classifier_origin':'HASH_BOUND_SAME_OBSERVED_PREPROCESSING_CACHE','methods':outcomes,'read_log':g.log,'code_bindings':code,
                            'elapsed_s':time.perf_counter()-t,'freeze':freeze,'native_rejected':rejected,'observed_rejected':obs_rejected})

def outer(baseline):
    from shapely.geometry import Point
    from src.scene_data import export_negative_access_areas
    rows=read(baseline/'data/task_manifest.json')['instances'];row=next(r for r in rows if r.get('natural'))
    work=ROOT/'runs/benchmark/NORTH_regression';work.mkdir(exist_ok=True,parents=True)
    if not(work/'result.json').exists():
        oldguard=baseline/'data/common_guards_v2'/f"{row['id']}.json";guard=read(oldguard)
        scene_id=Path(guard['source_clip']).name.replace('.osm.json','')
        obs=read(baseline/row['observed']);window=Point(obs['domain']['anchor_xy']).buffer(row['context_radius_m'],quad_segs=32)
        areas,excluded=export_negative_access_areas(scene_id,window)
        guard.update(access_areas=areas,guard_version='HISTORICAL_NATURAL_UNIFIED_SOURCE_NEGATIVE_V1')
        inputs={'observed.json':baseline/row['observed'],'query.json':baseline/row['query'],'route_graph.json':baseline/row['route_graph'],
                'classifier_cache.json':baseline/'data/classifier_cache'/f"{row['id']}.json",'config.json':ROOT/'config/frozen_region.json','methods.json':ROOT/'config/historical_methods.json'}
        for name,p in inputs.items():
            field={'observed.json':'observed','query.json':'query','route_graph.json':'route_graph'}.get(name)
            if field:assert sha(p)==row[field+'_sha256']
            shutil.copyfile(p,work/name)
        write(work/'guards.json',guard);write(work/'version.json',version())
        command=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--worker',str(work)]
        t=time.perf_counter();done=subprocess.run(command,cwd=work,capture_output=True,text=True,encoding='utf8',timeout=900)
        write(work/'execution.json',{'command':['python','-X','utf8','-B','scripts/regress_natural.py','--worker','runs/benchmark/NORTH_regression'],
                                   'returncode':done.returncode,'stdout':done.stdout,'stderr':done.stderr,'wall_s':time.perf_counter()-t})
        if done.returncode:raise RuntimeError(done.stderr)
    result=read(work/'result.json');comparison=[]
    for method,pred in result['methods'].items():
        old=read(baseline/'data/predictions'/row['id']/f'{method}.json')
        for qid,r in pred['routes'].items():
            o=old['routes'][qid]
            comparison.append({'method':method,'query_id':qid,'old_status':o['status'],'new_status':r['status'],'old_reached':o['reached'],'new_reached':r['reached'],
                               'old_length_m':o['length_m'],'new_length_m':r['length_m'],'old_layers':o['layer_lengths'],'new_layers':r['layer_lengths'],
                               'delta_length_m':r['length_m']-o['length_m']if r['reached']and o['reached']else None})
    write(work/'comparison.json',comparison)
    print(json.dumps({'queries':len(comparison),'reached_by_method':{m:sum(r['new_reached']for r in comparison if r['method']==m)for m in ('M1-C','F0','F1')},'changed_lengths':sum(abs(r['delta_length_m'] or 0)>1e-6 for r in comparison)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path);p.add_argument('--worker',type=Path);args=p.parse_args()
    if args.worker:worker(args.worker.resolve())
    else:outer(args.baseline.resolve())
