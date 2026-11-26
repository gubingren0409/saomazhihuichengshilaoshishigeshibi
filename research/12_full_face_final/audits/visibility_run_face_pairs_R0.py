"""Fixed source-supported local face mechanism queries, not APP/door claims.

--lock performs no path search. --run refuses to select endpoints and consumes
the pre-existing lock. All geometry comes from frozen metric source evidence.
"""
from pathlib import Path
import argparse,gzip,hashlib,heapq,json,math,sys,time
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from shapely.geometry import Point,LineString,mapping
from src.face_geometry import compile_faces,face_edge_conflicts
from src.face_visibility import shortest_path
from src.region import non_ground,access_conflict
from src.common_constraints import parsed_contract
from audit_faces import source_contract
from src.scene_data import file_sha


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def area_population():
    # One already used APP domain plus the two primary source faces. This is a
    # pre-result mechanism population, not a scan for the biggest improvement.
    scenes=read(ROOT/'data/face_selection_lock.json')['scenes']
    return [s for s in scenes if s['scene_id']in{'sh-huangpu-01','sh-library'}]
def iterate_edges(scene_id):
    scene=next(s for s in read(ROOT/'data/scene_manifest.json')['scenes']if s['scene_id']==scene_id)
    path=ROOT/scene['mapped_edges_path'];assert file_sha(path)==scene['mapped_edges_sha256']
    with gzip.open(path,'rt',encoding='utf-8')as f:
        for line in f:yield json.loads(line)


def lock():
    destination=ROOT/'data/face_pairs_lock.json'
    if destination.exists():raise FileExistsError('Fixed pair lock exists; do not reselect after outcomes')
    selected=[];population=[]
    for scene in area_population():
        scene_id=scene['scene_id'];data,common,cfg,unlocated=source_contract(scene_id)
        faces=compile_faces(data,common,cfg);parsed=parsed_contract(common)
        candidates={f['source_id']:{}for f in faces};native_candidates={f['source_id']:{}for f in faces}
        by_id={f['source_id']:f for f in faces}
        # Native ports are already explicitly identified in frozen band input.
        for row in iterate_edges(scene_id):
            sid=row['source_area_id'];face=by_id.get(sid)
            if face is None or face['status']!='ADMITTED' or not row.get('native_port_id'):continue
            line=LineString(row['coordinates_metric'])
            if face_edge_conflicts(line,face,parsed):continue
            for ident,xy in zip((row['u'],row['v']),row['coordinates_metric']):
                if not face['omega'].covers(Point(xy)):continue
                rec={'id':ident,'xy':xy,'endpoint_kind':'EXISTING_NATIVE_PORT'if ident==row['native_port_id']else'EXISTING_BAND_DERIVED_NODE',
                     'source_edge_id':row['edge_id'],'native_port_source_way_ids':row.get('native_port_source_way_ids',[])}
                candidates[sid].setdefault(ident,rec)
                if ident==row['native_port_id']:native_candidates[sid].setdefault(ident,rec)
        for face in faces:
            sid=face['source_id'];raw=native_candidates[sid]
            pool=raw if len(raw)>=3 else candidates[sid]
            points=sorted(pool.values(),key=lambda p:p['id'])
            population.append({'scene_id':scene_id,'source_area_id':sid,'status':face['status'],'native_ports':len(raw),'eligible_source_nodes':len(pool),
                'geometry_hash':face['geometry_hash'],'selection_role':'Existing source ports on whole-edge-legal frozen band segments; no result read'})
            if len(points)<2:continue
            pairs=[('EAST_WEST_EXTREMA',min(points,key=lambda p:(p['xy'][0],p['xy'][1],p['id'])),max(points,key=lambda p:(p['xy'][0],p['xy'][1],p['id']))),
                   ('NORTH_SOUTH_EXTREMA',min(points,key=lambda p:(p['xy'][1],p['xy'][0],p['id'])),max(points,key=lambda p:(p['xy'][1],p['xy'][0],p['id']))),
                   ('FIRST_TWO_STABLE_SOURCE_IDS',points[0],points[1])]
            used=set();limit=3 if scene_id=='sh-huangpu-01'else 2
            for rule,a,b in pairs:
                key=tuple(sorted((a['id'],b['id'])))
                if a['id']==b['id']or key in used:continue
                used.add(key);selected.append({'pair_id':f'{scene_id}/{sid}/{len(used)}','scene_id':scene_id,'source_area_id':sid,'rule':rule,
                    'source':a,'target':b,'omega_sha256':face['geometry_hash'],'old_mapped_edges_sha256':scene['mapped_edges_sha256'],
                    'role':'LOCAL_FACE_MECHANISM_POINTS_NOT_NEW_ENTRANCES_OR_BUILDINGS'})
                if len(used)>=limit:break
    assert len(selected)<=12
    result={'role':'LOCKED_BEFORE_ANY_FULL_FACE_MECHANISM_SEARCH','selection':'Primary north/south plus existing library face; stable extrema and ID order; never route-result filtered',
            'crs':'EPSG:32651','real_face_pairs':len(selected),'population':population,'pairs':selected,'reference_or_saved_route_reads':0}
    write(destination,result);print(json.dumps(result,ensure_ascii=False,indent=2))


