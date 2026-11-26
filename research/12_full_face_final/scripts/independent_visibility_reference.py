"""Independent complete-vertex visibility reference and analytic checks.

The expected algorithm uses every polygon vertex plus heap Dijkstra, rather
than the implementation's reflex pruning/NetworkX shortest path. The author
API is called only as device under test, never as the reference calculator.
"""
from pathlib import Path
import argparse,hashlib,heapq,json,math,random,sys,time
from shapely.geometry import Polygon,MultiPolygon,LineString,Point,box
from shapely.ops import unary_union
from shapely.affinity import translate
from shapely.prepared import prep
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from independent_face_check import RawSource,polygons,face_tagged,area_permission,ground,save,read,file_sha,expected_omega

def dijkstra(adj,s,t):
    queue=[(0.,s)];best={s:0.};previous={}
    while queue:
        distance,u=heapq.heappop(queue)
        if distance!=best.get(u):continue
        if u==t:
            path=[u]
            while u!=s:u=previous[u];path.append(u)
            return distance,path[::-1]
        for v,cost in adj[u]:
            new=distance+cost
            if new<best.get(v,math.inf):best[v]=new;previous[v]=u;heapq.heappush(queue,(new,v))
    return None,[]

def complete_vertex_reference(domain,start,end,allowed=None,required=()):
    best=None;total_checks=0
    for component_id,p in enumerate(polygons(domain)):
        if not p.covers(Point(start))or not p.covers(Point(end)):continue
        covers=prep(p).covers
        points=sorted(set([tuple(start),tuple(end),*[tuple(c)for ring in[p.exterior,*p.interiors]for c in list(ring.coords)[:-1]],*[tuple(c)for c in required if p.covers(Point(c))]]))
        adj={i:[]for i in range(len(points))}
        for i,a in enumerate(points):
            for j in range(i+1,len(points)):
                b=points[j];line=LineString([a,b]);total_checks+=1
                if covers(line)and(allowed is None or allowed(line)):
                    length=math.dist(a,b);adj[i].append((j,length));adj[j].append((i,length))
        length,path=dijkstra(adj,points.index(tuple(start)),points.index(tuple(end)))
        if length is not None and(best is None or length<best['length_m']):
            best={'length_m':length,'points':[points[i]for i in path],'component_id':component_id,'all_vertex_count':len(points)}
    return {'reached':best is not None,'length_m':best['length_m']if best else None,'points':best['points']if best else[],'visibility_checks':total_checks}

def lazy_complete_vertex_reference(domain,start,end):
    """Same complete all-vertex visibility graph, generated only when relaxed.

    Euclidean distance to target is admissible and consistent for every
    Euclidean visibility edge. No reflex, tangent or endpoint/portal pruning.
    """
    best_answer=None;checks=0;expanded=0;tick=time.perf_counter()
    for component_id,p in enumerate(polygons(domain)):
        if not p.covers(Point(start))or not p.covers(Point(end)):continue
        points=sorted(set([tuple(start),tuple(end),*[tuple(c)for ring in[p.exterior,*p.interiors]for c in list(ring.coords)[:-1]]]))
        covers=prep(p).covers;s,t=points.index(tuple(start)),points.index(tuple(end));heuristic=[math.dist(x,end)for x in points]
        best={s:0.};prior={};closed=set();queue=[(heuristic[s],0.,s)]
        while queue:
            _,distance,u=heapq.heappop(queue)
            if distance!=best.get(u)or u in closed:continue
            if u==t:
                path=[u]
                while u!=s:u=prior[u];path.append(u)
                answer={'length_m':distance,'points':[points[i]for i in path[::-1]],'component_id':component_id,'all_vertex_count':len(points)}
                if best_answer is None or distance<best_answer['length_m']:best_answer=answer
                break
            closed.add(u);expanded+=1
            for v,q in enumerate(points):
                if v in closed:continue
                new=distance+math.dist(points[u],q)
                if new>=best.get(v,math.inf):continue
                checks+=1
                if covers(LineString([points[u],q])):
                    best[v]=new;prior[v]=u;heapq.heappush(queue,(new+heuristic[v],new,v))
            if expanded%50==0:
                save(ROOT/'audits/independent_real_reference_progress.json',{'status':'RUNNING','expanded':expanded,'visibility_checks':checks,'elapsed_s':time.perf_counter()-tick})
    return {'reached':best_answer is not None,'length_m':best_answer['length_m']if best_answer else None,
        'points':best_answer['points']if best_answer else[],'visibility_checks':checks,'expanded_vertices':expanded,
        'method':'LAZY_COMPLETE_ALL_VERTEX_VISIBILITY_EUCLIDEAN_A_STAR_NO_GEOMETRIC_PRUNING','elapsed_s':time.perf_counter()-tick}

