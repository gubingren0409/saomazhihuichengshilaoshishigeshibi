"""Fixed, paired real HTTP queries. Historical answers are comparison-only."""
from pathlib import Path
import argparse,csv,json,time,urllib.request,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def put(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
def call(q,url,out):
    request=urllib.request.Request(url+'api/plan',data=json.dumps(q).encode(),headers={'Content-Type':'application/json'},method='POST')
    t=time.perf_counter();r=json.loads(urllib.request.urlopen(request,timeout=600).read());put(out,r)
    print(q['request_id'],r['status'],r.get('route',{}).get('length_m'),round(time.perf_counter()-t,3),flush=True)
    return r
def main(args):
    spec=read(ROOT/'data/baseline_requests.json');folder=ROOT/'runs'/args.suite
    if folder.exists():raise FileExistsError('Choose a new suite; first runs are never replaced')
    folder.mkdir(parents=True);records=[];comparisons=[]
    put(folder/'protocol.json',{'fixed_requests_sha256':hashlib.sha256((ROOT/'data/baseline_requests.json').read_bytes()).hexdigest(),
        'area_modes':['EDGE_BAND','FULL_FACE'],'same_sources_inputs_costs':True,'route_answer_cache':False,'calls_planned':26,
        'source_of_old_answers':'Exact sealed ZIP, only read for comparison after each new solver result'})
    with zipfile.ZipFile(ROOT/'input_contract/baseline/OPEN_REVIEW_R1_FIXED.zip')as z:
        for q in spec['positive']:
            case=q['request_id'];pair=[]
            for mode in ('EDGE_BAND','FULL_FACE'):
                body={**q,'area_routing':mode,'request_id':args.suite+'-'+case+'-'+mode}
                result=call(body,args.url,folder/(case+'-'+mode+'.json'));records.append({'case_id':case,'area_mode':mode,'run_id':result['run_id'],'solver_invoked':result['solver']['invoked'],'status':result['status']});pair.append(result)
            old=read_from_zip(z,f'runs/acceptance/{case}.response.json')
            a,b=pair;ar=a.get('route');br=b.get('route')
            row={'case_id':case,'scene_id':q['scene_id'],'start_id':q['start_id'],'door_id':q['door_id'],'purpose':q['purpose'],'method':q['method'],
                 'edge_status':a['status'],'full_status':b['status'],'edge_length_m':ar['length_m']if ar else None,'full_length_m':br['length_m']if br else None,
                 'edge_cost_m':ar['cost_weighted_m']if ar else None,'full_cost_m':br['cost_weighted_m']if br else None,
                 'saving_length_m':ar['length_m']-br['length_m']if ar and br else None,
                 'saving_cost_m':ar['cost_weighted_m']-br['cost_weighted_m']if ar and br else None,
                 'saving_length_ratio':(ar['length_m']-br['length_m'])/ar['length_m']if ar and br and ar['length_m']else None,
                 'full_outside_old_band_m':br.get('full_face_outside_old_band_m')if br else None,
                 'full_face_derived_m':br.get('source_lengths_m',{}).get('full_face_derived')if br else None,
                 'full_assumed_m':br.get('source_lengths_m',{}).get('assumed')if br else None,
                 'same_local_surface':a.get('versions',{}).get('surface_sha256')==b.get('versions',{}).get('surface_sha256'),
                 'baseline_edge_length_difference_m':ar['length_m']-old['route']['length_m']if ar and old.get('route')else None,
                 'full_endpoint_residual_m':br.get('end_residual_m')if br else None,
                 'full_validation_passed':b.get('validation',{}).get('passed'),
                 'edge_graph_sha256':a.get('versions',{}).get('unweighted_graph_sha256'),'full_graph_sha256':b.get('versions',{}).get('unweighted_graph_sha256'),
                 'edge_run':a['run_id'],'full_run':b['run_id']}
            comparisons.append(row);put(folder/'progress.json',{'completed_calls':len(records),'records':records,'comparisons':comparisons})
        for entry in spec['negative']:
            for mode in ('EDGE_BAND','FULL_FACE'):
                body={**entry['request'],'area_routing':mode,'request_id':args.suite+'-'+entry['case_id']+'-'+mode}
                result=call(body,args.url,folder/(entry['case_id']+'-'+mode+'.json'))
                records.append({'case_id':entry['case_id'],'area_mode':mode,'run_id':result['run_id'],'solver_invoked':result['solver']['invoked'],
                    'status':result['status'],'expected_status':entry['expected_status'],'matches_expected':result['status']==entry['expected_status']})
    with (folder/'paired_results.csv').open('w',encoding='utf-8-sig',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(comparisons)
    result={'role':'CURRENT_REAL_PAIRED_APP_RUN','calls':len(records),'actual_solver_invocations':sum(r['solver_invoked']for r in records),
        'positive_comparisons':comparisons,'negative_checks':[r for r in records if 'expected_status'in r],
        'all_local_domains_unchanged':all(r['same_local_surface']for r in comparisons),
        'cost_monotonic':all(r['saving_cost_m']is None or r['saving_cost_m']>=-1e-6 for r in comparisons),
        'route_answer_cache':False,'records':records}
    put(folder/'summary.json',result)
def read_from_zip(z,name):return json.loads(z.read(name))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:53431/');p.add_argument('--suite',default='main_matrix_R1');main(p.parse_args())
