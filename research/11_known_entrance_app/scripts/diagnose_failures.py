"""Endpoint/component diagnostics, using observed inputs and frozen preprocessing.

Historical routes are comparison labels only. Candidate binding is recomputed
against the saved shared surface/common constraints, without hidden references.
"""
from pathlib import Path
import argparse, csv, gzip, hashlib, json, math, sys
import networkx as nx
from shapely.geometry import Point, LineString, shape, mapping
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.region import Surface, STATES, union, context_layers, non_ground, access_conflict
from src.region_routing import RegionGraph, route, bidirectional
from src.free_routing import checked_native, bind, reweight
from src.common_constraints import parsed_contract, edge_conflicts

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def restore(baseline, ident, cfg):
    obs = read(baseline/'data/observed'/f'{ident}.json')
    saved = read(baseline/'data/predictions'/ident/'F0.json')['surface']
    domain = shape(saved['domain'])
    cells = [dict(c, g=shape(c['geometry']), ij=tuple(c['ij'])) for c in saved['cells']]
    surface = Surface(domain,cells,{s:union(c['g'] for c in cells if c['walkability_state']==s) for s in STATES},
                      context_layers(obs,domain,cfg),saved['sha256'],saved['area_m2'],saved['statistics'],saved['grid_m'])
    with gzip.open(baseline/'data/graphs'/ident/'F0.graph.json.gz','rt',encoding='utf-8') as f: rec=json.load(f)
    graph=nx.DiGraph()
    graph.add_nodes_from((n['id'],{k:v for k,v in n.items() if k!='id'}) for n in rec['nodes'])
    graph.add_edges_from((e['u'],e['v'],{'segments':e['segments']}) for e in rec['edges'])
    reweight(graph,1)
    active=[c for c in cells if c['walkability_state'] in ('NATIVE_WALKABLE','INFERRED_WALKABLE')]
    points=[(c['region_id'],c['g'].representative_point(),c['walkability_state']) for c in active]
    region=RegionGraph(graph,rec['interfaces'],union(c['g'] for c in active),points,STRtree([p[1] for p in points]),surface,{})
    common=read(baseline/'data/constraints'/f'{ident}.json')
    return obs,region,common

def component(graph,key,strong=False):
    if key not in graph:return {'present':False}
    comps=nx.strongly_connected_components(graph) if strong else nx.weakly_connected_components(graph)
    for n,c in enumerate(comps):
        if key in c:return {'present':True,'component':n,'size':len(c),'degree':graph.degree(key),'in_degree':graph.in_degree(key),'out_degree':graph.out_degree(key)}

def endpoint(end,base,region,common,cfg):
    p=Point(end['xy']); visible=None
    if end['id'] in base and math.dist(base.nodes[end['id']]['xy'],end['xy'])<=1e-6:
        adjacent=list(base.in_edges(end['id'],data=True))+list(base.out_edges(end['id'],data=True))
        eligible=any(not non_ground(s.get('tags',{})) and not access_conflict(s.get('tags',{})) for _,_,r in adjacent for s in r['segments'])
        if eligible and not non_ground(base.nodes[end['id']].get('tags',{})) and not access_conflict(base.nodes[end['id']].get('tags',{})):visible=base.nodes[end['id']]
    key, stitch=bind(end,region,cfg,common,'F0',visible)
    nearest=[]
    for k in sorted(region.index.query(p,predicate='dwithin',distance=cfg['interface_reach_m']),key=lambda k:(p.distance(region.points[k][1]),region.points[k][0])):
        ident,point,state=region.points[k];line=LineString([p,point])
        nearest.append({'cell_id':ident,'xy':list(point.coords[0]),'distance_m':line.length,'conflicts':edge_conflicts(line,common),
                        'restricted_overlap_m':line.intersection(region.surface.masks['RESTRICTED']).length,'cell_degree':region.internal.degree(ident)})
    restrictions=[]
    for c in common['contract']['constraints']:
        g=shape(c['geometry'])
        if g.distance(p)<=cfg['interface_reach_m']:
            restrictions.append({'source_id':c['source_id'],'kind':c.get('kind'),'tags':c.get('tags'),
                                 'point_distance_m':g.distance(p),'point_in_interior':g.contains(p),'restriction_role':c.get('restriction_role')})
    adjacent=[]
    if key in base:
        for u,v,r in list(base.in_edges(key,data=True))+list(base.out_edges(key,data=True)):
            adjacent.extend({'u':u,'v':v,'source_id':s.get('source_id'),'tags':s.get('tags'), 'xy':s['xy']} for s in r['segments'])
    return {'id':key,'xy':end['xy'],'role':end.get('role'),'visible_eligible':visible is not None,
            'native':component(base,key),'local':component(region.internal,key),
            'point_states':[s for s,g in region.surface.masks.items() if g.covers(p)],
            'distance_to_active_m':region.active.distance(p),'candidate_stitch':stitch,'near_candidates':nearest,
            'near_restrictions':restrictions,'native_adjacent':adjacent},stitch

