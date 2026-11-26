"""Actual isolated masked regression; historical route files never enter workers.

Use --baseline for preparation/comparison. Worker inputs are observed, independent
negative guards, frozen configuration; queries open only after surface freeze.
"""
from pathlib import Path
import argparse, copy, csv, gzip, hashlib, json, os, re, shutil, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def version():return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src').glob('*.py'))}

def prepare_guards(baseline,ledger_path):
    from shapely.geometry import Point,shape
    from src.scene_data import export_negative_access_areas
    rows=[r for r in read(baseline/'data/task_manifest.json')['instances']if r['panel']=='MAIN']
    ledgers={(r['parent_task_id'],r['masking_mode']):r for r in [json.loads(s)for s in ledger_path.read_text(encoding='utf-8').splitlines()]}
    audits=[]
    for row in rows:
        ident=row['id'];obs=read(baseline/row['observed']);ledger=ledgers[row['parent_task_id'],row['masking_mode']]
        forbidden=set(ledger.get('hidden_relation_member_ids',[]))|set(ledger.get('removed_context_source_ids',[]))
        for segment in ledger.get('historical_hidden_segments',[]):
            m=re.match(r'((?:node|way|relation)/\d+)',segment)
            if m:forbidden.add(m.group(1))
        if row['masking_mode']=='H':forbidden.update(ledger.get('historical_hidden_way_ids',[]))
        window=Point(obs['domain']['anchor_xy']).buffer(row['context_radius_m'],quad_segs=32)
        areas,excluded=export_negative_access_areas(row['group'],window,forbidden)
        original=baseline/'data/common_guards_v2'/f'{ident}.json';guard=read(original)
        if areas:
            guard.update(guard_version='BENCHMARK_UNIFIED_SOURCE_NEGATIVE_GUARDS_V1',parent_guard_sha256=sha(original),access_areas=areas,
                         access_area_export_role='SOURCE_NEGATIVE_ONLY;NO_HIDDEN_POSITIVE;NO_NODE_OR_MEMBER_ARRAYS')
        target=ROOT/'data/benchmark_guards'/f'{ident}.json';write(target,guard)
        allowed={'source_id','geometry','tags','source_clip_sha256','geometry_role','source_node_ring_closed','explicit_area_tag','source_tag_area_basis'}
        assert all(set(a)==allowed and a['source_id'] not in forbidden for a in areas)
        domain=Point(obs['domain']['anchor_xy']).buffer(30,quad_segs=32)
        audits.append({'input_id':ident,'namespace':'BENCHMARK_REGRESSION','guard_sha256':sha(target),'source_clip_sha256':row['source_clip_sha256'],
                       'observed_sha256':sha(baseline/row['observed']),'ledger_sha256':sha(ledger_path),'forbidden_source_ids':sorted(forbidden),
                       'negative_areas':[{k:a[k]for k in ('source_id','tags','geometry_role')}|{'domain_intersection_m2':shape(a['geometry']).intersection(domain).area}for a in areas],
                       'excluded_whole_objects':excluded,'positive_geometry_added':False,'node_member_arrays_added':False,'reference_read':False,
                       'fixed_selection_window_m':row['context_radius_m'],'export_code_sha256':sha(ROOT/'src/scene_data.py')})
    write(ROOT/'AUDIT/regression_guard_export.json',{'status':'NEGATIVE_ONLY_EXPORT_COMPLETE','count':len(audits),'rows':audits})
    print('UNIFIED_NEGATIVE_GUARDS',len(audits),flush=True)

class Guard:
    def __init__(self,work):self.work=work.resolve();self.phase='BEFORE_FREEZE';self.log=[]
    def event(self,event,args):
        if event!='open' or not isinstance(args[0],(str,bytes,os.PathLike)):return
        p=Path(os.fsdecode(args[0]))
        if p.suffix.lower() in ('.py','.pyc','.pyd','.dll') and p.is_absolute():return
        p=p.resolve();writing=bool(args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_APPEND|os.O_TRUNC))
        if p.parent!=self.work:raise PermissionError('BENCHMARK_OUTSIDE_WORKER_INPUT_DENIED:'+str(p))
        if writing:
            if p.name in {'freeze.json','result.json','graphs.json.gz','surfaces.json.gz'}:return
            raise PermissionError('BENCHMARK_OUTPUT_ROLE_DENIED')
        if p.name not in {'observed.json','guards.json','config.json','methods.json','query.json','version.json'}:raise PermissionError('BENCHMARK_INPUT_ROLE_DENIED')
        if p.name=='query.json' and self.phase!='AFTER_FREEZE':raise PermissionError('QUERY_BEFORE_FREEZE_DENIED')
        self.log.append({'file':p.name,'phase':self.phase,'event':'ACTUAL_OPEN'})
    def load(self,name):
        p=self.work/name;b=p.read_bytes();self.log[-1]['sha256']=hashlib.sha256(b).hexdigest();return json.loads(b)

