"""Independent option-incidence/slack, finite alternatives and deletion certificates."""
from pathlib import Path
import json,csv,gzip,math,collections,hashlib,gc,zipfile,io,argparse
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
def structured(r,key,default):
    v=r.get(key,'');return json.loads(v)if v else default
def yes(v):return str(v).lower()=='true'
def key(o):return(o[0],o[1],tuple(o[2]),tuple(o[3]),o[4])
def main():
    registry=json.loads((ROOT/'results/solver_registry.json').read_text());counterfacts=json.loads((ROOT/'results/counterfactual_certificates.json').read_text());summary=[];errors=[]
    with zipfile.ZipFile(ARCHIVE)as z:
        samples=list(csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))))
        for case,app in [('south','APP-01'),('north_near','APP-03'),('north_far','APP-05'),('library','APP-07')]:
            scene=next(r for r in samples if r['request_id']==app)['scene_id'];faces=json.loads(z.read('data/connectivity/'+scene+'_faces.json'));old=json.loads(z.read(next(r for r in samples if r['request_id']==app and r['mode']=='FROZEN_FULL_FACE')['response_path']));newids={r['source_id']for r in faces}-{r['source_id']for r in old.get('mapped_faces',[])}
            rows=[];wanted=set()
            with(ROOT/'INTERFACE_USAGE_AUDIT.csv').open(encoding='utf-8-sig',newline='')as f:
                for r in csv.DictReader(f):
                    if r['case']==case:
                        rows.append(r);wanted.update(structured(r,'graph_node_ids',[]))
            xy={};edges={};explicit=collections.defaultdict(list);incident=collections.defaultdict(list)
            with gzip.open(ROOT/f'data/{case}_query_graph.jsonl.gz','rt',encoding='utf-8')as f:
                for line in f:
                    r=json.loads(line)
                    if r['kind']=='node':xy[r['id']]=r['xy'];continue
                    u,v=r['u'],r['v'];edges[u,v]=r['options']
                    for o in r['options']:
                        for ident in o[3]:explicit[ident].append((u,v,o))
                        if u in wanted:incident[u].append((u,v,o))
                        if v in wanted:incident[v].append((u,v,o))
            for method in('F0','F1'):
                factor=1 if method=='F0'else 2;run=next(r for r in registry['formal_invocations']if r['case']==case and r['method']==method);cert=np.load(ROOT/f'data/{case}_{method}_distances.npz',allow_pickle=False);ids=cert['ids'].tolist();index={n:i for i,n in enumerate(ids)};ds,dt=cert['ds'],cert['dt'];best=float(ds[index[run['door_id']]]);ncheck=0;counts=collections.Counter();maxerr=0.;bad=[]
                appid=f'APP-{int(app.split("-")[1])+(method=="F1"):02d}';history=json.loads(z.read(next(r for r in samples if r['request_id']==appid and r['mode']=='CONDITIONAL_SEAMS')['response_path']));ev=history.get('connectivity_evidence',{});raw_interfaces=collections.defaultdict(list)
                for raw in[*ev.get('interfaces',[]),*ev.get('seams',[])]:raw_interfaces[raw['id']].append(raw)
                owned_used=explicit_used=0
                for r in rows:
                    if r['method']!=method:continue
                    ident=r['id'];matches=[a for a in raw_interfaces[ident]if a.get('graph_node_ids',[])==structured(r,'graph_node_ids',[])and a.get('source_area_ids',[])==structured(r,'source_area_ids',[])];raw=matches[0]if matches else raw_interfaces[ident][0];arcs=explicit.get(ident,[])
                    if yes(r['accepted'])!=bool(raw.get('accepted'))or yes(r['original_entered_graph'])!=bool(raw.get('entered_graph'))or structured(r,'source_area_ids',[])!=raw.get('source_area_ids',[])or structured(r,'graph_node_ids',[])!=raw.get('graph_node_ids',[]):bad.append([ident,'FROZEN_RAW_INTERFACE_FIELDS'])
                    if not arcs and raw.get('accepted')and raw.get('entered_graph'):
                        owners=set(raw.get('source_area_ids',[]));arcs=[(u,v,o)for n in raw.get('graph_node_ids',[])for u,v,o in incident.get(n,[])if owners.intersection(o[2])]
                    actual_explicit=ident in history['route'].get('interface_ids_used',[])
                    owners=set(raw.get('source_area_ids',[]));portals=set(raw.get('graph_node_ids',[]))
                    if owners:
                        actual_owned=any((not portals or s.get('u')in portals or s.get('v')in portals)and owners.intersection([s.get('source_area_id',s.get('source_id'))]+s.get('source_area_ids',[]))for s in history['route']['segments'])
                    else:
                        pairs={(u,v)for u,v,o in arcs};actual_owned=any((s.get('u'),s.get('v'))in pairs for s in history['route']['segments'])
                    if actual_explicit!=yes(r['used_explicit_tag'])or actual_owned!=yes(r['route_uses_owner_incident_arc']):bad.append([ident,'ACTUAL_SELECTED_OPTION_OWNER_USE'])
                    owned_used+=actual_owned;explicit_used+=actual_explicit
                    pts={n for u,v,o in arcs for n in(u,v)};reachable=any(math.isfinite(ds[index[n]])for n in pts);goalable=any(math.isfinite(dt[index[n]])for n in pts)
                    totals=[float(ds[index[u]]+o[0]+(factor-1)*o[1]+dt[index[v]])for u,v,o in arcs];finite=[v for v in totals if math.isfinite(v)];forced=min(finite)if finite else None
                    if yes(r['entered_graph'])!=bool(arcs)or yes(r['directed_from_start'])!=reachable or yes(r['directed_to_goal'])!=goalable:bad.append([ident,'INCIDENCE_OR_REACH'])
                    observed=float(r['forced_cost_m'])if r['forced_cost_m']else None
                    if (observed is None)!=(forced is None):bad.append([ident,'FORCED_NULL'])
                    elif forced is not None:
                        residual=max(abs(observed-forced),abs(float(r['slack_m'])-(forced-best)));maxerr=max(maxerr,residual)
                        if residual>1e-7:bad.append([ident,'FORCED_SLACK',residual])
                        arg=structured(r,'forced_argmin_arc',{});u,v,o=arg['u'],arg['v'],arg['option']
                        if not any(u==a and v==b and key(o)==key(p)for a,b,p in arcs)or abs(ds[index[u]]+o[0]+(factor-1)*o[1]+dt[index[v]]-forced)>1e-7:bad.append([ident,'ARGMIN_IDENTITY'])
                    counts[r['reason']]+=1;ncheck+=1
                materialized=json.loads((ROOT/f'results/materialized_{case}_{method}.json').read_text());alternative=materialized['alternative'];altinfo=None
                if alternative:
                    nodes=alternative['nodes'];forced=alternative['forced_option'];cost=length=hyp=0.;segments=alternative['segments'];flat=[p for s in segments for p in s['xy']]
                    if len(set(nodes))!=len(nodes)or nodes[0]!=run['start_id']or nodes[-1]!=run['door_id']:bad.append(['ALT_SIMPLE_ENDPOINT'])
                    grouped=[]
                    for s in segments:
                        if grouped and grouped[-1][0]==(s['u'],s['v']):grouped[-1][1].append(s)
                        else:grouped.append(((s['u'],s['v']),[s]))
                    if [uv for uv,ss in grouped]!=list(zip(nodes,nodes[1:])):bad.append(['ALT_ARC_ORDER'])
                    if any(math.dist(a['xy'][-1],b['xy'][0])>1e-8 for a,b in zip(segments,segments[1:])):bad.append(['ALT_SEGMENT_CONTINUITY'])
                    for (u,v),ss in grouped:
                        l=sum(sum(math.dist(a,b)for a,b in zip(s['xy'],s['xy'][1:]))for s in ss);h=sum(s['length_m']for s in ss if s['layer']in('inferred','unknown','assumed'));opts=edges[u,v]
                        if not any(abs(o[0]-l)<=1e-7 and abs(o[1]-h)<=1e-7 for o in opts):bad.append(['ALT_OPTION_WEIGHT',u,v])
                        if math.dist(ss[0]['xy'][0],xy[u])>1e-8 or math.dist(ss[-1]['xy'][-1],xy[v])>1e-8:bad.append(['ALT_ARC_XY'])
                        if(u,v)==tuple(forced[:2])and(abs(l-forced[2][0])>1e-7 or abs(h-forced[2][1])>1e-7):bad.append(['FORCED_MATERIALIZED_PARALLEL_OPTION'])
                        length+=l;hyp+=h;cost+=l+(factor-1)*h
                    expect=ds[index[forced[0]]]+forced[2][0]+(factor-1)*forced[2][1]+dt[index[forced[1]]]
                    if max(abs(cost-alternative['cost_m']),abs(length-alternative['length_m']),abs(hyp-alternative['hypothesis_m']),abs(cost-expect),abs(cost-best-alternative['slack_m']))>1e-7:bad.append(['ALT_COST_SLACK'])
                    if math.dist(flat[0],run['start_xy'])>1e-8 or math.dist(flat[-1],run['door_xy'])>1e-8:bad.append(['ALT_ORIGINAL_ENDPOINT_COORD'])
                    altinfo={'length_m':length,'hypothesis_m':hyp,'cost_m':cost,'slack_m':cost-best,'segments':len(segments),'via_interface':alternative['via_interface'],'forced_entry_scope':alternative['forced_entry_scope']}
                filters={'DELETE_NEW_FACES':lambda o:not newids.intersection(o[2]),'DELETE_EXACT_INTERFACES':lambda o:o[4]!='SOURCE_SUPPORTED_INTERFACE','DELETE_CONDITIONAL_SEAMS':lambda o:o[4]not in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH'),'ONLY_EXACT_INCREMENT_NO_SEAMS':lambda o:o[4]not in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')};cfinfo=[]
                for r in counterfacts:
                    if r['case']!=case or r['method']!=method:continue
                    allowed=filters[r['counterfactual']];removed=sum(not allowed(o)for oo in edges.values()for o in oo);parallel=sum(any(not allowed(o)for o in oo)and any(allowed(o)for o in oo)for oo in edges.values());w=r['witness'];total=0.
                    if removed!=r['removed_options']or parallel!=r['parallel_parent_arcs_retained']:bad.append(['COUNTERFACTUAL_FILTER_COUNTS',r['counterfactual']])
                    for a,b in zip(w,w[1:]):
                        if a['v']!=b['u']:bad.append(['COUNTERFACTUAL_CONTINUITY'])
                    if not w or w[0]['u']!=run['start_id']or w[-1]['v']!=run['door_id']:bad.append(['COUNTERFACTUAL_ENDPOINT'])
                    for arc in w:
                        o=arc['option']
                        if not allowed(o)or not any(key(o)==key(p)for p in edges.get((arc['u'],arc['v']),[])):bad.append(['COUNTERFACTUAL_WITNESS_OPTION'])
                        total+=o[0]+(factor-1)*o[1]
                    if max(abs(total-r['upper_witness_cost_m']),abs(total-best),abs(best-r['lower_bound_m']))>1e-7:bad.append(['COUNTERFACTUAL_OPTIMAL_CERTIFICATE'])
                    cfinfo.append({'filter':r['counterfactual'],'removed_options':removed,'parallel_parent_arcs_retained':parallel,'retained_primal_cost_m':total,'certified_optimum_m':best})
                summary.append({'case':case,'method':method,'interface_rows_checked':ncheck,'interface_reason_counts':dict(counts),'selected_owner_incident_used':owned_used,'selected_explicit_tag_used':explicit_used,'max_forced_slack_residual_m':maxerr,'alternative':altinfo,'counterfactuals':cfinfo,'errors':bad});errors.extend([[case,method,*b]for b in bad]);cert.close()
            del xy,edges,incident,explicit;gc.collect()
    out={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'interface_csv_sha256':hashlib.sha256((ROOT/'INTERFACE_USAGE_AUDIT.csv').read_bytes()).hexdigest(),'new_solver_calls':0,'new_SSSP_calls':0,'status':'PASS_FOR_OPTION_OPPORTUNITIES_ALTERNATIVES_AND_DELETION_CERTIFICATES'if not errors else'REQUIRES_INSPECTION','rows':summary,'errors':errors,'scope':'Independent arithmetic and graph-option provenance bound to frozen raw interface declarations and actual historical selected owner-labelled segments; forced costs are shortest walks, selected exported alternatives additionally simple. Optimality limited to frozen finite graph and fixed bindings. Exact-increment-no-seams is same topology as deletion of seams, not a separate solver experiment. Alternative raw obstacle geometry checked separately.'}
    (ROOT/'audits/independent_opportunity_certificates.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':out['status'],'rows':len(summary),'interfaces':sum(r['interface_rows_checked']for r in summary),'counterfactuals':sum(len(r['counterfactuals'])for r in summary),'errors':errors[:30]},ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,default=ARCHIVE);ARCHIVE=ap.parse_args().baseline;main()
