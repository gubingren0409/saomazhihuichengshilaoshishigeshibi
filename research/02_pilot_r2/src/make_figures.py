"""Render four neutral evidence maps and the geographic viewer payload."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patheffects
from matplotlib.lines import Line2D
from matplotlib.path import Path as DrawPath
from matplotlib.patches import PathPatch, Rectangle
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union, transform

from .geometry import ROOT,Evidence,PROJECT,UNPROJECT,dump,project,read

C={"paper":"#f7f7f1","ink":"#263744","muted":"#526975","local":"#265e91","hosted":"#b75b32",
   "reference":"#a13550","plaza":"#b8d8c0","walk":"#63847a","road":"#dad4c4","building":"#e0d4ca"}
for candidate in ("C:/Windows/Fonts/msyh.ttc","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
    from pathlib import Path
    path=Path(candidate)
    if path.is_file():
        font_manager.fontManager.addfont(str(path))
        plt.rcParams["font.family"]=font_manager.FontProperties(fname=str(path)).get_name()
        break
plt.rcParams.update({"axes.unicode_minus":False,"svg.fonttype":"path","savefig.facecolor":C["paper"]})


def parts(g, kind):
    if g.is_empty:
        return
    if g.geom_type==kind:
        yield g
    elif hasattr(g,"geoms"):
        for child in g.geoms:
            yield from parts(child,kind)


def padded(g,x,y=None):
    a,b,c,d=g.bounds
    y=x if y is None else y
    return (a-x,b-y,c+x,d+y)


def position(p):
    return PROJECT(*p)


def ground_view(bounds):
    return list(transform(UNPROJECT,box(*bounds)).bounds)


def dot(ax,coord,color,*,size=52,z=12,edge="white",face=True):
    x,y=position(coord)
    ax.scatter(x,y,s=size,facecolors=color if face else "none",edgecolors=edge if face else color,
               linewidths=1.6,zorder=z)
    return x,y


def callout(ax,point,label,offset,color=C["ink"]):
    ax.annotate(label, xy=point, xytext=offset,textcoords="offset points", fontsize=9.4,color=color,
                ha="left" if offset[0]>=0 else "right",va="center",zorder=20,
                bbox=dict(boxstyle="round,pad=.32",fc="#fdfdf8",ec="#e2e7dd",lw=.65),
                arrowprops=dict(arrowstyle="-",lw=.9,color=color,alpha=.78))


def plot_line(ax,geometry,**kw):
    for p in parts(geometry,"LineString"):
        x,y=p.xy
        ax.plot(x,y,solid_capstyle="round",**kw)


def plot_area(ax,geometry,fill,edge,*,alpha=1,z=1,hatch=None):
    for poly in parts(geometry,"Polygon"):
        poly=orient(poly,sign=1)
        vertices,codes=[],[]
        for ring in (poly.exterior,*poly.interiors):
            pts=list(ring.coords)
            vertices.extend(pts)
            codes.extend([DrawPath.MOVETO]+[DrawPath.LINETO]*(len(pts)-2)+[DrawPath.CLOSEPOLY])
        ax.add_patch(PathPatch(DrawPath(vertices,codes),facecolor=fill,edgecolor=edge,
                              alpha=alpha,lw=.85,zorder=z,hatch=hatch))


def view_panel(title,sub,notes,bounds,scalem):
    fig=plt.figure(figsize=(13.8,8.2),dpi=145,facecolor=C["paper"])
    fig.text(.047,.945,title,color=C["ink"],size=21,weight="bold")
    fig.text(.049,.905,sub,color=C["muted"],size=10.7)
    ax=fig.add_axes([.047,.113,.683,.746],facecolor="#f3f4ed")
    left,bottom,right,top=bounds
    ax.set(xlim=(left,right),ylim=(bottom,top),aspect="equal",xticks=[],yticks=[])
    for spine in ax.spines.values(): spine.set_edgecolor("#cad5cb")
    h=fig.add_axes([.756,.12,.202,.74],facecolor="#eff2e9")
    h.set(xticks=[],yticks=[])
    for spine in h.spines.values(): spine.set_visible(False)
    y=.94
    for head,text in notes:
        h.text(.08,y,head,color=C["ink"],size=11.2,weight="bold",transform=h.transAxes,va="top")
        y-=.048
        h.text(.08,y,text,color=C["muted"],size=9.5,transform=h.transAxes,va="top",linespacing=1.55)
        y-=.052*len(text.splitlines())+.047
    margin=(right-left)*.036
    x,y=left+margin,bottom+(top-bottom)*.05
    ax.plot([x,x+scalem],[y,y],lw=2.3,color=C["ink"],zorder=40,
            path_effects=[patheffects.withStroke(linewidth=5,foreground=C["paper"])])
    ax.text(x+scalem/2,y+(top-bottom)*.018,f"{scalem} m",ha="center",size=9,zorder=41,color=C["ink"],
            bbox=dict(fc=C["paper"],ec="none",pad=1.4))
    # Arrow follows projected WGS84 true north rather than assuming UTM grid north.
    a,b=right-margin,top-(top-bottom)*.105
    lon,lat=UNPROJECT(a,b)
    na,nb=PROJECT(lon,lat+.001)
    scale=(top-bottom)*.061/(nb-b)
    ax.annotate("N",xy=(a+(na-a)*scale,b+(nb-b)*scale),xytext=(a,b),size=10,
                arrowprops=dict(arrowstyle="-|>",color=C["ink"],lw=1.2),zorder=41)
    fig.text(.047,.055,"© OpenStreetMap contributors · ODbL  |  Powered by Geoapify  |  WGS84 来源，EPSG:32651 制图  |  上海博物馆人民广场馆",
             size=9,color=C["muted"])
    return fig,ax


def draw_background(ax,cache,bounds):
    clip=box(*bounds)
    for id_,tags,g in cache:
        if not g.intersects(clip): continue
        if g.geom_type=="Polygon":
            col="#e6d9d1" if tags.get("building") else "#e7eadb"
            plot_area(ax,g.intersection(clip),col,"#c4b9ad",z=2)
        elif tags.get("highway"):
            kind=tags["highway"]
            is_road=kind in {"primary","secondary","tertiary","residential","service","trunk"}
            if is_road:
                plot_line(ax,g.intersection(clip),color=C["road"],lw=3.1,alpha=.82,zorder=3)
            elif kind in {"footway","path","pedestrian","steps","living_street"}:
                plot_line(ax,g.intersection(clip),color=C["walk"],lw=.77,alpha=.62,zorder=4)


def draw_routes(ax,e,bounds):
    clip=box(*bounds)
    for path,col,lw,style in ((e.local,C["local"],3.1,"-"),(e.hosted,C["hosted"],2.45,(0,(4,2.3)))):
        g=project(LineString(path)).intersection(clip)
        plot_line(ax,g,color="#fdfdf9",lw=lw+1.9,zorder=7)
        plot_line(ax,g,color=col,lw=lw,linestyle=style,zorder=8)
    ax.legend(handles=[Line2D([0],[0],color=C["local"],lw=2.8,label="本地 OSM 诊断路线"),
                      Line2D([0],[0],color=C["hosted"],lw=2.6,ls="--",label="Geoapify 返回路线")],
              loc="upper left",fontsize=9,framealpha=.95,facecolor="#fdfdf8",edgecolor="#d7e0d2")


def figure_path(fig,name):
    path=ROOT/"figures"/name
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path,dpi=145)
    plt.close(fig)


def local_cache(e, bbox):
    cache=[]
    for id_,tags,line in e.relevant_ways(box(*bbox)):
        g=Polygon(line.coords) if line.is_ring and any(tags.get(k) for k in ("building","landuse","leisure","natural")) else line
        if g.is_valid:
            cache.append((id_,tags,project(g)))
    return cache


def end_markers(ax,e):
    pt=dot(ax,e.local[-1],C["local"],size=146,face=False)
    dot(ax,e.hosted[-1],C["hosted"],size=32)
    entry=dot(ax,e.target,C["reference"],size=72)
    return pt,entry


def build():
    e=Evidence()
    t=read(ROOT/"analysis/topology.json")
    m=read(ROOT/"analysis/endpoint_metrics.json")
    o,p=t["origin"],t["plaza"]
    trace=unary_union([project(LineString(e.local)),project(LineString(e.hosted)),
                       project(e.target_building),project(e.plaza())])
    overview=padded(trace,64,61)
    origin_bounds=padded(unary_union([project(e.building(o["origin_building_way_id"])),
                                    project(LineString(e.local[:15])),project(LineString(e.hosted[:14]))]),29,30)
    plaza_bounds=padded(unary_union([project(e.plaza()),project(e.target_building),
                                    project(Point(e.local[-1]))]),31,31)
    gap_bounds=padded(unary_union([project(e.target_building),project(Point(e.target)),
                                  project(Point(e.local[-1]))]),20,22)
    cache=local_cache(e,ground_view(overview))

    fig,ax=view_panel("01  ·  两条实际路线的全局对照","同一中性底图 · 本地折线为单独的接近诊断",
        [("共同起点","设定地图起点\nnode/476682043"),("主要分歧","约 44 m 后分开\n起点局部见图 02"),
         ("末点相距约 4 cm","两点图上重合\n距南侧入口参考约 55 m"),
         ("两条线路长度","本地诊断 1,416.72 m\n托管折线 961.82 m\n托管接口报 964 m")],overview,100)
    draw_background(ax,cache,overview)
    plot_area(ax,project(e.target_building),"#e4d2c9","#a38278",z=5)
    draw_routes(ax,e,overview)
    pt=dot(ax,e.start,"#237651");callout(ax,pt,"设定起点",(-17,-24))
    p_end,p_ref=end_markers(ax,e)
    callout(ax,p_end,"两个路网末点",(15,21))
    callout(ax,p_ref,"南侧入口参考",(13,-23),C["reference"])
    split=dot(ax,o["split_wgs84"],"#654f80",size=55)
    callout(ax,split,"约 44 m 后分开",(-20,-22))
    x,y,xx,yy=origin_bounds
    ax.add_patch(Rectangle((x,y),xx-x,yy-y,fill=False,ls="--",lw=1,color="#685477",zorder=6))
    figure_path(fig,"figure01_global.png")

    fig,ax=view_panel("02  ·  起点附近为何分开","同起点、同一共有步道。两条折线最终使用同一处人民大道过街几何。",
        [("分歧原生节点",f"node/{o['split_node_id']}\n距起点 {o['shared_prefix_m']:.2f} m"),
         ("本地路径","39764359 等人行道\n绕大剧院北侧\n分歧至汇合 537.35 m"),
         ("托管折线","654297629 / 1074409256\n黄陂北路轴线几何吻合\ntertiary，缺 foot / sidewalk\n分歧至汇合 73.90 m"),
         ("两条线共有过街","way/761403176\n托管内部图边、通行规则未知")],origin_bounds,50)
    draw_background(ax,cache,origin_bounds)
    plot_area(ax,project(e.building(o["origin_building_way_id"])),"#e0d0bc","#aa937c",z=4)
    for id_ in o["hosted_candidate_road_axis_way_ids"]:
        plot_line(ax,project(e.way(id_)).intersection(box(*origin_bounds)),color="#bc9d6b",lw=2.1,zorder=5,linestyle=":")
    draw_routes(ax,e,origin_bounds)
    callout(ax,dot(ax,e.start,"#237651"),"起点",(20,-10))
    callout(ax,dot(ax,o["split_wgs84"],"#654f80"),"分歧节点",(14,22))
    callout(ax,dot(ax,o["rejoin_wgs84"],"#325d68"),"汇合／共同过街",(14,-21))
    cx,cy=project(e.building(o["origin_building_way_id"])).representative_point().coords[0]
    ax.text(cx,cy,"上海大剧院\nway/39763758",ha="center",va="center",size=10,color=C["ink"],zorder=10)
    figure_path(fig,"figure02_origin.png")

    fig,ax=view_panel("03  ·  南侧广场与步行网","绿纹是来源登记广场面。圆点标原生路网接点。",
        [("广场面","relation/2385771\narea=yes · pedestrian\n外环 way/178721643"),
         ("三个原生接点","① node/1890745480\n② node/1890935415\n③ node/1890935454\n三点均可由起点到达"),
         ("广场内部","本地合格穿入线段 0\n入口节点没有入图"),
         ("托管内部与现场","广场面是否路由化未知\n实际开放及通行未核验")],plaza_bounds,30)
    draw_background(ax,cache,plaza_bounds)
    plot_area(ax,project(e.target_building),"#e4d2c9","#a38278",z=4)
    plot_area(ax,project(e.plaza()),C["plaza"],"#638b76",alpha=.86,z=5,hatch="//")
    for way in p["nearby_eligible_way_ids"]:
        plot_line(ax,project(e.way(way)).intersection(box(*plaza_bounds)),color="#60897d",lw=1.45,zorder=6)
    draw_routes(ax,e,plaza_bounds)
    for i,(item,offset) in enumerate(zip(p["connections"],[(-13,-17),(14,-12),(-16,14)]),1):
        callout(ax,dot(ax,item["wgs84"],"#197d63",size=53),f"{i}  原生接点",offset)
    _,entry=end_markers(ax,e);callout(ax,entry,"南侧入口参考",(9,21),C["reference"])
    figure_path(fig,"figure03_plaza.png")

    fig,ax=view_panel("04  ·  约 55 米末段缺口","点位为原坐标。玫红虚线是测距线，经过建筑内部。",
        [("入口参考","node/6897141353\nentrance=main，位于馆轮廓\nREFERENCE_UNCERTAIN\n实体位置、开放性未核验"),
         ("最近本地步网","way/178719573 · footway\n最近节点 node/1890732610"),
         ("WGS84 椭球测距","本地末点 55.02 m\n托管末点 54.99 m\n两末点相距 0.038 m"),
         ("固定接入门","35 m，运行前冻结\n直线有约 50.46 m 穿馆\n不可作为步行连接")],gap_bounds,20)
    draw_background(ax,cache,gap_bounds)
    plot_area(ax,project(e.target_building),"#e4d2c9","#a38278",z=4)
    plot_line(ax,project(e.way(178719573)).intersection(box(*gap_bounds)),color="#466e63",lw=2.4,zorder=6)
    draw_routes(ax,e,gap_bounds)
    plot_line(ax,project(LineString([e.local[-1],e.target])),color=C["reference"],lw=2.05,zorder=10,linestyle=(0,(2.8,2.2)))
    p_end,p_ref=end_markers(ax,e)
    callout(ax,p_end,"两个实际路网末点",(15,12))
    callout(ax,p_ref,"南侧入口参考",(17,-21),C["reference"])
    line=project(LineString([e.local[-1],e.target]))
    midpoint=line.interpolate(.5,normalized=True).coords[0]
    callout(ax,midpoint,"55.02 m  直线测距",(-12,-12),C["reference"])
    figure_path(fig,"figure04_endpoint.png")
    build_viewer(e,t,m,cache,overview,origin_bounds,plaza_bounds,gap_bounds)


def build_viewer(e,t,m,cache,*bounds):
    items=[]
    geo=t["features"]
    for feature in geo["features"] if isinstance(geo,dict) else geo:
        if not feature.get("geometry") or not feature.get("properties"):
            continue
        props=feature["properties"]
        role=str(props.get("role",""))
        id_=str(props.get("id",""))
        geometry_type=feature["geometry"]["type"]
        if geometry_type in {"Polygon","MultiPolygon"}:
            layer="plaza" if "plaza" in role else "buildings"
        elif geometry_type!="LineString":
            layer="reference"
        elif role=="plaza_outer":
            layer="plaza"
        elif role in {"hosted_axis_candidate","crossed_road_axis","crossed_cycleway","wusheng_road","residential_junction"}:
            layer="diagnostic"
        else:
            layer="crossing" if "cross" in role else "walk"
        items.append({"type":"Feature","geometry":feature["geometry"],"properties":{
            "id":id_,"layer":layer,"label":role.replace("_"," "),"tags":props.get("tags",{}),
            "source":props.get("evidence","冻结 OSM 快照"),"role":role}})
    def add(geometry,id_,layer,label,role=None):
        items.append({"type":"Feature","geometry":mapping(geometry),"properties":{
            "id":id_,"layer":layer,"label":label,"source":"R1 冻结原件 / R2 复算","role":role,"label_map":bool(role)}})
    for id_,tags,shape_ in cache:
        if shape_.geom_type=="Polygon" and tags.get("building") and id_ not in {161090899,39763758}:
            items.append({"type":"Feature","geometry":mapping(transform(UNPROJECT,shape_)),"properties":{
                "id":f"way/{id_}","layer":"buildings","label":tags.get("name","建筑轮廓"),"source":"冻结 OSM","tags":tags}})
    add(LineString(e.local),"local-r1-diagnostic","route_local","本地 OSM 接近诊断路线")
    add(LineString(e.hosted),"geoapify-r1-returned","route_geoapify","Geoapify 返回路线")
    for point,id_,label,role in [(e.start,e.scene["start_native_id"],"设定起点","start"),
            (e.target,e.scene["entry_native_id"],"南侧入口参考","entry"),
            (e.local[-1],m["eligible_snap_node_id"],"本地诊断末点","local_end"),
            (e.hosted[-1],"hosted-route-last-vertex","托管折线末点","geoapify_end"),
            (t["origin"]["split_wgs84"],"node/13763096985","起点附近分歧","split")]:
        add(Point(point),id_,"reference",label,role)
    add(LineString([e.local[-1],e.target]),"geodesic-gap-reference","diagnostic","55.02 m 直线测距，不是步行连接")
    metrics=[{"label":"本地 OSM 诊断折线","value":"1,416.72 m"},
             {"label":"Geoapify 返回折线","value":"961.82 m（API 声明 964 m）"},
             {"label":"共同起点后首次分歧","value":"44.16 m · node/13763096985"},
             {"label":"两个折线末点","value":"相距 0.038 m"},
             {"label":"末点到南侧入口参考","value":"本地 55.02 m · 托管 54.99 m"},
             {"label":"南侧广场本地路网","value":"三个原生边界接点，零条合格线段穿过广场内部"},
             {"label":"现场通行","value":"UNKNOWN · 未实地核验"}]
    dump(ROOT/"analysis/viewer_payload.json",{"features":items,
        "presets":dict(zip(("overview","origin","plaza","endpoint"),map(ground_view,bounds))),"metrics":metrics})


if __name__=="__main__":
    build()
