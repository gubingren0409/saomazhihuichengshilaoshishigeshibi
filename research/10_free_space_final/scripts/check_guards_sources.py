"""Source-level independent-method checks of exported guards (data-role self-check).

Does not call prepare_common.export_guard or the main classifier/router. Exact
same-file ID/geometry checks are useful, but this is not field validation or an
independent review of this role's own data contract.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape

ROOT=Path(__file__).resolve().parents[1]
MOTOR={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road'}
project=Transformer.from_crs(4326,32651,always_xy=True).transform


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-dir',type=Path,required=True);args=p.parse_args()
    frozen=ROOT/'frozen_context'
    manifest=read(frozen/'data/task_manifest.json')['instances']
    byid={r['id']:r for r in manifest}
    n=read(frozen/'data/e5/task_manifest.json')['instances'][0];byid[n['id']]=n
    rows=[]
    for clip in sorted(args.source_dir.glob('*.osm.json')):
        raw=read(clip);nodes={e['id']:e for e in raw['elements'] if e['type']=='node'}
        ways={e['id']:e for e in raw['elements'] if e['type']=='way'}
        for path in sorted((ROOT/'data/common_guards_v2').glob('*.json')):
            guard=read(path)
            if guard['source_clip']!=clip.name:continue
            observed_path=frozen/byid[guard['id']]['observed'];obs=read(observed_path)
            failures=[];checked=[]
            if sign(clip)!=guard['source_sha256']:failures.append('SOURCE_HASH')
            if sign(observed_path)!=guard['observed_sha256']:failures.append('OBSERVED_HASH')
            disk=Point(obs['domain']['anchor_xy']).buffer(byid[guard['id']]['context_radius_m'],quad_segs=32)
            for r in guard['road_centerlines']:
                ident=int(r['source_id'].split('/')[1]);w=ways[ident]
                if r['tags']!=w.get('tags',{}):failures.append(('TAGS',ident))
                xy=[project(nodes[k]['lon'],nodes[k]['lat']) for k in w['nodes']]
                expected=LineString(xy).intersection(disk);got=shape(r['geometry'])
                err=expected.hausdorff_distance(got)
                if err>1e-7 or abs(expected.length-got.length)>1e-7:failures.append(('GEOMETRY',ident,err))
                if set(r)&{'nodes','members'}:failures.append(('RAW_MEMBERS',ident))
                checked.append({'source_id':r['source_id'],'geometry_hausdorff_m':err,'source_tag_match':r['tags']==w.get('tags',{}),'length_m':got.length})
            for barrier,gates in guard.get('barrier_gates',{}).items():
                way=ways[int(barrier.split('/')[1])]
                for gate in gates:
                    ident=int(gate['id'].split('/')[1]);node=nodes[ident]
                    if ident not in way['nodes']:failures.append(('GATE_NOT_INCIDENT',gate['id']))
                    if Point(project(node['lon'],node['lat'])).distance(Point(gate['xy']))>1e-7:failures.append(('GATE_COORD',gate['id']))
            old_motor={e['source_id'] for e in obs['edges'] if e.get('tags',{}).get('highway') in MOTOR}
            source_road={r['source_id'] for r in guard['road_centerlines']}
            domain=Point(obs['domain']['anchor_xy']).buffer(30,quad_segs=32)
            valid=domain.intersection(shape(guard['coverage_geometry']))
            rows.append({'id':guard['id'],'guard_sha256':sign(path),'source_sha256':sign(clip),
                'road_count':len(checked),'source_geometry_checks':checked,
                'extra_road_ids_not_in_old_observed_graph':sorted(source_road-old_motor),
                'valid_coverage_m2':valid.area,'unavailable_domain_m2':domain.difference(valid).area,
                'barrier_gate_count':sum(map(len,guard.get('barrier_gates',{}).values())),
                'failures':failures,'status':'PASS' if not failures else 'FAIL'})
    doc={'role':'DATA_CONSTRAINT_BUILDER_SELF_CHECK_INDEPENDENT_GEOMETRY_METHOD',
        'scope':'55_EXPORTED_INPUTS_EXACT_RAW_TAGS_AND_GEOMETRY; NO_REFERENCE_READ; NOT_REAL_WORLD_COMPLETENESS',
        'status':'PASS' if len(rows)==55 and all(r['status']=='PASS' for r in rows) else 'FAIL',
        'input_count':len(rows),'rows':rows}
    with (ROOT/'audits/common_guard_source_review.json').open('x',encoding='utf-8') as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':doc['status'],'inputs':len(rows),'road_records':sum(r['road_count'] for r in rows),
                      'inputs_with_new_road_guards':sum(bool(r['extra_road_ids_not_in_old_observed_graph']) for r in rows),
                      'unavailable_m2':sum(r['unavailable_domain_m2'] for r in rows)}))


if __name__=='__main__':main()
