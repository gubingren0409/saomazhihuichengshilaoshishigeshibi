"""Read frozen artifacts and prepare illustrated materials. No routing or API calls."""
from pathlib import Path
import base64, csv, hashlib, html, io, json, shutil, zipfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, FancyBboxPatch, PathPatch
from matplotlib.path import Path as MPath
from shapely.geometry import shape
from shapely.geometry.polygon import orient
from shapely.ops import transform
from pyproj import Transformer

R = Path(__file__).resolve().parents[1]
P = R/'package'
H = R.parent/'PG1_RESEARCH_MATERIALS_HANDOFF_R1'
C = Path('C:/Users/28489/.codex/visualizations/2026/10/10/01a12554-d978-7d60-bdf2-97caf96e0581')
S = R.parent/'PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115'
def sha(b): return hashlib.sha256(b).hexdigest()
def write(p,s):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(s,encoding='utf8')
def csvout(p,rows,fields=None):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def js(p): return json.loads(p.read_text(encoding='utf-8-sig'))
zpath=H/'delivery/HANDOFF_PACKAGE.zip'
assert sha(zpath.read_bytes())=='1da065a47356057018246d2213812fc9ef7158471e15b2ecb2e216621c3f9444'
z=zipfile.ZipFile(zpath)
suppzip=S/'delivery/PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115_REVIEW.zip'
assert sha(suppzip.read_bytes())=='bebdd6cb52c3afc156fc62a3b373ea29a2f4f38d68b28976ef771c5df6728103'
sz=zipfile.ZipFile(suppzip)
catalog=list(csv.DictReader(io.StringIO(z.read('figures/FIGURE_CATALOG.csv').decode('utf-8-sig'))))
sourceindex=list(csv.DictReader(io.StringIO(z.read('evidence/SOURCE_INDEX.csv').decode('utf-8-sig'))))
metadata={r['package_path']:r for r in sourceindex+catalog}
selection=js(R/'working/figure_selection.json')
traces=[]
def source(member):
    dest=P/'sources'/member
    if not any(t['package_path']==dest.relative_to(P).as_posix() for t in traces):
        b=z.read(member); m=metadata.get(member,{})
        if m.get('sha256'): assert sha(b)==m['sha256'], member
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        traces.append(dict(package_path=dest.relative_to(P).as_posix(),source_experiment=m.get('round','HANDOFF-R1'),
            fixed_archive=m.get('archive','HANDOFF_PACKAGE.zip'),fixed_archive_sha256=m.get('fixed_archive_sha256','1da065a47356057018246d2213812fc9ef7158471e15b2ecb2e216621c3f9444'),
            original_member=m.get('member',member),source_sha256=sha(b),source_identity=m.get('source_identity','R1 frozen package member'),
            containing_handoff_sha256='1da065a47356057018246d2213812fc9ef7158471e15b2ecb2e216621c3f9444'))
    return dest
def evidence(round,prefix):
    return source(next(n for n in z.namelist() if n.startswith('source_materials/') and '/'+round+'/' in n and Path(n).name.startswith(prefix)))
def extra(src,relative,stage,archive,archive_sha,member):
    p=P/'sources'/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(src.read_bytes())
    traces.append(dict(package_path=p.relative_to(P).as_posix(),source_experiment=stage,fixed_archive=archive,
        fixed_archive_sha256=archive_sha,original_member=member,source_sha256=sha(p.read_bytes()),source_identity='READ_ONLY_FIXED_ARTIFACT',containing_handoff_sha256='NOT_IN_R1_HANDOFF'))
    return p
rounds=['OSM_GEOAPIFY_R4','OSM_GEOAPIFY_R4_REV1','OSM_GEOAPIFY_R4_NORTH_ACCESS_R1','WALKABILITY-R2','PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED','PED-AREA-CONNECTIVITY-R2']
for n in z.namelist():
    if n.startswith('source_materials/') and any('/'+r+'/' in n for r in rounds): source(n)
# Read the actual frozen map reconstruction archive, not an old incorrect scene overlay.
recon=R.parent/'PG1_MAP_CONTEXT_RECONSTRUCTION_R2/delivery/OPEN_REVIEW.zip'
reconsha=sha(recon.read_bytes());assert reconsha=='8a14afa8e2d39436c5a4365b35897e5c523e0e5a49785d1663373b7a7d2a1b98'
rz=zipfile.ZipFile(recon); scene_bytes=rz.read('data/scene.json')
scene_path=P/'sources/reconstruction/scene.json';scene_path.parent.mkdir(parents=True,exist_ok=True);scene_path.write_bytes(scene_bytes)
traces.append(dict(package_path='sources/reconstruction/scene.json',source_experiment='PG1_MAP_CONTEXT_RECONSTRUCTION_R2',fixed_archive='OPEN_REVIEW.zip',fixed_archive_sha256=reconsha,original_member='data/scene.json',source_sha256=sha(scene_bytes),source_identity='FROZEN_RAW_MAP_CONTEXT_NOT_OLD_ALGORITHM_OVERLAY',containing_handoff_sha256='NOT_IN_R1_HANDOFF'))
scene=json.loads(scene_bytes)
assert scene['source']['sha256']=='3219eccb7a7d37ea463895c63cc98688d66e0abe6b85575d38ea53ec023afc91'
for member in ['audit/TARGET_IDENTITY_AUDIT.md','TARGET_SCENE_CORRECTION.md','audit/target_objects.json','audits/INDEPENDENT_REVIEW.md']:
    p=P/'sources/reconstruction'/member;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(rz.read(member))
    traces.append(dict(package_path=p.relative_to(P).as_posix(),source_experiment='PG1_MAP_CONTEXT_RECONSTRUCTION_R2',fixed_archive='OPEN_REVIEW.zip',fixed_archive_sha256=reconsha,original_member=member,source_sha256=sha(p.read_bytes()),source_identity='FROZEN_RECONSTRUCTION_AUDIT',containing_handoff_sha256='NOT_IN_R1_HANDOFF'))
