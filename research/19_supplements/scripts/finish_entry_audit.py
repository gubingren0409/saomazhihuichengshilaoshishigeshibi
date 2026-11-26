from pathlib import Path
import csv,json,hashlib,zipfile,sys,math
from shapely.geometry import shape,Point,LineString,box,mapping
from shapely.ops import transform
ROOT=Path(__file__).resolve().parents[1];RT=ROOT/'frozen_runtime';D=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';sys.path.insert(0,str(RT))
from src.frozen_scene.native_adapter import Source,PROJECT
def csvout(name,rows):
 with(D/name).open('w',encoding='utf-8-sig',newline='')as f:
  fields=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in r.items()})
meta=json.loads((RT/'data/scene_manifest.json').read_text(encoding='utf-8'));requests=json.loads((D/'outputs/fixed_requests_before_execution.json').read_text(encoding='utf-8'));identity=list(csv.DictReader((D/'entry_identity_audit.csv').open(encoding='utf-8-sig')));comparisons=list(csv.DictReader((D/'target_definition_comparison.csv').open(encoding='utf-8-sig')))
oldzip=ROOT.parent/'PG1_RESUME_STREET_SIDE_R1/delivery/PG1_RESUME_STREET_SIDE_R1_REVIEW_FIXED.zip'
with zipfile.ZipFile(oldzip)as z:old=json.loads(z.read('audit/window_lock.json'))
newzip=ROOT.parent/'PG1_MAP_CONTEXT_RECONSTRUCTION_R2/delivery/OPEN_REVIEW.zip'
assert hashlib.sha256(newzip.read_bytes()).hexdigest()=='8a14afa8e2d39436c5a4365b35897e5c523e0e5a49785d1663373b7a7d2a1b98'
with zipfile.ZipFile(newzip)as z:new=json.loads(z.read('audit/window_definition.json'))
windows=old.get('windows',[]);native=next(w for w in windows if w.get('window_id',w.get('id'))=='native')if any(w.get('window_id',w.get('id'))=='native'for w in windows)else windows[0]
oldbox=native.get('bounds_xy',native.get('bounds'))
checks=[];access=[];source_cache={}
for i,req in enumerate(requests):
 row=next(s for s in meta['scenes']if s['scene_id']==req['scene_id'])
 if req['scene_id']not in source_cache:source_cache[req['scene_id']]=Source(json.loads((RT/row['source_path']).read_text(encoding='utf-8')))
 source=source_cache[req['scene_id']];sc=json.loads((RT/'data/scenes'/req['scene_id']/'frozen_scene.json').read_text(encoding='utf-8-sig'));g=source.area(sc['building_native_id']);frozen=transform(PROJECT,shape(sc['building_footprint']))
 door=source.nodes[int(req['door_id'].split('/')[1])];p=Point(PROJECT(door['lon'],door['lat']))
 check={'scene_id':req['scene_id'],'entrance_id':req['door_id'],'raw_building_id':sc['building_native_id'],'footprint_symmetric_difference_m2':g.symmetric_difference(frozen).area,'raw_boundary_distance_m':g.boundary.distance(p),'status':'PASS'if g.symmetric_difference(frozen).area<=1e-6 and g.boundary.distance(p)<=1e-6 else'FAIL','old_native_window_intersects_building':box(*oldbox).intersects(g)if req['scene_id']=='sh-huangpu-01'and oldbox else None,'old_window_role':'Wrong northwest sidewalk diagnostic, not target museum'if req['scene_id']=='sh-huangpu-01'else'NOT_APPLICABLE_DIFFERENT_HISTORICAL_WINDOW','latest_target_source':'PG1_MAP_CONTEXT_RECONSTRUCTION_R2 Museum identity; frozen original library contract','public_opening':'UNKNOWN','physical_door':'UNKNOWN'}
 checks.append(check)
 existing=[r for r in comparisons if r['scene_id']==req['scene_id']and r['entrance_id']==req['door_id']]
 reg=next(r for r in existing if r['target_definition']=='REGISTERED_DOOR');outer=next(r for r in existing if r['target_definition']=='NATIVE_OUTSIDE_APPROACH_POINT');centroid=next(r for r in existing if r['target_definition']=='BUILDING_CENTROID')
 access.append({'scene_id':req['scene_id'],'entrance_id':req['door_id'],'status':'PASS'if check['status']=='PASS'else'INVALID_INPUT','identity_valid':check['status']=='PASS','centroid_status':centroid['status'],'registered_route_m':reg['route_length_m'],'outer_route_m':outer['route_length_m'],'outer_point_to_registered_door_m':outer['endpoint_to_registered_door_m'],'result_code':'SUPPORTS_ACCESS_COMPLETION'if reg['route_length_m']!=outer['route_length_m']or centroid['status']!=reg['status']else'NO_EXTRA_BUSINESS_GAIN_OBSERVED_FOR_THIS_REQUEST','limitations':'Same-point library comparison is not evidence that access completion lacks value; no field facts confirmed'})
 # A truthful local source map for the new route plots, not an external image.
 start=json.loads((D/f'outputs/Q2-TARGET-{i}-REGISTERED_DOOR.json').read_text(encoding='utf-8'))['route']['segments'][0]['xy'][0]
 window=box(min(start[0],p.x,g.bounds[0])-65,min(start[1],p.y,g.bounds[1])-65,max(start[0],p.x,g.bounds[2])+65,max(start[1],p.y,g.bounds[3])+65)
 features=[]
 for kind,objects in [('way',source.ways),('relation',source.relations)]:
  for number,obj in objects.items():
   tags=obj.get('tags',{});sid=f'{kind}/{number}';cat='building'if tags.get('building')not in(None,'no')else'walkable_area'if tags.get('area')=='yes'and tags.get('highway')in('pedestrian','footway')else'grass'if tags.get('landuse')=='grass'or tags.get('natural')=='grassland'else'water'if tags.get('natural')=='water'else'barrier'if tags.get('barrier')else'line'if tags.get('highway')else None
   if cat is None:continue
   geom=None
   if cat in('building','walkable_area','grass','water'):geom=source.area(sid)
   if geom is None and kind=='way':
    ns=obj.get('nodes',[])
    if len(ns)>=2 and all(n in source.projected for n in ns):geom=LineString([source.projected[n]for n in ns])
   if geom is not None and geom.intersects(window):features.append({'type':'Feature','geometry':mapping(geom),'properties':{'source_id':sid,'category':cat,'tags':tags,'target':sid==sc['building_native_id']}})
 fc={'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'features':features,'bounds':list(window.bounds),'door_xy':[p.x,p.y],'start_xy':start,'door_id':req['door_id'],'building_id':sc['building_native_id'],'source_sha256':row['source_sha256']}
 (D/f'outputs/context_{i}.geojson').write_text(json.dumps(fc,ensure_ascii=False),encoding='utf-8')
csvout('window_binding_audit.csv',checks);csvout('entry_access_value.csv',access)
(D/'outputs/window_definition_sources.json').write_text(json.dumps({'old_window_definition':native,'latest_window_definition':new},ensure_ascii=False,indent=2),encoding='utf-8')
print('ENTRY_GEOMETRY_AND_CONTEXT_FINALIZED',len(checks))
