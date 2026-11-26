"""Static same-scale four-layer maps; all coordinates originate in frozen OSM."""
import json, argparse, math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath
from matplotlib.collections import LineCollection
OUT=Path(__file__).resolve().parents[1]
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,'svg.fonttype':'none'})
PAPER='#FCFAF7';INK='#2D3238'

def style(p,legacy=False):
    fs=p['families']; t=p['tags']
    if legacy:
        if 'building'in fs:return '#cac4b7','#a29b8d',.45,2
        if 'grass'in fs:return '#d5e5b9','#adc28f',.4,0
        if 'water'in fs:return '#c2dee4','#91bdc7',.4,0
        if 'vehicle_road'in fs:return 'none','#a9a696',1.0,3
        if 'pedestrian_line'in fs:return 'none','#5b8da4',.65,4
        if 'barrier'in fs:return 'none','#a76070',.8,5
        return 'none','#b4bfac',.35,1
    if 'building'in fs:return '#F5D9B8','#70757A',.5,2
    if 'grass'in fs or 'vegetation_park'in fs:return '#D7D3EA','#8177A8',.4,0
    if 'water'in fs:return '#D3EAF5','#5B9FBE',.5,0
    if 'pedestrian_area'in fs or 'road_area'in fs:return '#D3EAF5','#5B9FBE',.5,1
    if 'vehicle_road'in fs:return 'none',INK,1.4 if t.get('highway')in {'primary','secondary','trunk'}else .75,3
    if 'pedestrian_line'in fs:return 'none','#5B9FBE',1.0,4
    if 'crossing'in fs:return '#B97589','#B97589',.8,6
    if 'barrier'in fs or 'restriction'in fs:return 'none','#B97589',1,5
    return 'none','#70757A',.3,1

def paint(ax,g,fill,stroke,lw,z,alpha=1,dashed=False):
    if not g:return
    typ=g['type']; c=g.get('coordinates')
    if typ=='GeometryCollection':
        for x in g['geometries']:paint(ax,x,fill,stroke,lw,z,alpha)
    elif typ=='Point':ax.plot(c[0],c[1],marker='o',markersize=2.6,color=stroke,zorder=z,alpha=alpha)
    elif typ=='MultiPoint':
        for pt in c:paint(ax,{'type':'Point','coordinates':pt},fill,stroke,lw,z,alpha,dashed)
    elif typ in ['LineString','MultiLineString']:
        ax.add_collection(LineCollection([c]if typ=='LineString'else c,colors=stroke,linewidths=lw,zorder=z,alpha=alpha,linestyles='dashed'if dashed else'solid'))
    elif typ in ['Polygon','MultiPolygon']:
        polys=[c]if typ=='Polygon'else c
        for poly in polys:
            vertices=[]; codes=[]
            for ring in poly:
                vertices+=ring;codes += [MPath.MOVETO]+[MPath.LINETO]*(len(ring)-2)+[MPath.CLOSEPOLY]
            if vertices:ax.add_patch(PathPatch(MPath(vertices,codes),facecolor=fill,edgecolor=stroke,lw=lw,zorder=z,alpha=alpha,linestyle='--'if dashed else '-'))

def inbounds(g,b):
    def points(c):
        if c and isinstance(c[0],(int,float)):yield c
        else:
            for x in c:yield from points(x)
    if not g.get('coordinates'):return False
    pts=list(points(g['coordinates']))
    return bool(pts)and max(p[0]for p in pts)>=b[0]and min(p[0]for p in pts)<=b[2]and max(p[1]for p in pts)>=b[1]and min(p[1]for p in pts)<=b[3]

