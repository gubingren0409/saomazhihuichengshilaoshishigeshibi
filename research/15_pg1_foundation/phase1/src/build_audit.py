"""Read-only six frozen-scene source/import/routing/render audit. No solver/API/VG.

Imports immutable historical parsers with bytecode disabled. Replays only the
source adapter's segment admission predicate; no graph or shortest path is built.
All routes are read from hash-checked historical result JSON.
"""
import sys
sys.dont_write_bytecode = True
import argparse, collections, gc, gzip, hashlib, json, math, time, zipfile
from pathlib import Path
OUT = Path(__file__).resolve().parents[1]
from shapely.geometry import Point, LineString, shape, mapping
from shapely.strtree import STRtree
from shapely.validation import explain_validity

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def sid(o):return str(o['type'])+'/'+str(o['id'])
def families(o):
    t=o.get('tags',{}); h=t.get('highway'); f=[]
    if t.get('building') not in (None,'no') or t.get('building:part') not in (None,'no'):f.append('building')
    if h in MOTOR:f.append('vehicle_road')
    elif h in {'footway','pedestrian','path','steps','cycleway','bridleway','corridor'}:f.append('pedestrian_line')
    if t.get('area:highway'):f.append('road_area')
    if h in {'pedestrian','footway','path'} and (t.get('area')=='yes' or t.get('type')=='multipolygon'):f.append('pedestrian_area')
    if t.get('footway')=='sidewalk':f.append('sidewalk_geometry')
    if any(k.startswith('sidewalk') for k in t):f.append('sidewalk_tag_on_axis')
    if h=='crossing' or t.get('footway')=='crossing' or 'crossing' in t:f.append('crossing')
    if t.get('entrance'):f.append('entrance')
    if t.get('landuse') in {'grass','meadow','flowerbed','flower_bed'} or t.get('landcover') in {'grass','flowerbed'}:f.append('grass')
    if t.get('natural') in {'water','wetland'} or t.get('water') or t.get('waterway'):f.append('water')
    if t.get('natural') in {'wood','tree','scrub'} or t.get('leisure') in {'park','garden'}:f.append('vegetation_park')
    if t.get('barrier'):f.append('barrier')
    if restricted(t):f.append('restriction')
    if non_ground(t):f.append('level_steps_bridge_tunnel')
    return f or ['topology_node' if o['type']=='node' and not t else 'other_context']

def source_geometry(source,o):
    if o['type']=='node':return Point(source.projected[o['id']]),'ORIGINAL_SOURCE_POINT'
    t=o.get('tags',{}); refs=o.get('nodes',[])
    area=(o['type']=='relation' and t.get('type')=='multipolygon') or (o['type']=='way' and len(refs)>=4 and refs[0]==refs[-1] and (t.get('area')=='yes' or any(k in t for k in ['building','building:part','landuse','landcover','leisure','area:highway']) or t.get('natural') in {'water','wetland','wood'}))
    if area:
        g=source.area(sid(o))
        return g,'ORIGINAL_SOURCE_POLYGON_WITH_HOLES' if g is not None else 'UNRESOLVED_SOURCE_RING'
    if o['type']=='way' and len(refs)>=2 and all(n in source.projected for n in refs):return LineString([source.projected[n] for n in refs]),'ORIGINAL_SOURCE_LINE'
    return None,'NONSPATIAL_OR_INCOMPLETE_RELATION' if o['type']=='relation' else 'MISSING_SOURCE_NODES'

