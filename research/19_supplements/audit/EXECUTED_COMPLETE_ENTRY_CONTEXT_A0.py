from experiment_core import *
from src.frozen_scene.native_adapter import Source
from src.frozen_scene.semantics import obstacle_kind
from shapely.geometry import shape
D=ROOT/IDS['q2'];identities=list(csv.DictReader((D/'entry_identity_audit.csv').open(encoding='utf-8-sig')));manifest=json.loads((RUNTIME/'data/scene_manifest.json').read_text());cache={};rows=[]
for r in identities:
 sid=r['scene_id'];meta=next(s for s in manifest['scenes']if s['scene_id']==sid)
 if sid not in cache:
  source=Source(json.loads((RUNTIME/meta['source_path']).read_text()));objects,unlocated=source.obstacles([]);cache[sid]=(source,objects,unlocated)
 source,objects,unlocated=cache[sid];point=Point(source.coord(r['entrance_id']));contacts=[]
 for o in objects:
  g=o['geometry'];dist=g.distance(point)
  if dist<=30:contacts.append({'source_id':o['id'],'kind':obstacle_kind(o),'source_tags':o.get('tags',{}),'distance_m':dist,'point_on_boundary':g.boundary.distance(point)<=1e-6 if g.geom_type in('Polygon','MultiPolygon')else None,'point_in_interior':g.contains(point),'geometry_type':g.geom_type,'is_target_building':o['id']==r['building_id']})
 row=base_row(IDS['q2'],'Q2-SOURCE-CONTEXT-'+r['entrance_id'].replace('/','-'),sid,r['entrance_id'],'SOURCE_CONTEXT_ONLY','INCONCLUSIVE'if unlocated else'PASS');row.update(building_id=r['building_id'],result={'full_source_obstacle_contacts_within_30m':contacts,'unlocated_source_hazards':unlocated,'earlier_nearby_restrictions_column_scope':'way-line screening only; this area/node-aware source parser context supplements it','unknown_unmapped_obstacles':True,'level_is_field_verified':False},output_file='entry_constraint_context.csv');rows.append(row);append(IDS['q2'],row)
csvout(D/'entry_constraint_context.csv',rows);write(D/'outputs/entry_constraint_context.json',rows);print('ENTRY_SOURCE_CONTEXT',len(rows),[r['status']for r in rows])
