"""Read-only R1 source/response cartography; no planner or solver import."""
from pathlib import Path
import argparse,csv,io,json,hashlib,zipfile,types,sys,math,gzip,base64
from shapely.geometry import shape,mapping,LineString,Point,box
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
SHA='d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed'
CASE_KEYS=[('south','博物馆南门','APP-01','APP-02'),('north_near','北出口 · 近起点','APP-03','APP-04'),('north_far','北出口 · 远起点','APP-05','APP-06'),('library','上海图书馆登记门','APP-07','APP-08')]
MODES=['FROZEN_FULL_FACE','SOURCE_COMPLETE','EXACT_STITCH','CONDITIONAL_SEAMS']
def dump(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
class JsonStream:
 def __init__(self,path):self.f=path.open(encoding='utf-8-sig');self.buf='';self.pos=0;self.dec=json.JSONDecoder()
 def more(self):
  self.buf=self.buf[self.pos:]+self.f.read(1048576);self.pos=0
 def space(self):
  while True:
   while self.pos<len(self.buf)and self.buf[self.pos].isspace():self.pos+=1
   if self.pos<len(self.buf):return
   self.more()
   if not self.buf:raise ValueError('UNEXPECTED_JSON_EOF')
 def peek(self):self.space();return self.buf[self.pos]
 def take(self,ch):
  if self.peek()!=ch:raise ValueError('EXPECTED_JSON_TOKEN:'+ch)
  self.pos+=1
 def value(self):
  while True:
   self.space()
   try:value,end=self.dec.raw_decode(self.buf,self.pos);self.pos=end;return value
   except json.JSONDecodeError:
    before=len(self.buf)-self.pos;self.more()
    if len(self.buf)==before:raise
def stream_compact(path):
 """Parse interfaces one record at a time, never load the 200MB document."""
 stream=JsonStream(path);stream.take('{');out={};pool=[];lookup={};values=[];value_lookup={};count=0
 dynamic=['method','distance_m','in_start_component','in_goal_component','component_labels','used','forced_cost_m','slack_m','reason','accepted','entered_graph','original_entered_graph']
 shared_fields={'per_mode','source_objects','evidence_scope','original_reason'}
 def shared(v):
  h=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  if h not in value_lookup:value_lookup[h]=len(values);values.append(v)
  elif values[value_lookup[h]]!=v:raise ValueError('SHARED_VALUE_HASH_COLLISION')
  return {'__ui_pool_ref__':value_lookup[h]}
 def add(row,c):
  nonlocal count
  common={k:(shared(v)if k in shared_fields else v)for k,v in row.items()if k not in dynamic+['case']}
  h=hashlib.sha256(json.dumps(common,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  if h not in lookup:lookup[h]=len(pool);pool.append(common)
  elif pool[lookup[h]]!=common:raise ValueError('INTERFACE_POOL_HASH_COLLISION')
  metric=[lookup[h],*[row.get(k)for k in dynamic],sum(1<<i for i,k in enumerate(dynamic)if k in row)];c['interface_metrics'].append(metric)
  rebuilt={k:(values[v['__ui_pool_ref__']]if isinstance(v,dict)and set(v)=={'__ui_pool_ref__'}else v)for k,v in pool[metric[0]].items()};rebuilt['case']=c.get('id',row.get('case'))
  for i,k in enumerate(dynamic):
   if metric[-1]&(1<<i):rebuilt[k]=metric[i+1]
  if rebuilt!=row:raise ValueError('STREAM_POOL_NOT_LOSSLESS:'+str(row.get('id')))
  count+=1
 try:
  while stream.peek()!='}':
   key=stream.value();stream.take(':')
   if key!='cases':out[key]=stream.value()
   else:
    out['cases']=[];stream.take('[')
    while stream.peek()!=']':
     c={'interface_metrics':[]};stream.take('{')
     while stream.peek()!='}':
      k=stream.value();stream.take(':')
      if k=='interfaces':
       stream.take('[')
       while stream.peek()!=']':
        add(stream.value(),c)
        if stream.peek()==',':stream.take(',')
       stream.take(']')
      elif k=='modes':
       old=stream.value();c['mode_summaries']={m:{mth:{kk:vv for kk,vv in rr.items()if kk not in ['route','segments','xy']}for mth,rr in methods.items()}for m,methods in old.items()}
      else:c[k]=stream.value()
      if stream.peek()==',':stream.take(',')
     stream.take('}');out['cases'].append(c)
     if stream.peek()==',':stream.take(',')
    stream.take(']')
   if stream.peek()==',':stream.take(',')
  stream.take('}')
 finally:stream.f.close()
 out['interface_definitions']=pool;out['shared_evidence_values']=values;out['interface_metric_fields']=dynamic
 return out,{'interface_rows_compared':count,'lossless_original_field_equality':True,'solver_calls':0,'streaming_input':True,'role':'AUTHOR_UI_DATA_TRANSPORT_CHECK'}
def make_figures(payload):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.path import Path as MPath
 from matplotlib.patches import PathPatch
 from shapely.geometry.polygon import orient
 plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10,'savefig.facecolor':'#FCFAF7'})
 out=ROOT/'visuals/figures';out.mkdir(parents=True,exist_ok=True)
 def draw(ax,g,color,fill=None,ls='-',lw=.7,alpha=1):
  if g is None or g.is_empty:return
  if hasattr(g,'geoms'):
   for x in g.geoms:draw(ax,x,color,fill,ls,lw,alpha)
  elif g.geom_type=='Polygon':
   g=orient(g,sign=1)
   if fill:
    verts=[];codes=[]
    for ring in [g.exterior,*g.interiors]:
     p=list(ring.coords);verts+=p;codes+=[MPath.MOVETO]+[MPath.LINETO]*(len(p)-2)+[MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(verts,codes),facecolor=fill,edgecolor='none',alpha=alpha))
   for ring in [g.exterior,*g.interiors]:ax.plot(*zip(*ring.coords),color=color,ls=ls,lw=lw,alpha=alpha)
  elif g.geom_type in ['LineString','LinearRing']:ax.plot(*zip(*g.coords),color=color,ls=ls,lw=lw,alpha=alpha)
  elif g.geom_type=='Point':ax.scatter([g.x],[g.y],color=color,s=10)
 metadata=[]
 for c in payload['cases']:
  diag=next((x for x in payload.get('diagnosis',{}).get('cases',[])if x['id']==c['id']),{});r=c['routes'][MODES[3]]['F0'];scene=payload['scenes'][c['scene_id']];fig,ax=plt.subplots(figsize=(11,9));fig.patch.set_facecolor('#FCFAF7');ax.set_facecolor('#FFFDFC')
  for kind,color,fill in [('PARK','#D49757','#F5D9B8'),('GRASS','#B97589','#E8C7D3'),('WATER','#8177A8','#D7D3EA'),('BUILDING','#8c959d','#e2e5e8'),('RESTRICTED','#B97589','#E8C7D3'),('BARRIER','#2D3238',None)]:
   for f in scene['features']:
    if f['properties']['kind']==kind and shape(f['geometry']).intersects(box(*c['bounds'])):draw(ax,shape(f['geometry']),color,fill,alpha=.7)
  for f in scene['faces']:
   draw(ax,shape(f['omega']),'#5B9FBE','#D3EAF5',alpha=.55)
   draw(ax,shape(f['P']),'#5B9FBE'if f['old_population']else'#8177A8',ls='-'if f['old_population']else'--',lw=.9)
  for f in scene['features']:
   if f['properties']['kind']in ['ROAD','WALKWAY']and shape(f['geometry']).intersects(box(*c['bounds'])):draw(ax,shape(f['geometry']),'#70757A',ls='--'if f['properties']['kind']=='ROAD'else'-',lw=.6,alpha=.6)
  draw(ax,LineString(r['xy']).buffer(10),'#5B9FBE','#D3EAF5',alpha=.16)
  for alt in diag.get('alternatives',[]):
   if alt.get('method')=='F0'and alt.get('geometry'):draw(ax,shape(alt['geometry']),'#B97589',ls='--',lw=2.5,alpha=.8)
  for seg in r['segments']:draw(ax,LineString(seg['xy']),'#2D3238'if seg['layer']=='native'else'#5B9FBE'if seg['layer']=='derived'else'#D49757',ls='--'if seg['layer']not in ['native','derived']else'-',lw=2.5)
  start=r['xy'][0];end=r['xy'][-1];ax.scatter(*start,marker='^',s=70,c='#2D3238',zorder=9);ax.scatter(*end,marker='s',s=55,c='#FFFDFC',edgecolor='#2D3238',zorder=9)
  ax.annotate(c['start_id'],start,xytext=(7,-18),textcoords='offset points',fontsize=9,bbox={'fc':'white','alpha':.8,'ec':'none'})
  ax.annotate(c['door_id']+(' · exit仅门外'if'north'in c['id']else''),end,xytext=(7,8),textcoords='offset points',fontsize=9,bbox={'fc':'white','alpha':.8,'ec':'none'})
  b=c['bounds'];ax.set_xlim(b[0],b[2]);ax.set_ylim(b[1],b[3]);ax.set_aspect('equal');ax.ticklabel_format(style='plain',useOffset=False);ax.set_xlabel('E / m · EPSG:32651');ax.set_ylabel('N / m');ax.set_title(c['label']+'：R1四模式完整路线相同',loc='left',fontsize=18,pad=20)
  fig.text(.08,.93,'B3/F0保存路线 '+format(r['length_m'],'.2f')+' m；虚线替代线为本轮有限诊断，不修改原始P/Ω或起终点。',fontsize=10,color='#70757A')
  fig.text(.08,.045,'黑：原生路线　蓝：面派生　橙虚线：假设段　紫虚线：新面P　玫瑰虚线：本轮替代线\n© OpenStreetMap contributors · ODbL · frozen2026-11-08；10m走廊仅诊断；用户观察待定。',fontsize=9,color='#70757A')
  fig.subplots_adjust(left=.11,right=.95,bottom=.14,top=.87)
  exports=[]
  for ext in ['png','svg']:
   target=out/(c['id']+'.'+ext);fig.savefig(target,dpi=180);exports.append({'path':target.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
  plt.close(fig);metadata.append({'id':c['id'],'historical_run_id':r['run_id'],'source_response_sha256':r['source_sha256'],'outputs':exports,'route_geometry_changed':False,'corridor_used_for_routing':False})
 dump(out/'figure_manifest.json',{'role':'AUTHOR_STATIC_MAP_EXPORT','solver_calls':0,'figures':metadata,'publication_plots_skill':'Not found in listed local skill roots; standard matplotlib used','working_crs':'EPSG:32651'})
def render(payload,a):
 if a.strict and not a.diagnosis.exists():raise ValueError('DIAGNOSIS_OUTPUT_NOT_READY')
 diagnosis,check=stream_compact(a.diagnosis)if a.diagnosis.exists()else({}, {'interface_rows_compared':0,'lossless_original_field_equality':True,'solver_calls':0})
 face_csv=ROOT/'NEW_FACE_ROUTE_RELEVANCE.csv'
 if face_csv.exists():
  groups={};global_ids=set();by_query={}
  with face_csv.open(encoding='utf-8-sig',newline='')as f:
   for row in csv.DictReader(f):
    if row.get('scene_added')!='True':continue
    sid=row['source_area_id'];scene=row['record_scene_id'];key=(scene,sid);q=groups.setdefault(key,{'scene':scene,'id':sid,'distance_m':None,'query_namespace':False,'reachable_any':False,'to_goal_any':False})
    if row.get('global_unique_new')=='True':global_ids.add(sid)
    if row.get('distance_m')not in ('',None):
     v=float(row['distance_m']);q['distance_m']=v if q['distance_m']is None else min(q['distance_m'],v)
    q['query_namespace']|=row.get('in_query_scene')=='True';q['reachable_any']|=row.get('in_start_component')=='True';q['to_goal_any']|=row.get('in_goal_component')=='True'
  scene_rows=[]
  for scene in sorted({g['scene']for g in groups.values()}):
   v=[g for g in groups.values()if g['scene']==scene];dist=[g['distance_m']for g in v if g['distance_m']is not None]
   scene_rows.append({'scene_id':scene,'new_scene_records':len(v),'minimum_route_distance_m':min(dist)if dist else None,'within20m_records':sum(g['distance_m']is not None and g['distance_m']<=20 for g in v),'with_any_business_start_reachable_node':sum(g['reachable_any']for g in v),'not_loaded_by_business_scene':sum(not g['query_namespace']for g in v)})
  diagnosis['overview']={'source':'NEW_FACE_ROUTE_RELEVANCE.csv','source_sha256':hashlib.sha256(face_csv.read_bytes()).hexdigest(),'csv_flagged_unique_source_ids':len(global_ids),'scene_records':len(groups),'scene_rows':scene_rows,'interpretation':'场景记录可重复，不与82个全局身份混算。可达表示至少有节点对至少一个业务查询可达；未装载到业务图不等于现实不通。'}
 cf_path=ROOT/'results/counterfactual_certificates.json'
 if cf_path.exists():
  certificates=json.loads(cf_path.read_text(encoding='utf-8-sig'))
  diagnosis['counterfactual_binding']={'path':'results/counterfactual_certificates.json','sha256':hashlib.sha256(cf_path.read_bytes()).hexdigest(),'full_witnesses_preserved_in_source':True,'not_new_solver_calls':True}
  for c in diagnosis.get('cases',[]):
   c['counterfactuals']=[{k:v for k,v in row.items()if k not in ['witness','missing_witness_arcs']}|{'witness_arc_count':len(row.get('witness',[])),'missing_witness_arc_count':len(row.get('missing_witness_arcs',[]))}for row in certificates if row['case']==c['id']]
 if a.strict:
  cases=diagnosis.get('cases',[])
  if {c['id']for c in cases}!={c[0]for c in CASE_KEYS}:raise ValueError('FOUR_DIAGNOSED_CASES_REQUIRED')
  for c in cases:
   if not c.get('explanation'):raise ValueError('MISSING_CASE_EXPLANATION:'+c['id'])
  if not all('per_mode'in row for row in diagnosis.get('interface_definitions',[])):raise ValueError('PER_MODE_INTERFACE_EVIDENCE_NOT_READY')
 payload['diagnosis']=diagnosis;dump(ROOT/'results/map_ui.json',diagnosis);payload['strict_diagnosis_ready']=bool(a.strict);template=(ROOT/'visuals/template.html').read_text(encoding='utf-8');raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8');packed=gzip.compress(raw,compresslevel=6,mtime=0)
 if gzip.decompress(packed)!=raw:raise ValueError('GZIP_TRANSPORT_MISMATCH')
 dump(ROOT/'audits/map_payload_integrity.json',check|{'gzip_roundtrip_bytes_equal':True,'source_archive_sha256':SHA,'strict_complete_check':bool(a.strict)})
 (ROOT/'visuals/map_payload.json.gz').write_bytes(packed);dump(ROOT/'visuals/map_payload_manifest.json',{'uncompressed_bytes':len(raw),'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'gzip_bytes':len(packed),'gzip_sha256':hashlib.sha256(packed).hexdigest(),'source_archive_sha256':SHA,'lossless_transport':True,'solver_calls':0})
 (ROOT/'visuals/index.html').write_text(template.replace('__PAYLOAD__',base64.b64encode(packed).decode('ascii')),encoding='utf-8')
 print(json.dumps({'source_cases':len(payload['cases']),'source_scenes':len(payload['scenes']),'solver_calls':0,'diagnosis_ready':bool(diagnosis),'output':'visuals/index.html'}))
def main():
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,default=BASE);p.add_argument('--diagnosis',type=Path,default=ROOT/'results/map_diagnosis.json');p.add_argument('--strict',action='store_true');p.add_argument('--render-only',action='store_true');p.add_argument('--figures',action='store_true');a=p.parse_args()
 if a.render_only:
  payload=json.loads((ROOT/'visuals/source_context.json').read_text(encoding='utf-8-sig'))
  if payload['source_archive_sha256']!=SHA:raise ValueError('WRONG_CONTEXT_BASELINE')
  render(payload,a)
  if a.figures:make_figures(payload)
  return
 if hashlib.sha256(a.baseline.read_bytes()).hexdigest()!=SHA:raise ValueError('WRONG_R1_ZIP')
 with zipfile.ZipFile(a.baseline)as z:
  read=lambda n:json.loads(z.read(n).decode('utf-8-sig'))
  frozen=types.ModuleType('r2_display_frozen_native');sys.modules[frozen.__name__]=frozen;exec(compile(z.read('src/frozen_scene/native_adapter.py'),'R1:src/frozen_scene/native_adapter.py','exec'),frozen.__dict__)
  manifest=read('data/scene_manifest.json');records=list(csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))));cases=[];bindings=[];scenes={}
  for cid,label,q0,q1 in CASE_KEYS:
   routes={};corridors={}
   for mode in MODES:
    routes[mode]={}
    for method,qid in [('F0',q0),('F1',q1)]:
     row=next(r for r in records if r['request_id']==qid and r['mode']==mode);data=z.read(row['response_path']);assert hashlib.sha256(data).hexdigest()==row['response_sha256'];d=json.loads(data);sg=d['route']['segments'];xy=[]
     for s in sg:
      for pt in s['xy']:
       if not xy or pt!=xy[-1]:xy.append(pt)
     routes[mode][method]={'segments':sg,'xy':xy,'length_m':d['route']['length_m'],'cost_m':d['route']['cost_weighted_m'],'run_id':d['run_id'],'source_sha256':row['response_sha256'],'source_path':row['response_path'],'door':d['door'],'status':d['status'],'request':d['input'],'interface_ids_used':d['route']['interface_ids_used']}
     bindings.append({'path':row['response_path'],'sha256':row['response_sha256']})
   for method in ['F0','F1']:corridors[method]={str(w):mapping(LineString(routes[MODES[0]][method]['xy']).buffer(w))for w in [5,10,20]}
   ref=routes[MODES[0]]['F0'];scene=ref['request']['scene_id'];bounds=list(LineString(ref['xy']).buffer(80).bounds)
   cases.append({'id':cid,'label':label,'scene_id':scene,'start_id':ref['request']['start_id'],'door_id':ref['request']['door_id'],'bounds':bounds,'routes':routes,'corridors':corridors})
  for sid in sorted({c['scene_id']for c in cases}):
   s=next(s for s in manifest['scenes']if s['scene_id']==sid);raw=read(s['source_path']);source=frozen.Source(raw);features=[];unresolved=[];extent=box(*[min(c['bounds'][i]for c in cases if c['scene_id']==sid)if i<2 else max(c['bounds'][i]for c in cases if c['scene_id']==sid)for i in range(4)])
   for obj in [*source.ways.values(),*source.relations.values()]:
    tags=obj.get('tags',{});ident=f"{obj['type']}/{obj['id']}"
    if tags.get('highway'):continue
    area=obj['type']=='relation'and tags.get('type')=='multipolygon'or any(k in tags for k in ['building','building:part','leisure','landuse','landcover','water'])or tags.get('natural')in ['water','wetland','wood']
    try:g=source.area(ident)if area else LineString([source.projected[n]for n in obj.get('nodes',[])])if obj['type']=='way'and tags.get('barrier')and len(obj.get('nodes',[]))>=2 and all(n in source.projected for n in obj['nodes'])else None
    except Exception:g=None
    if g is None:
     if area:unresolved.append(ident)
     continue
    kind='BUILDING'if 'building'in tags or'building:part'in tags else 'RESTRICTED'if tags.get('foot',tags.get('access'))in ['no','private','customers','destination','permit','restricted']else 'GRASS'if tags.get('landuse')in ['grass','flowerbed','meadow']or tags.get('landcover')in ['grass','flowerbed']else 'WATER'if tags.get('natural')in ['water','wetland']or'water'in tags else'BARRIER'if'barrier'in tags else 'PARK'if tags.get('leisure')in ['park','garden']else'CONTEXT'
    features.append({'geometry':mapping(g),'bounds':list(g.bounds),'properties':{'id':ident,'kind':kind,'tags':tags,'source_version':obj.get('version'),'role':'RAW_SOURCE_DISPLAY_ONLY'}})
   for number,obj in source.nodes.items():
    if obj.get('tags',{}).get('barrier'):
     pt=Point(source.projected[number]);features.append({'geometry':mapping(pt),'bounds':list(pt.bounds),'properties':{'id':f'node/{number}','kind':'BARRIER','tags':obj['tags'],'role':'RAW_TAGGED_BARRIER_NODE_NOT_AUTOMATICALLY_A_BLOCK'}})
   common=read(f'data/connectivity/{sid}_full_common.json')
   for row in common['constraints']:
    if row['kind']not in ['RESTRICTED_LINEAR_ACCESS','SOURCE_RESTRICTED_ACCESS_AREA','UNKNOWN']:continue
    features.append({'geometry':row['geometry'],'bounds':list(shape(row['geometry']).bounds),'properties':{k:v for k,v in row.items()if k not in ['geometry','source_geometry']}|{'id':row['constraint_id'],'kind':'MODEL_RESTRICTION','constraint_kind':row['kind'],'role':'FROZEN_COMPUTATIONAL_CONSTRAINT_NOT_RAW_P_OR_MEASURED_WIDTH'}})
   for row in read(f'data/connectivity/{sid}_native_lines.json'):
    if row.get('geometry'):features.append({'geometry':row['geometry'],'bounds':list(shape(row['geometry']).bounds),'properties':{'id':row['source_id'],'kind':'ROAD'if row['tags'].get('highway')in ['residential','service','primary','secondary','tertiary','unclassified','trunk','living_street']else'WALKWAY','tags':row['tags'],'status':row['status'],'source_version':row.get('version'),'role':'ORIGINAL_NATIVE_LINE_CENTERLINE_NOT_ROAD_WIDTH'}})
   pop=read(f'data/connectivity/{sid}_inventory_summary.json');faces=[]
   for row in read(f'data/connectivity/{sid}_faces.json'):
    faces.append({'id':row['source_id'],'P':row['source_geometry'],'omega':row['omega'],'tags':row['tags'],'old_population':row['source_id']in pop['old_area_ids'],'status':row['status'],'role':'SOURCE_P_AND_CONSTRAINT_OMEGA_NOT_NEW_ROUTING_DOMAIN'})
   scenes[sid]={'features':features,'faces':faces,'unresolved_display_areas':unresolved,'source_sha256':s['source_sha256'],'source_path':s['source_path']}
  payload={'cases':cases,'scenes':scenes,'CRS':'EPSG:32651','source_archive_sha256':SHA,'source_time':'2026-11-08T21:21:00Z','user_observation':'PENDING_USER_OBSERVATION','screenshot_binding':'SCREENSHOT_REQUEST_UNBOUND','historical_results_only':True}
 dump(ROOT/'visuals/source_context.json',payload);dump(ROOT/'visuals/source_bindings.json',{'baseline_sha256':SHA,'display_builder_solver_calls':0,'bindings':bindings,'new_context_API':0,'unresolved_display_geometry_is_not_repaired':True})
 render(payload,a)
 if a.figures:make_figures(payload)
if __name__=='__main__':main()
