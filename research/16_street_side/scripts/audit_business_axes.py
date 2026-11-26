"""Read fixed historical routes and their actual native lineage; no solver."""
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'SMART_CITY_WALKABILITY_FOUNDATION_PG1'
R1 = ROOT.parent / 'PED_AREA_CONNECTIVITY_R1'
MOTOR = {'motorway','motorway_link','trunk','trunk_link','primary','primary_link',
         'secondary','secondary_link','tertiary','tertiary_link','unclassified',
         'residential','living_street','service','road'}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    registry = R1 / 'results/formal_registry.jsonl'
    records = [json.loads(x) for x in registry.read_text(encoding='utf-8-sig').splitlines()]
    wanted = {'APP-%02d' % i for i in range(1,9)}
    fixed = [r for r in records if r.get('request',{}).get('request_id') in wanted
             and r['request'].get('connectivity_mode') == 'CONDITIONAL_SEAMS']
    assert len(fixed) == 8
    admission = {}
    for scene in {'sh-huangpu-01','sh-library'}:
        admission[scene] = {}
        with gzip.open(OLD/'phase1/data'/scene/'native_admission.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                ns = r['source_node_ids']
                admission[scene][(r['source_id'],frozenset(str(n) for n in ns))] = r
    rows, segments, refs = [], [], []
    for record in fixed:
        p = R1/record['path']
        assert sha(p) == record['result_sha256']
        data = json.loads(p.read_text(encoding='utf-8-sig'))
        q = data['input']; route = data['route']; segs = route['segments']
        road_rows = []
        for i,s in enumerate(segs):
            t = s.get('tags',{})
            if t.get('highway') not in MOTOR:
                continue
            nodes = frozenset(str(s.get(k,'')).removeprefix('node/') for k in ('u','v'))
            a = admission[q['scene_id']].get((s.get('source_id'),nodes))
            r = {'request_id':q['request_id'],'scene_id':q['scene_id'],'method':q['method'],
                 'segment_order':i,'source_id':s.get('source_id'),'edge_id':s.get('edge_id'),
                 'highway':t['highway'],'name':t.get('name',''),'foot':t.get('foot','UNKNOWN'),
                 'sidewalk':t.get('sidewalk','UNKNOWN'),'sidewalk_left':t.get('sidewalk:left','UNKNOWN'),
                 'sidewalk_right':t.get('sidewalk:right','UNKNOWN'),
                 'length_m':s['length_m'],'old_route_source_class':s.get('source_class'),
                 'axis_admission_evidence':a.get('evidence') if a else 'NOT_MATCHED',
                 'axis_admission_status':a.get('status') if a else 'NOT_MATCHED',
                 'physical_sidewalk_geometry':False,
                 'interpretation':'ROAD_AXIS_GEOMETRY_IS_NOT_INDEPENDENT_SIDEWALK',
                 'xy_json':json.dumps(s['xy'],separators=(',',':')),'old_result_sha256':sha(p)}
            road_rows.append(r);segments.append(r)
        length = sum(s['length_m'] for s in segs)
        axis_length = sum(s['length_m'] for s in road_rows)
        rows.append({'request_id':q['request_id'],'scene_id':q['scene_id'],'start_id':q['start_id'],
                     'door_id':q['door_id'],'purpose':q['purpose'],'method':q['method'],
                     'status':data['status'],'total_segments':len(segs),'route_length_m':length,
                     'road_axis_segments':len(road_rows),'road_axis_length_m':axis_length,
                     'road_axis_fraction_by_length':axis_length/length if length else None,
                     'axis_evidence':dict(collections.Counter(s['axis_admission_evidence'] for s in road_rows)),
                     'new_solver_calls':0,'old_result_path':str(p),'old_result_sha256':sha(p)})
        refs.append({'path':str(p),'sha256':sha(p)})
    for name,rs in [('business_route_axis_usage.csv',rows),('business_route_axis_segments.csv',segments)]:
        with (ROOT/'results'/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader()
            for r in rs:
                w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else v for k,v in r.items()})
    result={'scope':'FOUR_FIXED_BUSINESS_QUERIES_TIMES_TWO_COST_METHODS; HISTORICAL_RESULT_READ_ONLY',
            'historical_records':len(rows),'business_queries':4,'axis_using_records':sum(r['road_axis_segments']>0 for r in rows),
            'axis_using_business_queries':len({(r['start_id'],r['door_id'],r['purpose']) for r in rows if r['road_axis_segments']}),
            'rows':rows,'source_refs':refs,'new_solver_calls':0,'new_network_requests':0}
    (ROOT/'results/business_route_axis_usage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['# 历史业务路线中的道路轴实际使用','',
          '只读核对四个固定业务任务×F0/F1共8份旧结果，未重跑求路。原生来源的道路轴折线不能改称独立人行道；共享/foot许可语义也不证明车行轴实际适合步行。','']
    for r in rows:
        text.append(f"- {r['request_id']} {r['scene_id']} {r['method']}：道路轴{r['road_axis_segments']}/{r['total_segments']}段，轴线长度{r['road_axis_length_m']:.3f}/{r['route_length_m']:.3f}m；原接纳证据{r['axis_evidence']}。")
    text+=['','这些是原地图轴几何在旧业务结果中的使用，不是危险率、真实步行占比或本轮R2收益。未核验现实道路宽度、车道分隔、公众通行或精确侧向位置。全裁片道路数量不作为路线使用率。']
    (ROOT/'results/business_route_axis_usage.md').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','source_refs')},ensure_ascii=False))

if __name__=='__main__':main()
