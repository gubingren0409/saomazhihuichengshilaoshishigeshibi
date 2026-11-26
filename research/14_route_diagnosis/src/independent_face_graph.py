"""Independently check newly admitted face ownership and directed cost opportunity."""
from pathlib import Path
import json,csv,gzip,math,hashlib,collections,gc
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def yes(v):return v=='True'
def main():
    inputrows=list(csv.DictReader((ROOT/'NEW_FACE_ROUTE_RELEVANCE.csv').open(encoding='utf-8-sig')));rows=[];errors=[]
    for case in('south','north_near','north_far','library'):
        wanted={r['source_area_id']for r in inputrows if r['case']==case and yes(r['in_query_scene'])};arcs=collections.defaultdict(list);nodes=collections.defaultdict(set)
        with gzip.open(ROOT/f'data/{case}_query_graph.jsonl.gz','rt',encoding='utf-8')as f:
            for line in f:
                r=json.loads(line)
                if r['kind']!='arc':continue
                for o in r['options']:
                    for ident in wanted.intersection(o[2]):arcs[ident].append((r['u'],r['v'],o));nodes[ident].update((r['u'],r['v']))
        for method in('F0','F1'):
            d=np.load(ROOT/f'data/{case}_{method}_distances.npz',allow_pickle=False);index={n:i for i,n in enumerate(d['ids'])};ds,dt=d['ds'],d['dt'];factor=method=='F1';best=float(min(ds[i]+dt[i]for i in range(len(ds))if math.isfinite(ds[i])and math.isfinite(dt[i])))
            for r in inputrows:
                if r['case']!=case or r['method']!=method or not yes(r['in_query_scene']):continue
                ident=r['source_area_id'];ns=nodes[ident];aa=arcs[ident];forced=min((float(ds[index[u]]+o[0]+factor*o[1]+dt[index[v]])for u,v,o in aa),default=math.inf);reachable=any(math.isfinite(ds[index[n]])for n in ns);goalable=any(math.isfinite(dt[index[n]])for n in ns);bad=[];observed=float(r['forced_arc_cost_lower_bound_m'])if r['forced_arc_cost_lower_bound_m']else math.inf
                if len(ns)!=int(r['owned_node_count'])or reachable!=yes(r['in_start_component'])or goalable!=yes(r['in_goal_component']):bad.append('OWNER_NODES_OR_DIRECTION')
                if math.isfinite(observed)!=math.isfinite(forced)or math.isfinite(forced)and max(abs(observed-forced),abs(float(r['slack_lower_bound_m'])-(forced-best)))>1e-7:bad.append('MIN_FORCED_COST_OR_SLACK')
                rows.append({'case':case,'method':method,'source_id':ident,'global_new':yes(r['global_unique_new']),'owned_nodes':len(ns),'owner_options':len(aa),'directed_from_start':reachable,'directed_to_goal':goalable,'minimum_forced_cost_m':forced if math.isfinite(forced)else None,'slack_m':forced-best if math.isfinite(forced)else None,'reported_reason':r['reason'],'errors':bad});errors.extend((case,method,ident,e)for e in bad)
            d.close()
        del arcs,nodes;gc.collect()
    result={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'face_CSV_sha256':hashlib.sha256((ROOT/'NEW_FACE_ROUTE_RELEVANCE.csv').read_bytes()).hexdigest(),'status':'PASS_FOR_FACE_OWNERSHIP_AND_DIRECTED_OPPORTUNITY'if not errors else'REQUIRES_INSPECTION','new_solver_calls':0,'new_SSSP_calls':0,'rows':rows,'errors':errors,'scope':'All184 own-scene face×method records (27×3 Museum endpoint tasks +11 Library, each F0/F1) independently measured against full exported owner-labelled parallel options and previously certified ds/dt. Finite forced walks do not automatically certify simple alternative paths.'}
    (ROOT/'audits/independent_face_graph_opportunity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':result['status'],'rows':len(rows),'errors':errors[:20]}))
if __name__=='__main__':main()
