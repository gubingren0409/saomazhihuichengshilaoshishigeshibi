"""One preregistered zero-solver materialization correction; retained original certificates."""
import postprocess as P
from postprocess import *
import shutil

def cases_stream(path):
 dec=json.JSONDecoder();buf='';started=False
 with path.open(encoding='utf-8')as f:
  while not started:
   buf+=f.read(65536);k=buf.find('"cases":[')
   if k>=0:buf=buf[k+9:];started=True
  while True:
   buf=buf.lstrip(' \n\r,')
   if buf.startswith(']'):return
   try:value,end=dec.raw_decode(buf)
   except json.JSONDecodeError:
    more=f.read(1048576)
    if not more:raise
    buf+=more;continue
   buf=buf[end:];yield value

def history_uses_owner(hist,it,arcs):
 pairs={(u,v)for u,v,o in arcs};owners=set(it.get('source_area_ids',[]))
 return any((s.get('u'),s.get('v'))in pairs and owners.intersection(D.option([s])[2])for s in hist['route']['segments'])

def main():
 prior=json.loads((ROOT/'results/summary.json').read_text());prior_summary=ROOT/'audit/materialization_phase1_summary.json';prior_summary.write_text(json.dumps(prior,ensure_ascii=False,indent=2),encoding='utf-8')
 shutil.copyfile(ROOT/'ALTERNATIVE_ROUTES.csv',ROOT/'audit/ALTERNATIVE_ROUTES_phase1.csv')
 summary_by={r['case']:r for r in prior['cases']};altrows=[];case_summaries=[];audit=[];interfacestream=[]
 out=(ROOT/'results/map_diagnosis_refined.json').open('w',encoding='utf-8');out.write('{"status":"READY","crs":"EPSG:32651","cases":[');first=True
 for cp in cases_stream(ROOT/'results/map_diagnosis.json'):
  P.case_global[0]=case=cp['id'];scene=cp['scene_id'];door=cp['door_id'];start=cp['start_id'];xy,edge=P.loadgraph(case);ids=list(xy);idx={n:i for i,n in enumerate(ids)}
  common=read('data/connectivity/'+scene+'_full_common.json');a,b=next((a,b)for c,l,a,b in CASES if c==case);hist0,_=response(a,MODES[3]);pp=hist0['planning_region'];surface=SimpleNamespace(domain=shape(pp['domain']),masks={STATES[0]:shape(pp['native']),STATES[1]:shape(pp['assumed']),STATES[2]:shape(pp['restricted'])});surface.masks[STATES[3]]=surface.domain.difference(surface.masks[STATES[0]]).difference(surface.masks[STATES[1]]).difference(surface.masks[STATES[2]])
  raw=read(SCENES[scene]['source_path']);source_meta={r['type']+'/'+str(r['id']):{k:r.get(k)for k in ['type','id','version','timestamp','tags']}for r in raw['elements']};del raw
  cp['alternatives']=[]
  for meth,app,method in [('F0',a,1),('F1',b,2)]:
   hist,_=response(app,MODES[3]);cert=np.load(ROOT/('data/'+case+'_'+meth+'_distances.npz'));ds,dt,ps,pt=[cert[k]for k in ['ds','dt','ps','pt']];best=float(ds[idx[door]]);minimum=P.thin_path(ps,idx[start],idx[door],ids);minimum_line=LineString([xy[n]for n in minimum]);rr=[r for r in cp['interfaces']if r['method']==meth]
   candidates=[]
   for row in rr:
    row['source_objects']=[source_meta.get(s,{'id':s,'source_status':'DERIVED_OR_UNRESOLVED'})for s in sorted(set(row.get('source_ids',[])+row.get('source_area_ids',[])))]
    arg=row.get('forced_argmin_arc')
    if arg:
     o=arg['option'];o=(o[0],o[1],tuple(o[2]),tuple(o[3]),o[4]);candidates.append((row['forced_cost_m'],row['id'],arg['u'],arg['v'],o))
     row['route_uses_owner_incident_arc']=P.history_uses_owner(hist,row,[(arg['u'],arg['v'],o)]) if row.get('entry_scope')=='EXPLICIT_INTERFACE_TAGGED_OPTIONS' else row['route_uses_owner_incident_arc']
    # Exact ownership use is checked against actual historical selected segments,
    # never merely a matching (u,v) that may select another parallel option.
    if row.get('source_area_ids'):
     owners=set(row['source_area_ids']);nodes=set(row.get('graph_node_ids',[]))
     row['route_uses_owner_incident_arc']=any((not nodes or s.get('u')in nodes or s.get('v')in nodes)and owners.intersection(D.option([s])[2])for s in hist['route']['segments'])
   seen=set();counts=Counter();alternative=None;candidate_evidence=[]
   for total,interface,u,v,o in sorted(candidates):
    key=(u,v,o[0],o[1],o[2],o[4])
    if key in seen:counts['duplicate_bridge_option']+=1;continue
    seen.add(key);counts['unique_bridge_options']+=1
    left=P.thin_path(ps,idx[start],idx[u],ids);right=P.thin_path(pt,idx[door],idx[v],ids)
    if left is None or right is None:counts['unreachable']+=1;continue
    nodes=left+list(reversed(right))
    if len(set(nodes))!=len(nodes):counts['non_simple_forced_walk']+=1;continue
    if LineString([xy[n]for n in nodes]).equals(minimum_line):counts['current_primal_geometry']+=1;continue
    counts['distinct_noncurrent_simple_candidates']+=1;candidate_evidence.append({'interface':interface,'u':u,'v':v,'option':o,'forced_cost_m':total})
    forced=(u,v,o);wanted=set(zip(nodes,nodes[1:]));resolve,parsed=P.materializer(scene,door,xy,edge,wanted,common,surface)
    actual=P.route_from_edges(nodes,xy,edge,method,forced,resolve,parsed)
    if abs(actual['cost_m']-total)>1e-7:raise ValueError('FORCED_PATH_COST_DIFFERS_FROM_LOCKED_OPTION')
    if actual['constraint_errors']:raise ValueError('ALTERNATIVE_WHOLE_SEGMENT_CONFLICT:'+str(actual['constraint_errors'][:2]))
    alternative={**actual,'nodes':nodes,'simple':True,'method':meth,'mode':'B3','via_interface':interface,'forced_option':[u,v,o],'slack_m':actual['cost_m']-best,'invocation_id':P.get_selected_run(case,meth)['invocation_id'],'forced_entry_scope':next(r['entry_scope']for r in rr if r['id']==interface),'geometric_meaning':'NEAR_EQUIVALENT_MODEL_GRAPH_PATH'if actual['cost_m']-best<.01 else'HIGHER_COST_MODEL_GRAPH_ALTERNATIVE','candidate_rule_lock':'data/materialization_repair_lock.json'}
    break
   if alternative:cp['alternatives'].append(alternative)
   run=P.get_selected_run(case,meth)
   result={'case':case,'method':meth,'mode':'B3','invocation_id':run['invocation_id'],'distance_certificate_unchanged':True,'new_solver_calls':0,'materializer_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'candidate_counts':dict(counts),'candidate_evidence':candidate_evidence,'alternative':alternative}
   put('results/materialized_'+case+'_'+meth+'.json',result);audit.append({k:v for k,v in result.items()if k not in ['candidate_evidence','alternative']})
   altrows.append({'case':case,'method':meth,'mode':'B3','status':'FOUND_SIMPLE_ALTERNATIVE'if alternative else'NO_NONCURRENT_SIMPLE_ALTERNATIVE_IN_FINITE_CANDIDATES','invocation_id':run['invocation_id'],'length_m':alternative['length_m']if alternative else None,'cost_m':alternative['cost_m']if alternative else None,'hypothesis_m':alternative['hypothesis_m']if alternative else None,'slack_m':alternative['slack_m']if alternative else None,'via_interface':alternative['via_interface']if alternative else None,'validation':'PASS'if alternative else'NOT_APPLICABLE','candidate_counts':dict(counts)})
   sm=summary_by[case]['methods'][meth];sm.update(alternative_count=int(alternative is not None),alternative_cost_m=alternative['cost_m']if alternative else None,alternative_slack_m=alternative['slack_m']if alternative else None,alternative_validation='PASS'if alternative else'NA',portal_incident_used=sum(r['route_uses_owner_incident_arc']for r in rr),candidate_counts=dict(counts))
  if not first:out.write(',')
  json.dump(cp,out,ensure_ascii=False,separators=(',',':'));first=False
  interfacestream.extend(cp['interfaces']);case_summaries.append(summary_by[case]);print('REFINED',case,flush=True)
  del cp,xy,edge,common,surface,cert,source_meta,rr;gc.collect()
 out.write(']}');out.close()
 D.csvout('INTERFACE_USAGE_AUDIT.csv',interfacestream);D.csvout('ALTERNATIVE_ROUTES.csv',altrows);put('results/materialization_repair_audit.json',{'actual_postprocess_time':datetime.datetime.now().astimezone().isoformat(),'rows':audit,'solver_calls':0,'original_8_runs_untouched':True,'old_summary_snapshot':'audit/materialization_phase1_summary.json','repair_lock':'data/materialization_repair_lock.json'})
 prior['cases']=case_summaries;prior['refinement']='Prelocked single zero-SSSP bridge deduplication and forced option correction complete';prior['source_weight_independent_proof']='audits/independent_source_weight_restoration.json';put('results/summary.json',prior)
 # Final replacement is atomic; no reader sees a half-written payload.
 (ROOT/'results/map_diagnosis_refined.json').replace(ROOT/'results/map_diagnosis.json')
 print('REFINEMENT_COMPLETE',flush=True)
if __name__=='__main__':main()
