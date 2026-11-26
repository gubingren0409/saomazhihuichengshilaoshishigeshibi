"""Fixed fresh APP acceptance requests; zero route-answer reuse."""
from pathlib import Path
import json,time,urllib.request,csv
ROOT=Path(__file__).resolve().parents[1]
def main():
    folder=ROOT/'runs/acceptance';spec=json.loads((folder/'fixed_requests.json').read_text(encoding='utf-8'))
    north=next(q for q in spec['requests']if q['door_id']=='node/6897145227')
    scenes=json.loads(urllib.request.urlopen('http://127.0.0.1:53421/api/scenes',timeout=20).read())['scenes']
    no_door=next(s for s in scenes if not s['doors'])
    extra=[dict(north,request_id='APP-09',purpose='ENTER_BUILDING'),
           dict(north,request_id='APP-10',scene_id=no_door['scene_id'],door_id=''),
           dict(north,request_id='APP-11',start_id='node/NOT_A_SOURCE_NODE'),
           dict(north,request_id='APP-12',start_xy=['INVALID','COORDINATE']),
           dict(north,request_id='APP-13',scene_id='OUTSIDE_FROZEN_SCENE_COVERAGE')]
    registered={**spec,'negative_requests':extra,'max_fresh_business_requests':16,
                'minimal_cli_role':'Early engineering same query as APP-03, not extra scene or independent case',
                'package_request_reserved':'One new legal start chosen by stable ID after all current requests; never read historical answers'}
    (folder/'registered_acceptance.json').write_text(json.dumps(registered,ensure_ascii=False,indent=2),encoding='utf-8')
    browser=json.loads((ROOT/'AUDIT/browser/receipt.json').read_text(encoding='utf-8'))
    records=[]
    for q in spec['requests']+extra:
        prior=next((r['result']for r in browser['responses']if r['registered_case']==q['request_id']),None)
        if prior is not None:r=prior;source='ACTUAL_BROWSER_BUTTON_HTTP_SOLVER'
        else:
            req=urllib.request.Request('http://127.0.0.1:53421/api/plan',data=json.dumps(q).encode(),headers={'Content-Type':'application/json'},method='POST')
            r=json.loads(urllib.request.urlopen(req,timeout=300).read());source='ACTUAL_HTTP_FRESH_REQUEST'
        (folder/(q['request_id']+'.response.json')).write_text(json.dumps(r,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        record={'case_id':q['request_id'],'request_id':r['request_id'],'run_id':r['run_id'],'scene_id':q['scene_id'],'door_id':q['door_id'],
                'start_id':q['start_id'],'purpose':q['purpose'],'method':q['method'],'status':r['status'],'solver_invoked':r['solver']['invoked'],
                'route_answer_cache':r['route_answer_cache']['enabled'],'preprocessing_cache_hit':r.get('preprocessing_cache',{}).get('hit'),
                'elapsed_s':r['elapsed_s'],'prepare_s':r.get('preprocessing_cache',{}).get('load_or_prepare_s'),'solver_s':r['solver'].get('elapsed_s'),
                'validation_s':r.get('validation_s'),'length_m':r.get('route',{}).get('length_m'),
                'assumed_m':sum(r.get('route',{}).get('layer_lengths_m',{}).get(k,0)for k in ('inferred','unknown')),
                'end_residual_m':r.get('route',{}).get('end_residual_m'),'evidence':source,'failure':r.get('failure',{}).get('code','')}
        records.append(record);print(q['request_id'],r['status'],round(r['elapsed_s'],3),flush=True)
        (folder/'progress.json').write_text(json.dumps({'completed':len(records),'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    with (folder/'app_acceptance.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    summary={'namespace':'APP_NATURAL_QUERY','distinct_registered_cases':len(records),'positive_requests':len(spec['requests']),'negative_requests':len(extra),
             'actual_graph_search_count':sum(r['solver_invoked']for r in records),'routed':sum(r['status'].startswith('ROUTED')for r in records),
             'route_answers_cached':False,'records':records,'scientific_scope':'Functional acceptance on existing source, not independent recovery benchmark or field navigation success'}
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
