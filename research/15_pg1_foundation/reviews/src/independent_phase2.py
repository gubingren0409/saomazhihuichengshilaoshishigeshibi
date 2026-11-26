"""Independently census retained candidate files, atlas SVG vertices and split IDs."""
from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
from shapely.geometry import shape,box
from datetime import datetime,timezone
import csv,gzip,hashlib,json,math,re,zipfile,os

ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'phase2'
class Atlas(HTMLParser):
    def __init__(self):super().__init__();self.scene=None;self.group=None;self.depth=0;self.title=False;self.entries=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='section':self.scene=a.get('id')
        if tag=='g':
            if self.group:self.depth+=1
            elif a.get('class','').startswith('layer-'):self.group={'scene':self.scene,'layer':a['class'][6:],'title':'','paths':[]};self.depth=1
        if self.group and tag=='title':self.title=True
        if self.group and tag=='path':self.group['paths'].append(a['d'])
    def handle_data(self,data):
        if self.group and self.title:self.group['title']+=data
    def handle_endtag(self,tag):
        if tag=='title':self.title=False
        if tag=='g'and self.group:
            self.depth-=1
            if not self.depth:self.entries.append(self.group);self.group=None
        if tag=='section':self.scene=None
parser=Atlas();parser.feed((DATA/'index.html').read_text(encoding='utf8'))
atlas={}
for item in parser.entries:
    item['title']=json.loads(item['title']);ident=item['title']['source_object_id']
    atlas.setdefault((item['scene'],item['layer'],ident),[]).append(item)
registry=json.loads((DATA/'candidate_registry.json').read_text(encoding='utf8'))
audit=json.loads((DATA/'layer_audit.json').read_text(encoding='utf8'))
log=[json.loads(l)for l in(DATA/'request_log.jsonl').read_text(encoding='utf8').splitlines()]
checks=[];ids={};all_vertices=0
number=re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?')
for scene in registry:
    sid=scene['scene_id'];ids[sid]=set();count=Counter();actual_bounds=[];duplicates=[]
    west,south,east,north=scene['bounds_wsen'];cosine=math.cos(math.radians((south+north)/2));scale=940/((east-west)*cosine)
    assert scene['evaluation_split']=='UNASSIGNED_NOT_FROZEN' and scene['target_building_object_id']=='UNKNOWN'
    assert scene['entrance_count']=='UNKNOWN' and scene['registered_entrance_reference_status']=='NOT_ACQUIRED'
    assert scene['status'].startswith('EXPOSED_') and all(t!='GOLD'for t in scene['dimensions'].values())
    for member,digest in scene['source_hashes'].items():
        p=DATA/member;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
        assert any(r['path']==member and r['sha256']==digest and r['status']=='RETAINED'for r in log)
        source=json.loads(p.read_text(encoding='utf8'));layer=p.stem.replace('_crsfix','').split('_')[-1]
        count[layer]=len(source['features']);assert count[layer]==scene['object_counts'][layer]
        layerrow=next(r for r in audit if r['scene_id']==sid and r['layer']==layer)
        assert layerrow['features']==count[layer]
        null=invalid=outside=holes=0
        for feature in source['features']:
            props=feature.get('properties')or{};native=feature.get('id')
            if native is None:native=next((props[k]for k in ['objectid','source_id','id']if props.get(k)is not None),'UNKNOWN')
            ident=f"{scene['provider']}:{layer}:{native}"
            if ident in ids[sid]:duplicates.append(ident)
            ids[sid].add(ident)
            if not feature.get('geometry'):null+=1;continue
            g=shape(feature['geometry']);actual_bounds.append(g.bounds);invalid+=int(not g.is_valid);outside+=int(not g.intersects(box(west,south,east,north)))
            polygons=list(g.geoms)if g.geom_type=='MultiPolygon'else[g]
            holes+=sum(len(p.interiors)for p in polygons)
            rendered=atlas[(sid,layer,ident)].pop(0)
            assert rendered['title']['properties']==props
            # Derive display coordinates directly from all original rings.
            expected=[]
            for polygon in polygons:
                for ring in [polygon.exterior,*polygon.interiors]:
                    for x,y,*_ in ring.coords:expected.extend([30+(x-west)*cosine*scale,30+(north-y)*scale])
            actual=[float(v)for path in rendered['paths']for v in number.findall(path)]
            assert len(actual)==len(expected) and max((abs(a-b)for a,b in zip(actual,expected)),default=0)<1e-6
            all_vertices+=len(actual)//2
        assert [null,invalid,outside,holes]==[layerrow[k]for k in ['geometry_null','geometry_invalid','features_not_intersecting_request_bbox','polygon_inner_rings']]
    assert ids[sid]==set(scene['source_object_ids'])
    envelope=[min(b[0]for b in actual_bounds),min(b[1]for b in actual_bounds),max(b[2]for b in actual_bounds),max(b[3]for b in actual_bounds)]if actual_bounds else None
    assert envelope==scene['observed_geometry_bounds_wsen']
    if not actual_bounds:assert all(t=='BRONZE'for t in scene['dimensions'].values())
    checks.append({'scene_id':sid,'verified_real_feature_counts':dict(count),'verified_unique_source_ids':len(ids[sid]),'duplicate_source_ids':sorted(set(duplicates)),'target_building_denominator':0,'registered_entrance_denominator':0,'metadata_only':not actual_bounds})
