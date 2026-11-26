"""Publish attributed, anonymous review images and an unfilled human rubric."""
from collections import Counter
import csv
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
from secrets import token_hex, randbelow
from shutil import copyfile

ROOT=Path(__file__).resolve().parents[1]
METRICS=(
 ("building_outline","建筑轮廓","看不清","主要轮廓可见","完整清晰"),
 ("building_road_separation","建筑与道路区分","容易混淆","能分主层","细部区分明确"),
 ("pedestrian_visibility","步行通道","几乎不可辨","部分可辨","连续通路易辨"),
 ("entrance_context","入口附近细节","基本缺失","只见大致环境","接近位置清楚"),
 ("occlusion","文字与图标遮挡","遮挡严重","局部遮挡","关键区域少遮挡"),
 ("target_identification","目标建筑定位","难以找到","需借助街区","能立即定位"),
 ("detail_access","近景接入判读","无法判断","大致可辨","可看清具体接近位置"),
 ("context_detour","上下文绕行判读","看不出","可推断部分","主要外围通路清楚"),
 ("route_alignment","路线与地图对齐","明显偏离","大体对齐","可见段清楚对齐"),
 ("open_space","开放空间表达","无法区分","只见边界","边界与连接语义清楚"),
 ("sidewalk_crossing","人行道与过街","难辨","部分可见","主要人行道和过街可辨"),
 ("entrance_identity","入口标记及身份","无标记或含混","有标记但身份不清","标记和身份均可读"),
 ("interbuilding_walkability","建筑间步行空间","难辨","能见部分空隙","边界及候选通行空间清楚"),
)
PREFERENCE=(("cv_input_preference","更适合视觉解析输入"),
            ("approach_input_preference","更适合末端路径补全输入"),
            ("overall_preference","总体偏好"))
FIELDS=("blind_scene_id","detail_pair_id","context_pair_id",
        *(f"{side}_{m[0]}" for side in ("A","B") for m in METRICS),
        *(key for key,_ in PREFERENCE),"notes","scored_at_utc")
CREDITS={"osm":"© OpenStreetMap contributors","geoapify":"© OpenStreetMap contributors · © OpenMapTiles · Powered by Geoapify"}
LABELS={"detail":"近景","context":"上下文"}


def plain(value):
    return escape(str(value if value is not None else "—"),quote=True)


