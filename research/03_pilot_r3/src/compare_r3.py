"""Read frozen results, create attributed review assets, and measure descriptive metrics."""
from collections import Counter
import csv
from hashlib import sha256
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as DrawPath
from PIL import Image,ImageDraw,ImageFont
from pyproj import Geod,Transformer
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.geometry.polygon import orient
from shapely.ops import transform, unary_union, polygonize

from .gallery_r3 import frame

ROOT=Path(__file__).resolve().parents[1]
WGS=Geod(ellps="WGS84")
UTM=Transformer.from_crs(4326,32651,always_xy=True).transform
MERC=Transformer.from_crs(4326,3857,always_xy=True).transform
PALETTE={"local":"#24619e","hosted":"#bb542b","target":"#8c2e53","ink":"#243b3f","walk":"#427865"}
FONT=next((Path(x) for x in ("C:/Windows/Fonts/msyh.ttc","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if Path(x).is_file()),None)
if FONT:
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"]=font_manager.FontProperties(fname=str(FONT)).get_name()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def csv_out(path,rows):
    if rows:
        with path.open("w",encoding="utf-8-sig",newline="") as handle:
            w=csv.DictWriter(handle,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def geometry_parts(doc):
    if not isinstance(doc,dict):
        return []
    kind=doc.get("type")
    if kind=="FeatureCollection":
        return [segment for f in doc.get("features",[]) for segment in geometry_parts(f)]
    if kind=="Feature":
        return geometry_parts(doc.get("geometry"))
    if kind=="LineString":
        return [doc["coordinates"]] if len(doc["coordinates"])>=2 else []
    if kind=="MultiLineString":
        return [s for s in doc.get("coordinates",[]) if len(s)>=2]
    return []


def dist(a,b):
    return WGS.inv(*a,*b)[2] if a is not None and b is not None else None


def measure(parts,start,target):
    if not parts:
        return {"length_m":None,"start_offset_m":None,"target_gap_m":None,"end":None,"parts":0}
    length=sum(WGS.line_length(*zip(*part)) for part in parts)
    return {"length_m":length,"start_offset_m":dist(start,parts[0][0]),"target_gap_m":dist(target,parts[-1][-1]),
            "end":parts[-1][-1],"parts":len(parts)}


def native_geometry(payload,near):
    nodes={r["id"]:(r["lon"],r["lat"]) for r in payload["elements"] if r["type"]=="node"}
    way_index={}
    buildings=[]; walking=[]; areas=[]; roads=[]; crossings=[]
    for row in payload["elements"]:
        if row["type"]=="node":
            tag=row.get("tags",{})
            if tag.get("highway")=="crossing" and near.covers(Point(nodes[row["id"]])):
                crossings.append((row["id"],Point(nodes[row["id"]])))
        if row["type"]!="way":
            continue
        coords=[nodes[n] for n in row["nodes"] if n in nodes]
        if len(coords)<2 or len(coords)!=len(row["nodes"]):
            continue
        line=LineString(coords)
        if not box(*line.bounds).intersects(near) and not line.intersects(near):
            continue
        way_index[row["id"]]=line
        tags=row.get("tags",{})
        if tags.get("highway") in {"primary","secondary","tertiary","unclassified","residential","service","trunk",
                                   "primary_link","secondary_link","tertiary_link","trunk_link"} and tags.get("area")!="yes":
            roads.append((row["id"],line))
        if tags.get("footway")=="crossing" or tags.get("path")=="crossing":
            crossings.append((row["id"],line))
        poly=Polygon(coords) if line.is_ring and len(coords)>3 else None
        if poly is not None and poly.is_valid and tags.get("building") not in (None,"no"):
            buildings.append((row["id"],poly))
        if (tags.get("highway") in {"footway","path","pedestrian","steps","living_street"}
                or tags.get("foot") in {"yes","designated","permissive"}) and tags.get("area")!="yes":
            walking.append((row["id"],line))
        if poly is not None and poly.is_valid and open_tags(tags):
            areas.append(("way/"+str(row["id"]),poly))
    for row in payload["elements"]:
        if row["type"]!="relation" or not open_tags(row.get("tags",{})):
            continue
        members=[m for m in row.get("members",[]) if m.get("type")=="way"]
        if not members or any(m["ref"] not in way_index for m in members):
            continue
        outer=[way_index[m["ref"]] for m in members if m["role"] in ("","outer")]
        inner=[way_index[m["ref"]] for m in members if m["role"]=="inner"]
        if outer:
            geom=unary_union(list(polygonize(unary_union(outer))))
            if inner:
                geom=geom.difference(unary_union(list(polygonize(unary_union(inner)))))
            if not geom.is_empty and geom.is_valid:
                areas.append(("relation/"+str(row["id"]),geom))
    return buildings,walking,areas,roads,crossings


def open_tags(tags):
    return (tags.get("highway")=="pedestrian" and tags.get("area")=="yes" or tags.get("area:highway")=="pedestrian"
            or tags.get("leisure") in {"park","garden","playground","pitch"} or tags.get("landuse") in {"grass","village_green"})


def source_overlap(parts, walking, buildings):
    if not parts:
        return {"line_near_tagged_osm_pedestrian_fraction":None,"osm_footprint_intersections":None,
                "near_native_way_ids":None}
    route=unary_union([transform(UTM,LineString(p)) for p in parts])
    if not route.length:
        return {"line_near_tagged_osm_pedestrian_fraction":None,"osm_footprint_intersections":None,
                "near_native_way_ids":None}
    padded=[];near_ids=[]
    for key,line in walking:
        metric=transform(UTM,line)
        if metric.distance(route)<=2:
            near_ids.append(key)
            padded.append(metric.buffer(2))
    buildings_hit=[]
    for key,poly in buildings:
        core=transform(UTM,poly).buffer(-.25)
        if not core.is_empty and core.intersection(route).length>.3:
            buildings_hit.append("way/"+str(key))
    return {"line_near_tagged_osm_pedestrian_fraction":route.intersection(unary_union(padded)).length/route.length,
            "osm_footprint_intersections":len(buildings_hit),"osm_footprint_intersection_way_ids":buildings_hit,
            "near_native_way_ids":near_ids}


def font(size):
    return ImageFont.truetype(str(FONT),size) if FONT else ImageFont.load_default()


def route_plate(root,path,view,scene,lp,hp,local_diag):
    with Image.open(root/path) as src:
        base=src.convert("RGB")
    width,height=base.size
    image=Image.new("RGB",(width,height+78),"#f8f8ef")
    d=ImageDraw.Draw(base)
    w,s,e,n=view["extent_3857"]
    def xy(point):
        x,y=MERC(*point)
        return (x-w)/(e-w)*width,(n-y)/(n-s)*height
    for part in lp+hp:
        d.line([xy(p) for p in part],fill="white",width=9,joint="curve")
    for parts,col,dash in ((lp,PALETTE["local"],False),(hp,PALETTE["hosted"],True)):
        for part in parts:
            pts=[xy(p) for p in part]
            if dash:
                for j,(a,b) in enumerate(zip(pts,pts[1:])):
                    # Dots preserve every returned vertex and keep the other route legible where coincident.
                    steps=max(1,round(((a[0]-b[0])**2+(a[1]-b[1])**2)**.5/6))
                    for k in range(steps+1):
                        f=k/steps;x=a[0]+f*(b[0]-a[0]);y=a[1]+f*(b[1]-a[1])
                        d.ellipse((x-2,y-2,x+2,y+2),fill=col)
            else:
                d.line(pts,fill=col,width=5,joint="curve")
    for p,col,label in ((scene.get("start"),"#22664e","起"),(scene.get("target"),PALETTE["target"],"参"),
                        (lp[-1][-1] if lp else None,PALETTE["local"],"本"),
                        (hp[-1][-1] if hp else None,PALETTE["hosted"],"托")):
        if p is not None:
            x,y=xy(p)
            if 6<=x<width-6 and 6<=y<height-6:
                d.ellipse((x-6,y-6,x+6,y+6),fill=col,outline="white",width=2)
                d.text((x+10,y-10),label,font=font(16),fill=col,stroke_width=2,stroke_fill="#fcfcf5")
    image.paste(base,(0,46))
    d=ImageDraw.Draw(image)
    d.text((16,11),scene["label"]+" · 共同底图上的实际折线",font=font(22),fill=PALETTE["ink"])
    caption=("蓝：本地接近诊断；" if local_diag else "蓝：本地冻结请求；")+"橙点：托管返回折线；参：请求参考"
    d.text((13,height+53),caption,font=font(15),fill=PALETTE["ink"])
    credit="© OpenStreetMap contributors"+(" · Powered by Geoapify" if hp else "")
    d.text((width-390,height+53),credit,font=font(14),fill=PALETTE["ink"])
    dest=root/"visuals/routes"/(scene["scene_id"]+"_route.png")
    image.save(dest)
    return dest.relative_to(root).as_posix()


def polygons(geometry):
    if geometry.geom_type=="Polygon":
        yield geometry
    elif hasattr(geometry,"geoms"):
        for item in geometry.geoms:
            yield from polygons(item)


def fill_poly(ax,g,face,edge,alpha=1,z=1,hatch=None):
    for poly in polygons(g):
        poly=orient(poly,sign=1)
        xy=[]; codes=[]
        for ring in (poly.exterior,*poly.interiors):
            coords=list(ring.coords)
            xy.extend(coords)
            codes.extend([DrawPath.MOVETO]+[DrawPath.LINETO]*(len(coords)-2)+[DrawPath.CLOSEPOLY])
        ax.add_patch(PathPatch(DrawPath(xy,codes),facecolor=face,edgecolor=edge,lw=.8,alpha=alpha,zorder=z,hatch=hatch))


def access_plate(root,scene,source,lp,hp,failed_local_snap=None):
    footprint=transform(UTM,shape(scene["building_footprint"]))
    ends=[scene.get("target"),lp[-1][-1] if lp else None,hp[-1][-1] if hp else None,failed_local_snap]
    nearby=[Point(*UTM(*p)) for p in ends if p is not None and footprint.distance(Point(*UTM(*p)))<=200]
    a,b,c,d=unary_union([footprint,*nearby]).bounds
    extent=box(a-38,b-38,c+38,d+38)
    a,b,c,d=extent.bounds
    fig,ax=plt.subplots(figsize=(max(8.1,min(13,6*(c-a)/(d-b))),7.4),dpi=130,facecolor="#f8f8ef")
    ax.set_facecolor("#f0f2e8")
    for _,area in source[2]:
        g=transform(UTM,area).intersection(extent)
        if not g.is_empty:
            fill_poly(ax,g,"#c4ddc1","#709376",.72,2,"//")
    for _,poly in source[0]:
        g=transform(UTM,poly).intersection(extent)
        if not g.is_empty:
            fill_poly(ax,g,"#e3dbd0","#c6baae",.7,1)
    for features,color,width in ((source[3],"#988c7e",.75),(source[1],PALETTE["walk"],.9),(source[4],"#a77918",1.5)):
        for _,geom in features:
            clipped=transform(UTM,geom).intersection(extent)
            for piece in getattr(clipped,"geoms",[clipped]):
                if piece.is_empty:
                    continue
                if piece.geom_type=="LineString":
                    ax.plot(*piece.xy,color=color,lw=width,zorder=3)
                elif piece.geom_type=="Point":
                    ax.scatter(piece.x,piece.y,color=color,marker="D",s=11,zorder=3)
    fill_poly(ax,footprint,"#dbc8b8","#967f65",.85,4)
    for parts,key in ((lp,"local"),(hp,"hosted")):
        for coords in parts:
            g=transform(UTM,LineString(coords)).intersection(extent)
            for piece in ([g] if g.geom_type=="LineString" else getattr(g,"geoms",[])):
                if piece.geom_type=="LineString" and not piece.is_empty:
                    ax.plot(*piece.xy,color=PALETTE[key],lw=1.8,ls="--" if key=="hosted" else "-",zorder=5)
    legend=[Patch(facecolor="#c4ddc1",edgecolor="#709376",hatch="//",label="原生开放空间／草地面（通行未知）"),
            Line2D([0],[0],color="#988c7e",label="原生机动车道路中心线"),
            Line2D([0],[0],color=PALETTE["walk"],label="OSM 含步行标签的线"),
            Line2D([0],[0],color="#a77918",marker="D",label="原生过街点或过街线"),
            Patch(facecolor="#dbc8b8",edgecolor="#967f65",label="目标轮廓")]
    points=[("target",scene.get("target"),"请求参考"),
            ("local",lp[-1][-1] if lp else None,"本地末点"),
            ("hosted",hp[-1][-1] if hp else None,"托管末点")]
    for key,p,text in points:
        if p is not None:
            x,y=UTM(*p)
            if extent.covers(Point(x,y)):
                ax.scatter(x,y,s=83 if key=="target" else 56,
                           facecolors="none" if key=="local" else PALETTE[key],edgecolors=PALETTE[key],
                           linewidths=1.8,zorder=10)
                legend.append(Line2D([0],[0],marker="o",ls="none",color=PALETTE[key],label=text))
    if failed_local_snap is not None:
        snap=Point(*UTM(*failed_local_snap))
        if extent.covers(snap):
            ax.scatter(snap.x,snap.y,marker="x",s=116,color=PALETTE["local"],linewidths=2,zorder=11)
            legend.append(Line2D([0],[0],marker="x",ls="none",color=PALETTE["local"],label="本地吸附候选（未连通）"))
    for ref in scene.get("entrance_references",[]):
        p=ref.get("coordinate") or ref.get("coordinates") or ref.get("wgs84")
        if isinstance(p,(list,tuple)) and len(p)==2:
            x,y=UTM(*p)
            if extent.covers(Point(x,y)):
                ax.scatter(x,y,marker="+",s=40,color=PALETTE["target"],zorder=9)
    a,b,c,d=extent.bounds
    tick=25 if c-a<180 else 50
    ax.plot([a+7,a+7+tick],[b+6,b+6],color=PALETTE["ink"],lw=2.8)
    ax.text(a+7,b+8,f"{tick} m",fontsize=9)
    ax.text(c-10,d-8,"↑ N",ha="right")
    ax.set(xlim=(a,c),ylim=(b,d),aspect="equal",xticks=[],yticks=[])
    ax.legend(handles=legend,loc="upper left",fontsize=8,framealpha=.96)
    ax.set_title(scene["label"]+" · 开放空间、步行线与入口参考",fontsize=16,color=PALETTE["ink"])
    gaps=[dist(scene.get("target"),coords[-1][-1]) if coords else None for coords in (lp,hp)]
    gap_note=" · ".join(f"{name}末点距请求点 {value:.1f} m" for name,value in zip(("本地","托管"),gaps) if value is not None)
    if failed_local_snap is not None:
        gap_note+=f" · 本地仅吸附候选 {dist(scene.get('target'),failed_local_snap):.1f} m"
    fig.text(.06,.065,gap_note or "无折线末点可核对",fontsize=9)
    fig.text(.06,.035,"EPSG:32651 · OBSERVED 原生 OSM 要素；无现场验证。  © OpenStreetMap contributors · Powered by Geoapify",fontsize=9)
    dest=root/"visuals/routes"/(scene["scene_id"]+"_access.png")
    fig.savefig(dest,bbox_inches="tight",facecolor=fig.get_facecolor())
    plt.close(fig)
    return dest.relative_to(root).as_posix()


def historical(root):
    r=root/"inputs/r1"
    prefix="inputs/r1/"
    scene=load(r/"runs/scene_contract.json")
    scene.update(category="历史首例 · 公共文化",historical=True,osm_clip=prefix+"data/sh-huangpu-01.osm.json")
    if scene.get("entry_native_id") and scene.get("target"):
        scene["entrance_references"]=[{"native_id":scene["entry_native_id"],"coordinate":scene["target"]}]
    local_view=load(r/"runs/local_viewports.json")["views"]
    remote_view=load(r/"runs/geoapify_static_completion.json")["views"]
    for view in local_view.values():
        for k in ("base","route"):
            if view.get(k):view[k]=prefix+view[k]
    for view in remote_view.values():
        for k in ("base","route"):
            if view.get(k):view[k]=prefix+view[k]
    probe=load(r/"runs/geoapify_walk_probe_proxy.json")
    route={**probe["route"],"geometry_path":prefix+probe["geojson"]["path"],"status":"HISTORICAL_LIVE_ROUTE_RETURNED"}
    local={"route":load(r/"runs/local_route.json"),"diagnostic":load(r/"runs/local_approach_diagnostic.json"),"views":local_view}
    hosted={"route":route,"views":remote_view,"status":"HISTORICAL_LIVE_NOT_RECALLED"}
    return scene,local,hosted


def clip_path(value):
    if isinstance(value,dict):
        return value.get("path") or value.get("relative_path") or value.get("artifact")
    return value


def hosted_parts(root,rec):
    p=rec.get("geometry_path")
    if isinstance(p,dict):
        p=p.get("path")
    return geometry_parts(load(root/p)) if p and (root/p).is_file() else geometry_parts(rec.get("geometry"))


def base_status(a,b):
    if not a.get("base") or not b.get("base"):
        return "缺一侧或两侧实图"
    if b.get("bounds_match") is True:
        return "同尺度核验通过"
    if b.get("bounds_match") is False:
        return "实际视野有偏差或未核实"
    return "实际尺度待核实"


def build(root=ROOT):
    contracts=load(root/"runs/scene_contracts.json")["scenes"]
    locals_=load(root/"runs/local_results.json")["scenes"]
    hosted_=load(root/"runs/hosted_results.json") if (root/"runs/hosted_results.json").is_file() else {"scenes":[]}
    local_by={x["scene_id"]:x for x in locals_}
    hosted_by={x["scene_id"]:x for x in hosted_["scenes"]}
    all_cases=[historical(root)]+[(s,local_by.get(s["scene_id"],{}),hosted_by.get(s["scene_id"],{})) for s in contracts]
    display=[];records=[];pages=[];failed=[]
    (root/"visuals/routes").mkdir(parents=True,exist_ok=True)
    (root/"visuals/failure_cases").mkdir(parents=True,exist_ok=True)
    for scene,local,hosted in all_cases:
        ident=scene["scene_id"]
        lroute=local.get("route") or {}
        ldiag=local.get("diagnostic") or {}
        hroute=hosted.get("route") or {}
        lm=geometry_parts(lroute.get("geometry"))
        ld=geometry_parts(ldiag.get("geometry"))
        hp=hosted_parts(root,hroute)
        lp=lm or ld
        report={"scene_id":ident,"label":scene["label"],"category":scene["category"],"historical":bool(scene.get("historical")),
                "contract_status":scene.get("contract_status","HISTORICAL_LOCKED"),"building_native_id":scene.get("building_native_id"),
                "target_role":scene.get("target_role"),"entrance_count":len(scene.get("entrance_references",[])),
                "entrance_reference":scene.get("entry_native_id"),"frozen_start":scene.get("start"),
                "frozen_target":scene.get("target"),"local_status":lroute.get("status","NOT_RUN"),
                "local_failure_reason":lroute.get("failure_reason"),"local":measure(lm,scene.get("start"),scene.get("target")),
                "local_snap_distance_m":lroute.get("snap_end_m"),
                "local_diagnostic":measure(ld,scene.get("start"),scene.get("target")),
                "hosted_status":hroute.get("status","NOT_RUN"),"hosted":measure(hp,scene.get("start"),scene.get("target")),
                "hosted_provider_distance_m":hroute.get("provider_distance_m"),"views":{}}
        visible={"scene_id":ident,"label":scene["label"],"category":scene["category"],"historical":report["historical"],"views":{}}
        for name,view in scene.get("views",{}).items():
            lv=(local.get("views") or {}).get(name,{})
            hv=(hosted.get("views") or {}).get(name,{})
            status=base_status(lv,hv)
            report["views"][name]={"status":status,"local_png":lv.get("base"),"hosted_png":hv.get("base"),
                "hosted_overlay":hv.get("overlay") or hv.get("route"),
                "local_mpp":view.get("meters_per_pixel"),"hosted_mpp":hv.get("meters_per_pixel"),
                "hosted_bounds_match":hv.get("bounds_match"),"local_source_counts":lv.get("feature_counts"),
                "hosted_vector_coverage":"UNKNOWN_IMAGE_ONLY"}
            actual=view.get("meters_per_pixel")
            caption=f"锁定视野 · 1200×900 · 约 {actual:.3f} m/px" if actual is not None else "范围未核实"
            visible["views"][name]={"comparison_status":status,"scale_caption":caption+" · "+status,
                "assets":{"osm":{"base":lv.get("base"),"overlay":lv.get("route"),
                    "base_caption":"无路线真实底图" if lv.get("base") else local.get("status","缺图"),
                    "overlay_caption":"只到路网的诊断折线" if ld and not lm else "冻结请求路线或真实失败标记"},
                 "geoapify":{"base":hv.get("base"),"overlay":hv.get("overlay") or hv.get("route"),
                    "base_caption":"无路线真实底图" if hv.get("base") else hv.get("status",hosted.get("status","缺图")),
                    "overlay_caption":"已返回路线；终点身份单独检查" if hp else "未取得正式路线"}}}
        pairs=sum(v["status"]=="同尺度核验通过" for v in report["views"].values())
        report["verified_paired_views"]=pairs
        visible["status_label"]=f"{pairs}/2 档同尺度" if not report["historical"] else "历史样本 · 原评分保留"
        display.append(visible)
        html=f'<article><h2>{escape(scene["label"])}</h2>'
        context=(local.get("views") or {}).get("context",{})
        if context.get("base") and scene.get("views",{}).get("context"):
            v=scene["views"]["context"]
            plate=route_plate(root,context["base"],v,scene,lp,hp,bool(ld and not lm))
            html+=f'<p><a href="../../{plate}"><img src="../../{plate}" alt="共同底图路线对照"></a></p>'
        cp=clip_path(scene.get("osm_clip"))
        if cp and scene.get("building_footprint") and scene.get("views",{}).get("context"):
            src=native_geometry(load(root/cp),box(*scene["views"]["context"]["bounds"]))
            report["native_open_space_objects_in_context"]=len(src[2])
            report["native_pedestrian_tagged_ways_in_context"]=len(src[1])
            report["native_road_centerlines_in_context"]=len(src[3])
            report["native_crossings_in_context"]=len(src[4])
            report["local_geometry_support"]=source_overlap(lp,src[1],src[0])
            report["hosted_geometry_support"]=source_overlap(hp,src[1],src[0])
            failed_snap=(lroute.get("snap_end") or {}).get("position") if not lp else None
            plate=access_plate(root,scene,src,lp,hp,failed_snap)
            html+=f'<p><a href="../../{plate}"><img src="../../{plate}" alt="开放空间与入口参考"></a></p>'
        html+=("<p>OBSERVED 原生要素与返回折线。RECOMPUTED 末段距离。INFERRED 代理点仅作空间诊断。UNKNOWN 现实通行与提供方内部图。</p></article>")
        pages.append(html)
        hosted_gap=report["hosted"]["target_gap_m"]
        if not lm or not hp or pairs<2 or (hosted_gap is not None and hosted_gap>35):
            failed.append(html)
        records.append(report)
    save_json(root/"runs/display_cases.json",{"scenes":display})
    save_json(root/"runs/comparison.json",{"scenes":records,"field_checks":0,"human":"PENDING_USER_REVIEW",
        "overlay_geometry_support_scope":"Nearest raw OSM pedestrian-tagged geometry within 2 m; no topological or independent truth implication."})
    csv_out(root/"runs/comparison.csv",[
        {"scene_id":c["scene_id"],"name":c["label"],"category":c["category"],"historical":c["historical"],
         "target_role":c["target_role"],"entrance_reference":c["entrance_reference"],"paired_views":c["verified_paired_views"],
         "local_status":c["local_status"],"local_failure":c["local_failure_reason"],"local_length_m":c["local"]["length_m"],
         "local_snap_m":c["local_snap_distance_m"],"local_diagnostic_m":c["local_diagnostic"]["length_m"],
         "hosted_status":c["hosted_status"],"hosted_route_m":c["hosted"]["length_m"],"hosted_target_gap_m":c["hosted"]["target_gap_m"]}
        for c in records])
    def page(title,content):
        doc=frame(title,'<header><h1>'+title+'</h1><p>真实坐标诊断 · 无现场通行核验</p></header><main>'
                  '<nav><a href="../blind_review/index.html">返回匿名图册</a></nav>'+content+'</main>')
        return doc.replace('href="style.css"','href="../blind_review/style.css"')
    (root/"visuals/routes/index.html").write_text(page("统一底图路线与开放空间细节","".join(pages)),encoding="utf-8")
    (root/"visuals/failure_cases/index.html").write_text(page("失败与待核验案例","".join(failed) or "<p>未触发记录条件。</p>"),encoding="utf-8")
    print(json.dumps({"scenes":len(records),"paired_views":sum(c["verified_paired_views"] for c in records)},ensure_ascii=True))


if __name__=="__main__":
    build()
