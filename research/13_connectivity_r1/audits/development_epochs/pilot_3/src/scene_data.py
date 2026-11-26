"""APP-only frozen source adapter. No query/reference/route answers are read.

Raw OSM topology and exact R4-REV1 face edges retain their independent source
roles. Permission areas are interpreted for every scene, not selected task IDs.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
import gzip
import json
import math
from pathlib import Path
import time

import networkx as nx
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .frozen_scene import local_route as engine
from .frozen_scene.native_adapter import Source, PROJECT, INVERSE
from .frozen_scene.semantics import segment_decision, KEEP, permission, obstacle_kind

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = {'yes', 'designated', 'permissive', 'official'}
DENIED = {'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
MOTOR = {'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road'}
STRUCTURAL = {'wall','fence','hedge','retaining_wall','chain','city_wall','jersey_barrier'}
FALSE = {None,'','0','no','false'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def file_sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def restricted(t):
    return (t.get('foot',t.get('access')) in DENIED or t.get('locked')=='yes' or
            any(k.endswith(':conditional') and k.split(':')[0] in {'foot','access','oneway'} for k in t))


def non_ground(t):
    return any(t.get(k) not in FALSE for k in ('layer','level','bridge','tunnel','indoor','repeat_on')) or t.get('highway') in {'steps','elevator'}


def area_role(t):
    return t.get('area')!='no' and (t.get('area')=='yes' or t.get('amenity') in {'parking','parking_space'} or 'landuse' in t or 'leisure' in t or t.get('building') not in (None,'no') or t.get('natural') in {'water','wetland'} or t.get('type')=='multipolygon')


def source_key(key):
    if isinstance(key,str): return key
    if len(key)==3 and key[1:]==('0','0'): return f'node/{key[0]}'
    return f'node/{key[0]}@layer={key[1]}@level={key[2]}'


def source_coverage(bounds):
    west,south,east,north=bounds; corners=[(west,south),(east,south),(east,north),(west,north)]
    return Polygon([PROJECT(a[0]+(b[0]-a[0])*i/32,a[1]+(b[1]-a[1])*i/32) for a,b in zip(corners,corners[1:]+corners[:1]) for i in range(32)])


@lru_cache(maxsize=6)
def source_negative_areas(scene_id):
    """Trusted negative-only export, usable before masked prediction.

    It intentionally exports no source node/member arrays, footway geometry,
    pedestrian face, boundary allowance, reference or route answer. Selection
    uses the fixed observation window in the caller, never target-shaped cuts.
    """
    row=next(s for s in read(ROOT/'data/scene_manifest.json')['scenes']if s['scene_id']==scene_id)
    path=ROOT/row['source_path'];actual=file_sha(path)
    if actual!=row['source_sha256']:raise ValueError('SOURCE_SHA_MISMATCH')
    source=Source(read(path));out=[]
    for kind,objects in [('way',source.ways),('relation',source.relations)]:
        for number,obj in sorted(objects.items()):
            tags=obj.get('tags',{});refs=obj.get('nodes',[])
            closed=(kind=='relation' and tags.get('type')=='multipolygon')or(len(refs)>=4 and refs[0]==refs[-1])
            if not restricted(tags)or not closed or not area_role(tags):continue
            sid=f'{kind}/{number}';g=source.area(sid)
            if g is None:raise ValueError('NEGATIVE_SOURCE_AREA_UNPARSEABLE:'+sid)
            out.append({'source_id':sid,'geometry':mapping(g),'tags':tags,'source_clip_sha256':actual,
                'geometry_role':'COMPLETE_INDEPENDENT_RESTRICTED_SOURCE_AREA','source_node_ring_closed':True,
                'explicit_area_tag':tags.get('area'),'source_tag_area_basis':[k for k in ('amenity','area','landuse','leisure','building','natural')if k in tags]})
    return out


def export_negative_access_areas(scene_id,window,forbidden_ids=()):
    window=window if hasattr(window,'geom_type')else shape(window)
    forbidden=set(forbidden_ids);areas=[];excluded=[]
    for row in source_negative_areas(scene_id):
        if not shape(row['geometry']).intersects(window):continue
        if row['source_id']in forbidden:
            excluded.append({'source_id':row['source_id'],'reason':'WHOLE_FORBIDDEN_NEGATIVE_OBJECT_OMITTED'})
        else:areas.append(row)
    return areas,excluded


def list_scenes():
    manifest=read(ROOT/'data/scene_manifest.json')
    rows=[]
    for row in manifest['scenes']:
        scene=read(ROOT/'data/scenes'/row['scene_id']/'frozen_scene.json')
        rows.append({**row,'name':row['label'],'doors':door_catalog(scene),'building_footprint':scene['building_footprint'],'start_native_id':scene.get('start_native_id')})
    return {'scenes':rows,'crs':'EPSG:32651','channel':'APP_NATURAL_QUERY'}


def door_catalog(scene):
    """Only already registered target-building doors; no nearest proxy points."""
    result=[]
    for row in scene.get('r4_entrances',[]):
        tags=row['tags'];kind=tags.get('entrance'); denied=restricted(tags)
        inbound=kind not in (None,'no','exit','emergency','service','home','garage') and not denied and not non_ground(tags)
        result.append({'id':row['native_id'],'native_id':row['native_id'],'xy':list(PROJECT(*row['coordinate'])),'wgs84':row['coordinate'],
            'tags':tags,'entrance_type':kind,'registered':True,'building_id':scene['building_native_id'],
            'association_evidence':'NATIVE_NODE_ON_TARGET_BUILDING_OUTER_RING_FROZEN_SOURCE_CONTRACT',
            'role':'REGISTERED_EXIT' if kind=='exit' else 'REGISTERED_DOOR',
            'eligible_purposes':(['APPROACH_OUTSIDE'] if not denied and not non_ground(tags) else [])+(['ENTER_BUILDING'] if inbound else []),
            'public_access':'UNKNOWN','current_opening':'UNKNOWN','physical_door_field_verified':False})
    return result


def _add_arc(graph,u,v,seg):
    value={'segments':[seg], 'cost':seg['length_m'],'alternative_segments':[]}
    # The route solver is a DiGraph, but constraint filtering must consider all
    # original parallel source arcs before selecting a valid minimum. Preserve
    # alternatives in the live graph rather than only an external source file.
    if not graph.has_edge(u,v) or (value['cost'],seg.get('source_id',''),seg.get('edge_id','')) < (graph[u][v]['cost'],graph[u][v]['segments'][0].get('source_id',''),graph[u][v]['segments'][0].get('edge_id','')):
        if graph.has_edge(u,v):value['alternative_segments']=graph[u][v]['segments']+graph[u][v].get('alternative_segments',[])
        graph.add_edge(u,v,**value)
    else:graph[u][v].setdefault('alternative_segments',[]).append(seg)


@lru_cache(maxsize=1)
def _prepared_scene(scene_id):
    started=time.perf_counter()
    row=next((s for s in read(ROOT/'data/scene_manifest.json')['scenes'] if s['scene_id']==scene_id),None)
    if row is None: raise ValueError('UNKNOWN_SCENE')
    folder=ROOT/'data/scenes'/scene_id;path=ROOT/row['source_path']
    if file_sha(path)!=row['source_sha256']: raise ValueError('SOURCE_SHA_MISMATCH')
    raw=read(path);source=Source(raw);scene=read(folder/'frozen_scene.json')
    # Guard the frozen contract's building/door identity directly against source.
    outline=source.outline(scene['building_native_id'])
    doors=door_catalog(scene)
    for door in doors:
        nid=int(door['id'].split('/')[1]);node=source.nodes[nid]
        if nid not in outline or [node['lon'],node['lat']]!=door['wgs84'] or node.get('tags',{})!=door['tags']:
            raise ValueError('REGISTERED_DOOR_SOURCE_IDENTITY_MISMATCH')
    source_objects,unlocated=source.obstacles([])
    obstacle_tree=STRtree([x['geometry'] for x in source_objects])
    segments,endings,raw_stats=engine._segments(raw)
    native,_=engine._build_graph(segments,endings,())
    decisions={};native_ledger=[];grass_segments=set()
    for seg in segments:
        line=LineString([source.projected[seg.a[0]],source.projected[seg.b[0]]]);tags=source.ways[seg.way].get('tags',{})
        obstacles=[source_objects[int(i)] for i in obstacle_tree.query(line,predicate='intersects')]
        result=segment_decision(line,tags,obstacles,'S1',native_nodes=(seg.a[0],seg.b[0]),endpoint_tags=[source.nodes[n].get('tags',{})for n in (seg.a[0],seg.b[0])])
        decisions[seg.key]=result
        if result['status']==KEEP and any(c['decision_reason']=='MAPPED_PATH_OVER_LANDCOVER' for c in result['contacts']):grass_segments.add(seg.key)
        if result['status']!=KEEP or result['contacts']:native_ledger.append({'source_id':f'way/{seg.way}','segment_index':seg.index,'xy':list(line.coords),**result})
    graph=nx.DiGraph()
    nodes={}
    for n,attrs in native.nodes(data=True):
        ident=source_key(n);node=source.nodes.get(n[0],{});node_tags=node.get('tags',{})
        nodes[ident]={'id':ident,'xy':list(PROJECT(*attrs['coord'])),'wgs84':list(attrs['coord']),'tags':node_tags,'layer_key':n[1],'level_key':n[2],'endpoint_kind':'NATIVE_OSM_NODE'}
        graph.add_node(ident,**{k:v for k,v in nodes[ident].items()if k!='id'})
    raw_native_edges=[]
    for a,b,k,attrs in native.edges(keys=True,data=True):
        wid=attrs.get('osm_way_id');si=attrs.get('segment_index')
        if wid is not None and decisions[(wid,si)]['status']!=KEEP:continue
        u,v=source_key(a),source_key(b);xy=[nodes[u]['xy'],nodes[v]['xy']];tags=source.ways[wid].get('tags',{}) if wid is not None else {}
        sid=f'way/{wid}' if wid is not None else f'node/{a[0]}'
        record={'id':f'{sid}/segment/{si}/{u}>{v}','u':u,'v':v,'kind':'NATIVE_LINEAR','tags':tags,'source_id':sid,'source_segment_index':si,'source_direction':1 if attrs.get('osm_source_node_ids',[None])[0]==a[0] else -1}
        raw_native_edges.append(record)
        length=math.dist(*xy)
        _add_arc(graph,u,v,{'xy':xy,'layer':'native','source_id':sid,'length_m':length,'cost_m':length,'tags':tags,'edge_id':record['id'],'geometry_kind':'ORIGINAL_OSM_NATIVE_SEGMENT','level_key':a[2],'layer_key':a[1]})
    graph.remove_nodes_from(list(nx.isolates(graph)))
    native_node_ids=set(graph)
    # Full exact face-derived graph, never historical routes. A separate overlay
    # keeps native-source and mapped-area identities distinguishable.
    mapped_count=0
    mapped_path=ROOT/row['mapped_edges_path']
    if file_sha(mapped_path)!=row['mapped_edges_sha256']:raise ValueError('MAPPED_GRAPH_SHA_MISMATCH')
    with gzip.open(mapped_path,'rt',encoding='utf8') as handle:
        for line in handle:
            edge=json.loads(line);u,v=edge['u'],edge['v'];xy=edge['coordinates_metric'];tags=edge.get('source_tags',{})
            for n,p in zip((u,v),xy):
                if n in graph and math.dist(graph.nodes[n]['xy'],p)>1e-6:raise ValueError('MAPPED_NATIVE_TOPOLOGY_DRIFT')
                if n not in graph:graph.add_node(n,xy=p,tags={},endpoint_kind='MAPPED_AREA_DERIVED_NODE')
            segment={'xy':xy,'layer':'derived','source_id':edge['source_area_id'],'length_m':edge['length_m'],'cost_m':edge['length_m'],'tags':tags,'edge_id':edge['edge_id'],'geometry_kind':'FROZEN_R4_REV1_MAPPED_FACE_EDGE','model_assumptions':edge.get('model_assumptions',[])}
            _add_arc(graph,u,v,segment)
            if edge['direction']=='BIDIRECTIONAL':_add_arc(graph,v,u,{**segment,'xy':xy[::-1]})
            mapped_count+=1
    # Classification: polygons and explicit permissions remain spatial objects.
    context={'hard':[],'background':[],'support':[]};mapped_seen=set();map_layers=[];access_areas=[];road_rows=[];gate_by_id={}
    for obj in source_objects:
        kind=obstacle_kind(obj);tags=obj.get('tags',{});g=obj['geometry'];sid=obj['id']
        if kind=='BACKGROUND_GRASS':layer='background';kind='GRASS'
        elif kind=='AREA':
            # A foot-specific public tag can override general access on an area.
            # It is neither lawn nor a physical obstacle simply because the
            # legacy parser included the general access-tagged object.
            layer='support';kind='MAPPED_NON_RESTRICTED_AREA'
        else:layer='hard'
        record={'id':sid,'kind':kind,'tags':tags,'geometry':mapping(g),'gates':obj.get('gates',[])}
        context[layer].append(record);mapped_seen.add(sid);map_layers.append({'type':'Feature','geometry':mapping(g),'properties':{'id':sid,'kind':kind,'tags':tags,'layer':layer}})
        if obj.get('kind')=='BARRIER' and sid.startswith('way/'):
            # Match the frozen common-guard exporter, not a proximity-derived
            # opening. Only original gate nodes belonging to this barrier way
            # can create its bounded opening; separate point restrictions stay.
            gate_rows=[]
            for nid in source.ways[int(sid.split('/')[1])].get('nodes',[]):
                node=source.nodes.get(nid)
                if node is None:continue
                gt=node.get('tags',{})
                if gt.get('barrier') not in {'gate','lift_gate','swing_gate','kissing_gate','bollard','cycle_barrier','entrance'}:continue
                gate_rows.append({'id':f'node/{nid}','xy':list(source.projected[nid]),'tags':gt,
                    'allowed':not restricted(gt) and not non_ground(gt),
                    'evidence':'SOURCE_GATE_NODE_MEMBER_OF_BARRIER_WAY',
                    'permission_status':'SOURCE_CONDITIONAL_NOT_FIELD_VERIFIED'})
            if gate_rows:gate_by_id[sid]=gate_rows
        elif obj.get('gates'):gate_by_id[sid]=obj['gates']
    for kind,objects in [('way',source.ways),('relation',source.relations)]:
        for number,obj in objects.items():
            tags=obj.get('tags',{});sid=f'{kind}/{number}';refs=obj.get('nodes',[])
            is_closed=(kind=='relation' and tags.get('type')=='multipolygon') or (len(refs)>=4 and refs[0]==refs[-1])
            if restricted(tags) and is_closed and area_role(tags):
                g=source.area(sid)
                if g is not None:
                    access_areas.append({'source_id':sid,'geometry':mapping(g),'tags':tags,'source_clip_sha256':row['source_sha256'],'geometry_role':'COMPLETE_INDEPENDENT_RESTRICTED_SOURCE_AREA','source_node_ring_closed':True,'explicit_area_tag':tags.get('area'),'source_tag_area_basis':[k for k in ('amenity','area','landuse','leisure','building','natural')if k in tags]})
                    if sid not in mapped_seen:
                        record={'id':sid,'kind':'RESTRICTED','tags':tags,'geometry':mapping(g),'gates':[]};context['hard'].append(record);mapped_seen.add(sid);map_layers.append({'type':'Feature','geometry':mapping(g),'properties':{'id':sid,'kind':'RESTRICTED','tags':tags,'layer':'hard'}})
                else:unlocated.append(sid)
            elif restricted(tags) and kind=='way' and len(refs)>1 and all(n in source.projected for n in refs) and sid not in mapped_seen:
                g=LineString([source.projected[n]for n in refs]);record={'id':sid,'kind':'RESTRICTED_LINEAR_ACCESS','tags':tags,'geometry':mapping(g),'gates':[]}
                context['hard'].append(record);mapped_seen.add(sid);map_layers.append({'type':'Feature','geometry':mapping(g),'properties':{'id':sid,'kind':'RESTRICTED_LINEAR_ACCESS','tags':tags,'layer':'hard'}})
            face=(tags.get('highway')=='pedestrian' and tags.get('area')=='yes') or tags.get('area:highway') in {'pedestrian','footway','path'}
            support=tags.get('leisure') in {'park','garden','recreation_ground'} or tags.get('surface') in {'paved','paving_stones','concrete','asphalt'}
            if is_closed and (face or support) and sid not in mapped_seen:
                g=source.area(sid)
                if g is not None:
                    typ='PEDESTRIAN_AREA' if face else 'PARK' if tags.get('leisure') else 'PAVING'
                    record={'id':sid,'kind':typ,'tags':tags,'geometry':mapping(g),'gates':[]};context['support'].append(record);mapped_seen.add(sid);map_layers.append({'type':'Feature','geometry':mapping(g),'properties':{'id':sid,'kind':typ,'tags':tags,'layer':'support'}})
            if kind=='way' and len(refs)>1 and all(n in source.projected for n in refs) and tags.get('highway') and tags.get('area')!='yes':
                g=LineString([source.projected[n]for n in refs])
                map_layers.append({'type':'Feature','geometry':mapping(g),'properties':{'id':sid,'kind':'ROAD' if tags['highway'] in MOTOR else 'NATIVE_WALKWAY','tags':tags,'layer':'linear'}})
                if tags['highway'] in MOTOR and not non_ground(tags):road_rows.append({'source_id':sid,'kind':'MOTOR_ROAD_CENTERLINE','geometry':mapping(g),'tags':tags,'source_geometry_sha256':digest(mapping(g)),'geometry_role':'TOPOLOGICAL_NO_NEW_FREE_CROSSING_NOT_CARRIAGEWAY_WIDTH','crop':'FULL_FROZEN_CLIP'})
    for n in list(graph):
        graph.nodes[n].setdefault('tags',{})
    native_nodes=[nodes[n]for n in sorted(native_node_ids)]
    full_obs={'task_id':'APP/'+scene_id,'crs':'EPSG:32651','domain':{'anchor_xy':doors[0]['xy']if doors else list(PROJECT(*scene['target'])),'anchor_role':'REGISTERED_DOOR'if doors else'VIEW_ONLY_NO_REGISTERED_DOOR'},'registered_entrance':doors[0]if doors else None,'nodes':native_nodes,'edges':raw_native_edges,'context':context}
    # Same-source native node identity, not an arbitrary coordinate crossing.
    road_nodes=defaultdict(set)
    for item in road_rows:
        for n in source.ways[int(item['source_id'].split('/')[1])]['nodes']:road_nodes[f'node/{n}'].add(item['source_id'])
    access_points=[{'id':n,'xy':nodes[n]['xy'],'source_ids':sorted(road_nodes[n]),'tags':nodes[n]['tags'],'evidence':'EXACT_SHARED_ORIGINAL_ROAD_AND_OBSERVED_GRAPH_NODE'}for n in sorted(native_node_ids)if n in road_nodes and not restricted(nodes[n]['tags'])and not non_ground(nodes[n]['tags'])]
    guards={'guard_version':'APP_UNIFIED_SOURCE_GUARDS_V1','id':scene_id,'crs':'EPSG:32651','source_sha256':row['source_sha256'],'source_parse_status':'PARSED','source_bounds_wsen':raw['bounds_wsen'],'source_timestamp':raw.get('osm3s',{}).get('timestamp_osm_base'),'coverage_geometry':mapping(source_coverage(raw['bounds_wsen'])),'road_centerlines':road_rows,'barrier_gates':gate_by_id,'native_road_access_points':access_points,'access_areas':access_areas,'constraints_not_covered':['UNMAPPED_REAL_WORLD_OBSTACLES','UNMAPPED_PERMISSION_OR_HEIGHT_CHANGE','EXACT_CARRIAGEWAY_WIDTH_NOT_AVAILABLE']}
    preparation={'source_sha256':row['source_sha256'],'mapped_edges_sha256':row['mapped_edges_sha256'],'raw_native_stats':raw_stats,'native_kept_segments':sum(v['status']==KEEP for v in decisions.values()),'native_grass_unique_segments':len(grass_segments),'native_grass_segment_keys':[list(k)for k in sorted(grass_segments)],'mapped_edge_rows':mapped_count,'combined_graph_nodes':graph.number_of_nodes(),'combined_graph_arcs':graph.number_of_edges(),'parallel_alternative_segments':sum(len(r.get('alternative_segments',[]))for _,_,r in graph.edges(data=True)),'source_unlocated_hazards':sorted(set(unlocated)),'extra_access_areas':len(access_areas),'source_timestamp':raw.get('osm3s',{}).get('timestamp_osm_base'),'time_s':time.perf_counter()-started,'parallel_arc_policy':'All parallel source arc alternatives preserved in live graph; common constraint filter must select valid minimum only after checking candidates; no new 2D intersection nodes'}
    return {'scene_id':scene_id,'name':row['label'],'scene':scene,'manifest':row,'doors':doors,'source_info':preparation,'full_observed':full_obs,'full_guards':guards,'combined_source_graph':graph,'native_ledger':native_ledger,'map_layers':{'type':'FeatureCollection','features':map_layers},'native_nodes':native_nodes}


def load_scene(scene_id,door_id=None):
    ready=_prepared_scene(scene_id)
    if door_id is None:
        if not ready['doors']:return {**ready,'door':None,'observed':None,'guards':None,'starts':[]}
        door=ready['doors'][0]
    else:
        door=next((d for d in ready['doors']if d['id']==door_id),None)
        if door is None:raise ValueError('NO_ELIGIBLE_REGISTERED_ENTRANCE')
    anchor=Point(door['xy']);window=anchor.buffer(160,quad_segs=32)
    # Context observation is independent of start and final route.
    context={k:[r for r in rows if shape(r['geometry']).intersects(window)]for k,rows in ready['full_observed']['context'].items()}
    graph=ready['combined_source_graph'];local_nodes=set()
    edges=[]
    for u,v,r in graph.edges(data=True):
        line=LineString([graph.nodes[u]['xy'],graph.nodes[v]['xy']])
        if not line.intersects(window):continue
        local_nodes.update((u,v))
        for s in r['segments']:
            edges.append({'id':s['edge_id'],'u':u,'v':v,'kind':'NATIVE_LINEAR'if s['layer']=='native'else'DERIVED_FROM_TAGGED_PEDESTRIAN_AREA','tags':s['tags'],'source_id':s['source_id'],'source_segment_index':s.get('edge_id')})
    obs={'task_id':f'APP/{scene_id}/{door_id or door["id"]}','crs':'EPSG:32651','domain':{'anchor_xy':door['xy'],'anchor_role':'EXACT_REGISTERED_DOOR_LOCAL_DOMAIN'},'registered_entrance':door,'nodes':[{'id':n,**graph.nodes[n]}for n in sorted(local_nodes)],'edges':edges,'context':context}
    guards={**ready['full_guards'],'observed_sha256':digest(obs),'road_centerlines':[r for r in ready['full_guards']['road_centerlines']if shape(r['geometry']).intersects(window)],'access_areas':[r for r in ready['full_guards']['access_areas']if shape(r['geometry']).intersects(window)],'native_road_access_points':[r for r in ready['full_guards']['native_road_access_points']if window.covers(Point(r['xy']))]}
    starts=[]
    for n in ready['native_nodes']:
        if n['id']not in graph or not graph.degree(n['id']) or non_ground(n['tags'])or restricted(n['tags'])or n.get('layer_key')!='0'or n.get('level_key')!='0':continue
        adjacent=list(graph.in_edges(n['id'],data=True))+list(graph.out_edges(n['id'],data=True))
        if not any(s['layer']=='native'and not non_ground(s.get('tags',{}))and not restricted(s.get('tags',{})) for _,_,r in adjacent for s in r['segments']):continue
        distance=math.dist(n['xy'],door['xy'])
        starts.append({'id':n['id'],'label':n['id'],'xy':n['xy'],'wgs84':n['wgs84'],'tags':n['tags'],'distance_to_door_m':distance,'role':'EXACT_EXISTING_ELIGIBLE_NATIVE_NODE'})
    starts.sort(key=lambda n:(n['distance_to_door_m'],n['id']))
    return {**ready,'door':door,'observed':obs,'guards':guards,'native_graph':graph,'starts':starts,'observation_radius_m':160,'prediction_radius_m':30}
