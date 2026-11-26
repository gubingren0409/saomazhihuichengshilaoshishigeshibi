"""Prelocked real source-interface queries; targets never become entrances."""
from pathlib import Path
import json,math,time,uuid
from datetime import datetime
from shapely.geometry import Point,LineString,shape,mapping
from src.face_geometry import face_edge_conflicts
from src.connectivity import _domains,_domain_conflicts,_derived_segments,validate_connectivity_segment
from src.region_routing import bidirectional
from src.common_constraints import edge_conflicts
from src.region import digest

def _bind_endpoint(endpoint,prepared,graph):
    ident=endpoint.get('layer_aware_native_graph_id',endpoint['id']);xy=endpoint['xy']
    if ident in graph:
        error=math.dist(graph.nodes[ident]['xy'],xy)
        if error>1e-8:raise ValueError('MECHANISM_ORIGINAL_COORDINATE_MISMATCH')
        return {'id':ident,'bound':True,'identity':'EXISTING_SOURCE_NETWORK_NODE','displacement_m':0.}
    area=endpoint.get('source_area_id')
    if not area:return {'id':ident,'bound':False,'reason':'SOURCE_NODE_ABSENT_FROM_ELIGIBLE_LAYER_AWARE_NETWORK'}
    faces=[f for f in prepared['faces']if f['source_id']==area and f['status']=='ADMITTED'and f['omega'].covers(Point(xy))]
    if not faces:return {'id':ident,'bound':False,'reason':'UNBOUND_TO_INACTIVE_OR_CONSTRAINED_SOURCE_FACE','source_area_id':area}
    graph.add_node(ident,xy=tuple(xy),tags=endpoint.get('source_node_tags',{}),role='ORIGINAL_BOUNDARY_MECHANISM_REFERENCE_NOT_ENTRANCE')
    domains=[];mode=prepared['connectivity_mode']
    if mode in('EXACT_STITCH','CONDITIONAL_SEAMS'):
        candidates,_,_,_=_domains(prepared['faces'],prepared['full_parsed'])
        domains=[d for d in candidates if area in {f['source_id']for f in d['faces']}and d['poly'].covers(Point(xy))]
    else:
        for face in faces:
            for ci,c in enumerate(face['components']):
                if c['geometry'].covers(Point(xy)):
                    domains.append({'key':f'query/{area}/{ci}','prefix':f'fullface/{area}/component/{ci}','poly':c['geometry'],'faces':[face]})
    ports=[]
    for d in domains:
        ids={p['id']for p in prepared.get('face_evidence',{}).get('portals',[])if p.get('source_area_id')in{f['source_id']for f in d['faces']}}
        ids.update(p['id']for p in prepared.get('connectivity_evidence',{}).get('stitch_portals',[])if p.get('domain_key')==d['key'])
        prefixes=tuple([d['prefix']]+[f"fullface/{f['source_id']}/component/"for f in d['faces']])
        candidates=[n for n in graph if n!=ident and(n in ids or str(n).startswith(prefixes))and d['poly'].covers(Point(graph.nodes[n]['xy']))]
        for n in candidates:
            target=graph.nodes[n]['xy'];line=LineString([xy,target])
            if line.length==0:continue
            if mode in('EXACT_STITCH','CONDITIONAL_SEAMS'):
                if _domain_conflicts(line,d,prepared['full_parsed']):continue
                segments=_derived_segments(line,d)
                if not segments:continue
            else:
                face=d['faces'][0]
                if face_edge_conflicts(line,face,prepared['full_parsed']):continue
                segments=[{'xy':[list(xy),list(target)],'length_m':line.length,'cost_m':line.length,'layer':'derived',
                    'source_id':area,'source_area_id':area,'geometry_kind':'DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE','tags':face['tags'],
                    'component':d['key'],'clearance_m':.25,'mechanism_endpoint_binding':True}]
            bidirectional(graph,ident,n,segments);ports.append(n)
    return {'id':ident,'bound':bool(ports),'identity':'ORIGINAL_SOURCE_BOUNDARY_NODE_QUERY_ATTACHMENT','source_area_id':area,
        'visible_attachments':len(ports),'attached_node_ids':ports,'displacement_m':0.,'reason':None if ports else'NO_LEGAL_QUERY_VISIBILITY_ATTACHMENT'}

