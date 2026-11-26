"""Frozen-source pedestrian faces and full-domain restrictions, never routes.

The main face collection is the source-area set already represented by each
scene's frozen mapped-edge file. IDs select the fixed comparison population;
source tags, topology, permission, level and coverage still determine admission.
"""
from __future__ import annotations
from functools import lru_cache
from hashlib import sha256
import gzip,json,math
from pathlib import Path
from shapely import make_valid,normalize
from shapely.geometry import Point,Polygon,LineString,GeometryCollection,mapping,shape
from shapely.ops import unary_union,split
from shapely.prepared import prep
from shapely.strtree import STRtree
from src.frozen_scene.native_adapter import Source
from src.common_constraints import edge_conflicts,parsed_contract,digest,denied,explicit_non_ground
from src.frozen_scene.semantics import obstacle_kind

ROOT=Path(__file__).resolve().parents[1]
EPS=1e-6
WALK_AREA={'pedestrian','footway','path'}
PUBLIC={'yes','public','permissive','designated','official'}
FALSE={None,'no','false','0'}

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def file_sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def polygons(g):
    if g.geom_type=='Polygon':
        if g.area>EPS:yield g
    else:
        for part in getattr(g,'geoms',()):yield from polygons(part)
def geometry_sha(g):return sha256(normalize(g).wkb).hexdigest()
def metrics(g):
    parts=list(polygons(g))
    return {'area_m2':g.area,'component_count':len(parts),'hole_count':sum(len(p.interiors)for p in parts),
        'vertex_count':sum(len(p.exterior.coords)-1+sum(len(r.coords)-1 for r in p.interiors)for p in parts)}

def area_reason(tags,g):
    if not(tags.get('area:highway')in WALK_AREA or tags.get('area')=='yes'and tags.get('highway')in WALK_AREA):return 'SOURCE_NOT_EXPLICIT_PEDESTRIAN_AREA'
    # Match APP foot-specific permission priority; selected legacy area IDs are
    # fixed independently, so this cannot add unrepresented source areas.
    if denied(tags)or('pedestrian'in tags and tags['pedestrian']not in PUBLIC)or'pedestrian:conditional'in tags:return 'RESTRICTED_OR_CONDITIONAL_AREA'
    if explicit_non_ground(tags)or tags.get('ford')not in FALSE:return 'NON_GROUND_OR_UNRESOLVED_LAYER'
    if g is None or g.is_empty or not g.is_valid or g.geom_type not in {'Polygon','MultiPolygon'}:return 'UNRESOLVED_SOURCE_AREA_GEOMETRY'
    return None

def lock_selection(path=None):
    """Read-only repeated call; create once, before any FULL_FACE real queries."""
    path=Path(path)if path else ROOT/'data/face_selection_lock.json'
    rows=[]
    for scene in read(ROOT/'data/scene_manifest.json')['scenes']:
        source=ROOT/scene['source_path'];mapped=ROOT/scene['mapped_edges_path']
        if file_sha(source)!=scene['source_sha256']or file_sha(mapped)!=scene['mapped_edges_sha256']:raise ValueError('FIXED_SCENE_INPUT_CHANGED')
        ids=set();count=0
        with gzip.open(mapped,'rt',encoding='utf-8')as f:
            for line in f:
                r=json.loads(line);ids.add(r['source_area_id']);count+=1
        rows.append({'scene_id':scene['scene_id'],'source_sha256':scene['source_sha256'],'mapped_edges_sha256':scene['mapped_edges_sha256'],
            'area_ids':sorted(ids),'source_edge_rows':count,'selection':'ALL_SOURCE_AREA_IDS_IN_FROZEN_SCENE_MAPPED_EDGES_BEFORE_FULL_FACE_RESULTS',
            'admission':'Independent explicit pedestrian-area tags, source member completeness, ground/permission and full acquired coverage required'})
    result={'role':'PRE_EXPERIMENT_FIXED_AREA_POPULATION_NOT_ID_PERMISSION_ALLOWLIST','crs':'EPSG:32651','scenes':rows,'new_map_or_area_collection':False}
    if path.exists():
        if read(path)!=result:raise ValueError('FACE_SELECTION_LOCK_CHANGED')
    else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

