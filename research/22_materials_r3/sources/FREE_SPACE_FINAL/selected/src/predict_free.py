"""Isolated worker. One region per policy, the identical F0 graph reweighted for F1."""
import argparse,gzip,json,os,sys
from pathlib import Path
from hashlib import sha256
from time import perf_counter
import networkx as nx
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.region import build_surface,digest,Surface,STATES,context_layers,union
from src.context_policy import enhance
from src.free_surface import build_free_surface
from src.free_routing import checked_native,build_graph,reweight,queries_on_graph,graph_record
from src.region_routing import empty,route
from src.common_constraints import build_contract
from shapely.geometry import mapping,shape

class Guard:
    def __init__(self):
        self.root=Path.cwd().resolve();self.phase='BEFORE_SURFACE';self.log=[]
        self.allowed={'observed.json':'OBSERVED','guards.json':'OBSERVED_COMMON_GUARDS','config.json':'CONFIG','historical_methods.json':'M1_FROZEN_CONFIG','classifier_surface_cache.json':'FROZEN_SAME_OBSERVED_CLASSIFIER_SURFACE','query.json':'QUERY','route_graph.json':'NATURAL_ROUTE_ONLY_GRAPH'}
    def event(self,event,args):
        if event!='open' or not isinstance(args[0],(str,bytes,os.PathLike)):return
        p=Path(os.fsdecode(args[0]))
        if p.suffix.lower() in ('.py','.pyc','.pyd','.dll') and p.is_absolute() and (p.is_relative_to(Path(sys.base_prefix)) or p.is_relative_to(Path(__file__).resolve().parent)):return
        p=p.resolve();write=bool(args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_APPEND|os.O_TRUNC))
        if p.parent!=self.root:raise PermissionError('OUTSIDE_WORKER_ALLOWLIST')
        if write:
            if p.name.endswith(('.prediction.json','.graph.json.gz')) or p.name in ('surface.freeze','constraints.json','execution.json','history.json'):return
            raise PermissionError('OUTPUT_ROLE_DENIED')
        if p.name not in self.allowed:raise PermissionError('INPUT_ROLE_DENIED')
        if p.name in ('query.json','route_graph.json') and self.phase!='AFTER_SURFACE':raise PermissionError('POST_FREEZE_INPUT_EARLY_READ_DENIED')
        self.log.append(dict(role=self.allowed[p.name],path=p.name,event='ACTUAL_FILE_OPEN',phase=self.phase))
    def read(self,name):
        b=(self.root/name).read_bytes();self.log[-1]['sha256']=sha256(b).hexdigest();return json.loads(b)
    def probe(self,name):
        try:(self.root/name).read_bytes()
        except PermissionError as e:self.log.append(dict(role='DENIED_PROBE',path=name,event='DENIED_OPEN',reason=str(e)))
        else:raise RuntimeError('Invalid read permitted')
    def freeze(self,records):
        put('surface.freeze',records);self.log.append(dict(role='SURFACE_FROZEN',event='ACTUAL_STAGE_WRITE',sha256=digest(records),surface_hashes=records));self.phase='AFTER_SURFACE'

def put(name,value):
    with open(name,'w',encoding='utf8',newline='\n') as f:json.dump(value,f,ensure_ascii=False,separators=(',',':'),allow_nan=False);f.write('\n')
def pack(surface):
    return dict(sha256=surface.sha256,domain=mapping(surface.domain),cells=[{k:v for k,v in c.items() if k!='g'} for c in surface.cells],area_m2=surface.area_m2,statistics=surface.statistics,grid_m=surface.step)
def unpack_cache(p,obs,cfg):
    if set(p)!={'sha256','domain','cells','area_m2','statistics','grid_m'} or digest(p['cells'])!=p['sha256']:raise ValueError('Invalid observed-only surface cache')
    cells=[dict(c,g=shape(c['geometry']),ij=tuple(c['ij'])) for c in p['cells']];domain=shape(p['domain'])
    return Surface(domain,cells,{s:union(c['g'] for c in cells if c['walkability_state']==s) for s in STATES},context_layers(obs,domain,cfg),p['sha256'],p['area_m2'],p['statistics'],p['grid_m'])
