"""Independent six-scene raw OSM census directly from fixed R1 ZIP bytes."""
from pathlib import Path
from collections import Counter
import gzip, hashlib, itertools, json, zipfile,os
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
ZIP=Path(os.environ.get('PG1_REVIEW_R1_ZIP',ROOT.parent/'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip'))
SCENES=['sh-exhibition','sh-huangpu-01','sh-library','sh-newworld','sh-tower','sh-wukang']
rows=[]; ids={}; bounds={}; building_ids={}
with zipfile.ZipFile(ZIP) as z:
    for scene in SCENES:
        base=f'data/scenes/{scene}/'
        rawbytes=z.read(base+'source.osm.json')
        raw=json.loads(rawbytes)
        frozen=json.loads(z.read(base+'frozen_scene.json'))
        elements=raw['elements']
        ids[scene]={f"{e['type']}/{e['id']}" for e in elements}
        bounds[scene]=raw['bounds_wsen']
        building_ids[scene]=frozen['building_native_id']
        tagged=[e for e in elements if e.get('tags')]
        ways=[e for e in elements if e['type']=='way']
        nodes={e['id']:e for e in elements if e['type']=='node'}
        roadways=[e for e in ways if e.get('tags',{}).get('highway')]
        geometry_missing=[]
        for way in roadways:
            if not way.get('geometry') and not all(n in nodes for n in way.get('nodes',[])):
                geometry_missing.append(way['id'])
        graph=[json.loads(line) for line in gzip.decompress(z.read(base+'mapped_edges.jsonl.gz')).splitlines()]
        row={'scene':scene,'source_zip_member':base+'source.osm.json','source_sha256':hashlib.sha256(rawbytes).hexdigest(),'raw_total_objects':len(elements),'raw_unique_ids':len(ids[scene]),'source_duplicate_objects':len(elements)-len(ids[scene]),'raw_types':dict(Counter(e['type'] for e in elements)), 'building_native_id':building_ids[scene], 'registered_entry_native_id':frozen['entry_native_id'], 'source_bounds':bounds[scene], 'raw_highway_way_count':len(roadways),'raw_highway_classes':dict(sorted(Counter(e['tags']['highway'] for e in roadways).items())), 'raw_named_highway_way_count':sum(bool(e['tags'].get('name')) for e in roadways),'raw_highway_missing_coordinate_ways':geometry_missing,'raw_crossing_tag_objects':sum(e.get('tags',{}).get('highway')=='crossing' or 'crossing' in e.get('tags',{}) for e in elements),'raw_sidewalk_tag_objects':sum(any(k.startswith('sidewalk') for k in e.get('tags',{})) for e in elements),'raw_tagged_objects':len(tagged),'raw_access_tag_objects':sum('access' in e.get('tags',{}) for e in elements),'raw_foot_tag_objects':sum('foot' in e.get('tags',{}) for e in elements),'raw_barrier_objects':sum('barrier' in e.get('tags',{}) for e in elements),'raw_entrance_objects':sum('entrance' in e.get('tags',{}) for e in elements),'mapped_edge_records':len(graph),'mapped_edge_schema':sorted(graph[0]) if graph else []}
        rows.append(row)
    overlap=[]
    for a,b in itertools.combinations(SCENES,2):
        aw,as_,ae,an=bounds[a];bw,bs,be,bn=bounds[b]
        dx=min(ae,be)-max(aw,bw);dy=min(an,bn)-max(as_,bs)
        shared=ids[a]&ids[b]
        overlap.append({'scene_a':a,'scene_b':b,'shared_native_objects':len(shared),'shared_ways':sum(n.startswith('way/') for n in shared),'bounds_overlap_positive_area':dx>0 and dy>0,'same_target_building':building_ids[a]==building_ids[b]})
out={'at_utc':datetime.now(timezone.utc).isoformat(),'source':'fixed R1 ZIP, source objects parsed without author modules','scene_count':6,'independent_target_building_denominator':len(set(building_ids.values())),'scenes':rows,'pairwise_source_overlap':overlap,'limit':'Raw-tag census; tag absence is not physical-world absence. No performance or entrance truth labels inferred.'}
(ROOT/'reviews/independent_raw_inventory.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'scenes':6,'target_buildings':out['independent_target_building_denominator'],'raw_highway_ways':sum(r['raw_highway_way_count'] for r in rows),'pairs_with_shared_ids':sum(r['shared_native_objects']>0 for r in overlap)},ensure_ascii=False))