northzip=C/'OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/delivery/OPEN_REVIEW.zip'
nz=zipfile.ZipFile(northzip); northsha=sha(northzip.read_bytes())
northmeta=next(r for r in sourceindex if r['round']=='OSM_GEOAPIFY_R4_NORTH_ACCESS_R1')
assert northsha==northmeta['fixed_archive_sha256']
constraints=P/'sources/north/constraints.geojson';constraints.parent.mkdir(parents=True,exist_ok=True);constraints.write_bytes(nz.read('data/constraints.geojson'))
traces.append(dict(package_path=constraints.relative_to(P).as_posix(),source_experiment='OSM_GEOAPIFY_R4_NORTH_ACCESS_R1',fixed_archive='OPEN_REVIEW.zip',fixed_archive_sha256=northsha,original_member='data/constraints.geojson',source_sha256=sha(constraints.read_bytes()),source_identity='FROZEN_CONSTRAINT_GEOMETRY',containing_handoff_sha256='NOT_IN_R1_HANDOFF'))
for name in ['RESEARCH_REVIEW.md','INDEPENDENCE_SCOPE.md','EXPERIMENT_BRIEF.md']:
    assert (S/name).read_bytes()==sz.read(name), name
    extra(S/name,'supplementary/'+name,'PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115','PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115_REVIEW.zip','bebdd6cb52c3afc156fc62a3b373ea29a2f4f38d68b28976ef771c5df6728103',name)
for name in ['FINAL_STATUS.json','SUPPLEMENTARY_VERIFICATION.json']:
    extra(S/'delivery'/name,'supplementary/'+name,'PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115','OUTSIDE_SEALED_ZIP_RECEIPT','NOT_APPLICABLE',name)

plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':11,'svg.fonttype':'none','figure.facecolor':'#fcfbf7','axes.facecolor':'#fcfbf7'})
proj=Transformer.from_crs(4326,32651,always_xy=True).transform
features=[f for f in scene['features'] if 'algorithm' not in ' '.join(f.get('families',[])).lower() and f.get('geometry')]
target=next(f for f in features if f['source_id']=='way/161090899')
south=proj(121.4712158,31.2299607);north=proj(121.4706605,31.2305674)
def drawgeom(ax,g,fc=None,ec='#aaa',lw=.7,z=1,alpha=1,ls='-'):
    if g.is_empty:return
    if g.geom_type=='Polygon':
        # Transparent holes preserve the frozen grass/water/building layers below.
        g=orient(g,sign=1.0);verts=[];codes=[]
        for ring in [g.exterior,*g.interiors]:
            pts=list(ring.coords);verts.extend(pts)
            codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(pts)-2)+[MPath.CLOSEPOLY])
        ax.add_patch(PathPatch(MPath(verts,codes),fc=fc or 'none',ec=ec,lw=lw,zorder=z,alpha=alpha))
    elif g.geom_type in ['MultiPolygon','MultiLineString','GeometryCollection']:
        for k in g.geoms:drawgeom(ax,k,fc,ec,lw,z,alpha,ls)
    elif g.geom_type=='LineString':
        x,y=g.xy;ax.plot(x,y,color=ec,lw=lw,zorder=z,alpha=alpha,ls=ls)
def basemap(ax,bounds,faces=True,labels=True):
    for f in features:
        g=shape(f['geometry']);t=f.get('tags',{});fam=f.get('families',[])
        if not g.intersects(shape({'type':'Polygon','coordinates':[[[bounds[0],bounds[1]],[bounds[2],bounds[1]],[bounds[2],bounds[3]],[bounds[0],bounds[3]],[bounds[0],bounds[1]]]]})):continue
        if 'vegetation' in fam:drawgeom(ax,g,'#dae5c7','#b3c49e',.45,1)
        elif 'water' in fam:drawgeom(ax,g,'#c3dce5','#8cb5c6',.5,2)
        elif 'pedestrian_areas' in fam and faces:drawgeom(ax,g,'#bfe2e8','#73a8b2',.6,1.2)
        elif 'buildings' in fam:drawgeom(ax,g,'#ddd9cf','#b4afa2',.5,3)
        elif 'road_centerlines' in fam:drawgeom(ax,g,ec='#bcc1c3',lw=1.7,z=4)
        elif any(x in fam for x in ['native_walkways','crossings','sidewalks']):drawgeom(ax,g,ec='#567f83',lw=.7,z=5)
        elif 'barriers' in fam:drawgeom(ax,g,ec='#865b58',lw=.8,z=6)
    drawgeom(ax,shape(target['geometry']),'#d8ad7e','#8b6541',1.2,7)
    ax.scatter(*south,s=60,marker='*',color='#d94f39',zorder=20)
    ax.scatter(*north,s=30,marker='s',facecolor='white',edgecolor='#93445c',zorder=20)
    if labels:
        cen=shape(target['geometry']).representative_point();ax.text(cen.x,cen.y,'上海博物馆\n人民广场馆',ha='center',va='center',fontsize=10,zorder=21,bbox={'fc':'#fff9','ec':'none','pad':2})
        ax.annotate('南门 main',south,xytext=(8,-15),textcoords='offset points',fontsize=9,zorder=21)
        ax.annotate('北出口 exit（仅门外）',north,xytext=(-6,12),textcoords='offset points',ha='right',fontsize=8,zorder=21)
        # Label native named road geometry; no invented width or road surface.
        seen=set()
        for f in features:
            name=f.get('tags',{}).get('name','')
            if name not in ['黄陂北路','人民大道'] or name in seen:continue
            g=shape(f['geometry']);q=g.representative_point()
            if bounds[0]<q.x<bounds[2] and bounds[1]<q.y<bounds[3]:
                ax.text(q.x,q.y,name,fontsize=9,color='#525962',zorder=22,bbox={'fc':'#fffd','ec':'none','pad':1});seen.add(name)
    ax.set(xlim=(bounds[0],bounds[2]),ylim=(bounds[1],bounds[3]));ax.set_aspect('equal');ax.tick_params(labelbottom=False,labelleft=False,length=0)
    span=bounds[2]-bounds[0];bar=10 if span<100 else 50
    xx=bounds[0]+.05*span;yy=bounds[1]+.05*(bounds[3]-bounds[1]);ax.plot([xx,xx+bar],[yy,yy],color='#333',lw=3,zorder=40);ax.text(xx,yy+.02*(bounds[3]-bounds[1]),f'{bar}米',fontsize=8,zorder=40)
    ax.text(.97,.97,'↑ N',transform=ax.transAxes,ha='right',va='top',fontsize=10)