def adapter_context(source,obstacles):
    """Literal bounded replay of scene_data.py map_layers classification only."""
    imported={}
    for o in obstacles:
        k=obstacle_kind(o)
        imported[o['id']]={'kind':'GRASS' if k=='BACKGROUND_GRASS' else 'MAPPED_NON_RESTRICTED_AREA' if k=='AREA' else k,'geometry':mapping(o['geometry']),'basis':'SOURCE_OBSTACLE_ADAPTER'}
    for typ,objects in [('way',source.ways),('relation',source.relations)]:
        for n,o in objects.items():
            t=o.get('tags',{}); key=sid(o); refs=o.get('nodes',[])
            closed=(typ=='relation' and t.get('type')=='multipolygon') or (len(refs)>=4 and refs[0]==refs[-1])
            if restricted(t) and closed and area_role(t):
                g=source.area(key)
                if g is not None and key not in imported:imported[key]={'kind':'RESTRICTED','geometry':mapping(g),'basis':'EXPLICIT_RESTRICTED_AREA'}
            elif restricted(t) and typ=='way' and len(refs)>1 and all(n in source.projected for n in refs) and key not in imported:
                imported[key]={'kind':'RESTRICTED_LINEAR_ACCESS','geometry':mapping(LineString([source.projected[n] for n in refs])),'basis':'EXPLICIT_RESTRICTED_LINE'}
            face=(t.get('highway')=='pedestrian' and t.get('area')=='yes') or t.get('area:highway') in {'pedestrian','footway','path'}
            support=t.get('leisure') in {'park','garden','recreation_ground'} or t.get('surface') in {'paved','paving_stones','concrete','asphalt'}
            if closed and (face or support) and key not in imported:
                g=source.area(key)
                if g is not None:imported[key]={'kind':'PEDESTRIAN_AREA' if face else 'PARK' if t.get('leisure') else 'PAVING','geometry':mapping(g),'basis':'SOURCE_SUPPORT_POLYGON'}
            if typ=='way' and len(refs)>1 and all(n in source.projected for n in refs) and t.get('highway') and t.get('area')!='yes':
                imported[key]={'kind':'ROAD' if t['highway'] in MOTOR else 'NATIVE_WALKWAY','geometry':mapping(LineString([source.projected[n]for n in refs])),'basis':'FULL_SOURCE_HIGHWAY_LINE_CONTEXT_NOT_ROUTE_ADMISSION'}
    return imported

def choose_history(scene_id):
    rows=[json.loads(l)for l in (RUNTIME/'results/formal_registry.jsonl').read_text(encoding='utf8').splitlines()]
    candidates=[r for r in rows if r.get('request',{}).get('scene_id')==scene_id and r['status'].startswith('ROUTED')]
    candidates.sort(key=lambda r:(r.get('request',{}).get('connectivity_mode')=='CONDITIONAL_SEAMS',r.get('request',{}).get('method')=='F1',r.get('path','')),reverse=True)
    if not candidates:
        write(OUT/'data'/scene_id/'historical_variants.json',{'routes':[],'solver_invoked_this_audit':False})
        return {'status':'NO_HISTORICAL_APP_ROUTE','label':'无原登记门 / 本轮无对应 APP 路线；未造端点','solver_invoked_this_audit':False,'routes':[]},None
    r=candidates[0]; p=RUNTIME/r['path']; actual=sha(p)
    if actual!=r['result_sha256']:raise ValueError('HISTORICAL_RESULT_SHA_MISMATCH')
    d=read(p)
    history={'status':'HISTORICAL_RESULT_REPLAY_ONLY','label':'历史真实路线 · 本轮未求路','solver_invoked_this_audit':False,'path':str(p),'sha256':actual,'run_id':d['run_id'],'input':d['input'],'result_status':d['status'],'route':d['route'],'graph_record':d.get('graph'),'preprocessing_cache':d.get('preprocessing_cache'),'timestamp':d.get('timestamp')}
    endpoint=lambda rr:tuple(rr.get('request',{}).get(k)for k in ('start_id','door_id','purpose'))
    variants=[history];seen={(d['input'].get('method'),d['input'].get('connectivity_mode'))}
    for rr in candidates:
        key=(rr['request'].get('method'),rr['request'].get('connectivity_mode'))
        if endpoint(rr)!=endpoint(r) or key in seen:continue
        pp=RUNTIME/rr['path'];hh=sha(pp)
        if hh!=rr['result_sha256']:raise ValueError('HISTORICAL_VARIANT_SHA_MISMATCH')
        dd=read(pp);variants.append({'status':'HISTORICAL_RESULT_REPLAY_ONLY','path':str(pp),'sha256':hh,'run_id':dd['run_id'],'input':dd['input'],'result_status':dd['status'],'route':dd['route'],'solver_invoked_this_audit':False});seen.add(key)
    write(OUT/'data'/scene_id/'historical_variants.json',{'routes':variants,'endpoint_comparison':'SAME_START_DOOR_PURPOSE_ONLY','solver_invoked_this_audit':False})
    return history,d

