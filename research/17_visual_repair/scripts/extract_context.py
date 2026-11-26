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

def families(o,area=False):
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

def old_render_policy(o,old_present):
    if not old_present:return 'EXPORT_OMISSION_OLD_PAYLOAD_DOES_NOT_CARRY_SOURCE_OBJECT'
    t=o.get('tags',{});h=t.get('highway')
    if h in {'traffic_signals','bus_stop','street_lamp'}:return 'CARRIED_BUT_GENERIC_POINT_SYMBOL_NO_DISTINCT_TRAFFIC_FACILITY'
    if h in MOTOR:return 'CARRIED_BUT_UNIFORM_ROAD_LINEWIDTH_NO_CLASS_HIERARCHY'
    if h in PED:return 'CARRIED_BUT_SOURCE_WALKWAY_OPACITY_0_35_AND_ROUTING_OVERLAY_DOMINATES'
    if t.get('leisure')=='park':return 'CARRIED_BUT_GENERIC_CONTEXT_FILL_NOT_DISTINCT_PARK_SYMBOL'
    if t.get('railway') or t.get('barrier'):return 'CARRIED_BUT_GENERIC_CONSTRAINT_STYLE_NO_DISTINCT_FAMILY'
    return 'CARRIED_DEFAULT_ENABLED_BUT_GENERIC_CONTEXT_STYLE'

def collect_fragment(raw,features,extra_records,idx):
    wanted={sid(f)for f in features}|{r['source_id']for r in extra_records}
    # Include source members and nodes needed to reconstruct every exported ring.
    pending=list(wanted);done=set()
    while pending:
        ident=pending.pop()
        if ident in done:continue
        done.add(ident);typ,num=ident.split('/');o=idx.get(typ,{}).get(int(num))
        if not o:continue
        if typ=='way':pending.extend('node/'+str(n)for n in o.get('nodes',[]))
        if typ=='relation':pending.extend(m['type']+'/'+str(m['ref'])for m in o.get('members',[]))
    elements=[o for o in raw['elements']if sid(o)in done]
    return {'version':raw.get('version',0.6),'generator':'LOCAL_FROZEN_SOURCE_SUBSET_NOT_NEW_ACQUISITION',
            '_frozen_full_clip_record_count':raw.get('_frozen_full_clip_record_count',len(raw['elements'])),
            'osm3s':raw.get('osm3s',{}),'elements':elements}

