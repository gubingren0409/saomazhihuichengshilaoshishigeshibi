"""Read-only source-object display export; never participates in routing."""
from pathlib import Path
import json
from functools import lru_cache
from pyproj import Transformer
from collections import Counter,defaultdict
from shapely.geometry import shape,mapping,LineString,Point
from shapely.ops import transform,nearest_points
from src.frozen_scene.native_adapter import Source
ROOT=Path(__file__).resolve().parents[1]
TO_METRIC=Transformer.from_crs(4326,32651,always_xy=True).transform

def _read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def _context_features(source,scene_id):
    """Original source objects only; no scene graphs, basemap or buffered footprints."""
    rows=[];unresolved=[]
    for obj in [*source.ways.values(),*source.relations.values()]:
        tags=obj.get('tags',{});sid=f"{obj['type']}/{obj['id']}"
        # Highway ways are supplied once by the complete independent line export.
        if obj['type']=='way'and tags.get('highway'):continue
        area=(obj['type']=='relation'and tags.get('type')=='multipolygon')or(tags.get('area')=='yes'or
            tags.get('building')not in(None,'no')or tags.get('building:part')not in(None,'no')or
            any(k in tags for k in('landuse','landcover','leisure'))or tags.get('natural')in{'water','wetland','wood'})
        try:
            g=source.area(sid)if area else LineString([source.projected[n]for n in obj.get('nodes',[])])if obj['type']=='way'and len(obj.get('nodes',[]))>=2 and all(n in source.projected for n in obj['nodes'])else None
        except Exception:g=None
        if g is None:
            unresolved.append({'id':sid,'tags':tags,'reason':'SOURCE_GEOMETRY_NOT_RESOLVABLE_WITHOUT_INVENTING_COORDINATES'})
            continue
        if tags.get('building')not in(None,'no')or tags.get('building:part')not in(None,'no'):kind='BUILDING';layer='hard'
        elif tags.get('landuse')in{'grass','flowerbed','flower_bed','meadow'}or tags.get('landcover')in{'grass','flowerbed'}:kind='GRASS';layer='background'
        elif tags.get('natural')in{'water','wetland'}or tags.get('water'):kind='WATER';layer='hard'
        elif tags.get('barrier'):kind='BARRIER';layer='hard'
        elif tags.get('leisure')in{'park','garden','recreation_ground'}or tags.get('landuse')in{'forest'}or tags.get('natural')=='wood':kind='PARK';layer='support'
        else:kind='SOURCE_CONTEXT';layer='source'
        rows.append({'type':'Feature','geometry':mapping(g),'properties':{'id':sid,'source_id':sid,'tags':tags,
            'source_version':obj.get('version'),'kind':kind,'layer':layer,'geometry_role':'SOURCE_CONTEXT','scene_id':scene_id}})
    for number,obj in source.nodes.items():
        tags=obj.get('tags',{})
        if not tags:continue
        role='UNCHANGED_REGISTERED_DOOR'if scene_id=='sh-huangpu-01'and number in{6897141353,6897145227}else'SOURCE_TAGGED_NODE'
        rows.append({'type':'Feature','geometry':mapping(Point(source.projected[number])),'properties':{
            'id':f'node/{number}','source_id':f'node/{number}','tags':tags,'source_version':obj.get('version'),
            'kind':'SOURCE_NODE','layer':'source','geometry_role':role,'scene_id':scene_id}})
    return rows,unresolved

