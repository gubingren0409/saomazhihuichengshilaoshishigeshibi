"""Regenerate final scalar summaries, lineage and provenance, without new search."""
from pathlib import Path
import json,csv,hashlib,datetime,collections
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def put(n,d):
 (ROOT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 summary=json.loads((ROOT/'results/summary.json').read_text());faces=list(csv.DictReader((ROOT/'NEW_FACE_ROUTE_RELEVANCE.csv').open(encoding='utf-8-sig')))
 for case in summary['cases']:
  for method,sm in case['methods'].items():
   rr=[x for x in faces if x['case']==case['case']and x['method']==method and x['in_query_scene']=='True'];gg=[x for x in rr if x['global_unique_new']=='True']
   sm['faces']={'scene_added':len(rr),'global_unique_new_in_scene':len(gg),'within_5m':sum(x['within_5m']=='True'for x in rr),'within_10m':sum(x['within_10m']=='True'for x in rr),'within_20m':sum(x['within_20m']=='True'for x in rr),'scene_reasons':dict(collections.Counter(x['reason']for x in rr)),'global_new_reasons':dict(collections.Counter(x['reason']for x in gg))}
 seen={x['source_area_id']:x for x in faces if x['global_unique_new']=='True'and x['in_query_scene']=='True'}
 summary['global_new_business_scene_overlap']={'global_new_total':82,'unique_new_in_business_scene_pools':len(seen),'outside_business_scene_pools':82-len(seen),'unique_reasons':dict(collections.Counter(x['reason']for x in seen.values())),'dedup_scope':'R1 unique source IDs; scene records not independent evidence'}
 summary['unconnected_face_evidence']='results/unconnected_face_evidence.json';put('results/summary.json',summary)
 lineage=[];native=[]
 for case in ['south','north_near','north_far','library']:
  for mi in [1,2,3]:
   a=np.load(ROOT/f'data/{case}_B{mi-1}_topology.npz');b=np.load(ROOT/f'data/{case}_B{mi}_topology.npz');aa={str(n):int(c)for n,c in zip(a['ids'],a['wcc'])};bb={str(n):int(c)for n,c in zip(b['ids'],b['wcc'])}
   counts=collections.Counter((aa[n],bb[n])for n in aa.keys()&bb.keys());nn=collections.Counter((aa[n],bb[n])for n in aa.keys()&bb.keys()if n.startswith('node/'))
   for k,v in counts.items():lineage.append({'case':case,'from_mode':'B'+str(mi-1),'to_mode':'B'+str(mi),'old_component':k[0],'new_component':k[1],'common_node_count':v,'common_native_token_count':nn[k]})
   native.append({'case':case,'from_mode':'B'+str(mi-1),'to_mode':'B'+str(mi),'common_native_tokens':sum(nn.values()),'source':'node/ID with original @layer/@level; derived nodes excluded'})
 put('results/graph_lineage.json',{'lineage':lineage,'native_anchor_summary':native,'scope':'Query-bound graph IDs; grades not merged; numeric labels local to case/mode'})
 registry=json.loads((ROOT/'results/solver_registry.json').read_text());binding=[];checks=[]
 for r in registry['formal_invocations']:
  case,method=r['case'],r['method'];run=ROOT/'runs'/(r['invocation_id']+'.json');g=ROOT/f'data/{case}_query_graph.jsonl.gz';c=ROOT/f'data/{case}_{method}_distances.npz'
  binding.append({'invocation_id':r['invocation_id'],'case':case,'method':method,'original_run_path':run.relative_to(ROOT).as_posix(),'original_run_sha256':sha(run),'executed_source_snapshot':'audit/diagnose_first_run.py','executed_source_sha256':sha(ROOT/'audit/diagnose_first_run.py'),'graph_path':g.relative_to(ROOT).as_posix(),'graph_sha256':sha(g),'distance_certificate_path':c.relative_to(ROOT).as_posix(),'distance_certificate_sha256':sha(c),'R1_archive_sha256':'d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed','R1_response_sha256':r['old_response_sha256']})
  z=np.load(c);ds,dt,u,v,w=[z[k]for k in ['ds','dt','edge_u','edge_v','cost']];ids=list(z['ids']);s=ids.index(r['start_id']);t=ids.index(r['door_id'])
  checks.append({'case':case,'method':method,'forward_bellman_violations':int((np.isfinite(ds[u])&(ds[v]>ds[u]+w+1e-7)).sum()),'reverse_bellman_violations':int((np.isfinite(dt[v])&(dt[u]>w+dt[v]+1e-7)).sum()),'ds_source':float(ds[s]),'dt_target':float(dt[t]),'best_cost_m':float(ds[t]),'source_target_dual_difference':float(ds[t]-dt[s]),'tolerance_m':1e-7,'scope':'Graph cost consistency only, no geometry admission relaxation'})
 put('runs/provenance_bindings.json',{'recorded_at':datetime.datetime.now().astimezone().isoformat(),'record_type':'POST_RUN_BINDING_NOT_RETROACTIVE_PREREGISTRATION','formal_original_runs_preserved':True,'rows':binding})
 put('results/author_distance_certificate_check.json',{'status':'PASS'if all(x['forward_bellman_violations']==0 and x['reverse_bellman_violations']==0 for x in checks)else'FAIL','rows':checks,'new_SSSP':0})
 outputs=['results/summary.json','NEW_FACE_ROUTE_RELEVANCE.csv','INTERFACE_USAGE_AUDIT.csv','ALTERNATIVE_ROUTES.csv','COUNTERFACTUAL_ANALYSIS.csv','results/counterfactual_certificates.json','results/graph_lineage.json','results/query_component_lineage.json','results/map_diagnosis.json','runs/provenance_bindings.json','results/author_distance_certificate_check.json','results/materialization_repair_audit.json','results/unconnected_face_evidence.json']
 put('results/FINALIZED.json',{'status':'DIAGNOSIS_FINALIZED_UI_PENDING','at':datetime.datetime.now().astimezone().isoformat(),'formal_calls':8,'SSSP_traversals':16,'new_SSSP_in_materialization':0,'source_scope':'Owned frozen diagnostic core only; UI and independent scripts have separate owners and later final bindings','source':[{'path':n,'sha256':sha(ROOT/n)}for n in ['src/diagnose.py','src/postprocess.py','src/refine_materialization.py','src/certificates.py','src/finalize_analysis.py','tests/test_diagnosis.py']],'files':[{'path':n,'sha256':sha(ROOT/n),'bytes':(ROOT/n).stat().st_size}for n in outputs],'UI_compaction_owner':'r2_maps; machine evidence finalized, do not replace these fields without versioned fix'})
 print('FINALIZED',len(outputs),len(checks),len(lineage),flush=True)
if __name__=='__main__':main()
