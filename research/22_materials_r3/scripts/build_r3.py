"""Material composition and drawing from saved geometry. No solver calls."""
from pathlib import Path
import ast,csv,hashlib,html,json,shutil,zipfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch,FancyBboxPatch,PathPatch
from matplotlib.path import Path as MPath
from shapely.geometry import shape
from shapely.geometry.polygon import orient
from shapely.ops import transform
from pyproj import Transformer
R=Path(__file__).resolve().parents[1];P=R/'package'
def rd(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def sh(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def text(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf8')
def table(p,rs,fields=None):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields or list(rs[0]));w.writeheader();w.writerows(rs)
sources=rows(P/'evidence/SOURCE_INDEX.csv')
def addfile(src,dst,stage,archive_sha,member,identity='FROZEN_MEMBER_UNCHANGED'):
 dst=P/dst;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 rel=dst.relative_to(P).as_posix()
 if not any(x['package_file']==rel for x in sources):sources.append(dict(source_id=stage+'::'+member,experiment=stage,version='FINAL_OR_EXPLICIT_HISTORICAL',package_file=rel,archive_sha256=archive_sha,archive_member=member,sha256=sh(dst),bytes=dst.stat().st_size,identity=identity))
 return dst
hist=R/'working/history'
for r in rows(hist/'source_index.csv'):
 n=r['member'];stage=r['stage']
 if n.endswith(('.md','.py')) or n.startswith('config/') or n in ['STATUS.json','runs/experiment.json','runs/summary.json','runs/geometry/sh-huangpu-01.geojson','data/ir/sh-huangpu-01.local.json','data/entrance_approach.json','data/routes.geojson','data/source/sh-huangpu-01.osm.json','config/method.json','config/experiment.json']:
  assert sh(Path(r['local_path']))==r['sha256']
  addfile(Path(r['local_path']),'sources/'+stage+'/'+n,stage,r['archive_sha256'],n)
text(P/'corrections/R4_AND_REV1_HISTORICAL_CORRECTION.md',(hist/'R4_AND_REV1_HISTORICAL_CORRECTION.md').read_text(encoding='utf8').replace('`history_evidence.csv`','`R4_REV1_EVIDENCE.csv`'))
he=rows(hist/'history_evidence.csv')
for r in he:r['source_path']='sources/'+r['stage']+'/'+r['source_file']
table(P/'corrections/R4_REV1_EVIDENCE.csv',he)

free=R/'working/freespace'
for r in rows(free/'SOURCE_MANIFEST.csv'):
 assert sh(free/r['relative_path'])==r['sha256']
 addfile(free/r['relative_path'],'sources/FREE_SPACE_FINAL/'+r['relative_path'],'FREE_SPACE_FINAL',r['fixed_archive_sha256'],r['member'],r['role'])
for name in ['verified_evidence.json','normalized_primary_queries.csv','normalized_region_metrics.csv','free_space_numbers.csv','F0_F1_saved_graph_identity_check.csv','FULL_QUERY_INPUT_PREDICTION_SHA_CHECK.csv','FULL_QUERY_LINEAGE_COMPLETION.json']:
 addfile(free/name,'08_free_space_inference/'+name,'R3_READ_ONLY_EXTRACTION','1d4110a76d0e5006f5c518366d82d6fb1aa98c8e46bac6956b2b0dbd91ccc77a',name,'DERIVED_TABLE_FROM_FROZEN_RESULTS_NO_SOLVER')
for f in (free/'external_receipts').glob('*'):
 if f.is_file():addfile(f,'sources/FREE_SPACE_FINAL/external_receipts/'+f.name,'FREE_SPACE_FINAL_RECEIPT','OUTSIDE_SEALED_ZIP',f.name,'HISTORICAL_EXTERNAL_RECEIPT')

# Retain R2's original origin mapping, not just its containing material archive identity.
origin={x['package_path']:x for x in rows(P/'prior/R2_selected/SOURCE_MANIFEST.csv')}
for s in sources:
 if s['experiment']=='MATERIALS_R2':
  key=s['archive_member'];o=origin.get(key)
  if o:s['version']='ORIGIN='+o['source_experiment']+'; ARCHIVE='+o['fixed_archive_sha256']+'; MEMBER='+o['original_member']

def find(pattern):return next(P.glob(pattern))
scene=rd(P/'prior/R2_selected/sources/reconstruction/scene.json')
features=[f for f in scene['features'] if f.get('geometry') and 'algorithm' not in ' '.join(f.get('families',[])).lower()]
target=next(f for f in features if f['source_id']=='way/161090899')
proj=Transformer.from_crs(4326,32651,always_xy=True).transform
south=proj(121.4712158,31.2299607);north=proj(121.4706605,31.2305674)
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':11,'figure.facecolor':'#fcfbf7','axes.facecolor':'#fcfbf7','svg.fonttype':'none'})
# Reuse only the archived map-artist function definitions; never import/execute the R2 build module.
with zipfile.ZipFile(P/'prior/PG1_MIDTERM_RESEARCH_MATERIALS_R2.zip') as zz:oldcode=zz.read('scripts/build_materials.py').decode('utf-8-sig')
tree=ast.parse(oldcode)
for node in tree.body:
 if isinstance(node,ast.FunctionDef) and node.name in ['drawgeom','basemap','save']:exec(compile(ast.Module(body=[node],type_ignores=[]),'<frozen-map-artists>','exec'))

events=[
('E01','corrections/event_02_corrected','线网失败，广场却已被识别','R4','CORE_RESEARCH'),
('E02','corrections/event_05_revised','R4→REV1：从源线门禁转向边缘派生网络','R4-REV1','CORE_RESEARCH'),
('E03','materials/03_north_exit','北出口7.95米：区域约束不等于通行证据','NORTH-ACCESS-R1','CORE_RESEARCH'),
('E04','materials/04_grass_fix','草地背景不能抹去已有原生步道','WALKABILITY-R2','CORE_RESEARCH'),
('E05','materials/05_positive_evidence','正向证据恢复：上下文确有使用，但收益有限','WALKABILITY-R4-CONTEXT','CORE_RESEARCH'),
('E06','08_free_space_inference','F0/F1：未知事实与条件规划许可分开','FREE-SPACE-R1-FINAL','CORE_RESEARCH'),
('E07','materials/07_full_face','从3米边缘带到完整合法步行面','PEDESTRIAN-AREA-SHORTEST-R1-FINAL','CORE_RESEARCH'),
('E08','materials/08_local_business','局部连通改善不等于完整业务路线收益','PED-AREA-CONNECTIVITY-R2','CORE_RESEARCH'),
('E09','supplementary/street_side_R0_R1_R2','街区侧R0/R1/R2：逻辑侧别与条件通道','PG1-RESUME-STREET-SIDE-R1','SUPPLEMENTARY_RESEARCH / LATER_EXPLORATION'),
('E10','supplementary/system_integration','已知门原型、动态适配器与冷热性能','E2E-R1-FIXED + SUPPLEMENTARY-20261115','SUPPLEMENTARY_SYSTEM_INTEGRATION'),
('E11','materials/11_current_stage','典型开发场景之后：适用性与独立证据仍待验证','CURRENT_RESEARCH_SCOPE','SYNTHESIS_NOT_EXPERIMENT')]
for _,p,*_ in events:(P/p).mkdir(parents=True,exist_ok=True)
figs=[];numbers=[];claims=[]
def rel(p):return p.relative_to(P).as_posix()
def cat(eid,p,inputs,kind='REDRAW_FROM_FROZEN_GEOMETRY',grade='PRESENTATION_GRADE_FIGURE',note=''):
 stage=next(x[3] for x in events if x[0]==eid)
 figs.append(dict(figure_id=eid+'-'+p.stem,event_id=eid,title=next(x[2] for x in events if x[0]==eid),package_file=rel(p),figure_role='main' if p.stem=='main_figure' else 'supplement',figure_type=kind,presentation_status=grade,source_experiment=stage,source_files=';'.join(rel(x) for x in inputs),original_to_redraw=kind,sha256=sh(p),scope_and_limit=note))
def copyfig(eid,src,name='main_figure',note=''):
 folder=P/next(x[1] for x in events if x[0]==eid);dest=folder/(name+'.png');shutil.copyfile(src,dest)
 if src.with_suffix('.svg').is_file():shutil.copyfile(src.with_suffix('.svg'),dest.with_suffix('.svg'))
 cat(eid,dest,[src],'ORIGINAL_RESULT_REUSED',note=note)
 return dest
def r2fig(eid,old,name='main_figure',oldname='main_figure',note=''):
 return copyfig(eid,find('prior/R2_selected/'+old+'/'+oldname+'.png'),name,note)
def number(eid,label,value,unit,src,field,denom,query,version,limit='冻结地图与条件规划；非现场通行或泛化证明'):
 s=next((s for s in sources if s['package_file']==rel(src)),None)
 numbers.append(dict(event_id=eid,metric=label,value=value,unit=unit,experiment=next(e[3] for e in events if e[0]==eid),version=version,query_or_endpoints=query,denominator=denom,source_file=rel(src),source_field=field,fixed_archive_sha256=s['archive_sha256'] if s else 'DERIVED_FROM_BOUND_SOURCES',source_sha256=sh(src),limitation=limit))

# Pure B0 graphic: draw saved B0 edges, never historical Geoapify/diagnostic route features.
geom=P/'sources/R4/runs/geometry/sh-huangpu-01.geojson';gg=rd(geom)
ir=P/'sources/R4/data/ir/sh-huangpu-01.local.json';ird=rd(ir)
ap=ird['access_candidates'][0];near=proj(*ap['coordinate']);gap=ap['distance_to_request_target_m']
rev=P/'sources/REV1/data/entrance_approach.json';rv=rd(rev)
# selected record is also available in the original summary.
revsummary=P/'sources/REV1/runs/summary.json';rs=rd(revsummary);selected=rs['south_selected']
revroutes=P/'sources/REV1/data/routes.geojson';rr=rd(revroutes)
bounds=[354185,3455985,354485,3456300]
def b0draw(ax):
 basemap(ax,bounds)
 for f in gg['features']:
  if f['properties']['kind']=='b0_network':drawgeom(ax,transform(proj,shape(f['geometry'])),ec='#286b8a',lw=1.6,z=10)
 ax.scatter(*near,s=40,color='#ad4866',zorder=30);ax.plot([near[0],south[0]],[near[1],south[1]],ls='--',color='#c9583b',lw=1.4,zorder=30)
 ax.annotate('最近合格线网接近点\n不是门，也不是成功终点',near,xytext=(15,15),textcoords='offset points',fontsize=9,zorder=35,bbox={'fc':'#fffd','ec':'none'})
 ax.text(.02,.98,'建筑 way/161090899｜南门 node/6897141353\n南广场 relation/2385771 已识别',transform=ax.transAxes,va='top',fontsize=8,zorder=40,bbox={'fc':'#fffd','ec':'none'})
 ax.text(.02,.02,'红虚线：55.022米测距线，不可当作通路\nB0严格南门：NO_ROUTE',transform=ax.transAxes,fontsize=9,zorder=40,bbox={'fc':'#fff','ec':'none'})
fig,ax=plt.subplots(figsize=(9,9));b0draw(ax);ax.set_title('原南门存在，但B0原生网络没有可用入口图节点',pad=14)
save(fig,P/events[0][1]/'main_figure.png','源：R4保存b0_network；无B3、无托管路线、无伪造到门折线；EPSG:32651米；© OpenStreetMap contributors')
cat('E01',P/events[0][1]/'main_figure.png',[geom,ir],note='B3对本馆不适用；测距线与路由边分开。')
r2fig('E01','01_problem_definition','optional_figure',note='真实完整街区原始地图上下文，不是算法成功图')
fig,axs=plt.subplots(1,2,figsize=(15,8));b0draw(axs[0]);axs[0].set_title('R4：面已识别，严格源线策略新增0边')
basemap(axs[1],bounds)
for f in gg['features']:
 if f['properties']['kind']=='b0_network':drawgeom(axs[1],transform(proj,shape(f['geometry'])),ec='#286b8a',lw=1.1,z=10,alpha=.55)
for f in rr['features']:
 pr=f['properties']
 if pr.get('route_id')!=selected['route_id']:continue
 kind=pr.get('kind');color={'NATIVE_LINEAR':'#286b8a','DERIVED_FROM_TAGGED_PEDESTRIAN_AREA':'#925ab3','DERIVED_TERMINAL_CONNECTOR':'#d66b36'}.get(kind,'#777')
 drawgeom(axs[1],transform(proj,shape(f['geometry'])),ec=color,lw=2,z=20)
axs[1].set_title('REV1：3米边缘派生接通原南门')
axs[1].text(.03,.02,'同一起点、同一原门；完整保存路线1067.371米\n原生+面派生+0.700米门前端口；残差0',transform=axs[1].transAxes,fontsize=9,zorder=40,bbox={'fc':'white','ec':'none'})
save(fig,P/'corrections/R4_SOUTH_PLAZA_BEFORE_AFTER.png','蓝：B0原生网/路线；紫：面派生；橙：门前端口；红虚线仅测距。同底图同范围；图为末段局部、数值为完整原请求；© OSM contributors；未现场核验')
for ext in ['.png','.svg']:shutil.copyfile(P/('corrections/R4_SOUTH_PLAZA_BEFORE_AFTER'+ext),P/events[1][1]/('main_figure'+ext))
cat('E02',P/events[1][1]/'main_figure.png',[geom,ir,revroutes,revsummary],note='仅重绘保存选定路线；没有重算、换起点或换门')
r2fig('E02','06_south_plaza_connection','optional_figure',oldname='optional_figure')
number('E01','南广场原生面积',5880.020892024015,'m²',geom,'features[kind=open_space].area_m2','1个已登记面','relation/2385771','R4')
number('E01','南门到原合格线网接近点',gap,'m',ir,'access_candidates[0].distance_to_request_target_m','1个原南门','node/6897141353→way/178719573','R4')
for field in ['length_m','gap_m']:
 number('E02','选定条件路线'+field,selected[field],'m',revsummary,'south_selected.'+field,'三个实际接点尝试中2个合格','node/1890935454→node/6897141353','REV1')
number('E02','门前派生端口',selected['section_lengths_m']['DERIVED_TERMINAL_CONNECTOR'],'m',revsummary,'south_selected.section_lengths_m.DERIVED_TERMINAL_CONNECTOR','同一选定路线','node/6897141353','REV1')

for eid,old in [('E03','08_north_exit_conditional_access'),('E04','07_native_walkway_grass_fix'),('E07','09_full_face_routing'),('E08','10_local_vs_business_gain'),('E11','11_current_stage')]:
 r2fig(eid,old);src=P/'prior/R2_selected'/old/'optional_figure.png'
 if src.exists():copyfig(eid,src,'optional_figure')
 if eid=='E11':r2fig(eid,'01_problem_definition','optional_figure',oldname='optional_figure')

context_report=find('sources/HANDOFF_R1/source_materials/experiment_reports/WALKABILITY-R4-CONTEXT/RESULTS*')
fig,axs=plt.subplots(1,2,figsize=(13,6))
for ax,vals,title,unit in [(axs[0],[.77,.92],'同一G80输入：七面参考覆盖率','%'),(axs[1],[20,20],'同一G80输入：33条正例可达数量','条')]:
 ax.bar(['冻结M0','上下文M1'],vals,color=['#77949f','#37867b'],width=.5)
 for j,v in enumerate(vals):ax.text(j,v,f'{v}{unit}',ha='center',va='bottom',fontsize=15)
 ax.set_title(title,pad=16);ax.set_ylim(0,max(vals)*1.3);ax.spines[['top','right']].set_visible(False)
save(fig,P/events[4][1]/'main_figure.png','原R4-CONTEXT合同；固定30米评分域；0新增可达正例。此处M1不是统一约束后的M1-C，也不是F0/F1。')
cat('E05',P/events[4][1]/'main_figure.png',[context_report],'REDRAW_SAVED_REPORT_STATISTICS',note='同一任务内M0/M1比较；不跨强遮蔽与几何缺标拼接')
ctxpng=next(p for p in (P/'sources/HANDOFF_R1/figures').rglob('03-m0-m1-comparison*.png'))
copyfig('E05',ctxpng,'optional_figure',note='保留细粒度上下文诊断图，仅作辅助')
for metric,value,unit in [('M0面积参考覆盖率',.77,'%'),('M1面积参考覆盖率',.92,'%'),('M0正例可达',20,'条'),('M1正例可达',20,'条')]:number('E05',metric,value,unit,context_report,'E3/E4主G80原报告','7个面参考合计3996.53m²（原报告显示精度）' if unit=='%' else '33条固定正例查询','G80 固定30米评分窗','R4-CONTEXT G80')

fs=P/'sources/FREE_SPACE_FINAL/selected'
copyfig('E06',fs/'visuals/figures/04-new-reachability.png',note='W2b809bbe6b8_G_080固定受控查询；不是新物理入口')
for name,file in [('optional_figure','02-north-three-methods.png'),('failure_case','05-still-no-path.png'),('known_obstacle_detour','06-water-and-policy.png'),('private_constraint_fix','08-private-before-after.png'),('context_and_domain','01-north-full-route.png')]:
 copyfig('E06',fs/'visuals/figures'/file,name,note='原最终包图；自然北门与受控主查询分开；07旧错误图不作当前结果')
fd=rd(free/'verified_evidence.json')
fig,axs=plt.subplots(1,3,figsize=(15,5.5))
for ax,vals,title,unit in [(axs[0],[20,26,26],'33条受控正例的条件可达','条'),(axs[1],[.9169,100,100],'七面参考内覆盖（约值）','%'),(axs[2],[66.8593835,10278.9861863,10278.9861863],'七面参考外未证实扩张','m²')]:
 ax.bar(['M1-C','F0','F1'],vals,color=['#77949f','#d4ad6b','#37867b'])
 for j,v in enumerate(vals):ax.text(j,v,f'{v:.2f}{unit}',ha='center',va='bottom',fontsize=10)
 ax.set_ylim(0,max(vals)*1.25);ax.set_title(title,pad=15);ax.spines[['top','right']].set_visible(False)
save(fig,P/events[5][1]/'summary_figure.png','同一MAIN_G80_N80输入、1米格网、30米评分域。覆盖是对隐藏参考的覆盖；扩张未被参考证实，不自动算错误或风险概率。')
cat('E06',P/events[5][1]/'summary_figure.png',[P/'08_free_space_inference/free_space_numbers.csv'],'REDRAW_SAVED_RESULTS_STATISTICS')
for r in rows(free/'free_space_numbers.csv'):
 src=fs/r['source_member']
 if not src.is_file():continue
 number('E06',r['metric'],r['value'],r['unit'],src,r['field'],r['denominator'],r['query_ids'],r['version'],r['limitation'])

street=P/'sources/STREET_SIDE_R1'
copyfig('E09',street/'figures/missing_comparison.png',note='兴国路missing固定窗口；4米偏移SCHEMATIC，不是真实人行道位置')
copyfig('E09',street/'figures/tagged_comparison.png','optional_figure',note='安福路tagged固定窗口；不是独立验证场景')
copyfig('E09',street/'figures/native_comparison.png','native_control',note='way/39764359原生步道窗口，不是博物馆到门路线')
stsum=street/'results/trial_summary.json';std=rd(stsum)
for metric,key in [('正式尝试','formal_attempts'),('实际正式Dijkstra','actual_formal_dijkstra_calls'),('修复重测','repair_retests'),('当前矩阵请求','current_matrix_requests')]:number('E09',metric,std[key],'次',stsum,key,'3窗×2查询×3方法；同查询有修复重测','native/tagged/missing 固定ID','STREET_SIDE_R1_FINAL','拓扑候选；轴长为代理成本，不是精确步程收益')

app=P/'sources/KNOWN_ENTRANCE_E2E_R1_FIXED'
copyfig('E10',app/'AUDIT/independent_browser_exports.computed-full.png',note='历史真实APP计算和导出快照；本轮只展示，不启动服务或求路')
copyfig('E10',app/'AUDIT/independent_browser_exports.computed-door.png','optional_figure',note='历史同请求门前视图；这是旧EDGE_BAND应用版本')
q7=P/'sources/SUPPLEMENTARY_20261115/Q7-DYNAMIC-CLOSURE-SIMULATION-R1';q8=P/'sources/SUPPLEMENTARY_20261115/Q8-SCALE-LATENCY-BENCHMARK-R1'
fig,axs=plt.subplots(1,2,figsize=(12,5.5))
axs[0].bar(['PASS','NO_PATH'],[18,18],color=['#37867b','#b4a080']);axs[0].set_title('实验状态适配器：36次请求')
for j in range(2):axs[0].text(j,18,'18',ha='center',va='bottom')
axs[1].axis('off');axs[1].text(.05,.8,'原Python P.plan动态关闭负控：2次FAIL',fontsize=13,weight='bold');axs[1].text(.05,.6,'适配器：0条禁止对象使用\n关闭/恢复的保存结果有明确版本\n\n不表示原APP已具备动态导航\n本轮未重新测试HTTP动态接口',fontsize=12,linespacing=1.7)
save(fig,P/events[9][1]/'dynamic_status.png','原Q7主ID清单区分修正干预与旧压力测试；18次NO_PATH不等于软件错误；无实时感知或现场关闭实验。')
cat('E10',P/events[9][1]/'dynamic_status.png',[q7/'summary.json',q7/'outputs/primary_result_ids.json'],'REDRAW_SAVED_RESULT_COUNTS')
lat=rows(q8/'latency_distribution.csv');chosen=[]
for scale,query in [('SMALL_FROZEN_LIBRARY_ONLY','SINGLE_SHORTEST_PATH'),('SMALL_FROZEN_MUSEUM_TWO_DOORS','MULTI_ENTRANCE_K2_SEQUENTIAL_COST_SELECTION_ADAPTER')]:
 for temp,timing in [('HOT_PROCESS','end_to_end_worker_ms'),('COLD_PROCESS','cold_process_end_to_end_ms')]:
  chosen.append(next(r for r in lat if r['scale']==scale and r['query_type']==query and r['mode']=='FULL_FACE' and r['method']=='F1' and r['temperature']==temp and r['timing_scope']==timing))
table(P/events[9][1]/'cold_hot_selected.csv',chosen)
fig,ax=plt.subplots(figsize=(12,6));labels=['图书馆K1 热内核','图书馆K1 冷进程总计','博物馆K2 热内核','博物馆K2 冷进程总计']
values=[float(r['p95_ms'])/1000 for r in chosen];ax.barh(labels,values,color=['#37867b','#c89963','#37867b','#c89963']);ax.set_xscale('log');ax.set_xlabel('保存记录p95（秒，对数轴）')
for j,v in enumerate(values):ax.text(v,j,f'  {v:.3f}秒',va='center')
ax.set_xlim(.05,1000);ax.set_title('冷热时间必须成对披露；两个不同场景不是候选数量单变量实验',pad=18)
save(fig,P/events[9][1]/'cold_hot_performance.png','热=CLI内核、不含结果写出；冷=进程启动/导入/预处理/求路/校验/输出/退出；不是HTTP响应承诺；OS磁盘缓存未控制。')
cat('E10',P/events[9][1]/'cold_hot_performance.png',[q8/'latency_distribution.csv'],'REDRAW_SAVED_PERFORMANCE',note='K2为逐门求解实验适配器，非原APP多门功能或尺度斜率')
for r in chosen:
 for k in ['p95_ms','max_ms']:number('E10',r['scale']+' '+r['temperature']+' '+k,r[k],'ms',q8/'latency_distribution.csv',r['timing_scope']+'.'+k,r['n']+'次正式观测',r['query_type']+' FULL_FACE F1','Q8_PRIMARY_FINAL','CPU/进程/预处理口径见原字段；非现场导航速度保证')
number('E10','状态适配器PASS',18,'请求',q7/'summary.json','primary_adapter_outcomes.PASS','36适配器请求','primary_result_ids清单','Q7_TAGGED_FOOTWAY_CORRECTED')
number('E10','状态适配器NO_PATH',18,'请求',q7/'summary.json','primary_adapter_outcomes.NO_PATH','36适配器请求','primary_result_ids清单','Q7_TAGGED_FOOTWAY_CORRECTED')
q7s=rd(q7/'summary.json')
number('E10','主状态适配器请求',q7s['adapter_rows'],'请求',q7/'summary.json','adapter_rows','2场景×6状态×3重复','primary_result_ids清单','Q7_TAGGED_FOOTWAY_CORRECTED')
number('E10','原Python接口关闭负控FAIL',q7s['native_interface_negative_controls'],'请求',q7/'summary.json','native_interface_negative_controls','2条主原接口负控均FAIL','primary_result_ids中control记录','Q7_ORIGINAL_P_PLAN','原Python P.plan忽略动态关闭；未等价实测HTTP动态接口')
appsummary=app/'runs/acceptance/summary.json';asum=rd(appsummary)
for label,field in [('原APP合法功能请求','positive_requests'),('原APP拒绝请求','negative_requests'),('原APP实际图搜索','actual_graph_search_count')]:
 number('E10',label,asum[field],'次',appsummary,field,'13固定功能验收请求，不是13个独立场地','APP-01…APP-13，原run_id见records','KNOWN_ENTRANCE_E2E_R1_FIXED','旧EDGE_BAND原型验收；不冒充本轮新请求或真实导航成功率')

# Carry original R2 numbers with explicit original-version/endpoint references, never endorse its invalid B3 figure.
map_e={3:'E01',4:'E02',6:'E02',7:'E04',8:'E03',9:'E07',10:'E08'}
for r in rows(P/'prior/R2_selected/MASTER_NUMBERS_TABLE.csv'):
 i=int(r['event_id'])
 if i not in map_e:continue
 src=P/'prior/R2_selected'/r['source_file']
 number(map_e[i],r['metric'],r['value'],r['unit'],src,r['field'],r['scope'],r['scope'],r['source_experiment'],r['limitation'])

notes={
'E01':('登记南门存在，南广场也已被识别；B0目标失败和严格源线B1/B2新增0边是两种相关但不同的记录。','蓝色为原R4保存B0边；红虚线仅测距55.022米，不是连接。B3需要至少两个适用门，本馆只有一个，原B3主图撤出。'),
'E02':('REV1删除“派生边必须已有同位置原生线”的循环门槛，从已标步行面内侧3米带生成网络并接回原门。','3米是事前模型设置，非测得的人行道宽度或规范值。三接点都试走，2条当前平面检查合格；另一条原生前缀碰围栏，原记录保留。1067米历史长起点不和后来的149米近起点拼接。'),
'E03':('N0保留7.95米缺口；N1直线假设；N2增加31.80平方米门前区域约束却选回同一直线。','N0/N1/N2是独立历史合同；同层和现实通行未证实。exit保持原坐标及身份，只到门外。区域派生段同时为假设段，不重复加总。'),
'E04':('377段为六冻结裁片中原生有效步道去重恢复，不是推断出377条新路。','1237.81→1166.10米仅到固定北侧接点，仍距出口7.95米。71.72由未舍入值相减得到。草地未整体开放。'),
'E05':('保留合法圈外原段、扩大观察并显式使用上下文，提升了部分覆盖，但同一G80输入M0/M1均20/33正例可达。','强遮蔽H与几何缺标G任务难度不同，不能混成算法提升。0.47%强遮蔽历史值不和G80的0.92%直接比较；此处M1不是后来统一约束的M1-C。'),
'E06':('F0先排除共同已知限制，再允许剩余局部未知空间条件参与求路。F1与F0同区域、节点、边和接口，只对假设段采用有限额外成本。','同一主批33正例从20到26，新增6失去0；F0/F1可达集合相同。七面参考外10278.99平方米仅未获参考证实，不自动算全错；8障碍查询6合法绕行、2不通，已知冲突0。七正例仍失败。旧private漏导已修，不能用旧07图作当前成果。'),
'E07':('从边缘带到完整合法面，求解器可重选多个接点并绕洞、障碍，减少特定查询的表示绕行。','南门159.20→148.86；北出口F0 331.65→299.53，F1另算。北门假设段并未因完整面而消失。883.48→682.44是原日志相似演示，不是截图唯一请求复算。'),
'E08':('82个新增面中36个在业务池：19经面可达但更贵、16其他有向分量、1没有当前可用接点。','局部机制3/8→5/8与四业务任务是不同查询和分母；四业务×F0/F1仍保持最小代价。不把对象数或接口记录当独立建筑数。'),
'E09':('R0沿用道路轴/共享街道；R1/R2才分别保留road_id+side+level逻辑身份，R2进一步增加条件缺标侧道。','24次尝试含6成本修复重测，22实际求解，最终矩阵18；R0两条ZERO_LENGTH_COLLAPSED_SIDE_ALIAS仍不是合法过街。4米偏移SCHEMATIC，缺真实侧向位置/物理平行去重/同侧广场接口验证；原生窗不是博物馆到门任务。'),
'E10':('旧固定APP通过CLI、HTTP、网页调用共同内核；已有新请求和分段来源实物可核验。本轮只收录当时响应、源码与截图。','原APP、Q7新状态适配器、Q8性能适配器分开。36适配器请求18PASS18NO_PATH；原Python P.plan关闭负控2FAIL，未测试HTTP动态接口。冷启动与热内核成对展示，不是实时动态导航已经部署。'),
'E11':('当前OSM主线完成了典型场景中的规则、空间表示、条件求路原型和开发/回归。','尚无跨建筑/跨城泛化证明，无现场同层与公众通行认证；当前OSM规则轨道未做正式训练，旧NYC关系模型训练属另一历史轨道。Parent Goal和用户验收没有自动通过。')}

for eid,folder,title,stage,role in events:
 f=P/folder;related=[n for n in numbers if n['event_id']==eid]
 table(f/'metrics.csv',related,fields=list(numbers[0]))
 text(f/'metrics.md',f'# {title}\n\n{notes[eid][0]}\n\n'+('\n'.join(f"- {r['metric']}：{r['value']} {r['unit']}；口径：{r['denominator']}" for r in related) if related else '本项为综合范围归纳，不新增性能数字。')+'\n\n限制：'+notes[eid][1]+'\n')
 text(f/'caption_zh.md',f'# {title}\n\n{notes[eid][0]}\n\n{notes[eid][1]}\n\n材料身份：{role}。本轮没有重算路线。\n')
 text(f/'unsupported_claims.md','# 不支持的结论\n\n'+notes[eid][1]+'\n\n地图内一致、条件可达、人工验收和现场通行分别记录。\n')
 inputs=sorted({s for g in figs if g['event_id']==eid for s in g['source_files'].split(';')}|{n['source_file'] for n in related})
 lines=['# 图件与数字来源','',f'原阶段：{stage}；材料角色：{role}。','']
 for inp in inputs:
  ss=next((s for s in sources if s['package_file']==inp),None)
  if ss:
   identity=(f'本轮派生表（非原ZIP成员）；父来源见表内source_member/source_table_member及其SHA；父固定包SHA256：`{ss["archive_sha256"]}`' if ss['identity'].startswith('DERIVED_') else f'原成员：`{ss["archive_member"]}`；固定包SHA256：`{ss["archive_sha256"]}`')
   lines += [f'- 包内文件：`{inp}`；{identity}；文件SHA256：`{ss["sha256"]}`；版本：{ss["version"]}']
 text(f/'source_traceability.md','\n'.join(lines)+'\n')
 claims.append(dict(claim_id=eid,event_id=eid,claim=notes[eid][0],source_files=';'.join(inputs),source_sha256=';'.join(sh(P/i) for i in inputs),scope=role,limitations=notes[eid][1],status='SUPPORTED_WITH_EXPLICIT_BOUNDARIES'))

text(P/'08_free_space_inference/METHOD_AND_BOUNDARIES.md','''# F0/F1方法与结论边界

主配对使用MAIN_G80_N80：80米观察、30米固定预测/评分域、1米格网；25个区域父任务中21个有查询、另4个只做区域评价，实际41查询含33正例和8已知障碍查询。每个方法使用相同观测、共同约束、参考、查询。历史M1与重新统一约束/代价的M1-C不合并。

F0：排除导出的建筑、墙/围栏、水体、禁行、明确层级冲突和草地等限制后，让局部剩余未知空间参与条件规划；不暗中加回公园或靠近步道的正向放行门槛。有效原生步道不被背景草地抹掉，也不新增自由穿车道过街。

F1：与F0的区域、节点、边和接口相同，仅将假设段成本乘2（F0为1）；原生/已标面派生段身份独立。保存图和区域身份核验表见F0_F1_saved_graph_identity_check.csv。代价不是现实风险概率。

最终M1-C20/33，F0/F1同26/33；新增6、失去0、仍有7不通。七面参考内覆盖100%来自默认许可假设；参考外10278.986平方米没有该参考的通行佐证，但不是自动全错。三方法8障碍查询都6条合法绕行、2条NO_PATH，冲突计数0。不能以“8全拒绝”替代真实行为。

最终private导出修复保留：源私有面128.388559平方米，旧版本曾误放574条有向段，最终0。08-private-before-after为纠错成果图；07-private-parking-gap属于已保留旧错误，不作当前成果。参考用于评价，不能泄入预测；所有任务已暴露，同源受控诊断，不是新独立盲测。

原合同、输入、参考、逐查询CSV、保存预测、区域和独立审核见sources/FREE_SPACE_FINAL及evidence/SOURCE_INDEX.csv。主逐查询表normalized_primary_queries.csv保留原生端点、输入/参考/预测成员SHA。没有训练、生成新入口或现场核验。
''')
text(P/'supplementary/system_integration/INTERFACE_AND_VERSION_BOUNDARY.md','''# 原型与适配器身份

原APP固定版本：KNOWN-ENTRANCE-E2E-R1-FIXED，SHA 4fc46d...；CLI scripts/plan.py、HTTP scripts/serve_app.py、网页app/app.js共同调用src/planner.py。已保存8个合法功能请求和5类拒绝的实际响应/solver记录，而不是本轮重新运行。看sources/KNOWN_ENTRANCE_E2E_R1_FIXED/runs/acceptance/，原代码只供审查，不在本轮启动。APP界面图为当时真实浏览器实操截图，非当前在线演示。

FREE-SPACE受控遮蔽输入和APP完整源输入分开；无门目标不冒称登记门，exit仅到门外。旧APP是EDGE_BAND版本；后续FULL_FACE结果单独材料中给出，不倒写成旧APP结果。

Q7状态适配器是后来新增实验包装器，主ID清单选出36个适配器请求：18PASS、18NO_PATH；禁止对象使用0，恢复状态6。两条原Python P.plan负控失败说明该旧接口忽略新增关闭参数。并未对HTTP动态关闭接口作等价独立测试，不称原网页已有动态导航。旧博物馆住宅轴干预被保留为次级压力测试，主结果改为同基线上的已标footway；这是干预纠正，不是算法改进。

Q8热请求记录CLI内核时间，冷进程记录包含启动/导入/预处理/求解/校验/输出/退出的墙钟；阶段计时嵌套，不能相加。图书馆K1与博物馆K2属于不同场景，不能拟合单变量候选数量收益。K2为两门逐个求路后排序适配器，不是已部署APP功能。独立审核复算了420条正式观测对应的p95/max；OS磁盘缓存和桌面其他轻负载没有隔离。
''')
text(P/'01_CORRECTION_LOG.md','''# R3纠错清单（R2原件不变）

1. 撤出R2事件02带“B3联合可达”题头的主图：本馆只有一个适用登记入口，B3不适用。新图直接取R4保存b0_network及原门，不画托管或历史诊断路线作成功路线。
2. 原事件05不再保留“只北侧恢复”因果说法：与REV1演进合并。R4已发现南广场但源线策略0新增；REV1才生成受约束面边缘网络。
3. 三接点不是3条合法通路：全部实际试走，2条平面合格；1条原生前缀围栏告警保留。
4. 补入真正最终FREE-SPACE包及123行主方法-查询结果，区分20/33→26/33与外扩张、未知、7失败、private修复；不复用旧PARTIAL结论。
5. 障碍负例纠偏：8查询里6合法绕行、2不通，并非全部拒绝。参考外不是全部错误。
6. 街区侧R0零长度跨侧别名仍不算合法过街；6次修复重测针对R0成本恢复，不能写成已把零长跨侧问题修好。
7. 动态适配器与原APP接口分开；原Python P.plan负控失败不能偷换成已实测HTTP动态接口。冷热性能与不同场景分开。
8. R2整包原字节保存在prior/，其无效图和旧叙事只作历史，不再作为R3当前推荐证据。新增图仅重绘冻结结果，未求路或改变旧指标。
''')
timeline='''# 修订研究时间与依赖

这是阶段依赖与实际保存时间的核对，不以ZIP成员时间伪造实验时间。

- 2026-11-10 10:33:28+08：R4开始。南广场已是焦点，仍只接纳原生源线，B1/B2均0新增。
- 同日11:33:00+08：REV1开始。合同允许已标面派生；3米边缘网络接原南门，北出口仍缺7.95米。
- 同日后续：北门N0/N1/N2先研究条件接入；WALKABILITY-R2于14:36后修复草地原生步道并研究多候选推断。两合同起点/前缀和证据身份分别保留。
- WALKABILITY-R3随后改为独立区域表示；R4-CONTEXT继续固定30米评分，比较40/80/160米观察与不同遮蔽。Context精确启动时刻未核验，不用ZIP日期代替。
- 2026-11-11：FREE-SPACE最终修复版允许残余未知空间条件求路；随后E2E原型整合CLI/HTTP/网页。
- 后续PEDESTRIAN-AREA-SHORTEST提供EDGE_BAND/FULL_FACE同合同比较；CONNECTIVITY-R1/R2检查遗漏面与接口、局部收益及四条业务路线。
- 2026-11-13：街区侧逻辑通道为已暴露开发集后续探索。地图重建R2另修正真实目标绑定，不改变街区侧历史求路。
- 2026-11-15补充：Q2/Q6/Q7/Q8分别检查端点、源一致、动态适配器和性能；含纠错和负结果，不是新泛化实验。

核心材料按上述依赖组织；街区侧和系统集成放补充轨道。系统APP最初整合先于FULL_FACE，不因材料放在最后就改写先后。没有从1067米长起点到149米近起点的纵向性能曲线。
'''
text(P/'02_REVISED_RESEARCH_TIMELINE.md',timeline)
text(P/'03_REVISED_EVENT_CATALOG.md','# 修订事件目录\n\n合并旧事件02/05的重复及错误因果后，保留11个有证据材料节点，不凑12项。顺序与补充轨道见时间线。\n\n'+'\n'.join(f'- {eid}｜{title}｜{stage}｜{role} → `{folder}`' for eid,folder,title,stage,role in events)+'\n')
table(P/'04_MASTER_NUMBERS_TABLE.csv',numbers)
table(P/'evidence/SOURCE_INDEX.csv',sources)
table(P/'figures/FIGURE_CATALOG.csv',figs)
table(P/'evidence/CLAIM_EVIDENCE_MATRIX.csv',claims)
limitations=[{'id':e[0],'scope':e[3],'limitation':notes[e[0]][1],'status':'RETAINED_NOT_RESOLVED_BY_MATERIAL_PREPARATION'} for e in events]
table(P/'evidence/LIMITATION_REGISTER.csv',limitations)
text(P/'05_EVIDENCE_STATUS.md','''# 证据状态与仍缺材料

固定源、图件、数字与版本关系已按文件核验；具体独立检查见audit/INDEPENDENT_REVIEW.md和包外INDEPENDENT_VERIFICATION.json，不能用作者自查替代。

11个节点都有可用主图及辅图；E05主图是有来源的同合同统计归纳，E11是范围归纳图，不是新实验地图。最完整的成果型材料为E01/E02纠错、E04原生步道修复、E06受控缺标成功与限制、E07完整面、E08局部与业务收益区别。

NO_PRESENTATION_GRADE_FIGURE：不存在一个有证据支持的“只恢复北侧导致南门失败”的消融成果图，该叙事已取消；不再为它凑图。街区侧没有实测宽度和真实侧向几何，原生窗不是博物馆到门；没有现场轨迹或公众通行认证图。截图唯一请求未绑定的历史相似演示保留限定。

当前OSM规则/几何主线未开展正式模型训练和新独立泛化测试；旧NYC关系模型训练是另一轨道。所有已暴露同源开发结果保留暴露身份；材料完整不等于Parent Goal、用户自然语言验收或现实导航完成。
''')
text(P/'00_MASTER_INDEX.md','# 中期科研材料R3｜阅读入口\n\n[离线图册](index.html) · [历史纠错](01_CORRECTION_LOG.md) · [时间与依赖](02_REVISED_RESEARCH_TIMELINE.md) · [数字CSV](04_MASTER_NUMBERS_TABLE.csv) · [证据状态](05_EVIDENCE_STATUS.md)\n\n本轮只整理已有结果；没有PPT、讲稿、排版建议或新求路。R2原包完整保留于prior/，以本轮纠错为当前解释。\n\n'+'\n\n'.join(f'- [{eid} {title}]({folder}/caption_zh.md)\n\n  [主图]({folder}/main_figure.png) · [辅图]({folder}/optional_figure.png) · [数字]({folder}/metrics.csv) · [来源]({folder}/source_traceability.md)' for eid,folder,title,*_ in events)+'\n\n© OpenStreetMap contributors / ODbL；仅私有科研材料交接，未授权公开Push。\n')
cards=[]
for eid,folder,title,stage,role in events:
 gs=[g for g in figs if g['event_id']==eid]
 gallery=''.join(f'<figure><a href="{g["package_file"]}"><img loading="lazy" src="{g["package_file"]}" alt="{html.escape(title)}"></a><figcaption>{html.escape(g["figure_type"])} · {html.escape(g["scope_and_limit"])}</figcaption></figure>' for g in gs)
 cards.append(f'<section id="{eid}"><h2>{eid}　{html.escape(title)}</h2><p class="badge">{html.escape(role)} · {html.escape(stage)}</p><p>{html.escape(notes[eid][0])}</p><p class="warn">{html.escape(notes[eid][1])}</p>{gallery}<a href="{folder}/metrics.csv">逐项数字</a> · <a href="{folder}/source_traceability.md">来源与SHA</a></section>')
text(P/'index.html','<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PG1科研材料R3</title><style>body{background:#f5f4ee;color:#263b34;margin:0;font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif}header,main{max-width:1280px;margin:auto;padding:26px}section{background:white;padding:26px;margin:28px 0;border-radius:12px;scroll-margin-top:60px}h1{font-size:30px}h2{font-size:25px}a{color:#17685e}img{width:100%;height:auto;display:block}figure{margin:24px 0}figcaption,.badge{font-size:13px;color:#65736c}.warn{background:#fff2d7;padding:12px}nav{position:sticky;top:0;background:#164238;display:flex;gap:20px;justify-content:center;padding:8px;z-index:10}nav a{color:white}</style><header><h1>复杂建筑入口接入与末段步行规划｜科研材料R3</h1><p>历史因果纠错 · 缺标空间F0/F1补证 · 侧别探索与系统集成分轨</p><p class="warn">南广场在R4已经被识别，REV1才将其转为面派生路由连接。26/33是条件查询可达，不是26栋建筑的现场通行认证。</p><a href="00_MASTER_INDEX.md">总索引</a> · <a href="01_CORRECTION_LOG.md">纠错清单</a> · <a href="02_REVISED_RESEARCH_TIMELINE.md">历史时间线</a> · <a href="04_MASTER_NUMBERS_TABLE.csv">关键数字</a> · <a href="05_EVIDENCE_STATUS.md">证据状态</a></header><nav>'+''.join(f'<a href="#{e[0]}">{e[0]}</a>' for e in events)+'</nav><main>'+''.join(cards)+'</main></html>')
text(P/'audit/FACT_CHECK_REPORT.md','''# 作者事实检查

实际核对R2、旧交接、R4、REV1、最终FREE-SPACE、固定APP、街区侧与Nov15补充的源字节/成员/字段；原始包SHA见evidence/SOURCE_INDEX.csv和audit输入清单。独立角色另从原CSV、ID清单及保存响应复数，不调用作者算法。

旧R2错误B3图和不存在的北侧-only因果不再推荐；所有原件保留。红色测距线不能当路线；North N0/N1/N2与F0/F1分别引用；完整面不放开公园/草地；状态适配器不冒充原APP动态功能；冷/热和几何/代价/分母分开。

本轮求路0、模型训练0、外部地图/接口请求0、Git写入0。静态图、归纳表和素材页面不是新算法实测。现场、独立盲测、公众权限与原生未记录条件保持未知。
''')
text(P/'README_SCOPE.md','''# 使用范围

解压后离线打开index.html，或从00_MASTER_INDEX.md逐项查看；图片/表/原报告无需安装实验环境即可阅读。本页面不是在线计算原型，没有启动服务器或路线求解。

prior/完整保留R2固定ZIP；R3目录的纠错文件取代R2中错误图题或不充分历史解释，不修改原件。sources/原始历史文档可能含当时本机路径或未纳入的相对运行依赖；保留原字节，不承诺整段历史工程全部自包含。图册自身及关键证据文件离线可读。

地图来自冻结OSM，© OpenStreetMap contributors / ODbL。仅私有科研审查，未新增许可、API请求、费用或公开发布。旧算法源码只供追溯，不在本轮执行。不包含密钥、字体或模型。
''')
text(R/'working/events.json',json.dumps(events,ensure_ascii=False,indent=2))
print(json.dumps({'events':len(events),'figures':len(figs),'numbers':len(numbers),'sources':len(sources)},ensure_ascii=False))
