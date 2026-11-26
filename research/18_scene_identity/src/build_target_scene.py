"""Read frozen OSM and export map context only. No routing code is imported.

Projection and conservative multipolygon assembly mirror the frozen Source.area
geometry contract: original rings, polygonize, outer-minus-inner, never buffer0.
No graph is constructed and no input/result is rewritten.
"""
from __future__ import annotations
import argparse
import collections
import csv
import datetime
import gc
import hashlib
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, MultiLineString, box, mapping, shape
from shapely.ops import polygonize, unary_union

ROOT=Path(__file__).resolve().parents[1]
FOUNDATION=ROOT.parent/'SMART_CITY_WALKABILITY_FOUNDATION_PG1'
FAMILIES=['buildings','road_centerlines','road_areas','native_walkways','crossings',
          'traffic_facilities','pedestrian_areas','vegetation','water','barriers',
          'railway','poi','other_context']
MOTOR={'motorway','motorway_link','trunk','trunk_link','primary','primary_link',
       'secondary','secondary_link','tertiary','tertiary_link','unclassified',
       'residential','living_street','service','road','construction','proposed','track'}
PED={'footway','path','pedestrian','steps','cycleway','bridleway','corridor','platform'}
VEGETATION_NATURAL={'wood','tree','tree_row','scrub','grassland','heath','fell','moor'}
PROJECT=Transformer.from_crs(4326,32651,always_xy=True).transform

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sid(o):return o['type']+'/'+str(o['id'])

def base_families(o,area=False):
    t=o.get('tags',{});h=t.get('highway');out=[]
    if t.get('building') not in (None,'no') or t.get('building:part') not in (None,'no'):out.append('buildings')
    if o['type']=='way' and h in MOTOR and not area:out.append('road_centerlines')
    if t.get('area:highway') not in (None,'no','pedestrian','footway','path','cycleway') or (area and h in MOTOR):out.append('road_areas')
    if h in PED and not area:out.append('native_walkways')
    if h=='living_street':out.append('native_walkways')
    if h=='crossing' or t.get('footway')=='crossing' or 'crossing' in t:out.append('crossings')
    if h in {'traffic_signals','crossing','bus_stop','street_lamp','stop','give_way','turning_circle','turning_loop'} or 'traffic_signals'in t or t.get('public_transport'):out.append('traffic_facilities')
    if (area and (h in {'pedestrian','footway','path'} or t.get('area:highway')in{'pedestrian','footway','path','cycleway'})) or t.get('place')=='square':out.append('pedestrian_areas')
    if t.get('leisure')in{'park','garden','recreation_ground','nature_reserve','common','flowerbed'} or t.get('landuse')in{'grass','meadow','forest','flowerbed','flower_bed','recreation_ground','village_green','allotments','orchard','vineyard'} or t.get('landcover')in{'grass','trees','flowerbed','scrub'} or t.get('natural')in VEGETATION_NATURAL:out.append('vegetation')
    if t.get('natural')in{'water','wetland','spring','bay'} or t.get('water') or t.get('waterway') or t.get('landuse')in{'reservoir','basin'}:out.append('water')
    if t.get('barrier') or t.get('man_made')in{'embankment','retaining_wall'}:out.append('barriers')
    if t.get('railway'):out.append('railway')
    if t.get('name') or t.get('amenity') or t.get('tourism') or t.get('shop') or t.get('place') or t.get('office') or t.get('entrance'):out.append('poi')
    return list(dict.fromkeys(out)) or ['other_context']

def area_intent(o):
    t=o.get('tags',{})
    if o['type']=='relation':return t.get('type')=='multipolygon'
    if o['type']!='way':return False
    n=o.get('nodes',[])
    if len(n)<4 or n[0]!=n[-1] or t.get('area')=='no':return False
    return (t.get('area')=='yes' or t.get('building') not in (None,'no') or t.get('building:part')not in(None,'no')
            or any(k in t for k in ['landuse','landcover','leisure','area:highway'])
            or t.get('natural')in{'water','wetland','wood','scrub','sand','beach','grassland','heath'}
            or t.get('waterway')=='riverbank' or t.get('place')=='square'
            or t.get('amenity')in{'parking','school','hospital','university','kindergarten','place_of_worship','grave_yard','marketplace','college'})

