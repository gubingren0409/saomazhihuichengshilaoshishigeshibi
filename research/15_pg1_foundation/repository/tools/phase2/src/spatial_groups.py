"""Conservative geographic/network leakage audit. No split assignment or freezing.
The buffer is a discovery guard, not evidence that unobserved network dependencies end.
"""
import argparse, csv, gzip, hashlib, itertools, json, math, pathlib
from shapely.geometry import box
from shapely.ops import transform

def run(root, development, buffer_m):
    root=pathlib.Path(root);development=pathlib.Path(development)
    data=development.read_bytes();dev=json.loads(gzip.decompress(data) if development.suffix=='.gz' else data)
    scenes=[]
    for r in dev['scenes']:
        scenes.append(dict(scene_id=r['scene_id'],city='Shanghai',provider='OSM',bounds=r['bounds_wsen'],ids=set('OSM:'+x for x in r['object_ids']),split='DEVELOPMENT',group='DEVELOPMENT_SHANGHAI_SHARED_NATIVE_IDS',geometry_observed=True))
    for r in json.loads((root/'candidate_registry.json').read_text(encoding='utf-8')):
        scenes.append(dict(scene_id=r['scene_id'],city=r['city'],provider=r['provider'],bounds=r['observed_geometry_bounds_wsen'] or r['bounds_wsen'],ids=set(r['source_object_ids']),split='UNASSIGNED_NOT_FROZEN',group=r['provisional_group'],geometry_observed=bool(r['observed_geometry_bounds_wsen'])))
    parent={r['scene_id']:r['scene_id'] for r in scenes}
    def find(a):
        while parent[a]!=a:a=parent[a]
        return a
    def union(a,b): parent[find(b)]=find(a)
    pairs=[]
    for a,b in itertools.combinations(scenes,2):
        same_namespace=a['provider']==b['provider']; shared=len(a['ids']&b['ids']) if same_namespace and a['geometry_observed'] and b['geometry_observed'] else 'UNKNOWN'
        overlap=box(*a['bounds']).intersects(box(*b['bounds']))
        # Local display-style planar distance is used only for nearby same-city
        # conservative screening. Far/cross-city geodesic values are not fabricated.
        distance='NOT_COMPUTED_CROSS_CITY'; buffered=False
        if a['city']==b['city']:
            lat=sum([a['bounds'][1],a['bounds'][3],b['bounds'][1],b['bounds'][3]])/4
            project=lambda x,y,z=None:(x*111320*math.cos(math.radians(lat)),y*111320)
            distance=round(transform(project,box(*a['bounds'])).distance(transform(project,box(*b['bounds']))),3)
            buffered=distance<=buffer_m*2
        reasons=[]
        if isinstance(shared,int) and shared>0:reasons.append('SHARED_OBSERVED_NATIVE_OBJECT_IDS')
        if overlap:reasons.append('GEOMETRY_ENVELOPE_OVERLAP')
        if buffered:reasons.append('500M_EACH_DEPENDENCY_ENVELOPE_CONTACT')
        if a['city']==b['city']:reasons.append('SAME_CITY_NETWORK_CLOSURE_UNKNOWN_CONSERVATIVE_GROUP')
        if reasons:union(a['scene_id'],b['scene_id'])
        pairs.append(dict(scene_a=a['scene_id'],scene_b=b['scene_id'],same_source_namespace=same_namespace,shared_observed_ids=shared,geometry_envelope_overlap=overlap,envelope_distance_m=distance,buffer_each_m=buffer_m,buffered_envelope_contact=buffered,group_reasons='|'.join(reasons),network_reference_complete=False,independence_status='MUST_GROUP' if reasons else 'PROVISIONAL_GEOGRAPHIC_SEPARATION_NETWORK_REFERENCE_UNKNOWN',split_frozen=False))
    groups={}
    for r in scenes:groups.setdefault(find(r['scene_id']),[]).append(r['scene_id'])
    out=[]
    for i,members in enumerate(groups.values(),1):
        out.append(dict(group_id=f'PROVISIONAL_GROUP_{i:02}',members=members,split='DEVELOPMENT' if any(next(s for s in scenes if s['scene_id']==m)['split']=='DEVELOPMENT' for m in members) else 'UNASSIGNED_NOT_FROZEN',network_reference_complete=False,building_reference_complete=False,eligible_for_frozen_validation=False,eligible_for_blind=False))
    with (root/'spatial_pairs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
    (root/'spatial_groups.json').write_text(json.dumps(dict(groups=out,buffer_each_m=buffer_m,buffer_rationale='500m discovery guard surrounds whole observed feature envelopes; no observed road network closure, therefore same-city candidates remain grouped regardless of this distance. This is a proposal, not accepted task semantics.',development_identity_sha256=hashlib.sha256(data).hexdigest(),pair_count=len(pairs),independence_pass_count=0,freeze_performed=False),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Pairs',len(pairs),'conservative groups',len(out),'independence PASS 0; split freeze false')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=pathlib.Path);p.add_argument('--development',required=True,type=pathlib.Path);p.add_argument('--buffer-m',type=float,default=500);a=p.parse_args();run(a.root,a.development,a.buffer_m)