def render(path):
    d=json.loads(path.read_text(encoding='utf8'));i=d['info'];b=i['block_bounds_xy']; cp=path.parent/'current_graph.json';current=json.loads(cp.read_text(encoding='utf8'))if cp.exists()else{};fig,axs=plt.subplots(2,2,figsize=(16,13),facecolor=PAPER)
    titles=['A 原始源地图 · 全部可定位源对象','B 实际导入规则 · 上下文对象','C 路由语义 · 准入原生边与合法面 Ω','D 历史 R1 输出 · 原样式复现与真实旧路线']
    for n,ax in enumerate(axs.flat):
        ax.set_facecolor(PAPER); ax.set_xlim(b[0],b[2]);ax.set_ylim(b[1],b[3]);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
        ax.set_title(titles[n],loc='left',fontsize=12,color=INK,pad=12)
        for f in d['features']:
            p=f['properties'];g=f.get('import_geometry')if n==1 else f.get('diagnostic_geometry')if n==3 and f.get('diagnostic_geometry')else f['geometry']
            if g is None:continue
            if not inbounds(g,b):continue
            if n==1 and not p['imported_context']:continue
            if n==3 and not p['diagnostic_render']:continue
            sty=style(p,n==3)
            paint(ax,g,*sty,alpha=.35 if n==2 else 1)
        if n==1:
            for f in d.get('imported_only_features',[]):
                if inbounds(f['geometry'],b):paint(ax,f['geometry'],'none','#B97589',.85,6,dashed=True)
        if n==2:
            for f in d['legal_faces']:paint(ax,f['geometry'],'#D3EAF5','#5B9FBE',.55,5,.5)
            for f in d['native_edges']:paint(ax,f['geometry'],'none','#8177A8'if f['properties'].get('road_axis')else'#5B9FBE',.9,6,dashed=bool(f['properties'].get('road_axis')))
            for f in d['supplemental_graph_edges']:paint(ax,f['geometry'],'none','#B97589',.8,7)
            for r in current.get('interfaces',[]):
                if r.get('geometry')and inbounds(r['geometry'],b):paint(ax,r['geometry'],'none','#5B9FBE',.45,8,.6)
            for r in current.get('seams',[]):
                if r.get('geometry')and inbounds(r['geometry'],b):paint(ax,r['geometry'],'none','#B97589'if r.get('accepted')is False else'#5B9FBE',.8,9,.4 if r.get('accepted')is False else .9,dashed=True)
        if n==3 and d.get('historical_route'):
            for s in d['historical_route']['segments']:
                g={'type':'LineString','coordinates':s['xy']};paint(ax,g,'none',PAPER,4,8);paint(ax,g,'none','#5B9FBE'if s.get('layer')=='native'else'#B97589',2.1,9)
        if n!=3:
            occupied=set()
            for f in d['features']:
                p=f['properties'];g=f['geometry'];name=p['tags'].get('name')
                if 'vehicle_road'not in p['families']or not name or g['type']!='LineString':continue
                cs=g['coordinates']; a=cs[len(cs)//2]; cell=(int((a[0]-b[0])/130),int((a[1]-b[1])/70))
                if not(b[0]<a[0]<b[2]and b[1]<a[1]<b[3])or cell in occupied:continue
                occupied.add(cell);ax.text(*a,name,fontsize=6.5,color=INK,zorder=12,bbox={'facecolor':PAPER,'edgecolor':'none','pad':.6,'alpha':.85})
        sx=b[0]+35;sy=b[1]+38;ax.plot([sx,sx+100],[sy,sy],color=INK,lw=2,zorder=15);ax.text(sx,sy+9,'100 m',fontsize=8,color=INK,zorder=15)
        ax.annotate('N',xy=(b[2]-35,b[3]-55),xytext=(b[2]-35,b[3]-105),ha='center',fontsize=10,arrowprops={'arrowstyle':'->','color':INK},color=INK)
        ax.plot(*i['target_xy'],marker='+',color='#B97589',markersize=9,zorder=15)
        for sp in ax.spines.values():sp.set_color('#DDE3E7')
    fig.suptitle(i['label']+' · '+i['scene_id']+' · 冻结开发集同尺度街区对照',fontsize=19,color=INK,y=.985)
    history='历史真实路线 '+i['history'].get('run_id','')if d.get('historical_route')else'无原登记门 / 本轮无对应 APP 路线'
    fig.text(.04,.045,'粗道路线：primary / secondary / trunk；细线：residential / service 等。线宽非实测路宽；原生边为规则回放，完整 VG 未重建。',fontsize=9,color=INK)
    fig.text(.04,.027,history+'；本轮未求路。C蓝线为人行源线，紫虚线为准入道路轴（非独立人行道）；B玫瑰虚框为UNKNOWN导入几何。',fontsize=9,color=INK)
    fig.text(.04,.009,'© OpenStreetMap contributors · ODbL · source EPSG:4326 → EPSG:32651 · '+str(i['source_timestamp'])+' · SHA256 '+i['source_sha256'][:16],fontsize=9,color='#70757A')
    fig.subplots_adjust(left=.035,right=.975,bottom=.08,top=.935,hspace=.15,wspace=.07)
    target=OUT/'maps'/i['scene_id'];target.parent.mkdir(exist_ok=True)
    fig.savefig(str(target)+'.png',dpi=150,facecolor=PAPER);fig.savefig(str(target)+'.svg',facecolor=PAPER);plt.close(fig)
    print(str(target)+'.png',flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--scene');a.add_argument('--out',type=Path);args=a.parse_args()
    if args.out:OUT=args.out.resolve()
    for p in sorted((OUT/'data').glob('*/scene.json')):
        if not args.scene or p.parent.name==args.scene:render(p)