def save(fig,p,footer):
    fig.text(.02,.015,footer,fontsize=9,color='#555');fig.savefig(p,dpi=190,bbox_inches='tight');fig.savefig(p.with_suffix('.svg'),bbox_inches='tight');plt.close(fig)

events=[
('01_problem_definition','研究问题：复杂建筑的“到门”为什么难','已知建筑位置和登记门，仍不等于外部步行网络能连续接到门。','原始地图上下文图'),
('02_line_only_failure','初始真实失败：南门有登记，但线网未接通','旧 R4 的南门存在于地图，原生线网却没有入口图节点。','算法叠加图'),
('03_walkable_area_needed','步行线不是全部：广场面是另一类空间输入','南广场已标为步行面，但“画得出面”和“能在面内寻路”是两回事。','原始地图上下文对照'),
('04_conservative_edge_band','第一版保守策略：先在步行面边缘寻路','R4-REV1 在已标步行面内派生边缘网络，并保留内环和门前端口检查。','机制成果图'),
('05_early_endpoint_and_evidence_gap','早期未到南门：可证实的结果与解释缺口','能确认早期南门未接通；不能确认“只恢复北侧”是既有实验事实。','结果对照图／叙事核对'),
('06_south_plaza_connection','南广场参与计算后：南门条件接通','在 R4-REV1 中，南广场派生边和门前端口实际参加路线，终点到原南门残差为零。','结果对照图'),
('07_native_walkway_grass_fix','草地背景不能抹掉已有步道','WALKABILITY-R2 恢复原生有效步道后，同一北侧接点路线减少约71.72米。','结果对照图'),
('08_north_exit_conditional_access','北出口7.95米：条件接入不等于通行证明','N1和N2均补成条件路线；N2没有在本例增加同层或通行证据。','结果对照图'),
('09_full_face_routing','从边缘绕行到完整合法步行面','同源、同起终点与约束下，完整面路线可减少表示方式造成的绕行。','结果对照图'),
('10_local_vs_business_gain','局部机制改善，不保证业务路线收益','新增面即使接入了图，也可能更贵、处于其他分量，或没有当前可用接口。','定量机制总结图'),
('11_current_stage','当前阶段与下一阶段','当前OSM末段规划线以规则、空间表示与典型场景原型为主，多场景独立验证仍待开展。','机制解释图'),
('12_research_progress','阶段推进链与证据边界','阶段推进来自空间表示和实现修复；每一步都有适用范围，未形成普遍到达证明。','机制解释图')]
figrows=[];numbers=[];event_sources={i:[] for i in range(1,13)}
for dirname,*_ in events:(P/dirname).mkdir(parents=True,exist_ok=True)
def dep(i,p):
    rel=p.relative_to(P).as_posix()
    if rel not in event_sources[i]:event_sources[i].append(rel)
def original(i,idx,name='main_figure',title=None):
    r=selection[idx];src=source(r['package_path']);dep(i,src)
    dest=P/events[i-1][0]/(name+'.png')
    if src.suffix=='.svg':
        shutil.copy2(R/f'working/render_{idx}.png',dest);shutil.copy2(src,dest.with_suffix('.svg'));kind='original_svg_rasterized'
    else:
        shutil.copy2(src,dest);kind='original'
        # Retain the paired vector when available.
        other=next((x for x in selection if x['round']==r['round'] and x['member']==str(Path(r['member']).with_suffix('.svg')).replace('\\','/')),None)
        if other:shutil.copy2(source(other['package_path']),dest.with_suffix('.svg'))
    figrows.append(dict(figure_id=f'E{i:02}-{name}',event_id=i,title=title or events[i-1][1],description=events[i-1][2],source_experiment=r['round'],source_file=src.relative_to(P).as_posix(),regenerated_or_original=kind,suitable_for_main_slide='no' if i==5 or name!='main_figure' else 'yes',figure_type=events[i-1][3],output_file=dest.relative_to(P).as_posix(),sha256=sha(dest.read_bytes()),caveat='历史结果；非本轮新求路；不证明现场通行'))
def drawn(i,inputs,name='main_figure',suitable=True):
    for x in inputs:dep(i,x)
    dest=P/events[i-1][0]/(name+'.png')
    figrows.append(dict(figure_id=f'E{i:02}-{name}',event_id=i,title=events[i-1][1],description=events[i-1][2],source_experiment=';'.join(sorted({next((t['source_experiment'] for t in traces if t['package_path']==x.relative_to(P).as_posix()),'frozen source') for x in inputs})),source_file=';'.join(x.relative_to(P).as_posix() for x in inputs),regenerated_or_original='redrawn_from_frozen_results_no_solver',suitable_for_main_slide='yes' if suitable and name=='main_figure' else 'no',figure_type=events[i-1][3],output_file=dest.relative_to(P).as_posix(),sha256=sha(dest.read_bytes()),caveat='仅重绘既有几何/统计；未重新求路'))
def num(i,label,value,unit,src,field,scope,limitation='仅冻结地图/有限计算图，不是现实导航成功率'):
    dep(i,src);numbers.append(dict(event_id=i,metric=label,value=value,unit=unit,source_experiment=next(t['source_experiment'] for t in traces if t['package_path']==src.relative_to(P).as_posix()),source_file=src.relative_to(P).as_posix(),field=field,scope=scope,limitation=limitation,source_sha256=sha(src.read_bytes())))