def extract(raw,w,source_meta,lineage,old_ids):
    idx={k:{}for k in ['node','way','relation']}
    for o in raw['elements']:idx[o['type']][o['id']]=o
    xy={n:PROJECT(o['lon'],o['lat'])for n,o in idx['node'].items()}
    frame=box(*w['bounds_xy']);features=[];metadata=[];spatial_source=[]
    membership={v:{e['source_id']for e in w['variants'][v]['edges']}for v in ['R0','R1','R2']}
    # Census each original tagged spatial object; untagged nodes remain references.
    reference_nodes=raw.get('_frozen_window_reference_node_count',sum(not o.get('tags')and frame.covers(Point(xy[n]))for n,o in idx['node'].items()))
    for o in raw['elements']:
        t=o.get('tags',{});ident=sid(o)
        if not t:continue
        g,basis,warning=source_geometry(o,idx,xy)
        if g is None:
            known_geometries=[]
            if o['type']=='way':
                coords=[xy[n]for n in o.get('nodes',[])if n in xy]
                if coords:known_geometries.append(LineString(coords)if len(coords)>1 else Point(coords[0]))
            elif o['type']=='relation':
                for m in o.get('members',[]):
                    if m['type']=='way'and m['ref']in idx['way']:
                        member=idx['way'][m['ref']];mg,_,_=source_geometry(member,idx,xy)
                        if mg is not None:known_geometries.append(mg)
            if any(mg.intersects(frame)for mg in known_geometries):
                metadata.append({'source_id':ident,'tags':t,'families':families(o,area_intent(o)),'reason':warning,'geometry_basis':basis,'spatial_scope':'ORIGINAL_MEMBER_GEOMETRY_INTERSECTS_WINDOW; NOT_A_CONFIRMED_INDEPENDENT_RELATION_GEOMETRY'})
            continue
        if not g.intersects(frame):continue
        fs=families(o,area_intent(o));spatial_source.append(ident)
        props=lineage.get(ident,{})
        graph={v:ident in membership[v]for v in membership}
        if any(graph.values()):route_reason='SOURCE_ID_REFERENCED_IN_SAVED_VARIANT_GRAPH; NOT_A_NEW_ADMISSION_CHECK'
        else:route_reason=props.get('native_filter_status')or props.get('import_reason')or'CONTEXT_OBJECT_NOT_REFERENCED_IN_SAVED_LOCAL_VARIANT_GRAPHS'
        features.append({'source_id':ident,'type':o['type'],'id':o['id'],'source_version':o.get('version'),
            'tags':t,'geometry':mapping(g),'families':fs,'kind':fs,'geometry_basis':basis,'source_geometry_warning':warning,
            'source_file':source_meta['path'],'source_sha256':source_meta['sha256'],'source_timestamp':source_meta['timestamp'],
            'source_crs':'EPSG:4326','working_crs':'EPSG:32651',
            'imported_in_previous_payload':ident in old_ids,'imported_in_routing_context':props.get('imported_context','UNKNOWN_NO_PRIOR_LINEAGE'),
            'import_reason':props.get('import_reason','NOT_RECORDED_IN_OLD_LINEAGE'),
            'import_lineage_source':lineage.get('_lineage_source',{'status':'UNKNOWN_NO_PRIOR_LINEAGE_SOURCE'}),
            'previously_rendered_policy':old_render_policy(o,ident in old_ids),
            'graph_membership':graph,'routing_reason':route_reason,'native_filter_status':props.get('native_filter_status'),
            'source_id_membership_is_not_side_association':True})
    features.sort(key=lambda x:(x['type'],x['id']))
    counts={k:sum(k in f['families']for f in features)for k in FAMILIES}
    metadata_counts={k:sum(k in f['families']for f in metadata)for k in FAMILIES}
    absence={k:('PRESENT_EXPORTED'if counts[k]else'NOT_EXTRACTED'if metadata_counts[k]else'NOT_PRESENT_IN_FROZEN_SOURCE')for k in FAMILIES}
    widths=[{'source_id':f['source_id'],'tags':{k:v for k,v in f['tags'].items()if k in {'width','width:carriageway','width:lanes','est_width','kerb','curb'}}}for f in features if any(k in f['tags']for k in {'width','width:carriageway','width:lanes','est_width','kerb','curb'})]
    context={'window_id':w['window_id'],'scene_id':w['scene_id'],'label':w['label'],'bounds_xy':w['bounds_xy'],
        'crs':'EPSG:32651','source':source_meta,'features':features,'family_counts':counts,'absence_status':absence,
        'source_counts':{'raw_clip_records':raw.get('_frozen_full_clip_record_count',len(raw['elements'])),'window_tagged_spatial_objects':len(features),
            'window_metadata_only_objects':len(metadata),'coordinate_reference_nodes_not_independent_features':reference_nodes},
        'metadata_only_objects':metadata,'width_or_kerb_fields_unvalidated':widths,
        'road_surface_width_status':'SOURCE_ROAD_AREA_PRESENT'if counts['road_areas']else'road surface/width unavailable in frozen source; any raw width field is unvalidated metadata only',
        'algorithm_runs_added':0,'solver_calls_added':0,'external_map_requests':0,'new_data_downloads':0,
        'geometry_policy':'Original un-clipped geometry, exact intersects fixed320m window; viewport clips only; no generated road area/width/curb; unresolved source areas retain explicit member/ring outline identity.'}
    fragment=collect_fragment(raw,[idx[f['type']][f['id']]for f in features],metadata,idx)
    fragment['_frozen_window_reference_node_count']=reference_nodes
    return context,fragment