def plan_mechanism(request):
    from src.planner import ROOT,LOCK,prepare_connectivity,compose_prepared,_weighted_route,graph_sha,put,code_identity,IMPORTED_CODE_SHA
    tick=time.perf_counter();rid='RUN-'+datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:10]
    result={'run_id':rid,'request_id':request.get('request_id',uuid.uuid4().hex),'input':request,'namespace':'REAL_SOURCE_INTERFACE_MECHANISM',
        'entrance_assertion':False,'reference_door':None,'route_answer_cache':{'enabled':False,'hit':False},'solver':{'invoked':False},
        'status':'INVALID_MECHANISM_REQUEST','working_crs':'EPSG:32651','user_observation':'PENDING_USER_OBSERVATION'}
    def finish():
        if code_identity()!=IMPORTED_CODE_SHA:result.update(status='INVALID_RESULT_VERSION_CHANGED')
        result['elapsed_s']=time.perf_counter()-tick;put(ROOT/'runs/mechanisms'/f'{rid}.json',result);return result
    try:
        lock_path=ROOT/'data/connectivity/mechanism_request_endpoints_lock.json';raw=lock_path.read_bytes();locked=json.loads(raw)
        query=next((q for q in locked['queries']if q['mechanism_id']==request.get('mechanism_id')),None)
        if query is None:raise ValueError('MECHANISM_ID_NOT_PRELOCKED')
        method=request.get('method','F0');mode=request.get('connectivity_mode','FROZEN_FULL_FACE');threshold=float(request.get('seam_max_m',2.))
        if method not in('F0','F1'):raise ValueError('INVALID_METHOD')
        with LOCK:prepared,hit,prep_s=prepare_connectivity(query['scene_id'],None,mode,threshold)
        graph=compose_prepared(prepared);bindings=[_bind_endpoint(query[k],prepared,graph)for k in('start','end')]
        result.update(query=query,bindings=bindings,connectivity_mode=mode,method=method,source_selection_lock=digest(locked),
            versions={'code_sha256':prepared['code_sha'],'source':prepared['data']['source_info'],'unweighted_graph_sha256':graph_sha(graph)},
            preprocessing_cache={'key':prepared['cache_key'],'hit':hit,'load_or_prepare_s':prep_s},
            graph={'nodes':len(graph),'arcs':graph.number_of_edges()},local_door_free_area_m2=0,
            connectivity_evidence=prepared.get('connectivity_evidence',{}),face_network=prepared.get('face_evidence',{}))
        if not all(b['bound']for b in bindings):result.update(status='MECHANISM_ENDPOINT_UNBOUND',failure={'stage':'MODE_ENDPOINT_BINDING','bindings':bindings});return finish()
        route,failure,solver=_weighted_route(graph,bindings[0]['id'],bindings[1]['id'],1 if method=='F0'else 2)
        result['solver']={**solver,'invocation_id':uuid.uuid4().hex,'answer_source':'CURRENT_REQUEST_SOLVER','algorithm':'networkx weighted shortest path'}
        if route is None:result.update(status='NO_VALID_ROUTE',failure={'stage':'GRAPH_SEARCH',**failure});return finish()
        conflicts=[];previous=query['start']['xy'];max_gap=0.
        face_by_id={f['source_id']:f for f in prepared['faces']}
        for i,s in enumerate(route['segments']):
            line=LineString(s['xy']);reasons=edge_conflicts(line,prepared['full_parsed'],native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
            if s.get('geometry_kind')in('SOURCE_SUPPORTED_INTERFACE','CONDITIONAL_GAP_LINK'):
                reasons.extend(validate_connectivity_segment(s,prepared['faces'],prepared['full_parsed'],prepared.get('connectivity_evidence',{})))
            elif s.get('geometry_kind')=='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE':
                f=face_by_id.get(s.get('source_area_id'));reasons.extend(face_edge_conflicts(line,f,prepared['full_parsed'])if f else['MISSING_SOURCE_FACE'])
            max_gap=max(max_gap,math.dist(previous,s['xy'][0]));previous=s['xy'][-1]
            if reasons:conflicts.append({'segment':i,'reasons':sorted(set(reasons))})
        residual=math.dist(previous,query['end']['xy']);length=sum(s['length_m']for s in route['segments']);cost=sum(s['cost_m']for s in route['segments'])
        conditional=sum(s['length_m']for s in route['segments']if s['layer']in('inferred','unknown','assumed'))
        seam=sum(s['length_m']for s in route['segments']if s.get('geometry_kind')=='CONDITIONAL_GAP_LINK')
        valid=not conflicts and max(max_gap,residual)<=1e-6
        result.update(status=('ROUTED_CONDITIONAL'if conditional>1e-6 else'ROUTED_NATIVE_OR_MAPPED')if valid else'NO_VALID_ROUTE',
            route={'segments':route['segments'],'length_m':length,'cost_weighted_m':cost,'conditional_seam_m':seam,'all_hypothesis_m':conditional,
                'native_m':sum(s['length_m']for s in route['segments']if s['layer']=='native'),'mapped_derived_m':sum(s['length_m']for s in route['segments']if s['layer']=='derived'),
                'door_front_assumed_m':0.,'end_residual_m':residual,'max_continuity_gap_m':max_gap,'zero_length':length==0,
                'interface_ids_used':sorted({s['interface_id']for s in route['segments']if s.get('interface_id')})},
            validation={'passed':valid,'whole_route_checked':True,'conflicts':conflicts},
            geometry_evidence_scope='FROZEN_SOURCE_AND_DECLARED_CONDITIONAL_INTERFACES_NOT_FIELD_PASSAGE')
        return finish()
    except (ValueError,KeyError,TypeError)as e:result['failure']={'code':str(e)};return finish()
