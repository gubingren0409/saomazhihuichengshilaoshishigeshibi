"""Real source vectors and newly computed result figures; no generated imagery."""
from pathlib import Path
import json,csv,collections,sys,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PatchPolygon
from matplotlib.lines import Line2D
from shapely.geometry import shape,LineString,Point
ROOT=Path(__file__).resolve().parents[1];Q2=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';Q6=ROOT/'Q6-LOCAL-MAP-CONSISTENCY-R1';Q7=ROOT/'Q7-DYNAMIC-CLOSURE-SIMULATION-R1'
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':9,'svg.fonttype':'none'})
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def table(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig')))
def state_output(idx,state,repeat=0):
 scene='sh-huangpu-01'if idx==0 else'sh-library';row=next(r for r in table(Q7/'dynamic_route_results.csv')if r['scene_id']==scene and r.get('state')==state and r.get('repeat')==str(repeat)and r.get('control_variant')=='STATE_INJECTION_ADAPTER');return read(Q7/row['output_file'])
contexts=[read(Q2/f'outputs/context_{i}.geojson')for i in range(3)]
colors={'building':'#d4cec1','grass':'#bed5b3','walkable_area':'#f3e0a6','water':'#aedce7','barrier':'#ad3f40','private':'#c887a9'}
def geom(ax,g,color,fill=True,linewidth=.7,**kw):
 edgecolor=kw.pop('edgecolor',color)
 if g.geom_type in ('Polygon','MultiPolygon'):
  for p in g.geoms if g.geom_type=='MultiPolygon'else[g]:
   ax.add_patch(PatchPolygon(list(p.exterior.coords),facecolor=color if fill else'none',edgecolor=edgecolor,linewidth=linewidth,**kw))
   for ring in p.interiors:ax.add_patch(PatchPolygon(list(ring.coords),facecolor='#fbfaf5',edgecolor=color,linewidth=.4))
 elif g.geom_type in ('LineString','MultiLineString'):
  for p in g.geoms if g.geom_type=='MultiLineString'else[g]:
   x,y=p.xy;ax.plot(x,y,color=color,lw=linewidth,**kw)
def base(ax,c,bounds=None):
 ax.set_facecolor('#fbfaf5')
 for f in c['features']:
  props=f['properties'];category=props['category'];tags=props.get('tags',{});g=shape(f['geometry'])
  if category=='line':
   h=tags.get('highway');walk=h in ('footway','path','steps','pedestrian','crossing');col='#678579'if walk else'#b0a799';geom(ax,g,col,linewidth=1 if walk else 1.6)
  else:geom(ax,g,colors.get(category,'#dedbd1'),edgecolor='#666'if props.get('target')else colors.get(category,'#aaa'),linewidth=1 if props.get('target')else.6)
 ax.scatter(*c['start_xy'],marker='s',c='#284b83',s=28,zorder=8);ax.scatter(*c['door_xy'],marker='*',c='#b32831',edgecolor='white',s=110,zorder=10)
 b=bounds or c['bounds'];ax.set_xlim(b[0],b[2]);ax.set_ylim(b[1],b[3]);ax.set_aspect('equal');ax.ticklabel_format(style='plain',useOffset=False);ax.tick_params(labelsize=6)
 width=b[2]-b[0];bar=20 if width<200 else 50;x=b[0]+width*.06;y=b[1]+(b[3]-b[1])*.06;ax.plot([x,x+bar],[y,y],c='#333',lw=2);ax.text(x,y+4,f'{bar} m',fontsize=7)
def route(ax,r,color=None):
 if not r:return
 for s in r['segments']:
  layer=s['layer'];col=color or('#116a87'if layer=='native'else'#db8720'if layer=='derived'else'#b43591');geom(ax,LineString(s['xy']),col,linewidth=2.3,linestyle='--'if layer in('inferred','unknown','assumed')else'-',zorder=7)
def save(fig,path):
 fig.text(.08,-.018,'© OpenStreetMap contributors · ODbL · 冻结地图来源；计算/模拟结果不是现场通行证明',fontsize=7,color='#53615b')
 path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path.with_suffix('.png'),dpi=170,bbox_inches='tight');fig.savefig(path.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)
