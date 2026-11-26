"""Eight bounded fresh solves on fixed development graphs; no new map/constraint model."""
from pathlib import Path
import argparse,csv,datetime,gzip,hashlib,json,sys,time,uuid,zipfile,gc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from walkability_foundation.graph_costs import batch_costs,scalar_costs

def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--expected-sha',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 if(a.out/'protocol.json').exists():raise SystemExit('EXISTING_PROBE_REFUSED')
 assert sha(a.archive)==a.expected_sha
 a.out.mkdir(parents=True,exist_ok=True);clock=time.perf_counter();code={p.relative_to(Path(__file__).resolve().parents[1]).as_posix():sha(p)for p in[Path(__file__),Path(__file__).resolve().parents[1]/'src/walkability_foundation/graph_costs.py']}
 put(a.out/'protocol.json',{'task':'TA-PG1-01','locked_at':datetime.datetime.now().astimezone().isoformat(),'max_formal_calls':8,'method':'same B3 graph; scalar versus batch min-option construction; fresh forward Dijkstra once per request','source_archive_sha256':a.expected_sha,'code':code,'split':'EXPOSED_DEVELOPMENT_ONLY','new_constraint_or_penalty':False,'answer_cache':False,'positive_gain_not_required':True})
 rows=[]
 with zipfile.ZipFile(a.archive)as z:
  reg=json.loads(z.read('results/solver_registry.json'))['formal_invocations']
  for case in dict.fromkeys(r['case']for r in reg):
   tick=time.perf_counter();xy={};arcs=[]
   with z.open('data/'+case+'_query_graph.jsonl.gz')as f,gzip.GzipFile(fileobj=f)as stream:
    for line in stream:
     r=json.loads(line)
     if r['kind']=='node':xy[r['id']]=r['xy']
     else:arcs.append(r)
   load_s=time.perf_counter()-tick;ids=list(xy);idx={n:i for i,n in enumerate(ids)};u=np.array([idx[r['u']]for r in arcs]);v=np.array([idx[r['v']]for r in arcs]);assert len(set(zip(u.tolist(),v.tolist())))==len(arcs)
   groups=[r['options']for r in arcs];topology_sha=hashlib.sha256(u.tobytes()+v.tobytes()).hexdigest();sibling=[]
   for old in [r for r in reg if r['case']==case]:
    method=old['method'];penalty=0 if method=='F0'else 1;tick=time.perf_counter();reference=scalar_costs(groups,penalty);scalar_s=time.perf_counter()-tick;tick=time.perf_counter();cost=batch_costs(groups,penalty);batch_s=time.perf_counter()-tick
    assert np.array_equal(cost,reference);graph=csr_matrix((cost,(u,v)),shape=(len(ids),len(ids)));assert graph.nnz==len(arcs)
    invocation='TA-PG1-01-'+uuid.uuid4().hex;tick=time.perf_counter();ds,pred=dijkstra(graph,directed=True,indices=idx[old['start_id']],return_predecessors=True);solver_s=time.perf_counter()-tick;target=idx[old['door_id']];assert np.isfinite(ds[target])
    path=[target]
    while path[-1]!=idx[old['start_id']]:
     nxt=int(pred[path[-1]]);assert nxt>=0 and nxt not in path;path.append(nxt)
    path.reverse();lookup={(r['u'],r['v']):r['options']for r in arcs};segments=[]
    for i,j in zip(path,path[1:]):
     uu,vv=ids[i],ids[j];o=min(lookup[uu,vv],key=lambda x:x[0]+penalty*x[1]);segments.append({'u':uu,'v':vv,'xy':[xy[uu],xy[vv]],'length_m':o[0],'hypothesis_m':o[1],'cost_m':o[0]+penalty*o[1],'source_area_ids':o[2],'interface_ids':o[3],'geometry_kind':o[4]})
    historical=json.loads(z.read('runs/'+old['invocation_id']+'.json'))['minimum'];error=float(ds[target])-historical['cost_m'];assert abs(error)<1e-7
    finite=np.isfinite(ds[u]);assert np.all(np.isfinite(ds[v[finite]]))
    assert np.max(ds[v[finite]]-ds[u[finite]]-cost[finite],initial=-np.inf)<1e-7
    run={'invocation_id':invocation,'case':case,'method':method,'split':'EXPOSED_DEVELOPMENT_ONLY','start_id':old['start_id'],'door_id':old['door_id'],'start_xy':xy[old['start_id']],'door_xy':xy[old['door_id']],'purpose':'APPROACH_OUTSIDE'if old['door_id']=='node/6897145227'else'KNOWN_REGISTERED_DOOR_APPROACH','segments':segments,'length_m':sum(s['length_m']for s in segments),'hypothesis_m':sum(s['hypothesis_m']for s in segments),'cost_m':float(ds[target]),'historical_cost_m':historical['cost_m'],'historical_cost_error_m':error,'new_solver_calls':1,'answer_cache':False,'new_geometry_admission':False,'topology_sha256':topology_sha,'source_archive_sha256':a.expected_sha,'source_graph_member':old['query_graph'],'source_code_hashes':code,'load_s':load_s,'scalar_weight_s':scalar_s,'batch_weight_s':batch_s,'solver_s':solver_s,'geometry_and_permissions':'INHERITED_FIXED_R2_GRAPH_NOT_FIELD_VALIDATED'}
    put(a.out/'runs'/(invocation+'.json'),run);np.savez_compressed(a.out/(case+'_'+method+'_certificate.npz'),ids=np.array(ids),ds=ds,pred=pred,u=u,v=v,cost=cost)
    row={k:run[k]for k in('invocation_id','case','method','length_m','hypothesis_m','cost_m','historical_cost_error_m','load_s','scalar_weight_s','batch_weight_s','solver_s','topology_sha256')};rows.append(row);sibling.append(topology_sha);put(a.out/'registry.json',{'formal_calls':len(rows),'cap':8,'complete':False,'rows':rows});print(json.dumps(row),flush=True);del ds,pred,graph,lookup;gc.collect()
   assert len(set(sibling))==1;del xy,arcs,groups;gc.collect()
 assert len(rows)==8
 put(a.out/'registry.json',{'formal_calls':8,'cap':8,'SSSP_calls':8,'complete':True,'rows':rows,'elapsed_s':time.perf_counter()-clock,'scope':'Engineering cost-mode continuity, not a new algorithm mechanism or generalization test','business_improvement':'NONE_CLAIMED','source_archive_unchanged':sha(a.archive)==a.expected_sha})
 with(a.out/'results.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
if __name__=='__main__':main()