def source_geometry(o,idx,xy):
    """Original coordinates or explicit relation member linework; no repair."""
    if o['type']=='node':return Point(xy[o['id']]),'ORIGINAL_SOURCE_POINT',None
    if o['type']=='way':
        refs=o.get('nodes',[])
        if len(refs)<2 or any(n not in xy for n in refs):return None,'NOT_EXTRACTED','MISSING_SOURCE_NODES_OR_NO_LINE'
        line=LineString([xy[n]for n in refs])
        if not area_intent(o):return line,'ORIGINAL_SOURCE_LINE',None
        polys=list(polygonize([line]))
        if len(polys)==1 and polys[0].is_valid:return polys[0],'ORIGINAL_SOURCE_POLYGON_WITH_HOLES',None
        return line,'ORIGINAL_SOURCE_INVALID_RING_OUTLINE_ONLY','SOURCE_AREA_RING_INVALID_NO_GEOMETRY_REPAIR'
    if not area_intent(o):return None,'NONSPATIAL_RELATION','RELATION_IS_MEMBERSHIP_NOT_AN_INDEPENDENT_DRAWABLE_GEOMETRY'
    grouped={'outer':[],'inner':[]};all_lines=[];problem=None
    for m in o.get('members',[]):
        role=m.get('role')or'outer'
        if m['type']!='way' or role not in grouped or m['ref']not in idx['way']:
            problem='MISSING_OR_UNSUPPORTED_RELATION_MEMBER';continue
        w=idx['way'][m['ref']];refs=w.get('nodes',[])
        if len(refs)<2 or any(n not in xy for n in refs):problem='MISSING_RELATION_MEMBER_SOURCE_NODES';continue
        line=LineString([xy[n]for n in refs]);grouped[role].append(line);all_lines.append(line)
    if problem is None:
        areas=[]
        for role in ['outer','inner']:
            lines=grouped[role];area=unary_union(list(polygonize(lines)))
            if lines and(area.is_empty or any(line.difference(area.boundary.buffer(1e-7)).length>1e-6 for line in lines)):
                problem='UNRESOLVED_RELATION_RING_ASSEMBLY';break
            areas.append(area)
        if problem is None:
            outer,inner=areas
            if outer.is_empty or(not inner.is_empty and not outer.covers(inner)):problem='RELATION_INNER_OUTSIDE_OR_NO_OUTER'
            else:
                area=outer.difference(inner)
                if not area.is_empty and area.is_valid and area.geom_type in{'Polygon','MultiPolygon'}:
                    return area,'ORIGINAL_SOURCE_MULTIPOLYGON_WITH_HOLES',None
                problem='RELATION_AREA_INVALID_NO_REPAIR'
    if all_lines:return MultiLineString(all_lines),'RELATION_MEMBER_LINEWORK_UNRESOLVED_AREA',problem
    return None,'NOT_EXTRACTED',problem or'NO_RELATION_LINEWORK'

# This file copies only source-geometry parsing from the preceding visual repair.
# Everything below concerns identity, cartographic coverage and saved records.
import math
from shapely.geometry import Polygon

TARGET_ID=161090899
SOUTH_ID=6897141353
NORTH_ID=6897145227
EXPECTED_SOURCE_SHA='3219eccb7a7d37ea463895c63cc98688d66e0abe6b85575d38ea53ec023afc91'
FAMILIES+=['restrictions','sidewalks','cycleways','steps_ramps','levels']

def families(o,area=False):
    fs=base_families(o,area);t=o.get('tags',{})
    if t.get('foot',t.get('access'))in{'no','private','customers','destination','permit','restricted','delivery','agricultural','forestry'}:fs.append('restrictions')
    if t.get('footway')=='sidewalk':fs.append('sidewalks')
    if t.get('highway')=='cycleway'or any(k.startswith('cycleway')for k in t):fs.append('cycleways')
    if t.get('highway')in{'steps','elevator'}or any(k.startswith('ramp')for k in t):fs.append('steps_ramps')
    if any(t.get(k)not in{None,'','no','0','false'}for k in['layer','level','bridge','tunnel','indoor']):fs.append('levels')
    return list(dict.fromkeys(fs))