titles=['上海博物馆南门 main','上海博物馆北出口 exit（仅到门外）','上海图书馆登记门']
viewer=[]
for i,c in enumerate(contexts):
 fig,axs=plt.subplots(1,3,figsize=(15,5.4));variants=[]
 for ax,kind,label in zip(axs,['REGISTERED_DOOR','BUILDING_CENTROID','NATIVE_OUTSIDE_APPROACH_POINT'],['登记门','建筑中心（内部对照点）','最近合格原生接近点']):
  x=read(Q2/f'outputs/Q2-TARGET-{i}-{kind}.json');base(ax,c);route(ax,x['route']);lock=read(Q2/f'outputs/targets_locked_{i}.json');target=next(v for k,v in lock['targets']if k==kind);xy=target['xy']if target else c['door_xy'];ax.scatter(*xy,marker='o',facecolor='none',edgecolor='#d5572c',s=75,zorder=11)
  row=x['row'];length=row['route_length_m'];ax.set_title(f'{label}\n{row["status"]}'+(f' · {length:.2f} m'if length is not None else''));variants.append({'kind':kind,'label':label,'row':row,'route':x['route'],'target_xy':xy})
 fig.suptitle(titles[i]+'｜同一起点、数据与 F1 成本；条件路线，不是现场通行证明',fontsize=12);fig.text(.08,.015,'灰：建筑 / 绿：草地 / 黄：登记步行面 / 细线：原始线（含道路轴） / 蓝：原生路线 / 橙：面派生 / 紫虚线：假设段 / 红星：原登记门',fontsize=8)
 save(fig,Q2/f'figures/entry_targets_{i}');viewer.append({'title':titles[i],'context':c,'variants':variants})
scenarios=read(Q7/'dynamic_scenarios.json')['cases']
for j,case in enumerate(scenarios):
 idx=0 if case['scene_id']=='sh-huangpu-01'else 2;c=contexts[idx];fig,axs=plt.subplots(2,3,figsize=(14,10))
 baseline=state_output(idx,'S0')['route'];closed=next(s for s in baseline['segments']if s.get('edge_id')==case['selected_native_edge_id'])
 for n,ax in enumerate(axs.flat):
  x=state_output(idx,f'S{n}');base(ax,c);route(ax,x['route']);
  if n in(2,4):geom(ax,LineString(closed['xy']),'#c33131',linewidth=4,linestyle='--',zorder=9)
  if n==3:geom(ax,shape(case['obstacle']),'#d84848',alpha=.6)
  if n in(1,4):ax.scatter(*c['door_xy'],marker='x',c='#111',s=120,zorder=12)
  ax.set_title(f'S{n} · '+['正常','关门','删除原生边','合成临时障碍','门与边同时关闭','恢复'][n]+f' · {x["row"]["status"]}')
 fig.suptitle(titles[idx]+'｜本轮状态适配器：实际路线/NO_PATH；条件结果，不代表现场通行',fontsize=12);fig.text(.08,.015,'每状态实际重复3次，图示第1次；原APP不处理封闭参数的失败负控另见报告。',fontsize=9);save(fig,Q7/f'figures/closure_states_{idx}')
 center=LineString(closed['xy']).interpolate(.5,normalized=True);bounds=[center.x-18,center.y-18,center.x+18,center.y+18];fig,axs=plt.subplots(1,3,figsize=(13,4.6))
 for ax,n in zip(axs,[0,2,3]):
  x=state_output(idx,f'S{n}');base(ax,c,bounds);route(ax,x['route'])
  if n==2:geom(ax,LineString(closed['xy']),'#c33131',linewidth=4,linestyle='--',zorder=9)
  if n==3:geom(ax,shape(case['obstacle']),'#c33131',alpha=.6,zorder=9)
  ax.set_title(f'S{n} · {x["row"]["status"]}')
 fig.suptitle(titles[idx]+'｜具体断边/合成障碍局部；红色是实验状态，非现场事实');save(fig,Q7/f'figures/closure_detail_{idx}')
if(Q7/'secondary_results/A0_dynamic_scenarios.json').exists():
 old=read(Q7/'secondary_results/A0_dynamic_scenarios.json')['cases'][0];new=scenarios[0];base_route=state_output(0,'S0')['route'];fig,axs=plt.subplots(1,2,figsize=(12,6))
 for ax,case,title in zip(axs,[old,new],['首版：住宅道路轴压力测试（不满足原生步道条件）','修正：按源标签选择合格 footway（求解器不变）']):
  base(ax,contexts[0]);s=next(s for s in base_route['segments']if s.get('edge_id')==case['selected_native_edge_id']);geom(ax,LineString(s['xy']),'#c33131',linewidth=4,zorder=12);ax.set_title(title+'\n'+s['source_id']+' / '+s['tags'].get('highway',''))
 fig.suptitle('两版封闭对象不同，不能把结果变化称为算法优化');save(fig,Q7/'figures/intervention_correction')