@lru_cache(maxsize=1)
def _source(scene_id):
    row=next(r for r in read(ROOT/'data/scene_manifest.json')['scenes']if r['scene_id']==scene_id)
    p=ROOT/row['source_path']
    if file_sha(p)!=row['source_sha256']:raise ValueError('SOURCE_SHA_MISMATCH')
    return Source(read(p)),row

def source_ring_audit(source,sid):
    obj=source.obj(sid)
    members=obj.get('members',[])
    missing_ways=[m['ref']for m in members if m['type']=='way'and m['ref']not in source.ways]
    unsupported=[m for m in members if m['type']!='way'or(m.get('role')or'outer')not in{'outer','inner'}]
    ways=[obj]if obj['type']=='way'else[source.ways[m['ref']]for m in members if m['type']=='way'and m['ref']in source.ways]
    missing_nodes=sorted({n for w in ways for n in w.get('nodes',[])if n not in source.nodes})
    return {'object_type':obj['type'],'member_way_count':len(ways),'inner_way_members':sum(m.get('role')=='inner'for m in members),
        'outer_way_members':sum((m.get('role')or'outer')=='outer'for m in members),'missing_way_ids':missing_ways,'missing_node_ids':missing_nodes,
        'unsupported_members':unsupported,'source_ring_check':'Source.area polygonizes complete source line rings and checks every segment against result boundaries; holes retained'}

def _road_parts(g,roads):
    pieces=list(polygons(g))
    for record in roads:
        road=shape(record['geometry']);new=[]
        for p in pieces:
            if not p.intersects(road):new.append(p);continue
            try:new.extend(polygons(split(p,road)))
            except ValueError:new.append(p)
        pieces=new
    return [q for p in pieces for q in polygons(p.intersection(g))]