def cases():
    wall=LineString([(10,0),(10,10)]);gate=Point(10,2)
    def through_gate(line):
        hit=line.intersection(wall)
        return hit.is_empty or hit.geom_type=='Point'and hit.distance(gate)<=1e-9
    base=box(0,0,20,10)
    narrow=unary_union([box(4,0,6,1.8),box(4,2.2,6,4)])
    return [
        {'id':'RECTANGLE_ANALYTIC_DIAGONAL','domain':box(0,0,10,6),'start':(0,0),'end':(10,6),'expected':math.sqrt(136)},
        {'id':'RECTANGULAR_HOLE_ANALYTIC','domain':Polygon([(0,0),(12,0),(12,8),(0,8)],holes=[[(4,2),(8,2),(8,6),(4,6)]]),'start':(1,4),'end':(11,4),'expected':2*math.sqrt(13)+4},
        {'id':'CONCAVE_L_REFLEX','domain':Polygon([(0,0),(6,0),(6,2),(2,2),(2,6),(0,6)]),'start':(5,1),'end':(1,5),'expected':2*math.sqrt(10)},
        {'id':'DISCONNECTED_PARTS','domain':MultiPolygon([box(0,0,3,3),box(5,0,8,3)]),'start':(1,1),'end':(6,1),'expected':None},
        {'id':'POINT_TOUCH_NOT_POSITIVE_WIDTH','domain':MultiPolygon([box(0,0,2,2),box(2,2,4,4)]),'start':(1,1),'end':(3,3),'expected':None},
        {'id':'FENCE_OPEN_POSITIVE_GAP','domain':base.difference(unary_union([box(9.75,0,10.25,4.5),box(9.75,5.5,10.25,10)])),'start':(1,5),'end':(19,5),'expected':18},
        {'id':'FENCE_CLOSED','domain':base.difference(box(9.75,0,10.25,10)),'start':(1,5),'end':(19,5),'expected':None},
        {'id':'CLEARANCE_CLOSED_NARROW_GAP','domain':box(0,0,10,4).difference(narrow.buffer(.25,quad_segs=16)),'start':(2,2),'end':(8,2),'expected':None},
        {'id':'ORIGINAL_BOUNDARY_COORDINATES','domain':box(0,0,5,5),'start':(0,2),'end':(5,2),'expected':5},
        {'id':'ZERO_WIDTH_BARRIER_EXACT_SOURCE_GATE','domain':base,'start':(1,5),'end':(19,5),'expected':2*math.sqrt(90),'allowed':through_gate,'required':[(10,2)]},
        {'id':'PRIVATE_FULL_STRIPE','domain':box(0,0,20,10).difference(box(9,0,11,10)),'start':(1,5),'end':(19,5),'expected':None}]

