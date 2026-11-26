"""Author topology replay from retained overlays, without VG rebuild or search.

Rebuild only the frozen source/local base, load hash-bound actual overlays,
require the original full prepared-graph SHA, and count directed components.
The small topology snapshots omit duplicate geometry, not isolated nodes.
"""
from pathlib import Path
import sys,json,gzip,csv,hashlib,gc,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import networkx as nx
from src import planner
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvfile(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in row.items()})
def load_graph(path,expected):
    if sha(path)!=expected:raise ValueError('ACTUAL_OVERLAY_SHA_MISMATCH:'+str(path))
    graph=nx.DiGraph()
    with gzip.open(path,'rt',encoding='utf-8')as stream:
        for line in stream:
            row=json.loads(line);kind=row.pop('kind')
            if kind=='node':graph.add_node(row.pop('id'),**row)
            elif kind=='arc':u=row.pop('u');v=row.pop('v');graph.add_edge(u,v,**row)
            else:raise ValueError('UNKNOWN_SERIALIZED_GRAPH_RECORD')
    return graph
def structure_snapshot(graph):
    digest=hashlib.sha256()
    for n in sorted(graph):digest.update(json.dumps(['node',n],separators=(',',':')).encode()+b'\n')
    for u,v in sorted(graph.edges()):digest.update(json.dumps(['arc',u,v],separators=(',',':')).encode()+b'\n')
    target=ROOT/'results/topology_inputs'/f'{digest.hexdigest()}.jsonl.gz';target.parent.mkdir(exist_ok=True)
    if not target.exists():
        with gzip.open(target,'wt',encoding='utf-8')as f:
            for n in sorted(graph):f.write(json.dumps({'kind':'node','id':n},separators=(',',':'))+'\n')
            for u,v in sorted(graph.edges()):f.write(json.dumps({'kind':'arc','u':u,'v':v},separators=(',',':'))+'\n')
    return {'path':target.relative_to(ROOT).as_posix(),'sha256':sha(target),'structural_sha256':digest.hexdigest(),'nodes':len(graph),'arcs':graph.number_of_edges()}
def labels(graph):
    weak={};strong={};wc=sc=0
    for component in nx.weakly_connected_components(graph):
        label=min(component);wc+=1
        for n in component:weak[n]=label
    for component in nx.strongly_connected_components(graph):
        label=min(component);sc+=1
        for n in component:strong[n]=label
    return weak,strong,wc,sc
