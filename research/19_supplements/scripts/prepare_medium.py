"""Merge two overlapping frozen crops by native identity; no new map acquisition."""
from experiment_core import *
import shutil,gzip
from shapely.ops import unary_union
from src.scene_data import source_coverage
D=ROOT/IDS['q8'];M=ROOT/'medium_runtime';inputs=['sh-library','sh-wukang']
manifest=json.loads((RUNTIME/'data/scene_manifest.json').read_text(encoding='utf-8'))
rows=[next(r for r in manifest['scenes']if r['scene_id']==s)for s in inputs]
objects={};owners={};conflicts=[];bounds=[];timestamps=[];enriched=[]
for row in rows:
 path=RUNTIME/row['source_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['source_sha256']
 raw=json.loads(path.read_text(encoding='utf-8'));bounds.append(raw['bounds_wsen']);timestamps.append(raw.get('osm3s',{}).get('timestamp_osm_base'))
 for obj in raw['elements']:
  key=(obj['type'],obj['id']);owners.setdefault(key,[]).append(row['scene_id'])
  if key in objects and objects[key]!=obj:
   old=objects[key];different=[k for k in set(old)&set(obj)if old[k]!=obj[k]]
   if different:conflicts.append({'source_id':f'{key[0]}/{key[1]}','versions':[old.get('version'),obj.get('version')],'conflicting_fields':different,'action':'BLOCK_INPUT_NOT_SILENTLY_RESOLVED'})
   else:
    objects[key]={**old,**obj};enriched.append({'source_id':f'{key[0]}/{key[1]}','missing_fields_completed_from_other_frozen_crop':sorted(set(old)^set(obj))})
  else:objects[key]=obj
report={'locked_at':stamp(),'input_scenes':inputs,'input_sha256':[r['source_sha256']for r in rows],'merge_rule':'Native type/id deduplication; shared fields must be identical. Fill absent metadata from the same native object in the other crop; never overwrite a conflicting coordinate/tag/version','unique_objects':len(objects),'overlapping_ids':sum(len(v)>1 for v in owners.values()),'conflicts':conflicts,'metadata_enriched_objects':enriched,'source_windows_wsen':bounds,'source_timestamps':timestamps,'derived_new_input_not_new_field_observation':True,'same_registered_target_and_start':True,'local_F0_domain_radius_m':30,'no_synthetic_connection_between_crops':True}
write(D/'outputs/medium_merge_audit.json',report)
if conflicts:raise SystemExit('MERGE_INPUT_CONFLICT; see audit')
for folder in ('src','config'):
 for p in (RUNTIME/folder).rglob('*'):
  if p.is_file()and '__pycache__'not in p.parts:
   dest=M/p.relative_to(RUNTIME);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for rel in ('data/face_selection_lock.json','data/scenes/sh-library/frozen_scene.json'):
 dest=M/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUNTIME/rel,dest)
south=min(b[1]for b in bounds);west=min(b[0]for b in bounds);east=max(b[2]for b in bounds);north=max(b[3]for b in bounds)
raw={'version':.6,'generator':'EXACT_FROZEN_CROP_UNION_EXPERIMENT_ADAPTER','bounds_wsen':[west,south,east,north],'elements':[objects[k]for k in sorted(objects)],'osm3s':{'timestamp_osm_base':timestamps[0]if len(set(timestamps))==1 else None},'experiment_provenance':report}
source_path=M/'data/scenes/sh-library/source.osm.json';write(source_path,raw)
coverage=unary_union([source_coverage(b)for b in bounds]);write(M/'data/actual_coverage_union.geojson',mapping(coverage))
# Existing mapped segments are unioned by their complete stable row, never a new line.
seen=set();mapped=[]
for row in rows:
 p=RUNTIME/row['mapped_edges_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['mapped_edges_sha256']
 with gzip.open(p,'rt',encoding='utf-8')as f:
  for line in f:
   obj=json.loads(line);sig=digest(obj)
   if sig not in seen:seen.add(sig);mapped.append(obj)
mp=M/'data/scenes/sh-library/mapped_edges.jsonl.gz'
with gzip.open(mp,'wt',encoding='utf-8')as f:
 for obj in mapped:f.write(json.dumps(obj,ensure_ascii=False)+'\n')
row={**rows[0],'source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),'mapped_edges_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'mapped_edge_count':len(mapped),'full_source_clip_bounds':raw['bounds_wsen'],'coverage_note':'Bounding box is indexing only; adapter overrides coverage with exact source-window union'}
write(M/'data/scene_manifest.json',{'crs':'EPSG:32651','channel':'DERIVED_MEDIUM_FROZEN_CROP_UNION','scene_count':1,'scenes':[row]})
report.update(status='PASS',mapped_rows=len(mapped),coverage_geometry_sha256=digest(mapping(coverage)),coverage_m2=coverage.area,derived_source_sha256=row['source_sha256'])
write(D/'outputs/medium_merge_audit.json',report)
csvout(D/'medium_object_lineage.csv',[{'source_id':f'{k[0]}/{k[1]}','source_scenes':owners[k],'source_object_sha256':digest(objects[k]),'duplicate_occurrences_removed':len(owners[k])-1}for k in sorted(objects)])
print(json.dumps(report,ensure_ascii=False))
