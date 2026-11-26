"""Verify directed topology and component lineage without author classifiers/SSSP."""
from pathlib import Path
import json,collections,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def adjacency(u,v,n):
    order=np.argsort(u,kind='stable');return v[order],np.r_[0,np.cumsum(np.bincount(u,minlength=n))]
def bfs(start,targets,offset,labels=None):
    seen={int(start)};q=collections.deque(seen);label=labels[start]if labels is not None else None
    while q:
        u=q.popleft()
        for v in targets[offset[u]:offset[u+1]]:
            v=int(v)
            if v not in seen and(labels is None or labels[v]==label):seen.add(v);q.append(v)
    return seen
def main():
    lineage=json.loads((ROOT/'results/graph_lineage.json').read_text())['lineage'];details=json.loads((ROOT/'results/query_component_lineage.json').read_text());registry=json.loads((ROOT/'results/solver_registry.json').read_text());allrows=[];errors=[];lineage_rows=0
    for case in('south','north_near','north_far','library'):
        run=next(r for r in registry['formal_invocations']if r['case']==case);old=None
        for mode in('B0','B1','B2','B3'):
            path=ROOT/f'data/{case}_{mode}_topology.npz';d=np.load(path,allow_pickle=False);ids=d['ids'].tolist();ix={n:i for i,n in enumerate(ids)};n=len(ids);u,v=d['edge_u'],d['edge_v'];a,ao=adjacency(u,v,n);b,bo=adjacency(v,u,n);wc=d['wcc'];sc=d['scc'];bad=[]
            fr=bfs(ix[run['start_id']],a,ao);to=bfs(ix[run['door_id']],b,bo)
            if fr!=set(np.flatnonzero(d['from_start']))or to!=set(np.flatnonzero(d['to_goal'])):bad.append('DIRECTED_ENDPOINT_REACH')
            # A weak label is valid iff every edge stays within it, and every class
            # has one connected spanning exploration in the undirected graph.
            if np.any(wc[u]!=wc[v]):bad.append('WEAK_EDGE_CROSSES_LABEL')
            wgroups=collections.defaultdict(list);sgroups=collections.defaultdict(list)
            for i in range(n):wgroups[int(wc[i])].append(i);sgroups[int(sc[i])].append(i)
            und,undo=adjacency(np.r_[u,v],np.r_[v,u],n)
            if any(len(bfs(nodes[0],und,undo,wc))!=len(nodes)for nodes in wgroups.values()):bad.append('WEAK_CLASS_NOT_CONNECTED')
            if any(len(bfs(nodes[0],a,ao,sc))!=len(nodes)or len(bfs(nodes[0],b,bo,sc))!=len(nodes)for nodes in sgroups.values()):bad.append('STRONG_CLASS_NOT_STRONGLY_CONNECTED')
            cross={(int(sc[x]),int(sc[y]))for x,y in zip(u,v)if sc[x]!=sc[y]};out=collections.defaultdict(set);indegree={k:0 for k in sgroups}
            for x,y in cross:out[x].add(y);indegree[y]+=1
            queue=collections.deque(k for k,nin in indegree.items()if not nin);visited=0
            while queue:
                x=queue.popleft();visited+=1
                for y in out[x]:
                    indegree[y]-=1
                    if not indegree[y]:queue.append(y)
            if visited!=len(sgroups):bad.append('SCC_CONDENSATION_HAS_CYCLE')
            meta=next(r for r in details if r['case']==case and r['mode']==mode)
            if len(wgroups)!=meta['weak_components']or len(sgroups)!=meta['strong_components']or int(wc[ix[run['start_id']]])!=meta['start_component']or int(wc[ix[run['door_id']]])!=meta['door_component']:bad.append('COMPONENT_META')
            if old:
                oldmode,oldlabels=old;common=oldlabels.keys()&ix.keys();counts=collections.Counter((oldlabels[node],int(wc[ix[node]]))for node in common);nativecounts=collections.Counter((oldlabels[node],int(wc[ix[node]]))for node in common if node.startswith('node/'));published={(r['old_component'],r['new_component']):r['common_node_count']for r in lineage if r['case']==case and r['from_mode']==oldmode and r['to_mode']==mode};published_native={(r['old_component'],r['new_component']):r['common_native_token_count']for r in lineage if r['case']==case and r['from_mode']==oldmode and r['to_mode']==mode}
                if counts!=published:bad.append('COMMON_NODE_LINEAGE')
                if any(nativecounts[k]!=v for k,v in published_native.items()):bad.append('COMMON_NATIVE_TOKEN_LINEAGE')
                lineage_rows+=len(counts)
            old=(mode,{node:int(wc[i])for i,node in enumerate(ids)})
            allrows.append({'case':case,'mode':mode,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'nodes':n,'arcs':len(u),'weak_components':len(wgroups),'strong_components':len(sgroups),'from_start_nodes':len(fr),'to_goal_nodes':len(to),'errors':bad});errors.extend((case,mode,e)for e in bad);d.close()
    result={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_solver_calls':0,'new_SSSP_calls':0,'status':'PASS_FOR_ALL_MODE_COMPONENTS_AND_LINEAGE'if not errors else'REQUIRES_INSPECTION','rows':allrows,'lineage_cells_verified':lineage_rows,'errors':errors,'scope':'Own queue traversal verifies endpoint directed reachability, all WCC internal connectivity, all SCC forward/reverse connectivity plus acyclic condensation, and exact common-ID lineage; numeric labels are mode-local, not stable physical identities.'}
    (ROOT/'audits/independent_topology_lineage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':result['status'],'rows':len(allrows),'lineage_rows':lineage_rows,'errors':errors}))
if __name__=='__main__':main()
