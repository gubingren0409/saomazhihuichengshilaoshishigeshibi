"""Post-prediction whole-route check against the complete frozen Shanghai clip.

Independent execution context from the main router. The frozen Source parser is
used only for OSM rings; no author classification/route validation is invoked.
Full raw source is intentionally confined to this post-prediction audit role.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

from shapely.geometry import LineString, Point, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
DENIED={'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
PUBLIC={'yes','designated','permissive','official'}
EPS=1e-6


def sign(path):
    h=sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def access(tags):
    return tags.get('foot',tags.get('access')) in DENIED or tags.get('locked')=='yes' or any(k in tags for k in ('foot:conditional','access:conditional','oneway:foot:conditional'))


def whole_check(pred,obstacles,tree,source):
    outcomes=[]
    for query,route in pred['routes'].items():
        conflicts=[];exceptions=[];bylayer=Counter();nolevel=0;explicit=[];discontinuities=[];previous=None
        source_checks=[]
        expected=source['queries'].get(query)
        endpoint_error={}
        if expected is None:
            conflicts.append({'reason':'QUERY_NOT_IN_FROZEN_SET'})
        elif route.get('reached'):
            edges=route.get('edges',[])
            actual_start=edges[0]['xy'][0] if edges else route.get('start_xy')
            actual_end=edges[-1]['xy'][-1] if edges else route.get('end_xy')
            for role,actual in (('source',actual_start),('target',actual_end)):
                err=None if actual is None else math.dist(actual,expected[role]['xy'])
                endpoint_error[role+'_error_m']=err
                if err is None or err>EPS:conflicts.append({'reason':'FROZEN_ENDPOINT_NOT_EXACT','role':role,'error_m':err})
        for index,seg in enumerate(route.get('edges',[])):
            xy=seg['xy'];line=LineString(xy);tags=seg.get('tags',{})
            bylayer[seg['layer']]+=line.length
            if previous is not None and math.dist(previous,xy[0])>EPS:
                discontinuities.append({'segment':index,'gap_m':math.dist(previous,xy[0])})
            previous=xy[-1]
            actual_length=sum(math.dist(a,b) for a,b in zip(xy,xy[1:]))
            if abs(actual_length-seg['length_m'])>EPS:
                conflicts.append({'segment':index,'reason':'SERIALIZED_LENGTH_DISAGREES','actual_m':actual_length,'recorded_m':seg['length_m']})
            if access(tags):conflicts.append({'segment':index,'reason':'EXPLICIT_ACCESS_OR_CONDITIONAL_RESTRICTION','source_id':seg.get('source_id'),'tags':tags})
            if seg['layer']=='native':
                sid=seg.get('source_id','');m=re.fullmatch(r'way/(\d+)',sid)
                line_source=source['native_lines'].get(int(m.group(1))) if m else None
                off_source=line.length if line_source is None else line.difference(line_source.buffer(1e-6)).length
                raw_tags=source['native_tags'].get(int(m.group(1))) if m else None
                tags_match=raw_tags==tags
                source_checks.append({'segment':index,'role':'NATIVE_LINE','source_id':sid,'unmatched_length_m':off_source,'source_tags_match':tags_match})
                if off_source>EPS:conflicts.append({'segment':index,'source_id':sid,'reason':'NATIVE_GEOMETRY_NOT_SUPPORTED_BY_ORIGINAL_SOURCE_WAY','length_m':off_source})
                if not tags_match:conflicts.append({'segment':index,'source_id':sid,'reason':'NATIVE_TAGS_DIFFER_FROM_ORIGINAL_SOURCE','recorded_tags':tags,'original_tags':raw_tags})
            elif seg['layer']=='derived':
                off_area=line.difference(source['mapped_faces'].buffer(1e-6)).length
                source_checks.append({'segment':index,'role':'MAPPED_AREA_DERIVED','source_id':seg.get('source_id'),'unmatched_length_m':off_area})
                if off_area>EPS:conflicts.append({'segment':index,'source_id':seg.get('source_id'),'reason':'DERIVED_GEOMETRY_OUTSIDE_ORIGINAL_MAPPED_PEDESTRIAN_FACE','length_m':off_area})
            lev={k:tags[k] for k in ('level','layer','bridge','tunnel','indoor','repeat_on') if k in tags}
            if not lev:nolevel+=1
            else:explicit.append({'segment':index,'source_id':seg.get('source_id'),'tags':lev})
            for n in tree.query(line,predicate='intersects'):
                obj=obstacles[int(n)];g=obj['geometry'];typ=obj['audit_kind'];overlap=line.intersection(g)
                if overlap.is_empty:continue
                # Mapped line exceptions are confined to their exact original route,
                # never interpreted as a free area width.
                original=seg['layer']=='native'
                structure=tags.get('bridge') not in (None,'no','false','0') or tags.get('tunnel') not in (None,'no','false','0')
                if typ=='BACKGROUND_POLICY' and not access(obj.get('tags',{})):
                    if original:
                        if overlap.length>EPS:exceptions.append({'segment':index,'source_id':seg.get('source_id'),'obstacle_id':obj['id'],'reason':'ORIGINAL_VALID_NATIVE_LINE_IN_BACKGROUND','length_m':overlap.length})
                        continue
                if typ in ('BUILDING','WATER','RESTRICTED','UNKNOWN_BBOX','BACKGROUND_POLICY') and g.area>EPS:
                    # Exterior boundary contact including the unchanged door is not
                    # an interior traversal. Use DE-9IM on raw geometry independently.
                    interior_length=line.intersection(g.buffer(-1e-7)).length
                    if typ=='RESTRICTED' or access(obj.get('tags',{})):
                        boundary=line.intersection(g.boundary)
                        allowance=source['boundary_allowances'].get((obj['id'],seg.get('source_id')))
                        allowed=(boundary.intersection(allowance).length if original and allowance is not None else 0)
                        length=interior_length+max(0,boundary.length-allowed)
                        if allowed>EPS:
                            exceptions.append({'segment':index,'source_id':seg.get('source_id'),'obstacle_id':obj['id'],
                                'reason':'ENUMERATED_EXACT_ORIGINAL_FOOT_ALLOWED_SHARED_BOUNDARY',
                                'length_m':allowed,'buffer_m':0,'private_area_interior_m':interior_length,
                                'scope':'THIS_ORIGINAL_SOURCE_WAY_AND_EXACT_SHARED_NODE_EDGE_ONLY; NO_AREA_OPENING'})
                    else:
                        if line.relate_pattern(g,'F********'):continue
                        length=interior_length
                elif typ=='BARRIER':
                    barrier=g.buffer(.15) if g.area<=EPS else g
                    openings=unary_union([Point(p['xy']).buffer(.30) for p in obj.get('gates',[]) if p.get('allowed')])
                    if not openings.is_empty:barrier=barrier.difference(openings)
                    length=line.intersection(barrier).length
                else:length=overlap.length
                if length<=EPS:continue
                if original and structure and typ in ('BUILDING','WATER'):
                    exceptions.append({'segment':index,'source_id':seg.get('source_id'),'obstacle_id':obj['id'],'reason':'ORIGINAL_GRAPH_STRUCTURAL_TAG_EXCEPTION_NOT_NEW_GROUND_INTERFACE','tags':lev,'length_m':length})
                else:conflicts.append({'segment':index,'source_id':seg.get('source_id'),'layer':seg['layer'],'obstacle_id':obj['id'],'obstacle_kind':typ,'tags':obj.get('tags',{}),'length_m':length,'reason':'WHOLE_SEGMENT_SOURCE_OVERLAP'})
        route_xy=[p for e in route.get('edges',[]) for p in e['xy']]
        coverage=source['coverage']
        uncovered=sum(LineString(e['xy']).difference(coverage).length for e in route.get('edges',[]))
        outcomes.append({'query_id':query,'reached':route.get('reached'), 'route_segments':len(route.get('edges',[])),
            'actual_layer_lengths_m':dict(bylayer),'outside_acquired_clip_length_m':uncovered,
            'conflicts':conflicts,'source_line_exceptions':exceptions,'discontinuities':discontinuities,
            'source_geometry_checks':source_checks,
            'frozen_endpoint_check':endpoint_error,
            'missing_level_tag_segment_count':nolevel,'level_absence_semantics':'UNKNOWN_OUTDOOR_LEVEL_NOT_ASSIGNED_MEASURED_ZERO',
            'explicit_level_records':explicit,'status':'PASS_WITH_UNVERIFIED_REAL_WORLD_LIMITS' if not conflicts and not discontinuities and uncovered<EPS else 'SOURCE_CONFLICT_OR_UNCOVERED'})
    return outcomes


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--predictions',type=Path,default=ROOT/'data/predictions/NORTH_160');p.add_argument('--output',type=Path,default=ROOT/'audits/north_full_source_check.json')
    args=p.parse_args()
    guard=read(ROOT/'data/common_guards_v2/NORTH_160.json')
    if sign(args.source)!=guard['source_sha256']:raise ValueError('Full frozen clip identity mismatch')
    if sign(args.adapter)!='5bcefd9a7fddfbea67c778825fdc783d3a39d304ae8729673a620faad5349b83':
        raise ValueError('Source-ring parser differs from exact nested R4-REV1 archive')
    spec=importlib.util.spec_from_file_location('frozen_source_parser_for_posthoc_audit',args.adapter)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod
    exec(compile(args.adapter.read_bytes(),str(args.adapter),'exec'),mod.__dict__)
    source=mod.Source(read(args.source));objects,unlocated=source.obstacles([])
    obstacles=[]
    for obj in objects:
        tags=obj.get('tags',{});typ=obj['kind']
        if typ=='AREA':
            if tags.get('landuse') in {'grass','flowerbed','flower_bed'} or tags.get('landcover') in {'grass','flowerbed'}:typ='BACKGROUND_POLICY'
            elif tags.get('natural') in {'water','wetland'} or tags.get('water') or tags.get('waterway')=='riverbank':typ='WATER'
            elif access(tags):typ='RESTRICTED'
            else:typ='BACKGROUND_POLICY'
        if typ=='UNKNOWN':typ='UNKNOWN_BBOX'
        obstacles.append(dict(obj,audit_kind=typ))
    # Frozen Source.obstacles only recognizes explicit area=yes/type=multipolygon
    # restrictions. It misses ordinary closed private parking rings and all open
    # restricted way axes. Audit them directly from native objects, without
    # treating a private area boundary as a wall across an independent public path.
    included={o['id'] for o in obstacles}
    permission_additions=[]
    for ident,row in source.ways.items():
        tags=row.get('tags',{})
        sid=f'way/{ident}'
        if sid in included or not access(tags):continue
        ns=row.get('nodes',[])
        if len(ns)<2 or any(n not in source.projected for n in ns):continue
        closed=ns[0]==ns[-1]
        implicit_area=(closed and tags.get('area')!='no' and
                       (tags.get('amenity') in {'parking','parking_space'} or
                        tags.get('landuse') is not None or tags.get('leisure') is not None or
                        tags.get('area')=='yes'))
        g=source.area(sid) if implicit_area else None
        role='RESTRICTED'if g is not None else'RESTRICTED_LINEAR_ACCESS'
        if g is None:g=LineString([source.projected[n]for n in ns])
        entry={'id':sid,'kind':role,'audit_kind':role,'geometry':g,'tags':tags,
               'gates':[],'geometry_role':'CLOSED_SOURCE_AREA_PERMISSION_INTERIOR_ONLY'if role=='RESTRICTED'else'ORIGINAL_SOURCE_LINEAR_PERMISSION'}
        obstacles.append(entry)
        permission_additions.append({'source_id':sid,'native_nodes_closed':closed,'node_count':len(ns),
            'tags':tags,'audit_kind':role,'geometry_role':entry['geometry_role'],
            'area_m2':g.area,'length_m':g.length,'geometry':mapping(g)})
    tree=STRtree([r['geometry'] for r in obstacles])
    from shapely.geometry import shape
    native_lines={i:LineString([source.projected[n] for n in row['nodes']]) for i,row in source.ways.items()
                  if row.get('tags',{}).get('highway') and len(row.get('nodes',[]))>1 and all(n in source.projected for n in row['nodes'])}
    faces=[]
    for kind,items in (('way',source.ways),('relation',source.relations)):
        for ident,row in items.items():
            tags=row.get('tags',{})
            if (tags.get('highway')=='pedestrian' and tags.get('area')=='yes' or tags.get('area:highway') in {'pedestrian','footway','path'}) and not access(tags):
                a=source.area(f'{kind}/{ident}')
                if a is not None:faces.append(a)
    manifest=read(ROOT/'data/task_manifest.json')
    north_row=next(r for r in manifest['instances'] if r['id']=='NORTH_160')
    query_path=ROOT/north_row['query']
    if sign(query_path)!=north_row['query_sha256']:raise ValueError('Frozen natural queries differ')
    query_doc=read(query_path)
    original_exit=source.nodes[6897145227]
    door_query=next(q for q in query_doc['queries'] if q['target']['id']=='node/6897145227')
    exit_xy=source.projected[6897145227]
    door_binding={'id':'node/6897145227','source_wgs84':[original_exit['lon'],original_exit['lat']],
        'source_xy':exit_xy,'source_tags':original_exit.get('tags',{}),
        'query_xy':door_query['target']['xy'],'query_tags':door_query['target'].get('tags',{}),
        'displacement_m':math.dist(exit_xy,door_query['target']['xy']),
        'inbound_eligibility':'NOT_ELIGIBLE_EXIT'}
    if door_binding['displacement_m']>EPS or original_exit.get('tags',{}).get('entrance')!='exit' or door_query['target'].get('tags',{}).get('entrance')!='exit':
        raise ValueError('Original registered exit coordinate/role was changed')
    registry_path=ROOT/'data/access_area_interpretations.json'
    registry=read(registry_path)
    allowances={}
    for area in registry['areas']:
        if area['source_clip']!=args.source.name:continue
        if area['source_clip_sha256']!=sign(args.source):raise ValueError('Permission registry source identity differs')
        for e in area['boundary_exceptions']:
            allowances[(area['source_id'],e['allowed_source_footway_id'])]=shape(e['geometry'])
    source_info={'coverage':shape(guard['coverage_geometry']),'native_lines':native_lines,
                 'boundary_allowances':allowances,
                 'queries':{q['query_id']:q for q in query_doc['queries']},
                 'native_tags':{i:row.get('tags',{}) for i,row in source.ways.items()},'mapped_faces':unary_union(faces)}
    rows=[]
    for path in sorted(args.predictions.glob('*.json')):
        pred=read(path)
        if 'routes' not in pred:continue
        rows.append({'method':pred['method'],'prediction_path':path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),'prediction_sha256':sign(path),
                     'queries':whole_check(pred,obstacles,tree,source_info)})
    if not rows:raise ValueError('No actual NORTH predictions available')
    doc={'reviewer_role':'FREE_CONSTRAINTS_DATA_ROLE_DIFFERENT_CONTEXT_FROM_MAIN_IMPLEMENTER',
        'scope':'WHOLE_ROUTE_GEOMETRY_AGAINST_ENTIRE_FROZEN_SOURCE_CLIP_POST_PREDICTION; NOT_FIELD_VALIDATION',
        'parser_reuse':'FROZEN_SOURCE_RING_PARSER_ONLY; NO_AUTHOR_CLASSIFIER_OR_VALIDATION_FUNCTION_CALLED',
        'source_sha256':sign(args.source),'source_adapter_sha256':sign(args.adapter),
        'audit_script_sha256':sign(Path(__file__)),
        'constraint_object_count':len(obstacles),'constraint_kind_counts':dict(Counter(r['audit_kind'] for r in obstacles)),
        'permission_audit_revision':'RAW_CLOSED_IMPLICIT_AREAS_AND_OPEN_RESTRICTED_WAYS_INCLUDED_V2',
        'private_boundary_exception_revision':'ONLY_ENUMERATED_EXACT_FOOT_ALLOWED_SOURCE_WAY_SHARED_EDGE_NO_BUFFER',
        'access_area_registry_sha256':sign(registry_path),
        'additional_permission_objects':permission_additions,
        'unlocated_source_hazard_ids':unlocated,'runs':rows,
        'registered_exit_binding':door_binding,'frozen_queries_sha256':sign(query_path),
        'unknowns':['Unmapped physical obstacles','Current permissions and opening hours','Unmapped steps or platform height','All absent level tags remain unknown'],
        'replay_dependencies':'Exact full source and Source parser are in nested frozen archive; predictor does not read them'}
    doc['conflict_count']=sum(len(q['conflicts']) for r in rows for q in r['queries'])
    doc['status']='PASS_WITH_LIMITS' if doc['conflict_count']==0 and not unlocated and all(q['status'].startswith('PASS') for r in rows for q in r['queries']) else 'FINDINGS_REQUIRE_EXPLANATION_OR_REPAIR'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':doc['status'],'runs':len(rows),'source_objects':len(obstacles),'conflicts':doc['conflict_count']},ensure_ascii=False))


if __name__=='__main__':main()
