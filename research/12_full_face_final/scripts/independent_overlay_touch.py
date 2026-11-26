"""Independent overlay point-touch counterexample, tiny synthetic graph only."""
from pathlib import Path
import argparse,json,math,sys,hashlib
import networkx as nx
from shapely.geometry import box,MultiPolygon,mapping
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.common_constraints import build_contract
from src.face_visibility import build_overlay

def run(revision=''):
    path=ROOT/'src/face_visibility.py';before=hashlib.sha256(path.read_bytes()).hexdigest()
    a,b=box(0,0,2,2),box(2,2,4,4);domain=MultiPolygon([a,b]);coverage=box(-2,-2,6,6)
    obs={'crs':'EPSG:32651','domain':{'anchor_xy':[2,2]},'nodes':[],'edges':[],'context':{'hard':[],'background':[],'support':[]}}
    guards={'crs':'EPSG:32651','source_parse_status':'PARSED','coverage_geometry':mapping(coverage)}
    common=build_contract(obs,guards,{'domain_radius_m':30},domain=mapping(coverage))
    source=nx.DiGraph();local=nx.DiGraph()
    def add(g,ident,xy):g.add_node(ident,xy=xy,tags={})
    def link(g,u,v,layer):
        xy=[g.nodes[u]['xy'],g.nodes[v]['xy']];length=math.dist(*xy)
        s={'xy':xy,'layer':layer,'source_id':'way/synthetic'if layer=='native'else'cell/synthetic','length_m':length,'cost_m':length,'tags':{'highway':'footway'}if layer=='native'else{}}
        g.add_edge(u,v,cost=length,segments=[s]);g.add_edge(v,u,cost=length,segments=[{**s,'xy':xy[::-1]}])
    for ident,xy in[('native/A',(1,1)),('native/An',(.5,1)),('native/B',(3,3)),('native/Bn',(3.5,3))]:add(source,ident,xy)
    link(source,'native/A','native/An','native');link(source,'native/B','native/Bn','native')
    add(local,'cell/touch',(2,2));add(local,'cell/outside',(1,3));link(local,'cell/touch','cell/outside','inferred')
    face={'id':'synthetic-face','source_id':'synthetic-face','omega':domain,'tags':{'area':'yes','highway':'pedestrian'},'geometry_hash':'synthetic',
        'clearance_m':.25,'components':[{'geometry':a},{'geometry':b}]}
    overlay,evidence=build_overlay([face],source,local,common)
    combined=nx.compose_all([source,local,overlay]);reached=nx.has_path(combined,'native/A','native/B')
    nodes=nx.shortest_path(combined,'native/A','native/B',weight='cost')if reached else[]
    segs=[s for u,v in zip(nodes,nodes[1:])for s in combined[u][v]['segments']]
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_ANALYTICAL_OVERLAY_POINT_TOUCH_COUNTEREXAMPLE','APP_solver_calls':0,
        'DUT_sha256':before,'DUT_stable':before==hashlib.sha256(path.read_bytes()).hexdigest(),
        'fixture':'Two positive-area polygons meet only at(2,2); source native graphs disconnected; one local inferred cell at touch has an outward edge',
        'expected_derived_only_cross_component_route':False,'DUT_reached':reached,'nodes':nodes,
        'route_layers':[s['layer']for s in segs],'assumed_length_m':sum(s['length_m']for s in segs if s['layer']in{'inferred','assumed','unknown'}),
        'portals':evidence['portals'],'source_graph_unmodified_nodes':list(source),'local_graph_unmodified_nodes':list(local)}
    result['status']='CONFIRMED_IMPLEMENTATION_DEFECT'if reached and not result['assumed_length_m']else'PASS_NO_DERIVED_POINT_TOUCH_SHORTCUT'
    output=ROOT/'audits'/('independent_overlay_touch'+('_'+revision if revision else'')+'.json');output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in['status','DUT_reached','route_layers','assumed_length_m','DUT_sha256']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--revision',default='');a=p.parse_args();run(a.revision)
