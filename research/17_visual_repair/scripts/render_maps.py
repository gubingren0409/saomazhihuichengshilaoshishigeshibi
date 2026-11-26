"""Render frozen context and saved overlays. No graph construction or solver imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch, Patch
from matplotlib.path import Path as PlotPath
from shapely.geometry import shape, box

ROOT=Path(__file__).resolve().parents[1]
PAPER='#FCFAF7'; INK='#2D3238'; BLUE='#5B9FBE'; ROSE='#B97589'; VIOLET='#8177A8'; GOLD='#D49757'
plt.rcParams.update({'font.family':'Microsoft YaHei','svg.fonttype':'none',
                     'svg.hashsalt':'PG1-MAP-CONTEXT-VISUAL-REPAIR-R1',
                     'axes.unicode_minus':False,'font.size':10,'figure.facecolor':PAPER,
                     'axes.facecolor':'#FFFDFC','text.color':INK,'axes.labelcolor':INK})

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def polygon_path(rings):
    vertices=[]; codes=[]
    for i,ring in enumerate(rings):
        pts=[tuple(p[:2])for p in ring]
        if len(pts)<4:continue
        signed=sum(a[0]*b[1]-b[0]*a[1]for a,b in zip(pts,pts[1:]))
        if (i==0 and signed<0)or(i>0 and signed>0):pts.reverse()
        vertices+=pts;codes+=[PlotPath.MOVETO]+[PlotPath.LINETO]*(len(pts)-2)+[PlotPath.CLOSEPOLY]
    return PlotPath(vertices,codes) if vertices else None

def style(feature):
    fam=set(feature['families']);tags=feature['tags'];highway=tags.get('highway','')
    if 'buildings'in fam:return {'fill':'#d1cfca','edge':'#858782','width':.75,'z':4}
    if 'water'in fam:return {'fill':'#D3EAF5','edge':BLUE,'width':1.1,'z':2}
    if 'vegetation'in fam:return {'fill':'#e7efde'if tags.get('landuse')in{'grass','meadow'}else'#dfe9d6','edge':'#99aa91','width':.8,'z':1}
    if 'road_areas'in fam:return {'fill':'#e1e0dc','edge':'#919497','width':.8,'z':3}
    if 'pedestrian_areas'in fam:return {'fill':'#F5D9B8','edge':'#bca98e','width':.9,'z':3}
    if 'barriers'in fam:return {'fill':'none','edge':VIOLET,'width':1.8,'z':10}
    if 'railway'in fam:return {'fill':'none','edge':'#777078','width':1.7,'z':6}
    if 'crossings'in fam:return {'fill':ROSE,'edge':ROSE,'width':2.3,'z':9,'marker':'x'}
    if 'native_walkways'in fam:return {'fill':'none','edge':BLUE,'width':2.0,'z':8}
    if 'road_centerlines'in fam:
        widths={'motorway':4.5,'trunk':4.5,'primary':4.2,'secondary':3.4,'tertiary':3.0,'residential':2.4,'living_street':2.3,'unclassified':2.2,'service':1.6}
        return {'fill':'none','edge':'#555b61','width':widths.get(highway,1.5),'z':7}
    if 'traffic_facilities'in fam:return {'fill':INK,'edge':INK,'width':1.3,'z':10,'marker':'s'}
    if feature.get('geometry',{}).get('type')in{'Polygon','MultiPolygon'}:
        return {'fill':'none','edge':'#aaa89e','width':.9,'z':2}
    return {'fill':'#b1b0a7','edge':'#757971','width':.7,'z':5}

def draw_geometry(ax,g,s,gid):
    typ=g['type'];c=g.get('coordinates');artists=[]
    if typ=='Polygon':
        p=polygon_path(c)
        if p is not None:
            a=PathPatch(p,facecolor=s['fill'],edgecolor=s['edge'],linewidth=s['width'],zorder=s['z']);ax.add_patch(a);artists.append(a)
    elif typ=='MultiPolygon':
        for part in c:artists+=draw_geometry(ax,{'type':'Polygon','coordinates':part},s,gid)
    elif typ in {'LineString','MultiLineString'}:
        for pts in ([c]if typ=='LineString'else c):
            if len(pts)<2:continue
            x,y=zip(*[p[:2]for p in pts])
            a,=ax.plot(x,y,color=s['edge'],linewidth=s['width'],zorder=s['z'],solid_capstyle='round');artists.append(a)
    elif typ in {'Point','MultiPoint'}:
        for p in ([c]if typ=='Point'else c):
            a,=ax.plot(*p[:2],marker=s.get('marker','o'),markersize=3.5,color=s['edge'],zorder=s['z'],linestyle='none');artists.append(a)
    elif typ=='GeometryCollection':
        for part in g['geometries']:artists+=draw_geometry(ax,part,s,gid)
    for i,a in enumerate(artists):a.set_gid(getattr(ax,'_pg1_panel_prefix','')+gid+'_'+str(i))
    return artists

def draw_base(ax,context,extent):
    clip=box(*extent);ids=[];labels=[];label_boxes=[]
    features=sorted(context['features'],key=lambda f:(style(f)['z'],f['source_id']))
    for f in features:
        geom=f.get('geometry')
        if not geom:continue
        g=shape(geom)
        if g.is_empty or not g.intersects(clip):continue
        s=style(f)
        if 'road_centerlines'in f['families']and geom['type']in{'LineString','MultiLineString'}:
            draw_geometry(ax,geom,{**s,'edge':'#FFFDFC','width':s['width']+1.6,'z':s['z']-.2},'casing_'+f['source_id'].replace('/','_'))
        artists=draw_geometry(ax,geom,s,'src_'+f['source_id'].replace('/','_'))
        tags=f['tags']
        if tags.get('tunnel') not in (None,'no') or tags.get('location')=='underground' or str(tags.get('layer','0')).startswith('-'):
            for artist in artists:
                if isinstance(artist,Line2D):artist.set_linestyle((0,(2,3)))
        if artists:ids.append(f['source_id'])
    # Names come from source tags. Stable screen-space collision control affects labels only.
    named=[f for f in features if f['tags'].get('name')and f.get('geometry')]
    named.sort(key=lambda f:(0 if 'road_centerlines'in f['families']else 1, f['source_id']))
    for f in named:
        g=shape(f['geometry'])
        if not g.intersects(clip):continue
        visible=g.intersection(clip)
        if visible.is_empty:continue
        road='road_centerlines'in f['families'];ped='native_walkways'in f['families']
        if road or ped:
            if visible.geom_type=='MultiLineString':visible=max(visible.geoms,key=lambda a:a.length)
            p=visible.interpolate(.5,normalized=True)if visible.geom_type=='LineString'else visible.representative_point()
        else:p=visible.representative_point()
        name=f['tags']['name'].replace('\n',' ')
        if f['tags'].get('tunnel')not in(None,'no'):name+=' · 隧道'
        elif f['tags'].get('bridge')not in(None,'no'):name+=' · 桥'
        if f['tags'].get('oneway')in{'yes','1','-1'}:name+=' · 单行'
        x,y=p.x,p.y
        span=extent[2]-extent[0];w=min(span*.42,len(name)*span*.017);h=(extent[3]-extent[1])*.033
        bounds=(x-w/2,y-h/2,x+w/2,y+h/2)
        if any(not(bounds[2]<b[0]or bounds[0]>b[2]or bounds[3]<b[1]or bounds[1]>b[3])for b in label_boxes):continue
        label_boxes.append(bounds)
        txt=ax.text(x,y,name,ha='center',va='center',fontsize=9.5 if road else 8,color=INK if road else '#66675f',zorder=12,clip_on=True,
                    path_effects=[patheffects.withStroke(linewidth=2.5,foreground=PAPER)])
        txt.set_gid(getattr(ax,'_pg1_panel_prefix','')+'label_'+f['source_id'].replace('/','_'));labels.append(f['source_id'])
    ax.set_xlim(extent[0],extent[2]);ax.set_ylim(extent[1],extent[3]);ax.set_aspect('equal',adjustable='box')
    ax.tick_params(labelsize=8);ax.ticklabel_format(useOffset=False,style='plain')
    for a in ax.spines.values():a.set_color('#9da0a1')
    ax.set_xlabel('EPSG:32651 东向 / m',fontsize=9)
    scale=50 if extent[2]-extent[0]>220 else 20
    x=extent[0]+(extent[2]-extent[0])*.055;y=extent[1]+(extent[3]-extent[1])*.055
    ax.plot([x,x+scale],[y,y],color=INK,lw=2.0,zorder=20)
    ax.text(x+scale/2,y+(extent[3]-extent[1])*.018,f'{scale} m',ha='center',fontsize=9,zorder=20,
            path_effects=[patheffects.withStroke(linewidth=3,foreground=PAPER)])
    ax.annotate('N',xy=(.945,.94),xytext=(.945,.865),xycoords='axes fraction',textcoords='axes fraction',ha='center',arrowprops={'arrowstyle':'->','color':INK},fontsize=10)
    return {'source_ids':sorted(set(ids)),'label_source_ids':sorted(set(labels)),
            'base_object_sha256':canonical([f for f in context['features']if f['source_id']in ids]),'extent_xy':extent}

def draw_overlay(ax,window,variant,query):
    graph=window['variants'][variant];byid={e['edge_id']:e for e in graph['edges']};edge_ids=[]
    for e in graph['edges']:
        pts=e['xy'];x,y=zip(*pts);hyp=e.get('hypothesis',False);schematic=e.get('geometry_status')=='SCHEMATIC'
        color=GOLD if e['layer']=='hypothesis'else VIOLET if e['layer']=='tag_derived'else ROSE if e['layer']=='crossing'else BLUE if e['layer']=='native'else INK
        artist,=ax.plot(x,y,color=color,lw=1.6 if e['layer']!='road_axis'else 1.8,ls=(0,(5,3))if schematic or hyp else '-',zorder=14,alpha=.9)
        artist.set_gid(getattr(ax,'_pg1_panel_prefix','')+'edge_'+e['edge_id'].replace('/','_').replace(':','_'));edge_ids.append(e['edge_id'])
    result=query['results'][variant];route_ids=result.get('edge_ids',[])
    for eid in route_ids:
        e=byid[eid];x,y=zip(*e['xy']);dashed=e.get('geometry_status')=='SCHEMATIC'or e.get('hypothesis',False)
        a,=ax.plot(x,y,color=INK,lw=3.1,ls=(0,(5,3))if dashed else '-',zorder=16,
                  path_effects=[patheffects.Stroke(linewidth=5,foreground=PAPER),patheffects.Normal()])
        a.set_gid(getattr(ax,'_pg1_panel_prefix','')+'saved_route_'+eid.replace('/','_').replace(':','_'))
    bind=query['bindings'][variant]
    for key,col,symbol in [('start',INK,'起'),('end',ROSE,'终')]:
        xy=graph['nodes'].get(bind[key])or window.get('nodes',{}).get(bind[key])
        if xy:
            ax.scatter(*xy,s=28,c=col,edgecolors=PAPER,linewidths=1,zorder=19)
            ax.annotate(symbol,xy,xytext=(5,7),textcoords='offset points',color=col,fontsize=10,zorder=20)
    return {'variant':variant,'query_id':query['query_id'],'edge_ids':edge_ids,'route_edge_ids':route_ids,
            'frozen_edges_sha256':canonical(graph['edges']),'status':result['status']}

def legend(fig):
    handles=[Patch(facecolor='#d1cfca',edgecolor='#858782',label='原始建筑/内环保留'),
             Line2D([0],[0],color='#555b61',lw=2.5,label='道路中心线/分级符号'),
             Line2D([0],[0],color=BLUE,lw=2,label='原生步行线'),
             Line2D([0],[0],color=ROSE,lw=2,marker='o',label='原生过街/设施'),
             Patch(facecolor='#dfe9d6',edgecolor='#99aa91',label='绿化/草地'),
             Patch(facecolor='#F5D9B8',label='登记步行面/广场'),
             Patch(facecolor='#D3EAF5',label='源水体'),
             Line2D([0],[0],color='#777078',lw=1.7,ls=':',label='铁路/地下线（源标签）'),
             Line2D([0],[0],color=VIOLET,lw=2,label='墙/围栏等障碍'),
             Line2D([0],[0],color=VIOLET,lw=2,ls='--',label='标签侧向 SCHEMATIC'),
             Line2D([0],[0],color=GOLD,lw=2,ls='--',label='条件侧道 HYPOTHESIS'),
             Line2D([0],[0],color=INK,lw=3,label='已保存查询路线（假设段虚线）')]
    fig.legend(handles=handles,loc='lower center',ncol=4,fontsize=9,frameon=False,bbox_to_anchor=(.5,.033))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);args=ap.parse_args()
    global_root=args.root
    data=read(global_root/'data/frozen/maps/trial_map_data.json');manifest=[]
    for w in data['windows']:
        context=read(global_root/'data/context'/f"{w['window_id']}.json")
        full=w['bounds_xy'];q=w['queries'][0]
        xs=[p[0]for e in w['variants']['R0']['edges']if e['source_id']==w['selected_road_id']for p in e['xy']]
        ys=[p[1]for e in w['variants']['R0']['edges']if e['source_id']==w['selected_road_id']for p in e['xy']]
        cx=(min(xs)+max(xs))/2 if xs else(full[0]+full[2])/2;cy=(min(ys)+max(ys))/2 if ys else(full[1]+full[3])/2
        half=75;cx=max(full[0]+half,min(full[2]-half,cx));cy=max(full[1]+half,min(full[3]-half,cy));detail=[cx-half,cy-half,cx+half,cy+half]
        specs=[('context_full',[None],full),('R0_context_overlay',['R0'],full),('R1_context_overlay',['R1'],full),('R2_context_overlay',['R2'],full),('R0_R1_R2_same_extent',['R0','R1','R2'],full),('local_detail',['R0','R1','R2'],detail)]
        for name,variants,extent in specs:
            cols=len(variants);fig,axes=plt.subplots(1,cols,figsize=(18,9)if cols==3 else(12,10),squeeze=False)
            fig.subplots_adjust(left=.04,right=.985,top=.84,bottom=.20,wspace=.05)
            title=context['label']+' [数据窗口] · '+('路侧150m局部'if name=='local_detail'else'固定320m街区上下文')
            fig.suptitle(title,fontsize=17,y=.965)
            meta=f"{w['selected_road_id']} · 来源 {w['source_timestamp']} · SHA {w['source_sha256'][:16]}… · 只读重绘，无新增求路"
            fig.text(.5,.918,meta,ha='center',fontsize=9,color='#70757A')
            panels=[]
            for ax,v in zip(axes.flat,variants):
                ax._pg1_panel_prefix='panel_'+(v or 'A')+'_'
                base=draw_base(ax,context,extent);overlay=draw_overlay(ax,w,v,q)if v else None
                ax.set_title('A · 冻结原始上下文（不按路由准入删对象）'if v is None else v+' · '+q['results'][v]['status'],fontsize=11,pad=10)
                panels.append({'variant':v,'base':base,'overlay':overlay})
            assert len({p['base']['base_object_sha256']for p in panels})==1
            legend(fig)
            fig.text(.5,.012,'© OpenStreetMap contributors · 冻结源无道路面/已核验路宽；中心线线宽仅为符号。SCHEMATIC不是物理人行道，未伪造道路结构。',ha='center',fontsize=9,color='#70757A')
            folder=global_root/'figures'/w['window_id'];folder.mkdir(parents=True,exist_ok=True)
            fig.canvas.draw()
            fw,fh=fig.get_size_inches()
            for ax,panel in zip(axes.flat,panels):
                pos=ax.get_position();sx=72*fw*pos.width/(extent[2]-extent[0]);sy=-72*fh*pos.height/(extent[3]-extent[1])
                panel['world_to_svg_points']={'scale_x':sx,'scale_y':sy,
                    'offset_x':72*fw*pos.x0-sx*extent[0],
                    'offset_y':72*fh*(1-pos.y0)-sy*extent[1],
                    'svg_id_prefix':'panel_'+(panel['variant']or'A')+'_',
                    'purpose':'Independent SVG overlay vertex check; SVG serialization rounds screen units, frozen world coordinates remain unchanged.'}
            files=[]
            for ext in ['png','svg']:
                p=folder/f'{name}.{ext}';fig.savefig(p,dpi=160,metadata={'Date':None}if ext=='svg'else None);files.append({'path':p.relative_to(global_root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
            plt.close(fig)
            manifest.append({'window_id':w['window_id'],'figure':name,'query_id':q['query_id'],'extent_xy':extent,'equal_xy_aspect':True,'panels':panels,'files':files})
    (global_root/'audit/static_render_membership.json').write_text(json.dumps({'scope':'Actual generated source artists/labels and exact saved edgeIDs; no graph or route computation','figures':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'figures':len(manifest),'PNG':len(manifest),'SVG':len(manifest),'solver_calls_added':0}))

if __name__=='__main__':main()