fig,ax=plt.subplots(figsize=(10,2.5));ax.axis('off')
for k,t in enumerate(['S0 正常','S1 关门','S2 断边','S3 障碍','S4 关门+断边','S5 恢复']):
 ax.text(k,0,t,ha='center',bbox={'boxstyle':'round,pad=.6','facecolor':'#edf2eb','edgecolor':'#54776b'})
 if k<5:ax.annotate('',xy=(k+.7,0),xytext=(k+.3,0),arrowprops={'arrowstyle':'->'})
ax.set_xlim(-.7,5.7);ax.set_ylim(-1,1);ax.set_title('状态逐个由 S0 图构造，非累计修改；S5 与 S0 比较几何签名');save(fig,Q7/'figures/state_transition_figure')
# Q6 uses the exact source nodes underlying the 377 reported restoration rows.
sys.path.insert(0,str(ROOT/'frozen_runtime'))
from src.frozen_scene.native_adapter import Source
manifest=read(ROOT/'frozen_runtime/data/scene_manifest.json');sources={s['scene_id']:Source(read(ROOT/'frozen_runtime'/s['source_path']))for s in manifest['scenes']}
restored=table(Q6/'restored_native_edges.csv');lines=[]
for r in restored:
 wid=int(r['source_id'].split('/')[1]);source=next(s for s in sources.values()if wid in s.ways);a,b=json.loads(r['native_nodes']);lines.append(LineString([source.projected[a],source.projected[b]]))
fig,ax=plt.subplots(figsize=(8,7));base(ax,contexts[0]);ax.set_title('Q6 ① 源对象：真实博物馆街区\n保留建筑、草地、登记面、道路与步道的不同身份');save(fig,Q6/'figures/01_source_objects')
fig,ax=plt.subplots(figsize=(9,7));
for g in lines:geom(ax,g,'#168877',linewidth=1.1)
ax.set_aspect('equal');ax.ticklabel_format(style='plain',useOffset=False);ax.set_title('Q6 ② 377条恢复片段的原生几何\n754是有向弧声明数；没有把草地面整体开放');ax.set_xlabel('EPSG:32651 / m');save(fig,Q6/'figures/02_restored_native_admission')
faces=table(Q6/'added_face_usage.csv');fig,ax=plt.subplots(figsize=(10,7));facegeo=[]
for r in faces:
 for sid in json.loads(r['source_scenes']):
  g=sources[sid].area(r['source_id'])
  if g is not None:break
 if g is None:continue
 evidence=json.loads(r['business_case_evidence']);start=any(z.get('in_start_component')=='True'for z in evidence);goal=any(z.get('in_goal_component')=='True'for z in evidence);both=any(z.get('in_start_component')=='True'and z.get('in_goal_component')=='True'for z in evidence)
 col='#2c9977'if both else'#cf9e38'if r['in_business_face_pool']=='True'else'#bbc2ca';geom(ax,g,col,alpha=.65);facegeo.append({'type':'Feature','geometry':json.loads(json.dumps(g.__geo_interface__)),'properties':{'source_id':r['source_id'],'business_pool':r['in_business_face_pool'],'saved_start_component':start,'saved_goal_component':goal,'same_record_start_and_goal_component':both,'reason_set':r['reason_set']}})
ax.set_aspect('equal');ax.ticklabel_format(style='plain',useOffset=False);ax.set_title('Q6 ③ 新增82个源面及保存的业务分量证据\n灰=业务池外 / 黄=池内 / 绿=某业务记录中同属起终分量；未重建历史SCC');save(fig,Q6/'figures/03_saved_components')
(Q6/'outputs/added_faces_visual.geojson').write_text(json.dumps({'type':'FeatureCollection','features':facegeo},ensure_ascii=False),encoding='utf-8')
fig,ax=plt.subplots(figsize=(8,7));base(ax,contexts[0]);route(ax,read(Q2/'outputs/Q2-TARGET-0-REGISTERED_DOOR.json')['route']);ax.set_title('Q6 ④ 同一冻结来源上的本轮路线分层\n蓝=原生（可能是道路轴） / 橙=面派生 / 紫虚线=假设');save(fig,Q6/'figures/04_source_and_new_route')
data={'scenes':viewer,'dynamic':scenarios};(ROOT/'figures/viewer_data.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
print('REAL_FIGURES_COMPLETE',len(list(ROOT.rglob('figures/*.png'))))
