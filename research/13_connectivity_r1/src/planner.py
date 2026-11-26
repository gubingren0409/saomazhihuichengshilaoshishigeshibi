"""Request-time known-door solver. No stored-route lookup or route-answer cache."""
from __future__ import annotations
import json, math, threading, time, uuid
from datetime import datetime
from pathlib import Path
from hashlib import sha256
import networkx as nx
import gc,gzip
from shapely.geometry import Point, LineString, GeometryCollection, mapping, shape
from src.region import Surface, STATES, NATIVE, INFERRED, UNKNOWN, RESTRICTED, context_layers, union, digest, non_ground, access_conflict
from src.free_surface import build_free_surface
from src.free_routing import build_graph, checked_native, bind, graph_record
from src.region_routing import bidirectional
from src.common_constraints import build_contract, parsed_contract, edge_conflicts

ROOT=Path(__file__).resolve().parents[1]
LOCK=threading.RLock()
CACHE={}
SOURCE_CACHE={}
PREPARED_INDEX={}
AREA_CACHE={}
FACE_CACHE={}
CONNECTIVITY_CACHE={}
COMPLETE_FACE_CACHE={}
PREPROCESSING_GROUP=None
CONNECTIVITY_MODES=('FROZEN_FULL_FACE','SOURCE_COMPLETE','EXACT_STITCH','CONDITIONAL_SEAMS')

def _activate_preprocessing_group(scene_id,door_id):
    """Bound heavy overlays to one source/door namespace, without mutating graphs.

    A concurrent route retains its prepared reference; only cache ownership is
    released. F0/F1 and all four modes in the same namespace keep identical
    reusable unweighted graphs. No answer cache exists.
    """
    global PREPROCESSING_GROUP
    group=(scene_id,door_id)
    with LOCK:
        if group==PREPROCESSING_GROUP:return
        for cache in (CACHE,PREPARED_INDEX,AREA_CACHE,CONNECTIVITY_CACHE):cache.clear()
        if PREPROCESSING_GROUP is not None and scene_id!=PREPROCESSING_GROUP[0]:
            FACE_CACHE.clear();COMPLETE_FACE_CACHE.clear()
        PREPROCESSING_GROUP=group
        gc.collect()

def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    temp.replace(path)

