"""Whole-segment independent selected-alternative source and constraint checks."""
from pathlib import Path
import sys,json,zipfile,csv,io,hashlib,math,collections,gc,argparse
from shapely.geometry import shape,LineString,Point,Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src/r1_independent'))
from independent_connectivity_source import coverage
from independent_connectivity_omega import raw_masks,denied,nonground
from independent_connectivity_responses import native_proof,FROZEN_VISIBILITY_SHA
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
def main():
    rows=[];errors=[];inherited=[]
    with zipfile.ZipFile(ARCHIVE)as z:
        for module in('independent_connectivity_source','independent_connectivity_omega','independent_connectivity_responses'):
            original=z.read('scripts/'+module+'.py');actual=(ROOT/'src/r1_independent'/(module+'.py')).read_bytes();assert original==actual;inherited.append({'prior_independent_module':module,'R1_SHA256':hashlib.sha256(actual).hexdigest(),'unchanged':True})
        catalog={s['scene_id']:s for s in json.loads(z.read('data/scene_manifest.json'))['scenes']};samples=list(csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))));registered=hashlib.sha256(z.read('src/face_visibility.py')).hexdigest()==FROZEN_VISIBILITY_SHA
        scene='sh-huangpu-01';raw=json.loads(z.read(catalog[scene]['source_path']));source,areal,common=raw_masks(raw);ai=STRtree([r['geometry']for r in areal]);ci=STRtree([r['geometry']for r in common]);omegas={}
        contract=json.loads(z.read('data/connectivity/'+scene+'_full_common.json'));valid=shape(contract['valid_geometry']);physical=shape(contract['physical_geometry']);interior=physical.buffer(-1e-7)if physical.area>1e-6 else physical;background=shape(contract['background_geometry']);roads=[(r,shape(r['geometry']))for r in contract['road_centerlines']];ri=STRtree([g for r,g in roads]);access=[Point(r['xy'])for r in contract['native_road_access_points']];permissions=[(r,shape(r['geometry']).buffer(-1e-7),shape(r['source_geometry']).boundary)for r in contract['access_area_constraints']];exceptions=contract['visible_native_boundary_exceptions'];domain=shape(contract['domain'])
        def omega(ident):
            if ident not in omegas:
                kind,num=ident.split('/');p,_,reason=source.area(source.objects[kind,int(num)]);assert p is not None,(ident,reason);m=[areal[int(i)]['geometry']for i in ai.query(p,predicate='intersects')];c=[common[int(i)]['geometry']for i in ci.query(p,predicate='intersects')];parts=[p]if p.geom_type=='Polygon'else p.geoms;holes=[Polygon(r).buffer(.25,quad_segs=16)for part in parts for r in part.interiors];omegas[ident]=p.difference(unary_union(m+holes)).difference(unary_union(c)).intersection(coverage(catalog[scene]['full_source_clip_bounds']))
            return omegas[ident]
        for case,app0 in [('south',1),('north_near',3),('north_far',5)]:
            for method,app in [('F0',app0),('F1',app0+1)]:
                actual=json.loads((ROOT/f'results/materialized_{case}_{method}.json').read_text());alt=actual['alternative'];body=json.loads(z.read(next(r for r in samples if r['request_id']==f'APP-{app:02d}'and r['mode']=='CONDITIONAL_SEAMS')['response_path']));native=[];whole=[];bad=[];layers=collections.Counter()
                for i,s in enumerate(alt['segments']):
                    line=LineString(s['xy']);tags=s.get('tags',{});isnative=s['layer']=='native';kind=s.get('geometry_kind');why=[];layers[s['layer']]+=line.length
                    if denied(tags):why.append('EXPLICIT_PERMISSION')
                    if not isnative and nonground(tags):why.append('NEW_NON_GROUND')
                    if not isnative and line.difference(valid).length>1e-6:why.append('OUTSIDE_VALID_COVERAGE')
                    structure=tags.get('bridge')not in(None,'no','false','0')or tags.get('tunnel')not in(None,'no','false','0')
                    if line.intersection(interior).length>1e-6 and not(isnative and structure):why.append('HARD_OBSTACLE_INTERIOR')
                    if not isnative and line.intersection(background).length>1e-6:why.append('BACKGROUND_NEW_EDGE_POLICY')
                    for r,p,boundary in permissions:
                        if line.intersection(p).length>1e-6:why.append('PERMISSION_INTERIOR:'+r['source_id'])
                        hit=line.intersection(boundary).intersection(domain)
                        if hit.length>1e-6:
                            allowed=unary_union([shape(e['geometry'])for e in exceptions if isnative and e['area_source_id']==r['source_id']and e['source_id']==s.get('source_id')])
                            if hit.difference(allowed).length>1e-6:why.append('PERMISSION_BOUNDARY:'+r['source_id'])
                    if not isnative:
                        for j in ri.query(line,predicate='intersects'):
                            r,road=roads[int(j)];hit=line.intersection(road);points=[hit]if hit.geom_type=='Point'else list(hit.geoms)if hit.geom_type=='MultiPoint'else[];ends=[Point(line.coords[0]),Point(line.coords[-1])]
                            if not(points and all(any(q.distance(e)<=1e-6 for e in ends)and any(q.distance(a)<=1e-6 for a in access)for q in points)):why.append('NO_FREE_ROAD_CROSSING:'+r['source_id'])
                    if isnative:
                        proof=native_proof(s,source,body,registered);native.append({'index':i,**proof})
                        if not proof['passed']:why.extend(proof['errors'])
                    if kind in('DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE','SOURCE_SUPPORTED_INTERFACE'):
                        owners=s.get('source_area_ids',[s.get('source_area_id',s.get('source_id'))]);covered=any(omega(o).covers(line)for o in owners)
                        if s['layer']!='derived'or not covered:why.append('RAW_REBUILT_OMEGA_DOES_NOT_COVER_WHOLE_EDGE')
                    whole.append({'index':i,'kind':kind,'layer':s['layer'],'source_id':s.get('source_id'),'length_m':line.length,'errors':why})
                    if why:bad.append({'index':i,'errors':why})
                rows.append({'case':case,'method':method,'materialized_sha256':hashlib.sha256((ROOT/f'results/materialized_{case}_{method}.json').read_bytes()).hexdigest(),'segment_count':len(whole),'native_parent_proofs':native,'whole_segment_checks':whole,'layer_lengths_m':dict(layers),'errors':bad});errors.extend([[case,method,b]for b in bad])
    out={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_solver_calls':0,'new_SSSP_calls':0,'status':'PASS_FOR_SELECTED_ALTERNATIVE_WHOLE_GEOMETRY'if not errors else'REQUIRES_INSPECTION','prior_independent_helpers':inherited,'rows':rows,'errors':errors,'scope':'Six actual finite alternatives: own whole-line constraint evaluation using SHA-bound frozen common contract; raw OSM source-ring/negative-mask independent Omega rebuild for all selected full-face/interface edges and unchanged prior independent native ordered-parent proof. Does not re-create all source constraint objects or assert real-world completeness; all full-network admitted edges inherited from fixed R1.'}
    (ROOT/'audits/independent_alternative_geometry.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':out['status'],'routes':len(rows),'segments':sum(r['segment_count']for r in rows),'errors':errors[:10]},ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,default=ARCHIVE);ARCHIVE=ap.parse_args().baseline;main()
