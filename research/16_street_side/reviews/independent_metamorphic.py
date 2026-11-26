"""Metamorphic checks of delivered author graph, with independent equality logic.

This is not an independent implementation of the classification policy and
does not call a path solver. It checks way reversal of actual graph outputs.
"""
import datetime, hashlib, importlib.util, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
src=ROOT/'scripts/street_side.py'
spec=importlib.util.spec_from_file_location('side_author_under_test',src)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def fixture(tags,reverse=False):
    xy={1:[0.,0.],2:[10.,0.],3:[10.,10.]};ids=[1,2,3]
    if reverse:ids.reverse()
    return {'ways':{'7':{'type':'way','id':7,'nodes':ids,'tags':tags}},'nodes':{str(n):{'type':'node','id':n,'tags':{}}for n in ids},'native_admission':[{'source_id':'way/7','segment_index':i,'source_node_ids':[a,b],'xy':[xy[a],xy[b]],'directions':[-1]if reverse else[1],'evidence':'SHARED_STREET_ASSUMPTION','status':'KEEP_NATIVE'}for i,(a,b)in enumerate(zip(ids,ids[1:]))]}

def canonical(graph,reverse_side=False):
    arcs=[]
    for edge in graph['edges']:
        side=edge['side']
        if reverse_side:side={'left':'right','right':'left',None:None}[side]
        coords=[tuple(round(v,9)for v in p)for p in edge['xy']]
        for d in edge['directions']:
            a,b=coords if d==1 else coords[::-1]
            arcs.append((side,a,b,round(edge['cost_f0'],9),round(edge['cost_f1'],9),edge['evidence'],edge['hypothesis'],edge['geometry_status']))
    return sorted(arcs)

cases=[]
for name,variant,tags,reversed_tags in [('tagged_left_to_right','R1',{'highway':'residential','sidewalk:left':'yes'},{'highway':'residential','sidewalk:right':'yes'}),('missing_both_sides','R2',{'highway':'residential'},{'highway':'residential'})]:
    a=module.graph(fixture(tags),variant);b=module.graph(fixture(reversed_tags,True),variant)
    ca,cb=canonical(a),canonical(b,True)
    cases.append({'name':name,'variant':variant,'graph_builds':2,'pass':ca==cb,'directed_arcs_checked':len(ca),'original_canonical_arcs':ca,'reversed_canonical_arcs':cb})
report={'reviewer':'/root/resume_review','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS_FOR_TWO_WAY_REVERSAL_METAMORPHIC_CASES'if all(c['pass']for c in cases)else'FAIL','author_source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'cases':cases,'independent_metamorphic_graph_builds':4,'new_solver_calls':0,'new_sssp_calls':0,'new_network_requests':0,'scope':'Independent input reversal and directed-edge/cost/geometry equality comparison around delivered author graph. This calls author graph generation under test and is not an independently reimplemented classifier or field validation.'}
(ROOT/'reviews/independent_metamorphic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'graph_builds':4,'solver_calls':0},ensure_ascii=False))
raise SystemExit(0 if all(c['pass']for c in cases) else 1)
