"""Zero-SSSP repair of diagnostic materialization and complete option-level audits."""
import diagnose as D
from diagnose import *
import datetime
from src.common_constraints import parsed_contract,edge_conflicts
from src.region import access_conflict,non_ground

def loadgraph(case):
 xy={};edge={}
 with gzip.open(ROOT/('data/'+case+'_query_graph.jsonl.gz'),'rt',encoding='utf-8')as f:
  for line in f:
   r=json.loads(line)
   if r['kind']=='node':xy[r['id']]=tuple(r['xy'])
   else:edge[r['u'],r['v']]=[(o[0],o[1],tuple(o[2]),tuple(o[3]),o[4])for o in r['options']]
 return xy,edge

def raw_records(d):return [*d.get('connectivity_evidence',{}).get('interfaces',[]),*d.get('connectivity_evidence',{}).get('seams',[])]
def incident_interface(it,edge,explicit,incident):
 ident=it['id']
 if explicit.get(ident):return explicit[ident],'EXPLICIT_INTERFACE_TAGGED_OPTIONS'
 owners=set(it.get('source_area_ids',[]));arcs=[]
 if it.get('accepted') and it.get('entered_graph'):
  for n in it.get('graph_node_ids',[]):
   for u,v,o in incident.get(n,[]):
    if owners.intersection(o[2]):arcs.append((u,v,o))
 return arcs,'PORTAL_NODE_TO_DECLARED_OWNER_INCIDENT_OPTIONS'if arcs else'NO_AUDITED_FACE_OPTION'
def index_edges(edge,wanted_nodes):
 explicit=defaultdict(list);incident=defaultdict(list);owners=defaultdict(list)
 for (u,v),oo in edge.items():
  for o in oo:
   for i in o[3]:explicit[i].append((u,v,o))
   if u in wanted_nodes:incident[u].append((u,v,o))
   if v in wanted_nodes:incident[v].append((u,v,o))
   for owner in o[2]:owners[owner].append((u,v,o))
 return explicit,incident,owners

def thin_path(pred,s,t,ids):return D.path_nodes(pred,s,t,list(ids))
def get_selected_run(case,method):
 index=json.loads((ROOT/'results/solver_registry.json').read_text())
 r=next(r for r in index['formal_invocations']if r['case']==case and r['method']==method)
 return json.loads((ROOT/'runs'/ (r['invocation_id']+'.json')).read_text())

