"""Scientific static plots from actual solver polylines and frozen map features."""
from pathlib import Path
import argparse,json,html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from matplotlib.lines import Line2D
from shapely.geometry import shape
from shapely.geometry.polygon import orient
ROOT=Path(__file__).resolve().parents[1]
plt.rcParams.update({'font.family':'Microsoft YaHei','svg.fonttype':'none','axes.unicode_minus':False})
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def draw_geometry(ax,g,face,edge,alpha=1,lw=.5,z=1):
    if g.is_empty:return
    if g.geom_type in('MultiPolygon','MultiLineString','GeometryCollection'):
        for part in g.geoms:draw_geometry(ax,part,face,edge,alpha,lw,z)
    elif g.geom_type=='Polygon':
        g=orient(g,sign=1);verts=[];codes=[]
        for ring in[g.exterior,*g.interiors]:
            xy=list(ring.coords);verts.extend(xy);codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(xy)-2)+[MPath.CLOSEPOLY])
        ax.add_patch(PathPatch(MPath(verts,codes),facecolor=face,edgecolor=edge,alpha=alpha,lw=lw,zorder=z))
    elif g.geom_type in('LineString','LinearRing'):
        x,y=g.xy;ax.plot(x,y,color=edge,alpha=alpha,lw=lw,zorder=z)
def style(p):
    k=p.get('kind','');t=p.get('tags',{})
    if k=='PARK':return('#e9eed8','#d0d8bc',0)
    if 'GRASS'in k or k=='FLOWERBED'or t.get('landuse')=='grass':return('#d1e4b6','#b4cb95',1)
    if 'PEDESTRIAN'in k or 'WALKABLE'in k:return('#ecdfc4','#baa67f',2)
    if 'WATER'in k:return('#c2dfe8','#8aafbf',3)
    if 'BUILDING'in k or t.get('building'):return('#bdb7aa','#918c83',4)
    if 'RESTRICT'in k or 'BARRIER'in k:return('#edcdd3'if'BARRIER'not in k else'none','#9c5464',5)
    if k=='ROAD':return('none','#aaa798',6)
    if k=='NATIVE_WALKWAY':return('none','#5c8ca5',7)
    return('none','#bec5b2',1)
def background(ax,view,window):
    features=view.get('map_layers',[])
    if isinstance(features,dict):features=features['features']
    for f in sorted(features,key=lambda f:style(f.get('properties',{}))[2]):
        g=shape(f['geometry']);bounds=g.bounds
        if not bounds or bounds[2]<window[0]or bounds[0]>window[1]or bounds[3]<window[2]or bounds[1]>window[3]:continue
        fc,ec,z=style(f.get('properties',{}));draw_geometry(ax,g,fc,ec,.95,.55,z)
    ax.set_facecolor('#f7f4e9')
def bounds(results,pad=25):
    xy=[p for r in results for s in r['route']['segments']for p in s['xy']]
    xs=[p[0]for p in xy];ys=[p[1]for p in xy]
    return min(xs)-pad,max(xs)+pad,min(ys)-pad,max(ys)+pad
def route(ax,r,muted=False):
    for s in r['route']['segments']:
        color='#6c7775'if muted else'#195fa2'if s['layer']=='native'else'#833db4'if s.get('geometry_kind')=='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE'else'#008a7b'if s['layer']=='derived'else'#df622f'
        x,y=zip(*s['xy']);ax.plot(x,y,color='white',lw=4,zorder=11);ax.plot(x,y,color=color,lw=2.2,ls='--'if muted else'-',zorder=12)
    a=r['start']['network_xy'];d=r['door']['xy'];ax.scatter(*a,s=55,c='#21428d',edgecolors='white',zorder=14);ax.scatter(*d,s=140,c='#b7382f',marker='^'if r.get('mechanism')else'*',edgecolors='white',zorder=14)
def paired(case,a,b,view,out):
    fig,axs=plt.subplots(1,2,figsize=(14,7));box=bounds([a,b]);width=box[1]-box[0]
    old_title='旧：边缘带（BAND-C，同Ω复检）'if a.get('mechanism')else'旧：3米边缘带'
    for ax,r,title in zip(axs,[a,b],[old_title,'新：完整合法步行面']):
        background(ax,view,box)
        for f in b.get('mapped_faces',[]):
            if f.get('omega'):draw_geometry(ax,shape(f['omega']),'#8eb6dd','#3e689c',.14,.7,8)
        route(ax,r);ax.set_xlim(box[:2]);ax.set_ylim(box[2:]);ax.set_aspect('equal');ax.ticklabel_format(style='plain',useOffset=False);ax.tick_params(labelsize=7)
        ax.set_title(f"{title}\n{r['route']['length_m']:.2f}米 · 代价{r['route']['cost_weighted_m']:.2f}",fontsize=12)
        length=10 if width<150 else 50 if width<600 else 100
        x=box[0]+width*.07;y=box[2]+(box[3]-box[2])*.06;ax.plot([x,x+length],[y,y],c='#222',lw=2,zorder=15);ax.text(x,y+3,f'{length}米',fontsize=8,zorder=15)
    identity='相同原接点对（非入口）'if a.get('mechanism')else'相同原起点、原登记门与用途'
    fig.suptitle(case+f"｜{identity}；缩短{a['route']['length_m']-b['route']['length_m']:.2f}米",fontsize=14)
    q=a.get('input',{});fig.text(.5,.925,f"{q.get('start_id','')} → {q.get('door_id','')}　{q.get('method','')}　{q.get('purpose','')}",ha='center',fontsize=8)
    legends=[Line2D([0],[0],color=c,lw=3,label=t)for c,t in[('#195fa2','原生步道'),('#008a7b','旧面派生段'),('#833db4','完整面派生段'),('#df622f','条件假设段')]]
    info=view.get('source_info',{});stamp=info.get('source_timestamp','快照时间未知');short=info.get('source_sha256','')[:12]
    fig.legend(handles=legends,loc='lower center',bbox_to_anchor=(.5,.047),ncol=4,frameon=False);fig.text(.02,.015,f'© OpenStreetMap contributors · {stamp} · SHA {short} · EPSG:32651米 · 非现场通行证明',fontsize=7)
    fig.subplots_adjust(bottom=.12,top=.86,wspace=.15)
    for suffix in('.svg','.png'):fig.savefig(out.with_suffix(suffix),dpi=160,facecolor='white')
    plt.close(fig)