r4=evidence(rounds[0],'summary_');r4report=evidence(rounds[0],'04_EXPERIMENT_RESULTS_');r4audit=evidence(rounds[0],'02_OPEN_SPACE_FEATURE_AUDIT_')
rev=evidence(rounds[1],'summary_');revreport=evidence(rounds[1],'RESULTS_');revdata=js(rev)
grass=evidence('WALKABILITY-R2','semantics_');gd=js(grass)
northmetrics=evidence(rounds[2],'experiment_');nd=js(northmetrics)
northroutes=evidence(rounds[2],'route_variants_');northgeo=js(northroutes)
short=evidence(rounds[4],'RESULTS_');conn=evidence(rounds[5],'summary_');cd=js(conn)
connreport=evidence(rounds[5],'ROUTE_DIAGNOSIS_')

original(1,14);original(1,12,'optional_figure')
for i in [1,3,5]:dep(i,scene_path)
original(2,20);original(2,16,'optional_figure');dep(2,r4report);dep(2,r4audit)
num(2,'南门至原冻结线网接近点距离',55.022,'m',r4audit,'入口资格与B0实物：原文约55.022米','旧R4历史B0诊断；非完整到门路线')
num(2,'博物馆B1正式新增边',0,'条',r4report,'B1新增0条','旧R4严格原生线边策略')

# Event 3: identical frozen context, only switch source face display. This is NOT a route experiment.
bounds=[354205,3456005,354485,3456270]
fig,axs=plt.subplots(1,2,figsize=(14,7))
for ax,show,title in zip(axs,[False,True],['相同原始地图：显示线状步行对象','相同原始地图：同时显示已标步行面']):
    basemap(ax,bounds,faces=show);ax.set_title(title,pad=14)
axs[1].text(354425,3456050,'南广场\nrelation/2385771',ha='center',fontsize=9,bbox={'fc':'#fffc','ec':'none'},zorder=50)
fig.suptitle('显示差异用于说明输入表示；没有运行新算法或改变网络',fontsize=15)
save(fig,P/events[2][0]/'main_figure.png','底图：同一冻结OSM对象；EPSG:32651米；© OpenStreetMap contributors / ODbL；源中草地和建筑保持原样')
drawn(3,[scene_path,r4audit]);original(3,27,'optional_figure')
num(3,'南广场原生外围接点',3,'个',r4audit,'南广场：三个直接接点','relation/2385771；非新增入口')

original(4,30);original(4,29,'optional_figure');dep(4,revreport)
num(4,'主设置边缘带宽度',3,'m',revreport,'固定带宽对照主设置','R4-REV1，与后来的FULL_FACE主实验不同起点合同')

# An explicit evidence correction is preferable to fabricating the requested history.
original(5,20);original(5,28,'optional_figure');dep(5,r4audit);dep(5,r4report);dep(5,revreport)
write(P/events[4][0]/'NARRATIVE_EVIDENCE_GAP.md','''# 事件5：拟定因果叙事尚无充分证据

已有真实图件说明早期线网没有到达南门，并能看出诊断路线停在馆侧。\n
但“只恢复北侧、没有恢复南侧”不能作为已核实的原因：
- 旧R4《开放空间与登记入口源证据》已以南广场relation/2385771为唯一开发焦点。
- 旧R4实际B1/B2都新增0边，并非已有成功北侧面恢复的对照实验。
- R4-REV1在同一轮同时评估南、北两个步行面；南门接通，北出口仍有未知间隙。

可采用的准确解释是：早期系统认识到了南侧步行面，但未把面内可行连接转换为可用路由边；后续REV1实现了受约束面派生。\n
本目录main_figure是历史诊断图，不是“只北侧恢复”消融图。不把它作为该因果叙事的正文证据。没有重跑实验补造缺失历史。
''')

original(6,28);original(6,29,'optional_figure');dep(6,revreport);dep(6,r4report)
num(6,'南门选定条件路线长度',revdata['south_selected']['length_m'],'m',rev,'south_selected.length_m','同一历史冻结起点→原南门；选定接点node/1890935454')
num(6,'到原南门终点残差',revdata['south_selected']['gap_m'],'m',rev,'south_selected.gap_m','R4-REV1地图坐标到达，不是现场门位认证')
num(6,'选定路线门前派生端口长度',revdata['south_selected']['section_lengths_m']['DERIVED_TERMINAL_CONNECTOR'],'m',rev,'south_selected.section_lengths_m.DERIVED_TERMINAL_CONNECTOR','独立记录的派生门前端口，不当作原生步道')
num(6,'三个接点中合格条件路线',2,'条/3个接点',rev,'south_trial_statuses.EXTERIOR_REACHED_CONDITIONAL','另1条原生前缀有平面围栏冲突，不能写3/3全部合法')

original(7,35);original(7,36,'optional_figure');dep(7,grass);dep(7,evidence('WALKABILITY-R2','RESULTS_'))
for label,key,unit in [('恢复原生步道片段','restored_segments','段'),('恢复有向弧','restored_directed_arcs','弧')]:num(7,label,gd['source_identity_dedup'][key],unit,grass,'source_identity_dedup.'+key,'六冻结裁片原生身份去重；非377个独立地点')
for method in ['S0','S1']:num(7,method+'到固定北侧接点长度',gd['variants'][method]['north_fixed']['length_m'],'m',grass,f'variants.{method}.north_fixed.length_m','同起点、同接点；不是到北出口，仍有7.95米门前缺口')
num(7,'未舍入差值再取两位',gd['fixed_north_approach_improvement_m'],'m',grass,'fixed_north_approach_improvement_m','71.72来自原精度差，不用1237.81减1166.10反算71.71')
num(7,'固定北侧路线使用恢复片段',48,'段',evidence('WALKABILITY-R2','RESULTS_'),'S修复已有信息：实际使用48段恢复边','377段去重总量中的子集，不是全部恢复边都参加该路线')