def main():
    tick=time.perf_counter();rows=[json.loads(x)for x in (ROOT/'results/formal_registry.jsonl').read_text().splitlines()]
    replay=ROOT/'results/formal_replay_registry.jsonl'
    replacements={r['supersedes_attempt_id']:r for r in [json.loads(x)for x in replay.read_text().splitlines()]}if replay.exists()else{}
    rows=[replacements.get(r['attempt_id'],r)for r in rows]
    groups={};prep_index={}
    for p in (ROOT/'runs/preprocessing').glob('*.json'):
        d=read(p)
        if d.get('stored_overlay')or d.get('derived_overlay_path'):prep_index[d['cache_key']]=d
    for row in rows:
        if not row.get('path'):continue
        d=read(ROOT/row['path']);key=d.get('preprocessing_cache',{}).get('key')
        if not key or key not in prep_index:continue
        q=row['request'];query=d.get('query',{});scene=q.get('scene_id',query.get('scene_id'));door=q.get('door_id')
        if float(q.get('seam_max_m',2))!=2:continue
        group=groups.setdefault((scene,door),{})
        mode=q['connectivity_mode'];candidate={'row':row,'response':d,'prep_key':key}
        old=group.get(mode)
        if old is None or d.get('versions',{}).get('code_sha256')==planner.code_identity():group[mode]=candidate
    stats=[];memberships=[];failures=[]
    modes=planner.CONNECTIVITY_MODES
    for (scene,door),records in sorted(groups.items(),key=lambda item:(item[0][0],item[0][1]or'')):
        print(json.dumps({'namespace':[scene,door],'stage':'RECONSTRUCT_SOURCE_LOCAL_ONLY_NO_SEARCH'}),flush=True)
        planner._activate_preprocessing_group(scene,door)
        base,_,_=planner._prepare_network(scene)if door is None else planner._prepare(scene,door)
        source_snapshot=structure_snapshot(base['source']);local_snapshot=structure_snapshot(base['region'].internal)
        previous=None
        for mode in modes:
            if mode not in records:continue
            rec=records[mode];pp=prep_index[rec['prep_key']];overlay_paths=[]
            def load_chain(key):
                p=prep_index[key]
                if p.get('mode')in('EXACT_STITCH','CONDITIONAL_SEAMS'):parents=load_chain(p['parent_cache_key'])
                else:parents=[]
                path=p.get('stored_overlay',p.get('derived_overlay_path'));expected=p.get('stored_overlay_sha256',p.get('derived_overlay_sha256'))
                overlay_paths.append({'path':path,'sha256':expected})
                return [*parents,load_graph(ROOT/path,expected)]
            overlays=load_chain(rec['prep_key'])
            graph=planner.compose_prepared({**base,'face_overlays':overlays});actual=planner.graph_sha(graph)
            if actual!=pp['graph_sha256']:
                failures.append({'namespace':[scene,door],'mode':mode,'actual_sha256':actual,'expected':pp['graph_sha256'],'status':'NOT_VERIFIED_GRAPH_IDENTITY_MISMATCH'})
                del graph,overlays;gc.collect();continue
            weak,strong,wc,sc=labels(graph)
            row={'scene_id':scene,'door_id':door,'mode':mode,'nodes':len(graph),'arcs':graph.number_of_edges(),'weak_components':wc,'strong_components':sc,
                'prepared_graph_sha256':actual,'original_PREP_cache_key':rec['prep_key'],'bound_response_sha256':rec['row']['result_sha256'],
                'source_topology':source_snapshot,'local_topology':local_snapshot,'overlays':overlay_paths,
                'scope':'EXACT_PREPARED_SOURCE_LOCAL_AND_FACE_GRAPH_BEFORE_QUERY_BINDING; NOT_PHYSICAL_PASSAGE_OR_DOOR_QUALIFICATION'}
            if previous:row.update(parent_comparison_mode=previous['mode'],weak_component_count_change=wc-previous['wc'],strong_component_count_change=sc-previous['sc'])
            stats.append(row)
            ev=pp.get('connectivity_evidence',pp.get('face_evidence',{}))
            for record_kind in ('interfaces','seams'):
                for item in ev.get(record_kind,[]):
                    ids=item.get('graph_node_ids',[])
                    memberships.append({'scene_id':scene,'door_id':door,'mode':mode,'id':item['id'],'record_kind':record_kind,'accepted':item.get('accepted'),'entered_graph':item.get('entered_graph'),
                        'graph_node_ids':ids,'old_weak_component_labels':[previous['weak'].get(n)for n in ids]if previous else None,
                        'new_weak_component_labels':[weak.get(n)for n in ids],'old_strong_component_labels':[previous['strong'].get(n)for n in ids]if previous else None,
                        'new_strong_component_labels':[strong.get(n)for n in ids],'missing_parent_node_identity_is_not_a_physical_gap':True,
                        'graph_sha256':actual,'scope':'PREPARED_GRAPH_BEFORE_TERMINAL_BINDING'})
            previous={'mode':mode,'weak':weak,'strong':strong,'wc':wc,'sc':sc}
            print(json.dumps({'scene':scene,'door':door,'mode':mode,'WCC':wc,'SCC':sc,'graph_identity':'MATCH'}),flush=True)
            del graph,overlays;gc.collect()
    csvfile(ROOT/'results/component_statistics.csv',stats);csvfile(ROOT/'results/interface_component_membership.csv',memberships)
    output={'author_role':'/root','scope':'Independent of route answers but uses author frozen base compiler; independent counting can replay structure snapshots and retained overlays.','APP_solver_calls':0,'VG_rebuilds':0,'verified_prepared_graphs':len(stats),'identity_failures':failures,'elapsed_s':time.perf_counter()-tick,'snapshots':'results/topology_inputs','scientific_limit':'Connected components in this model do not establish current public or physical passage.'}
    planner.put(ROOT/'results/component_analysis_receipt.json',output);print(json.dumps(output),flush=True)
if __name__=='__main__':main()
