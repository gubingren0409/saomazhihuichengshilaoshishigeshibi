"""Independent source identity/eligibility check of post-freeze local terminals.

No main graph builder, classifier, bind or validation function is called.
Mapped-area grid points are computational source points, never OSM entrances.
"""
from collections import Counter,defaultdict
from hashlib import sha256
import json,math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EPS=1e-6
DENIED={'no','private','customers','destination','delivery','permit','restricted','agricultural','forestry'}


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sign(p):return sha256(p.read_bytes()).hexdigest()


def denied(tags):
    return tags.get('foot',tags.get('access'))in DENIED or tags.get('locked')=='yes' or any(k in tags for k in ('foot:conditional','access:conditional','oneway:foot:conditional'))


def incompatible(tags):
    return tags.get('highway')in {'steps','elevator'} or any(tags.get(k)not in (None,'','0','no','false')for k in ('level','layer','bridge','tunnel','indoor','repeat_on'))


def main():
    op=ROOT/'data/e5/observed/NORTH_160.json';qp=ROOT/'data/e5/queries/NORTH.json'
    obs,qs=read(op),read(qp)['queries'];nodes={n['id']:n for n in obs['nodes']}
    queries={q['query_id']:q for q in qs}
    wanted={r[k]['id']for r in qs for k in ('source','target')}
    adjacent=defaultdict(list)
    for e in obs['edges']:
        if e['u']not in wanted and e['v']not in wanted:continue
        tags=e.get('tags',{});a,b=nodes[e['u']],nodes[e['v']]
        state={'edge_id':e['id'],'source_id':e.get('source_id'),'kind':e['kind'],'tags':tags,
            'direction':[e['u'],e['v']],'permission_conflict':any(denied(t)for t in (tags,a.get('tags',{}),b.get('tags',{}))),
            'explicit_incompatible_layer':any(incompatible(t)for t in (tags,a.get('tags',{}),b.get('tags',{}))),
            'level_facts':'UNKNOWN'if not any(k in tags for k in ('level','layer','bridge','tunnel'))else'AS_SOURCE_TAGGED'}
        for key in (e['u'],e['v']):
            if key in wanted:adjacent[key].append(state)
    rows=[];methods=[]
    for p in sorted((ROOT/'data/predictions/NORTH_160').glob('*.json')):
        d=read(p);auth=d['graph'].get('terminal_authorization',[])
        terminals={(t['query_id'],t['id']):t for t in d['graph']['terminals']}
        good=[]
        for a in auth:
            key=a['id'];q=queries[a['query_id']]
            original=next((q[k]for k in ('source','target')if q[k]['id']==key),None)
            reasons=[]
            if original is None or math.dist(original['xy'],a['xy'])>EPS:reasons.append('NOT_EXACT_FROZEN_QUERY_ENDPOINT')
            source=nodes.get(key);is_visible=a['binding_evidence']=='EXACT_VISIBLE_OBSERVED_GRAPH_ID_AND_COORDINATE'
            if is_visible:
                if q['scope']!='LOCAL_REGION_ONLY':reasons.append('NOT_LOCAL_QUERY_REPAIR_SCOPE')
                if source is None or math.dist(source['xy'],a['xy'])>EPS:reasons.append('NOT_EXACT_VISIBLE_SOURCE_NODE')
                if source and (denied(source.get('tags',{}))or incompatible(source.get('tags',{}))):reasons.append('SOURCE_NODE_PERMISSION_OR_LAYER')
                if not any(not e['permission_conflict']and not e['explicit_incompatible_layer']for e in adjacent[key]):reasons.append('NO_COMPATIBLE_ORIGINAL_INCIDENT_EDGE')
            elif original is None or original.get('role')not in {'REGISTERED_EXIT','REGISTERED_DOOR','CONTROL_INTERIOR_POINT'}:
                reasons.append('NOT_ORIGINAL_AUTHORIZED_QUERY_ROLE')
            expected_identity='NATIVE_OSM_NODE'if key.startswith('node/')else'MAPPED_AREA_DERIVED_OR_EXPLICIT_CONTROL_POINT'
            if a['endpoint_identity']!=expected_identity:reasons.append('IDENTITY_CLASS_UPGRADED')
            term=terminals[(a['query_id'],key)]
            length=sum(math.dist(s['xy'][0],s['xy'][-1])for s in term['segments'])
            if length>1.6+EPS:reasons.append('OLD_1P6M_BIND_TOLERANCE_EXCEEDED')
            if term['segments']and math.dist(term['segments'][0]['xy'][0],a['xy'])>EPS:reasons.append('STITCH_ENDPOINT_MOVED')
            row={'method':d['method'],'query_id':a['query_id'],'id':key,'xy':a['xy'],
                'binding_evidence':a['binding_evidence'],'endpoint_identity':expected_identity,
                'source_node_tags':source.get('tags',{})if source else None,'source_endpoint_kind':source.get('endpoint_kind')if source else None,
                'incident_edge_count':len(adjacent[key]),'compatible_incident_edges':sum(not e['permission_conflict']and not e['explicit_incompatible_layer']for e in adjacent[key]),
                'incident_source_ids':sorted({e['source_id']for e in adjacent[key]if e['source_id']}),
                'mapped_area_derived_point_not_native_door':key.startswith('grid/'),
                'actual_stitch_m':length,'reasons':reasons,'status':'PASS'if not reasons else'FAIL'}
            good.append(row);rows.append(row)
        methods.append({'method':d['method'],'prediction_sha256':sign(p),'route_count':len(d['routes']),
            'reached':sum(r['reached']for r in d['routes'].values()),'terminal_count':len(auth),
            'region_sha256':d['surface']['sha256'],'graph_sha256':d['graph']['graph_sha256'],'terminal_graph_sha256':d['graph']['terminal_graph_sha256']})
    doc={'status':'PASS_WITH_FACTUAL_LEVEL_UNCERTAINTY'if rows and all(r['status']=='PASS'for r in rows)else'FAIL',
        'reviewer':'/root/free_constraints source data context independent from main route implementation',
        'scope':'POST_FREEZE_TERMINAL_ID_XY_SOURCE_TAG_INCIDENT_EDGE_AND_IDENTITY_CHECK; NO_CLASSIFIER_OR_BIND_FUNCTION_CALL',
        'observed_sha256':sign(op),'query_sha256':sign(qp),'script_sha256':sign(Path(__file__)),
        'method_count':len(methods),'terminal_rows':len(rows),'methods':methods,'checks':rows,
        'interpretation':'Absent level tags are UNKNOWN compatible assumptions, not measured same-level facts. Grid-derived mapped-face nodes and controls are not physical entrances. The original exit identity is unchanged.'}
    out=ROOT/'audits/north_terminal_source_FINAL.json'
    with out.open('x',encoding='utf-8')as f:json.dump(doc,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':doc['status'],'methods':len(methods),'terminals':len(rows),'failures':sum(r['status']!='PASS'for r in rows),'visible_repair_bindings':sum(r['binding_evidence'].startswith('EXACT')for r in rows)}))


if __name__=='__main__':main()