# Event 8: original stored N0/N1/N2 geometry, a common map extent, no new connector generation.
exitxy=north
for near,name in [(False,'main_figure'),(True,'optional_figure')]:
    fig,axs=plt.subplots(1,3,figsize=(17,7))
    for ax,variant in zip(axs,['N0','N1','N2']):
        b=[north[0]-26,north[1]-19,north[0]+19,north[1]+26] if near else [354190,3456050,354455,3456310]
        basemap(ax,b,labels=not near)
        if variant=='N2':
            for f in js(constraints)['features']:
                if f['properties'].get('role')=='N2_corridor':
                    drawgeom(ax,transform(proj,shape(f['geometry'])),'#e8c576','#bc8b23',.8,8,.6)
        for f in northgeo['features']:
            p=f['properties']
            if p.get('variant')!=variant:continue
            if p.get('role')=='native_approach':drawgeom(ax,transform(proj,shape(f['geometry'])),ec='#236d9a',lw=2,z=12)
            if p.get('role')=='connector':drawgeom(ax,transform(proj,shape(f['geometry'])),ec='#d86235',lw=2.2,z=15,ls='--')
        ax.set_title({'N0':'N0 原网：仍差7.95米','N1':'N1 直线假设：7.95米','N2':'N2 区域约束：同一7.95米'}[variant],fontsize=12)
        if variant=='N2':ax.text(.03,.89,'金色：门前假设允许域\n约31.80平方米，非通行证明',transform=ax.transAxes,fontsize=8,zorder=40,bbox={'fc':'#fffc','ec':'none','pad':3})
        if near:ax.annotate('原北出口（不移动）\nentrance=exit',north,xytext=(10,-25),textcoords='offset points',fontsize=8,zorder=40)
    fig.suptitle('北出口门外条件接入｜N1与N2相同几何，不等于增加现实通行证据',fontsize=15)
    save(fig,P/events[7][0]/(name+'.png'),'同一冻结OSM底图 / EPSG:32651米；蓝：已有路线，橙虚线：假设连接；楼层与现场通行未知；© OpenStreetMap contributors')
    drawn(8,[northroutes,northmetrics,constraints,scene_path],name)
for v in ['N0','N1','N2']:
    num(8,v+'路线长度',nd['variants'][v]['length_m'],'m',northmetrics,f'variants.{v}.length_m','北门接入R1原冻结起点；与后来的草地修复路线不同版本')
    num(8,v+'到原出口残差',nd['variants'][v]['residual_m'],'m',northmetrics,f'variants.{v}.residual_m','仅门外；N1/N2是假设可达')
num(8,'N2门前允许域面积',nd['sensitivity'][0]['corridor_area_m2'],'m²',northmetrics,'sensitivity[0].corridor_area_m2','围原线构建的历史31.80平方米；不是区域恢复方法性能')

original(9,42);original(9,44,'optional_figure');original(9,48,'optional_long_route');dep(9,short)
mainmatrix=evidence(rounds[4],'independent_main_matrix_R2_');dep(9,mainmatrix)
md=js(mainmatrix)
for label,row,key in [('北出口F1旧边缘带',6,'length_m'),('北出口F1完整面',7,'length_m'),('北出口F1完整面代价',7,'cost_m')]:
    num(9,label,md['rows'][row]['measurements'][key],'加权米' if key=='cost_m' else 'm',mainmatrix,f'rows[{row}].measurements.{key}','APP-04，F1惩罚假设段；几何长与代价不能互换')
for label,row in [('北出口F0完整面假设段',5),('北出口F1完整面假设段',7)]:
    num(9,label,md['rows'][row]['measurements']['layers']['inferred'],'m',mainmatrix,f'rows[{row}].measurements.layers.inferred','仍为条件假设段；不是来源支持的连续真实步道')
for label,a,b,scope in [('南门F0/F1',159.195600,148.863122,'APP-01/02 同起点南门'),('北出口门外F0',331.647435,299.531450,'APP-03；F0假设段12.534190米'),('历史日志相似长绕行',883.484688,682.443499,'历史相似任务，非截图唯一请求精确复算')]:
    num(9,label+'旧边缘带',a,'m',short,'结果表/'+scope,scope)
    num(9,label+'完整面',b,'m',short,'结果表/'+scope,scope)

fig,ax=plt.subplots(figsize=(12.5,6));ax.axis('off')
cats=['经面可形成完整walk，但更贵','其他有向分量','没有当前可用接点']
vals=[19,16,1];colors=['#479c9c','#7190b6','#c8ad7f']
left=0
for value,col,cat in zip(vals,colors,cats):
    ax.barh(.65,value,left=left,color=col,height=.19);ax.text(left+value/2,.65,str(value),ha='center',va='center',fontsize=19,color='white' if value>1 else 'black');left+=value
ax.set_xlim(-1,37);ax.set_ylim(0,1)
ax.text(0,.96,'36个业务场景池内新增面：为什么没有改善四条固定业务路线？',fontsize=17,weight='bold')
for y,t,col,v in zip([.40,.29,.18],cats,colors,vals):ax.text(0,y,f'●  {t}：{v}个',fontsize=15,color=col)
ax.text(0,.04,'不是“全部未接入”，也不是“接入就有收益”；同图最小代价复核保持原值。',fontsize=12,color='#555')
save(fig,P/events[9][0]/'main_figure.png','来源：PED-AREA-CONNECTIVITY-R2固定诊断；82为全局新增面，36为业务池子集；有限图最优性，不是现实最短路')
drawn(10,[conn,connreport]);original(10,60,'optional_figure')
for label,key in [('全局新增唯一面','global_new_total'),('业务场景池内唯一面','unique_new_in_business_scene_pools'),('池外面','outside_business_scene_pools')]:num(10,label,cd['global_new_business_scene_overlap'][key],'个面',conn,'global_new_business_scene_overlap.'+key,'原生身份去重；不是独立场景数')
for label,key in zip(cats,['EXISTING_ROUTE_STRICTLY_CHEAPER','OTHER_DIRECTED_COMPONENT','NOT_PRESENT_IN_QUERY_NAMESPACE']):num(10,label,cd['global_new_business_scene_overlap']['unique_reasons'][key],'个面',conn,'global_new_business_scene_overlap.unique_reasons.'+key,'36个业务池新增面；最后1个来源对象存在但当前query没有owner弧')