assert all(not entries for entries in atlas.values())
dev=json.loads(gzip.decompress((ROOT/'phase1/development_source_identity.json.gz').read_bytes()))['scenes']
with zipfile.ZipFile(Path(os.environ.get('PG1_REVIEW_R1_ZIP',ROOT.parent/'PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')))as z:
    for scene in dev:
        sid=scene['scene_id'];raw=json.loads(z.read(f'data/scenes/{sid}/source.osm.json'));sourceids={f"{o['type']}/{o['id']}"for o in raw['elements']}
        assert sourceids==set(scene['object_ids']);ids[sid]=sourceids
pairs=list(csv.DictReader((DATA/'spatial_pairs.csv').open(encoding='utf-8-sig',newline='')))
assert len(pairs)==55
numeric_pairs=unknown_pairs=0
for pair in pairs:
    a,b=pair['scene_a'],pair['scene_b']
    if pair['shared_observed_ids']=='UNKNOWN':
        assert pair['same_source_namespace']=='False' or not ids[a] or not ids[b]
        unknown_pairs+=1
    else:
        assert len(ids[a]&ids[b])==int(pair['shared_observed_ids']);numeric_pairs+=1
groups=json.loads((DATA/'spatial_groups.json').read_text(encoding='utf8'))
assert groups['freeze_performed']is False and groups['independence_pass_count']==0
assert len(groups['groups'])==3 and sorted(len(g['members'])for g in groups['groups'])==[2,3,6]
assert all(not g['eligible_for_blind']and not g['eligible_for_frozen_validation']for g in groups['groups'])
vectors=[r for r in log if r['path'].startswith('samples/')]
retained=[r for r in vectors if r['status']=='RETAINED']
known=sum(r.get('bytes_received',0)for r in vectors)
unknown=[r['path']for r in vectors if r.get('bytes_received')is None]
out={'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'independent raw count/tag/geometry/atlas ring coordinates/hash/native-ID split checks; no author functions or new map acquisition','scenes':checks,'atlas_vertices_checked':all_vertices,'pairwise_id_checks':{'all_pairs':55,'numeric_source_intersections':numeric_pairs,'correctly_uncomparable_or_missing_ids':unknown_pairs},'provisional_groups':3,'frozen_splits':0,'new_candidates_suitable_for_blind':0,'requests':{'all_logged_requests':len(log),'vector_requests':len(vectors),'retained_vector_requests':len(retained),'failed_vector_requests':len(vectors)-len(retained),'known_vector_response_bytes':known,'unknown_vector_byte_paths':unknown,'unknown_OSM_reserved_bytes':3000000,'budget_accounting_estimate_bytes':known+3000000,'actual_total_vector_transfer_bytes':'UNKNOWN','reserve_is_not_proven_network_upper_bound':True,'legacy_sentinel_accounting_excess_bytes':1},'field_or_reference_truth_verified':False,'status':'PASS_FOR_BOUNDED_DISCOVERY_EVIDENCE_AND_NO_FROZEN_SPLIT_SCOPE'}
(ROOT/'reviews/independent_phase2.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'real_features':sum(sum(s['verified_real_feature_counts'].values())for s in checks),'atlas_vertices':all_vertices,'pairs':55,'vector_requests':len(vectors),'budget_bytes':known+3000000}))