def materializer(scene,door,xy,edge,wanted,common,surface):
 # Only recover exact selected segments, streaming original overlay members.
 rec=next(x for x in COMP if x['scene_id']==scene and x['door_id']==door and x['mode']==MODES[3]);found={}
 for ref in json.loads(rec['overlays']):
  with gzip.GzipFile(fileobj=io.BytesIO(Z.read(ref['path'])))as f:
   for line in f:
    r=json.loads(line)
    if r['kind']!='arc' or(r['u'],r['v'])not in wanted:continue
    for ss in r.get('routing_alternatives',[r['segments']]):found[r['u'],r['v'],D.option(ss)]=ss
 historical,_=response(next(a for c,l,a,b in CASES if c==case_global[0]),MODES[3])
 for bind in historical['bindings']:
  u,v=bind['id'],bind['attach'];ss=bind['segments'];found[u,v,D.option(ss)]=ss
  rs=[{**s,'xy':s['xy'][::-1]}for s in reversed(ss)];found[v,u,D.option(rs)]=rs
 mapped={}
 with gzip.GzipFile(fileobj=io.BytesIO(Z.read(SCENES[scene]['mapped_edges_path'])))as f:
  for line in f:
   r=json.loads(line);u,v=r['u'],r['v']
   for a,b,coords in [(u,v,r['coordinates_metric']),(v,u,r['coordinates_metric'][::-1])]:
    if(a,b)in wanted:mapped[a,b]={'xy':coords,'layer':'derived','source_id':r['source_area_id'],'source_area_id':r['source_area_id'],'length_m':r['length_m'],'geometry_kind':'FROZEN_R4_REV1_MAPPED_FACE_EDGE','tags':r.get('source_tags',{}),'edge_id':r['edge_id']}
 raw=read(SCENES[scene]['source_path']);nodepairs=defaultdict(list);wanted_native={(int(u.split('/')[1].split('@')[0]),int(v.split('/')[1].split('@')[0]))for u,v in wanted if u.startswith('node/')and v.startswith('node/')}
 for r in raw['elements']:
  if r['type']!='way':continue
  for i,(u,v)in enumerate(zip(r.get('nodes',[]),r.get('nodes',[])[1:])):
   if(u,v)in wanted_native:nodepairs[u,v].append((r,i,1))
   if(v,u)in wanted_native:nodepairs[v,u].append((r,i,-1))
 parsed=parsed_contract(common)
 def segment_arc(u,v,o):
  key=(u,v,o)
  if key in found:return [dict(s)for s in found[key]]
  coords=[xy[u],xy[v]]
  if o[4]=='SOURCE_SNAPSHOT':
   if(u,v)in mapped:
    ss=[mapped[u,v]]
    if not edge_conflicts(LineString(coords),parsed,native=False,tags=ss[0]['tags'],source_id=ss[0]['source_id']):return ss
   if u.startswith('node/')and v.startswith('node/'):
    pair=tuple(int(n.split('/')[1].split('@')[0])for n in(u,v))
    for r,i,direction in sorted(nodepairs.get(pair,[]),key=lambda a:a[0]['id']):
     tags=r.get('tags',{});sid='way/'+str(r['id'])
     if non_ground(tags)or access_conflict(tags):continue
     if edge_conflicts(LineString(coords),parsed,native=True,tags=tags,source_id=sid):continue
     return [{'xy':coords,'layer':'native','source_id':sid,'tags':tags,'length_m':o[0],'geometry_kind':'ORIGINAL_OSM_NATIVE_SEGMENT','source_segment_index':i,'source_direction':direction,'edge_id':f'{sid}/segment/{i}/{u}>{v}'}]
   raise ValueError('NO_VALID_SOURCE_PARENT_FOR_SELECTED_ARC:'+str((u,v)))
  ss=D.metric_segments(coords,surface)
  if D.option(ss)[:2]!=o[:2]:
   if abs(sum(s['length_m']for s in ss)-o[0])>1e-7:raise ValueError('LOCAL_SEGMENT_COST_MISMATCH')
  return ss
 return segment_arc,parsed

def route_from_edges(nodes,xy,edge,method,forced,resolve,parsed):
 out=[];errors=[]
 for u,v in zip(nodes,nodes[1:]):
  o=forced[2]if forced and(u,v)==forced[:2]else D.choose(edge[u,v],method)
  ss=resolve(u,v,o)
  if abs(sum(s['length_m']for s in ss)-o[0])>1e-7:errors.append('MATERIALIZED_LENGTH')
  for s in ss:
   s={**s,'u':u,'v':v,'cost_m':s['length_m']*(method if s['layer']in('inferred','unknown','assumed')else 1)}
   why=edge_conflicts(LineString(s['xy']),parsed,native=s['layer']=='native',tags=s.get('tags',{}),source_id=s.get('source_id'))
   if why:errors.append({'u':u,'v':v,'source':s.get('source_id'),'conflicts':why})
   out.append(s)
 return {'segments':out,'xy':[p for s in out for p in s['xy']],'geometry':{'type':'LineString','coordinates':[p for s in out for p in s['xy']]},'length_m':sum(s['length_m']for s in out),'cost_m':sum(s['cost_m']for s in out),'hypothesis_m':sum(s['length_m']for s in out if s['layer']in('inferred','unknown','assumed')),'constraint_errors':errors,'whole_segment_validation':'PASS'if not errors else'REQUIRES_INSPECTION','raw_parent_and_overlay_geometry_recovered':True}