def main(suite):
    target=ROOT/'visuals';target.mkdir(exist_ok=True)
    summary=read(ROOT/'runs'/suite/'summary.json');cards=[]
    for case,label in[('APP-01','博物馆南门 F0'),('APP-03','博物馆北出口门外 F0'),('APP-07','图书馆登记门 F0')]:
        a=read(ROOT/'runs'/suite/(case+'-EDGE_BAND.json'));b=read(ROOT/'runs'/suite/(case+'-FULL_FACE.json'))
        view=read(ROOT/'data/map_views'/(a['input']['scene_id']+'.json'));stem=target/case
        paired(label,a,b,view,stem);cards.append((case,label,a['route']['length_m'],b['route']['length_m']))
    extra=ROOT/'runs/extra_and_concurrency_R1'
    if(extra/'EXTRA-HISTORICAL-FULL_FACE-F1.json').exists():
        a=read(extra/'EXTRA-HISTORICAL-EDGE_BAND-F1.json');b=read(extra/'EXTRA-HISTORICAL-FULL_FACE-F1.json')
        paired('原日志长绕行相似演示（未唯一绑定截图）',a,b,read(ROOT/'data/map_views/sh-huangpu-01.json'),target/'historical_long')
        cards.append(('historical_long','原日志长绕行相似演示',a['route']['length_m'],b['route']['length_m']))
    mechanism=ROOT/'runs/face_pairs_R1'
    if mechanism.exists():
        for sid,label in[('2153738','北步行面绕洞：局部机制点对'),('2385771','南步行面：局部机制点对')]:
            raw=read(next(mechanism.glob('*relation_'+sid+'_1.json')))
            q=raw['query'];start=q['source']['xy'];end=q['target']['xy']
            def proxy(result,points):
                return {'mechanism':True,'input':{'start_id':q['source']['id'],'door_id':q['target']['id'],'purpose':q['source_area_id'],'method':'局部均匀代价'},'start':{'network_xy':start},'door':{'xy':end},'route':{'segments':[{'xy':points,'layer':'derived'}],'length_m':result['length_m'],'cost_weighted_m':result['length_m']}}
            a=proxy(raw['old'],raw['old']['points']);b=proxy(raw['full_face'],raw['full_face']['points'])
            b['route']['segments'][0]['geometry_kind']='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE'
            b['mapped_faces']=read(ROOT/'runs'/suite/'APP-01-FULL_FACE.json').get('mapped_faces',[])
            case='mechanism_'+sid;paired(label,a,b,read(ROOT/'data/map_views/sh-huangpu-01.json'),target/case)
            cards.append((case,label+'（BAND-C同Ω约束；三角不是门）',a['route']['length_m'],b['route']['length_m']))
    rows=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>'for k in['case_id','method','edge_status','edge_length_m','full_length_m','saving_length_m','full_assumed_m'])+'</tr>'for r in summary['positive_comparisons'])
    pictures=''.join(f'<section><h2>{label}</h2><p>{a:.2f} → {b:.2f}米，缩短{a-b:.2f}米。<a href="visuals/{case}.svg">打开矢量图</a> · <a href="visuals/{case}.png">PNG</a></p><img src="visuals/{case}.svg"></section>'for case,label,a,b in cards)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>完整步行面：旧新真实结果</title><style>body{font:16px/1.65 "Microsoft YaHei",sans-serif;max-width:1450px;margin:32px auto;padding:0 20px;background:#f7f6f0;color:#233d36}section{background:white;padding:20px;margin:24px 0;border:1px solid #d4ddd6;border-radius:10px}img{width:100%}table{border-collapse:collapse;font-size:13px}td,th{padding:8px;border:1px solid #ccc}a{color:#126959}</style><h1>完整步行面参与真实全程寻路</h1><p>这些图片来自实际求解几何。<a href="http://127.0.0.1:53431/">进入实际计算APP</a>（需按README启动本机服务） · <a href="README.md">运行说明</a> · <a href="RESULTS.md">完整结果与边界</a></p><p>灰色建筑、绿色草地、黄色已标步行面仍保留；蓝色为原生步道，紫色为完整面派生段，橙色为缺标条件假设。新边是地图面内计算路线，不是新发现的真实道路。北门仍为exit。</p>'''+pictures+'<section><h2>固定8请求：同起终点主配对</h2><table><tr><th>请求</th><th>方法</th><th>旧状态</th><th>旧长度米</th><th>新长度米</th><th>缩短米</th><th>新假设段米</th></tr>'+rows+'</table><p>面内局部机制7点对另见RESULTS；不与完整APP请求混合分母。不代表现场公众可以通行。</p></section></html>'
    (ROOT/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'figures':len(cards),'formats':['SVG','PNG'],'real_result_suite':suite}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--suite',default='main_matrix_R2');main(p.parse_args().suite)