def scene(row):
    tic=time.perf_counter(); ident=row['scene_id']; folder=OUT/'data'/ident; folder.mkdir(parents=True,exist_ok=True)
    raw_path=OLD/row['source_path']; actual=sha(raw_path)
    if actual!=row['source_sha256']:raise ValueError('RAW_SOURCE_HASH_MISMATCH')
    baseline_files={r['path']:r for r in read(OLD/'MANIFEST_SHA256.json')['files']}
    inputs=[row['source_path'],f'data/scenes/{ident}/frozen_scene.json',f'data/connectivity/{ident}_native_lines.json',f'data/connectivity/{ident}_source_inventory.json',f'data/connectivity/{ident}_faces.json']
    input_receipt=[]
    for rel in inputs:
        expected=baseline_files[rel]['sha256']; got=sha(OLD/rel)
        if expected!=got:raise ValueError('FROZEN_INPUT_MANIFEST_MISMATCH:'+rel)
        input_receipt.append({'path':str(OLD/rel),'sha256':got,'bytes':(OLD/rel).stat().st_size})
    write(folder/'input_receipt.json',input_receipt)
    raw=read(raw_path); source=Source(raw); frozen=read(OLD/'data/scenes'/ident/'frozen_scene.json')
    all_objects={sid(o):o for o in raw['elements']}; lines={x['source_id']:x for x in read(OLD/'data/connectivity'/f'{ident}_native_lines.json')}
    candidates={x['source_id']:x for x in read(OLD/'data/connectivity'/f'{ident}_source_inventory.json')}
    faces={x['source_id']:x for x in read(OLD/'data/connectivity'/f'{ident}_faces.json')}
    obstacles,unlocated=source.obstacles([]); imported=adapter_context(source,obstacles)
    diag,diag_unresolved=_context_features(source,ident); display={f['properties']['id']:f for f in diag}
    for k,l in lines.items():
        if l.get('geometry'):display[k]={'geometry':l['geometry'],'properties':{'id':k,'tags':l['tags'],'kind':'ROAD'if l['tags'].get('highway')in MOTOR else'NATIVE_WALKWAY','geometry_role':'INDEPENDENT_NATIVE_SOURCE_LINE'}}
    # Actual frozen adapter segment admission, without _build_graph or solver.
    tree=STRtree([o['geometry']for o in obstacles]); native=collections.defaultdict(list); rejected=collections.defaultdict(list); native_node_refs=set()
    segments,_,raw_stats=_segments(raw)
    with gzip.open(folder/'native_admission.jsonl.gz','wt',encoding='utf8')as out:
        for seg in segments:
            g=LineString([source.projected[seg.a[0]],source.projected[seg.b[0]]]); t=source.ways[seg.way].get('tags',{})
            contacts=[obstacles[int(i)]for i in tree.query(g,predicate='intersects')]
            d=segment_decision(g,t,contacts,'S1',native_nodes=(seg.a[0],seg.b[0]),endpoint_tags=[source.nodes[n].get('tags',{})for n in(seg.a[0],seg.b[0])])
            rec={'source_id':'way/'+str(seg.way),'segment_index':seg.index,'source_node_ids':[seg.a[0],seg.b[0]],'xy':list(g.coords),'directions':list(seg.directions),'evidence':seg.evidence,**d}
            if d['status']==KEEP:native_node_refs.update(['node/'+str(seg.a[0]),'node/'+str(seg.b[0])])
            (native if d['status']==KEEP else rejected)[rec['source_id']].append(rec)
            out.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n')
    history,hist=choose_history(ident)
    write(folder/'historical_route.json',history)
    # Existing supplemental graph caches are NOT the complete global graph.
    cache_receipt=[]; supplemental=[]
    if hist:
        key=hist.get('preprocessing_cache',{}).get('key','')
        for p in sorted((RUNTIME/'data').glob('*_graphs/'+key+'*.gz'))if key else []:
            counts=collections.Counter()
            with gzip.open(p,'rt',encoding='utf8')as fh:
                for line in fh:
                    r=json.loads(line);counts[r.get('kind')]+=1
                    if r.get('kind')=='arc':
                        for s in r.get('segments',[]):
                            if s.get('xy'):supplemental.append({'geometry':{'type':'LineString','coordinates':s['xy']},'properties':{k:v for k,v in s.items()if k!='xy'}})
            cache_receipt.append({'path':str(p),'sha256':sha(p),'counts':dict(counts),'scope':'PERSISTED_SUPPLEMENTAL_GRAPH_ONLY_NOT_ENTIRE_GLOBAL_GRAPH'})
    features=[]; imported_only_features=[]; counters=collections.defaultdict(collections.Counter); geomhash={}; exact_dupes=[]; invalid=[]; area_objects=[]
    with gzip.open(folder/'object_lineage.jsonl.gz','wt',encoding='utf8')as ledger:
        for k,o in all_objects.items():
            tags=o.get('tags',{}); fam=families(o); g,basis=source_geometry(source,o); imp=imported.get(k); face=faces.get(k); line=lines.get(k); dr=display.get(k)
            topology=o['type']=='node' and not tags
            if topology:ing_reason='PRESERVED_AS_SOURCE_TOPOLOGY_COORDINATE_NOT_STANDALONE_CONTEXT'
            elif imp:ing_reason=imp['basis']
            elif line:ing_reason='SOURCE_LINE_IN_DIAGNOSTIC_INVENTORY; '+line['status']
            elif o['type']=='node':ing_reason='SOURCE_TAGGED_NODE_NOT_IN_SCENE_ADAPTER_MAP_LAYERS; DIAGNOSTIC_RETAINS'
            else:ing_reason='OUTSIDE_SCENE_ADAPTER_CONTEXT_FAMILIES; DIAGNOSTIC_MAY_RETAIN'
            reason= candidates.get(k,{}).get('status') or line.get('status') if line else candidates.get(k,{}).get('status')
            graph={'native_kept_segments':len(native[k]),'native_rejected_segments':len(rejected[k]),'native_rejection_reasons':dict(collections.Counter(str(x.get('reason',x.get('status')))for x in rejected[k])),'face_status':face.get('status')if face else None,'face_omega_geometry_hash':face.get('geometry_hash')if face else None,'admission_or_filter_reason':reason,'scope':'NATIVE_ADAPTER_REPLAY_AND_FROZEN_FACE_RECORDS; FULL_GLOBAL_VG_NOT_REBUILT'}
            render={'scene_adapter_context':bool(imp),'historical_diagnostic_render':bool(dr or face),'historical_road_name_label':False,'historical_road_class_label':False,'historical_style':'ROAD_1.8PX_GRAY_NO_NAME_CLASS_LABEL'if 'vehicle_road'in fam else 'SOURCE_DIAGNOSTIC_STYLE','source_absence':False,'render_absence_reason':None if dr or face else 'NONSPATIAL_RELATION_OR_TOPOLOGY_SUPPORT_OR_UNRESOLVED_GEOMETRY','new_review_render':g is not None and not topology}
            rec={'scene_id':ident,'source_id':k,'families':fam,'source_version':o.get('version'),'source_timestamp':o.get('timestamp'),'clip_timestamp':raw.get('osm3s',{}).get('timestamp_osm_base'),'raw':{'tags':tags,'geometry_basis':basis,'geometry_type':g.geom_type if g is not None else None,'geometry_valid':g.is_valid if g is not None else None,'geometry_validity_reason':explain_validity(g)if g is not None else None,'node_ids':o.get('nodes',[]),'member_ids':[str(m['type'])+'/'+str(m['ref'])for m in o.get('members',[])]},'import':{'context_imported':bool(imp),'reason':ing_reason,'tags_retained':sorted(tags)if imp else [],'tags_dropped_from_context':[]if imp else sorted(tags),'tags_retained_in_diagnostic':sorted(tags)if dr or line or face else [],'tag_status':'CONTEXT_OMISSION_IS_STAGE_SPECIFIC; ORIGINAL_RAW_TAGS_REMAIN_ON_DISK','geometry_transform':'EPSG:4326→EPSG:32651; always_xy','geometry_changed':bool(imp and g is not None and not g.equals(shape(imp['geometry'])))},'routing':graph,'render':render}
            rec['routing']['native_topology_endpoint']=k in native_node_refs
            ledger.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n')
            if g is None and imp:
                imported_only_features.append({'type':'Feature','geometry':imp['geometry'],'import_geometry':imp['geometry'],'properties':{'source_id':k,'families':fam,'tags':tags,'imported_context':True,'import_kind':imp['kind'],'import_reason':ing_reason,'geometry_basis':'IMPORTED_ADAPTER_FALLBACK_BOUNDING_BOX_NOT_ORIGINAL_SOURCE_GEOMETRY','source_geometry_available':False,'diagnostic_render':False,'source_clip_sha256':actual}})
            for f in fam:
                c=counters[f];c['raw_objects']+=1;c['imported_context']+=bool(imp);c['diagnostic_render']+=bool(dr or face);c['review_render']+=g is not None and not topology;c['native_route_objects']+=bool(native[k]);c['face_objects']+=bool(face);c['unresolved_geometry']+=g is None;c['geometry_invalid']+=g is not None and not g.is_valid
            if g is not None and not topology:
                if g.geom_type in {'Polygon','MultiPolygon'}:area_objects.append((k,g))
                gh=hashlib.sha256(g.normalize().wkb).hexdigest()
                if gh in geomhash:exact_dupes.append({'a':geomhash[gh],'b':k,'basis':'IDENTICAL_NORMALIZED_GEOMETRY; NOT_AUTOMATIC_SEMANTIC_DUPLICATE'})
                else:geomhash[gh]=k
                if not g.is_valid:invalid.append({'source_id':k,'reason':explain_validity(g)})
                features.append({'type':'Feature','geometry':mapping(g),'properties':{'source_id':k,'families':fam,'tags':tags,'geometry_basis':basis,'imported_context':bool(imp),'import_reason':ing_reason,'native_kept_segments':len(native[k]),'native_filter_status':line.get('status')if line else None,'face_status':face.get('status')if face else None,'diagnostic_render':bool(dr or face),'diagnostic_properties':dr.get('properties',{})if dr else {},'source_version':o.get('version'),'source_clip_sha256':actual}})
                features[-1]['properties']['native_topology_endpoint']=k in native_node_refs
                features[-1]['import_geometry']=imp['geometry']if imp else None
                features[-1]['properties']['import_kind']=imp['kind']if imp else None
                features[-1]['diagnostic_geometry']=dr['geometry']if dr else None
    overlap_pairs=[];atree=STRtree([g for k,g in area_objects])
    for a,(ka,ga)in enumerate(area_objects):
        for j in atree.query(ga,predicate='intersects'):
            j=int(j)
            if j<=a:continue
            kb,gb=area_objects[j];inter=ga.intersection(gb)
            if inter.area>1e-6:overlap_pairs.append({'a':ka,'b':kb,'intersection_area_m2':inter.area,'equal_geometry':ga.equals(gb),'policy':'RECORDED_ONLY; OVERLAP_DOES_NOT_IMPLY_DUPLICATE_OR_AUTOMATIC_DROP'})
    write(folder/'source_polygon_overlaps.json',overlap_pairs)
    xy=PROJECT(*frozen['target']); view=[xy[0]-520,xy[1]-420,xy[0]+520,xy[1]+420]
    fullpts=[PROJECT(x,y)for x,y in [(raw['bounds_wsen'][0],raw['bounds_wsen'][1]),(raw['bounds_wsen'][2],raw['bounds_wsen'][3])]]
    native_features=[{'geometry':{'type':'LineString','coordinates':r['xy']},'properties':{'source_id':k,'layer':'native','evidence':r['evidence'],'segment_index':r['segment_index'],'source_highway':all_objects[k].get('tags',{}).get('highway'),'road_axis':all_objects[k].get('tags',{}).get('highway')in MOTOR,'source_role':'ADMITTED_VEHICLE_ROAD_AXIS_NOT_INDEPENDENT_SIDEWALK'if all_objects[k].get('tags',{}).get('highway')in MOTOR else'ADMITTED_NATIVE_PEDESTRIAN_SOURCE_LINE'}}for k,rr in native.items()for r in rr]
    face_features=[{'geometry':f['omega'],'properties':{'source_id':k,'kind':'LEGAL_OMEGA','status':f.get('status'),'source_geometry':f['source_geometry'],'clearance_m':f.get('clearance_m')}}for k,f in faces.items()if f.get('omega')]
    info={'scene_id':ident,'label':row['label'],'split':'DEVELOPMENT_FROZEN','source_path':str(raw_path),'source_sha256':actual,'source_timestamp':raw.get('osm3s',{}).get('timestamp_osm_base'),'source_crs':'EPSG:4326','working_crs':'EPSG:32651','bounds_wsen':raw['bounds_wsen'],'full_bounds_xy':[fullpts[0][0],fullpts[0][1],fullpts[1][0],fullpts[1][1]],'block_bounds_xy':view,'target_xy':xy,'registered_entrances':frozen.get('r4_entrances',[]),'history':{k:v for k,v in history.items()if k!='route'},'counts':{k:dict(v)for k,v in counters.items()},'raw_total':len(raw['elements']),'raw_unique':len(all_objects),'raw_native_stats':raw_stats,'native_kept_segments':sum(map(len,native.values())),'native_rejected_segments':sum(map(len,rejected.values())),'frozen_mapped_edge_count':row['mapped_edge_count'],'road_area_source_count':sum('area:highway'in o.get('tags',{})for o in raw['elements']),'exact_geometry_duplicates':exact_dupes,'invalid_source_geometries':invalid,'unlocated_adapter_obstacles':unlocated,'diagnostic_unresolved_count':len(diag_unresolved),'supplemental_graph_receipt':cache_receipt,'full_global_vg_status':'NOT_REBUILT; HISTORICAL_RESULT_GRAPH_COUNTS_ONLY','no_api_requests':True,'no_fresh_solver':True,'elapsed_s':round(time.perf_counter()-tic,3)}
    info['positive_area_overlap_count']=len(overlap_pairs)
    info['road_tag_presence']={k:sum(k in o.get('tags',{})for o in source.ways.values()if o.get('tags',{}).get('highway')in MOTOR)for k in ['name','highway','width','lanes','sidewalk','foot','access','surface','layer','level','bridge','tunnel']}
    info['geometry_validity_scope']='PARSED_EXPORT_GEOMETRY_ONLY; UNRESOLVED_RAW_RINGS_NOT_PROVEN_VALID'
    info['imported_only_unresolved_source_count']=len(imported_only_features)
    write(folder/'scene.json',{'info':info,'features':features,'imported_only_features':imported_only_features,'native_edges':native_features,'legal_faces':face_features,'supplemental_graph_edges':supplemental,'historical_route':history.get('route')})
    write(folder/'summary.json',info)
    print(json.dumps({'scene_id':ident,'features':len(features),'native_segments':info['native_kept_segments'],'seconds':info['elapsed_s'],'folder':str(folder)},ensure_ascii=False),flush=True)
    return info

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--scene');ap.add_argument('--baseline',type=Path,required=True,help='Immutable R1 review ZIP; never extracted or mutated');ap.add_argument('--source-root',type=Path,required=True,help='Existing read-only R1 unpacked root');ap.add_argument('--runtime',type=Path,required=True,help='Existing R1 historical result root');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    global OLD,RUNTIME,OUT,Source,PROJECT,_segments,segment_decision,KEEP,obstacle_kind,restricted,non_ground,area_role,MOTOR,_context_features
    OLD=args.source_root.resolve();RUNTIME=args.runtime.resolve();OUT=args.out.resolve();OUT.mkdir(parents=True,exist_ok=True)
    if OUT==OLD or OLD in OUT.parents or OUT==RUNTIME or RUNTIME in OUT.parents:raise ValueError('OUTPUT_MUST_BE_ISOLATED_FROM_BASELINE_AND_HISTORICAL_RUNTIME')
    baseline_sha=sha(args.baseline)
    if baseline_sha!='d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed':raise ValueError('NOT_FIXED_FINAL_R1_ZIP')
    with zipfile.ZipFile(args.baseline)as z:
        members=[n for n in z.namelist()if n.endswith('MANIFEST_SHA256.json')and n.count('/')<=1]
        if len(members)!=1:raise ValueError('AMBIGUOUS_BASELINE_MEMBER_MANIFEST')
        if hashlib.sha256(z.read(members[0])).hexdigest()!=sha(OLD/'MANIFEST_SHA256.json'):raise ValueError('UNPACKED_MANIFEST_NOT_BOUND_TO_FIXED_ZIP')
    sys.path.insert(0,str(OLD))
    from src.frozen_scene.native_adapter import Source, PROJECT
    from src.frozen_scene.local_route import _segments
    from src.frozen_scene.semantics import segment_decision, KEEP, obstacle_kind
    from src.scene_data import restricted, non_ground, area_role, MOTOR
    from src.connectivity_view import _context_features
    manifest=read(OLD/'data/scene_manifest.json'); rows=[r for r in manifest['scenes']if not args.scene or r['scene_id']==args.scene]
    checked=[]; old_manifest={r['path']:r for r in read(OLD/'MANIFEST_SHA256.json')['files']}
    for rel in ['src/scene_data.py','src/connectivity_view.py','src/frozen_scene/native_adapter.py','src/frozen_scene/local_route.py','src/frozen_scene/semantics.py','app/app.js','data/scene_manifest.json']:
        actual=sha(OLD/rel); expected=old_manifest.get(rel,{}).get('sha256'); checked.append({'path':str(OLD/rel),'sha256':actual,'manifest_sha256':expected,'matches':actual==expected})
    if not all(r['matches']for r in checked):raise ValueError('HISTORICAL_CODE_MANIFEST_MISMATCH')
    write(OUT/'historical_code_receipt.json',checked)
    write(OUT/'baseline_receipt.json',{'zip':str(args.baseline.resolve()),'sha256':baseline_sha,'unpacked_root':str(OLD),'runtime':str(RUNTIME),'scope':'NO_SOLVER_NO_GRAPH_CONSTRUCTION_NO_API; NATIVE_ADMISSION_PREDICATE_REPLAY_ONLY'})
    for r in rows:scene(r);gc.collect()
    summaries=[read(p)for p in sorted((OUT/'data').glob('*/summary.json'))]
    write(OUT/'scene_index.json',summaries)
if __name__=='__main__':main()