def run(args):
    t=perf_counter();g=Guard();sys.addaudithook(g.event)
    g.probe('reference.json');g.probe('query.json')
    cfg=g.read('config.json');methods=g.read('historical_methods.json');obs=g.read('observed.json');obs_sha=g.log[-1]['sha256'];guards=g.read('guards.json');guards_sha=g.log[-1]['sha256']
    if args.natural_cache or args.classifier_cache:
        if args.input_id not in ('NORTH_160','W7a6b5a10076_G_080') or (args.input_id=='NORTH_160')!=bool(args.natural):raise ValueError('Cache restricted to independently verified same-observed fixed cases')
        cached=g.read('classifier_surface_cache.json')
        if set(cached)!={'observed_sha256','classifier_bindings','M0','M1'} or cached['observed_sha256']!=obs_sha:raise ValueError('Cached classifier role or observation mismatch')
        expected={'src/region.py':sha256((Path(__file__).parent/'region.py').read_bytes()).hexdigest(),'src/context_policy.py':sha256((Path(__file__).parent/'context_policy.py').read_bytes()).hexdigest(),
                  'config/frozen_region.json':next(r['sha256'] for r in g.log if r.get('path')=='config.json'),
                  'config/methods.json':next(r['sha256'] for r in g.log if r.get('path')=='historical_methods.json')}
        if cached['classifier_bindings']!=expected:raise ValueError('Frozen classifier/config bindings differ')
        m0=unpack_cache(cached['M0'],obs,cfg);m1=unpack_cache(cached['M1'],obs,cfg)
        features={'mode':'EXPLICIT_FROZEN_OBSERVED_ONLY_M1_SURFACE_CACHE','changed_cells':0,'witnesses':{}}
        class_origin='REUSED_PREVIOUS_SAME_OBSERVED_CLASSIFIER_SURFACE_NO_CLASSIFIER_RERUN';builds=2
    else:
        m0=build_surface(obs,cfg)
        m1,features=enhance(m0,obs,cfg,methods['M1'])
        class_origin='CURRENT_OBSERVED_ONLY_CLASSIFIER_EXECUTION';builds=4
    common=build_contract(obs,guards,cfg,domain=mapping(m1.domain))
    put('constraints.json',common)
    mc=build_free_surface(m1,common,default=False)
    f0=build_free_surface(m1,common,default=True)
    g.freeze({'M1-HISTORICAL':m1.sha256,'M1-C':mc.sha256,'F0':f0.sha256,'F1':f0.sha256,'constraint_sha256':digest(common)})
    queries=g.read('query.json')['queries'];query_sha=g.log[-1]['sha256']
    routing=g.read('route_graph.json') if args.natural else obs
    base,rejected=checked_native(routing,common)
    interfaces,_=checked_native(obs,common) if args.natural else (base,rejected)
    for q in queries:
        for field in ('source','target'):
            end=q[field];door=obs.get('registered_entrance')
            if door and end['id']==door['id']:end.update(role='REGISTERED_EXIT' if door['tags'].get('entrance')=='exit' else 'REGISTERED_DOOR',tags=door['tags'])
    # Costs are pure geometry for M1-C/F0. F1 multiplies only conditional/unknown lengths.
    cfg={**cfg,'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
    reweight(base,1)
    base_routes={q['query_id']:empty('NO_REGION_GRAPH') if q.get('scope')=='LOCAL_REGION_ONLY' else route(base,q['source']['id'],q['target']['id']) for q in queries}
    execution=[]
    for arm,surface in [('M1-C',mc),('F0',f0)]:
        rg=build_graph(surface,interfaces,cfg,common,arm)
        unweighted=graph_record(rg.internal)
        graph_sha=digest(unweighted)
        # Native edges reference exact observed inputs; new graph edges are explicit in the archive.
        record={**unweighted,'graph_sha256':graph_sha,'interfaces':rg.interfaces,'native_input':{'observed_sha256':obs_sha,'route_graph_is_post_freeze':args.natural},'native_rejected':rejected}
        with gzip.open(arm+'.graph.json.gz','wt',encoding='utf8') as f:json.dump(record,f,separators=(',',':'))
        names=[('M1-C',1)] if arm=='M1-C' else [('F0',1),('F1',2)]
        if arm=='F0' and args.sensitivity:names.extend([('F1-L1',1),('F1-L1p5',1.5),('F1-L3',3),('F1-L5',5)])
        for name,weight in names:
            reweight(rg.internal,weight)
            routes,terminals=queries_on_graph(base,rg,queries,cfg,common,arm,weight,visible_source=interfaces)
            term_canonical=[dict(query_id=r['query_id'],id=r['id'],attach=r['attach'],xy=r['xy'],segments=[{k:v for k,v in s.items() if k!='cost_m'} for s in r['segments']]) for r in terminals]
            graphinfo=dict(rg.stats,interfaces=rg.interfaces,graph_sha256=graph_sha,unweighted_graph_sha256=graph_sha,
                           graph_path=f'data/graphs/{args.input_id}/{arm}.graph.json.gz',terminals=term_canonical,terminal_graph_sha256=digest(term_canonical),
                           observed_nodes=len(interfaces),observed_arcs=interfaces.number_of_edges(),routing_nodes=len(base),routing_arcs=base.number_of_edges(),
                           observed_components=nx.number_weakly_connected_components(interfaces),native_rejected_count=len(rejected))
            p=dict(input_id=args.input_id,method=name,lambda_value=weight,context_radius_m=args.radius,
                   observed_sha256=obs_sha,guards_sha256=guards_sha,query_sha256=query_sha,
                   constraint_sha256=digest(common),config_sha256=args.config_sha,code_sha256=args.code_sha,
                   read_log=[dict(row,sequence=k) for k,row in enumerate(g.log,1)],surface=pack(surface),
                   routes=routes,base_routes=base_routes,graph=graphinfo,features=features if arm=='M1-C' else {'admission':'DEFAULT_FREE_POLICY_V1','positive_evidence_gate':False},
                   historical_m1_surface_sha256=m1.sha256,historical_m1_area_m2=m1.area_m2,
                   elapsed_s=perf_counter()-t,peak_working_set_bytes=psutil.Process().memory_info().rss,
                   external_requests=0,isolation_scope='APPLICATION_OPEN_AUDIT_NOT_OS_SANDBOX',region_builds=builds,classifier_origin=class_origin)
            put(name+'.prediction.json',p)
            execution.append(dict(method=name,surface_sha256=surface.sha256,graph_sha256=graph_sha,reached=sum(r['reached'] for r in routes.values())))
    put('history.json',{'M0':pack(m0),'M1':pack(m1),'features':features,'classifier_origin':class_origin})
    put('execution.json',dict(input_id=args.input_id,elapsed_s=perf_counter()-t,region_builds=builds,runs=execution,classifier_origin=class_origin))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-id',required=True);p.add_argument('--radius',type=int,required=True);p.add_argument('--natural',action='store_true');p.add_argument('--natural-cache',action='store_true');p.add_argument('--classifier-cache',action='store_true');p.add_argument('--sensitivity',action='store_true');p.add_argument('--code-sha');p.add_argument('--config-sha');run(p.parse_args())
