"""Add only independent restrictive source areas to the affected fixed W7 input.

No reference, query, prediction, route or positive boundary exception is read.
Full negative polygons are selected using the original fixed observation window.
"""
from hashlib import sha256
import argparse
import importlib.util
import json
from pathlib import Path
import sys

from shapely.geometry import Point, mapping, shape

ROOT=Path(__file__).resolve().parents[1]
IDENT='W7a6b5a10076_G_080'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True);args=p.parse_args()
    if sign(args.adapter)!='5bcefd9a7fddfbea67c778825fdc783d3a39d304ae8729673a620faad5349b83':raise ValueError('Wrong parser')
    oldp=ROOT/'data/common_guards_v2'/f'{IDENT}.json';old=read(oldp)
    if sign(args.source)!=old['source_sha256']:raise ValueError('Wrong source')
    op=ROOT/'data/observed'/f'{IDENT}.json';obs=read(op)
    if sign(op)!=old['observed_sha256']:raise ValueError('Observed differs')
    spec=importlib.util.spec_from_file_location('v3_negative_source_area_parser',args.adapter);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod
    exec(compile(args.adapter.read_bytes(),str(args.adapter),'exec'),mod.__dict__)
    raw=read(args.source);s=mod.Source(raw)
    center=Point(obs['domain']['anchor_xy']);window=center.buffer(80,quad_segs=32)
    # Only IDs are inspected in the existing mask ledger. No hidden shape is used.
    ledger=next(json.loads(line)for line in (ROOT/'frozen_context/data/mask_dependency_ledger.jsonl').read_text().splitlines()
                if json.loads(line)['parent_task_id']=='W7a6b5a10076'and json.loads(line)['masking_mode']=='G')
    forbidden=set(ledger['removed_context_source_ids'])|set(ledger['hidden_relation_member_ids'])
    denied={'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
    added=[];checks=[]
    for wid,w in sorted(s.ways.items()):
        tags=w.get('tags',{});ns=w.get('nodes',[]);sid=f'way/{wid}'
        is_restricted=tags.get('foot',tags.get('access'))in denied or tags.get('locked')=='yes'
        area_tag=tags.get('area')!='no'and(tags.get('amenity')in {'parking','parking_space'}or tags.get('area')=='yes'or'landuse'in tags or'leisure'in tags or tags.get('building')not in(None,'no'))
        if not is_restricted or not area_tag or len(ns)<4 or ns[0]!=ns[-1]:continue
        g=s.area(sid)
        if g is None:raise ValueError('Unparseable negative source '+sid)
        if not g.intersects(window):continue
        if sid in forbidden:raise ValueError('Restrictive object depends on hidden target '+sid)
        added.append({'source_id':sid,'geometry':mapping(g),'tags':tags,
            'source_clip_sha256':sign(args.source),'geometry_role':'COMPLETE_INDEPENDENT_RESTRICTED_SOURCE_AREA',
            'source_node_ring_closed':True,'explicit_area_tag':tags.get('area'),
            'source_tag_area_basis':[key for key in('amenity','area','landuse','leisure','building')if key in tags]})
        checks.append({'source_id':sid,'tags_match_raw':tags==s.ways[wid].get('tags',{}),
            'source_ring_closed':ns[0]==ns[-1],'source_area_m2':g.area,
            'source_geometry_sha256':sha256(json.dumps(mapping(g),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'source_id_not_hidden_target_or_member':sid not in forbidden,
            'selected_by':'ORIGINAL_ANCHOR_80M_WINDOW_ONLY','full_geometry_preserved':True})
    if not any(a['source_id']=='way/178730989'for a in added):raise ValueError('Required source area not found')
    guard={**old,'guard_version':'OBSERVED_COMMON_GUARDS_V3_SOURCE_ACCESS_AREAS',
        'parent_guard_sha256':sign(oldp),'access_areas':added,
        'access_area_export_role':'SOURCE_NEGATIVE_ONLY; NO_TARGET_OR_REFERENCE_SHAPE; NO_POSITIVE_FOOT_OR_MEMBER_ARRAYS'}
    dest=ROOT/'data/common_guards_v3'/f'{IDENT}.json';dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x',encoding='utf-8')as f:json.dump(guard,f,ensure_ascii=False,sort_keys=True,separators=(',',':'));f.write('\n')
    # Structural allowlist proves the newly introduced fields are negative-only.
    allowed={'source_id','geometry','tags','source_clip_sha256','geometry_role','source_node_ring_closed','explicit_area_tag','source_tag_area_basis'}
    if any(set(a)!=allowed for a in guard['access_areas']):raise ValueError('Unexpected extra field')
    audit={'status':'PASS_NEGATIVE_SOURCE_EXPORT_ONLY','input_id':IDENT,'guard_path':dest.relative_to(ROOT).as_posix(),
        'guard_sha256':sign(dest),'parent_guard_sha256':sign(oldp),'observed_sha256':sign(op),
        'raw_source_sha256':sign(args.source),'parser_sha256':sign(args.adapter),'source_checks':checks,
        'new_payload_allowlist':sorted(allowed),'hidden_dependency_ids_checked':True,'hidden_geometry_used':False,
        'reference_files_read':[],'query_files_read':[],'prediction_files_read':[],
        'positive_boundary_or_footway_data_added_to_guard':False,'raw_node_or_member_arrays_added':False,
        'domain_geometry_source':'ORIGINAL_OBSERVED_ANCHOR; ACTUAL_SURFACE_DOMAIN_PASSED_TO_BUILD_CONTRACT',
        'native_boundary_exceptions':'ONLY_FROM_SAME_OBSERVED_NATIVE_FOOT_ALLOWED_EXACT_LINE_IF_ANY; NEVER_RAW_HIDDEN_WAY',
        'regions_built_by_this_script':0,'production_old_version_backup':'runs/production_versions/BEFORE_PRIVATE_FIX'}
    with (ROOT/'audits/private_guard_v3_source_audit.json').open('x',encoding='utf8')as f:json.dump(audit,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':audit['status'],'negative_area_count':len(added),'source_ids':[a['source_id']for a in added],'guard_sha256':sign(dest)}))


if __name__=='__main__':main()