def finalize_inventory():
    """Attach actual emitted source artist identities; never equate export to render."""
    inv=read(ROOT/'audit/source_to_figure_inventory.json')
    receipt=read(ROOT/'audit/static_render_membership.json')
    for row in inv['rows']:
        figures=[f for f in receipt['figures']if f['window_id']==row['window_id']]
        full=next(f for f in figures if f['figure']=='context_full')
        rendered=set(full['panels'][0]['base']['source_ids']);expected=set(row['source_ids'])
        row['rendered_count']=len(rendered&expected)
        notdrawn=sorted(expected-rendered)
        row['exported_not_rendered_source_ids']=notdrawn
        row['omitted_count']=len(row['metadata_only_source_ids'])+len(notdrawn)
        if notdrawn:
            row['omission_reason']='EXPORTED_CONTEXT_OBJECT_NOT_EMITTED_BY_FULL_CONTEXT_RENDERER'
        row['rendered_count_scope']='ACTUAL_SOURCE_ARTIST_IDS_IN_CONTEXT_FULL; label collision suppression is separate'
        row['rendered_per_figure']={f['figure']:[len(set(p['base']['source_ids'])&expected)for p in f['panels']]for f in figures}
        row['labelled_count']=len(set(full['panels'][0]['base'].get('label_source_ids',[]))&expected)
    inv['rendered_status']='BOUND_TO_ACTUAL_STATIC_ARTIST_ID_RECEIPT'
    inv['static_render_receipt']={'path':'audit/static_render_membership.json','sha256':sha(ROOT/'audit/static_render_membership.json')}
    inv['note']='Rendered means a source artist emitted under figure viewport; not a subjective visibility guarantee. Labels may be collision-suppressed. Native/algorithm layers remain distinct.'
    write(ROOT/'audit/source_to_figure_inventory.json',inv)
    rows=inv['rows']
    with(ROOT/'audit/source_to_figure_inventory.csv').open('w',encoding='utf-8-sig',newline='')as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader()
        for row in rows:wr.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in row.items()})
    print(json.dumps({'inventory_rows':len(rows),'rendered_status':inv['rendered_status'],
                      'exported_not_rendered_total_overlapping_families':sum(len(r['exported_not_rendered_source_ids'])for r in rows)},ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fragments',action='store_true',help='Rebuild from packaged source fragments, not external full clips')
    ap.add_argument('--finalize-inventory',action='store_true',help='Bind inventory to actual emitted static-render source IDs only')
    args=ap.parse_args()
    if args.finalize_inventory:
        finalize_inventory();return
    if args.fragments:
        # The old renderer is a bound historical reference, not required input
        # for rebuilding packaged context. Do not reopen its external path.
        prior_renderer_evidence=dict(read(ROOT/'audit/context_extraction.json')['prior_renderer_evidence'])
        prior_renderer_evidence['verification_scope']='BOUND_HISTORICAL_REFERENCE_REUSED; OLD_RENDERER_NOT_REOPENED_DURING_FRAGMENT_REPLAY'
    else:
        prior_renderer=ROOT.parent/'PG1_RESUME_STREET_SIDE_R1/maps/viewer.js'
        prior_renderer_evidence={'path':str(prior_renderer),'sha256':sha(prior_renderer),
            'evidence':'baseKind collapses distinct source families into road/native/crossing/constraints; default-enabled allcarriedobjects; sourcewalkway opacity .35, allroadaxes width1.2; trafficpointgeneric; no sourcehighwayclass hierarchy.',
            'verification_scope':'ACTUAL_OLD_RENDERER_READ_DURING_FULL_SOURCE_EXTRACTION'}
    binding=read(ROOT/'audit/initial_binding.json');frozen=read(ROOT/'data/frozen/maps/trial_map_data.json');inventory=[];summaries=[]
    for w in frozen['windows']:
        wid=w['window_id'];src=next(x for x in binding['raw_sources']if x['scene_id']==w['scene_id']);fragment_path=ROOT/'data/context'/f'{wid}_source_fragment.json'
        meta={'path':src['path'],'sha256':src['sha256'],'timestamp':w['source_timestamp'],'version':'FROZEN_OSM_CLIP','full_clip_bytes':src['bytes']}
        if args.fragments:
            raw=read(fragment_path);lineage=read(ROOT/'data/context'/f'{wid}_previous_lineage.json')
        else:
            assert sha(src['path'])==src['sha256'];raw=read(src['path'])
            # Read actual prior metadata only; it is not rerunning the adapter.
            p=FOUNDATION/'phase1/data'/w['scene_id']/'scene.json';prior=read(p)
            lineage={f['properties']['source_id']:f['properties']for f in prior['features']}
            lineage['_lineage_source']={'path':str(p),'sha256':sha(p),'basis':'ACTUAL_SAVED_FOUNDATION_ADAPTER_LINEAGE; NO_ADAPTER_OR_ROUTER_REEXECUTION'}
            del prior;gc.collect()
        old_ids={f['source_id']for f in w['source_features']}
        context,fragment=extract(raw,w,meta,lineage,old_ids)
        selected={f['source_id']for f in context['features']}
        local_lineage={k:v for k,v in lineage.items()if k in selected or k=='_lineage_source'}
        if not args.fragments:
            write(fragment_path,fragment);write(ROOT/'data/context'/f'{wid}_previous_lineage.json',local_lineage)
        write(ROOT/'data/context'/f'{wid}.json',context)
        for family in FAMILIES:
            fs=[f for f in context['features']if family in f['families']];md=[f for f in context['metadata_only_objects']if family in f['families']]
            inventory.append({'window_id':wid,'source_family':family,'frozen_source_count':len(fs)+len(md),
                'source_drawable_geometry_count':len(fs),'exported_context_count':len(fs),'rendered_count':'PENDING_ACTUAL_RENDER_RECEIPT',
                'routing_graph_count':sum(any(f['graph_membership'].values())for f in fs),
                'routing_graph_R0_count':sum(f['graph_membership']['R0']for f in fs),
                'routing_graph_R1_count':sum(f['graph_membership']['R1']for f in fs),
                'routing_graph_R2_count':sum(f['graph_membership']['R2']for f in fs),
                'routing_graph_count_semantics':'SOURCE_ID_REFERENCE_MEMBERSHIP_IN_NATIVE_OR_DERIVED_PARENT_EDGES; NOT_RAW_GEOMETRY_ADMISSION',
                'previous_payload_count':sum(f['imported_in_previous_payload']for f in fs),
                'newly_exported_count':sum(not f['imported_in_previous_payload']for f in fs),
                'omitted_count':len(md),'omission_reason':';'.join(sorted({str(f['reason'])for f in md}))if md else'NONE_DRAWABLE_SOURCE_CONTEXT_OMITTED',
                'absence_status':context['absence_status'][family],
                'source_ids':[f['source_id']for f in fs],'metadata_only_source_ids':[f['source_id']for f in md]})
        summary={'window_id':wid,'source_count':len(context['features']),'old_payload_count':len(old_ids),
            'newly_exported_ids':sorted(selected-old_ids),'old_payload_ids_not_in_new_context':sorted(old_ids-selected),
            'family_counts':context['family_counts'],'absence_status':context['absence_status'],
            'source_fragment_path':str(fragment_path.relative_to(ROOT)).replace('\\','/'),'source_fragment_sha256':sha(fragment_path),
            'context_sha256':sha(ROOT/'data/context'/f'{wid}.json')}
        summaries.append(summary);print(json.dumps(summary,ensure_ascii=False))
        del raw,lineage,fragment,context;gc.collect()
    write(ROOT/'audit/source_to_figure_inventory.json',{'scope':'Per original fixed320m window, taggedspatialobjects; familiesoverlap andmustnot sum; rawreference-node omissions not mapfeatureloss','rendered_status':'PENDING_ACTUAL_RENDER_MEMBERSHIP','rows':inventory})
    with(ROOT/'audit/source_to_figure_inventory.csv').open('w',encoding='utf-8-sig',newline='')as f:
        wr=csv.DictWriter(f,fieldnames=list(inventory[0]));wr.writeheader()
        for row in inventory:wr.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,list)else v for k,v in row.items()})
    write(ROOT/'audit/context_extraction.json',{'script_sha256':sha(__file__),'windows':summaries,
        'prior_renderer_evidence':prior_renderer_evidence,
        'algorithm_runs_added':0,'solver_calls_added':0,'external_map_requests':0,'new_data_downloads':0,
        'rendered_count_note':'Not claimed from exportedfeatures; rootrenderreceiptmustsupplyactualdrawnIDs.'})

if __name__=='__main__':main()