def compile_faces(data,full_common,cfg=None,selected_area_ids=None):
    """Build complete legal face geometry, independent of query start/route.

    full_common must cover the full acquired source clip. It is not the D30
    contract. No full-source faces are imported into masked prediction workers.
    """
    cfg=cfg or {}
    if float(cfg.get('face_clearance_m',.25))!=.25:raise ValueError('FROZEN_AREAL_CLEARANCE_MUST_BE_0_25')
    scene_id=data['scene_id'];source,row=_source(scene_id)
    locked=read(ROOT/'data/face_selection_lock.json')
    select=next(s for s in locked['scenes']if s['scene_id']==scene_id)
    if select['source_sha256']!=row['source_sha256']:raise ValueError('FACE_SOURCE_SELECTION_BINDING_CHANGED')
    pcommon=parsed_contract(full_common)if'contract'not in full_common else full_common
    common=pcommon['contract'];coverage=shape(common['coverage_geometry'])
    if not shape(common['domain']).equals(coverage):raise ValueError('FACE_CONSTRAINTS_REQUIRE_FULL_SOURCE_COVERAGE_NOT_D30')
    candidates=[]
    for sid in select['area_ids'] if selected_area_ids is None else sorted(set(selected_area_ids)):
        obj=source.obj(sid);audit=source_ring_audit(source,sid)
        try:g=source.area(sid)
        except Exception:g=None
        why=area_reason(obj.get('tags',{}),g)
        candidates.append((sid,obj,g,audit,why))
    active=[g for _,_,g,_,why in candidates if why is None]
    obstacles,unlocated=source.obstacles(active)
    index=STRtree([r['geometry']for r in obstacles])
    rows=[]
    for sid,obj,P,ring,why in candidates:
        base={'id':sid,'source_id':sid,'tags':obj.get('tags',{}),'source_clip_sha256':row['source_sha256'],
            'mapped_edges_sha256':row['mapped_edges_sha256'],'admission_policy':'FROZEN_R4_EXPLICIT_FACE_TAGS_AND_CURRENT_APP_FOOT_PRIORITY_GROUND_V1',
            'ring_audit':ring,'source_geometry':P,'status':why or 'ADMITTED','clearance_m':.25,'buffer_quad_segs':16,
            'buffer_arc_max_radial_polygonization_error_m':.25*(1-math.cos(math.pi/64)),
            'source_barrier_intersection_tolerance_m':.001,'numeric_geometry_tolerance_m':EPS,
            'outer_boundary_inset_m':0,'surface_assumption':'ORDINARY_OUTDOOR_GROUND_IF_UNTAGGED_NOT_FIELD_VERIFIED',
            'full_constraint_sha256':common.get('sha256'), 'unlocated_source_hazards':unlocated}
        if why:
            base.update(omega=GeometryCollection(),components=[],geometry_hash=geometry_sha(GeometryCollection()),source_metrics=metrics(P)if P is not None else None)
            rows.append(base);continue
        base['source_metrics']=metrics(P)
        lost=P.difference(coverage)
        if lost.area>EPS:
            base.update(status='INCOMPLETE_SOURCE_COVERAGE',excluded_source_area_m2=lost.area,omega=GeometryCollection(),components=[],geometry_hash=geometry_sha(GeometryCollection()))
            rows.append(base);continue
        near=[obstacles[int(i)]for i in index.query(P.buffer(.25),predicate='intersects')]
        overrides=[r for r in near if r['kind']=='AREA'and obstacle_kind(r)=='AREA']
        # Final APP already treats these as support after pedestrian-specific
        # allow overrides access; an access-tagged area is not a physical wall.
        areal=[r for r in near if r['kind']!='BARRIER'and r not in overrides]
        barriers=[r for r in near if r['kind']=='BARRIER']
        # All source holes participate in FULL_FACE, including ones too far
        # from the old outer band to affect its precomputed grid.
        holes=[]
        for ci,part in enumerate(polygons(P)):
            for hi,ring_g in enumerate(part.interiors):
                holes.append({'id':f'{sid}:inner/{ci}/{hi}','kind':'SOURCE_INNER_RING','geometry':Polygon(ring_g)})
        masks=unary_union([r['geometry'].buffer(.25,quad_segs=16)for r in areal+holes])
        omega=P.difference(masks).difference(pcommon['blocked_geometry']).intersection(coverage)
        repair={'applied':False,'area_before_m2':omega.area,'area_after_m2':omega.area,'symmetric_difference_m2':0}
        if not omega.is_valid:
            before=omega;omega=make_valid(omega);repair={'applied':True,'area_before_m2':before.area,'area_after_m2':omega.area,'symmetric_difference_m2':None,'reason':'GEOS overlay returned invalid geometry; polygonal parts only, no convex hull/simplification'}
        road_rows=[r for r in common.get('road_centerlines',[])if shape(r['geometry']).intersects(omega)]
        parts=_road_parts(omega,road_rows)
        parts=sorted(parts,key=lambda p:(p.bounds,geometry_sha(p)))
        components=[{'id':f'{sid}/component/{i}','geometry':g,'geometry_hash':geometry_sha(g),'metrics':metrics(g)}for i,g in enumerate(parts)]
        required=[]
        for barrier in barriers:
            for gate in barrier.get('gates',[]):
                if gate.get('allowed')and omega.covers(Point(gate['xy'])):
                    required.append({'id':gate['id'],'xy':list(gate['xy']),'role':'SOURCE_EXPLICIT_GATE','source_barrier_id':barrier['id'],'tags':gate.get('tags',{})})
        restrictions=[]
        for r in areal:
            restrictions.append({'source_id':r['id'],'kind':r['kind'],'tags':r.get('tags',{}),'geometry':mapping(r['geometry']),
                'mask_geometry':mapping(r['geometry'].buffer(.25,quad_segs=16)),'clearance_m':.25,'scope':'FROZEN_R4_NON_BARRIER_AREAL_RULE'})
        for r in holes:restrictions.append({'source_id':r['id'],'kind':r['kind'],'geometry':mapping(r['geometry']),'mask_geometry':mapping(r['geometry'].buffer(.25,quad_segs=16)),'clearance_m':.25})
        band=P.intersection(unary_union([p.exterior for p in polygons(P)]).buffer(3,quad_segs=16)).difference(masks).difference(pcommon['blocked_geometry'])
        base.update(omega=omega,components=components,geometry_hash=geometry_sha(omega),metrics=metrics(omega),repair=repair,
            barriers=barriers,required_points=required,road_constraints=road_rows,
            restriction_evidence=restrictions,clearance_mask_geometry=mapping(masks),
            source_holes=[{'id':r['id'],'geometry':mapping(r['geometry'])}for r in holes],
            legacy_foot_priority_override_differences=[{'id':r['id'],'tags':r.get('tags',{}),'geometry':mapping(r['geometry']),
                'reason':'CURRENT_APP_FOOT_SPECIFIC_ALLOW_OVERRIDES_GENERAL_ACCESS; NOT_A_PHYSICAL_OBSTACLE',
                'intersects_old_band':r['geometry'].buffer(.25,quad_segs=16).intersects(P.intersection(unary_union([p.exterior for p in polygons(P)]).buffer(3,quad_segs=16)))}for r in overrides],
            common_blocked_geometry=mapping(pcommon['blocked_geometry'].intersection(P)),
            edge_band_geometry=band,old_edge_band=band,
            edge_band_identity='GEOMETRIC_REFERENCE_ONLY; FROZEN_MAPPED_EDGES_REMAIN_ACTUAL_OLD_GRAPH',
            clearance_semantics='Source R4 non-barrier areal + all inner rings .25 quad16; P exterior unchanged; common .15 barrier/.30 gate openings and raw permission masks additionally preserved; original barrier exact-gate rule checked per edge',
            status='ADMITTED'if components else'NO_LEGAL_COMPONENT')
        rows.append(base)
    return rows