def cards(i,title,items,footer,cols=2):
    fig,ax=plt.subplots(figsize=(13,7));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off');ax.text(.03,.94,title,fontsize=20,weight='bold')
    for j,(head,body) in enumerate(items):
        x=.04+(j%cols)*(.92/cols);y=.76-(j//cols)*.27
        ax.add_patch(FancyBboxPatch((x,y-.17),.86/cols,.20,boxstyle='round,pad=.018',fc='#e4efea' if j<cols else '#edf0f3',ec='#bbcec5'))
        ax.text(x+.015,y,head,fontsize=13,weight='bold');ax.text(x+.015,y-.06,body,fontsize=11,va='top',linespacing=1.6)
    save(fig,P/events[i-1][0]/'main_figure.png',footer)
cards(11,'当前OSM末段规划研究：已具备什么，还缺什么',[
('当前完成｜空间表示与规则','原生步道保留、约束导出、步行面穿行\n已知门的条件末段路线与可操作原型'),
('当前证据｜典型场景开发','固定上海地图、开发/回归与负结果\n不能据此宣告跨建筑或跨城市泛化'),
('下一阶段｜独立多场景验证','按建筑/共享道路隔离数据分组\n核对地图覆盖、端点身份与适用范围'),
('尚未解决｜现实与工程边界','同层、通行权限和现场验证仍缺\n冷启动和多候选效率仍有限制')],
'本图为材料归纳，不是新增研究或实验；旧NYC已训练匹配器属另一历史轨道，不能说项目从未训练模型。')
dep(11,short);dep(11,connreport)
for f in (P/'sources/supplementary').glob('*'):dep(11,f)
drawn(11,[short,connreport,P/'sources/supplementary/RESEARCH_REVIEW.md'])
cards(12,'阶段推进：把“图上有位置”转成“可解释的末段路线”',[
('① 线网不足 → ② 引入步行面','南门存在，线网却不包含可用入口连接\n南广场原生面提供另一类空间表示'),
('③ 保守边缘 → ④ 南门条件接通','R4-REV1生成受约束面内计算边\n历史不能改写成“只北侧恢复”消融'),
('⑤ 保留草地步道 → ⑥ 门前条件接入','修正已有步道被背景草地抹掉的问题\n北出口假设连接保持exit和未知身份'),
('⑦ 完整面穿行 → ⑧ 分清业务收益','保留洞、障碍和限制后减少绕行\n新增面/局部连通不保证完整路线改善')],
'逻辑推进链，非同一实验的连续性能曲线；各阶段起点、目标、约束、分母及版本分别绑定来源。')
drawn(12,[r4report,revreport,grass,northmetrics,short,connreport])

notes={
1:('建筑代表点、登记门与能走到门的网络是不同对象。图中突出真实上海博物馆人民广场馆及南门/北出口，不把附近历史博物馆或旧诊断道路当目标。','主图是原始地图上下文，不是计算成功图；没有可信路宽/路缘信息就不绘制。'),
2:('先指出南门原生ID和原坐标确实存在，再指出它不是原生线网中的可路由节点。历史接近折线停在附近，不应当作完整到门路线。','旧R4 B1/B2未产生新边，不能作为已成功开放面内通行的结果。约55米是南门这一旧场景，不是北出口7.95米。'),
3:('左右使用同一冻结原始场景，仅切换步行面显示。广场是带外环/内环的空间对象；可见区域并不会自动变成图中的连接。','这是输入表示解释图，没有新求路；公园、草地和已标步行面不是同一语义。'),
4:('为减少无证据自由穿行，第一版仅在已标步行面的边缘带内派生计算边，检查障碍、洞和端口。南门局部图能看出路线沿边而非任意穿面。','谨慎的是计算约束，不是现场可靠性认证。门前约0.70米端口有单独身份，不混作原生线。'),
5:('可展示早期诊断路线未到南门；拟定的“只恢复北侧”解释缺少对应版本/消融证据。本事件保留历史图及证据缺口，而不凑一张不存在的成果图。','事件5因果叙事不宜直接使用；请看NARRATIVE_EVIDENCE_GAP.md。旧R4已记录南广场，REV1同时处理南北。'),
6:('同一R4-REV1对照中，旧网络没有严格南门路线，新图把外围原生接点、广场面派生网络和门前端口连起来，选定路线达到原门坐标。','三个试走接点中只有2个通过当前平面检查；剩余1个前缀碰围栏。不把3/3几何连接当作3/3合法通路，也不称已证实现实入馆。'),
7:('关键修复不是开放整片草坪，而是保留草坪背景中本来有效的原生步道。377段是六冻结裁片去重总数，图上路线只使用其中48段。','1237.81→1166.10米到同一北侧路网接点，仍没跨过门前7.95米。71.72由未舍入原值相减得到。'),
8:('三栏保留同一原北出口、底图和视野；N0差7.95米，N1直线假设，N2增加区域约束但选回相同直线。没有已标二维冲突，不等于有同层/通行证据。','N2约31.80平方米是当时围原线产生的受约束域；不能冒充后来的独立区域恢复。N2派生段与假设段是重合身份，不重复加长度。exit不能用于入馆。'),
9:('同一对照允许求解器在完整合法步行面中重新选择接点和内部路径，内环及障碍保留。主图是南门；辅图分别是北出口和历史相似长绕行，不能拼成同一请求。','331.65→299.53是F0；北出口F1为331.92→300.78米且代价不同。883.48→682.44是原日志相似演示，不是截图唯一请求精确复算。仅有限图/可见图条件内的最短，不是现实全局最短。'),
10:('先分清全局82个新增面与业务池内36个。36个中19个确有经面连接但更贵，16个在其他有向分量，1个无当前可用接点，因此局部机制收益没有变成这组业务最短路线收益。','3/8→5/8属于局部机制端点，不是四业务任务；F0/F1为四任务×两种成本。不能把82个面或接口记录当82个独立建筑。'),
11:('当前这一OSM轨道主要在典型场景中校正空间表示、约束、接口和求解原型；下一步是隔离场景的验证及现实证据补足。只整理已有进度，不自动启动。','“尚无正式训练泛化主线”仅限当前OSM规则/几何路线，旧NYC关系学习模型已训练过。最新补充核验仍没有现场真值；动态实验适配器不等于已部署实时系统。'),
12:('按照问题与修正的逻辑串联各阶段，但每张图和每个数字仍留在自己的实验语境中。阶段总结保留负结果和证据等级，不把它写成单条持续上升的性能曲线。','当前材料没有新的样本、模型、路由或训练；地图通路、推断假设、用户验收和现场事实继续分开。')}

for i,(dirname,title,conclusion,kind) in enumerate(events,1):
    folder=P/dirname
    metricrows=[r for r in numbers if r['event_id']==i]
    csvout(folder/'metrics.csv',metricrows,fields=list(numbers[0]))
    lines=[f'# 事件{i}｜{title}','',conclusion,'']
    if metricrows:
        lines+=['| 指标 | 原值 | 单位 | 口径 |','|---|---:|---|---|']+[f"| {r['metric']} | {r['value']} | {r['unit']} | {r['scope']} |" for r in metricrows]
    else:lines+=['本事件以地图或机制归纳为主，没有新增性能指标。']
    lines+=['','边界：'+notes[i][1]];write(folder/'metrics.md','\n'.join(lines)+'\n')
    write(folder/'caption_zh.md',f'# 中文图注草稿\n\n{title}。{notes[i][0]}\n\n图件类型：{kind}。{notes[i][1]}\n')
    write(folder/'story_note_zh.md',f'# 材料逻辑（不是讲稿或页面设计）\n\n{notes[i][0]}\n\n一句话结论：{conclusion}\n\n{notes[i][1]}\n')
    trace=['# 来源与适用范围','','本轮仅提取/重绘；原文件不改写，不运行求路。历史独立审核只支持其明确记录的范围；本轮作者整理检查不冒称新独立研究审核。','']
    for rel in event_sources[i]:
        t=next(t for t in traces if t['package_path']==rel)
        trace+=['- 文件：['+Path(rel).name+'](../'+rel+')','  - 阶段：'+t['source_experiment'],'  - 原固定归档：`'+t['fixed_archive']+'`；SHA256：`'+t['fixed_archive_sha256']+'`','  - 原成员：`'+t['original_member']+'`','  - 文件SHA256：`'+t['source_sha256']+'`']
    write(folder/'source_traceability.md','\n'.join(trace)+'\n')

csvout(P/'MASTER_NUMBERS_TABLE.csv',numbers)
write(P/'MASTER_NUMBERS_TABLE.md','# 关键数字汇总\n\n原值保留精度；展示可取两位。m为EPSG:32651投影几何长度；加权代价不冒称实际步程。完整来源字段见CSV。\n\n| 事件 | 指标 | 原值 | 单位 | 来源 |\n|---|---|---:|---|---|\n'+'\n'.join(f"| {r['event_id']} | {r['metric']} | {r['value']} | {r['unit']} | {r['source_experiment']} |" for r in numbers)+'\n')
csvout(P/'FIGURE_MANIFEST.csv',figrows);csvout(P/'SOURCE_MANIFEST.csv',traces)
write(P/'00_MASTER_INDEX.md','# 中期研究材料R2｜总索引\n\n仅整理已有研究材料，不制作PPT、讲稿或新增实验。全部地图源于冻结OSM，不是高德截图或现场照片。\n\n**事件5的拟定因果关系缺少历史证据，不作为已验证叙事；其余事件有可用主图。**\n\n离线查看：[图像总览](index.html)。先读[网页版GPT交接说明](HANDOFF_FOR_GPT_WEB.md)。\n\n'+ '\n\n'.join(f"{i}. [{title}]({dirname}/caption_zh.md)\n\n   {conclusion}\n\n   [主图]({dirname}/main_figure.png) · [数据]({dirname}/metrics.csv) · [来源]({dirname}/source_traceability.md)" for i,(dirname,title,conclusion,_) in enumerate(events,1))+'\n')
write(P/'HANDOFF_FOR_GPT_WEB.md','''# 给后续GPT的材料说明

这是证据与图件交付，不包含PPT、演讲稿、版式或美化建议。所有输出保持各自实验的起点、终点、用途、约束、分母和版本。PNG可直接阅读；SVG用于检查矢量细节；CSV与sources/保存关键数字和原报告。离线index.html不依赖外部字体、脚本或地图瓦片。

主图较强：事件1真实完整街区，事件6南广场前后对照，事件7草地原生步道修复，事件8北出口条件接入，事件9完整面路线，事件10局部改善与业务收益的区别。事件3是同一原始地图的图层解释，不是新增算法结果。事件11/12是有来源的机制归纳，不能当实验图。

**事件5必须先纠正叙事。** 现有历史文件不支持“只恢复北侧所以停在侧面”：旧R4已选南广场作焦点但新增边为0，REV1同时评估南北。目录中的历史图可作补充；没有把它伪装成不存在的“仅北侧”消融。准确可用的解释是“已认识到南侧步行面，但尚未把面内连接转成可路由边”。

稳定的有限结论：原生线网不足以覆盖南门接入；草地背景不应抹掉有效原生步道；已标步行面的受约束派生可以参加路线；完整合法面可减少特定查询绕行；局部新增对象不必改善业务路线。

必须保留的不确定：登记门不是现场门位认证；北出口始终exit且仅到门外；N1/N2连接无连续同层与实际通行证据；恢复和默认允许的空间不等于已证实可走；地图没有记录的障碍、权限、高差与当前状态未知；少量共享地图开发案例不是泛化验证。旧NYC训练匹配器与当前OSM规则/几何轨道分开，不可说整个项目从未训练模型。

切勿混用：北出口7.95米缺口与南门约55米线网距离；R4-REV1约1067米长起点路线与后来APP约149米近起点路线；NORTH-R1未修草地的1237米前缀与WALKABILITY-R2修复后的1166米前缀；F0几何长度与F1惩罚代价；全局82面与业务池36面；3/8→5/8局部机制与四业务任务；历史日志相似演示与截图唯一请求。

71.72米来自未舍入原值的差：不能用已四舍五入的1237.81−1166.10强行改为71.71。北出口331.65→299.53是F0，F1另有331.92→300.78，不能把两者拼成同一方法。

新整理材料等待GPT与用户审核。既有独立审查原文保留；本次没有新增独立代理审查或现场核验。旧封包和历史报告字节不变，不代表Parent Goal或人工验收通过。仅供私有研究交接；© OpenStreetMap contributors / ODbL，未取得公开Push批准。
''')
write(P/'LICENSE_AND_LIMITATIONS.md','''# 来源、许可与阅读范围

地图基于已取得的冻结OpenStreetMap数据；© OpenStreetMap contributors / ODbL，保留原有归属与数据源记录。没有调用Geoapify或其他外部服务，没有新增采集/费用。材料中Geoapify仅出现于原历史报告，不构成新的服务使用或再分发授权。

仅供用户私有研究材料审核，不授予整包新的公开发布权，不包含凭据、模型、大型原始数据或字体文件。原历史文档中的本机路径作为原件保留；新索引和新增文档采用包内相对路径。来源ZIP未全部重复内嵌；它们通过固定SHA及成员身份追溯，不能声称全历史工程离线可复现。但图件、表格及本轮解释可离线完整阅读。
''')
write(P/'MATERIAL_STATUS.md','# 整理状态\n\n12个事件目录齐全；11个事件具备相应用途的主图；事件5仅有补充证据图，拟定“仅北侧恢复”的因果叙事NOT_VERIFIED。11/12中的事件11/12是机制归纳图，不是成果地图。\n\n所有数字来自已固定历史文件；无新实验、求解、训练、下载、Git写入或Push。数字没有为叙事而修改。\n')

cardshtml=[]
for i,(dirname,title,conclusion,kind) in enumerate(events,1):
    imagefiles=[x for x in figrows if x['event_id']==i]
    gallery=''.join(f'<figure><a href="{r["output_file"]}" target="_blank"><img src="{r["output_file"]}" loading="lazy" alt="{html.escape(r["title"])}"></a><figcaption>{html.escape(r["figure_type"])} · {html.escape(r["regenerated_or_original"])}</figcaption></figure>' for r in imagefiles)
    cardshtml.append(f'<section id="e{i}"><h2>{i:02}　{html.escape(title)}</h2><p>{html.escape(conclusion)}</p>'+('<p class="warn">该事件的拟定因果叙事尚无充分证据；图仅作补充。</p>' if i==5 else '')+f'<p class="muted">{html.escape(notes[i][1])}</p>{gallery}<p><a href="{dirname}/metrics.md">数据摘要</a> · <a href="{dirname}/metrics.csv">CSV</a> · <a href="{dirname}/caption_zh.md">图注</a> · <a href="{dirname}/source_traceability.md">来源与SHA</a></p></section>')
nav=''.join(f'<a href="#e{i}">{i:02}</a>' for i in range(1,13))
write(P/'index.html','<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PG1中期研究材料R2</title><style>body{margin:0;background:#f5f4ef;color:#243330;font:17px/1.7 system-ui,"Microsoft YaHei",sans-serif}header,main{max-width:1240px;margin:auto;padding:28px}h1{font-size:30px}nav{position:sticky;top:0;background:#163e38;padding:8px;z-index:10;display:flex;gap:18px;justify-content:center}nav a{color:white}section{background:white;border-radius:12px;margin:28px 0;padding:24px;scroll-margin-top:65px}a{color:#12695f}img{display:block;width:100%;height:auto;border:1px solid #e5e7df}figure{margin:20px 0}figcaption,.muted{font-size:14px;color:#626a64}.warn{background:#fff0cf;padding:12px}h2{font-size:24px}</style><header><h1>复杂建筑入口接入与末段步行规划｜中期研究材料 R2</h1><p>12个材料事件，来源、数字与图注可逐项检查。只整理冻结研究；没有新实验或新路线。</p><p class="warn">事件5“只恢复北侧”的因果叙事未获证实。当前所有地图路线均有适用边界，不等于现场通行证明。</p><a href="00_MASTER_INDEX.md">总索引</a> · <a href="MASTER_NUMBERS_TABLE.csv">关键数字</a> · <a href="FIGURE_MANIFEST.csv">图像清单</a> · <a href="HANDOFF_FOR_GPT_WEB.md">给GPT的材料说明</a></header><nav>'+nav+'</nav><main>'+''.join(cardshtml)+'</main></html>')
write(P/'audit/AUTHOR_REVIEW.md','''# 作者整理检查

- 已读取本轮全部339行任务书，未运行算法、求路、训练或外部采集。
- R1材料包实际SHA和CRC核验；选用图件/报告的字节逐一按清单SHA检查。
- 真实目标way/161090899、南门node/6897141353、北exit node/6897145227与原坐标保持一致；背景来自纠错后R2源图，不采用旧错位算法叠加。
- 关键纠偏：事件5因果关系不充分；事件7未到门；事件8同层未知；事件9F0/F1和历史相似请求分开；事件10面池分母及局部业务任务分开。
- 重新绘图只读既有区域/路线/统计，未重新计算路径或新增候选。新图没有替换原成果。
- 历史独立审查原文保留，本轮没有新独立代理/人工审核，作者的包校验与浏览器阅读不冒称独立事实认证。
- 原封包、算法和历史文档没有改写；新文件全部位于独立R2目录。
''')
write(P/'audit/EVENT5_NARRATIVE_CORRECTION.md',(P/events[4][0]/'NARRATIVE_EVIDENCE_GAP.md').read_text(encoding='utf8'))
csvout(R/'audit/READ_DEPENDENCIES_SHA256.csv',[
    {'path':str(zpath),'sha256':sha(zpath.read_bytes())}, {'path':str(recon),'sha256':reconsha}, {'path':str(northzip),'sha256':northsha}])
write(R/'working/events.json',json.dumps(events,ensure_ascii=False,indent=2))
print(json.dumps({'events':len(events),'figures':len(figrows),'numbers':len(numbers),'evidence_files':len(traces),'event5':'NARRATIVE_NOT_VERIFIED'},ensure_ascii=False))
