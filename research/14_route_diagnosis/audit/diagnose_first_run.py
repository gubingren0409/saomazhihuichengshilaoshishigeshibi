"""R1 frozen graph replay and finite route opportunity diagnosis. Never rebuild VG."""
from pathlib import Path
import sys,json,zipfile,csv,io,gzip,math,hashlib,time,uuid,itertools,gc
from collections import defaultdict,Counter
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'baseline_runtime'))
from src.region import STATES,polygons
from src.free_surface import partition_roads
from src.region_routing import surface_parts
from shapely.geometry import Point,LineString,shape,box,mapping
from pyproj import Transformer
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra,connected_components
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
Z=zipfile.ZipFile(ARCHIVE)
MODES=['FROZEN_FULL_FACE','SOURCE_COMPLETE','EXACT_STITCH','CONDITIONAL_SEAMS']
CASES=[('south','上海博物馆南门','APP-01','APP-02'),('north_near','北出口近起点','APP-03','APP-04'),('north_far','北出口远起点','APP-05','APP-06'),('library','上海图书馆登记门','APP-07','APP-08')]
def read(n):return json.loads(Z.read(n))
def put(p,x):
 p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
def csvout(n,rows):
 p=ROOT/n;p.parent.mkdir(exist_ok=True,parents=True)
 if not rows:return
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(dict,list,tuple))else v for k,v in r.items()})
def rows(n):return list(csv.DictReader(io.StringIO(Z.read(n).decode('utf-8-sig'))))
SAMPLES=rows('results/sample_results.csv');COMP=rows('results/component_statistics.csv');SCENES={s['scene_id']:s for s in read('data/scene_manifest.json')['scenes']}
def response(app,mode):
 r=next(x for x in SAMPLES if x['request_id']==app and x['mode']==mode)
 data=Z.read(r['response_path']);assert hashlib.sha256(data).hexdigest()==r['response_sha256'];return json.loads(data),r

def canon(s):return sys.intern(s)
def topology(desc):
 assert hashlib.sha256(Z.read(desc['path'])).hexdigest()==desc['sha256']
 ns=[];es=[]
 with gzip.GzipFile(fileobj=io.BytesIO(Z.read(desc['path'])))as stream:
  for line in stream:
   r=json.loads(line)
   if r['kind']=='node':ns.append(canon(r['id']))
   else:es.append((canon(r['u']),canon(r['v'])))
 return ns,es

def local_cells(d,common):
 p=d['planning_region'];domain=shape(p['domain']);masks={STATES[0]:shape(p['native']),STATES[1]:shape(p['assumed']),STATES[2]:shape(p['restricted'])};masks[STATES[3]]=domain.difference(masks[STATES[0]]).difference(masks[STATES[1]]).difference(masks[STATES[2]])
 roads=[x for x in common['road_centerlines']if shape(x['geometry']).intersects(domain)];cells={};k=0
 x0,y0,x1,y1=domain.bounds
 for i in range(math.floor(x0),math.ceil(x1)):
  for j in range(math.floor(y0),math.ceil(y1)):
   for state in STATES:
    parts=partition_roads(box(i,j,i+1,j+1).intersection(masks[state]),roads)
    for g in (p for part in parts for p in polygons(part.intersection(masks[state]))):
     if g.area<=1e-8:continue
     ident=canon(f'cell/{i}/{j}/{k}');k+=1;cells[ident]=tuple(g.representative_point().coords)[0]
 return cells,SimpleNamespace(domain=domain,masks=masks)

def metric_segments(coords,surface):
 cfg={'inference_cost_multiplier':1,'unknown_penalty_per_m':1,'unknown_fixed_penalty_m':0}
 ss=surface_parts(surface,LineString(coords),cfg,0,'LOCAL_SNAPSHOT')
 if ss is None:raise ValueError('LOCAL_SNAPSHOT_ARC_NOT_RESTORABLE')
 return ss

def option(ss):
 return (sum(s['length_m']for s in ss),sum(s['length_m']for s in ss if s['layer']in('inferred','assumed','unknown')),tuple(sorted({x for s in ss for x in ([s.get('source_area_id',s.get('source_id'))]+s.get('source_area_ids',[]))if x})),tuple(sorted({s['interface_id']for s in ss if s.get('interface_id')})),ss[0].get('geometry_kind','UNKNOWN')if ss else'ZERO_LENGTH_INTERFACE')