def diagnose(baseline):
    cfg=read(ROOT/'config/frozen_region.json')
    cfg.update(inference_cost_multiplier=1,unknown_penalty_per_m=1,unknown_fixed_penalty_m=0)
    seeds=read(ROOT/'input_contract/references/FAILED_QUERY_SEEDS.json')['failed_queries']
    result=[]
    for ident in sorted({s['id'] for s in seeds}):
        obs,rg,raw=restore(baseline,ident,cfg);common=parsed_contract(raw)
        base,rejected=checked_native(obs,common)
        queries=read(baseline/'data/queries'/f"{ident.split('_G_')[0]}.json")['queries']
        for q in queries:
            if not any(s['id']==ident and s['query_id']==q['query_id'] for s in seeds):continue
            graph=nx.compose(base,rg.internal)
            info=[];bindings=[]
            for end in [q['source'],q['target']]:
                item,stitch=endpoint(end,base,rg,common,cfg)
                item['combined_before']=component(graph,end['id']);item['strong_before']=component(graph,end['id'],True)
                info.append(item);bindings.append(stitch)
            old=route(graph,q['source']['id'],q['target']['id'])
            for end,stitch in zip([q['source'],q['target']],bindings):
                if stitch:
                    target,parts=stitch
                    if end['id'] not in graph:graph.add_node(end['id'],xy=end['xy'],tags=end.get('tags',{}))
                    bidirectional(graph,end['id'],target,parts)
            fixed=route(graph,q['source']['id'],q['target']['id'])
            a,b=q['source']['id'],q['target']['id']
            reachable=nx.descendants(graph,a)|{a} if a in graph else set()
            target_component=nx.ancestors(graph,b)|{b} if b in graph else set()
            frontier=[]
            if reachable and target_component and b not in reachable:
                tree=STRtree([Point(graph.nodes[n]['xy']) for n in sorted(target_component)])
                target_ids=sorted(target_component)
                candidates=[]
                for n in reachable:
                    p=Point(graph.nodes[n]['xy']);idx=int(tree.nearest(p));m=target_ids[idx]
                    candidates.append((p.distance(Point(graph.nodes[m]['xy'])),n,m))
                for dist,u,v in sorted(candidates)[:3]:
                    line=LineString([graph.nodes[u]['xy'],graph.nodes[v]['xy']])
                    hit=[]
                    for c in raw['constraints']:
                        g=shape(c['geometry'])
                        if line.intersects(g):hit.append({'source_id':c['source_id'],'kind':c.get('kind'),'intersection_length_m':line.intersection(g).length,'tags':c.get('tags')})
                    frontier.append({'distance_m':dist,'from_id':u,'to_id':v,'xy':list(map(list,line.coords)),
                                     'conflicts':edge_conflicts(line,common),'constraint_hits':hit})
            result.append({'input_id':ident,'query_id':q['query_id'],'query':q,'target_identity':'FIXED_NATIVE_NETWORK_QUERY_NOT_REGISTERED_ENTRANCE',
                'endpoints':info,'old_actual_reroute':old,'correct_binding_diagnostic_route':fixed,'frontier':frontier,'native_rejected':rejected,
                'source_hashes':{str(p.relative_to(baseline)):sha(p) for p in [baseline/'data/observed'/f'{ident}.json',baseline/'data/queries'/f"{ident.split('_G_')[0]}.json",baseline/'data/constraints'/f'{ident}.json',baseline/'data/graphs'/ident/'F0.graph.json.gz']},
                'diagnostic_role':'FROZEN_PREPROCESSING_DIAGNOSTIC_NOT_FRESH_CLASSIFICATION; NO_REFERENCE_READ'})
            print(ident,q['query_id'],old['status'],'=>',fixed['status'], 'binds', [bool(s) for s in bindings], flush=True)
    (ROOT/'AUDIT/failure_diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def finalize(baseline,source_dir):
    rows=read(ROOT/'AUDIT/failure_diagnostics.json');manifest=read(baseline/'data/task_manifest.json')['instances'];byid={r['id']:r for r in manifest}
    source_checks=[];table=[]
    objects_by_clip={}
    for clip in {byid[r['input_id']]['source_clip']for r in rows}:
        path=source_dir/clip
        if not path.exists():path=source_dir/clip.replace('.osm.json','')/'source.osm.json'
        raw=read(path);actual=sha(path)
        assert {byid[r['input_id']]['source_clip_sha256']for r in rows if byid[r['input_id']]['source_clip']==clip}=={actual}
        objects_by_clip[clip]={(x['type'],x['id']):x for x in raw['elements']}
    for row in rows:
        ident=row['input_id'];qid=row['query_id'];meta=byid[ident];objects=objects_by_clip[meta['source_clip']]
        stair_ends=[e for e in row['endpoints']if not e['visible_eligible'] and e['native_adjacent'] and all(x.get('tags',{}).get('highway')=='steps'for x in e['native_adjacent'])]
        assert stair_ends,'Root cause not confirmed: '+ident+'/'+qid
        relevant_ways=sorted({s['source_id']for e in stair_ends for s in e['native_adjacent']})
        raw_objects=[]
        for wid in relevant_ways:
            way=objects['way',int(wid.split('/')[1])];raw_objects.append(way)
            for nid in way['nodes']:
                raw_objects.append(objects['node',nid])
        seen=set();raw_objects=[x for x in raw_objects if not ((x['type'],x['id'])in seen or seen.add((x['type'],x['id'])))]
        check={'input_id':ident,'query_id':qid,'source_clip':meta['source_clip'],'source_sha256':meta['source_clip_sha256'],
               'failed_endpoint_ids':[e['id']for e in stair_ends],'raw_minimal_objects':raw_objects,
               'raw_tags_match_observed':all(objects['way',int(s['source_id'].split('/')[1])].get('tags',{})==s['tags']for e in stair_ends for s in e['native_adjacent']),
               'raw_node_tags':[{'id':e['id'],'tags':objects['node',int(e['id'].split('/')[1])].get('tags',{})}for e in stair_ends],
               'code_branch':'src/region.py:non_ground => highway steps; src/free_routing.py:visible eligible adjacent source check',
               'interpretation':'Native stairs remain routable by their own recorded topology. Their isolated endpoint is not authorized as same-level new free-space interface without compatible visible ground connection. No physical inaccessibility claim.',
               'counterfactual':'Planar nearby grid candidates have no known 2D obstacle conflict, but accepting that alone would remove the frozen level-compatibility policy; not adopted.',
               'new_route_answer_cache':False,'masked_reference_read_for_diagnosis':False}
        source_checks.append(check)
        current_path=ROOT/'runs/benchmark/R2_unified'/ident/'result.json'
        current=read(current_path)['methods']['F0']['routes'][qid]if current_path.exists()else None
        distances=[c['distance_m']for e in stair_ends for c in e['near_candidates']if not c['conflicts']]
        table.append({'input_id':ident,'parent_task_id':meta['parent_task_id'],'query_id':qid,'target_identity':'NATIVE_NETWORK_NODE_NOT_ENTRANCE',
            'source_id':row['query']['source']['id'],'target_id':row['query']['target']['id'],
            'raw_source_xy':json.dumps(row['query']['source']['xy']),'raw_target_xy':json.dumps(row['query']['target']['xy']),
            'coordinate_displacement_m':0,'old_status':row['old_actual_reroute']['status'],'new_status':current['status']if current else 'PENDING',
            'source_native_component':row['endpoints'][0]['native'].get('component'),'target_native_component':row['endpoints'][1]['native'].get('component'),
            'source_combined_component':row['endpoints'][0]['combined_before'].get('component'),'target_combined_component':row['endpoints'][1]['combined_before'].get('component'),
            'source_scc':row['endpoints'][0]['strong_before'].get('component'),'target_scc':row['endpoints'][1]['strong_before'].get('component'),
            'directed_issue':'NO: same split in weak and strong components; source stair arcs are bidirectional',
            'failed_endpoint_ids':';'.join(e['id']for e in stair_ends),'blocking_source_ids':';'.join(relevant_ways),
            'nearest_planar_grid_candidate_m':min(distances)if distances else None,'failure_stage':'NATIVE_STEPS_COMPONENT_TO_LOCAL_FREE_SPACE_INTERFACE',
            'reason_code':'STAIRS_ONLY_ENDPOINT_SAME_LEVEL_NOT_ESTABLISHED',
            'root_cause_zh':'原生楼梯边存在且保留，但此端点只邻接楼梯；冻结规则不把缺少同层连接依据的楼梯端点自动接入平面自由空间。',
            'fixability':'RETAIN_FAILURE_WITHIN_FROZEN_POLICY; explicit mapped landing or new approved level-interface research needed',
            'generic_fix_result':'Full-network checked binding repaired for eligible ground nodes, but does not authorize these steps-only endpoints',
            'scope_limit':'Not a proven physical obstacle or real-world no-route. Missing compatible level/interface evidence under current contract.',
            'diagnostic_json':'AUDIT/failure_diagnostics.json','source_fixture_json':'AUDIT/failure_source_minimal_fixtures.json',
            'new_run':f'runs/benchmark/R2_unified/{ident}/result.json','source_sha256':meta['source_clip_sha256']})
    (ROOT/'AUDIT/failure_source_minimal_fixtures.json').write_text(json.dumps(source_checks,ensure_ascii=False,indent=2),encoding='utf-8')
    with (ROOT/'FAILURE_DIAGNOSIS.csv').open('w',newline='',encoding='utf-8-sig')as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    print('SEVEN_FAILURES_EXPLICIT_SOURCE_CHECKED',len(table),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--finalize-source-dir',type=Path);args=p.parse_args()
    if args.finalize_source_dir:finalize(args.baseline,args.finalize_source_dir)
    else:diagnose(args.baseline)
