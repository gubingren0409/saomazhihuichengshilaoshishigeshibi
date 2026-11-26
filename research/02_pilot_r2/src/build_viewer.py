"""Build the R2 offline SVG viewer and two evidence figures from verified R1 copies."""

import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCORE_FILE = "user_scores_20261109T110307129Z.csv"
INK = "#192d25"
TEAL = "#164d43"
DIM = "#4c6156"
PAPER = "#f5f3e9"
SURFACE = "#fffdfa"
LINE = "#d6ddd0"
PALE = "#e8eee3"
GOLD = "#98613d"
NOTE = "#f6eddb"

FIELDS = (
    "building_outline", "building_road_separation", "pedestrian_visibility",
    "entrance_context", "occlusion", "target_identification", "detail_access",
    "context_detour", "route_alignment",
)
FIGURES = (
    ("figure01_global.png", "全局路线对照", "同一底图上的两条保存折线"),
    ("figure02_origin.png", "起点附近分歧", "源要素 ID、过街与绕行"),
    ("figure03_plaza.png", "南侧广场放大", "面、边界节点及步行线"),
    ("figure04_endpoint.png", "约 55 米末端缺口", "入口参考与路由端点"),
    ("figure05_visual_comparison.png", "地图视觉信息", "首轮无路线原图和人工观察"),
    ("figure06_layers.png", "从地图到路线", "按原生 ID 追溯各层关系"),
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_score(root):
    path = root / "inputs" / SCORE_FILE
    with path.open(encoding="utf-8-sig", newline="") as stream:
        [row] = list(csv.DictReader(stream))
    if (row["blind_scene_id"], row["detail_pair_id"], row["context_pair_id"]) != ("S-1814", "P-872C", "P-2CAE"):
        raise ValueError("UNEXPECTED_SCORE_ROW")
    totals = {side: sum(int(row[f"{side}_{name}"]) for name in FIELDS) for side in ("A","B")}
    visual = {side: totals[side]-int(row[f"{side}_route_alignment"]) for side in ("A","B")}
    return {"row":row,"filename":SCORE_FILE,"sha256":digest(path),"totals":totals,"visualTotals":visual}


def original_views(root):
    r1 = root / "inputs" / "r1"
    local = read_json(r1 / "runs/local_viewports.json")["views"]
    hosted = read_json(r1 / "runs/geoapify_static_completion.json")["views"]
    result = {}
    for label in ("detail","context"):
        a, b = hosted[label], local[label]
        if not a["bounds_match"] or len(a["actual_bounds"]) != 4 or not b["building_fully_inside"]:
            raise ValueError("R1_VIEW_MATCH_NOT_VERIFIED")
        if abs(a["meters_per_pixel"]-b["meters_per_pixel"]) > 0.000001:
            raise ValueError("R1_VIEW_SCALE_DIFFERS")
        result[label] = {"meters_per_pixel":b["meters_per_pixel"]}
        for letter, item in (("A",a),("B",b)):
            path = r1 / item["base"]
            if digest(path) != item["base_sha256"]:
                raise ValueError("R1_BASE_MAP_HASH_MISMATCH")
            result[label][letter] = path
    return result


def font(size, bold=False):
    path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc")
    if not path.is_file():
        choices = [
            Path("/usr/share/fonts/opentype/noto") / ("NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ]
        path = next((choice for choice in choices if choice.is_file()), path)
    if not path.is_file():
        raise FileNotFoundError("Install Microsoft YaHei or a listed Noto/WenQuanYi CJK font.")
    return ImageFont.truetype(str(path), size=size)


def label(draw, xy, message, size, color=INK, bold=False):
    draw.text(xy, message, font=font(size,bold), fill=color, anchor="lt")


def wrap_lines(text, draw, width, face):
    lines=[]
    for paragraph in text.split("\n"):
        current=""
        for char in re.findall(r"[A-Za-z0-9_:/+=.\-]+|.",paragraph):
            trial=current+char
            if current and draw.textlength(trial,font=face)>width:
                lines.append(current)
                current=char
            else:
                current=trial
        if current:
            lines.append(current)
    return lines


def wrapped(draw, xy, message, width, size, color=DIM, leading=None):
    face=font(size)
    step=leading or round(size*1.5)
    for i,line in enumerate(wrap_lines(message,draw,width,face)):
        draw.text((xy[0],xy[1]+i*step),line,font=face,fill=color,anchor="lt")


def figure05(root, views, score):
    target=root/"figures/figure05_visual_comparison.png"
    out=Image.new("RGB",(2536,2702),PAPER)
    draw=ImageDraw.Draw(out)
    draw.rectangle((0,0,2536,184),fill=TEAL)
    label(draw,(38,26),"FIGURE 05   首轮无路线底图 · 视觉信息对照",54,"#fffdf4",True)
    label(draw,(42,101),"上海博物馆人民广场馆  |  原图 1200×900 · 同一视野 · 北向上",31,"#e3efe2")
    label(draw,(42,148),"原匿名标签与首轮提交对应  A · Geoapify    B · 本地 OSM",23,"#e3efe2")
    xs=(36,1300)
    for key,y,view_name in (("detail",208,"近景  P-872C"),("context",1212,"上下文  P-2CAE")):
        item=views[key]
        for letter,x in zip(("A","B"),xs):
            label(draw,(x,y),f"{letter}   {view_name}   |   {item['meters_per_pixel']:.3f} 米/像素",29,TEAL,True)
            with Image.open(item[letter]) as source:
                if source.size!=(1200,900) or source.format!="PNG":
                    raise ValueError("R1_ORIGINAL_MAP_DIMENSIONS_MISMATCH")
                out.paste(source.convert("RGB"),(x,y+48))
            draw.rectangle((x-1,y+47,x+1200,y+948),outline="#bbc6b9",width=1)
            credits="© OpenStreetMap contributors"
            if letter=="A":
                credits+=" · © OpenMapTiles · Powered by Geoapify"
            label(draw,(x,y+955),credits,20,DIM)
    scores=score["totals"]
    heading=f"首轮人工合计 A {scores['A']}/45  ·  B {scores['B']}/45  ·  总体偏好  {score['row']['overall_preference']}"
    draw.rounded_rectangle((36,2207,2500,2300),radius=10,fill=PALE,outline=LINE)
    label(draw,(58,2230),heading,35,TEAL,True)
    notes=[
        ("建筑与空隙","用户观察：A 着色较统一，建筑与步行空隙色差较 B 小。"),
        ("道路与文字","用户观察：B 的路名、建筑名文字信息较多。显示阈值的原因仍待核验。"),
        ("步道与广场","用户认为南侧广场在两侧均未充分表达步行可达性。源面与路由边的关系见图 03 和图 06。"),
        ("入口标记","用户未在两幅图中看到北门标记。OSM 快照有北西侧 exit 与南侧 main 节点，身份与现场可用性分开核验。"),
        ("尺度与视域","两档保留完整原图和冻结边界。近景支持接入检查，上下文用于观察周边路线。"),
        ("评价口径","图面观察来自用户原记录。路由端点、缺口与路径长度另做功能核验。"),
    ]
    for idx,(title,body) in enumerate(notes):
        x=36+(idx%3)*826
        y=2323+(idx//3)*157
        draw.rounded_rectangle((x,y,x+803,y+138),radius=10,fill=SURFACE,outline=LINE)
        label(draw,(x+17,y+14),title,26,TEAL,True)
        wrapped(draw,(x+17,y+56),body,767,22)
    label(draw,(37,2657),"来源：首轮原始 PNG、视野复核记录及用户原评分 CSV。图册标识 S-1814。未裁切、拉伸或在底图中添加路线。",21,DIM)
    out.save(target,optimize=True)


def provenance_rows(root):
    r1=root/"inputs/r1"
    data=read_json(r1/"data/sh-huangpu-01.osm.json")["elements"]
    native={(item["type"],item["id"]):item for item in data}
    for kind,num in (
        ("node",13763096985),("node",6897141353),("node",6897145227),
        ("way",161090899),("way",178721643),("way",178719573),("way",761403176),
        ("way",654297629),("way",1074409256),("relation",2385771),
    ):
        if (kind,num) not in native:
            raise ValueError("FIGURE06_SOURCE_ID_NOT_FOUND")
    museum=native["way",161090899]
    plaza=native["way",178721643]
    relation=native["relation",2385771]
    if not any(member["ref"]==plaza["id"] and member["role"]=="outer" for member in relation["members"]):
        raise ValueError("FIGURE06_PLAZA_OUTER_MISMATCH")
    if not all(n in museum["nodes"] and n in plaza["nodes"] for n in [6897141353]):
        raise ValueError("FIGURE06_ENTRANCE_NODE_MISMATCH")
    for way_id,node_id in ((178737605,1890935454),(178737608,1890935415),(761403177,1890745480)):
        if not all(node_id in native["way",i]["nodes"] for i in (way_id,178721643)):
            raise ValueError("FIGURE06_PLAZA_BOUNDARY_NODE_MISMATCH")
    if native["way",761403176]["tags"].get("footway")!="crossing":
        raise ValueError("FIGURE06_CROSSING_TAG_MISMATCH")
    return [
      ("起点过街与绕行",[
          "图面可辨路口与建筑间通道。用户反馈 A 过街，B 绕起点建筑。",
          "黄陂北路轴线\nway/654297629\nway/1074409256\n两者 highway=tertiary",
          "分歧位置对应本地 node/13763096985。两段道路轴线不纳入本地步行图。",
          "A 折线与轴线空间贴合，内部边 ID UNKNOWN。B 使用另一路径绕行。",
      ]),
      ("南侧广场",[
          "底图中的南侧开放区域。绘制为面，入口与通路需要另行证据。",
          "relation/2385771\narea=yes · highway=pedestrian\n外环 way/178721643",
          "三处边界共享节点\n1890935454 · 1890935415\n1890745480\n图中未形成广场面内部通路。",
          "本地折线未穿越该面。A 本次折线也未穿越，托管面路由能力 UNKNOWN。",
      ]),
      ("共同过街与最近步段",[
          "地图可见步行线及过街标记。折线与源要素可叠合检查。",
          "人民大道过街 way/761403176\n最近步段 way/178719573\nhighway=footway · foot=yes",
          "过街 way 的节点在本地步行图。最近步段索引 98（从 0 起）的末点为 node/1890732610。",
          "B 有原生路段记录。A 折线有空间对应，托管内部图节点 UNKNOWN。",
      ]),
      ("入口参考与端点",[
          "用户原图未见北门标记。图像标注与源节点、路由端点分别核对。",
          "建筑 way/161090899\n南侧 node/6897141353 · main\n北西侧 node/6897145227 · exit",
          "main 节点同时属于建筑与广场外环。它不在首轮本地步行图中。",
          "两条折线末点距 main 均约 55 米。其余真实门位与当前通行 UNKNOWN。",
      ]),
    ]


def figure06(root):
    target=root/"figures/figure06_layers.png"
    out=Image.new("RGB",(1904,1205),PAPER)
    draw=ImageDraw.Draw(out)
    draw.rectangle((0,0,1904,140),fill=TEAL)
    label(draw,(34,23),"FIGURE 06   地图信息到路线的证据链",49,"#fffdf4",True)
    label(draw,(38,89),"同一场景的四类对象  |  每列保留其证据边界",25,"#e3efe2")
    xs=[35,504,973,1442]
    headers=["1  视觉对象","2  源地图对象","3  路由图节点与边","4  路线采用情况"]
    for x,heading in zip(xs,headers):
        draw.rounded_rectangle((x,165,x+425,215),radius=8,fill=PALE,outline=LINE)
        label(draw,(x+14,178),heading,25,TEAL,True)
    for index,(topic,cells) in enumerate(provenance_rows(root)):
        y=239+index*217
        label(draw,(35,y),topic,25,TEAL,True)
        for col,(x,content) in enumerate(zip(xs,cells)):
            draw.rounded_rectangle((x,y+37,x+425,y+194),radius=9,fill=NOTE if col==3 else SURFACE,outline=LINE)
            wrapped(draw,(x+13,y+49),content,399,21,INK,29)
    label(draw,(36,1138),"读法：横向查看证据层。相邻列并列记录观察与证据，不能据此把所有可见对象认作可走的边。",20,DIM)
    label(draw,(36,1168),"来源：冻结 OSM 矢量、首轮保存路线、首轮用户 CSV。A 托管路网和引擎内部状态未公开。",20,DIM)
    out.save(target,optimize=True)


def build(root=ROOT, figures_only=False):
    score=input_score(root)
    views=original_views(root)
    (root/"figures").mkdir(exist_ok=True)
    figure05(root,views,score)
    figure06(root)
    if figures_only:
        return
    source=root/"analysis/viewer_payload.json"
    payload=read_json(source)
    if set(payload["presets"])!={"overview","origin","plaza","endpoint"}:
        raise ValueError("EXPECTED_ALL_FOUR_VIEWS")
    if not isinstance(payload["features"],list) or not payload["features"]:
        raise ValueError("NO_ACTUAL_GEOMETRY_FEATURES")
    payload["score"]=score
    payload["originalMaps"]={key:{letter:"../"+views[key][letter].relative_to(root).as_posix() for letter in ("A","B")}
                             for key in ("detail","context")}
    payload["figures"]=[{"path":path,"title":title,"note":note} for path,title,note in FIGURES]
    (root/"web").mkdir(exist_ok=True)
    text=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    (root/"web/data.js").write_text("window.R2_EVIDENCE="+text+";\n",encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figures-only",action="store_true")
    args=parser.parse_args()
    build(figures_only=args.figures_only)
