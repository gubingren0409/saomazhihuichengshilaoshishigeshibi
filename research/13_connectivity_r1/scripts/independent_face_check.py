"""Independent raw-ring and numerical reviewer; no author implementation imports.

This reconstructs ring membership by source node IDs instead of calling Source
or the face compiler. It does not infer field permission or map completeness.
"""
from __future__ import annotations
import argparse, gc, hashlib, json, math
from collections import defaultdict
from pathlib import Path
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Polygon, LineString, Point, mapping, shape
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
EPS=1e-6
WALK={'pedestrian','footway','path'}
PUBLIC={'yes','public','permissive','designated','official'}
DENIED={'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def file_sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def polygons(g):
    if g.geom_type=='Polygon':yield g
    else:
        for p in getattr(g,'geoms',()):yield from polygons(p)
def counts(g):
    ps=list(polygons(g));return {'parts':len(ps),'holes':sum(len(p.interiors)for p in ps),'vertices':sum(len(p.exterior.coords)-1+sum(len(r.coords)-1 for r in p.interiors)for p in ps)}
def area_permission(t):
    return not any(k in t and t[k]not in PUBLIC for k in ('access','foot','pedestrian')) and not any(k in t for k in ('access:conditional','foot:conditional','pedestrian:conditional'))
def ground(t):
    return all(t.get(k)in(None,'','0',0)for k in ('layer','level'))and all(t.get(k)in(None,'no','false','0')for k in ('bridge','tunnel','indoor','ford'))
def face_tagged(t):return t.get('area:highway')in WALK or t.get('area')=='yes'and t.get('highway')in WALK
def denied(t):
    return t.get('foot',t.get('access'))in DENIED or t.get('locked')=='yes'or any(k.endswith(':conditional')and k.split(':')[0]in{'foot','access','oneway'}for k in t)

class RawSource:
    def __init__(self,path):
        self.path=Path(path);self.raw=read(path)
        self.objects={f"{o['type']}/{o['id']}":o for o in self.raw['elements']}
        self.nodes={o['id']:o for o in self.raw['elements']if o['type']=='node'}
        self.ways={o['id']:o for o in self.raw['elements']if o['type']=='way'}
        self.tx=Transformer.from_crs('EPSG:4326','EPSG:32651',always_xy=True);self.xy={};self.cache={};self.audit={}
    def coord(self,n):
        if n not in self.xy:
            o=self.nodes[n];self.xy[n]=self.tx.transform(o['lon'],o['lat'])
        return self.xy[n]
    def loops(self,ways):
        pending=[(w['id'],list(w.get('nodes',[])))for w in sorted(ways,key=lambda w:w['id'])]
        result=[];errors=[]
        while pending:
            wid,chain=pending.pop(0);used=[wid]
            if len(chain)<2:errors.append({'way':wid,'error':'TOO_FEW_SOURCE_NODES'});continue
            while chain[0]!=chain[-1]:
                matches=[(k,refs[0]==chain[-1])for k,(_,refs)in enumerate(pending)if refs and chain[-1]in(refs[0],refs[-1])]
                if len(matches)!=1:
                    errors.append({'ways':used,'error':'OPEN_OR_AMBIGUOUS_NODE_ID_CHAIN','end':chain[-1],'candidate_count':len(matches)});break
                k,forward=matches[0];n,refs=pending.pop(k);used.append(n);chain.extend(refs[1:]if forward else refs[::-1][1:])
            else:
                missing=sorted({n for n in chain if n not in self.nodes})
                if missing:errors.append({'ways':used,'error':'MISSING_SOURCE_NODES','nodes':missing})
                elif len(set(chain[:-1]))<3:errors.append({'ways':used,'error':'DEGENERATE_SOURCE_RING'})
                else:result.append((chain,used))
        return result,errors
    def geometry(self,sid):
        if sid in self.cache:return self.cache[sid]
        o=self.objects.get(sid)
        if not o:return None
        info={'source_id':sid,'errors':[],'outer_members':0,'inner_members':0,'non_geometric_members':[]}
        if o['type']=='way':
            ns=o.get('nodes',[])
            if len(ns)<4 or ns[0]!=ns[-1]:info['errors'].append('WAY_NOT_CLOSED');groups=([],[])
            else:groups=([o],[]);info['outer_members']=1
        elif o['type']=='relation'and o.get('tags',{}).get('type')=='multipolygon':
            gs={'outer':[],'inner':[]}
            for m in o.get('members',[]):
                role=m.get('role')or'outer'
                if role not in gs:
                    info['non_geometric_members'].append(m);continue
                if m['type']!='way'or m['ref']not in self.ways:info['errors'].append({'error':'MISSING_OR_UNSUPPORTED_GEOMETRY_MEMBER','member':m});continue
                gs[role].append(self.ways[m['ref']])
            groups=(gs['outer'],gs['inner']);info['outer_members']=len(gs['outer']);info['inner_members']=len(gs['inner'])
        else:info['errors'].append('NOT_A_RAW_POLYGON_OBJECT');groups=([],[])
        ring_sets=[];valid=True
        for label,ways in zip(('outer','inner'),groups):
            loops,errors=self.loops(ways);info['errors'].extend(errors);info[label+'_stitched_rings']=len(loops)
            gs=[]
            for ids,members in loops:
                p=Polygon([self.coord(n)for n in ids])
                if not p.is_valid:valid=False;info['errors'].append({'error':'INVALID_SOURCE_RING','role':label,'members':members})
                gs.append(make_valid(p))
            ring_sets.append(unary_union(gs))
        outside=ring_sets[1].difference(ring_sets[0]).area if ring_sets else 0
        if outside>EPS:info['errors'].append({'error':'INNER_OUTSIDE_OUTER','area_m2':outside})
        g=ring_sets[0].difference(ring_sets[1])
        if not g.is_valid:valid=False;g=make_valid(g)
        info.update(source_rings_valid=valid,area_m2=g.area,counts=counts(g),source_complete=not info['errors'])
        self.audit[sid]=info;self.cache[sid]=g if not g.is_empty else None;return self.cache[sid]
    def coverage(self):
        w,s,e,n=self.raw['bounds_wsen'];corners=[(w,s),(e,s),(e,n),(w,n)]
        return Polygon([self.tx.transform(a[0]+(b[0]-a[0])*i/32,a[1]+(b[1]-a[1])*i/32)for a,b in zip(corners,corners[1:]+corners[:1])for i in range(32)])

def inventory(scenes):
    manifest=read(ROOT/'data/scene_manifest.json');all_rows=[];features=[]
    for scene in manifest['scenes']:
        if scenes and scene['scene_id']not in scenes:continue
        path=ROOT/scene['source_path'];assert file_sha(path)==scene['source_sha256']
        src=RawSource(path);coverage=src.coverage()
        for sid,o in src.objects.items():
            t=o.get('tags',{})
            if not face_tagged(t):continue
            g=src.geometry(sid);info=src.audit.get(sid,{'source_complete':False})
            row={'scene_id':scene['scene_id'],'source_id':sid,'tags':t,'source_sha256':scene['source_sha256'],
                 'foot_area_semantics':True,'permission_eligible':area_permission(t),'ground_policy_eligible':ground(t),**info}
            if g is not None:
                row.update(outside_coverage_m2=g.difference(coverage).area,within_coverage_m2=g.intersection(coverage).area)
                features.append({'type':'Feature','geometry':mapping(g),'properties':row})
            all_rows.append(row)
        del src;gc.collect()
    report={'reviewer':'/root/face_review','role':'INDEPENDENT_RAW_NODE_ID_RING_ASSEMBLY_NOT_AUTHOR_SOURCE_ADAPTER','author_functions_called':False,'rows':all_rows,
            'scope':'Raw explicit pedestrian source polygons, complete member/node IDs, ring closure, parts/holes, source coverage and static tag eligibility; not field passage'}
    save(ROOT/'audits/independent_source_faces.json',report)
    save(ROOT/'audits/independent_source_faces.geojson',{'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'features':features})
    print(json.dumps({'faces':len(all_rows),'main':[r for r in all_rows if r['scene_id']=='sh-huangpu-01'and r['source_id']in{'relation/2153738','relation/2385771'}]},ensure_ascii=False))

STRUCTURES={'wall','fence','hedge','retaining_wall','chain','city_wall','jersey_barrier'}
GATES={'gate','lift_gate','swing_gate','turnstile','kissing_gate'}
def area_role(t):
    return t.get('area')!='no'and(t.get('area')=='yes'or t.get('amenity')in{'parking','parking_space'}or'landuse'in t or'leisure'in t or t.get('building')not in(None,'no')or t.get('natural')in{'water','wetland'}or t.get('type')=='multipolygon')
def old_restricted(t):
    return t.get('access')in DENIED or t.get('foot')in DENIED or any(k.endswith(':conditional')and k.split(':')[0]in{'access','foot','oneway'}for k in t)
def non_ground(t):
    return t.get('highway')in{'steps','elevator'}or any(t.get(k)not in(None,'','0','no','false')for k in('level','layer','bridge','tunnel','indoor','repeat_on'))
def source_areal_hazard(t):
    return (t.get('building')not in(None,'no')or t.get('building:part')not in(None,'no')or
        t.get('natural')in{'water','wetland'}or bool(t.get('water'))or t.get('waterway')=='riverbank'or
        t.get('landuse')in{'reservoir','basin','grass','flowerbed','flower_bed'}or
        t.get('leisure')=='flowerbed'or t.get('landcover')in{'grass','flowerbed'}or
        t.get('barrier')in{'flower_bed','planter'}or t.get('garden:type')=='flower_bed'or
        old_restricted(t)and(t.get('area')=='yes'or t.get('type')=='multipolygon'))

def _known_ids(src,o):
    if o['type']=='way':return o.get('nodes',[])
    return[n for m in o.get('members',[])if m['type']=='way'and m['ref']in src.ways for n in src.ways[m['ref']].get('nodes',[])]

def expected_omega(src,P):
    """Direct raw-object .25m area + .15/.30m common-line policy reconstruction."""
    masks=[];audit=[];bounds=P.buffer(.3).bounds
    for part in polygons(P):
        for ring in part.interiors:masks.append(Polygon(ring).buffer(.25,quad_segs=16))
    # Select relevant raw objects by metric coordinate bounds before constructing
    # polygons. This is a spatial filter, not an area-ID permission exception.
    for sid,o in src.objects.items():
        if o['type']not in{'way','relation'}:continue
        t=o.get('tags',{});refs=_known_ids(src,o);coords=[src.coord(n)for n in refs if n in src.nodes]
        if not coords:continue
        xs,ys=zip(*coords)
        if max(xs)<bounds[0]or min(xs)>bounds[2]or max(ys)<bounds[1]or min(ys)>bounds[3]:continue
        if source_areal_hazard(t):
            g=src.geometry(sid)
            if g is None:raise ValueError('Independent source hazard unresolved: '+sid)
            if g.distance(P)<=.25:
                masks.append(g.buffer(.25,quad_segs=16));audit.append({'source_id':sid,'role':'SOURCE_AREAL_CLEARANCE','buffer_m':.25})
        closed=o['type']=='relation'and t.get('type')=='multipolygon'or len(refs)>=4 and refs[0]==refs[-1]
        if denied(t)and closed and area_role(t):
            g=src.geometry(sid)
            if g is None:raise ValueError('Independent source access area unresolved: '+sid)
            masks.append(g);audit.append({'source_id':sid,'role':'COMMON_PERMISSION_AREA','buffer_m':0})
        elif o['type']=='way'and len(coords)>1 and denied(t)and not source_areal_hazard(t):
            masks.append(LineString(coords).buffer(.15));audit.append({'source_id':sid,'role':'COMMON_RESTRICTED_LINEAR','buffer_m':.15})
        if o['type']=='way'and t.get('barrier')in STRUCTURES|GATES:
            openings=[]
            for n in refs:
                nt=src.nodes.get(n,{}).get('tags',{})
                if nt.get('barrier')in GATES|{'bollard','cycle_barrier','entrance'}and not denied(nt)and not non_ground(nt):openings.append(Point(src.coord(n)).buffer(.30))
            masks.append(LineString(coords).buffer(.15).difference(unary_union(openings)))
            audit.append({'source_id':sid,'role':'COMMON_PHYSICAL_BARRIER','buffer_m':.15,'gate_opening_m':.30,'member_gate_count':len(openings)})
    for n,o in src.nodes.items():
        t=o.get('tags',{});kind=t.get('barrier')
        if kind not in STRUCTURES|GATES:continue
        p=Point(src.coord(n))
        if p.distance(P)>.3:continue
        public=kind in GATES and not non_ground(t)and not denied(t)and(t.get('foot')in PUBLIC or t.get('access')in PUBLIC)
        if not public:masks.append(p.buffer(.15));audit.append({'source_id':f'node/{n}','role':'COMMON_PHYSICAL_POINT','buffer_m':.15})
    omega=P.difference(unary_union(masks)).intersection(src.coverage())
    return omega,audit

def check_faces(scene_id,path):
    path=Path(path);before=file_sha(path);saved=read(path)
    row=next(s for s in read(ROOT/'data/scene_manifest.json')['scenes']if s['scene_id']==scene_id);src=RawSource(ROOT/row['source_path'])
    results=[]
    for f in saved['faces']:
        if f.get('status')!='ADMITTED':continue
        sid=f['source_id'];P=src.geometry(sid);actualP=shape(f['source_geometry']);actual=shape(f['omega'])
        expected,mask_audit=expected_omega(src,P)
        source_difference=P.symmetric_difference(actualP).area;omega_difference=expected.symmetric_difference(actual).area
        outside=actual.difference(P).area
        results.append({'source_id':sid,'source_polygon_symmetric_difference_m2':source_difference,'omega_symmetric_difference_m2':omega_difference,
            'outside_source_face_m2':outside,'raw_source_counts':counts(P),'expected_omega_counts':counts(expected),'saved_omega_counts':counts(actual),
            'expected_area_m2':expected.area,'saved_area_m2':actual.area,'independent_raw_mask_audit':mask_audit,
            'status':'PASS'if max(source_difference,omega_difference,outside)<=1e-5 else'DIFFERENCE_REQUIRES_INSPECTION'})
    report={'reviewer':'/root/face_review','role':'INDEPENDENT_RAW_CONSTRAINT_OMEGA_RECONSTRUCTION','author_functions_called':False,'source_sha256':file_sha(src.path),
        'face_file':str(path),'face_file_sha256':before,'source_file_stable':before==file_sha(path),'rows':results,
        'precision':'Symmetric-difference area tolerance1e-5m² for independently ordered floating overlays, not an obstacle buffer change',
        'status':'PASS'if before==file_sha(path)and all(r['status']=='PASS'for r in results)else'REQUIRES_INSPECTION'}
    save(ROOT/'audits'/f'independent_omega_{scene_id}.json',report)
    print(json.dumps({'status':report['status'],'faces':[(r['source_id'],r['omega_symmetric_difference_m2'])for r in results]},ensure_ascii=False))

def line_metrics(segments,multiplier):
    last=None;first=None;length=0.;cost=0.;layers=defaultdict(float);gaps=[];bad=[]
    for k,s in enumerate(segments):
        xy=s.get('xy')or s.get('geometry',{}).get('coordinates');d=sum(math.dist(a,b)for a,b in zip(xy,xy[1:]));layer=s.get('layer','UNKNOWN')
        if first is None:first=xy[0]
        if last is not None and math.dist(last,xy[0])>EPS:gaps.append({'index':k,'gap_m':math.dist(last,xy[0])})
        last=xy[-1];factor=multiplier if layer in{'inferred','assumed','unknown'}else 1
        length+=d;cost+=d*factor;layers[layer]+=d
        if abs(d-s.get('length_m',d))>EPS or abs(d*factor-s.get('cost_m',d*factor))>EPS:bad.append(k)
    return {'length_m':length,'cost_m':cost,'layers':dict(layers),'gaps':gaps,'saved_value_errors':bad,'first':first,'last':last}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--inventory',action='store_true');ap.add_argument('--scenes',nargs='*');ap.add_argument('--check-faces',type=Path);ap.add_argument('--scene');a=ap.parse_args()
    if a.inventory:inventory(a.scenes)
    if a.check_faces:check_faces(a.scene,a.check_faces)