def rounded_bounds(g,pad):
    b=g.bounds
    return [math.floor((b[0]-pad)/10)*10,math.floor((b[1]-pad)/10)*10,
            math.ceil((b[2]+pad)/10)*10,math.ceil((b[3]+pad)/10)*10]

def square_door(xy,half=130):return [xy[0]-half,xy[1]-half,xy[0]+half,xy[1]+half]

def record(o,g=None,**extra):
    return {'source_id':sid(o),'type':o['type'],'id':o['id'],'source_version':o.get('version'),
            'tags':o.get('tags',{}),'geometry':mapping(g)if g is not None else None,**extra}

def build_identity(raw,meta):
    idx={k:{}for k in['node','way','relation']}
    for o in raw['elements']:idx[o['type']][o['id']]=o
    xy={n:PROJECT(o['lon'],o['lat'])for n,o in idx['node'].items()}
    target=idx['way'].get(TARGET_ID)
    if not target:raise RuntimeError('TARGET_COVERAGE_BLOCKED: targetwayabsent')
    tg,basis,warning=source_geometry(target,idx,xy)
    assert tg is not None and tg.is_valid and tg.geom_type in{'Polygon','MultiPolygon'}
    assert target['tags'].get('building')not in{None,'no'}and target['tags'].get('wikidata')=='Q1051293'
    assert target['tags'].get('name')=='上海博物馆'and target['tags'].get('addr:housenumber')=='201'
    doors=[]
    for n,role,expected in[(SOUTH_ID,'SOUTH_REGISTERED_MAIN','main'),(NORTH_ID,'NORTH_REGISTERED_EXIT_OUTSIDE_ONLY','exit')]:
        o=idx['node'].get(n);assert o and o['tags'].get('entrance')==expected
        point=Point(xy[n]);distance=tg.boundary.distance(point);assert n in target['nodes']and distance<1e-7
        doors.append(record(o,point,xy=list(xy[n]),wgs84=[o['lon'],o['lat']],role=role,
                     outer_ring_member=True,boundary_distance_m=distance,
                     inbound_applicability='NOT_AN_INBOUND_ENTRANCE'if expected=='exit'else'REGISTERED_MAIN_REFERENCE_NOT_FIELD_VERIFIED'))
    same_name=[o for o in idx['way'].values()if o.get('tags',{}).get('name')=='黄陂北路'or o.get('tags',{}).get('name:zh')=='黄陂北路']
    roads=[o for o in same_name if o.get('tags',{}).get('highway')in MOTOR and not area_intent(o)]
    assert len(roads)==7
    road_geoms={o['id']:source_geometry(o,idx,xy)[0]for o in roads}
    assert all(g is not None and not g.is_empty for g in road_geoms.values())
    road_nodes=set(n for o in roads for n in o['nodes']);road_ids={o['id']for o in roads}
    junctions=[]
    for n in sorted(road_nodes):
        incident=[o for o in idx['way'].values()if n in o.get('nodes',[])and o.get('tags',{}).get('highway')in MOTOR]
        others=[o for o in incident if o['id']not in road_ids]
        if others:junctions.append({'source_id':'node/'+str(n),'xy':list(xy[n]),'wgs84':[idx['node'][n]['lon'],idx['node'][n]['lat']],
            'node_tags':idx['node'][n].get('tags',{}),'incident_road_ids':[sid(o)for o in incident],
            'other_roads':[{'source_id':sid(o),'name':o.get('tags',{}).get('name'),'tags':o.get('tags',{})}for o in others]})
    road_records=[]
    for o in sorted(roads,key=lambda x:x['id']):
        g=road_geoms[o['id']]
        road_records.append(record(o,g,node_ids=o['nodes'],bounds_xy=list(g.bounds),source_line_length_m=g.length,
            junction_ids=[j['source_id']for j in junctions if int(j['source_id'].split('/')[1])in o['nodes']],
            centerline_only=True,cycleway_lane_geometry='ATTRIBUTE_ONLY_NO_SEPARATE_GEOMETRY_INVENTED'))
    excluded=[record(o,source_geometry(o,idx,xy)[0],reason='SAME_NAME_PUBLIC_TRANSPORT_PLATFORM_NOT_ROAD')for o in same_name if o not in roads]
    # A source-object grouping, not a routing graph or route traversal.
    degree=collections.Counter(n for o in roads for n in[o['nodes'][0],o['nodes'][-1]])
    endpoints=[n for n,count in degree.items()if count==1]
    assert len(endpoints)==2
    union=unary_union([tg,*road_geoms.values(),*[Point(d['xy'])for d in doors]])
    full=rounded_bounds(union,120)
    near_junction_ids=[71127847,267195150,476675200,477568284]
    overview_junction_rationale=[{'source_id':j['source_id'],'other_road_names':sorted({r.get('name')for r in j['other_roads']if r.get('name')}),
                                  'other_road_source_ids':[r['source_id']for r in j['other_roads']]}for j in junctions if int(j['source_id'].split('/')[1])in near_junction_ids]
    overview_union=unary_union([tg,*[Point(xy[n])for n in near_junction_ids],*[Point(d['xy'])for d in doors]])
    overview=rounded_bounds(overview_union,90)
    # Additional vertical context gives both door-front pedestrian areas room,
    # without changing any source geometry or choosing a way midpoint.
    overview[1]-=50;overview[3]+=50
    views=[{'id':'block_context','label':'上海博物馆与黄陂北路完整街区','bounds_xy':full,
            'anchor_ids':['way/'+str(TARGET_ID),*[d['source_id']for d in doors],*[r['source_id']for r in road_records]],
            'rule':'Union verifiedtarget+bothEP+all7completeHuangpiNorthRoadsourceways, add120mneighborcontext, roundoutward10m'},
           {'id':'target_overview','label':'上海博物馆建筑与南北门接近空间','bounds_xy':overview,
            'anchor_ids':['way/'+str(TARGET_ID),*[d['source_id']for d in doors],*['node/'+str(n)for n in near_junction_ids]],
            'named_junction_rationale':overview_junction_rationale,
            'rule':'Union target+bothEP+sourcejunctionsPeopleAvenue/Wusheng/Weihai,90mcontext plus50mverticalcontext,roundoutward10m'},
           {'id':'huangpi_detail','label':'黄陂北路完整相关路段与博物馆关系','bounds_xy':rounded_bounds(union,60),
            'anchor_ids':['way/'+str(TARGET_ID),*[r['source_id']for r in road_records]],
            'rule':'Union target+bothEP+all7completeHuangpiNorthRoadways,60mcontext,roundoutward10m'},
           {'id':'south_detail','label':'上海博物馆南门 main 原坐标局部','bounds_xy':square_door(doors[0]['xy']),
            'anchor_ids':[doors[0]['source_id'],'way/'+str(TARGET_ID)],'focus_door':doors[0]['source_id'],
            'rule':'260m square centered on original registered Southmain coordinate; no sourcepoint movement'},
           {'id':'north_detail','label':'上海博物馆北侧 exit 原坐标局部（仅门外）','bounds_xy':square_door(doors[1]['xy']),
            'anchor_ids':[doors[1]['source_id'],'way/'+str(TARGET_ID)],'focus_door':doors[1]['source_id'],
            'rule':'260m square centered on original registered Northexit coordinate; no sourcepoint movement'}]
    for view in views:
        b=view['bounds_xy'];view.update({'width_m':b[2]-b[0],'height_m':b[3]-b[1],'center_xy':[(b[0]+b[2])/2,(b[1]+b[3])/2],
            'viewport_hash':hashlib.sha256(json.dumps(b,separators=(',',':')).encode()).hexdigest(),
            'target_building_fully_inside':box(*b).covers(tg),'both_registered_doors_inside':all(box(*b).covers(Point(d['xy']))for d in doors)})
    assert all(v['target_building_fully_inside']and v['both_registered_doors_inside']for v in views)
    assert all(box(*full).covers(g)for g in road_geoms.values())
    related_rel=[record(o,members=o.get('members',[]))for o in idx['relation'].values()if any(m['type']=='way'and m['ref']==TARGET_ID for m in o.get('members',[]))]
    confounders=[]
    for o in raw['elements']:
        t=o.get('tags',{})
        if t.get('wikidata')in{'Q779273','Q1325611'}:
            g,gb,gw=source_geometry(o,idx,xy);confounders.append(record(o,g,reason='DISTINCT_OBJECT_NOT_TARGET_MUSEUM',geometry_basis=gb))
    target_record=record(target,tg,source_node_ids=target['nodes'],valid=tg.is_valid,geometry_basis=basis,geometry_warning=warning,
                         bounds_xy=list(tg.bounds),centroid_xy=list(tg.centroid.coords)[0],related_relations=related_rel)
    objects={'status':'TARGET_SOURCE_IDENTITY_VERIFIED','target':target_record,'building_id':'way/'+str(TARGET_ID),'geometry':mapping(tg),
             'doors':doors,'confounders':confounders,'source':meta,'identity_basis':['namedbuilding+buildingyes+tourismmuseum','Q1051293','PeopleSquarePortugueseName','人民大道201号','bothregisteredEPnativeouterringmembers'],
             'physical_current_public_access':'UNKNOWN_NOT_FIELD_VERIFIED'}
    objects['conflicting_place_ids']=[o['source_id']for o in confounders]
    road_audit={'status':'SOURCE_ROAD_IDENTITY_VERIFIED','road_way_ids':[r['source_id']for r in road_records],'road_objects':road_records,
             'excluded_same_name_objects':excluded,'junctions':junctions,'endpoint_source_node_ids':sorted(endpoints),
             'geometry':mapping(unary_union(list(road_geoms.values()))),'source_total_centerline_length_m':sum(g.length for g in road_geoms.values()),
             'source':meta,'world_geometry_accuracy':'REAL_WORLD_GEOMETRY_UNVERIFIED','no_new_connections':True}
    return idx,xy,objects,road_audit,views

