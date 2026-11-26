"""Replay historical routing from this run's pre-query recomputed M1 surface."""
import argparse,json,sys
from pathlib import Path
from hashlib import sha256
from shapely.geometry import shape
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.region import Surface,STATES,union,context_layers,digest
from src.region_routing import native_graph,region_graph,routed_queries
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads(p.read_text(encoding='utf8'))
def replay(row):
    obs=load(ROOT/row['observed']);cfg=load(ROOT/'config/frozen_region.json')
    history=load(ROOT/'data/calibration'/f"{row['id']}.json");p=history['M1']
    cells=[dict(c,g=shape(c['geometry']),ij=tuple(c['ij'])) for c in p['cells']]
    domain=shape(p['domain']);masks={s:union(c['g'] for c in cells if c['walkability_state']==s) for s in STATES}
    s=Surface(domain,cells,masks,context_layers(obs,domain,cfg),p['sha256'],p['area_m2'],p['statistics'],p['grid_m'])
    q=load(ROOT/row['query'])['queries']
    door=obs.get('registered_entrance')
    for query in q:
        for field in ('source','target'):
            if door and query[field]['id']==door['id']:query[field].update(role='REGISTERED_DOOR',tags=door['tags'])
    routing=load(ROOT/row['route_graph']) if row.get('natural') else obs
    base=native_graph(routing);interfaces=native_graph(obs) if row.get('natural') else base
    rg=region_graph(s,interfaces,cfg);routes=routed_queries(base,rg,q,cfg)
    oldpath=ROOT/'frozen_context/data/predictions'/row['id']/'M1.json'
    old=load(oldpath)
    result=dict(id=row['id'],historical_output_sha256=sha256(oldpath.read_bytes()).hexdigest(),
        current_surface_sha256=s.sha256,historical_surface_sha256=old['surface']['sha256'],
        surface_exact=s.sha256==old['surface']['sha256'],routes_exact=digest(routes)==digest(old['routes']),
        actual_routes_sha256=digest(routes),historical_routes_sha256=digest(old['routes']),
        reached=sum(x['reached'] for x in routes.values()),area_m2=p['area_m2'],
        role=('FROZEN_OBSERVED_ONLY_CLASSIFIER_CACHE_IDENTITY_PLUS_ACTUAL_HISTORICAL_ROUTER_REPLAY' if row.get('natural') else 'CURRENT_RECOMPUTED_CLASSIFIER_PLUS_HISTORICAL_ROUTER_CALIBRATION_NO_REGION_REBUILD'))
    print(row['id'],result['surface_exact'],result['routes_exact'],flush=True)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ids',nargs='+',default=['Wc4183046a70_G_080','W6daddd19fdb_G_080','W745941f0f92_G_080','W0440b97497a_N_080','NORTH_160']);a=p.parse_args()
    rows=load(ROOT/'data/task_manifest.json')['instances'];results=[replay(next(r for r in rows if r['id']==i)) for i in a.ids]
    out=ROOT/'audits/historical_calibration.json';out.write_text(json.dumps({'status':'PASS' if all(r['surface_exact'] and r['routes_exact'] for r in results) else 'FAIL','cases':results,'region_builds':0},indent=2),encoding='utf8')