def worker(work):
    import networkx as nx
    from src.region import build_surface,digest
    from src.context_policy import enhance
    from src.common_constraints import build_contract
    from src.free_surface import build_free_surface
    from src.free_routing import checked_native,build_graph,reweight,queries_on_graph,graph_record
    from shapely.geometry import mapping
    t=time.perf_counter();guard=Guard(work);sys.addaudithook(guard.event)
    obs=guard.load('observed.json');negative=guard.load('guards.json');cfg=guard.load('config.json');methods=guard.load('methods.json');code=guard.load('version.json')
    m0=build_surface(obs,cfg);m1,features=enhance(m0,obs,cfg,methods['M1'])
    common=build_contract(obs,negative,cfg,domain=mapping(m1.domain))
    surfaces={'M1-C':build_free_surface(m1,common,default=False),'F0':build_free_surface(m1,common,default=True)}
    freeze={'common_sha256':digest(common),'surface_sha256':{k:v.sha256 for k,v in surfaces.items()}}
    write(work/'freeze.json',freeze);guard.phase='AFTER_FREEZE'
    queries=guard.load('query.json')['queries']
    for q in queries:
        for side in ('source','target'):
            end=q[side];door=obs.get('registered_entrance')
            if door and end['id']==door['id']:end.update(role='REGISTERED_EXIT' if door['tags'].get('entrance')=='exit' else 'REGISTERED_DOOR',tags=door['tags'])
    cfg={**cfg,'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
    base,rejected=checked_native(obs,common);reweight(base,1)
    outputs={};graphs={};packed={}
    for arm,surface in surfaces.items():
        rg=build_graph(surface,base,cfg,common,arm);canonical=graph_record(rg.internal);graphsha=digest(canonical)
        graphs[arm]={**canonical,'interfaces':rg.interfaces,'sha256':graphsha,'native_rejected':rejected}
        packed[arm]={'domain':mapping(surface.domain),'sha256':surface.sha256,'area_m2':surface.area_m2,'cells':[{k:v for k,v in c.items() if k!='g'} for c in surface.cells]}
        for name,weight in ([('M1-C',1)] if arm=='M1-C' else [('F0',1),('F1',2)]):
            reweight(rg.internal,weight)
            routes,terminals=queries_on_graph(base,rg,queries,cfg,common,arm,weight,visible_source=base)
            outputs[name]={'routes':routes,'terminals':terminals,'surface_sha256':surface.sha256,'graph_sha256':graphsha,
                           'surface_area_m2':surface.area_m2,'stats':rg.stats,'lambda':weight,'common_sha256':digest(common)}
    for filename,value in [('graphs.json.gz',graphs),('surfaces.json.gz',packed)]:
        with gzip.open(work/filename,'wt',encoding='utf-8') as f:json.dump(value,f,separators=(',',':'),ensure_ascii=False)
    evaluations=len(queries)*3
    searches=sum(r['status']!='UNAVAILABLE_ENDPOINT'for m in outputs.values()for r in m['routes'].values())
    result={'namespace':'BENCHMARK_REGRESSION','query_answer_cache':False,'classification':'FRESH_OBSERVED_ONLY_COLD_BUILD',
            'actual_solver_calls':evaluations,'legacy_counter_meaning':'ROUTING_FUNCTION_EVALUATIONS_NOT_NX_SEARCHES',
            'query_evaluation_count':evaluations,'actual_graph_search_count':searches,
            'methods':outputs,'common_constraints':common,'read_log':guard.log,
            'freeze':freeze,'code_bindings':code,'elapsed_s':time.perf_counter()-t,'external_requests':0,'reference_reads':0}
    write(work/'result.json',result)

def main(args):
    baseline=args.baseline.resolve();manifest=read(baseline/'data/task_manifest.json')
    rows=[r for r in manifest['instances'] if r['panel']=='MAIN' and (not args.ids or r['id'] in args.ids)]
    suite=ROOT/'runs/benchmark'/args.run_name;suite.mkdir(parents=True,exist_ok=True)
    oldrows=[]
    for row in rows:
        ident=row['id'];work=suite/ident
        if (work/'result.json').exists():print('RESUME',ident,flush=True);continue
        work.mkdir(exist_ok=True)
        guards=baseline/row.get('guards',f'data/common_guards_v3/{ident}.json')
        if not guards.exists():guards=baseline/'data/common_guards_v2'/f'{ident}.json'
        override=ROOT/'data/benchmark_guards'/f'{ident}.json'
        if args.unified_guards:
            if not override.exists():raise FileNotFoundError('Unified guards unavailable '+str(override))
            guards=override
        inputs={'observed.json':baseline/row['observed'],'query.json':baseline/row['query'],
                'guards.json':guards,'config.json':ROOT/'config/frozen_region.json','methods.json':ROOT/'config/historical_methods.json'}
        for name,p in inputs.items():
            field={'observed.json':'observed','query.json':'query'}.get(name)
            if field and sha(p)!=row[field+'_sha256']:raise ValueError('FROZEN_INPUT_HASH_MISMATCH '+str(p))
            shutil.copyfile(p,work/name)
        write(work/'version.json',version())
        write(work/'input_bindings.json',{'namespace':'BENCHMARK_REGRESSION','row':row,'files':{n:sha(p) for n,p in inputs.items()},'historical_predictions_not_worker_input':True})
        command=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--worker',str(work)]
        t=time.perf_counter();done=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',cwd=work,timeout=600)
        write(work/'execution.json',{'command':[Path(sys.executable).name,'-X','utf8','-B','scripts/run_regression.py','--worker',f'runs/benchmark/{args.run_name}/{ident}'],
                                   'runner_sha256':sha(Path(__file__)),
                                   'returncode':done.returncode,'stdout':done.stdout,'stderr':done.stderr,'wall_s':time.perf_counter()-t})
        if done.returncode:raise RuntimeError(done.stderr)
        print('COMPLETED',ident,round(time.perf_counter()-t,2),'s',flush=True)
    records=[];summary={}
    for row in rows:
        ident=row['id'];work=suite/ident
        if not (work/'result.json').exists():continue
        new=read(work/'result.json')
        for method,pred in new['methods'].items():
            historical=read(baseline/'data/predictions'/ident/f'{method}.json')
            for qid,r in pred['routes'].items():
                old=historical['routes'][qid]
                records.append({'input_id':ident,'parent_task_id':row['parent_task_id'],'query_id':qid,'label':row['label'],'method':method,
                                'old_status':old['status'],'old_reached':old['reached'],'old_length_m':old['length_m'],
                                'new_status':r['status'],'new_reached':r['reached'],'new_length_m':r['length_m'],
                                'delta_length_m':r['length_m']-old['length_m'] if r['reached'] and old['reached'] else None,
                                'graph_sha256':pred['graph_sha256'],'surface_sha256':pred['surface_sha256'],
                                'common_sha256':pred['common_sha256'],'actual_routing_evaluation':True,'actual_graph_search':r['status']!='UNAVAILABLE_ENDPOINT','route_answer_cache':False})
    for method in ('M1-C','F0','F1'):
        summary[method]={}
        for label in ('POSITIVE','NEGATIVE'):
            rr=[r for r in records if r['method']==method and r['label']==label]
            summary[method][label]={'queries':len(rr),'old_reached':sum(r['old_reached'] for r in rr),'new_reached':sum(r['new_reached'] for r in rr),
                'recovered':sum(not r['old_reached'] and r['new_reached'] for r in rr),'regressed':sum(r['old_reached'] and not r['new_reached'] for r in rr),
                'geometry_length_changed':sum(abs(r['delta_length_m'] or 0)>1e-6 for r in rr)}
    if records:
        with (suite/'query_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    write(suite/'summary.json',{'namespace':'BENCHMARK_REGRESSION','parents':len(rows),'query_rows':len(records),
                              'summary':summary,'actual_solver_calls':len(records),'legacy_counter_meaning':'ROUTING_FUNCTION_EVALUATIONS_NOT_NX_SEARCHES',
                              'query_evaluation_count':len(records),'actual_graph_search_count':sum(r['actual_graph_search']for r in records),
                              'old_predictions':'COMPARISON_ONLY_AFTER_NEW_SOLVING'})
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--baseline',type=Path);p.add_argument('--ids',nargs='+')
    p.add_argument('--run-name',default='R1');p.add_argument('--unified-guards',action='store_true');p.add_argument('--prepare-guards',type=Path);args=p.parse_args()
    if args.worker:worker(args.worker.resolve())
    else:
        if not args.baseline:p.error('--baseline required')
        if args.prepare_guards:prepare_guards(args.baseline.resolve(),args.prepare_guards.resolve())
        else:main(args)