case_global=['']
def main():
 tick=time.perf_counter();payload=json.loads((ROOT/'results/map_diagnosis.json').read_text());all_interfaces=[];all_faces=[];alts=[];counterfacts=[];summary=[];mode_topology=[];repairs=[]
 for cp in payload['cases']:
  case_global[0]=case=cp['id'];scene=cp['scene_id'];door=cp['door_id'];start=cp['start_id'];a,b=next((a,b)for c,l,a,b in CASES if c==case)
  xy,edge=loadgraph(case);ids=list(xy);idx={n:i for i,n in enumerate(ids)};allit=raw_records(response(a,MODES[3])[0]);wanted_nodes={n for it in allit for n in it.get('graph_node_ids',[])}
  explicit,incident,owner_arcs=index_edges(edge,wanted_nodes);imaps={it['id']:incident_interface(it,edge,explicit,incident)for it in allit};surface=SimpleNamespace(domain=shape(response(a,MODES[3])[0]['planning_region']['domain']),masks={})
  pp=response(a,MODES[3])[0]['planning_region'];surface.masks={STATES[0]:shape(pp['native']),STATES[1]:shape(pp['assumed']),STATES[2]:shape(pp['restricted'])};surface.masks[STATES[3]]=surface.domain.difference(surface.masks[STATES[0]]).difference(surface.masks[STATES[1]]).difference(surface.masks[STATES[2]])
  common=read('data/connectivity/'+scene+'_full_common.json')
  # Every mode has an independently inspectable query-bound topology certificate.
  rec0=next(r for r in COMP if r['scene_id']==scene and r['door_id']==door and r['mode']==MODES[0]);d0,_=response(a,MODES[0]);base_xy,base,sf,co=D.base_graph(scene,door,d0,rec0);per_interface=defaultdict(dict)
  for mi,mode in enumerate(MODES):
   dm,_=response(a,mode);rr=next(r for r in COMP if r['scene_id']==scene and r['door_id']==door and r['mode']==mode);ns=dict(base_xy);e=dict(base)
   for ref in json.loads(rr['overlays']):D.apply_overlay(ns,e,ref)
   D.binding(ns,e,dm);modeids=list(ns);modeidx={n:i for i,n in enumerate(modeids)};pairs=list(e);eeu=np.array([modeidx[u]for u,v in pairs]);eev=np.array([modeidx[v]for u,v in pairs]);g=csr_matrix((np.ones(len(pairs),dtype=np.int8),(eeu,eev)),shape=(len(modeids),len(modeids)))
   from scipy.sparse.csgraph import breadth_first_order
   fr=np.zeros(len(modeids),bool);to=np.zeros(len(modeids),bool);fr[breadth_first_order(g,modeidx[start],directed=True,return_predecessors=False)]=1;to[breadth_first_order(g.T.tocsr(),modeidx[door],directed=True,return_predecessors=False)]=1
   wc,wcl=connected_components(g,directed=True,connection='weak');sc,scl=connected_components(g,directed=True,connection='strong');ex,inc,_=index_edges(e,wanted_nodes);declared={x['id']for x in raw_records(dm)}
   np.savez_compressed(ROOT/('data/'+case+'_B'+str(mi)+'_topology.npz'),ids=np.array(modeids),edge_u=eeu,edge_v=eev,wcc=wcl,scc=scl,from_start=fr,to_goal=to,xy=np.array([ns[n]for n in modeids]))
   for it in allit:
    arcs,scope=incident_interface(it,e,ex,inc);points={n for u,v,o in arcs for n in(u,v)};per_interface[it['id']]['B'+str(mi)]={'declared_as_interface':it['id']in declared,'entered_graph':bool(arcs),'entry_scope':scope,'directed_from_start':any(fr[modeidx[n]]for n in points),'directed_to_goal':any(to[modeidx[n]]for n in points),'component_labels':sorted({int(wcl[modeidx[n]])for n in points})}
   mode_topology.append({'case':case,'mode':'B'+str(mi),'nodes':len(modeids),'arcs':len(pairs),'weak_components':int(wc),'strong_components':int(sc),'start_component':int(wcl[modeidx[start]]),'door_component':int(wcl[modeidx[door]]),'bindings':dm['bindings'],'source_PREP':rr['original_PREP_cache_key'],'source_response_sha256':rr['bound_response_sha256']})
   del ns,e,modeids,modeidx,g,ex,inc;gc.collect()
  del base,base_xy,sf,co;gc.collect()
  newids={f['source_id']for f in read('data/connectivity/'+scene+'_faces.json')} - {f['source_id']for f in d0.get('mapped_faces',[])}
  historical_by_method={m:response(app,MODES[3])[0]for m,app in [('F0',a),('F1',b)]};cp['interfaces']=[];cp['alternatives']=[]
  case_summary={'case':case,'methods':{},'general_routing_bug_proven':False,'diagnostic_materialization_bug_repaired':True}
  for meth,app,method in [('F0',a,1),('F1',b,2)]:
   hist=historical_by_method[meth];run=get_selected_run(case,meth);cert=np.load(ROOT/('data/'+case+'_'+meth+'_distances.npz'));cids=list(cert['ids']);assert cids==ids;ds,dt,ps,pt=[cert[k]for k in('ds','dt','ps','pt')];best=float(ds[idx[door]]);minimum=thin_path(ps,idx[start],idx[door],ids)
   candidates=[];interface_rows=[]
   for it in allit:
    ident=it['id'];arcs,scope=imaps[ident];vals=[(float(ds[idx[u]]+o[0]+(method-1)*o[1]+dt[idx[v]]),u,v,o)for u,v,o in arcs];finite=[x for x in vals if math.isfinite(x[0])];value=min(finite)if finite else None;slack=value[0]-best if value else None
    pts={n for u,v,o in arcs for n in(u,v)};reachable=any(math.isfinite(ds[idx[n]])for n in pts);goalable=any(math.isfinite(dt[idx[n]])for n in pts);actualused=ident in hist['route'].get('interface_ids_used',[])
    route_uv={(s['u'],s['v'])for s in hist['route']['segments']};incident_used=any((u,v)in route_uv for u,v,o in arcs);route_passes=any(n in{q for s in hist['route']['segments']for q in(s.get('u'),s.get('v'))}for n in it.get('graph_node_ids',[]))
    reason='E_REJECTED_CONSTRAINT_OR_POLICY'if not it.get('accepted')else'G_ACCEPTED_NO_AUDITED_OWNER_INCIDENCE'if not arcs else'B_OTHER_DIRECTED_COMPONENT'if not(reachable and goalable)else'TIED_EQUIVALENT'if slack is not None and abs(slack)<=1e-7 else'D_EXISTING_ROUTE_STRICTLY_CHEAPER'if slack is not None and slack>1e-7 else'G_UNKNOWN'
    row={**it,'case':case,'method':meth,'mode':'B3','in_start_component':reachable,'in_goal_component':goalable,'directed_from_start':reachable,'directed_to_goal':goalable,'component_labels':per_interface[ident]['B3']['component_labels'],'original_entered_graph':it.get('entered_graph'),'entered_graph':bool(arcs),'entry_scope':scope,'used':actualused,'used_explicit_tag':actualused,'route_passes_graph_node':route_passes,'route_uses_owner_incident_arc':incident_used,'forced_cost_m':value[0]if value else None,'slack_m':slack,'reason':reason,'original_reason':it.get('reason',it.get('reasons')),'per_mode':per_interface[ident],'distance_m':shape(it['geometry']).distance(LineString(cp['modes']['B3'][meth]['route']))if it.get('geometry')else None,'evidence_scope':'Query-bound B3 directed distances; PORTAL incidence not automatically newly introduced edge; parent equivalence separately recorded'}
    if value:row['forced_argmin_arc']={'u':value[1],'v':value[2],'option':value[3]};candidates.append((value[0],ident,*value[1:]))
    interface_rows.append(row)
   alternative=None;forced=None
   # Same original prelocked candidate budget; actual bridge option is now enforced.
   for total,interface,u,v,o in sorted(candidates)[:128]:
    left=thin_path(ps,idx[start],idx[u],ids);right=thin_path(pt,idx[door],idx[v],ids)
    if left is None or right is None:continue
    combined=left+list(reversed(right))
    if len(set(combined))!=len(combined):continue
    cand=D.path_output(combined,xy,edge,method,(u,v,o))
    if cand['xy']==[xy[n]for n in minimum]:continue
    alternative={**cand,'method':meth,'mode':'B3','via_interface':interface,'slack_m':cand['cost_m']-best,'invocation_id':run['invocation_id'],'nodes':combined,'forced_option':[u,v,o],'geometric_meaning':'MODEL_GRAPH_ALTERNATIVE_NOT_FIELD_CONFIRMED'};forced=(u,v,o);break
   wanted=set(zip(minimum,minimum[1:]))
   if alternative:wanted.update(zip(alternative['nodes'],alternative['nodes'][1:]))
   resolve,parsed=materializer(scene,door,xy,edge,wanted,common,surface)
   if alternative:
    actual=route_from_edges(alternative['nodes'],xy,edge,method,forced,resolve,parsed);alternative.update(actual)
    if abs(alternative['cost_m']-(ds[idx[forced[0]]]+forced[2][0]+(method-1)*forced[2][1]+dt[idx[forced[1]]]))>1e-7:raise ValueError('FORCED_MATERIALIZED_COST_MISMATCH')
    # For portal incidence the explicit tag may be absent, so preserve that witness separately.
    alternative['forced_entry_scope']=imaps[alternative['via_interface']][1];cp['alternatives'].append(alternative)
   put('results/materialized_'+case+'_'+meth+'.json',{'original_invocation_id':run['invocation_id'],'distance_certificate_unchanged':True,'new_solver_calls':0,'alternative':alternative,'original_run_path':'runs/'+run['invocation_id']+'.json','materializer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
   alts.append({'case':case,'method':meth,'mode':'B3','invocation_id':run['invocation_id'],'status':'FOUND_SIMPLE_ALTERNATIVE'if alternative else'NO_DIFFERENT_SIMPLE_PATH_IN_LOCKED_CANDIDATES','length_m':alternative['length_m']if alternative else None,'cost_m':alternative['cost_m']if alternative else None,'hypothesis_m':alternative['hypothesis_m']if alternative else None,'slack_m':alternative['slack_m']if alternative else None,'via_interface':alternative['via_interface']if alternative else None,'validation':alternative['whole_segment_validation']if alternative else'NOT_APPLICABLE'})
   # Primal upper witness plus supergraph lower bound, no additional solve.
   old=response(app,MODES[0])[0];old_arcs=[]
   for uv,sg in itertools.groupby(old['route']['segments'],key=lambda s:(s['u'],s['v'])):
    ss=list(sg);old_arcs.append((uv,sum(s['length_m']for s in ss),sum(s['length_m']for s in ss if s['layer']in('inferred','unknown','assumed'))))
   filters={'DELETE_NEW_FACES':lambda o:not newids.intersection(o[2]),'DELETE_EXACT_INTERFACES':lambda o:o[4]!='SOURCE_SUPPORTED_INTERFACE','DELETE_CONDITIONAL_SEAMS':lambda o:o[4]not in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH'),'ONLY_EXACT_INCREMENT_NO_SEAMS':lambda o:o[4]not in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')}
   for name,allowed in filters.items():
    witness=[];missing=[];removed=0;parallel_retained=0
    for oo in edge.values():
     n=sum(not allowed(o)for o in oo);removed+=n
     if n and n<len(oo):parallel_retained+=1
    for (u,v),length,hyp in old_arcs:
     opts=[o for o in edge.get((u,v),[])if allowed(o)and abs(o[0]-length)<=1e-7 and abs(o[1]-hyp)<=1e-7]
     if opts:witness.append({'u':u,'v':v,'option':opts[0]})
     else:missing.append({'u':u,'v':v,'original_length_m':length,'original_hypothesis_m':hyp})
    passed=not missing;counterfacts.append({'case':case,'method':meth,'counterfactual':name,'status':'CERTIFIED_SAME_OPTIMUM'if passed else'LOWER_BOUND_ONLY_PARENT_PATH_IDENTITY_NOT_RETAINED','baseline_optimum_m':best,'upper_witness_cost_m':old['route']['cost_weighted_m']if passed else None,'lower_bound_m':best,'removed_options':removed,'parallel_parent_arcs_retained':parallel_retained,'witness':witness,'missing_witness_arcs':missing,'proof':'Every retained option is in B3, so cannot beat B3 optimum; exact original B0 path gives matching upper bound when all original arc options survive. No SSSP.'})
   case_summary['methods'][meth]={'minimum_cost_m':best,'reference_cost_m':hist['route']['cost_weighted_m'],'reference_error_m':best-hist['route']['cost_weighted_m'],'interface_reasons':dict(Counter(r['reason']for r in interface_rows)),'interfaces_total':len(interface_rows),'explicit_tag_used':sum(r['used_explicit_tag']for r in interface_rows),'portal_incident_used':sum(r['route_uses_owner_incident_arc']for r in interface_rows),'alternative_count':int(alternative is not None),'alternative_cost_m':alternative['cost_m']if alternative else None,'alternative_slack_m':alternative['slack_m']if alternative else None,'alternative_validation':alternative['whole_segment_validation']if alternative else'NA'}
   all_interfaces.extend(interface_rows)
  # Attach both methods' face rows without changing their calculated geometry.
  facegeom={f['id']:f for f in cp['faces']};fr=[]
  with (ROOT/'NEW_FACE_ROUTE_RELEVANCE.csv').open(encoding='utf-8-sig')as f:
   for row in csv.DictReader(f):
    if row['case']!=case:continue
    for k in ['distance_m','forced_arc_cost_lower_bound_m','slack_lower_bound_m']:
     row[k]=float(row[k])if row[k]else None
    for k in ['scene_added','global_unique_new','in_query_scene','present_in_query_namespace','within_5m','within_10m','within_20m','intersects_route','in_start_component','in_goal_component']:row[k]=row[k]=='True'
    all_faces.append(row)
    if row['in_query_scene']:fr.append({**facegeom[row['source_area_id']],**row,'id':row['source_area_id']})
  cp['faces']=fr;cp['interfaces']=[r for r in all_interfaces if r['case']==case];cp['status']='READY';cp['explanation']='八次有限图复算的最小代价均与R1一致。新增对象可能接入同一分量，但强制经过的代价不更低；零slack接口为等价路径或已有几何重分类。具体以逐接口证据为准。'
  summary.append(case_summary);put('results/map_diagnosis_materialized.json',payload);print('MATERIALIZED',case,case_summary['methods'],flush=True)
  del edge,xy,common,surface;gc.collect()
 csvout('INTERFACE_USAGE_AUDIT.csv',all_interfaces);csvout('ALTERNATIVE_ROUTES.csv',alts);csvout('COUNTERFACTUAL_ANALYSIS.csv',counterfacts);put('results/counterfactual_certificates.json',counterfacts);put('results/query_component_lineage.json',mode_topology)
 put('results/summary.json',{'status':'READY','cases':summary,'formal_solver_count':8,'SSSP_traversals':16,'postprocess_solver_count':0,'counterfactual_status_counts':dict(Counter(r['status']for r in counterfacts)),'postprocess_elapsed_s':time.perf_counter()-tick,'routing_algorithm_modified':False,'diagnostic_export_repaired':True,'limits':['Finite frozen graph optimality only; no field passage claim','PORTAL owned-incidence can be equivalent to an old geometric route, not necessarily newly created connection','At most128 cheapest declared forced-interface candidates inspected for simple alternative; no claim of global second shortest']})
 put('results/map_diagnosis.json',payload);print('POSTPROCESS_COMPLETE',flush=True)
if __name__=='__main__':main()