def code_identity():
    return digest({p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for folder in ('src','config') for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')})

IMPORTED_CODE_SHA=code_identity()

def graph_sha(graph):
    """Same canonical bytes as digest(graph_record), streamed to bound memory."""
    h=sha256();h.update(b'{"edges":[')
    for i,(u,v,r) in enumerate(sorted(graph.edges(data=True))):
        if i:h.update(b',')
        clean=lambda option:[{k:v for k,v in s.items()if k!='cost_m'}for s in option]
        obj={'u':u,'v':v,'segments':clean(r['segments'])}
        if r.get('routing_alternatives'):obj['routing_alternatives']=[clean(a)for a in r['routing_alternatives']]
        h.update(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    h.update(b'],"nodes":[')
    for i,(n,r) in enumerate(sorted(graph.nodes(data=True))):
        if i:h.update(b',')
        h.update(json.dumps({'id':n,**r},sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    h.update(b']}');return h.hexdigest()

def compose_prepared(prepared):
    graph=nx.compose(prepared['source'],prepared['region'].internal)
    extras=prepared.get('face_overlays',[prepared.get('face_overlay')])
    for extra in extras:
        if extra is None:continue
        for n,r in extra.nodes(data=True):
            if n in graph and math.dist(graph.nodes[n]['xy'],r['xy'])>1e-6:raise ValueError('FACE_PORTAL_COORDINATE_DRIFT')
            if n not in graph:graph.add_node(n,**r)
        for u,v,r in extra.edges(data=True):
            rows=[graph[u][v],r]if graph.has_edge(u,v)else[r]
            options=[];seen=set()
            for row in rows:
                for option in row.get('routing_alternatives',[row['segments']]):
                    signature=digest([{k:v for k,v in s.items()if k!='cost_m'}for s in option])
                    if signature not in seen:options.append(option);seen.add(signature)
            primary=min(options,key=lambda o:_option_key(o,1))
            graph.add_edge(u,v,**{**r,'segments':primary,'cost':sum(s['length_m']for s in primary),'routing_alternatives':options})
    return graph


def _checked_source_graph(data,cfg,full_guards,full_parsed,progress):
    source_identity={k:data['source_info'][k]for k in('source_sha256','mapped_edges_sha256')}
    source_key=digest({'source':source_identity,'full_guard':digest(full_guards),'code':code_identity(),'cfg':cfg})
    if source_key in SOURCE_CACHE:source_graph,rejected=SOURCE_CACHE[source_key]
    else:
        source_graph=nx.compose(nx.DiGraph(),data['combined_source_graph']);rejected=[];geometry_checks={}
        arcs=list(source_graph.edges(data=True))
        progress('CHECK_FULL_SOURCE_GRAPH',arcs_total=len(arcs),arcs_checked=0)
        for index,(u,v,r) in enumerate(arcs):
            valid_options=[];reasons=[]
            for s in [r['segments'][0],*r.get('alternative_segments',[])]:
                coords_key=tuple(tuple(p) for p in s['xy'])
                if coords_key[::-1]<coords_key:coords_key=coords_key[::-1]
                check_key=(coords_key,s['layer'],s.get('source_id'),json.dumps(s.get('tags',{}),sort_keys=True))
                if check_key not in geometry_checks:
                    geometry_checks[check_key]=edge_conflicts(LineString(s['xy']),full_parsed,native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
                found=geometry_checks[check_key]
                if found:reasons.extend(found)
                else:valid_options.append(s)
            if valid_options:
                chosen=min(valid_options,key=lambda s:(s['length_m'],s['layer']!='native',s.get('source_id',''),s.get('edge_id','')))
                source_graph[u][v].update(segments=[chosen],cost=chosen['length_m'],alternative_segments=valid_options)
            else:
                rejected.append({'u':u,'v':v,'reasons':sorted(set(reasons))});source_graph.remove_edge(u,v)
            if (index+1)%10000==0:progress('CHECK_FULL_SOURCE_GRAPH',arcs_total=len(arcs),arcs_checked=index+1)
        if len(SOURCE_CACHE)>=2:SOURCE_CACHE.pop(next(iter(SOURCE_CACHE)))
        SOURCE_CACHE[source_key]=(source_graph,rejected)
    return source_graph,rejected

def _prepare(scene_id,door_id):
    from src.scene_data import load_scene
    tick=time.perf_counter()
    manifest_path=ROOT/'data/scene_manifest.json'
    manifest_bytes=manifest_path.read_bytes();manifest=json.loads(manifest_bytes)
    current_code=code_identity()
    if current_code!=IMPORTED_CODE_SHA:raise ValueError('SERVICE_CODE_CHANGED_RESTART_REQUIRED')
    scene_row=next(r for r in manifest['scenes'] if r['scene_id']==scene_id)
    for path_field,hash_field in [('source_path','source_sha256'),('mapped_edges_path','mapped_edges_sha256')]:
        if sha256((ROOT/scene_row[path_field]).read_bytes()).hexdigest()!=scene_row[hash_field]:raise ValueError('PREPROCESSING_SOURCE_BINDING_CHANGED')
    index_key=(scene_id,door_id,current_code,sha256(manifest_bytes).hexdigest())
    if index_key in PREPARED_INDEX:return CACHE[PREPARED_INDEX[index_key]],True,time.perf_counter()-tick
    data=load_scene(scene_id,door_id)
    cfg={**json.loads((ROOT/'config/frozen_region.json').read_text(encoding='utf-8')),
         'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
    obs=data['observed'];guards=data['guards']
    source_identity={k:data['source_info'][k] for k in ('source_sha256','mapped_edges_sha256')}
    key=digest({'namespace':'APP_NATURAL_QUERY','source':source_identity,'observation':digest(obs),'guards':digest(guards),'cfg':cfg,'code':code_identity(),'door':door_id,'domain':obs['domain']})
    if key in CACHE:return CACHE[key],True,time.perf_counter()-tick
    progress_path=ROOT/'runs/progress'/f'{scene_id}-{door_id.replace("/","-")}.json'
    def progress(stage,**extra):put(progress_path,{'stage':stage,'elapsed_s':time.perf_counter()-tick,'scene_id':scene_id,'door_id':door_id,**extra})
    progress('BUILD_LOCAL_SURFACE')
    domain=Point(obs['domain']['anchor_xy']).buffer(30,quad_segs=32)
    common=build_contract(obs,guards,cfg,domain=mapping(domain))
    ctx=context_layers(obs,domain,cfg)
    native=union(r['g'] for r in ctx['native']).intersection(domain)
    empty=GeometryCollection()
    base_surface=Surface(domain,[],{NATIVE:native,INFERRED:empty,RESTRICTED:empty,UNKNOWN:domain.difference(native)},ctx,'APP_NATIVE_ONLY',{}, {},1)
    # F0 has no positive-evidence gate. F1 shares this exact region and graph.
    surface=build_free_surface(base_surface,common,default=True)
    local,local_rejected=checked_native(obs,common)
    region=build_graph(surface,local,cfg,common,'F0')
    full_obs=data.get('full_observed',obs);full_guards=data.get('full_guards',guards)
    coverage=shape(full_guards['coverage_geometry'])
    full_common=build_contract(full_obs,full_guards,cfg,domain=mapping(coverage))
    full_parsed=parsed_contract(full_common)
    source_graph,rejected=_checked_source_graph(data,cfg,full_guards,full_parsed,progress)
    graph=nx.compose(source_graph,region.internal)
    unweighted_sha=graph_sha(graph)
    # Keep one shared checked source graph, rather than a full copied graph per
    # door. The APP recreates its private topology for each real search.
    metadata={k:v for k,v in data.items()if k not in {'combined_source_graph','native_graph','native_ledger','map_layers','native_nodes'}}
    result=dict(data=metadata,cfg=cfg,common=common,parsed=parsed_contract(common),full_common=full_common,
                full_parsed=full_parsed,source=source_graph,local=local,region=region,
                surface=surface,cache_key=key,graph_sha=unweighted_sha,
                rejected=rejected,local_rejected=local_rejected,code_sha=code_identity(),prepare_s=time.perf_counter()-tick)
    CACHE[key]=result
    PREPARED_INDEX[index_key]=key
    progress('PREPROCESSING_COMPLETE',nodes=len(graph),arcs=graph.number_of_edges(),source_rejected_arcs=len(rejected))
    # Each cold build is an execution record, rather than a replaceable cache
    # answer. A later process rebuilding this key must preserve earlier receipts.
    prep_id='PREP-'+uuid.uuid4().hex
    put(ROOT/'runs/preprocessing'/f'{key}-{prep_id}.json',{'namespace':'APP_NATURAL_QUERY','preprocessing_run_id':prep_id,'cache_key':key,'code_sha256':result['code_sha'],
        'source':data['source_info'],'observed_sha256':digest(obs),'guard_sha256':digest(guards),'cfg':cfg,
        'surface_sha256':surface.sha256,'graph_sha256':unweighted_sha,'prepare_s':result['prepare_s'],
        'route_answers_stored':False,'nodes':len(graph),'arcs':graph.number_of_edges()})
    from src.scene_data import _prepared_scene
    _prepared_scene.cache_clear()
    return result,False,time.perf_counter()-tick

def _prepare_network(scene_id):
    """Door-free mechanism graph: same source constraints, no invented D30 area."""
    from src.scene_data import load_scene,_prepared_scene
    from types import SimpleNamespace
    tick=time.perf_counter();current=code_identity()
    if current!=IMPORTED_CODE_SHA:raise ValueError('SERVICE_CODE_CHANGED_RESTART_REQUIRED')
    manifest_bytes=(ROOT/'data/scene_manifest.json').read_bytes();idx=('MECHANISM_NO_DOOR',scene_id,current,sha256(manifest_bytes).hexdigest())
    if idx in PREPARED_INDEX:return CACHE[PREPARED_INDEX[idx]],True,time.perf_counter()-tick
    data=load_scene(scene_id)
    cfg={**json.loads((ROOT/'config/frozen_region.json').read_text(encoding='utf-8')),'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
    guards=data['full_guards'];obs=data['full_observed'];coverage=shape(guards['coverage_geometry'])
    common=build_contract(obs,guards,cfg,domain=mapping(coverage));parsed=parsed_contract(common)
    key=digest({'namespace':'MECHANISM_NO_DOOR_NO_D30','scene':scene_id,'source':data['source_info']['source_sha256'],'code':current,'common':common['sha256']})
    def progress(stage,**extra):put(ROOT/'runs/progress'/f'{scene_id}-MECHANISM.json',{'stage':stage,'elapsed_s':time.perf_counter()-tick,**extra})
    source,rejected=_checked_source_graph(data,cfg,guards,parsed,progress)
    empty=GeometryCollection();region=SimpleNamespace(internal=nx.DiGraph())
    surface=SimpleNamespace(sha256=digest({'namespace':'NO_DOOR_NO_LOCAL_FREE_DOMAIN','scene':scene_id}),domain=empty,masks={name:empty for name in STATES})
    metadata={k:v for k,v in data.items()if k not in {'combined_source_graph','native_graph','native_ledger','map_layers','native_nodes'}}
    result=dict(data=metadata,cfg=cfg,common=common,parsed=parsed,full_common=common,full_parsed=parsed,source=source,
        region=region,local=nx.DiGraph(),surface=surface,cache_key=key,graph_sha=graph_sha(source),code_sha=current,rejected=rejected,local_rejected=[],prepare_s=time.perf_counter()-tick,
        task_role='LOCAL_MECHANISM_NO_DOOR_OR_ENTRANCE_ASSERTION')
    CACHE[key]=result;PREPARED_INDEX[idx]=key;_prepared_scene.cache_clear()
    put(ROOT/'runs/preprocessing'/f'{key}-PREP-{uuid.uuid4().hex}.json',{'namespace':'MECHANISM_NO_DOOR_NO_D30','code_sha256':current,'source':data['source_info'],
        'cache_key':key,'common_sha256':common['sha256'],'local_free_area_m2':0,'graph_sha256':result['graph_sha'],'route_answers_stored':False,'elapsed_s':result['prepare_s']})
    return result,False,time.perf_counter()-tick

def prepare_area(scene_id,door_id,mode):
    base,hit,seconds=_prepare_network(scene_id)if door_id is None else _prepare(scene_id,door_id)
    if mode=='EDGE_BAND':return {**base,'area_mode':mode,'faces':[],'face_evidence':{'mode':'FROZEN_3M_EDGE_BAND'},'face_overlay':None},hit,seconds
    population_sha=sha256((ROOT/'data/face_selection_lock.json').read_bytes()).hexdigest()
    cache_key=(base['cache_key'],mode,population_sha)
    if cache_key in AREA_CACHE:return AREA_CACHE[cache_key],True,seconds
    from src.face_geometry import compile_faces
    from src.face_visibility import build_overlay
    started=time.perf_counter()
    face_key=(scene_id,base['full_common']['sha256'],base['code_sha'],population_sha)
    if face_key not in FACE_CACHE:FACE_CACHE[face_key]=compile_faces(base['data'],base['full_common'],base['cfg'])
    faces=FACE_CACHE[face_key]
    overlay,evidence=build_overlay(faces,base['source'],base['region'],base['full_parsed'],base['cfg'])
    prepared={**base,'area_mode':mode,'faces':faces,'face_overlay':overlay,'face_evidence':evidence}
    graph=compose_prepared(prepared);prepared['graph_sha']=graph_sha(graph)
    key=digest({'namespace':'APP_NATURAL_QUERY','area_mode':mode,'base_key':base['cache_key'],
                'code':base['code_sha'],'population_sha256':population_sha,'faces':[(f['source_id'],f['geometry_hash'])for f in faces],
                'graph_sha256':prepared['graph_sha']})
    prepared['cache_key']=key;prepared['area_prepare_s']=time.perf_counter()-started
    AREA_CACHE[cache_key]=prepared
    prep_id='PREP-'+uuid.uuid4().hex
    graph_path=ROOT/'data/derived_graphs'/f'{key}-{prep_id}.jsonl.gz'
    graph_path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(graph_path,'wt',encoding='utf-8')as stream:
        for n,r in overlay.nodes(data=True):stream.write(json.dumps({'kind':'node','id':n,**r},ensure_ascii=False,separators=(',',':'))+'\n')
        for u,v,r in overlay.edges(data=True):stream.write(json.dumps({'kind':'arc','u':u,'v':v,**r},ensure_ascii=False,separators=(',',':'))+'\n')
    put(ROOT/'runs/preprocessing'/f'{key}-{prep_id}.json',{'namespace':'APP_NATURAL_QUERY','area_mode':mode,
        'cache_key':key,'base_cache_key':base['cache_key'],'code_sha256':base['code_sha'],'face_evidence':evidence,
        'geometry_hashes':[f['geometry_hash']for f in faces],'graph_sha256':prepared['graph_sha'],
        'area_prepare_s':prepared['area_prepare_s'],'route_answers_stored':False,
        'derived_overlay_path':graph_path.relative_to(ROOT).as_posix(),'derived_overlay_sha256':sha256(graph_path.read_bytes()).hexdigest()})
    return prepared,False,seconds+time.perf_counter()-started

def prepare_connectivity(scene_id,door_id,mode,seam_max_m=2.0):
    """Shared frozen source/face graphs plus versioned, incremental overlays."""
    if mode not in CONNECTIVITY_MODES:raise ValueError('INVALID_CONNECTIVITY_MODE')
    if float(seam_max_m)not in(.5,2.,5.):raise ValueError('SEAM_THRESHOLD_NOT_IN_APPROVED_CONFIGS')
    _activate_preprocessing_group(scene_id,door_id)
    if mode=='FROZEN_FULL_FACE':
        prepared,hit,seconds=prepare_area(scene_id,door_id,'FULL_FACE')
        return {**prepared,'connectivity_mode':mode,'connectivity_evidence':{'mode':mode,'parent_mode':None,'conditional_links':[],'interfaces':[]}},hit,seconds
    base,hit,seconds=_prepare_network(scene_id)if door_id is None else _prepare(scene_id,door_id)
    selection_path=ROOT/'data/connectivity/source_selection_lock.json'
    selection_bytes=selection_path.read_bytes();selection=json.loads(selection_bytes)
    selected=next(s for s in selection['scenes']if s['scene_id']==scene_id)
    if selected['source_sha256']!=base['data']['source_info']['source_sha256']:raise ValueError('SOURCE_COMPLETE_LOCK_SOURCE_MISMATCH')
    selection_sha=sha256(selection_bytes).hexdigest()
    threshold=float(seam_max_m)if mode=='CONDITIONAL_SEAMS'else None
    cache_key=(base['cache_key'],mode,selection_sha,threshold)
    if cache_key in CONNECTIVITY_CACHE:return CONNECTIVITY_CACHE[cache_key],True,seconds
    started=time.perf_counter()
    if mode=='SOURCE_COMPLETE':
        from src.face_geometry import compile_faces
        from src.face_visibility import build_overlay
        face_key=(scene_id,base['full_common']['sha256'],base['code_sha'],selection_sha)
        if face_key not in COMPLETE_FACE_CACHE:
            COMPLETE_FACE_CACHE[face_key]=compile_faces(base['data'],base['full_common'],base['cfg'],selected_area_ids=selected['area_ids'])
        faces=COMPLETE_FACE_CACHE[face_key]
        overlay,face_evidence=build_overlay(faces,base['source'],base['region'],base['full_parsed'],base['cfg'])
        evidence={**face_evidence,'mode':mode,'parent_mode':'FROZEN_FULL_FACE','source_selection_sha256':selection_sha,
            'old_area_ids':selected['old_area_ids'],'added_area_ids':selected['added_area_ids'],'interfaces':[],'conditional_links':[],'delta_only':False,
            'full_common_sha256':base['full_parsed']['contract']['sha256'],
            'visibility_code_sha256':sha256((ROOT/'src/face_visibility.py').read_bytes()).hexdigest()}
        prepared={**base,'area_mode':'FULL_FACE','faces':faces,'face_overlay':None,'face_overlays':[overlay],'face_evidence':face_evidence,
            'connectivity_mode':mode,'connectivity_evidence':evidence}
        parent_key=base['cache_key']
    else:
        parent_mode='SOURCE_COMPLETE'if mode=='EXACT_STITCH'else'EXACT_STITCH'
        parent,parent_hit,parent_s=prepare_connectivity(scene_id,door_id,parent_mode,seam_max_m)
        from src.connectivity import build_connectivity_overlay
        cfg={**base['cfg'],'seam_max_m':float(seam_max_m),'seam_probe_m':10.}
        overlay,evidence=build_connectivity_overlay(parent['faces'],base['source'],base['region'],base['full_parsed'],cfg,
            mode=mode,base_overlay=parent['face_overlays'],base_evidence=parent.get('connectivity_evidence',{}))
        if not evidence.get('delta_only'):raise ValueError('CONNECTIVITY_OVERLAY_MUST_BE_INCREMENTAL')
        prepared={**parent,'face_overlays':[*parent['face_overlays'],overlay],'connectivity_mode':mode,'connectivity_evidence':evidence}
        parent_key=parent['cache_key']
    graph=compose_prepared(prepared);graph_digest=graph_sha(graph)
    key=digest({'namespace':'APP_CONNECTIVITY','base':base['cache_key'],'parent':parent_key,'mode':mode,'seam_max_m':threshold,
        'selection_sha256':selection_sha,'graph_sha256':graph_digest,'code':base['code_sha']})
    prepared.update(cache_key=key,graph_sha=graph_digest,connectivity_prepare_s=time.perf_counter()-started,seam_max_m=threshold)
    CONNECTIVITY_CACHE[cache_key]=prepared
    prep_id='PREP-'+uuid.uuid4().hex;graph_path=ROOT/'data/connectivity_graphs'/f'{key}-{prep_id}.jsonl.gz';graph_path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(graph_path,'wt',encoding='utf-8')as stream:
        for n,r in overlay.nodes(data=True):stream.write(json.dumps({'kind':'node','id':n,**r},ensure_ascii=False,separators=(',',':'))+'\n')
        for u,v,r in overlay.edges(data=True):stream.write(json.dumps({'kind':'arc','u':u,'v':v,**r},ensure_ascii=False,separators=(',',':'))+'\n')
    put(ROOT/'runs/preprocessing'/f'{key}-{prep_id}.json',{'namespace':'APP_CONNECTIVITY','mode':mode,'seam_max_m':threshold,'cache_key':key,'parent_cache_key':parent_key,
        'source_selection_sha256':selection_sha,'graph_sha256':graph_digest,'code_sha256':base['code_sha'],'local_surface_sha256':base['surface'].sha256,
        'graph_delta_only':mode!='SOURCE_COMPLETE','stored_overlay':graph_path.relative_to(ROOT).as_posix(),'stored_overlay_sha256':sha256(graph_path.read_bytes()).hexdigest(),
        'connectivity_evidence':evidence,'elapsed_s':prepared['connectivity_prepare_s'],'route_answers_stored':False})
    del graph;gc.collect()
    return prepared,False,seconds+time.perf_counter()-started

def scene_list():
    from src.scene_data import list_scenes
    return list_scenes()

def scene_view(scene_id,door_id=None):
    from src.scene_data import load_scene
    data=load_scene(scene_id,door_id)
    result={k:data[k] for k in ('scene_id','name','doors','map_layers','starts','source_info') if k in data}
    result['coverage_geometry']=data['full_guards']['coverage_geometry']
    return result

def _option_key(segments,weight):
    assumed=sum(s['length_m']for s in segments if s['layer']in('inferred','assumed','unknown'))
    length=sum(s['length_m']for s in segments)
    return length+(weight-1)*assumed,assumed,length

def _winning_option(row,weight):
    return min(row.get('routing_alternatives',[row['segments']]),key=lambda o:_option_key(o,weight))

def _weighted_route(graph,a,b,weight):
    calls={'invoked':False}
    if a not in graph or b not in graph:return None,{'code':'UNBOUND_ENDPOINT','source_present':a in graph,'target_present':b in graph},calls
    def cost(u,v,row):
        return _option_key(_winning_option(row,weight),weight)[0]
    calls['invoked']=True;tick=time.perf_counter()
    try:nodes=nx.shortest_path(graph,a,b,weight=cost)
    except nx.NetworkXNoPath:
        reachable=nx.descendants(graph,a)|{a};target=graph.nodes[b]['xy']
        frontier=sorted(reachable,key=lambda n:(math.dist(graph.nodes[n]['xy'],target),str(n)))[:5]
        return None,{'code':'DISCONNECTED_GRAPH','reachable_nodes':len(reachable),'last_frontier':[{'id':n,'xy':graph.nodes[n]['xy'],'distance_to_door_m':math.dist(graph.nodes[n]['xy'],target)} for n in frontier]},dict(calls,elapsed_s=time.perf_counter()-tick)
    segments=[]
    for u,v in zip(nodes,nodes[1:]):
        for s in _winning_option(graph[u][v],weight):
            r={**s,'u':u,'v':v,'xy':[list(p) for p in s['xy']]}
            r['cost_m']=r['length_m']*(weight if r['layer'] in ('inferred','assumed','unknown') else 1)
            r['evidence_level']=('SOURCE_GEOMETRY' if r['layer']=='native' else 'DERIVED_WITHIN_MAPPED_WALKABLE_AREA' if r['layer']=='derived' else 'GEOMETRY_HYPOTHESIS')
            segments.append(r)
    return {'segments':segments,'path_nodes':len(nodes),'zero_length':len(nodes)==1},None,dict(calls,elapsed_s=time.perf_counter()-tick)

def plan(request):
    """Serial preparation; request-private topology and pure finite-cost views."""
    tick=time.perf_counter();run_id='RUN-'+datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:10]
    request_id=str(request.get('request_id') or uuid.uuid4().hex)
    result={'request_id':request_id,'run_id':run_id,'namespace':'APP_NATURAL_QUERY','timestamp':datetime.now().astimezone().isoformat(),
            'input':request,'route_answer_cache':{'enabled':False,'hit':False},'solver':{'invoked':False},'status':'INVALID_REQUEST',
            'constraints_scope':'ACQUIRED_FROZEN_MAP_NOT_FIELD_SURVEY','public_access':'UNKNOWN','source_crs':'WGS84','working_crs':'EPSG:32651'}
    def finish():
        if result.get('solver',{}).get('invoked') and code_identity()!=IMPORTED_CODE_SHA:
            result.update(status='INVALID_RESULT_VERSION_CHANGED',failure={'stage':'VERSION_GUARD','code':'LOADED_CODE_CHANGED_DURING_REQUEST_RESTART_REQUIRED'})
        result['elapsed_s']=time.perf_counter()-tick
        put(ROOT/'runs/app'/f'{run_id}.json',result)
        return result
    try:
        method=request.get('method','F1');purpose=request.get('purpose','APPROACH_OUTSIDE')
        area_mode=request.get('area_routing','FULL_FACE')
        connectivity_mode=request.get('connectivity_mode','FROZEN_FULL_FACE')
        seam_max_m=float(request.get('seam_max_m',2.0))
        result['area_routing']=area_mode
        result['connectivity_mode']=connectivity_mode
        if area_mode!='FULL_FACE':raise ValueError('CONNECTIVITY_COMPARISON_REQUIRES_FULL_FACE')
        if connectivity_mode not in CONNECTIVITY_MODES:raise ValueError('INVALID_CONNECTIVITY_MODE')
        if method not in ('F0','F1') or purpose not in ('APPROACH_OUTSIDE','ENTER_BUILDING'):raise ValueError('INVALID_METHOD_OR_PURPOSE')
        scene_id=str(request['scene_id']);door_id=str(request.get('door_id',''))
        catalog=scene_list();scenes=catalog.get('scenes',[]) if isinstance(catalog,dict) else catalog
        scene=next((s for s in scenes if s['scene_id']==scene_id),None)
        if scene is None:raise ValueError('UNKNOWN_SCENE')
        door=next((d for d in scene.get('doors',[]) if d['id']==door_id),None)
        if door is None:
            result.update(status='NO_ELIGIBLE_REGISTERED_ENTRANCE',failure={'stage':'DOOR_IDENTITY','code':'NO_ELIGIBLE_REGISTERED_ENTRANCE'})
            return finish()
        tags=door.get('tags',{})
        result['door']=door
        if purpose=='ENTER_BUILDING' and tags.get('entrance')=='exit':
            result.update(status='REJECTED_ENTRANCE_ROLE',failure={'stage':'DOOR_ROLE','code':'EXIT_NOT_AN_INBOUND_ENTRANCE','object_id':door_id})
            return finish()
        if purpose not in door.get('eligible_purposes',[]):
            result.update(status='REJECTED_ENTRANCE_ROLE',failure={'stage':'DOOR_ROLE','code':'PURPOSE_NOT_APPLICABLE_TO_REGISTERED_DOOR','object_id':door_id})
            return finish()
        if access_conflict(tags) or non_ground(tags):
            result.update(status='REJECTED_ENTRANCE_ROLE',failure={'stage':'DOOR_ROLE','code':'REGISTERED_DOOR_RESTRICTED_OR_NON_GROUND','object_id':door_id})
            return finish()
        with LOCK: prepared,hit,load_s=prepare_connectivity(scene_id,door_id,connectivity_mode,seam_max_m)
        result.update(preprocessing_cache={'key':prepared['cache_key'],'hit':hit,'load_or_prepare_s':load_s},
                      versions={'source':prepared['data']['source_info'],'code_sha256':prepared['code_sha'],'surface_sha256':prepared['surface'].sha256,'unweighted_graph_sha256':prepared['graph_sha']})
        graph=compose_prepared(prepared);source=prepared['source']
        start_id=request.get('start_id')
        if start_id not in source:
            result.update(status='INVALID_START',failure={'stage':'START_BINDING','code':'START_NOT_AN_EXISTING_ELIGIBLE_NETWORK_NODE','requested_start_id':start_id})
            return finish()
        start=source.nodes[start_id]
        adjacent=list(source.in_edges(start_id,data=True))+list(source.out_edges(start_id,data=True))
        eligible=not access_conflict(start.get('tags',{})) and not non_ground(start.get('tags',{})) and any(not non_ground(s.get('tags',{})) and not access_conflict(s.get('tags',{})) for _,_,r in adjacent for s in r['segments'])
        if not eligible:
            result.update(status='INVALID_START',failure={'stage':'START_BINDING','code':'START_NOT_GROUND_WALK_NODE'})
            return finish()
        raw_xy=request.get('start_xy',start['xy'])
        if len(raw_xy)!=2 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in raw_xy):raise ValueError('INVALID_START_COORDINATES')
        displacement=math.dist(raw_xy,start['xy'])
        if displacement>1e-6:
            result.update(status='INVALID_START',failure={'stage':'START_BINDING','code':'EXACT_NETWORK_NODE_COORDINATES_REQUIRED','displacement_m':displacement})
            return finish()
        door=prepared['data']['door'];end={'id':door['id'],'xy':door['xy'],'tags':door.get('tags',{}),'role':'REGISTERED_EXIT' if door.get('tags',{}).get('entrance')=='exit' else 'REGISTERED_DOOR'}
        bindings=[]
        for terminal in ({'id':start_id,'xy':start['xy'],'tags':start.get('tags',{})},end):
            verified=source.nodes.get(terminal['id'])
            key,stitch=bind(terminal,prepared['region'],prepared['cfg'],prepared['parsed'],'F0',verified_source=verified)
            if key in graph and math.dist(graph.nodes[key]['xy'],terminal['xy'])>1e-6:raise ValueError('SOURCE_ID_COORDINATE_MISMATCH')
            if stitch:
                attach,measured=stitch
                if key not in graph:graph.add_node(key,xy=tuple(terminal['xy']),tags=terminal.get('tags',{}))
                bidirectional(graph,key,attach,measured)
                bindings.append({'id':key,'attach':attach,'segments':measured,'displacement_m':0,'identity':'ORIGINAL_REGISTERED_DOOR' if key==end['id'] else 'EXACT_EXISTING_GROUND_SOURCE_NODE'})
        result.update(normalized_request={'scene_id':scene_id,'start_id':start_id,'door_id':door_id,'purpose':purpose,'method':method,'area_routing':area_mode,
                      'connectivity_mode':connectivity_mode,'seam_max_m':prepared.get('seam_max_m'),'lambda':1 if method=='F0' else 2},
                      start={'id':start_id,'raw_xy':raw_xy,'network_xy':start['xy'],'displacement_m':displacement},door=door,bindings=bindings,
                      graph={'nodes':len(graph),'arcs':graph.number_of_edges(),'unweighted_sha256':prepared['graph_sha']})
        route,failure,solver=_weighted_route(graph,start_id,end['id'],1 if method=='F0' else 2)
        result['solver']={**solver,'algorithm':'networkx weighted bidirectional shortest path','invocation_id':uuid.uuid4().hex,'answer_source':'CURRENT_REQUEST_SOLVER'}
        if route is None:
            result.update(status='NO_VALID_ROUTE',failure={'stage':'GRAPH_SEARCH',**failure});return finish()
        segments=route['segments'];checks=[];conflicts=[];continuity=0;validation_tick=time.perf_counter()
        face_by_id={f['source_id']:f for f in prepared.get('faces',[])}
        previous=tuple(start['xy'])
        for k,s in enumerate(segments):
            g=LineString(s['xy']);is_source=s['layer'] in ('native','derived') and not str(s.get('source_id','')).startswith('cell/')
            is_connectivity=s.get('geometry_kind')in('SOURCE_SUPPORTED_INTERFACE','CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')
            p=prepared['full_parsed'] if is_source or is_connectivity else prepared['parsed']
            reasons=edge_conflicts(g,p,native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
            if is_connectivity:
                from src.connectivity import validate_connectivity_segment
                reasons.extend(validate_connectivity_segment(s,prepared['faces'],prepared['full_parsed'],prepared['connectivity_evidence']))
            if s.get('geometry_kind')=='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE':
                from src.face_geometry import face_edge_conflicts
                face=face_by_id.get(s.get('source_area_id',s.get('source_id')))
                reasons.extend(face_edge_conflicts(g,face,prepared['full_parsed'])if face is not None else['MISSING_FULL_FACE_GEOMETRY'])
            gap=math.dist(previous,s['xy'][0]);continuity=max(continuity,gap);previous=s['xy'][-1]
            checks.append({'segment_index':k,'source_id':s.get('source_id'),'constraint_conflicts':reasons,'continuity_gap_m':gap})
            if reasons:conflicts.append({'segment_index':k,'source_id':s.get('source_id'),'reasons':reasons})
        residual=math.dist(previous,end['xy']);start_error=math.dist(segments[0]['xy'][0],start['xy']) if segments else math.dist(start['xy'],end['xy'])
        lengths={name:sum(s['length_m'] for s in segments if s['layer']==name) for name in ('native','derived','inferred','unknown')}
        source_lengths={'native':0.,'edge_band_derived':0.,'full_face_derived':0.,'local_mapped_grid_derived':0.,'assumed':0.,'exact_interface_derived':0.,'conditional_seam':0.}
        interior_outside_band=0.;face_passages=[]
        for s in segments:
            full=s.get('geometry_kind')=='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE'
            kind=s.get('geometry_kind')
            category='conditional_seam'if kind in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')else'exact_interface_derived'if kind=='SOURCE_SUPPORTED_INTERFACE'else'native'if s['layer']=='native'else'full_face_derived'if full else'local_mapped_grid_derived'if str(s.get('source_id','')).startswith('cell/')and s['layer']=='derived'else'edge_band_derived'if s['layer']=='derived'else'assumed'
            source_lengths[category]+=s['length_m'];s['source_class']=category
            if full:
                f=face_by_id[s.get('source_area_id',s['source_id'])];outside=LineString(s['xy']).difference(f['edge_band_geometry']).length
                interior_outside_band+=outside
                face_passages.append({'source_area_id':s.get('source_area_id',s['source_id']),'component':s.get('component'),'from':s['u'],'to':s['v'],
                    'start_xy':s['xy'][0],'end_xy':s['xy'][-1],'length_m':s['length_m'],'outside_old_band_m':outside})
        valid=not conflicts and max(continuity,residual,start_error)<=1e-6
        features=[{'type':'Feature','geometry':{'type':'LineString','coordinates':s['xy']},'properties':{k:v for k,v in s.items() if k!='xy'}} for s in segments]
        result.update(status=('ROUTED_CONDITIONAL' if lengths['inferred']+lengths['unknown']>1e-6 else 'ROUTED_NATIVE_OR_MAPPED') if valid else 'NO_VALID_ROUTE',
            route={'segments':segments,'geojson':{'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'features':features},
                   'length_m':sum(lengths.values()),'cost_weighted_m':sum(s['cost_m'] for s in segments),'layer_lengths_m':lengths,
                   'end_residual_m':residual,'start_error_m':start_error,'max_continuity_gap_m':continuity,'zero_length':route['zero_length'],
                   'source_lengths_m':source_lengths,'full_face_outside_old_band_m':interior_outside_band,'face_passages':face_passages},
            validation={'passed':valid,'whole_route_checked':True,'segment_checks':checks,'conflicts':conflicts},
            validation_s=time.perf_counter()-validation_tick,
            planning_region={'domain':mapping(prepared['surface'].domain),
                'assumed':mapping(prepared['surface'].masks[INFERRED]),'native':mapping(prepared['surface'].masks[NATIVE]),
                'restricted':mapping(prepared['surface'].masks[RESTRICTED]),'radius_m':30,'cell_m':1},
            uncertainty=['CONDITIONAL_LOCAL_FREE_SPACE_IS_NOT_MAP_FACT','KNOWN_ROAD_CENTERLINES_HAVE_NO_MEASURED_CARRIAGEWAY_WIDTH','CURRENT_PUBLIC_ACCESS_AND_LEVEL_NOT_FIELD_VERIFIED'])
        if prepared.get('faces'):
            from src.face_geometry import serializable_face
            result['mapped_faces']=[serializable_face(f)for f in prepared['faces']]
        result['face_network']=prepared.get('face_evidence',{})
        result['connectivity_evidence']=prepared.get('connectivity_evidence',{})
        result['route']['interface_ids_used']=sorted({s['interface_id']for s in segments if s.get('interface_id')})
        result['user_observation']='PENDING_USER_OBSERVATION'
        result['optimality_scope']='CURRENT_FINITE_INTERFACE_GRAPH_MINIMUM_COST; UNIFORM_POLYGON_VISIBILITY_ONLY_WITHIN_DECLARED_COMPUTED_FACE_DOMAINS'
        if not valid:result['failure']={'stage':'WHOLE_ROUTE_VALIDATION','code':'CONSTRAINT_OR_CONTINUITY_FAILURE','conflicts':conflicts}
        return finish()
    except (KeyError,ValueError,TypeError) as exc:
        result['failure']={'stage':'INPUT_OR_PREPARATION','code':str(exc)};return finish()
