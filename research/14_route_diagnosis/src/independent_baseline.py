"""Independent saved-route measurement. No author imports and no solver calls."""
from pathlib import Path
import argparse,csv,io,json,math,hashlib,zipfile,gc
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
PROJECT=Transformer.from_crs(4326,32651,always_xy=True)
def digest(data):return hashlib.sha256(data).hexdigest()
def main(archive=ARCHIVE):
    outputs=[];fingerprints={};points={};errors=[]
    with zipfile.ZipFile(archive)as z:
        manifest=json.loads(z.read('MANIFEST_SHA256.json'));hashes={r['path']:r['sha256']for r in manifest['files']}
        rows=[r for r in csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig')))if r['role']=='BASELINE_POSITIVE']
        scenes={r['scene_id']for r in rows}
        for scene in scenes:
            data=z.read('data/scenes/'+scene+'/source.osm.json');assert digest(data)==hashes['data/scenes/'+scene+'/source.osm.json']
            ids={int(r[k].split('/')[1])for r in rows if r['scene_id']==scene for k in ['start_id','door_or_target_id']}
            raw=json.loads(data)
            for n in raw['elements']:
                if n['type']=='node'and n['id']in ids:points[(scene,'node/'+str(n['id']))]={'xy':PROJECT.transform(n['lon'],n['lat']),'tags':n.get('tags',{})}
            del raw,data;gc.collect()
        for r in rows:
            raw=z.read(r['response_path']);e=[]
            if digest(raw)!=r['response_sha256']or digest(raw)!=hashes[r['response_path']]:e.append('HISTORICAL_RESPONSE_HASH')
            d=json.loads(raw);route=d['route'];segments=route['segments'];xy=[];length=cost=0.;layers={};hyp=0.
            for s in segments:
                line=s['xy'];measured=sum(math.dist(a,b)for a,b in zip(line,line[1:]));mult=2 if r['method']=='F1'and s['layer']in('inferred','assumed','unknown')else 1
                if abs(measured-s['length_m'])>1e-8:e.append('SEGMENT_LENGTH')
                if abs(measured*mult-s['cost_m'])>1e-8:e.append('SEGMENT_COST')
                length+=measured;cost+=measured*mult;layers[s['layer']]=layers.get(s['layer'],0.)+measured
                if s['layer']in('inferred','assumed','unknown'):hyp+=measured
                for p in line:
                    if not xy or p!=xy[-1]:xy.append(p)
            if abs(length-route['length_m'])>1e-8:e.append('ROUTE_LENGTH')
            if abs(cost-route['cost_weighted_m'])>1e-8:e.append('ROUTE_COST')
            start=points[(r['scene_id'],r['start_id'])];end=points[(r['scene_id'],r['door_or_target_id'])]
            if math.dist(start['xy'],xy[0])>1e-8 or math.dist(end['xy'],xy[-1])>1e-8:e.append('ORIGINAL_ENDPOINT_MOVED')
            if end['tags'].get('entrance')=='exit'and r['purpose']!='APPROACH_OUTSIDE':e.append('EXIT_ROLE')
            key=(r['request_id'],r['method']);fingerprint=digest(json.dumps(xy,separators=(',',':')).encode())
            fingerprints.setdefault(key,{})[r['mode']]=fingerprint
            outputs.append({'request_id':r['request_id'],'mode':r['mode'],'response_path':r['response_path'],'response_sha256':digest(raw),'xy_sha256':fingerprint,
                'measured_length_m':length,'measured_cost_m':cost,'layer_lengths_m':layers,'hypothesis_length_m':hyp,'start_error_m':math.dist(start['xy'],xy[0]),'end_error_m':math.dist(end['xy'],xy[-1]),'errors':e})
            errors.extend((r['request_id'],r['mode'],x)for x in e);del d,raw;gc.collect()
    equal={str(k):len(set(v.values()))==1 and len(v)==4 for k,v in fingerprints.items()}
    report={'reviewer':'/root/r2_independent','script_sha256':digest(Path(__file__).read_bytes()),'scope':'Independent original endpoint projection, route/segment distance, F0/F1 cost, SHA and complete ordered XY; not a new routing experiment or field validation',
        'APP_solver_calls':0,'new_solver_calls':0,'rows':outputs,'all_eight_requests_four_mode_XY_identical':all(equal.values()),'group_checks':equal,'errors':errors,'status':'PASS'if len(outputs)==32 and all(equal.values())and not errors else'REQUIRES_INSPECTION'}
    target=ROOT/'audits/independent_baseline32.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'rows':len(outputs),'errors':errors,'same_XY':all(equal.values())}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,default=ARCHIVE);args=parser.parse_args();main(args.baseline)
