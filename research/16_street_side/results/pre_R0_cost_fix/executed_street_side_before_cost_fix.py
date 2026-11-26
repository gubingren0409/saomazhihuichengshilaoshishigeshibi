"""Bounded source-grounded side-identity experiment; all offsets are schematic.

No network requests, no global visibility graph, no edits to historical inputs.
Formal queries test topology, not physical sidewalk clearance or navigation.
"""
from __future__ import annotations
import argparse, collections, csv, datetime, gzip, hashlib, heapq, json, math, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'SMART_CITY_WALKABILITY_FOUNDATION_PG1'
MOTOR = {'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road'}
ORDINARY = {'residential','service','living_street','unclassified'}
DENIED = {'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
FALSE = {None,'','0','no','false'}
OFFSET = 4.0  # Display separation only. No road-width inference or geometry test.

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
def write(p,d):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def denied(t):
    return t.get('foot',t.get('access')) in DENIED or t.get('locked')=='yes' or any(k.endswith(':conditional') and k.split(':')[0] in {'foot','access','oneway'} for k in t)
def nonground(t): return any(t.get(k) not in FALSE for k in ('layer','level','bridge','tunnel','indoor','repeat_on')) or t.get('highway') in {'steps','elevator'}
def level(t): return 'layer='+str(t.get('layer','0'))+';level='+str(t.get('level','0'))+';bridge='+str(t.get('bridge','no'))+';tunnel='+str(t.get('tunnel','no'))
def sides(t):
    out=[]
    for s in ('left','right'):
        v=t.get('sidewalk:'+s,t.get('sidewalk:both',t.get('sidewalk')))
        if v in {'yes','both'} or (v==s): out.append(s)
        elif t.get('sidewalk')==s and 'sidewalk:'+s not in t: out.append(s)
    return out
def separate(t,s): return t.get('sidewalk:'+s,t.get('sidewalk:both',t.get('sidewalk')))=='separate'
def axis_missing(t): return not any(k.startswith('sidewalk') for k in t)
def category(t):
    if denied(t) or nonground(t): return 'EXPLICIT_RESTRICTION_OR_NON_GROUND'
    if t.get('footway')=='sidewalk': return 'NATIVE_INDEPENDENT_SIDEWALK'
    if sides(t): return 'SIDE_TAG_SUPPORT_WITHOUT_INDEPENDENT_GEOMETRY'
    if t.get('sidewalk') in {'no','none','separate'} or any(t.get('sidewalk:'+s)=='separate' for s in ('left','right')): return 'EXPLICIT_NEGATIVE_OR_SEPARATE_DO_NOT_DEFAULT'
    if t.get('highway') in ORDINARY and axis_missing(t): return 'SHARED_STREET_OR_CONDITIONAL_SIDE_HYPOTHESIS'
    return 'UNKNOWN_OR_OUTSIDE_SIDE_POLICY'
def crossing(t): return t.get('highway')=='crossing' or t.get('footway')=='crossing'
def distance(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def shifted(a,b,side):
    dx,dy=b[0]-a[0],b[1]-a[1];n=math.hypot(dx,dy)
    if not n:return [list(a),list(b)]
    sign=1 if side=='left' else -1;ox,oy=-dy/n*OFFSET*sign,dx/n*OFFSET*sign
    return [[a[0]+ox,a[1]+oy],[b[0]+ox,b[1]+oy]]
def native_id(n,t): return f'native:{n}:{level(t)}'
def side_id(road,s,n,t): return f'{road}:{s}:node/{n}:{level(t)}'

def prepare():
    """Source-only selection. This writes the lock before any new graph exists."""
    if (ROOT/'audit/window_lock.json').exists(): raise RuntimeError('LOCK_EXISTS_DO_NOT_RESELECT')
    index=read(OLD/'phase1/scene_index.json'); inventory=[];window_rows=[]
    # Different examples chosen by source structure only; never by route outcomes.
    specs=[('native','sh-huangpu-01'),('tagged','sh-library'),('missing','sh-wukang')]
    for info in index:
        raw=read(info['source_path']);assert sha(info['source_path'])==info['source_sha256']
        for o in raw['elements']:
            t=o.get('tags',{})
            if o['type']=='way' and (t.get('highway') in MOTOR or t.get('footway')=='sidewalk'):
                inventory.append({'scene_id':info['scene_id'],'source_id':'way/'+str(o['id']),'name':t.get('name',''),'category':category(t),'highway':t.get('highway',''),'tags_json':json.dumps(t,ensure_ascii=False,sort_keys=True),'source_sha256':info['source_sha256'],'width_field_present_unvalidated':any(k in t for k in ('width','width:carriageway','lanes'))})
        spec=next((s for s in specs if s[1]==info['scene_id']),None)
        if not spec: continue
        mode,scene=spec;data=read(OLD/'phase1/data'/scene/'scene.json')
        features={f['properties']['source_id']:f for f in data['features'] if f.get('geometry')}
        ways={o['id']:o for o in raw['elements'] if o['type']=='way'}
        node_objects={o['id']:o for o in raw['elements'] if o['type']=='node'}
        with gzip.open(OLD/'phase1/data'/scene/'native_admission.jsonl.gz','rt',encoding='utf-8') as f: rows=[json.loads(l) for l in f if l.strip()]
        kept=collections.defaultdict(list)
        for r in rows:
            if r['status']=='KEEP_NATIVE': kept[r['source_id']].append(r)
        candidates=[]
        for w in ways.values():
            sid='way/'+str(w['id']);t=w.get('tags',{});rs=kept.get(sid,[])
            if not rs or denied(t) or nonground(t):continue
            okay=(mode=='native' and t.get('footway')=='sidewalk') or (mode=='tagged' and t.get('highway') in MOTOR and sides(t)) or (mode=='missing' and t.get('highway') in ORDINARY and axis_missing(t))
            if not okay:continue
            near=[r for r in rs if min(distance(x,info['target_xy']) for x in r['xy'])<=750]
            if near: candidates.append((w['id'],w,sorted(near,key=lambda r:r['segment_index'])))
        if not candidates: raise RuntimeError('NO_SOURCE_ELIGIBLE_'+mode)
        _,chosen,rs=min(candidates,key=lambda x:x[0]);seed=rs[len(rs)//2]
        center=[sum(x[k] for x in seed['xy'])/2 for k in (0,1)];bounds=[center[0]-160,center[1]-160,center[0]+160,center[1]+160]
        inside=lambda xy:bounds[0]<=xy[0]<=bounds[2] and bounds[1]<=xy[1]<=bounds[3]
        # Full-source segments only: no clipped new endpoints or closure edges.
        localrows=[r for r in rows if all(inside(x) for x in r['xy'])]
        localids={r['source_id'] for r in localrows};selected_ways={int(k.split('/')[1]):ways[int(k.split('/')[1])] for k in localids}
        wantednodes={n for r in localrows for n in r['source_node_ids']}
        # Source context retained independently of graph admission.
        from shapely.geometry import shape,box
        frame=box(*bounds);fs=[]
        for f in features.values():
            try:
                if shape(f['geometry']).intersects(frame):fs.append({'source_id':f['properties']['source_id'],'kind':f['properties'].get('families',[]),'tags':f['properties']['tags'],'geometry':f['geometry'],'geometry_basis':f['properties'].get('geometry_basis')})
            except (ValueError,TypeError):pass
        chosen_local=[r for r in localrows if r['source_id']=='way/'+str(chosen['id']) and r['status']=='KEEP_NATIVE']
        chosen_local.sort(key=lambda r:r['segment_index'])
        # Longitudinal query uses a single unbroken source way portion chosen now.
        chain=[chosen_local[0]]
        for r in chosen_local[1:]:
            if r['source_node_ids'][0]==chain[-1]['source_node_ids'][1]:chain.append(r)
            else:break
        a=chain[0]['source_node_ids'][0];b=chain[-1]['source_node_ids'][1]
        middle=chain[len(chain)//2]['source_node_ids'][0]
        queries=[{'query_id':mode+'-along','kind':'NATIVE_ALONG' if mode=='native' else 'SAME_LEFT_SIDE','road_id':'way/'+str(chosen['id']),'start_node':a,'end_node':b,'start_side':'left','end_side':'left'}]
        if mode=='native':
            # Native identity/control: reversed direction on exactly the same segment.
            queries.append({'query_id':mode+'-reverse','kind':'NATIVE_REVERSE','road_id':'way/'+str(chosen['id']),'start_node':b,'end_node':a,'start_side':'left','end_side':'left'})
        else: queries.append({'query_id':mode+'-cross-side','kind':'OPPOSITE_SIDE_SAME_SOURCE_STATION','road_id':'way/'+str(chosen['id']),'start_node':middle,'end_node':middle,'start_side':'left','end_side':'right'})
        payload={'window_id':mode,'scene_id':scene,'label':info['label']+' · '+chosen.get('tags',{}).get('name',str(chosen['id'])),'source_path_original':info['source_path'],'source_sha256':info['source_sha256'],'source_timestamp':info.get('source_timestamp'),'working_crs':'EPSG:32651','bounds_xy':bounds,'source_features':fs,'ways':selected_ways,'nodes':{n:node_objects[n] for n in wantednodes},'native_admission':localrows,'selected_road_id':'way/'+str(chosen['id']),'queries':queries,'selection_basis':'Fixed native/tagged/missing strata; minimum numeric way ID within750m of frozen target; midpoint kept source segment;320m square;no route outcome used'}
        output=ROOT/'results/inputs'/f'{mode}.json';write(output,payload)
        window_rows.append({k:payload[k] for k in ['window_id','scene_id','label','bounds_xy','selected_road_id','queries','source_sha256','selection_basis'] }|{'input_path':str(output.relative_to(ROOT)),'input_sha256':sha(output)})
        del data,raw
    inventory_path=ROOT/'results/road_information_inventory.csv'
    with inventory_path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
    write(ROOT/'results/road_information_summary.json',{'by_scene_category':{scene:dict(collections.Counter(r['category'] for r in inventory if r['scene_id']==scene)) for scene in [x['scene_id'] for x in index]},'unique_scene_records':len(inventory),'duplicate_shared_source_objects_not_independent':True,'new_route_calls':0})
    write(ROOT/'audit/window_lock.json',{'locked_at':now(),'new_graphs_or_routes_before_lock':0,'strata_order':['native','tagged','missing'],'main_formal_requests':18,'repair_allowance':6,'cost_policy':'F1 only for18main topology queries; F0/F1 edgecosts both exported; F1=F0+hypothesis_axis_reference_cost;no newcostsearch','query_scope':'Source waypoint/side identity diagnostics, NOT registered-door business routes;native control uses exact source geometry;side results topology only','cutoff':'2026-11-13T05:17:19+08:00','windows':window_rows})
    print(json.dumps({'locked':len(window_rows),'roads':len(inventory),'windows':[(r['window_id'],r['selected_road_id'],r['label'])for r in window_rows]},ensure_ascii=False))

def graph(payload,variant):
    ways={int(k):v for k,v in payload['ways'].items()};nodes={int(k):v for k,v in payload['nodes'].items()};edges=[];xy={};blocked=[]
    incident_roads=collections.defaultdict(set)
    for wid,w in ways.items():
        if w.get('tags',{}).get('highway') in MOTOR:
            for n in w.get('nodes',[]):incident_roads[n].add(wid)
    def add(e):
        assert e['u']!=e['v'];edges.append(e)
        xy.setdefault(e['u'],e['xy'][0]);xy.setdefault(e['v'],e['xy'][-1])
    admitted=[r for r in payload['native_admission'] if r['status']=='KEEP_NATIVE']
    for r in admitted:
        wid=int(r['source_id'].split('/')[1]);t=ways[wid].get('tags',{});motor=t.get('highway') in MOTOR
        if variant!='R0' and motor:continue
        a,b=r['source_node_ids'];hyp=r['evidence']=='SHARED_STREET_ASSUMPTION';length=distance(*r['xy'])
        add({'edge_id':f"{variant}:native:{r['source_id']}:{r['segment_index']}",'u':native_id(a,t),'v':native_id(b,t),'xy':r['xy'],'layer':'road_axis' if motor else 'crossing' if crossing(t) else 'native','evidence':r['evidence'],'source_id':r['source_id'],'source_node_ids':[a,b],'side':None,'directions':r.get('directions',[1,-1]),'geometry_status':'SOURCE_GEOMETRY','hypothesis':hyp,'cost_f0':length,'cost_f1':length*(2 if hyp else 1),'length_basis':'SOURCE_LINE_LENGTH_M;road_axis_is_not_sidewalk','tags':t})
    if variant!='R0':
        # No near-neighbor native joins: ambiguous interfaces remain missing.
        # Each side stays scoped to its original road+level; no all-way junction merge.
        seen_crossings=set()
        for r in admitted:
            wid=int(r['source_id'].split('/')[1]);t=ways[wid].get('tags',{});road=r['source_id']
            if t.get('highway') not in MOTOR or denied(t) or nonground(t):continue
            positive=sides(t);missing=variant=='R2' and t.get('highway') in ORDINARY and axis_missing(t)
            for side in ('left','right'):
                if separate(t,side):continue
                if side not in positive and not missing:continue
                # An independently mapped sidewalk marked 'separate' is never duplicated.
                a,b=r['source_node_ids'];display=shifted(*r['xy'],side);length=distance(*r['xy']);hyp=side not in positive
                add({'edge_id':f"{variant}:side:{road}:{side}:{r['segment_index']}",'u':side_id(road,side,a,t),'v':side_id(road,side,b,t),'xy':display,'layer':'hypothesis' if hyp else 'tag_derived','evidence':'CONDITIONAL_MISSING_SIDE_TAG_ORDINARY_GROUND_ROAD' if hyp else 'SOURCE_SIDEWALK_SIDE_TAG_TOPOLOGY_ONLY','source_id':road,'source_node_ids':[a,b],'side':side,'directions':r.get('directions',[1,-1]),'geometry_status':'SCHEMATIC','hypothesis':hyp,'cost_f0':length,'cost_f1':length*(2 if hyp else 1),'length_basis':'SOURCE_AXIS_REFERENCE_LENGTH_COST_PROXY_NOT_PHYSICAL_SIDEWALK_M','tags':t})
                for n,p in zip((a,b),display):
                    # Preserve explicit source crossing-node semantics. Do not infer a crossing at arbitrary intersections.
                    nt=nodes.get(n,{}).get('tags',{});ck=(road,side,n)
                    if not crossing(nt) or denied(nt) or nonground(nt) or ck in seen_crossings:continue
                    # A crossing node shared by multiple road identities does not tell
                    # us which side/channel pairing is lawful. Preserve UNKNOWN rather
                    # than merging every road's sides into the same junction node.
                    if incident_roads[n]!={wid}:continue
                    if nt.get('crossing') in {'no','uncontrolled_no'}:continue
                    seen_crossings.add(ck)
                    center=r['xy'][0 if n==a else 1]
                    add({'edge_id':f'{variant}:crossing:{road}:{side}:node/{n}','u':side_id(road,side,n,t),'v':native_id(n,t),'xy':[p,center],'layer':'crossing','evidence':'SOURCE_CROSSING_NODE_TOPOLOGY_ONLY','source_id':f'node/{n}','road_source_id':road,'source_node_ids':[n,n],'side':side,'directions':[1,-1],'geometry_status':'SCHEMATIC','hypothesis':False,'cost_f0':1.,'cost_f1':1.,'length_basis':'ONE_TOPOLOGICAL_INTERFACE_UNIT_NOT_CROSSING_METERS','tags':nt})
    return {'edges':edges,'nodes':xy,'unresolved_same_side_junction_policy':'No inferred native-to-side or side-to-other-road joins without source side binding; possible underconnection retained','full_face_parent':'FROZEN_NOT_REBUILT_OR_CHANGED;this local side probe does not invoke parent wholebusiness solver'}

def solve(g,start,end):
    adjacency=collections.defaultdict(list)
    for e in g['edges']:
        if 1 in e['directions']:adjacency[e['u']].append((e['v'],e))
        if -1 in e['directions']:adjacency[e['v']].append((e['u'],e))
    if start not in g['nodes'] or end not in g['nodes']:return {'status':'ENDPOINT_UNAVAILABLE','solver_invoked':False,'edge_ids':[],'node_path':[]}
    heap=[(0.,start)];best={start:0.};parent={};popped=0
    while heap:
        cost,u=heapq.heappop(heap)
        if cost!=best[u]:continue
        popped+=1
        for v,e in adjacency[u]:
            vcost=cost+e['cost_f1']
            if vcost<best.get(v,float('inf')):best[v]=vcost;parent[v]=(u,e);heapq.heappush(heap,(vcost,v))
    if end in best:
        u=end;ns=[u];es=[]
        while u!=start:u,e=parent[u];es.append(e);ns.append(u)
        es.reverse();ns.reverse()
        return {'status':'ZERO_LENGTH_COLLAPSED_SIDE_ALIAS' if start==end else 'CONNECTED','solver_invoked':True,'edge_ids':[e['edge_id']for e in es],'node_path':ns,'cost_f1_proxy':best[end],'cost_f0_proxy':sum(e['cost_f0']for e in es),'source_line_reference_length_m':sum(e['cost_f0']for e in es if e['geometry_status']=='SOURCE_GEOMETRY'),'hypothesis_edges':sum(e['hypothesis']for e in es),'schematic_edges':sum(e['geometry_status']=='SCHEMATIC'for e in es),'physical_route_length_m':None if start==end or any(e['geometry_status']=='SCHEMATIC' or e['layer']=='road_axis'for e in es) else sum(e['cost_f0']for e in es),'popped_nodes':popped,'distance_labels':best}
    return {'status':'DISCONNECTED','solver_invoked':True,'edge_ids':[],'node_path':[],'popped_nodes':popped,'distance_labels':best}

def binding(q,p,variant):
    w=p['ways'][q['road_id'].split('/')[1]];t=w.get('tags',{})
    if q['kind'].startswith('NATIVE') or variant=='R0': return {'start':native_id(q['start_node'],t),'end':native_id(q['end_node'],t),'meaning':'R0 collapses side identity to axis node' if not q['kind'].startswith('NATIVE') and variant=='R0' else 'exact native source nodes'}
    return {'start':side_id(q['road_id'],q['start_side'],q['start_node'],t),'end':side_id(q['road_id'],q['end_side'],q['end_node'],t),'meaning':'same source station and logical road side;physical position unknown'}

def synthetic():
    """Unit invariants, not formal source routes. Actual traversals recorded."""
    results=[];calls=0
    def fixture(t,nt=None):
        return {'ways':{'1':{'id':1,'type':'way','nodes':[1,2,3],'tags':t}},'nodes':{str(n):{'id':n,'type':'node','tags':nt or {}}for n in (1,2,3)},'native_admission':[{'source_id':'way/1','segment_index':i,'source_node_ids':[i+1,i+2],'xy':[[i*10,0],[(i+1)*10,0]],'directions':[1,-1],'evidence':'SHARED_STREET_ASSUMPTION','status':'KEEP_NATIVE'}for i in (0,1)]}
    p=fixture({'highway':'residential'});g=graph(p,'R2');t=p['ways']['1']['tags'];a=side_id('way/1','left',1,t);b=side_id('way/1','right',1,t)
    r=solve(g,a,b);calls+=1;results.append({'name':'sides_do_not_cross_without_source_crossing','pass':r['status']=='DISCONNECTED','result':r})
    p=fixture({'highway':'residential'},{'highway':'crossing','crossing':'marked'});g=graph(p,'R2');r=solve(g,a,b);calls+=1;results.append({'name':'explicit_source_crossing_connects_corresponding_road_sides_only','pass':r['status']=='CONNECTED' and all(e['source_id'] in {'node/1','way/1','node/2','node/3'} for e in g['edges']),'result':r})
    for name,t in [('explicit_restriction',{'highway':'residential','foot':'no'}),('crosslevel',{'highway':'residential','layer':'1'}),('no_sidewalk_tag_is_not_missing',{'highway':'residential','sidewalk':'no'})]:
        results.append({'name':name,'pass':not graph(fixture(t),'R2')['edges']})
    p=fixture({'highway':'footway','footway':'sidewalk'});g=graph(p,'R2');results.append({'name':'native_sidewalk_not_duplicated','pass':len(g['edges'])==2 and all(e['layer']=='native'for e in g['edges'])})
    axy=[[0,0],[10,0]];orig=shifted(*axy,'left');rev=shifted(*reversed(axy),'right');results.append({'name':'way_reverse_left_becomes_right_same_physical_schematic_side','pass':orig==list(reversed(rev)) and sides({'sidewalk':'left'})==['left'] and sides({'sidewalk':'right'})==['right']})
    g=graph(fixture({'highway':'residential'}),'R2');degree=collections.Counter(n for e in g['edges']for n in (e['u'],e['v']));results.append({'name':'no_forced_ring_at_open_clip_ends','pass':sorted(degree.values())==[1,1,1,1,2,2]})
    results.append({'name':'F1_hypothesis_cost_not_relabelled','pass':all(e['hypothesis'] and e['cost_f1']==2*e['cost_f0']for e in g['edges'])})
    p=fixture({'highway':'residential'},{'highway':'crossing','crossing':'marked'})
    p['ways']['2']={'id':2,'type':'way','nodes':[1,4],'tags':{'highway':'residential'}}
    p['nodes']['4']={'id':4,'type':'node','tags':{}}
    p['native_admission'].append({'source_id':'way/2','segment_index':0,'source_node_ids':[1,4],'xy':[[0,0],[0,10]],'directions':[1,-1],'evidence':'SHARED_STREET_ASSUMPTION','status':'KEEP_NATIVE'})
    g=graph(p,'R2')
    results.append({'name':'multi_road_shared_crossing_node_does_not_merge_all_sides','pass':not any(e['layer']=='crossing' and e['source_id']=='node/1'for e in g['edges'])})
    write(ROOT/'results/synthetic_tests.json',{'at':now(),'cases':results,'pass_count':sum(r['pass']for r in results),'cases_count':len(results),'synthetic_shortest_path_calls':calls,'formal_queries':0})
    if not all(r['pass']for r in results):raise RuntimeError('SYNTHETIC_FAILURE')
    return calls

def run():
    lock=read(ROOT/'audit/window_lock.json')
    if (ROOT/'audit/experiment_registry.jsonl').exists():raise RuntimeError('REGISTRY_EXISTS_NO_SILENT_RERUN')
    syntheticcalls=synthetic();windows=[];summary=[];formal=0;solver=0
    for row in lock['windows']:
        p=read(ROOT/row['input_path']);assert sha(ROOT/row['input_path'])==row['input_sha256']
        graphs={v:graph(p,v)for v in ('R0','R1','R2')};qs=[]
        for q in p['queries']:
            out={**q,'description':q['kind'],'bindings':{},'results':{}}
            for variant,g in graphs.items():
                start=time.perf_counter();bind=binding(q,p,variant);res=solve(g,bind['start'],bind['end']);formal+=1;solver+=res['solver_invoked']
                record={'formal_attempt':formal,'query_id':q['query_id'],'window_id':p['window_id'],'variant':variant,'input_sha256':row['input_sha256'],'graph_sha256':hashlib.sha256(json.dumps(g,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'code_sha256':sha(__file__),'at':now(),'elapsed_s':time.perf_counter()-start,'binding':bind,'result':res,'status_scope':'TOPOLOGY_ONLY_SCHEMATIC' if not q['kind'].startswith('NATIVE') else 'EXACT_NATIVE_GEOMETRY_CONTROL'}
                with (ROOT/'audit/experiment_registry.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
                out['bindings'][variant]=bind;out['results'][variant]=res
                summary.append({'query_id':q['query_id'],'window_id':p['window_id'],'variant':variant,'status':res['status'],'solver_invoked':res['solver_invoked'],'hypothesis_edges':res.get('hypothesis_edges',0),'schematic_edges':res.get('schematic_edges',0),'cost_f1_proxy':res.get('cost_f1_proxy'),'physical_route_length_m':res.get('physical_route_length_m'),'scope':record['status_scope']})
            qs.append(out)
        maprow={k:p[k]for k in ('window_id','label','scene_id','bounds_xy','source_timestamp','source_sha256','source_features')};maprow.update({'variants':graphs,'queries':qs,'nodes':{n:x for g in graphs.values()for n,x in g['nodes'].items()},'selected_road_id':p['selected_road_id']});windows.append(maprow)
        for variant,g in graphs.items():write(ROOT/'results/graphs'/f"{p['window_id']}_{variant}.json",g)
    with (ROOT/'results/query_results.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    write(ROOT/'maps/trial_map_data.json',{'crs':'EPSG:32651','display_offset_m':OFFSET,'offset_status':'SCHEMATIC_NOT_PHYSICAL_WIDTH','windows':windows,'policy':'Side graphs are a topology prototype. No source-supported cross-road connection is invented. Native objects preserved; unknown side junction interfaces deliberately unjoined. No physical clearance claim on schematic paths.'})
    write(ROOT/'results/trial_summary.json',{'completed_at':now(),'formal_attempts':formal,'actual_formal_dijkstra_calls':solver,'formal_endpoint_unavailable_without_search':formal-solver,'repair_retests':0,'synthetic_shortest_path_calls':syntheticcalls,'native_exact_geometry_query_count':6,'topology_only_query_count':12,'by_variant':{v:dict(collections.Counter(r['status']for r in summary if r['variant']==v))for v in ('R0','R1','R2')},'costs_are_topology_proxies_except_native_controls':True,'new_full_business_routes':0,'no_default_method_upgrade':True,'no_new_data_requests':True})
    print(json.dumps(read(ROOT/'results/trial_summary.json'),ensure_ascii=False,indent=2))

def verify_graphs():
    """Clean-package graph reconstruction only; does NOT issue route requests."""
    lock=read(ROOT/'audit/window_lock.json');checks=[]
    for row in lock['windows']:
        p=read(ROOT/row['input_path']);assert sha(ROOT/row['input_path'])==row['input_sha256']
        for v in ('R0','R1','R2'):
            rebuilt=graph(p,v);saved=read(ROOT/'results/graphs'/f"{row['window_id']}_{v}.json")
            checks.append({'window_id':row['window_id'],'variant':v,'equal':rebuilt==saved})
    result={'checked_at':now(),'graph_checks':checks,'all_equal':all(r['equal']for r in checks),'formal_route_requests':0,'new_shortest_path_calls':0,'scope':'Reconstructs nine graph objects from packaged source-derived local inputs; route certificates require independent checker. No global historical dependency or network.'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['all_equal']:raise SystemExit(2)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['prepare','run','synthetic','verify-graphs']);args=ap.parse_args()
    {'prepare':prepare,'run':run,'synthetic':synthetic,'verify-graphs':verify_graphs}[args.command]()
