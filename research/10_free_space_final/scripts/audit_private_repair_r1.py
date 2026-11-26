"""Read-only source-area audit of the final 26 fixed inputs and R1 repair.

No classifier, region builder, graph builder or route solver is imported.
The permission source registry is evaluation-only and never predictor input.
"""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from shapely.geometry import LineString,shape
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
IDENT='W7a6b5a10076_G_080'
EPS_AREA=1e-6
EPS_LINE=1e-6


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def main():
    registry_path=ROOT/'data/access_area_interpretations.json';registry=read(registry_path)
    archive=ROOT/'delivery/OPEN_REVIEW_R0_PARTIAL.zip';z=ZipFile(archive)
    rows=[r for r in read(ROOT/'data/task_manifest.json')['instances']if r.get('natural')or
          (r.get('context_radius_m')==80 and r.get('masking_mode')in {'G','N'})]
    if len(rows)!=26 or sum(bool(r.get('natural'))for r in rows)!=1:
        raise ValueError('Full audit must select exactly 25 fixed main inputs plus NORTH')
    cases=[];unchanged=[];route_failures=[]
    for row in rows:
        clip=row.get('source_clip','sh-huangpu-01.osm.json'if row.get('natural')else'')
        access=[(a,shape(a['geometry']))for a in registry['areas']if a['source_clip']==clip]
        for path in sorted((ROOT/'data/predictions'/row['id']).glob('*.json')):
            pred=read(path);D=shape(pred['surface']['domain'])
            if row['id']!=IDENT:
                member=path.relative_to(ROOT).as_posix()
                unchanged.append({'path':member,'byte_identical_to_fixed_R0_zip':path.read_bytes()==z.read(member)})
            intersections=[]
            for area,g in access:
                target=g.intersection(D)
                if target.area<=EPS_AREA:continue
                states={state:unary_union([shape(c['geometry'])for c in pred['surface']['cells']if c['walkability_state']==state]).intersection(target).area
                        for state in ('NATIVE_WALKABLE','INFERRED_WALKABLE','RESTRICTED','UNKNOWN')}
                intersections.append({'source_id':area['source_id'],'source_clip_sha256':area['source_clip_sha256'],
                    'actual_private_area_within_D_m2':target.area,'actual_state_overlaps_m2':states,
                    'passable_conflict_m2':states['NATIVE_WALKABLE']+states['INFERRED_WALKABLE'],
                    'restricted_shortfall_m2':max(0,target.area-states['RESTRICTED']),
                    'status':'PASS_WITH_NUMERICAL_TOLERANCE'if states['NATIVE_WALKABLE']+states['INFERRED_WALKABLE']<=EPS_AREA and target.area-states['RESTRICTED']<=EPS_AREA else'FAIL'})
            route_rows=[]
            for q,r in pred['routes'].items():
                interior=0;bad_boundary=0
                exceptions=[]
                for e in r['edges']:
                    line=LineString(e['xy'])
                    for area,g in access:
                        inside=line.intersection(g.buffer(-1e-7)).length
                        if inside>EPS_LINE:interior+=inside
                        boundary=line.intersection(g.boundary)
                        if boundary.length<=EPS_LINE:continue
                        allowed=unary_union([shape(x['geometry'])for x in area['boundary_exceptions']
                            if e['layer']=='native'and x['allowed_source_footway_id']==e.get('source_id')])
                        outside=boundary.difference(allowed).length
                        if outside>EPS_LINE:bad_boundary+=outside
                        if boundary.intersection(allowed).length>EPS_LINE:exceptions.append({'area_source_id':area['source_id'],
                            'allowed_source_footway_id':e.get('source_id'),'exact_boundary_m':boundary.intersection(allowed).length,'buffer_m':0})
                rr={'query_id':q,'reached':r['reached'],'private_interior_m':interior,
                    'unlicensed_boundary_m':bad_boundary,'exact_source_boundary_exceptions':exceptions,
                    'status':'PASS_SOURCE_PERMISSION_GEOMETRY'if interior<=EPS_LINE and bad_boundary<=EPS_LINE else'FAIL'}
                route_rows.append(rr)
                if rr['status']=='FAIL':route_failures.append({'input_id':row['id'],'method':pred['method'],**rr})
            cases.append({'input_id':row['id'],'method':pred['method'],'prediction_sha256':sign(path),
                'source_area_domain_intersections':intersections,'routes':route_rows})
    current=read(ROOT/'data/predictions'/IDENT/'F0.json');cache_path=ROOT/'data/classifier_cache'/f'{IDENT}.json';cache=read(cache_path)
    old_history=json.loads(z.read(f'data/calibration/{IDENT}.json'))
    log=current['read_log'];cache_open=next(r for r in log if r.get('path')=='classifier_surface_cache.json'and r['event']=='ACTUAL_FILE_OPEN')
    freeze=next(r for r in log if r.get('role')=='SURFACE_FROZEN');query=next(r for r in log if r.get('role')=='QUERY')
    gpath=ROOT/'data/common_guards_v3'/f'{IDENT}.json';guard=read(gpath);common=read(ROOT/'data/constraints'/f'{IDENT}.json')
    guard_checks={'exact_negative_area_id_only':[r['source_id']for r in guard['access_areas']]==['way/178730989'],
        'negative_payload_no_positive_keys':all(not(set(r)&{'boundary_exceptions','nodes','members','allowed_source_footway_id'})for r in guard['access_areas']),
        'same_observed_hash_as_fixed_R0':cache['observed_sha256']==sha256(z.read(f'data/observed/{IDENT}.json')).hexdigest(),
        'pure_M0_M1_cache_exact_R0_classification':cache['M0']==old_history['M0']and cache['M1']==old_history['M1'],
        'only_four_pure_cache_keys':set(cache)=={'observed_sha256','classifier_bindings','M0','M1'},
        'actual_cache_hash':cache_open['sha256']==sign(cache_path),
        'actual_v3_guard_hash':current['guards_sha256']==sign(gpath),
        'cache_then_surface_freeze_then_query':cache_open['sequence']<freeze['sequence']<query['sequence'],
        'private_boundary_positive_exception_count_is_zero':len(common.get('visible_native_boundary_exceptions',[]))==0,
        'no_other_fixed_prediction_changed':all(r['byte_identical_to_fixed_R0_zip']for r in unchanged)}
    area_failures=[{'input_id':c['input_id'],'method':c['method'],**x}for c in cases for x in c['source_area_domain_intersections']if x['status']=='FAIL']
    doc={'status':'PASS_SOURCE_ACCESS_REPAIR_WITH_LIMITS'if not area_failures and not route_failures and all(guard_checks.values())else'FAIL',
        'reviewer':'/root/free_constraints source role, independent from primary classifier/router; author of shared constraint helper',
        'scope':'READ_ONLY_SOURCE_POLYGON_AND_EXACT_BOUNDARY_RECOMPUTE_FOR_ALL_25_PRIMARY_PLUS_NORTH; NO_CLASSIFIER_OR_SOLVER_CALL',
        'R0_fixed_archive_sha256':sign(archive),'source_registry_sha256':sign(registry_path),
        'script_sha256':sign(Path(__file__)),'input_count':len(rows),'prediction_branch_count':len(cases),
        'area_tolerance_m2':EPS_AREA,'line_tolerance_m':EPS_LINE,
        'guard_and_cache_checks':guard_checks,'unchanged_other_predictions':unchanged,'cases':cases,
        'area_failures':area_failures,'route_failures':route_failures,
        'guard_sha256':sign(gpath),'actual_permission_geometry_area_m2':shape(common['permission_area_geometry']).area,
        'old_R0_gap_records_preserved':['audits/common_constraint_gap_W7a6b5a10076.json','audits/access_area_prediction_impact.json','audits/access_scope_26.json'],
        'new_region_builds_by_this_audit':0,'new_routes_by_this_audit':0,
        'limitations':['Only frozen mapped permissions, not current field access','Absent level remains unknown','One repaired source export task; not new blind confirmation','R0 gap remains a real recorded defect, not erased by corrected result']}
    out=ROOT/'audits/access_policy_FINAL_R1.json'
    with out.open('x',encoding='utf8')as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':doc['status'],'inputs':len(rows),'prediction_branches':len(cases),'area_failures':len(area_failures),
        'route_failures':len(route_failures),'guards':guard_checks,'permission_m2':doc['actual_permission_geometry_area_m2']}))


if __name__=='__main__':main()