def band_graph(scene_id,face,common):
    adjacency=defaultdict(list);xy={};counts=defaultdict(int)
    for row in iterate_edges(scene_id):
        if row['source_area_id']!=face['source_id']:continue
        counts['source_rows']+=1;line=LineString(row['coordinates_metric'])
        reasons=face_edge_conflicts(line,face,common)
        if reasons:
            counts['excluded_rows']+=1
            for reason in reasons:counts[reason]+=1
            continue
        u,v=row['u'],row['v'];a,b=row['coordinates_metric'];xy[u]=a;xy[v]=b
        length=line.length
        if abs(length-row['length_m'])>1e-6:raise ValueError('Band source length mismatch')
        adjacency[u].append((v,length,row['edge_id']))
        if row['direction']=='BIDIRECTIONAL':adjacency[v].append((u,length,row['edge_id']))
    return adjacency,xy,dict(counts)


def band_route(graph,points,a,b):
    if a not in points or b not in points:return {'status':'UNAVAILABLE_SOURCE_ENDPOINT','length_m':None,'points':[]}
    heap=[(0,a)];best={a:0};prior={}
    while heap:
        distance,u=heapq.heappop(heap)
        if distance!=best[u]:continue
        if u==b:break
        for v,cost,eid in graph.get(u,[]):
            candidate=distance+cost
            if candidate<best.get(v,math.inf):best[v]=candidate;prior[v]=(u,eid);heapq.heappush(heap,(candidate,v))
    if b not in best:return {'status':'NO_PATH','length_m':None,'points':[]}
    ids=[b];edges=[]
    while ids[-1]!=a:
        p,e=prior[ids[-1]];edges.append(e);ids.append(p)
    return {'status':'ROUTED','length_m':best[b],'points':[points[i]for i in ids[::-1]],'node_ids':ids[::-1],'source_edge_ids':edges[::-1]}


def run():
    locked=read(ROOT/'data/face_pairs_lock.json');records=[];t0=time.perf_counter()
    for scene in area_population():
        data,common,cfg,_=source_contract(scene['scene_id']);faces=compile_faces(data,common,cfg);parsed=parsed_contract(common)
        for face in faces:
            pairs=[p for p in locked['pairs']if p['scene_id']==scene['scene_id']and p['source_area_id']==face['source_id']]
            if not pairs:continue
            graph,points,old_counts=band_graph(scene['scene_id'],face,parsed)
            for query in pairs:
                assert query['omega_sha256']==face['geometry_hash']
                a,b=query['source'],query['target'];tick=time.perf_counter()
                old=band_route(graph,points,a['id'],b['id']);old_s=time.perf_counter()-tick
                required=[r['xy']for r in face.get('required_points',[])]
                new=shortest_path(face['omega'],a['xy'],b['xy'],edge_allowed=lambda line:not face_edge_conflicts(line,face,parsed),required_points=required)
                new_line=LineString(new['points'])if len(new['points'])>=2 else None
                direct=LineString([a['xy'],b['xy']]);same_part=any(r['geometry'].covers(Point(a['xy']))and r['geometry'].covers(Point(b['xy']))for r in face['components'])
                result={'query':query,'old':old,'full_face':new,'old_graph':old_counts,'old_query_s':old_s,
                    'geometry_hash':face['geometry_hash'],'full_constraint_sha256':common['sha256'],
                    'direct_visibility':not face_edge_conflicts(direct,face,parsed),'same_positive_width_component':same_part,
                    'delta_length_m':new['length_m']-old['length_m']if new['reached']and old['length_m']is not None else None,
                    'new_length_outside_old_band_m':new_line.difference(face['edge_band_geometry']).length if new_line is not None else None,
                    'full_segment_conflicts':[{'segment':i,'reasons':face_edge_conflicts(LineString([p,q]),face,parsed)}for i,(p,q)in enumerate(zip(new['points'],new['points'][1:]))if face_edge_conflicts(LineString([p,q]),face,parsed)],
                    'reference_reads':0,'saved_routes_used_as_solver_input':False,'scope':'Local uniform-domain mechanism comparison; native access exceptions not imported; not APP whole-route or field result'}
                records.append(result)
                name=query['pair_id'].replace('/','_');write(ROOT/'runs/face_pairs'/f'{name}.json',result)
                print(query['pair_id'],old['length_m'],new['length_m'],flush=True)
            del graph,points
    summary={'real_face_pairs':len(records),'records':[{'pair_id':r['query']['pair_id'],'old_status':r['old']['status'],'full_status':r['full_face']['status'],
        'old_length_m':r['old']['length_m'],'full_length_m':r['full_face']['length_m'],'delta_length_m':r['delta_length_m'],
        'outside_old_band_m':r['new_length_outside_old_band_m'],'direct_visibility':r['direct_visibility'],'conflicts':len(r['full_segment_conflicts'])}for r in records],
        'elapsed_s':time.perf_counter()-t0,'actual_local_shortest_queries':len(records),'APP_solver_calls':0,
        'limitations':['Local pairs are not entrances','No requirement to manufacture real disconnected/obstructed examples','Old rows rechecked in sameOmega; excluded counts reported separately','No observed masked benchmark reads']}
    write(ROOT/'runs/face_pairs/summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--lock',action='store_true');p.add_argument('--run',action='store_true');args=p.parse_args()
    if args.lock:lock()
    elif args.run:run()
    else:p.error('Choose --lock or --run')
