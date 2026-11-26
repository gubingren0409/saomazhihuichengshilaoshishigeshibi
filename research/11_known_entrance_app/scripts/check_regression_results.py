"""Author checks of newly executed regression primitives, not user/field review."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,csv,gzip,hashlib,json,math,sys
from shapely.geometry import LineString,Point,shape
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.common_constraints import parsed_contract,edge_conflicts

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    suite=ROOT/'runs/benchmark/R2_unified';checks=[];totals=defaultdict(Counter);failures=[];core=defaultdict(set)
    for file in sorted(suite.glob('*/result.json')):
        r=read(file);ident=file.parent.name;cfg=read(file.parent/'config.json');query=read(file.parent/'query.json')['queries']
        lookup={q['query_id']:q for q in query};common=parsed_contract(r['common_constraints'])
        for k,v in r['code_bindings'].items():
            if k in {'src/region.py','src/context_policy.py','src/free_surface.py','src/free_routing.py','src/common_constraints.py','src/region_routing.py'}:core[k].add(v)
        same=(r['methods']['F0']['graph_sha256']==r['methods']['F1']['graph_sha256']and r['methods']['F0']['surface_sha256']==r['methods']['F1']['surface_sha256'])
        if not same:failures.append({'input_id':ident,'error':'F0_F1_GRAPH_OR_SURFACE_DIFFER'})
        for method,pred in r['methods'].items():
            for qid,route in pred['routes'].items():
                q=lookup[qid];prior=q['source']['xy'];max_gap=0;lengths=Counter();cost=0;conflicts=[];length_error=0
                for e in route['edges']:
                    line=LineString(e['xy']);max_gap=max(max_gap,math.dist(prior,e['xy'][0]));prior=e['xy'][-1]
                    lengths[e['layer']]+=line.length;cost+=line.length*(2 if method=='F1'and e['layer']in {'inferred','unknown','assumed'}else 1)
                    length_error=max(length_error,abs(line.length-e['length_m']))
                    reasons=edge_conflicts(line,common,native=e['layer']=='native',tags=e.get('tags',{}),source_id=e.get('source_id'))
                    if reasons:conflicts.append({'source_id':e.get('source_id'),'reasons':reasons})
                residual=math.dist(prior,q['target']['xy'])if route['reached']else None
                valid=(not route['reached'])or(not conflicts and max_gap<=1e-6 and residual<=1e-6 and length_error<=1e-6 and abs(sum(lengths.values())-route['length_m'])<=1e-6 and abs(cost-route['cost_m'])<=1e-6)
                if not valid:failures.append({'input_id':ident,'method':method,'query_id':qid,'conflicts':conflicts,'gap':max_gap,'residual':residual})
                checks.append({'input_id':ident,'method':method,'query_id':qid,'status':route['status'],'reached':route['reached'],'route_valid_under_current_map_contract':valid,
                               'solver_search_invoked':route['status']!='UNAVAILABLE_ENDPOINT','max_gap_m':max_gap,'residual_m':residual,'length_error_m':length_error,'known_conflicts':len(conflicts),
                               'native_m':lengths['native'],'mapped_derived_m':lengths['derived'],'assumed_m':lengths['inferred']+lengths['unknown'],'cost_weighted_m':cost,'graph_surface_shared_F0_F1':same})
                if route['reached']:totals[method].update(native_m=lengths['native'],mapped_derived_m=lengths['derived'],assumed_m=lengths['inferred']+lengths['unknown'],length_m=sum(lengths.values()))
        for qid in lookup:
            if r['methods']['F0']['routes'][qid]['reached']!=r['methods']['F1']['routes'][qid]['reached']:
                failures.append({'input_id':ident,'query_id':qid,'error':'FINITE_COST_CHANGED_REACHABILITY'})
    target=ROOT/'AUDIT/regression_route_checks.csv'
    with target.open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
    summary={'role':'AUTHOR_GEOMETRY_AND_CONTRACT_CHECK_NOT_INDEPENDENT_REVIEW','status':'PASS'if not failures else'FAIL','query_evaluations':len(checks),
             'actual_search_invocations':sum(c['solver_search_invoked']for c in checks),'unbound_endpoint_rejections':sum(not c['solver_search_invoked']for c in checks),
             'full_route_known_constraint_conflicts':sum(c['known_conflicts']for c in checks),'failures':failures,'method_layer_totals_all41':dict(totals),
             'core_bindings':{k:sorted(v)for k,v in core.items()},'core_version_consistent':all(len(v)==1 for v in core.values()),
             'scope':'25 parents/41 exact frozen queries, three methods; 8 obstacle queries include legal native detours; no field truth',
             'limitations':['Author edge_conflicts function reused for whole-map-contract checks; independent reviewer must separately check primitives','Known obstacle controls are not 8 necessarily unreachable targets','Historical diagnostic source/target identity is separate from APP registered door acceptance']}
    (ROOT/'AUDIT/regression_author_checks.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:summary[k]for k in ('status','query_evaluations','actual_search_invocations','unbound_endpoint_rejections','full_route_known_constraint_conflicts','core_version_consistent')},ensure_ascii=False))

if __name__=='__main__':main()