def synthetic(suffix=''):
    # Load only now, after source is frozen by its author. Before/after SHA guard
    # records reject any concurrent implementation change during this run.
    path=ROOT/'src/face_visibility.py';before=hashlib.sha256(path.read_bytes()).hexdigest()
    from src.face_visibility import shortest_path
    rows=[];tick=time.perf_counter()
    for c in cases():
        ref=complete_vertex_reference(c['domain'],c['start'],c['end'],c.get('allowed'),c.get('required',()))
        actual=shortest_path(c['domain'],c['start'],c['end'],edge_allowed=c.get('allowed'),required_points=c.get('required',()))
        errors=[]
        for who,r in [('REFERENCE',ref),('DEVICE_UNDER_TEST',actual)]:
            if r['reached']!=(c['expected']is not None):errors.append(who+'_REACHABILITY')
            elif c['expected']is not None and abs(r['length_m']-c['expected'])>1e-7:errors.append(who+'_ANALYTIC_LENGTH')
            if r['reached']:
                if tuple(r['points'][0])!=c['start']or tuple(r['points'][-1])!=c['end']:errors.append(who+'_ENDPOINT_DRIFT')
                if LineString(r['points']).difference(c['domain']).length>1e-7:errors.append(who+'_OUTSIDE_DOMAIN')
        rows.append({'case_id':c['id'],'expected_length_m':c['expected'],'reference':ref,'device_under_test':actual,'errors':errors})
    after=hashlib.sha256(path.read_bytes()).hexdigest()
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_ANALYTIC_AND_COMPLETE_VERTEX_REFERENCE','author_API_called_only_as_device_under_test':True,
        'independent_reference_calls_author':False,'reference_method':'All polygon vertices; strict covers; per-component graph; own heap Dijkstra',
        'cases':rows,'elapsed_s':time.perf_counter()-tick,'DUT_source_sha256':before,'DUT_source_stable':before==after,'app_solver_calls':0,
        'admission_sanity':{'plain_park_is_not_full_face':not face_tagged({'leisure':'park'}),'private_face_not_eligible':not area_permission({'area':'yes','highway':'pedestrian','access':'private'}),'level1_not_ground_face':not ground({'level':'1'})}}
    result['status']='PASS'if before==after and all(not r['errors']for r in rows)and all(result['admission_sanity'].values())else'FAIL'
    save(ROOT/'audits'/('independent_visibility_analytic'+suffix+'.json'),result)
    print(json.dumps({'status':result['status'],'cases':len(rows),'elapsed_s':result['elapsed_s'],'source_sha256':before},ensure_ascii=False))

def tangent_comparison(suffix=''):
    """Independent all-vertex reference on deterministic varied polygon cases.

    This tests pruning correctness on finite synthetic inputs. It is not a
    general proof, a real-map score, or an APP solver budget request.
    """
    path=ROOT/'src/face_visibility.py';before=hashlib.sha256(path.read_bytes()).hexdigest()
    from src.face_visibility import shortest_path
    rng=random.Random(20261111);rows=[];tick=time.perf_counter()
    for k in range(24):
        if k%3==0:
            obstacles=[box(4,1.2+rng.random(),6,4.1+rng.random()),box(10,4.9+rng.random(),12,8.2+rng.random())]
            domain=box(0,0,16,11).difference(unary_union(obstacles))
            start,end=(1.,5.5),(15.,5.5)
        elif k%3==1:
            # Multiple alternating boundary indentations force several bends.
            obstacles=[box(3,-1,4,5+rng.random()),box(7,5+rng.random(),8,12),box(11,-1,12,5+rng.random())]
            domain=box(0,0,16,11).difference(unary_union(obstacles))
            start,end=(1.,5.5),(15.,5.5)
        else:
            domain=Polygon([(0,0),(16,0),(16,11),(12,11),(12,4),(10,4),(10,11),(6,11),(6,3),(4,3),(4,11),(0,11)])
            start,end=(2.,9.),(14.,9.)
        if k%2:
            domain=Polygon(list(domain.exterior.coords)[::-1],[list(r.coords)[::-1]for r in domain.interiors])
        dx,dy=(352217.314,3459034.587)if k>=12 else(0,0)
        domain=translate(domain,xoff=dx,yoff=dy);start=(start[0]+dx,start[1]+dy);end=(end[0]+dx,end[1]+dy)
        ref=complete_vertex_reference(domain,start,end);actual=shortest_path(domain,start,end)
        errors=[]
        if ref['reached']!=actual['reached']:errors.append('REACHABILITY')
        elif ref['reached']and abs(ref['length_m']-actual['length_m'])>1e-7:errors.append('LENGTH')
        if actual['reached']and LineString(actual['points']).difference(domain).length>1e-7:errors.append('OUTSIDE_DOMAIN')
        rows.append({'case_id':f'PRUNING_{k:02d}','winding_reversed':bool(k%2),'large_metric_translation':bool(k>=12),
            'reference':ref,'device_under_test':actual,'errors':errors})
    after=hashlib.sha256(path.read_bytes()).hexdigest()
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_PRUNING_COUNTEREXAMPLE_CHECK','seed':20261111,'cases':rows,
        'reference_method':'All polygon vertices; strict covers; own heap Dijkstra; no author tangent function',
        'DUT_source_sha256':before,'DUT_source_stable':before==after,'elapsed_s':time.perf_counter()-tick,'app_solver_calls':0,
        'limitations':'24 finite synthetic shapes, not general proof or real-world shortest-path certification'}
    result['status']='PASS'if before==after and all(not r['errors']for r in rows)else'FAIL'
    save(ROOT/'audits'/('independent_visibility_pruning'+suffix+'.json'),result)
    print(json.dumps({'status':result['status'],'cases':len(rows),'elapsed_s':result['elapsed_s']},ensure_ascii=False))

