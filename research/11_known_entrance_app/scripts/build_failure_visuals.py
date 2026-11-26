"""Real masked-observed geometry for the seven fixed diagnostic map cards."""
from pathlib import Path
import argparse,json,sys
from shapely.geometry import Point,LineString,shape,mapping
ROOT=Path(__file__).resolve().parents[1]

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def feature(g,**p):return {'type':'Feature','geometry':mapping(g),'properties':p}

def main(baseline):
    rows=read(ROOT/'AUDIT/failure_diagnostics.json');fixtures=read(ROOT/'AUDIT/failure_source_minimal_fixtures.json');cases=[]
    for row in rows:
        ident=row['input_id'];qid=row['query_id'];obs=read(baseline/'data/observed'/f'{ident}.json')
        q=row['query'];center=Point(obs['domain']['anchor_xy']);window=center.buffer(50,quad_segs=32);features=[]
        nodes={n['id']:n for n in obs['nodes']};stair_ids={s['source_id']for e in row['endpoints']if not e['visible_eligible']for s in e['native_adjacent']}
        for layer,objects in obs['context'].items():
            for o in objects:
                g=shape(o['geometry']).intersection(window)
                if not g.is_empty:features.append(feature(g,id=o['id'],kind=o['kind'],tags=o.get('tags',{}),layer=layer,evidence='FROZEN_MASKED_OBSERVED_CONTEXT'))
        seen=set()
        for e in obs['edges']:
            sid=e.get('source_id',e['id']);u,v=e['u'],e['v'];key=tuple(sorted((u,v)))+(sid,)
            if key in seen:continue
            seen.add(key);g=LineString([nodes[u]['xy'],nodes[v]['xy']]).intersection(window)
            if not g.is_empty:features.append(feature(g,id=e['id'],source_id=sid,kind=e['kind'],tags=e.get('tags',{}),layer='stairs'if sid in stair_ids else'native',evidence='OBSERVED_SOURCE_SEGMENT_NOT_NEW_CONNECTION'))
        features.append(feature(center.buffer(30,quad_segs=32),id='fixed-domain',kind='FIXED_30M_PREDICTION_AND_SCORE_DOMAIN',layer='domain',evidence='EXPERIMENT_DOMAIN_NOT_WALKABILITY_CLAIM'))
        for role in ('source','target'):
            end=q[role];features.append(feature(Point(end['xy']),id=end['id'],kind=role.upper(),role='FIXED_NATIVE_NETWORK_QUERY_NOT_A_DOOR',layer=role,tags=nodes.get(end['id'],{}).get('tags',{})))
        for n,front in enumerate(row['frontier']):
            features.append(feature(LineString(front['xy']),id=f'frontier/{n}',kind='REJECTED_PLANAR_CANDIDATE_NOT_ROUTE',layer='frontier',evidence='LAYER_COMPATIBILITY_NOT_ESTABLISHED',distance_m=front['distance_m'],conflicts=front['conflicts']))
        source_check=next(f for f in fixtures if f['input_id']==ident and f['query_id']==qid)
        run=ROOT/'runs/benchmark/R2_unified'/ident/'result.json'
        current=read(run)['methods']['F0']['routes'][qid]if run.exists()else None
        cases.append({'id':ident+'/'+qid,'input_id':ident,'query_id':qid,'title':f'{ident} / {qid}',
            'subtitle':'固定网络端点查询；不属于登记门成功率','crs':'EPSG:32651','view_bounds':list(window.bounds),
            'features':{'type':'FeatureCollection','features':features},'source':q['source'],'target':q['target'],
            'stairs_source_ids':sorted(stair_ids),'old_status':row['old_actual_reroute']['status'],'new_status':current['status']if current else'PENDING',
            'root_cause':'端点只邻接已登记楼梯。楼梯本身保留在原生图，但当前冻结规则没有把其端点认证为同层自由空间接点；不自动增加平面连接。',
            'meaning':'图上短虚线只是最近前沿候选，不是已采用路线。没有二维障碍冲突，不能证明与楼梯端点同层或现实可通行。',
            'failed_endpoint_ids':source_check['failed_endpoint_ids'],'components':[{k:e[k]for k in ('id','native','local','combined_before','strong_before','point_states','visible_eligible')}for e in row['endpoints']],
            'source_clip':source_check['source_clip'],'source_sha256':source_check['source_sha256'],
            'provenance':'AUDIT/failure_diagnostics.json; AUDIT/failure_source_minimal_fixtures.json; runs/benchmark/R2_unified',
            'display_extent_m':50,'prediction_extent_m':30,'hidden_reference_displayed':False})
    payload={'role':'CURRENT_SEVEN_FAILURE_DIAGNOSTICS_WITH_REAL_FROZEN_OBSERVED_GEOMETRY','namespace':'BENCHMARK_REGRESSION_DIAGNOSTIC_DISPLAY',
             'crs':'EPSG:32651','attribution':'© OpenStreetMap contributors; frozen source clips, no new requests','cases':cases,
             'limitations':['No physical door inference','Stairs-only means compatible interface is unconfirmed under frozen rule, not proven physically inaccessible','Display 50m is separate from fixed 30m prediction/score domain','No hidden-reference geometry used in these cards']}
    (ROOT/'visuals/diagnostics.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('DIAGNOSTIC_MAP_CARDS',len(cases))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',required=True,type=Path);args=p.parse_args();main(args.baseline.resolve())
