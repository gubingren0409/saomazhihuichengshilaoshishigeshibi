"""Read-only independent measurements of real APP response files.

No planner, compiler, routing module, stored-route oracle or author PASS flag is
used as reference. Raw OSM geometry is reconstructed by this role's own parser.
This script does not invoke the APP solver or change its request budget.
"""
from pathlib import Path
from collections import defaultdict
import argparse,json,math,sys
from shapely.geometry import Point,LineString,shape

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from independent_face_check import RawSource,read,save,file_sha,expected_omega,line_metrics

EPS=1e-6

def review(paths,output):
    catalog={s['scene_id']:s for s in read(ROOT/'data/scene_manifest.json')['scenes']}
    reference_path=next((p for p in[ROOT/'input_contract/references/BASELINE_REQUESTS.json',ROOT/'references/BASELINE_REQUESTS.json']if p.exists()),None)
    refusals=read(reference_path)['negative']if reference_path else[]
    sources={};faces={};rows=[];groups=defaultdict(list);skipped=[]
    for path in paths:
        path=Path(path);d=read(path)
        if not isinstance(d,dict)or not d.get('run_id'):skipped.append(str(path));continue
        request=d.get('normalized_request',d.get('input',{}));scene=request.get('scene_id')
        row={'file':str(path.relative_to(ROOT))if path.is_relative_to(ROOT)else str(path),'sha256':file_sha(path),
            'run_id':d.get('run_id'),'request_id':d.get('request_id'),'status':d.get('status'),'errors':[]}
        expected=next((r for r in refusals if path.name.startswith(r['case_id']+'-')),None)
        if expected:
            keys=['scene_id','door_id','start_id','purpose','method']
            if any(d.get('input',{}).get(k)!=expected['request'].get(k)for k in keys):row['errors'].append('FIXED_NEGATIVE_INPUT_CHANGED')
            if d.get('status')!=expected['expected_status']:row['errors'].append('FIXED_NEGATIVE_STATUS')
            if d.get('failure',{}).get('code')!=expected['failure']['code']:row['errors'].append('FIXED_NEGATIVE_REASON')
            if d.get('solver',{}).get('invoked'):row['errors'].append('INVALID_REQUEST_REACHED_SOLVER')
            row['expected_refusal']={'case_id':expected['case_id'],'status':expected['expected_status'],'failure_code':expected['failure']['code'],'bound_reference_sha256':file_sha(reference_path)}
            if scene not in catalog:
                row['check_scope']='FIXED_UNKNOWN_SCENE_REFUSAL';rows.append(row);continue
        if scene not in catalog:row['errors'].append('NO_BOUND_SCENE');rows.append(row);continue
        if scene not in sources:
            sourcepath=ROOT/catalog[scene]['source_path'];sources[scene]=RawSource(sourcepath)
            if file_sha(sourcepath)!=catalog[scene]['source_sha256']:raise ValueError('RAW_SOURCE_CHANGED:'+scene)
        src=sources[scene]
        route=d.get('route')
        if route is None:
            row['check_scope']='REFUSAL_OR_NO_ROUTE_FILE_ONLY';rows.append(row);continue
        if not d.get('solver',{}).get('invoked'):row['errors'].append('ROUTE_WITHOUT_CURRENT_SOLVER_INVOCATION')
        if d.get('route_answer_cache')!={'enabled':False,'hit':False}:row['errors'].append('ROUTE_ANSWER_CACHE_NOT_DISABLED')
        bound_source=d.get('versions',{}).get('source',{}).get('source_sha256')
        if bound_source!=catalog[scene]['source_sha256']:row['errors'].append('RESPONSE_RAW_SOURCE_SHA_BINDING')
        row['graph_identity']=d.get('graph',{})
        row['reported_interface_statistics']=[{'source_id':f['source_id'],'components':[{'component':c['component'],'portal_count':c['portal_count'],'local_interface_statistics':c.get('local_interface_statistics',{}),'constraint_rejections':c.get('constraint_rejections'),'numeric_tolerance_admissions':c.get('numeric_tolerance_admissions')}for c in f['components']]}for f in d.get('face_network',{}).get('faces',[])]
        method=request.get('method');multiplier=2 if method=='F1'else 1
        metrics=line_metrics(route['segments'],multiplier);row['measurements']=metrics
        if metrics['gaps']:row['errors'].append('DISCONTINUOUS_ROUTE')
        if metrics['saved_value_errors']:row['errors'].append('SAVED_SEGMENT_LENGTH_OR_COST')
        for a,b,name in[(metrics['length_m'],route.get('length_m'),'TOTAL_LENGTH'),(metrics['cost_m'],route.get('cost_weighted_m'),'TOTAL_COST')]:
            if b is None or abs(a-b)>EPS:row['errors'].append(name)
        door=request.get('door_id');start=request.get('start_id');row['source_endpoint_checks']={}
        for key,ident,actual in [('start',start,metrics['first']),('door',door,metrics['last'])]:
            node_id=int(ident.split('/',1)[1])if str(ident).startswith('node/')else None
            if node_id not in src.nodes:
                row['errors'].append('ENDPOINT_NATIVE_ID_NOT_PRESENT:'+str(ident));continue
            native=src.coord(node_id)
            if actual is None and route.get('zero_length')and start==door:actual=native
            error=math.dist(native,actual)if actual else None
            row['source_endpoint_checks'][key]={'id':ident,'raw_source_xy':native,'route_endpoint_error_m':error}
            if error is None or error>EPS:row['errors'].append('ORIGINAL_'+key.upper()+'_COORDINATE_DRIFT')
        native_bad=[];face_bad=[];outside_band=0.;full_segments=0
        for k,s in enumerate(route['segments']):
            line=LineString(s['xy']);sid=s.get('source_id')
            if s.get('layer')=='native'and str(sid).startswith('way/'):
                original_record=src.objects.get(sid);ids=original_record.get('nodes',[])if original_record else[]
                original=LineString([src.coord(n)for n in ids])if len(ids)>=2 and all(n in src.nodes for n in ids)else None
                if original is None:native_bad.append({'segment':k,'source_id':sid,'reason':'SOURCE_WAY_UNRESOLVED'})
                else:
                    mismatch=line.difference(original).length
                    if mismatch>EPS:native_bad.append({'segment':k,'source_id':sid,'outside_original_line_m':mismatch})
            if s.get('geometry_kind')!='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE':continue
            full_segments+=1;faceid=s.get('source_area_id',sid);key=(scene,faceid)
            if key not in faces:
                P=src.geometry(faceid)
                if P is None:raise ValueError('SOURCE_FACE_UNRESOLVED:'+str(key))
                omega,mask_evidence=expected_omega(src,P)
                # Independent old 3m boundary band, no author geometry loader.
                from shapely.ops import unary_union
                exteriors=[p.exterior for p in getattr(P,'geoms',[P])]
                oldband=P.intersection(unary_union(exteriors).buffer(3,quad_segs=16))
                faces[key]=(P,omega,oldband)
            P,omega,oldband=faces[key]
            outside=line.difference(omega).length
            if outside>EPS:face_bad.append({'segment':k,'source_area_id':faceid,'outside_independent_omega_m':outside})
            outside_band+=line.difference(oldband).length
            if s.get('layer')!='derived':row['errors'].append('FULL_FACE_NOT_DERIVED')
        row.update(native_source_geometry_errors=native_bad,full_face_geometry_errors=face_bad,
            full_face_segment_count=full_segments,full_face_length_outside_old_band_m=outside_band)
        if native_bad:row['errors'].append('NATIVE_SEGMENT_NOT_ORIGINAL_POLYLINE')
        if face_bad:row['errors'].append('FULL_FACE_SEGMENT_OUTSIDE_INDEPENDENT_OMEGA')
        if abs(outside_band-route.get('full_face_outside_old_band_m',outside_band))>EPS:row['errors'].append('OUTSIDE_OLD_BAND_MEASUREMENT')
        certificate_errors=[];maximum_shift=0.;certs=d.get('face_network',{}).get('intersection_certificates',[])
        for k,c in enumerate(certs):
            key=(scene,c['source_area_id'])
            if key not in faces:
                P=src.geometry(c['source_area_id']);omega,_=expected_omega(src,P)
                from shapely.ops import unary_union
                oldband=P.intersection(unary_union([p.exterior for p in getattr(P,'geoms',[P])]).buffer(3,quad_segs=16))
                faces[key]=(P,omega,oldband)
            P,omega,_=faces[key];shift=math.dist(c['raw_intersection_xy'],c['xy']);maximum_shift=max(maximum_shift,shift)
            errors=[]
            if shift>1e-8 or abs(c['parent_position_after_m']-c['parent_position_before_m'])>1e-8:errors.append('EXCEEDS_NUMERIC_NORMALIZATION_LIMIT')
            if abs(shift-c['coordinate_shift_m'])>1e-12:errors.append('COORDINATE_SHIFT_MEASUREMENT')
            if not omega.covers(Point(c['xy'])):errors.append('NORMALIZED_CONTACT_OUTSIDE_INDEPENDENT_OMEGA')
            witness=c['positive_parent_interval_witness_m']
            if witness[1]<=witness[0]:errors.append('NO_POSITIVE_PARENT_INTERVAL')
            if errors:certificate_errors.append({'index':k,'errors':errors,'certificate':c})
        row['certificate_validation']={'count':len(certs),'maximum_measured_shift_m':maximum_shift,'errors':certificate_errors,
            'limits':'Point containment and measured certificate values; does not reconstruct every complete source-graph parent arc here'}
        if certificate_errors:row['errors'].append('DERIVED_INTERFACE_CERTIFICATE')
        key=(scene,door,start,request.get('purpose'));groups[key].append((request.get('area_routing'),method,d,row))
        rows.append(row)
    pairchecks=[]
    for key,items in groups.items():
        by={(mode,method):d for mode,method,d,_ in items}
        for mode in ['EDGE_BAND','FULL_FACE']:
            a,b=by.get((mode,'F0')),by.get((mode,'F1'))
            if not(a and b):continue
            equal=a.get('graph',{}).get('unweighted_sha256')==b.get('graph',{}).get('unweighted_sha256')
            pairchecks.append({'identity':key,'area_routing':mode,'kind':'F0_F1_SAME_GRAPH','passed':equal})
        for method,field in [('F0','length_m'),('F1','cost_weighted_m')]:
            a,b=by.get(('EDGE_BAND',method)),by.get(('FULL_FACE',method))
            if not(a and b):continue
            old,new=a['route'][field],b['route'][field]
            pairchecks.append({'identity':key,'method':method,'kind':'FULL_GRAPH_SUPERSET_COST_MONOTONICITY',
                'metric':field,'old':old,'full_face':new,'passed':new<=old+EPS})
    result={'reviewer':'/root/face_review','role':'INDEPENDENT_RESPONSE_GEOMETRY_AND_COST_RECALCULATION',
        'author_validation_flags_used_as_reference':False,'author_functions_called':False,'APP_solver_calls':0,
        'rows':rows,'skipped_non_response_files':skipped,'paired_checks':pairchecks,'source_sha256':{s:file_sha(src.path)for s,src in sources.items()},
        'limitations':['Native way agreement checks geometry provenance, not observed public access',
            'Fullface Ω independently rebuilt from acquired raw constraints; no field survey',
            'This is output remeasurement, not an independent whole-network topology shortest-path solve',
            'Refusal/no-route files are source/status inspected here, not independently proved impossible']}
    result['status']='PASS'if all(not r['errors']for r in rows)and all(c['passed']for c in pairchecks)else'REQUIRES_INSPECTION'
    save(output,result);print(json.dumps({'status':result['status'],'rows':len(rows),'paired_checks':len(pairchecks),'errors':sum(bool(r['errors'])for r in rows)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('paths',nargs='+',type=Path);p.add_argument('--output',type=Path,default=ROOT/'audits/independent_app_results.json');args=p.parse_args()
    paths=[]
    for item in args.paths:paths.extend(sorted(item.glob('*.json'))if item.is_dir()else[item])
    review(paths,args.output)
