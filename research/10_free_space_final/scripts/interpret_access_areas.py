"""Source-derived permission geometry roles, without changing any old observation.

Closed parking/land-use areas retain private interiors; explicitly foot-allowed
native shared boundary edges may be recorded individually. A perimeter exception
never licenses the area interior, new free edges, or an unrelated source way.
"""
import argparse
from collections import Counter
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
DENIED={'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
PUBLIC={'yes','designated','permissive','official'}
STRUCTURAL={'wall','fence','hedge','retaining_wall','chain','city_wall','jersey_barrier'}


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def restricted(t):
    return t.get('foot',t.get('access'))in DENIED or t.get('locked')=='yes' or any(k in t for k in ('foot:conditional','access:conditional','oneway:foot:conditional'))


def area_semantics(t):
    return (t.get('area')!='no' and (t.get('area')=='yes' or t.get('amenity')in {'parking','parking_space'}
        or 'landuse'in t or 'leisure'in t or t.get('building')not in (None,'no')
        or t.get('natural')in {'water','wetland'}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True)
    args=p.parse_args()
    if sign(args.adapter)!='5bcefd9a7fddfbea67c778825fdc783d3a39d304ae8729673a620faad5349b83':raise ValueError('Wrong frozen ring parser')
    spec=importlib.util.spec_from_file_location('permission_source_ring_parser',args.adapter);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod
    exec(compile(args.adapter.read_bytes(),str(args.adapter),'exec'),mod.__dict__)
    mf=read(ROOT/'frozen_context/data/task_manifest.json')['instances']
    expected={r['source_clip']:r['source_clip_sha256']for r in mf}
    areas=[];sources=[];failures=[];linear=[]
    for name,expected_sha in sorted(expected.items()):
        path=args.source_dir/name
        if sign(path)!=expected_sha:raise ValueError('Wrong source '+name)
        raw=read(path);s=mod.Source(raw);sources.append({'source_clip':name,'sha256':sign(path),'timestamp':raw.get('osm3s',{}).get('timestamp_osm_base')})
        # Build precise original undirected edge ownership. Coincident coordinates
        # without original shared node identities do not create this exception.
        owners={}
        for wid,w in s.ways.items():
            t=w.get('tags',{})
            if t.get('foot')not in PUBLIC or restricted(t) or not t.get('highway'):continue
            for a,b in zip(w.get('nodes',[]),w.get('nodes',[])[1:]):
                if a!=b and a in s.projected and b in s.projected:owners.setdefault(tuple(sorted((a,b))),[]).append(wid)
        for wid,w in s.ways.items():
            tags=w.get('tags',{})
            if not restricted(tags):continue
            ns=w.get('nodes',[]);sid=f'way/{wid}'
            closed=len(ns)>=4 and ns[0]==ns[-1]
            if not closed or not area_semantics(tags):
                linear.append({'source_clip':name,'source_clip_sha256':expected_sha,'source_id':sid,'closed':closed,
                    'tags':tags,'role':'KEEP_ORIGINAL_LINEAR_ACCESS_RESTRICTION; CLOSED_LOOP_ALONE_DOES_NOT_ESTABLISH_AREA'})
                continue
            g=s.area(sid)
            if g is None:
                failures.append({'source_clip':name,'source_id':sid,'reason':'CLOSED_AREA_TAGS_BUT_RING_UNPARSEABLE'});continue
            byway={}
            if tags.get('barrier')not in STRUCTURAL:
                for a,b in zip(ns,ns[1:]):
                    for footway in owners.get(tuple(sorted((a,b))),[]):
                        if footway==wid:continue
                        byway.setdefault(footway,[]).append((a,b))
            exceptions=[]
            for footway,pairs in sorted(byway.items()):
                exact=unary_union([LineString([s.projected[a],s.projected[b]])for a,b in pairs])
                if exact.difference(g.boundary).length>1e-6:raise ValueError('Original shared edge not on area boundary')
                adjacent=[]
                for relid,rel in s.relations.items():
                    rt=rel.get('tags',{})
                    if rt.get('highway')!='pedestrian' or rt.get('area')!='yes' or restricted(rt):continue
                    if not any(m['type']=='way'and m['ref']==footway and m.get('role','outer')in ('','outer')for m in rel.get('members',[])):continue
                    rg=s.area(f'relation/{relid}')
                    adjacent.append({'source_id':f'relation/{relid}','tags':rt,'role':'REGISTERED_PEDESTRIAN_AREA_ADJACENCY',
                        'private_area_overlap_m2':g.intersection(rg).area if rg is not None else None,
                        'shared_boundary_m':g.boundary.intersection(rg.boundary).length if rg is not None else None})
                exceptions.append({'area_source_id':sid,'allowed_source_footway_id':f'way/{footway}',
                    'allowed_source_tags':s.ways[footway].get('tags',{}),'shared_original_node_ids':sorted({f'node/{n}'for ab in pairs for n in ab}),
                    'original_shared_node_pairs':[[f'node/{a}',f'node/{b}']for a,b in pairs],
                    'geometry':mapping(exact),'length_m':exact.length,'buffer_m':0,
                    'role':'EXACT_EXISTING_FOOT_ALLOWED_NATIVE_BOUNDARY_LINE_ONLY',
                    'does_not_allow':['PRIVATE_AREA_INTERIOR','NEW_FREE_EDGE','OTHER_SOURCE_WAY','BARRIER_OVERRIDE','PUBLIC_ENTRY_GUARANTEE'],
                    'adjacent_pedestrian_sources':adjacent,'permission_level':'MAP_TAG_SUPPORT_NOT_FIELD_AUTHORIZATION'})
            areas.append({'source_clip':name,'source_clip_sha256':expected_sha,'source_id':sid,'source_tags':tags,
                'native_nodes_closed':True,'native_node_ids':[f'node/{n}'for n in ns],
                'geometry':mapping(g),'geometry_role':'CLOSED_RESTRICTED_SOURCE_AREA_INTERIOR',
                'explicit_area_tag':tags.get('area'),'implicit_area_tag_basis':[k for k in ('amenity','landuse','leisure','building','natural')if k in tags],
                'area_m2':g.area,'boundary_length_m':g.length,'boundary_exceptions':exceptions,
                'private_interior_remains_forbidden':True,'source_layer_facts':'UNKNOWN_IF_ABSENT'})
    output={'version':'SOURCE_ACCESS_GEOMETRY_ROLE_V1','role':'DATA_AND_EVALUATION_ONLY_NOT_NEW_PREDICTOR_INPUT',
        'crs':'EPSG:32651','source_files':sources,'source_parser_sha256':sign(args.adapter),
        'areas':areas,'linear_access_roles_unchanged':linear,'unparseable_area_candidates':failures,
        'interpretation':'Native closed parking with access=private is an area permission object. Its edge is not automatically a wall. Only enumerated exact original foot-allowed shared boundary lines are exceptions; no area opening.',
        'no_reference_used':True,'no_new_region_builds':0}
    out=ROOT/'data/access_area_interpretations.json'
    with out.open('x',encoding='utf8')as f:json.dump(output,f,ensure_ascii=False,indent=2)
    # Main-domain impact scan covers objects missing altogether as well as objects
    # previously serialized as a line. It does not modify or reclassify any domain.
    main=[r for r in read(ROOT/'data/task_manifest.json')['instances']if r.get('panel')=='PRIMARY']
    if not main:main=[r for r in read(ROOT/'data/task_manifest.json')['instances']if not r.get('natural')and r['context_radius_m']==80 and r['masking_mode']in {'G','N'}]
    impacts=[]
    for r in main:
        obs=read(ROOT/r['observed']);domain=Point(obs['domain']['anchor_xy']).buffer(30,quad_segs=32)
        old={o['id']:o for xs in obs['context'].values()for o in xs}
        for a in areas:
            if a['source_clip']!=r['source_clip']:continue
            g=shape(a['geometry']);overlap=g.intersection(domain).area
            if overlap<=1e-8:continue
            row=old.get(a['source_id']);prior_kind=row.get('kind')if row else'OMITTED_FROM_OBSERVED'
            prior_geometry=shape(row['geometry'])if row else None
            mismatch=prior_geometry is None or prior_geometry.area<=1e-8
            impacts.append({'input_id':r['id'],'source_id':a['source_id'],'source_clip':a['source_clip'],
                'source_area_within_D_m2':overlap,'old_kind':prior_kind,
                'old_geometry_type':prior_geometry.geom_type if prior_geometry is not None else None,
                'area_missing_or_mistyped':mismatch,'reference_read':False})
    north=next(a for a in areas if a['source_clip']=='sh-huangpu-01.osm.json'and a['source_id']=='way/178730989')
    d=read(ROOT/'data/predictions/NORTH_160/F0.json');poly=shape(north['geometry'])
    north_routes=[]
    for pth in sorted((ROOT/'data/predictions/NORTH_160').glob('*.json')):
        pred=read(pth);rr=pred['routes']['NORTH-DOOR'];lines=[LineString(e['xy'])for e in rr['edges']]
        north_routes.append({'method':pred['method'],'prediction_sha256':sign(pth),'private_interior_m':sum(l.intersection(poly.buffer(-1e-7)).length for l in lines),
            'shared_boundary_m':sum(l.intersection(poly.boundary).length for l in lines),
            'boundary_source_way_ids':sorted({e['source_id']for e,l in zip(rr['edges'],lines)if l.intersection(poly.boundary).length>1e-6})})
    audit={'status':'SOURCE_ROLE_CONFIRMED'if all(x['private_interior_m']<1e-6 for x in north_routes)else'CONFLICT',
        'source_registry_sha256':sign(out),'source_area_records':len(areas),'unique_area_ids':len({a['source_id']for a in areas}),
        'boundary_exception_records':sum(len(a['boundary_exceptions'])for a in areas),
        'linear_access_source_records':len(linear),'unparseable_candidates':failures,
        'main_task_count':len(main),'main_domain_area_intersections':impacts,
        'main_missing_or_mistyped_intersections':[r for r in impacts if r['area_missing_or_mistyped']],
        'north_parking':north,'north_door_routes':north_routes,
        'old_audit_limitation':'Original Source.obstacles omitted closed amenity=parking/private rings without explicit area=yes and open linear access ways. Prior zero-conflict reports did not cover those classes; preserved, superseded for permissions.',
        'region_or_route_modified':False,'new_region_builds':0,'no_new_map_requests':True}
    with (ROOT/'audits/access_area_source_review.json').open('x',encoding='utf8')as f:json.dump(audit,f,ensure_ascii=False,indent=2)
    geo={'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'features':[{'type':'Feature','geometry':north['geometry'],'properties':{'source_id':north['source_id'],'source_tags':north['source_tags'],'role':'PRIVATE_PARKING_INTERIOR_FORBIDDEN'}},*({'type':'Feature','geometry':x['geometry'],'properties':{'source_id':x['allowed_source_footway_id'],'area_source_id':north['source_id'],'role':x['role'],'buffer_m':0}}for x in north['boundary_exceptions'])]}
    gd=ROOT/'data/source_diagnostics/private_parking_boundary.geojson';gd.parent.mkdir(parents=True,exist_ok=True)
    with gd.open('x',encoding='utf8')as f:json.dump(geo,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':audit['status'],'area_records':len(areas),'unique_areas':audit['unique_area_ids'],'boundary_exceptions':audit['boundary_exception_records'],
        'main_tasks':len(main),'main_domain_intersections':len(impacts),'main_mistyped_or_missing':len(audit['main_missing_or_mistyped_intersections']),'unparseable':len(failures)}))


if __name__=='__main__':main()
