"""Independent check of saved-result to embedded-map coordinates and identities.

This checker does not import the rendering implementation. It reconstructs the
inverse SVG affine transform and checks all displayed cells/route vertices.
It verifies the presentation contract, not real-world walkability.
"""
import argparse
import base64
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from shapely.geometry import LineString, shape

ROOT=Path(__file__).resolve().parents[1]
NUMBER=r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def source_vertices(g):
    def flatten(coords):
        if coords and isinstance(coords[0],(int,float)):
            yield tuple(coords[:2])
        else:
            for child in coords:
                yield from flatten(child)
    if g['type']=='GeometryCollection':
        for child in g['geometries']:
            yield from source_vertices(child)
    else:
        yield from flatten(g.get('coordinates',[]))


def drawn_vertices(features,anchor):
    for f in features:
        for piece in f['shape']:
            if 'point' in piece:
                x,y=piece['point'];yield (anchor[0]+x,anchor[1]-y)
            if 'd' in piece:
                nums=[float(x) for x in re.findall(NUMBER,piece['d'])]
                assert len(nums)%2==0
                for i in range(0,len(nums),2):
                    yield (anchor[0]+nums[i],anchor[1]-nums[i+1])


def check(root):
    text=(root/'visuals/index.html').read_text(encoding='utf-8')
    encoded=re.search(r'<script type="text/plain" id="payload">(.*?)</script>',text,re.S)[1]
    data=json.loads(gzip.decompress(base64.b64decode(encoded)))
    if data.get('surfaces'):
        for model in data['models']:
            model.update(data['surfaces'][model['surface_index']])
    manifest=read(root/'data/task_manifest.json')
    byid={x['id']:x for x in manifest['instances']}
    rows=[];max_error=0;vertices=0
    for parent,c in data['cases'].items():
        anchor=c['anchor']
        for values in c['inputs'].values():
            for item in values.values():
                original=byid[item['id']]
                assert sha256((root/original['observed']).read_bytes()).hexdigest()==item['observed_sha256']
                mappings={**item['models'],**item.get('historical_models',{})}
                for method,index in mappings.items():
                    model=data['models'][index]
                    pred=read(root/model['prediction_path']) if model.get('prediction_path') else read(root/'data/predictions'/item['id']/(method+'.json'))
                    assert pred['surface']['sha256']==model['sha256']
                    source={x['region_id']:x for x in pred['surface']['cells']}
                    assert len(source)==len(model['cells'])
                    for cell in model['cells']:
                        props=cell['props'];src=source[props['region_id']]
                        for field in ('source_evidence_state','planning_state','policy_id','constraint_ids','map_coverage_status'):
                            assert props.get(field)==src.get(field),(item['id'],method,field)
                        actual=list(drawn_vertices([cell],anchor));expected=list(source_vertices(src['geometry']))
                        assert len(actual)==len(expected)
                        for a,b in zip(actual,expected):
                            d=math.dist(a,b);max_error=max(max_error,d);vertices+=1
                            assert d<=.000708,(item['id'],method,d)
                    segments=0
                    for q,r in model['routes'].items():
                        expected=[]
                        for e in pred['routes'][q].get('edges',[]):
                            if len(e.get('xy',[]))>=2 and math.dist(e['xy'][0],e['xy'][-1])>1e-6:
                                expected.extend(e['xy']);segments+=1
                        actual=list(drawn_vertices(r['lines'],anchor))
                        assert len(actual)==len(expected)
                        assert r.get('length_m')==pred['routes'][q].get('length_m')
                        for a,b in zip(actual,expected):
                            d=math.dist(a,b);max_error=max(max_error,d);vertices+=1
                            assert d<=.000708,(item['id'],method,q,d)
                    rows.append({'input_id':item['id'],'method':method,'cells':len(source),'route_segments':segments})
                if 'F0' in item['models'] and 'F1' in item['models']:
                    a,b=(data['models'][item['models'][m]] for m in ('F0','F1'))
                    assert a['sha256']==b['sha256'] and a['cells']==b['cells']
                    assert a['graph_sha256']==b['graph_sha256']
                if item.get('historical_models'):
                    a,b=(data['models'][item['historical_models']['R0-'+m]] for m in ('F0','F1'))
                    assert a['sha256']==b['sha256'] and a['cells']==b['cells'] and a['graph_sha256']==b['graph_sha256']
    post_record=None
    post=data.get('post_audit')
    if post:
        table=root/'data/access_area_interpretations.json';impact=root/'audits/access_area_prediction_impact.json'
        assert sha256(table.read_bytes()).hexdigest()==post['source_table_sha256']
        assert sha256(impact.read_bytes()).hexdigest()==post['impact_table_sha256']
        area=next(a for a in read(table)['areas'] if a['source_id']==post['source_id'])
        assert area['source_tags']['access']=='private' and area['source_tags']['amenity']=='parking'
        case=data['cases'][post['case']];features=case['post_audit_features']
        fixed=bool(post.get('fixed'))
        assert len(features)==1 and features[0]['props']['predictor_input'] is fixed
        assert features[0]['props']['observation']==('SOURCE_RESTRICTION_V3_PARITY_REVIEW' if fixed else 'POST_AUDIT_SOURCE_RESTRICTION')
        a=list(drawn_vertices(features,case['anchor']));b=list(source_vertices(area['geometry']))
        assert len(a)==len(b)
        overlay_error=max(math.dist(x,y) for x,y in zip(a,b));assert overlay_error<=.000708
        restricted=shape(area['geometry']);state_overlaps={};route_lengths={}
        for method in ('M1-C','F0','F1'):
            pred=read(root/'data/predictions'/post['input_id']/(method+'.json'))
            assert not any('access_area' in str(r.get('path','')) for r in pred['read_log'])
            state_overlaps[method]={state:sum(shape(c['geometry']).intersection(restricted).area
                 for c in pred['surface']['cells'] if c['walkability_state']==state)
                 for state in ('NATIVE_WALKABLE','INFERRED_WALKABLE','RESTRICTED','UNKNOWN')}
            overlap=shape(pred['surface']['domain']).intersection(restricted).area
            assert abs(overlap-post['overlap_m2'])<=1e-6
            route_lengths[method]={q:sum(LineString(e['xy']).intersection(restricted.buffer(-1e-7)).length
                   for e in r.get('edges',[]) if len(e.get('xy',[]))>=2) for q,r in pred['routes'].items()}
        expected='RESTRICTED' if fixed else 'INFERRED_WALKABLE'
        assert abs(state_overlaps['F0'][expected]-post['overlap_m2'])<=1e-6
        assert abs(state_overlaps['F1'][expected]-post['overlap_m2'])<=1e-6
        assert abs(state_overlaps['M1-C']['RESTRICTED' if fixed else 'UNKNOWN']-post['overlap_m2'])<=1e-6
        assert all(length<=1e-6 for values in route_lengths.values() for length in values.values())
        post_record={'source_id':post['source_id'],'overlay_role':'V3_CURRENT_SOURCE_REVIEW_AND_R0_HISTORY' if fixed else 'POST_AUDIT_REVIEW_ONLY',
            'source_full_area_m2':restricted.area,'fixed_domain_overlap_m2':overlap,
            'state_area_overlaps_m2':state_overlaps,'route_private_interior_m':route_lengths,
            'source_overlay_coordinate_error_m':overlay_error,'new_region_builds':0,'predictions_modified':False}
    return {'status':'PASS','scope':'ALL_EMBEDDED_PREDICTION_CELL_AND_ROUTE_COORDINATES_DUAL_FIELDS_F0_F1_IDENTITIES',
            'cases':len(data['cases']),'model_payloads':len(data['models']),'checked_vertices':vertices,
            'max_coordinate_error_m':max_error,'tolerance_m':.000708,'rows':rows,'post_audit_source_restriction':post_record,
            'limitations':['SVG ordinates are rounded to 0.001m. Underlying metric prediction geometry remains authoritative.',
                           'Presentation checks do not establish physical access, missing obstacles, current levels or public permission.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args()
    result=check(args.root);p=args.root/'audits/visual_geometry_check.json';p.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