def assignment(root,cases):
    path=root/"private_local/blind_mapping.csv"
    path.parent.mkdir(exist_ok=True)
    columns=("scene_id","blind_scene_id","detail_pair_id","context_pair_id","A_provider","B_provider")
    if path.is_file():
        with path.open(encoding="utf-8-sig",newline="") as f:
            rows=list(csv.DictReader(f))
        assert {row["scene_id"] for row in rows}=={case["scene_id"] for case in cases}
        return {row["scene_id"]:row for row in rows}
    rows=[]
    for case in cases:
        if case.get("historical"):
            tags=["S-1814","P-872C","P-2CAE"]
            sides=["geoapify","osm"]
        else:
            tags=["S-"+token_hex(3).upper(),"P-"+token_hex(3).upper(),"P-"+token_hex(3).upper()]
            sides=["osm","geoapify"] if randbelow(2)==0 else ["geoapify","osm"]
        rows.append(dict(zip(columns,[case["scene_id"],*tags,*sides])))
    with path.open("x",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
    return {row["scene_id"]:row for row in rows}


def alias(root, out, image, prefix):
    if not image:
        return None
    source=(root/image).resolve()
    if not source.is_relative_to(root.resolve()) or source.suffix.lower()!=".png" or not source.is_file():
        raise ValueError("UNVERIFIED_IMAGE_REFERENCE")
    target=out/"assets"/(prefix+".png")
    target.parent.mkdir(exist_ok=True)
    if target.is_file():
        if target.read_bytes()!=source.read_bytes():
            raise ValueError("BLIND_ASSET_ALREADY_BOUND_TO_DIFFERENT_BYTES")
    else:
        try: os.link(source,target)
        except OSError: copyfile(source,target)
    return f"assets/{target.name}"


def side_image(root,out,pair,side,provider,asset,kind):
    local=alias(root,out,asset.get(kind),f"{pair}-{side}-{kind}")
    text=asset.get("overlay_caption") if kind=="overlay" else asset.get("base_caption")
    if not local:
        return f'<figure><b>{side} 侧</b><div class="missing">{plain(text or "当前无真实图像")}</div></figure>'
    attribution=(f'<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'
                 +(' · <a href="https://openmaptiles.org/">© OpenMapTiles</a> · '
                    'Powered by <a href="https://www.geoapify.com/">Geoapify</a>' if provider=="geoapify" else ""))
    return (f'<figure><b>{side} 侧</b><a href="{local}" target="_blank" rel="noopener" title="打开原图">'
            f'<img src="{local}" alt="{pair} {side} 侧 {kind}" loading="lazy"></a>'
            f'<figcaption>{plain(text or "已取得真实图像")}<br>{attribution}</figcaption></figure>')


def frame(title,body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'+f'<title>{plain(title)}</title><link rel="stylesheet" href="style.css">{body}</html>'

def report_section(root,out,case,mapping):
    head=(f'<article id="{mapping["blind_scene_id"]}"><div class="casehead"><div><p class="tag">{plain(mapping["blind_scene_id"])} · {plain(case["category"])}</p>'
          f'<h2>{plain(case["label"])}</h2></div><span>{plain(case.get("status_label",""))}</span></div>')
    sections=[]
    for view,label in LABELS.items():
        v=case["views"].get(view,{})
        pair=mapping[f"{view}_pair_id"]
        by_provider=v.get("assets",{})
        images,overlays=[],[]
        for side in ("A","B"):
            provider=mapping[side+"_provider"]
            data=by_provider.get(provider,{})
            images.append(side_image(root,out,pair,side,provider,data,"base"))
            overlays.append(side_image(root,out,pair,side,provider,data,"overlay"))
        sections.append(f'<section class="view"><div class="viewhead"><h3>{label}</h3><code>{pair}</code></div>'
                        f'<p>{plain(v.get("scale_caption","尺度未核实"))}</p><div class="pair">{"".join(images)}</div>'
                        '<details><summary>切换查看路线叠加</summary>'
                        f'<div class="pair">{"".join(overlays)}</div></details></section>')
    return head+"".join(sections)+"</article>"


def write_score(root,out,rows,case_by_id):
    csv_path=root/"07_USER_SCORE_SHEET.csv"
    if not csv_path.exists():
        with csv_path.open("x",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
            for row in rows:
                writer.writerow({k:row[k] for k in FIELDS[:3]})
    else:
        with csv_path.open(encoding="utf-8-sig",newline="") as f:
            current=list(csv.DictReader(f))
        assert [r["blind_scene_id"] for r in current]==[r["blind_scene_id"] for r in rows]
    blocks=[]
    def options(values):
        return '<option value="">留空</option>'+''.join(f'<option value="{plain(x)}">{plain(x)}</option>' for x in values)
    for row in rows:
        section=f'<fieldset data-row="{plain(row["blind_scene_id"])}"><legend>{plain(case_by_id[row["scene_id"]]["label"])} · {plain(row["blind_scene_id"])}</legend>'
        for k in FIELDS[:3]:
            section+=f'<input type="hidden" name="{k}" value="{plain(row[k])}">'
        section+='<div class="rubric"><b>评价项 / 1、3、5 分锚点</b><b>A</b><b>B</b>'
        for key,name,a,b,c in METRICS:
            section+=f'<label>{plain(name)}<small>1 {plain(a)}　3 {plain(b)}　5 {plain(c)}</small></label>'
            section+=''.join(f'<select name="{side}_{key}" aria-label="{side} {plain(name)}">{options(range(1,6))}</select>' for side in ("A","B"))
        section+='</div>'
        for key,label in PREFERENCE:
            section+=f'<label class="preference">{plain(label)} <select name="{key}">{options(("A","B","相同","都不可用"))}</select></label>'
        section+='<label class="preference">备注 <textarea name="notes" rows="3"></textarea></label></fieldset>'
        blocks.append(section)
    body=('<header><p class="tag">R3 · 空白人工评分</p><h1>地图图面与末端路径输入</h1>'
          '<p>看完图后填写。判断不确定、任一侧缺图或路线不可比时可留空。上海博物馆原评分不重复填写。</p></header>'
          '<main><nav><a href="index.html">返回图册</a><a href="../../07_USER_SCORE_SHEET.csv" download>下载空白 CSV</a></nav>'
          f'<form id="scores" data-fields="{plain(json.dumps(FIELDS))}">'+''.join(blocks)+
          '<button type="submit">下载我的评分 CSV</button><p id="save-note" role="status"></p></form></main>'
          '<script src="score.js"></script>')
    (out/"score.html").write_text(frame("R3 人工评分",body),encoding="utf-8")


def build(root=ROOT):
    cases=json.loads((root/"runs/display_cases.json").read_text(encoding="utf-8"))["scenes"]
    blind=assignment(root,cases)
    out=root/"visuals/blind_review"
    out.mkdir(parents=True,exist_ok=True)
    sections=[report_section(root,out,c,blind[c["scene_id"]]) for c in cases]
    table=[]
    for c in cases:
        row=blind[c["scene_id"]]
        kinds=[]
        for view in LABELS:
            v=c["views"].get(view,{})
            sides=v.get("assets",{})
            n=sum(bool(item.get("base")) for item in sides.values())
            kinds.append(f"<td>{n}/2 张 · {plain(v.get('comparison_status','未知'))}</td>")
        table.append(f'<tr><th><a href="#{row["blind_scene_id"]}">{plain(c["label"])}</a></th><td>{plain(c["category"])}</td>{"".join(kinds)}</tr>')
    body=('<header><p class="tag">OSM–GEOAPIFY PILOT R3 · 真实同场景图册</p><h1>建筑末端接近对照</h1>'
          '<p>先看无路线底图，再展开路线图。各场景 A/B 顺序已随机冻结，图片保留来源署名。</p></header>'
          '<main><nav><a href="score.html">打开空白评分页</a><a href="../../07_USER_SCORE_SHEET.csv" download>空白 CSV</a>'
          '</nav><details><summary>评分后查看按来源标注的诊断</summary><nav><a href="../routes/index.html">统一底图路线与细节</a><a href="../failure_cases/index.html">失败和未知</a></nav></details>'
          '<h2>场景总览矩阵</h2><table><thead><tr><th>建筑</th><th>类型</th><th>近景</th><th>上下文</th></tr></thead>'
          f'<tbody>{"".join(table)}</tbody></table>{"".join(sections)}'
          '<footer>人工评判为 PENDING_USER_REVIEW。路线图面和现实通行分开判断。</footer></main>')
    (out/"index.html").write_text(frame("R3 匿名图册",body),encoding="utf-8")
    write_score(root,out,[blind[c["scene_id"]] for c in cases if not c.get("historical")],
                {c["scene_id"]:c for c in cases})
    print(json.dumps({"scenes":len(cases),"new_blank_score_rows":sum(not c.get("historical") for c in cases),
                      "image_pairs":sum(sum(bool(a.get("base")) for a in v.get("assets",{}).values())==2
                                    for c in cases for v in c["views"].values())}))


if __name__=="__main__":
    build()