def face_edge_conflicts(line,face,full_common):
    """Whole-edge legality; a source gate is a point constraint, not a .3m licence."""
    line=line if hasattr(line,'geom_type')else LineString(line)
    reasons=[]
    if '_prepared_omega'not in face:
        face['_prepared_omega']=prep(face['omega'])
        face['_prepared_components']=[prep(r['geometry'])for r in face.get('components',[])]
        face['_barrier_index']=STRtree([r['geometry']for r in face.get('barriers',[])])
    if not face['_prepared_omega'].covers(line):reasons.append('OUTSIDE_FULL_FACE_OMEGA')
    if face['_prepared_components']and not any(p.covers(line)for p in face['_prepared_components']):reasons.append('NO_SINGLE_POSITIVE_WIDTH_COMPONENT')
    if 'contract'in full_common:common=full_common
    else:
        if face.get('_parsed_full_common_sha')!=full_common.get('sha256')or'_parsed_full_common'not in face:
            face['_parsed_full_common']=parsed_contract(full_common);face['_parsed_full_common_sha']=full_common.get('sha256')
        common=face['_parsed_full_common']
    reasons.extend(edge_conflicts(line,common,native=False,tags=face['tags'],source_id=face['source_id']))
    for index in face['_barrier_index'].query(line,predicate='intersects'):
        obj=face['barriers'][int(index)]
        g=obj['geometry'];hit=line.intersection(g)
        if hit.is_empty:continue
        contacts=[hit]if hit.geom_type=='Point'else list(hit.geoms)if hit.geom_type=='MultiPoint'else None
        if contacts is None or any(not any(gate.get('allowed')and Point(gate['xy']).distance(p)<=.001 and g.distance(Point(gate['xy']))<=.001 for gate in obj.get('gates',[]))for p in contacts):
            reasons.append('SOURCE_BARRIER_WITHOUT_EXACT_ALLOWED_GATE:'+obj['id'])
    return sorted(set(reasons))

def serializable_face(face):
    out={k:v for k,v in face.items()if not k.startswith('_')and k not in{'source_geometry','omega','components','barriers','old_edge_band','edge_band_geometry'}}
    out.update(source_geometry=mapping(face['source_geometry'])if face.get('source_geometry')is not None else None,
        omega=mapping(face['omega']),components=[{**r,'geometry':mapping(r['geometry'])}for r in face['components']],
        barriers=[{**r,'geometry':mapping(r['geometry'])}for r in face.get('barriers',[])],
        old_edge_band=mapping(face['old_edge_band'])if'old_edge_band'in face else None,
        edge_band_geometry=mapping(face['edge_band_geometry'])if'edge_band_geometry'in face else None)
    return out