def finalize_inventory():
    """Attach actual figure source artist membership; no source/result edits."""
    inventory=read(ROOT/'audit/source_to_render_inventory.json')
    manifest=read(ROOT/'audit/figure_manifest.json');scene=read(ROOT/'data/scene.json')
    checks=[]
    for row in inventory['rows']:
        figures=[f for f in manifest['figures']if f['view_id']==row['view_id']]
        assert figures,row['view_id']
        primary=next((f for f in figures if len(f['panels'])==1),figures[0])
        base=primary['panels'][0]['base'];expected=set(row['source_ids']);actual=set(base['source_ids'])
        missing=sorted(expected-actual)
        row['rendered_count']=len(expected&actual);row['omitted_count']=len(missing)
        row['omitted_source_ids']=missing;row['rendered_scope']='ACTUAL_STATIC_SOURCE_ARTIST_IDS; LABEL_COLLISIONS_SEPARATE'
        row['labelled_count']=len(expected&set(base.get('label_source_ids',[])))
        row['rendered_per_figure']={f['name']:[len(expected&set(p['base']['source_ids']))for p in f['panels']]for f in figures}
        if missing:row['reason']='EXPORTED_SOURCE_OBJECT_NOT_DRAWN_IN_THIS_VIEW'
    for f in manifest['figures']:
        for panel in f['panels']:
            ids=set(panel['base']['source_ids'])
            checks.append({'figure':f['name'],'view_id':f['view_id'],'variant':panel['variant'],
                'target_source_artist_present':scene['target']['building_id']in ids,
                'South_native_point_present':scene['target']['doors'][0]['source_id']in ids,
                'North_native_point_present':scene['target']['doors'][1]['source_id']in ids})
    assert all(x['target_source_artist_present']and x['South_native_point_present']and x['North_native_point_present']for x in checks)
    inventory['actual_render_receipt']={'path':'audit/figure_manifest.json','sha256':sha(ROOT/'audit/figure_manifest.json')}
    inventory['rendered_status']='BOUND_TO_ACTUAL_RENDERED_SOURCE_ARTIST_IDS'
    write(ROOT/'audit/source_to_render_inventory.json',inventory)
    with(ROOT/'audit/source_to_render_inventory.csv').open('w',encoding='utf-8-sig',newline='')as f:
        wr=csv.DictWriter(f,fieldnames=list(inventory['rows'][0]));wr.writeheader()
        for row in inventory['rows']:wr.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in row.items()})
    coverage=read(ROOT/'audit/target_coverage_checks.json');coverage['actual_render_source_artist_checks']=checks
    coverage['actual_render_source_artists_present']=True
    coverage['visual_recognizability']='See actual author and independent image/browser review; artistpresence alone is not real-world validation'
    write(ROOT/'audit/target_coverage_checks.json',coverage)
    print(json.dumps({'inventory_rows':len(inventory['rows']),'missing_drawable_source_objects':sum(r['omitted_count']for r in inventory['rows']),
                      'target_and_both_EP_artist_checks':len(checks),'solver_calls_added':0}))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--from-fragment',action='store_true',help='Compatibility alias for --from-packaged; consumes full packaged frozen OSM')
    ap.add_argument('--from-packaged',action='store_true',help='Rebuild from full byte-identical frozen OSM and saved lineage shipped in this package')
    ap.add_argument('--finalize-inventory',action='store_true',help='Bind source-to-render census to actual generated figure membership only')
    args=ap.parse_args();packaged=args.from_fragment or args.from_packaged
    if args.finalize_inventory:
        finalize_inventory();return
    source_ref=ROOT/'data/source/full_source_reference.json'
    if packaged:
        meta=read(source_ref);p=ROOT/'data/source/sh-huangpu-01.osm.json';assert sha(p)==EXPECTED_SOURCE_SHA
        raw=read(p);lineage=read(ROOT/'data/source/previous_lineage.json')
    else:
        source_path=Path(r'C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581/OSM_GEOAPIFY_PED_AREA_CONNECTIVITY_R1/data/scenes/sh-huangpu-01/source.osm.json')
        assert sha(source_path)==EXPECTED_SOURCE_SHA
        raw=read(source_path)
        # This is a local byte-for-byte reuse of an existing frozen source, not acquisition.
        (ROOT/'data/source/sh-huangpu-01.osm.json').write_bytes(source_path.read_bytes())
        meta={'path':str(source_path),'sha256':EXPECTED_SOURCE_SHA,'timestamp':raw.get('osm3s',{}).get('timestamp_osm_base'),'source_crs':'EPSG:4326','working_crs':'EPSG:32651','bytes':source_path.stat().st_size}
        write(source_ref,meta)
        p=ROOT.parent/'SMART_CITY_WALKABILITY_FOUNDATION_PG1/phase1/data/sh-huangpu-01/scene.json'
        prior=read(p);lineage={f['properties']['source_id']:f['properties']for f in prior['features']}
        lineage['_lineage_source']={'path':str(p),'sha256':sha(p),'basis':'ACTUAL_SAVED_ADAPTER_LINEAGE_READ_ONLY'}
        del prior
    idx,xy,target,road,views=build_identity(raw,meta)
    full=box(*views[0]['bounds_xy']);frozen=read(ROOT/'data/frozen/maps/trial_map_data.json');w=next(x for x in frozen['windows']if x['window_id']=='native')
    membership={v:{e['source_id']for e in w['variants'][v]['edges']}for v in['R0','R1','R2']}
    features=[];metadata=[]
    for o in raw['elements']:
        if not o.get('tags'):continue
        g,basis,warning=source_geometry(o,idx,xy);ident=sid(o)
        if g is None:
            # Preserve known member metadata without inventing a polygon or bbox.
            if o['type']=='relation':
                members=[idx.get(m['type'],{}).get(m['ref'])for m in o.get('members',[])]
                visible=False
                for member in members:
                    if member:
                        mg,_,_=source_geometry(member,idx,xy)
                        if mg is not None and mg.intersects(full):visible=True;break
                if visible:metadata.append({'source_id':ident,'tags':o['tags'],'reason':warning,'geometry_basis':basis,'families':families(o,area_intent(o))})
            continue
        if not g.intersects(full):continue
        props=lineage.get(ident,{})
        features.append({'source_id':ident,'type':o['type'],'id':o['id'],'source_version':o.get('version'),'tags':o.get('tags',{}),
            'geometry':mapping(g),'families':families(o,area_intent(o)),'geometry_basis':basis,'source_geometry_warning':warning,
            'source_file':meta['path'],'source_sha256':meta['sha256'],'source_timestamp':meta['timestamp'],
            'imported_in_routing_context':props.get('imported_context','UNKNOWN_NO_LINEAGE'),'import_reason':props.get('import_reason','UNKNOWN_NO_LINEAGE'),
            'native_filter_status':props.get('native_filter_status'),'import_lineage_source':lineage.get('_lineage_source'),
            'graph_membership':{v:ident in membership[v]for v in membership},
            'graph_membership_semantics':'REFERENCE_AS_NATIVE_EDGE_OR_DERIVED_PARENT_IN_OLD_NW_DIAGNOSTIC; NOT_MUSEUM_DOOR_ROUTE',
            'is_target_building':ident==target['building_id'],'is_registered_door':ident in{d['source_id']for d in target['doors']},
            'is_huangpi_north_road':ident in road['road_way_ids']})
    features.sort(key=lambda f:(f['type'],f['id']))
    counts={fam:sum(fam in f['families']for f in features)for fam in FAMILIES}
    for view in views:
        frame=box(*view['bounds_xy']);selected=[f for f in features if shape(f['geometry']).intersects(frame)]
        view.update({'source_ids':[f['source_id']for f in selected],'source_count':len(selected),
            'family_counts':{fam:sum(fam in f['families']for f in selected)for fam in FAMILIES},
            'base_map_hash':hashlib.sha256(json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'complete_huangpi_road_ways_inside':[r['source_id']for r in road['road_objects']if frame.covers(shape(r['geometry']))]})
    width_fields=[{'source_id':f['source_id'],'tags':{k:v for k,v in f['tags'].items()if k in{'width','width:carriageway','width:lanes','est_width','kerb','curb'}}}for f in features if any(k in f['tags']for k in{'width','width:carriageway','width:lanes','est_width','kerb','curb'})]
    context={'scene_id':'shanghai_museum_peoples_square','label':'上海博物馆人民广场馆','bounds_xy':views[0]['bounds_xy'],'crs':'EPSG:32651','source':meta,
             'features':features,'metadata_only_objects':metadata,'family_counts':counts,
             'absence_status':{f:('PRESENT_EXPORTED'if counts[f]else'NOT_EXTRACTED'if any(f in m['families']for m in metadata)else'NOT_PRESENT_IN_FROZEN_SOURCE')for f in FAMILIES},
             'target':target,'road':road,'huangpi_road_ids':road['road_way_ids'],'views':views,'default_view':'target_overview','width_or_kerb_fields_unvalidated':width_fields,
             'frozen_overlay_window_id':'native','overlay_scope':'OLD_NW_SIDEWALK_DIAGNOSTIC_NOT_MUSEUM_DOOR_ROUTE',
             'algorithm_runs_added':0,'solver_calls_added':0,'external_map_requests':0,'new_data_downloads':0,'algorithm_result_drift':0,
             'real_world_geometry_status':'REAL_WORLD_GEOMETRY_UNVERIFIED'}
    write(ROOT/'data/scene.json',context);write(ROOT/'audit/target_objects.json',target);write(ROOT/'audit/huangpi_north_road_objects.json',road)
    windows={'identity_gate':'PASS_TARGET_SOURCE_BUILDING_AND_BOTH_EP_VERIFIED','default_view':'target_overview','source':meta,
             'rule_scope':'Cartographiccoverageonly; no algorithm endpoint/config/threshold change','views':views,
             'old_window_scope':'Oldway39764359-based320mwindow NOTvalidShanghaiMuseumbusinessscene; preservedonlyashistoricalNWsidewalkdiagnostic'}
    write(ROOT/'audit/window_definition.json',windows)
    cover={'status':'TARGET_SOURCE_COVERAGE_PASS','target_building':target['building_id'],'source_geometry_valid':target['target']['valid'],
           'both_door_original_nodes_on_boundary':True,'road_way_count':len(road['road_way_ids']),'same_name_platform_excluded':True,
           'all7roads_fullinside_block':len(views[0]['complete_huangpi_road_ways_inside'])==7,'views':[{'id':v['id'],'target_building_fully_inside':v['target_building_fully_inside'],'both_registered_doors_inside':v['both_registered_doors_inside'],'source_count':v['source_count']}for v in views],
           'scene_identity_not_real_world_accuracy':'Sourceobjectidentityverified; noindependentcurrentgeoreferencedreferencefound','world_geometry_status':'REAL_WORLD_GEOMETRY_UNVERIFIED'}
    write(ROOT/'audit/target_coverage_checks.json',cover)
    if not packaged:
        # Package exactly the raw records and references needed for map rebuilding.
        wanted={f['source_id']for f in features}|{m['source_id']for m in metadata}|{'way/39764359'}
        wanted|={e['source_id']for v in w['variants'].values()for e in v['edges']}
        wanted|={sid(o)for o in idx['relation'].values()if any(m['type']=='way'and m['ref']==TARGET_ID for m in o.get('members',[]))}
        for j in road['junctions']:wanted|=set(j['incident_road_ids'])
        pending=list(wanted);done=set()
        while pending:
            ident=pending.pop()
            if ident in done:continue
            done.add(ident);typ,num=ident.split('/');o=idx.get(typ,{}).get(int(num))
            if not o:continue
            if typ=='way':pending.extend('node/'+str(n)for n in o.get('nodes',[]))
            if typ=='relation':pending.extend(m['type']+'/'+str(m['ref'])for m in o.get('members',[]))
        write(ROOT/'data/source/previous_lineage.json',{k:v for k,v in lineage.items()if k in wanted or k=='_lineage_source'})
    with(ROOT/'audit/window_object_inventory.csv').open('w',encoding='utf-8-sig',newline='')as f:
        wr=csv.DictWriter(f,fieldnames=['view_id','source_id','families','geometry_type','is_target_building','is_registered_door','is_huangpi_north_road']);wr.writeheader()
        for v in views:
            for feature in features:
                if feature['source_id']in v['source_ids']:wr.writerow({'view_id':v['id'],'source_id':feature['source_id'],'families':';'.join(feature['families']),'geometry_type':feature['geometry']['type'],'is_target_building':feature['is_target_building'],'is_registered_door':feature['is_registered_door'],'is_huangpi_north_road':feature['is_huangpi_north_road']})
    inventory=[]
    for v in views:
        for fam in FAMILIES:
            selected=[f for f in features if f['source_id']in v['source_ids']and fam in f['families']]
            inventory.append({'view_id':v['id'],'source_family':fam,'source_context_count':len(selected),'exported_count':len(selected),
                'rendered_count':'PENDING_ACTUAL_RENDER_MEMBERSHIP','omitted_count':0,'source_ids':[f['source_id']for f in selected],
                'reason':'PRESENT_EXPORTED_NOT_A_ROUTE_ADMISSION_CLAIM'if selected else'NOT_PRESENT_IN_FROZEN_SOURCE_WITHIN_THIS_VIEW'})
    write(ROOT/'audit/source_to_render_inventory.json',{'rows':inventory,'count_semantics':'Familiesoverlap; sourcecontextobjectcountnotroutingsegmentcount; rendercountrequiresactualrenderIDs'})
    with(ROOT/'audit/source_to_render_inventory.csv').open('w',encoding='utf-8-sig',newline='')as f:
        wr=csv.DictWriter(f,fieldnames=list(inventory[0]));wr.writeheader()
        for row in inventory:wr.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,list)else v for k,v in row.items()})
    print(json.dumps({'target_gate':'PASS','target':target['building_id'],'Huangpi_road_ways':road['road_way_ids'],'features':len(features),'views':[{'id':v['id'],'bounds':v['bounds_xy'],'objects':v['source_count']}for v in views],'algorithm_runs_added':0},ensure_ascii=False))

if __name__=='__main__':main()


