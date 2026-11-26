"""Request-time known-door solver. No stored-route lookup or route-answer cache."""
from __future__ import annotations
import json, math, threading, time, uuid
from datetime import datetime
from pathlib import Path
from hashlib import sha256
import networkx as nx
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

def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    temp.replace(path)

def code_identity():
    return digest({p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for folder in ('src','config') for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')})

IMPORTED_CODE_SHA=code_identity()

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
        SOURCE_CACHE[source_key]=(source_graph,rejected)
    graph=nx.compose(source_graph,region.internal)
    graph_sha=digest(graph_record(graph))
    result=dict(data=data,cfg=cfg,common=common,parsed=parsed_contract(common),full_common=full_common,
                full_parsed=full_parsed,source=source_graph,local=local,region=region,
                graph=graph,surface=surface,cache_key=key,graph_sha=graph_sha,
                rejected=rejected,local_rejected=local_rejected,code_sha=code_identity(),prepare_s=time.perf_counter()-tick)
    CACHE[key]=result
    PREPARED_INDEX[index_key]=key
    progress('PREPROCESSING_COMPLETE',nodes=len(graph),arcs=graph.number_of_edges(),source_rejected_arcs=len(rejected))
    # Each cold build is an execution record, rather than a replaceable cache
    # answer. A later process rebuilding this key must preserve earlier receipts.
    prep_id='PREP-'+uuid.uuid4().hex
    put(ROOT/'runs/preprocessing'/f'{key}-{prep_id}.json',{'namespace':'APP_NATURAL_QUERY','preprocessing_run_id':prep_id,'cache_key':key,'code_sha256':result['code_sha'],
        'source':data['source_info'],'observed_sha256':digest(obs),'guard_sha256':digest(guards),'cfg':cfg,
        'surface_sha256':surface.sha256,'graph_sha256':graph_sha,'prepare_s':result['prepare_s'],
        'route_answers_stored':False,'nodes':len(graph),'arcs':graph.number_of_edges()})
    return result,False,time.perf_counter()-tick

def scene_list():
    from src.scene_data import list_scenes
    return list_scenes()

def scene_view(scene_id,door_id=None):
    from src.scene_data import load_scene
    data=load_scene(scene_id,door_id)
    result={k:data[k] for k in ('scene_id','name','doors','map_layers','starts','source_info') if k in data}
    result['coverage_geometry']=data['full_guards']['coverage_geometry']
    return result

def _weighted_route(graph,a,b,weight):
    calls={'invoked':False}
    if a not in graph or b not in graph:return None,{'code':'UNBOUND_ENDPOINT','source_present':a in graph,'target_present':b in graph},calls
    def cost(u,v,row):
        return sum(s['length_m']*(weight if s['layer'] in ('inferred','assumed','unknown') else 1) for s in row['segments'])
    calls['invoked']=True;tick=time.perf_counter()
    try:nodes=nx.shortest_path(graph,a,b,weight=cost)
    except nx.NetworkXNoPath:
        reachable=nx.descendants(graph,a)|{a};target=graph.nodes[b]['xy']
        frontier=sorted(reachable,key=lambda n:(math.dist(graph.nodes[n]['xy'],target),str(n)))[:5]
        return None,{'code':'DISCONNECTED_GRAPH','reachable_nodes':len(reachable),'last_frontier':[{'id':n,'xy':graph.nodes[n]['xy'],'distance_to_door_m':math.dist(graph.nodes[n]['xy'],target)} for n in frontier]},dict(calls,elapsed_s=time.perf_counter()-tick)
    segments=[]
    for u,v in zip(nodes,nodes[1:]):
        for s in graph[u][v]['segments']:
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
        with LOCK: prepared,hit,load_s=_prepare(scene_id,door_id)
        result.update(preprocessing_cache={'key':prepared['cache_key'],'hit':hit,'load_or_prepare_s':load_s},
                      versions={'source':prepared['data']['source_info'],'code_sha256':prepared['code_sha'],'surface_sha256':prepared['surface'].sha256,'unweighted_graph_sha256':prepared['graph_sha']})
        graph=nx.compose(nx.DiGraph(),prepared['graph']);source=prepared['source']
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
        result.update(normalized_request={'scene_id':scene_id,'start_id':start_id,'door_id':door_id,'purpose':purpose,'method':method,'lambda':1 if method=='F0' else 2},
                      start={'id':start_id,'raw_xy':raw_xy,'network_xy':start['xy'],'displacement_m':displacement},door=door,bindings=bindings,
                      graph={'nodes':len(graph),'arcs':graph.number_of_edges(),'unweighted_sha256':prepared['graph_sha']})
        route,failure,solver=_weighted_route(graph,start_id,end['id'],1 if method=='F0' else 2)
        result['solver']={**solver,'algorithm':'networkx weighted bidirectional shortest path','invocation_id':uuid.uuid4().hex,'answer_source':'CURRENT_REQUEST_SOLVER'}
        if route is None:
            result.update(status='NO_VALID_ROUTE',failure={'stage':'GRAPH_SEARCH',**failure});return finish()
        segments=route['segments'];checks=[];conflicts=[];continuity=0;validation_tick=time.perf_counter()
        previous=tuple(start['xy'])
        for k,s in enumerate(segments):
            g=LineString(s['xy']);is_source=s['layer'] in ('native','derived') and not str(s.get('source_id','')).startswith('cell/')
            p=prepared['full_parsed'] if is_source else prepared['parsed']
            reasons=edge_conflicts(g,p,native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
            gap=math.dist(previous,s['xy'][0]);continuity=max(continuity,gap);previous=s['xy'][-1]
            checks.append({'segment_index':k,'source_id':s.get('source_id'),'constraint_conflicts':reasons,'continuity_gap_m':gap})
            if reasons:conflicts.append({'segment_index':k,'source_id':s.get('source_id'),'reasons':reasons})
        residual=math.dist(previous,end['xy']);start_error=math.dist(segments[0]['xy'][0],start['xy']) if segments else math.dist(start['xy'],end['xy'])
        lengths={name:sum(s['length_m'] for s in segments if s['layer']==name) for name in ('native','derived','inferred','unknown')}
        valid=not conflicts and max(continuity,residual,start_error)<=1e-6
        features=[{'type':'Feature','geometry':{'type':'LineString','coordinates':s['xy']},'properties':{k:v for k,v in s.items() if k!='xy'}} for s in segments]
        result.update(status=('ROUTED_CONDITIONAL' if lengths['inferred']+lengths['unknown']>1e-6 else 'ROUTED_NATIVE_OR_MAPPED') if valid else 'NO_VALID_ROUTE',
            route={'segments':segments,'geojson':{'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'features':features},
                   'length_m':sum(lengths.values()),'cost_weighted_m':sum(s['cost_m'] for s in segments),'layer_lengths_m':lengths,
                   'end_residual_m':residual,'start_error_m':start_error,'max_continuity_gap_m':continuity,'zero_length':route['zero_length']},
            validation={'passed':valid,'whole_route_checked':True,'segment_checks':checks,'conflicts':conflicts},
            validation_s=time.perf_counter()-validation_tick,
            planning_region={'domain':mapping(prepared['surface'].domain),
                'assumed':mapping(prepared['surface'].masks[INFERRED]),'native':mapping(prepared['surface'].masks[NATIVE]),
                'restricted':mapping(prepared['surface'].masks[RESTRICTED]),'radius_m':30,'cell_m':1},
            uncertainty=['CONDITIONAL_LOCAL_FREE_SPACE_IS_NOT_MAP_FACT','KNOWN_ROAD_CENTERLINES_HAVE_NO_MEASURED_CARRIAGEWAY_WIDTH','CURRENT_PUBLIC_ACCESS_AND_LEVEL_NOT_FIELD_VERIFIED'])
        if not valid:result['failure']={'stage':'WHOLE_ROUTE_VALIDATION','code':'CONSTRAINT_OR_CONTINUITY_FAILURE','conflicts':conflicts}
        return finish()
    except (KeyError,ValueError,TypeError) as exc:
        result['failure']={'stage':'INPUT_OR_PREPARATION','code':str(exc)};return finish()