@lru_cache(maxsize=6)
def diagnosis_data(scene_id):
    folder=ROOT/'data/connectivity';face_path=folder/f'{scene_id}_faces.json'
    if not face_path.is_file():return {'type':'FeatureCollection','features':[],'scene_id':scene_id,'status':'SOURCE_DIAGNOSTIC_NOT_YET_AVAILABLE'}
    manifest=next((r for r in _read(ROOT/'data/scene_manifest.json')['scenes']if r['scene_id']==scene_id),None)
    if manifest is None:raise ValueError('UNKNOWN_SCENE')
    source=Source(_read(ROOT/manifest['source_path']))
    faces=_read(face_path);relations=_read(folder/f'{scene_id}_relations.json')
    rejected_path=folder/f'{scene_id}_rejected_relations.json'
    rejected_relations=_read(rejected_path)if rejected_path.is_file()else[]
    by_line=defaultdict(list)
    for relation in relations+rejected_relations:
        if relation['kind']=='FACE_LINE':by_line[relation['b_source_id']].append(relation)
    population=_read(folder/f'{scene_id}_inventory_summary.json');features=[]
    for face in faces:
        props={'id':face['source_id'],'source_id':face['source_id'],'tags':face['tags'],'status':face['status'],
            'old_population':face['source_id']in population['old_area_ids'],'source_clip_sha256':manifest['source_sha256'],
            'scene_id':scene_id,'source_metrics':face.get('source_metrics'),'metrics':face.get('metrics'),'ring_audit':face.get('ring_audit')}
        for field,role in(('source_geometry','SOURCE_P'),('omega','LEGAL_OMEGA')):
            features.append({'type':'Feature','geometry':face[field],'properties':{**props,'geometry_role':role}})
    for line in _read(folder/f'{scene_id}_native_lines.json'):
        if line['geometry']is None:continue
        features.append({'type':'Feature','geometry':line['geometry'],'properties':{k:v for k,v in line.items()if k!='geometry'}|{
            'id':line['source_id'],'geometry_role':'INDEPENDENT_NATIVE_SOURCE_LINE','scene_id':scene_id,
            'kind':'ROAD'if line['tags'].get('highway')in{'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road'}else'NATIVE_WALKWAY',
            'layer':'linear','relations':by_line.get(line['source_id'],[])}})
    context,unresolved=_context_features(source,scene_id);features.extend(context)
    for feature in features:feature['properties'].update(display_crs='EPSG:32651',display_only_reprojection=False)
    why=[r for r in relations+rejected_relations if r['P']['class']in{'NONZERO_GAP','POINT_TOUCH','EMPTY_GEOMETRY'}or
         r['separation_introduced_by_omega']or not r['a_ground_permission_eligible']or not r['b_ground_permission_eligible']]
    result={'type':'FeatureCollection','features':features,'scene_id':scene_id,'working_crs':'EPSG:32651',
        'user_observation':'PENDING_USER_OBSERVATION','screenshot_request_binding':'SCREENSHOT_REQUEST_UNBOUND',
        'status':'FROZEN_SOURCE_DIAGNOSTIC_READY','source_clip_sha256':manifest['source_sha256'],
        'source_population':population,'raw_relations':relations,'rejected_source_relations':rejected_relations,
        'why_not_connected':why,'relation_summary':dict(Counter(r['omega']['class']for r in relations)),
        'unresolved_source_geometry':unresolved,'all_source_geometry_role':'RAW_SOURCE_OBJECTS_NO_INVENTED_BASEMAP',
        'note':'原生对象诊断；P、Ω及原生线直接读取EPSG:32651冻结输出。真实接图和路线使用另由当前求路结果报告。'}
    if scene_id=='sh-huangpu-01':
        south=next((shape(f['geometry'])for f in features if f['properties'].get('source_id')=='relation/2385771'and f['properties'].get('geometry_role')=='SOURCE_P'),None)
        east=next((shape(f['geometry'])for f in features if f['properties'].get('source_id')=='way/564255372'and f['properties'].get('geometry_role')=='INDEPENDENT_NATIVE_SOURCE_LINE'),None)
        door=next((shape(f['geometry'])for f in features if f['properties'].get('id')=='node/6897141353'and f['properties'].get('geometry_role')=='UNCHANGED_REGISTERED_DOOR'),None)
        if south is not None and east is not None:
            a,b=nearest_points(south,east);result['focus_xy']=[(a.x+b.x)/2,(a.y+b.y)/2]
        if door is not None:result['registered_door_xy']=list(door.coords[0])
    return result