def merge(edge,key,opts):
 if key not in edge:edge[key]=opts
 else:edge[key]=list(dict.fromkeys(edge[key]+opts))

def base_graph(scene,door,d,rec):
 raw=read(SCENES[scene]['source_path']);proj=Transformer.from_crs(4326,32651,always_xy=True)
 xy={canon('node/'+str(n['id'])):proj.transform(n['lon'],n['lat'])for n in raw['elements']if n['type']=='node'}
 del raw
 path=SCENES[scene]['mapped_edges_path']
 with gzip.GzipFile(fileobj=io.BytesIO(Z.read(path)))as stream:
  for line in stream:
   r=json.loads(line)
   for n,p in zip((r['u'],r['v']),r['coordinates_metric']):xy[canon(n)]=tuple(p)
 ns,es=topology(json.loads(rec['source_topology']))
 for n in ns:
  if n not in xy and n.startswith('node/'):xy[n]=xy[n.split('@')[0]]
 if any(n not in xy for n in ns):raise ValueError('UNKNOWN_SOURCE_NODE_COORD')
 edge={(u,v):[(math.dist(xy[u],xy[v]),0.,(),(),'SOURCE_SNAPSHOT')]for u,v in es};keep=set(ns)
 common=read('data/connectivity/'+scene+'_full_common.json');cells,surface=local_cells(d,common)
 lns,les=topology(json.loads(rec['local_topology']))
 for n in lns:
  if n.startswith('cell/'):
   if n not in cells:raise ValueError('LOCAL_CELL_ID_MISSING:'+n)
   xy[n]=cells[n]
  if n not in xy:raise ValueError('LOCAL_NONCELL_COORD_MISSING:'+n)
 keep.update(lns)
 for u,v in les:
  ss=metric_segments([xy[u],xy[v]],surface)
  if not ss:ss=[{'length_m':math.dist(xy[u],xy[v]),'layer':'derived','source_id':'LOCAL_ZERO','geometry_kind':'EXACT_REGION_PORTAL'}]
  merge(edge,(u,v),[option(ss)])
 print(json.dumps({'stage':'BASE_RESTORED','scene':scene,'door':door,'nodes':len(keep),'arcs':len(edge)}),flush=True)
 return {n:xy[n]for n in keep},edge,surface,common

def apply_overlay(xy,edge,ref):
 data=Z.read(ref['path']);assert hashlib.sha256(data).hexdigest()==ref['sha256']
 with gzip.GzipFile(fileobj=io.BytesIO(data))as f:
  for line in f:
   r=json.loads(line)
   if r['kind']=='node':
    n=canon(r['id']);p=tuple(r['xy'])
    if n in xy:assert math.dist(xy[n],p)<1e-6
    else:xy[n]=p
   else:merge(edge,(canon(r['u']),canon(r['v'])),[option(ss)for ss in r.get('routing_alternatives',[r['segments']])])

def binding(xy,edge,d):
 for r in d['bindings']:
  ss=r['segments'];u=canon(r['id']);v=canon(r['attach']);xy[u]=tuple(ss[0]['xy'][0]);assert math.dist(xy[v],ss[-1]['xy'][-1])<1e-6
  o=option(ss);merge(edge,(u,v),[o]);merge(edge,(v,u),[o])

def sparse(xy,edge,method):
 ids=list(xy);idx={n:i for i,n in enumerate(ids)};pairs=list(edge);cost=np.array([min(o[0]+(method-1)*o[1]for o in edge[p])for p in pairs]);a=np.array([idx[u]for u,v in pairs]);b=np.array([idx[v]for u,v in pairs]);g=csr_matrix((cost,(a,b)),shape=(len(ids),len(ids)));return ids,idx,pairs,cost,g

def path_nodes(pred,s,t,ids):
 out=[t];seen={t}
 while out[-1]!=s:
  v=int(pred[out[-1]])
  if v<0 or v in seen:return None
  out.append(v);seen.add(v)
 return [ids[i]for i in reversed(out)]
