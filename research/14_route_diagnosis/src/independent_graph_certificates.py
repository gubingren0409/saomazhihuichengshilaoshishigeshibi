"""Verify shortest-distance primal/dual certificates without new SSSP calls."""
from pathlib import Path
import gzip,json,hashlib,collections,gc
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def reach(start,u,v,n):
    order=np.argsort(u,kind='stable');targets=v[order];offset=np.r_[0,np.cumsum(np.bincount(u,minlength=n))]
    marked=np.zeros(n,dtype=bool);marked[start]=True;q=collections.deque([start])
    while q:
        a=q.popleft()
        for b in targets[offset[a]:offset[a+1]]:
            if not marked[b]:marked[b]=True;q.append(int(b))
    return marked
def roots_terminate(pred,finite,root):
    good={root};bad=[]
    for initial in np.flatnonzero(finite):
        a=int(initial);path=[];seen=set()
        while a not in good:
            if a<0 or a>=len(pred)or a in seen:bad.append(int(initial));break
            seen.add(a);path.append(a);a=int(pred[a])
        else:good.update(path)
    return bad
def main():
    registry=json.loads((ROOT/'results/solver_registry.json').read_text());runs=registry['formal_invocations'];outputs=[];all_errors=[]
    for case in ['south','north_near','north_far','library']:
        subset=[r for r in runs if r['case']==case];first=np.load(ROOT/f'data/{case}_F0_distances.npz',allow_pickle=False)
        ids=first['ids'].tolist();index={n:i for i,n in enumerate(ids)};n=len(ids);u=first['edge_u'];v=first['edge_v'];m=len(u);xy=np.empty((n,2));c0=np.empty(m);c1=np.empty(m);geometry_errors=[];i=0;node_count=0
        graphpath=ROOT/f'data/{case}_query_graph.jsonl.gz'
        with gzip.open(graphpath,'rt',encoding='utf-8')as stream:
            for line in stream:
                r=json.loads(line)
                if r['kind']=='node':xy[index[r['id']]]=r['xy'];node_count+=1;continue
                a=index[r['u']];b=index[r['v']]
                if a!=u[i]or b!=v[i]:geometry_errors.append('ARC_ORDER_ID_MISMATCH')
                lengths=[o[0]for o in r['options']];weighted=[o[0]+o[1]for o in r['options']]
                if any(o[0]<-1e-10 or o[1]<-1e-10 or o[1]>o[0]+1e-8 for o in r['options']):geometry_errors.append('INVALID_LENGTH_OR_HYPOTHESIS')
                c0[i]=min(lengths);c1[i]=min(weighted);i+=1
        if node_count!=n or i!=m:geometry_errors.append('GRAPH_CARDINALITY')
        keys=u.astype(np.int64)*n+v;order=np.argsort(keys);sorted_keys=keys[order]
        for run in subset:
            method=run['method'];npz=ROOT/f'data/{case}_{method}_distances.npz';data=np.load(npz,allow_pickle=False);errors=list(geometry_errors);cost=c0 if method=='F0'else c1
            if not np.array_equal(data['ids'],np.array(ids))or not np.array_equal(data['edge_u'],u)or not np.array_equal(data['edge_v'],v):errors.append('SHARED_GRAPH_IDENTITY')
            if np.max(np.abs(data['cost']-cost))>1e-8:errors.append('PARALLEL_OPTION_MIN_COST')
            s=index[run['start_id']];t=index[run['door_id']];ds=data['ds'];dt=data['dt'];ps=data['ps'];pt=data['pt'];rs=reach(s,u,v,n);rt=reach(t,v,u,n)
            if not np.array_equal(np.isfinite(ds),rs)or not np.array_equal(np.isfinite(dt),rt):errors.append('DIRECTED_REACHABILITY')
            if abs(ds[s])>1e-10 or abs(dt[t])>1e-10:errors.append('ROOT_DISTANCE')
            f=np.isfinite(ds[u])&np.isfinite(ds[v]);dual_s=float(np.max(ds[v[f]]-ds[u[f]]-cost[f]))if f.any()else 0.
            f=np.isfinite(dt[u])&np.isfinite(dt[v]);dual_t=float(np.max(dt[u[f]]-dt[v[f]]-cost[f]))if f.any()else 0.
            if max(dual_s,dual_t)>1e-7:errors.append('BELLMAN_DUAL_INEQUALITY')
            residuals=[]
            for distances,pred,root,reverse in [(ds,ps,s,False),(dt,pt,t,True)]:
                nodes=np.flatnonzero(np.isfinite(distances));nodes=nodes[nodes!=root];parents=pred[nodes]
                if np.any(parents<0):errors.append('MISSING_PRIMAL_PARENT');continue
                requested=(nodes*n+parents)if reverse else(parents*n+nodes);at=np.searchsorted(sorted_keys,requested)
                if np.any(at>=len(sorted_keys))or not np.array_equal(sorted_keys[np.minimum(at,len(sorted_keys)-1)],requested):errors.append('PRIMAL_EDGE_ABSENT');continue
                residual=float(np.max(np.abs(distances[nodes]-distances[parents]-cost[order[at]])))if len(nodes)else 0.;residuals.append(residual)
                if residual>1e-7:errors.append('PRIMAL_DISTANCE_COST')
                if roots_terminate(pred,np.isfinite(distances),root):errors.append('PRIMAL_NOT_TERMINATING_AT_ROOT')
            if abs(ds[t]-dt[s])>1e-7:errors.append('FORWARD_REVERSE_GOAL_COST')
            if max(np.linalg.norm(xy[s]-run['start_xy']),np.linalg.norm(xy[t]-run['door_xy']))>1e-8:errors.append('ORIGINAL_ENDPOINT_XY')
            outputs.append({'case':case,'method':method,'invocation_id':run['invocation_id'],'graph_sha256':sha(graphpath),'distance_npz_sha256':sha(npz),'nodes':n,'arcs':m,'directed_start_reachable_nodes':int(rs.sum()),'nodes_can_reach_goal':int(rt.sum()),'best_cost_m':float(ds[t]),'max_forward_dual_residual_m':dual_s,'max_reverse_dual_residual_m':dual_t,'primal_residuals_m':residuals,'errors':errors})
            all_errors.extend((case,method,e)for e in errors);data.close()
        first.close();gc.collect()
    result={'reviewer':'/root/r2_independent','scope':'Independent directed BFS and per-edge minimum over parallel options; all-arc Bellman inequalities plus primal parent paths to roots prove given distance certificates optimal in this finite reconstructed graph. No new shortest-path solver invoked.',
        'new_SSSP_calls':0,'new_APP_solver_calls':0,'formal_invocations_observed':registry['formal_count'],'SSSP_traversals_observed':registry['SSSP_traversals'],'rows':outputs,'errors':all_errors,'status':'PASS_FOR_RECONSTRUCTED_GRAPH_DISTANCE_CERTIFICATES'if not all_errors and len(outputs)==8 else'REQUIRES_INSPECTION','limits':['Does not independently assert all native source admission or physical access','Query bindings fixed; not continuous-domain or all-potential-attachment optimality','Alternative forced-option materialization audited separately']}
    (ROOT/'audits/independent_graph_distance_certificates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':result['status'],'rows':len(outputs),'errors':all_errors}))
if __name__=='__main__':main()