def fixed_real_pairs(author_dir):
    # Stable first prelocked pair per primary source face, chosen without
    # reading new route outcomes. These are repeats, not additional endpoints.
    author_dir=author_dir.resolve();lockpath=ROOT/'data/face_pairs_lock.json';locked=read(lockpath)
    chosen=[next(p for p in locked['pairs']if p['source_area_id']==sid)for sid in ['relation/2153738','relation/2385771']]
    catalog={s['scene_id']:s for s in read(ROOT/'data/scene_manifest.json')['scenes']}
    rows=[];tick=time.perf_counter()
    for query in chosen:
        row=catalog[query['scene_id']];src=RawSource(ROOT/row['source_path']);P=src.geometry(query['source_area_id']);omega,_=expected_omega(src,P)
        ref=lazy_complete_vertex_reference(omega,query['source']['xy'],query['target']['xy'])
        save(ROOT/'audits'/('independent_reference_completed_'+query['source_area_id'].replace('/','_')+'.json'),
            {'query':query,'reference':ref,'raw_source_sha256':file_sha(src.path),'lock_sha256':file_sha(lockpath),
             'reviewer_script_sha256':file_sha(Path(__file__)),'status':'COMPLETED_REFERENCE_BEFORE_AUTHOR_COMPARISON'})
        reference_length=sum(math.dist(a,b)for a,b in zip(ref['points'],ref['points'][1:]))
        outside=LineString(ref['points']).difference(omega).length if len(ref['points'])>1 else 0
        author_path=author_dir/(query['pair_id'].replace('/','_')+'.json')
        comparison=None
        if author_path.exists():
            actual=read(author_path)['full_face']
            comparison={'file':str(author_path.relative_to(ROOT)),'sha256':file_sha(author_path),
                'reached':actual['reached'],'length_m':actual['length_m'],
                'agrees':actual['reached']==ref['reached']and(not ref['reached']or abs(actual['length_m']-ref['length_m'])<=1e-6)}
        rows.append({'query':query,'raw_source_sha256':file_sha(src.path),'reference':ref,
            'independent_polyline_length_m':reference_length,'outside_independent_omega_m':outside,'author_comparison':comparison})
        print(json.dumps({'pair':query['pair_id'],'reference_length_m':ref['length_m'],'outside_omega_m':outside},ensure_ascii=False),flush=True)
        del src,omega
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_ALL_VERTEX_REAL_POLYGON_REFERENCE','APP_solver_calls':0,
        'new_real_endpoint_pairs':0,'repeated_fixed_pairs':len(rows),'selection_lock_sha256':file_sha(lockpath),'rows':rows,
        'author_functions_called':False,'method':'All independent raw polygon Ω vertices; strict prepared covers; own lazy complete-graph Euclidean A*; no reflex/tangent pruning',
        'elapsed_s':time.perf_counter()-tick,
        'limitations':['Polygonal domain optimum only; no native network or APP topology claim',
            'Primary raw road touches Ω only at isolated point, raw barrier intersections have zero length; no internal omitted linear barrier crossing in these selected domains',
            'No physical/field accessibility, finite-source-interface global optimum, or continuous circular-clearance certification']}
    result['status']='PASS'if all(r['outside_independent_omega_m']<=1e-6 and(r['author_comparison']is None or r['author_comparison']['agrees'])for r in rows)else'REQUIRES_INSPECTION'
    save(ROOT/'audits/independent_real_face_pairs.json',result)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--synthetic',action='store_true');ap.add_argument('--tangent',action='store_true');ap.add_argument('--real-pairs',action='store_true');ap.add_argument('--revision',default='');ap.add_argument('--author-dir',type=Path,default=ROOT/'runs/face_pairs_R1');a=ap.parse_args()
    suffix='_'+a.revision if a.revision else''
    if a.synthetic:synthetic(suffix)
    if a.tangent:tangent_comparison(suffix)
    if a.real_pairs:fixed_real_pairs(a.author_dir)