def choose(opts,method):return min(opts,key=lambda o:(o[0]+(method-1)*o[1],o[1],o[2],o[3],o[4]))
def path_output(nodes,xy,edge,method):
 ss=[]
 for u,v in zip(nodes,nodes[1:]):
  o=choose(edge[u,v],method);ss.append({'u':u,'v':v,'xy':[xy[u],xy[v]],'length_m':o[0],'hypothesis_m':o[1],'cost_m':o[0]+(method-1)*o[1],'source_area_ids':o[2],'interface_ids':o[3],'geometry_kind':o[4]})
 return {'xy':[xy[n]for n in nodes],'segments':ss,'length_m':sum(x['length_m']for x in ss),'cost_m':sum(x['cost_m']for x in ss),'hypothesis_m':sum(x['hypothesis_m']for x in ss),'simple':len(set(nodes))==len(nodes)}
def main():
 t=time.perf_counter();ROOT.joinpath('data').mkdir(exist_ok=True);ROOT.joinpath('runs').mkdir(exist_ok=True)
 lock={'frozen_before_solver':True,'budget_start':'2026-11-12T12:29:00.200043+08:00','calls':[{'case':c,'method':m,'mode':'B3','max_alternatives':1}for c,_,_,_ in CASES for m in ['F0','F1']],
 'algorithm':'one forward and reverse SSSP per formal invocation; at most128 minimum-slack interface candidates inspected for simple forced-through path; no additional shortest path queries',
 'counterfactual':'remove option classes only; retain parallel parent options; certify unchanged optimum only if recorded old route is preserved; otherwise UNKNOWN without extra solver',
 'near_route_m':[5,10,20],'tie_cost_tolerance_m':1e-7,'tolerance_identity':'analysis of cost equality only; never geometry admission relaxation'}
 put('data/diagnosis_protocol_lock.json',lock)
 face_records=[];iface_records=[];alternative_records=[];lineage=[];casepayload=[];audit=[];runindex=[]
 allfaces={scene:read('data/connectivity/'+scene+'_faces.json')for scene in SCENES}
 oldids={scene:set()for scene in SCENES}
 # Derive scene-old identities from the frozen response, never old source inventory names.
 for scene in SCENES:
  oldids[scene]=set()
  with gzip.GzipFile(fileobj=io.BytesIO(Z.read(SCENES[scene]['mapped_edges_path'])))as f:
   for line in f:oldids[scene].add(json.loads(line)['source_area_id'])
 globally_old=set().union(*oldids.values())
 for case,label,a,b in CASES:
  d0,_=response(a,MODES[0]);scene=d0['input']['scene_id'];door=d0['door']['id'];start=d0['input']['start_id']
  rec=next(r for r in COMP if r['scene_id']==scene and r['door_id']==door and r['mode']==MODES[0])
  xy,base,surface,common=base_graph(scene,door,d0,rec);modes_payload={};mode_members={};previous_labels=None;mode_edges={};component_info={}
  payload={'id':case,'label':label,'scene_id':scene,'start_id':start,'door_id':door,'modes':modes_payload,'faces':[],'interfaces':[],'alternatives':[],'status':'RUNNING'}
  for mi,mode in enumerate(MODES):
   short='B'+str(mi);rec=next(r for r in COMP if r['scene_id']==scene and r['door_id']==door and r['mode']==mode)
   d,_=response(a,mode);ns=dict(xy);e=dict(base)
   for ref in json.loads(rec['overlays']):apply_overlay(ns,e,ref)
   assert len(ns)==int(rec['nodes'])and len(e)==int(rec['arcs']),(case,mode,len(ns),rec['nodes'],len(e),rec['arcs'])
   prep_counts=[len(ns),len(e)];binding(ns,e,d)
   ids,idx,pairs,cost,g=sparse(ns,e,1);nwc,wcc=connected_components(g,directed=True,connection='weak');nsc,scc=connected_components(g,directed=True,connection='strong')
   dsreach=np.zeros(len(ids),dtype=bool);dtreach=np.zeros(len(ids),dtype=bool)
   from scipy.sparse.csgraph import breadth_first_order
   dsreach[breadth_first_order(g,idx[start],directed=True,return_predecessors=False)]=True
   dtreach[breadth_first_order(g.T.tocsr(),idx[door],directed=True,return_predecessors=False)]=True
   owner_nodes=defaultdict(set);owner_arcs=defaultdict(list);byiface=defaultdict(set)
   for (u,v),options in e.items():
    for o in options:
     for owner in o[2]:
      owner_nodes[owner].update((u,v));owner_arcs[owner].append((u,v,o))
     for interface in o[3]:byiface[interface].add((u,v))
   labels={n:int(wcc[i])for i,n in enumerate(ids)}
   # Lineage is counted on exact common graph IDs; numeric labels are namespace-local.
   if previous_labels is not None:
    links=Counter((previous_labels[n],labels[n])for n in labels.keys()&previous_labels.keys())
    for (old,new),count in links.items():lineage.append({'case':case,'from_mode':'B'+str(mi-1),'to_mode':short,'old_component':old,'new_component':new,'common_node_count':count})
   previous_labels=labels
   component_info[short]={'nodes':len(ids),'arcs':len(pairs),'prepared_nodes':prep_counts[0],'prepared_arcs':prep_counts[1],'weak_components':int(nwc),'strong_components':int(nsc),'start_component':int(wcc[idx[start]]),'door_component':int(wcc[idx[door]]),'bindings':d['bindings']}
   mode_members[short]={'owners':{k:{'node_count':len(v),'in_start_component':any(dsreach[idx[n]]for n in v),'in_goal_component':any(dtreach[idx[n]]for n in v),'component_labels':sorted({int(wcc[idx[n]])for n in v})}for k,v in owner_nodes.items()}}
   modes_payload[short]={}
   for app,meth in [(a,'F0'),(b,'F1')]:
    hist,row=response(app,mode);coords=[p for s in hist['route']['segments']for p in s['xy']]
    modes_payload[short][meth]={'route':coords,'length_m':hist['route']['length_m'],'cost_m':hist['route']['cost_weighted_m'],'hypothesis_m':sum(s['length_m']for s in hist['route']['segments']if s['layer']in('inferred','unknown','assumed')),'run_id':hist['run_id'],'response_sha256':row['response_sha256'],'historical':True}
   if mi==3:
    edgeindex={p:i for i,p in enumerate(pairs)}
    # Complete compact graph and parallel option dump supports independent replay.
    name='data/'+case+'_query_graph.jsonl.gz'
    with gzip.open(ROOT/name,'wt',encoding='utf-8')as f:
     for n,p in ns.items():f.write(json.dumps({'kind':'node','id':n,'xy':p},separators=(',',':'))+'\n')
     for (u,v),oo in e.items():f.write(json.dumps({'kind':'arc','u':u,'v':v,'options':oo},separators=(',',':'))+'\n')
    for meth,app,method in [('F0',a,1),('F1',b,2)]:
     tick=time.perf_counter();invocation=uuid.uuid4().hex
     _,_,_,cc,gg=sparse(ns,e,method)
     ds,ps=dijkstra(gg,directed=True,indices=idx[start],return_predecessors=True);dt,pt=dijkstra(gg.T.tocsr(),directed=True,indices=idx[door],return_predecessors=True)
     best=float(ds[idx[door]]);hist,hrow=response(app,mode);err=best-hist['route']['cost_weighted_m']
     if abs(err)>1e-7:raise ValueError('THIN_GRAPH_WEIGHT_RESTORATION_MISMATCH:'+str((case,meth,best,hist['route']['cost_weighted_m'])))
     nodes=path_nodes(ps,idx[start],idx[door],ids);minimum=path_output(nodes,ns,e,method)
     np.savez_compressed(ROOT/('data/'+case+'_'+meth+'_distances.npz'),ids=np.array(ids),ds=ds,dt=dt,ps=ps,pt=pt,edge_u=np.array([idx[u]for u,v in pairs]),edge_v=np.array([idx[v]for u,v in pairs]),cost=cc)
     candidates=[]
     for interface,arcs in byiface.items():
      vals=[]
      for u,v in arcs:
       for o in e[u,v]:
        if interface not in o[3]:continue
        total=float(ds[idx[u]]+o[0]+(method-1)*o[1]+dt[idx[v]])
        if math.isfinite(total):vals.append((total,u,v,o))
      if vals:
       total,u,v,o=min(vals);candidates.append((total,interface,u,v,o))
     alternative=None
     for total,interface,u,v,o in sorted(candidates)[:128]:
      left=path_nodes(ps,idx[start],idx[u],ids);right=path_nodes(pt,idx[door],idx[v],ids)
      if left is None or right is None:continue
      combined=left+list(reversed(right))
      if len(set(combined))!=len(combined):continue
      candidate=path_output(combined,ns,e,method)
      if candidate['xy']==minimum['xy']:continue
      alternative={**candidate,'method':meth,'mode':'B3','via_interface':interface,'slack_m':candidate['cost_m']-best,'invocation_id':invocation,'meaning':'simple forced-interface alternative; not claimed second-shortest globally'};break
     if alternative:
      payload['alternatives'].append(alternative);alternative_records.append({'case':case,'method':meth,'mode':'B3','status':'FOUND_SIMPLE_ALTERNATIVE',**{k:alternative[k]for k in ['length_m','cost_m','hypothesis_m','via_interface','slack_m','invocation_id']}})
     else:alternative_records.append({'case':case,'method':meth,'mode':'B3','status':'NO_DIFFERENT_SIMPLE_PATH_IN_128_LOCKED_CANDIDATES','invocation_id':invocation,'candidate_count':len(candidates)})
     cands={i:(total,u,v,o)for total,i,u,v,o in candidates}
     evidence=hist.get('connectivity_evidence',{})
     for kind in ['interfaces','seams']:
      for it in evidence.get(kind,[]):
       ident=it['id'];arcs=byiface.get(ident,set());pts={n for p in arcs for n in p};entry=bool(arcs);reachs=any(dsreach[idx[n]]for n in pts);reacht=any(dtreach[idx[n]]for n in pts)
       value=cands.get(ident);slack=value[0]-best if value else None
       used=ident in hist['route'].get('interface_ids_used',[])
       reason=('E_REJECTED_CONSTRAINT_OR_POLICY'if not it.get('accepted')else'G_ACCEPTED_BUT_NO_ARC_OPTION_FOUND'if not entry else'B_OTHER_DIRECTED_COMPONENT'if not(reachs and reacht)else'TIED_EQUIVALENT'if slack is not None and abs(slack)<=1e-7 else'D_EXISTING_ROUTE_STRICTLY_CHEAPER'if slack is not None and slack>1e-7 else'G_UNKNOWN')
       geom=it.get('geometry');distance=shape(geom).distance(LineString(modes_payload['B3'][meth]['route']))if geom else None
       out={'case':case,'method':meth,'mode':'B3','id':ident,'record_kind':kind,'kind':it.get('kind'),'source_ids':it.get('source_ids',[]),'source_area_ids':it.get('source_area_ids',[]),'geometry':geom,'accepted':it.get('accepted'),'entered_graph':entry,'original_entered_graph':it.get('entered_graph'),'in_start_component':reachs,'in_goal_component':reacht,'component_labels':sorted({int(wcc[idx[n]])for n in pts}),'used':used,'forced_cost_m':value[0]if value else None,'slack_m':slack,'distance_m':distance,'reason':reason,'original_reason':it.get('reason'),'graph_node_ids':it.get('graph_node_ids',[]),'parent_edge':it.get('parent_edge'),'P':it.get('P'),'omega':it.get('omega'),'evidence_scope':'B3 full query graph; parent modes cannot beat this supergraph forced-cost lower bound'}
       iface_records.append(out)
       if meth=='F0':payload['interfaces'].append(out)
     # Every scene-added record is retained, with global identity flag separate.
     for record_scene,faces in allfaces.items():
      for face in faces:
       sid=face['source_id']
       if sid in oldids[record_scene]:continue
       geom=shape(face['omega']);line=LineString(modes_payload['B3'][meth]['route']);dist=geom.distance(line)if not geom.is_empty else None
       own=owner_nodes.get(sid,set())if any(f['source_id']==sid for f in allfaces[scene])else set();arr=owner_arcs.get(sid,[])if own else []
       forced=[float(ds[idx[u]]+o[0]+(method-1)*o[1]+dt[idx[v]])for u,v,o in arr];finite=[v for v in forced if math.isfinite(v)];lower=min(finite)if finite else None
       reachs=any(dsreach[idx[n]]for n in own);reacht=any(dtreach[idx[n]]for n in own)
       rr={'case':case,'method':meth,'record_scene_id':record_scene,'query_scene_id':scene,'source_area_id':sid,'scene_added':True,'global_unique_new':sid not in globally_old,'in_query_scene':record_scene==scene,'present_in_query_namespace':bool(own),'owned_node_count':len(own),'distance_m':dist,'within_5m':dist is not None and dist<=5,'within_10m':dist is not None and dist<=10,'within_20m':dist is not None and dist<=20,'intersects_route':not geom.is_empty and geom.intersects(line),'in_start_component':reachs,'in_goal_component':reacht,'component_labels':sorted({int(wcc[idx[n]])for n in own}),'forced_arc_cost_lower_bound_m':lower,'slack_lower_bound_m':lower-best if lower is not None else None,'reason':'NOT_PRESENT_IN_QUERY_NAMESPACE'if not own else'OTHER_DIRECTED_COMPONENT'if not(reachs and reacht)else'TIED_EQUIVALENT'if lower is not None and abs(lower-best)<=1e-7 else'EXISTING_ROUTE_STRICTLY_CHEAPER'if lower is not None and lower>best+1e-7 else'UNKNOWN'}
       face_records.append(rr)
       if meth=='F0'and record_scene==scene:payload['faces'].append({'id':sid,'geometry':face['omega'],'P':face['source_geometry'],**rr,'mode_memberships':{m:mode_members[m]['owners'].get(sid)for m in mode_members}})
     run={'invocation_id':invocation,'case':case,'method':meth,'mode':'B3','algorithm':'scipy directed forward and reverse Dijkstra','SSSP_traversals':2,'answer_cache':False,'start_id':start,'door_id':door,'start_xy':ns[start],'door_xy':ns[door],'minimum':minimum,'alternative':alternative,'old_response_sha256':hrow['response_sha256'],'reference_cost_error_m':err,'elapsed_s':time.perf_counter()-tick,'query_graph':name}
     put('runs/'+invocation+'.json',run);runindex.append({k:v for k,v in run.items()if k not in ['minimum','alternative']});print(json.dumps({'FORMAL':len(runindex),'case':case,'method':meth,'best':best,'alternative':alternative['cost_m']if alternative else None,'old_error':err}),flush=True)
     put('results/solver_registry.json',{'formal_invocations':runindex,'formal_count':len(runindex),'SSSP_traversals':2*len(runindex),'cap':8,'complete':False});del ds,dt,ps,pt,cc,gg;gc.collect()
   del ns,e,ids,idx,pairs,cost,g;gc.collect()
  payload['components']=component_info;payload['status']='READY';payload['explanation']='B3重新计算的最小代价与R1一致；新增接口按有向可达性和强制经过代价逐条分类，分量和走廊不等同于业务收益。';casepayload.append(payload)
  put('results/map_diagnosis.json',{'status':'RUNNING'if len(casepayload)<4 else'READY','crs':'EPSG:32651','cases':casepayload})
  csvout('NEW_FACE_ROUTE_RELEVANCE.csv',face_records);csvout('INTERFACE_USAGE_AUDIT.csv',iface_records);csvout('ALTERNATIVE_ROUTES.csv',alternative_records)
  del xy,base,surface,common;gc.collect()
 csvout('NEW_FACE_ROUTE_RELEVANCE.csv',face_records);csvout('INTERFACE_USAGE_AUDIT.csv',iface_records);csvout('ALTERNATIVE_ROUTES.csv',alternative_records)
 put('results/graph_lineage.json',{'lineage':lineage,'scope':'Exact shared node IDs between query-bound mode graphs; labels local to case/mode, not physical geography'})
 put('results/solver_registry.json',{'formal_invocations':runindex,'formal_count':len(runindex),'SSSP_traversals':2*len(runindex),'cap':8,'elapsed_s':time.perf_counter()-t})
 print('DIAGNOSIS_COMPLETE',len(runindex),flush=True)
if __name__=='__main__':main()
