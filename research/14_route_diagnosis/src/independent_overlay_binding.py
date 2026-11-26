"""Bind every exported overlay/binding option to immutable R1 raw segment rows."""
from pathlib import Path
import json,csv,zipfile,io,gzip,math,collections,hashlib,gc,argparse
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
def option(parts):
    owners=set();interfaces=set()
    for s in parts:
        owners.update(v for v in([s.get('source_area_id',s.get('source_id'))]+s.get('source_area_ids',[]))if v)
        if s.get('interface_id'):interfaces.add(s['interface_id'])
    return(sum(s['length_m']for s in parts),sum(s['length_m']for s in parts if s['layer']in('inferred','assumed','unknown')),tuple(sorted(owners)),tuple(sorted(interfaces)),parts[0].get('geometry_kind','UNKNOWN')if parts else'ZERO_LENGTH_INTERFACE')
def key(o):return(o[0],o[1],tuple(o[2]),tuple(o[3]),o[4])
def main():
    rows=[];errors=[]
    with zipfile.ZipFile(ARCHIVE)as z:
        samples=list(csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))));comps=list(csv.DictReader(io.StringIO(z.read('results/component_statistics.csv').decode('utf-8-sig'))))
        for case,app in [('south','APP-01'),('north_near','APP-03'),('north_far','APP-05'),('library','APP-07')]:
            response=next(r for r in samples if r['request_id']==app and r['mode']=='CONDITIONAL_SEAMS');body=json.loads(z.read(response['response_path']));rec=next(r for r in comps if r['scene_id']==response['scene_id']and r['door_id']==body['door']['id']and r['mode']=='CONDITIONAL_SEAMS');xy={};edges={}
            with gzip.open(ROOT/f'data/{case}_query_graph.jsonl.gz','rt',encoding='utf-8')as f:
                for line in f:
                    r=json.loads(line)
                    if r['kind']=='node':xy[r['id']]=r['xy']
                    else:edges[r['u'],r['v']]={key(o)for o in r['options']}
            bad=[];overlay_nodes=overlay_arcs=overlay_options=0;deps=[]
            for desc in json.loads(rec['overlays']):
                data=z.read(desc['path']);digest=hashlib.sha256(data).hexdigest();assert digest==desc['sha256'];deps.append({'path':desc['path'],'sha256':digest})
                with gzip.GzipFile(fileobj=io.BytesIO(data))as f:
                    for line in f:
                        r=json.loads(line)
                        if r['kind']=='node':
                            overlay_nodes+=1
                            if r['id']not in xy or math.dist(r['xy'],xy[r['id']])>1e-8:bad.append(['OVERLAY_NODE',r['id']])
                        else:
                            overlay_arcs+=1
                            for ss in r.get('routing_alternatives',[r['segments']]):
                                overlay_options+=1;o=option(ss)
                                if o not in edges.get((r['u'],r['v']),set()):bad.append(['OVERLAY_OPTION_NOT_IN_GRAPH',r['u'],r['v']])
                                if any(abs(s['length_m']-sum(math.dist(a,b)for a,b in zip(s['xy'],s['xy'][1:])))>1e-7 for s in ss):bad.append(['ORIGINAL_OVERLAY_SEGMENT_LENGTH'])
                                if any(math.dist(a['xy'][-1],b['xy'][0])>1e-8 for a,b in zip(ss,ss[1:])):bad.append(['ORIGINAL_OVERLAY_CONTINUITY'])
                                if ss and(math.dist(ss[0]['xy'][0],xy[r['u']])>1e-8 or math.dist(ss[-1]['xy'][-1],xy[r['v']])>1e-8):bad.append(['ORIGINAL_OVERLAY_ENDPOINT'])
            for bind in body['bindings']:
                u,v,ss=bind['id'],bind['attach'],bind['segments'];o=option(ss)
                if o not in edges.get((u,v),set())or o not in edges.get((v,u),set()):bad.append(['QUERY_BINDING_OPTION'])
                if math.dist(xy[u],ss[0]['xy'][0])>1e-8 or math.dist(xy[v],ss[-1]['xy'][-1])>1e-8:bad.append(['QUERY_BINDING_COORD'])
                if bind['displacement_m']!=0 or bind['identity']!='ORIGINAL_REGISTERED_DOOR':bad.append(['QUERY_BINDING_IDENTITY'])
            rows.append({'case':case,'source_response_sha256':response['response_sha256'],'overlays':deps,'overlay_node_rows_checked':overlay_nodes,'overlay_arc_rows_checked':overlay_arcs,'overlay_options_checked':overlay_options,'bindings_checked':len(body['bindings']),'errors':bad});errors.extend((case,e)for e in bad);del xy,edges;gc.collect()
    out={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'status':'PASS_FOR_ALL_FROZEN_OVERLAY_AND_BINDING_OPTIONS'if not errors else'REQUIRES_INSPECTION','new_solver_calls':0,'new_SSSP_calls':0,'rows':rows,'errors':errors,'scope':'Every original B3 overlay node/arc and parallel option independently linked to export, with original segment length/continuity and exact bound door coords. Source/base and local options independently checked in separate all-arc provenance/weight reports. No continuous endpoint re-optimization.'}
    (ROOT/'audits/independent_overlay_binding.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':out['status'],'options':sum(r['overlay_options_checked']for r in rows),'errors':errors[:20]}))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,default=ARCHIVE);ARCHIVE=ap.parse_args().baseline;main()
