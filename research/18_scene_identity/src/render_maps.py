"""Target-anchored map rendering from source and frozen diagnostics; never plan routes."""
import hashlib
import json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import shape, box, LineString
import cartography as c

ROOT=Path(__file__).resolve().parents[1]
PINK='#E8C7D3';ROSE='#B97589';GOLD='#D49757';INK='#2D3238';PAPER='#FCFAF7'

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def canonical(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def emphasize_target(ax,scene,extent,inspect=False):
    target=scene['target'];g=target['geometry'];clip=box(*extent)
    c.draw_geometry(ax,g,{'fill':PINK,'edge':ROSE,'width':2.1,'z':18},'verified_museum_way_161090899')
    p=shape(g).representative_point()
    span=extent[2]-extent[0]
    # Force the intended target label above generic POIs; never let name collision hide it.
    right_side=(p.x-extent[0])/span>.62
    ax.annotate('上海博物馆\n人民广场馆 · way/161090899',(p.x,p.y),
                xytext=((-20,-45)if right_side else(26,26)),textcoords='offset points',ha='right'if right_side else'left',
                color=INK,fontsize=10.5,fontweight='bold',zorder=30,
                bbox={'facecolor':PAPER,'edgecolor':ROSE,'alpha':.95,'pad':3},
                arrowprops={'arrowstyle':'-','color':ROSE,'lw':1.2})
    markers=[]
    for door in target['doors']:
        xy=door['xy'];south=door['source_id']=='node/6897141353'
        label='南门 · main\nnode/6897141353'if south else'北侧出口 · exit\nnode/6897145227（仅门外）'
        if span<400:offset=(25,-42)if south else(-95,38)
        else:offset=(28,-80)if south else(-155,35)
        door_right=south and span>=400 and (xy[0]-extent[0])/span>.62
        if door_right:offset=(-20,-80)
        point=ax.scatter(*xy,s=48 if south else 55,c=INK if south else ROSE,marker='o'if south else'D',edgecolors=PAPER,linewidths=1.2,zorder=29)
        point.set_gid(ax._pg1_panel_prefix+'original_door_'+door['source_id'].replace('/','_'))
        ax.annotate(label,xy,xytext=offset,textcoords='offset points',ha='right'if door_right else'left',fontsize=9.2,color=INK if south else ROSE,zorder=31,
                    bbox={'facecolor':PAPER,'edgecolor':'none','alpha':.9,'pad':2},
                    arrowprops={'arrowstyle':'-','color':INK if south else ROSE,'lw':1})
        markers.append({'source_id':door['source_id'],'xy':xy,'tags':door['tags'],'symbol':'source point at originalcoordinate'})
    roads=[]
    for f in scene['features']:
        if f['source_id']in scene['huangpi_road_ids']:
            if shape(f['geometry']).intersects(clip):
                c.draw_geometry(ax,f['geometry'],{'fill':'none','edge':GOLD,'width':2.3,'z':15},'verified_huangpi_'+f['source_id'].replace('/','_'))
                roads.append(f['source_id'])
        if 'restrictions'in f['families']and shape(f['geometry']).intersects(clip):
            arts=c.draw_geometry(ax,f['geometry'],{'fill':'none','edge':'#8177A8','width':.9,'z':13},'source_restriction_'+f['source_id'].replace('/','_'))
            for a in arts:
                if isinstance(a,Line2D):a.set_linestyle((0,(1,2)))
    return {'target_id':target['building_id'],'target_fully_inside':clip.covers(shape(g)),
            'target_geometry_sha256':canonical(g),'door_markers':markers,'highlighted_huangpi_source_ids':roads}

def add_legend(fig):
    fig.legend(handles=[Patch(facecolor=PINK,edgecolor=ROSE,label='目标上海博物馆（真实源轮廓）'),
        Line2D([0],[0],color=GOLD,lw=2.5,label='核实黄陂北路：源中心线'),
        Line2D([0],[0],color='#555b61',lw=2,label='其他源道路/等级符号'),
        Line2D([0],[0],color='#5B9FBE',lw=2,label='原生步行线/独立人行道'),
        Line2D([0],[0],color=ROSE,marker='x',lw=1.5,label='原生过街/交通设施'),
        Patch(facecolor='#dfe9d6',label='绿地/草地（非通行推断）'),
        Patch(facecolor='#F5D9B8',label='源步行面/广场'),
        Patch(facecolor='#D3EAF5',label='源水体'),
        Line2D([0],[0],color='#777078',ls=':',lw=1.5,label='铁路/地下线'),
        Line2D([0],[0],color='#8177A8',ls=':',lw=1.5,label='源障碍/限制'),
        Line2D([0],[0],color='#8177A8',ls='--',lw=2,label='旧标签侧道 SCHEMATIC'),
        Line2D([0],[0],color=GOLD,ls='--',lw=2,label='旧条件侧道 HYPOTHESIS'),
        Line2D([0],[0],color=INK,lw=3,marker='o',label='旧诊断路线/端点（非馆门路线）')],
        loc='lower center',ncol=4,fontsize=8.5,frameon=False,bbox_to_anchor=(.5,.029))

def main():
    scene=read(ROOT/'data/scene.json');assert scene['target']['status']=='TARGET_SOURCE_IDENTITY_VERIFIED'
    frozen=read(ROOT/'data/frozen/maps/trial_map_data.json');w=next(x for x in frozen['windows']if x['window_id']=='native');query=w['queries'][0]
    views={v['id']:v for v in scene['views']}
    specs=[('target_context_full','block_context',[None]),('target_approach_overview','target_overview',[None]),
        ('huangpi_north_road_detail','huangpi_detail',[None]),('south_entrance_detail','south_detail',[None]),
        ('north_exit_detail','north_detail',[None]),('R0_R1_R2_same_extent','block_context',['R0','R1','R2']),
        ('source_vs_algorithm','block_context',[None,'R2']),('object_provenance_inspection','target_overview',[None])]
    manifest=[]
    for name,vid,variants in specs:
        v=views[vid];extent=v['bounds_xy'];cols=len(variants)
        fig,axes=plt.subplots(1,cols,figsize=(21,10)if cols==3 else(17,10)if cols==2 else(13,11),squeeze=False)
        fig.subplots_adjust(left=.035,right=.98,top=.83,bottom=.19,wspace=.06)
        fig.suptitle('上海博物馆人民广场馆 · '+v['label'],fontsize=16,y=.97)
        fig.text(.5,.928,'目标 way/161090899 · 南门 node/6897141353 · 北侧 exit node/6897145227 · 原坐标未移动',ha='center',fontsize=9)
        fig.text(.5,.899,'冻结 OSM '+scene['source']['timestamp']+' · SHA '+scene['source']['sha256'][:16]+'… · 实景几何仍待独立参考验证',ha='center',fontsize=8.5,color='#70757A')
        panels=[]
        for n,(ax,variant)in enumerate(zip(axes.flat,variants)):
            ax._pg1_panel_prefix='panel_'+(variant or'A')+'_'+str(n)+'_'
            base=c.draw_base(ax,scene,extent)
            target=emphasize_target(ax,scene,extent,name=='object_provenance_inspection')
            overlay=c.draw_overlay(ax,w,variant,query)if variant else None
            visible=[]
            if variant:
                visible=[e['edge_id']for e in w['variants'][variant]['edges']if LineString(e['xy']).intersects(box(*extent))]
                ax.set_title(variant+' · 旧西北侧步道诊断（非到门路线）'+(''if visible else'\n本视野没有对应冻结算法线'),fontsize=10,pad=12)
            else:ax.set_title('原始目标街区与登记门 · 不按路由准入删除源地物',fontsize=11,pad=12)
            panels.append({'variant':variant,'base':base,'target':target,'overlay':overlay,
                'visible_frozen_edge_ids':visible,'base_map_hash':v['base_map_hash'],'viewport_hash':v['viewport_hash'],
                'overlay_scope':'ORIGINAL_NORTHWEST_SIDEWALK_DIAGNOSTIC_NOT_MUSEUM_DOOR_REQUEST'if variant else'SOURCE_ONLY'})
        add_legend(fig)
        fig.text(.5,.008,'© OpenStreetMap contributors · 线宽为制图符号，不是实测道路宽度；未伪造车行面/路缘。北侧 exit 不作为入馆入口。',ha='center',fontsize=8.5,color='#70757A')
        fig.canvas.draw();fw,fh=fig.get_size_inches()
        for ax,p in zip(axes.flat,panels):
            pos=ax.get_position();sx=72*fw*pos.width/(extent[2]-extent[0]);sy=-72*fh*pos.height/(extent[3]-extent[1])
            p['world_to_svg_points']={'scale_x':sx,'scale_y':sy,'offset_x':72*fw*pos.x0-sx*extent[0],
                'offset_y':72*fh*(1-pos.y0)-sy*extent[1],'svg_id_prefix':ax._pg1_panel_prefix}
        outputs=[]
        for ext in ['png','svg']:
            dest=ROOT/'figures'/f'{name}.{ext}';fig.savefig(dest,dpi=160,metadata={'Date':None}if ext=='svg'else None)
            outputs.append({'path':dest.relative_to(ROOT).as_posix(),'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
        plt.close(fig);manifest.append({'name':name,'view_id':vid,'extent_xy':extent,'query_id':query['query_id']if any(variants)else None,'panels':panels,'files':outputs})
    (ROOT/'audit/figure_manifest.json').write_text(json.dumps({'figures':manifest,'algorithm_runs_added':0,'solver_calls_added':0},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'PNG':len(manifest),'SVG':len(manifest),'solver_calls_added':0}))

if __name__=='__main__':main()
