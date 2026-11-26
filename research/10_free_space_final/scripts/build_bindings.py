import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    manifest=json.loads((ROOT/'data/task_manifest.json').read_text(encoding='utf8'));rows=[]
    for r in manifest['instances']:
        roles={}
        for role,rel in [('OBSERVED',r['observed']),('QUERY_POST_FREEZE',r['query']),('COMMON_GUARD',r.get('guards','data/common_guards_v2/'+r['id']+'.json'))]:roles[role]={'path':rel,'sha256':sha(ROOT/rel)}
        if r.get('reference'):roles['REFERENCE_EVALUATION_ONLY']={'path':r['reference'],'sha256':sha(ROOT/r['reference'])}
        if r.get('natural'):
            roles['FULL_GRAPH_ROUTE_ONLY_POST_FREEZE']={'path':r['route_graph'],'sha256':sha(ROOT/r['route_graph'])}
            roles['FROZEN_OBSERVED_ONLY_CLASSIFIER_CACHE']={'path':'data/classifier_cache/NORTH_160.json','sha256':sha(ROOT/'data/classifier_cache/NORTH_160.json')}
        elif r.get('classifier_cache'):
            roles['PREVIOUS_SAME_MASKED_OBSERVED_CLASSIFIER_CACHE']={'path':r['classifier_cache'],'sha256':sha(ROOT/r['classifier_cache'])}
        rows.append({'id':r['id'],'panel':r['panel'],'executed':(ROOT/'data/predictions'/r['id']/'F1.json').is_file(),'staged_not_run_reason':'OPTIONAL_DIAGNOSTIC_REGION_BUILD_CAP' if r['panel']=='SUPPLEMENTARY' else None,'roles':roles,'crs':'EPSG:32651','prediction_m':30,'score_m':30,'grid_m':1,'observation_m':r['context_radius_m'],'display_input_role':'SEPARATE_DISPLAY_ONLY_NOT_PREDICTOR','domain_sha256':r.get('prediction_domain_sha256'),'mask_sha256':r.get('mask_sha256'),'grid_sha256':r.get('grid_sha256')})
    data={'instances':rows,'frozen_dependency':'input_contract/frozen/R4_CONTEXT_OPEN_REVIEW.zip','frozen_sha256':'40f8e18d76d04819d66a3bd526ecb2b74fc83201b3b58452881a6576b6651cbf','new_map_or_provider_api_requests':0,'new_entrances':0,'cache_scope':'Unmasked natural north and previously executed same-masked-observed W7 correctness repair; no routes/query/reference in classifier cache'}
    (ROOT/'data/observed_bindings.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');print(len(rows),'input bindings')
if __name__=='__main__':main()
