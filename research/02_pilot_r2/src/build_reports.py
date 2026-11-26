"""Build the provenance table and verbatim score trace from verified inputs."""
import csv
from hashlib import sha256
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SCORE=ROOT/"inputs/user_scores_20261109T110307129Z.csv"
SCORE_SHA="bf9031591b4d67be39ec7e0239432116a01f3197b414e88d3e8a682a68db108a"
ITEMS=(
    ("building_outline","建筑轮廓清晰度"),("building_road_separation","建筑与道路区分度"),
    ("pedestrian_visibility","步行通道可辨性"),("entrance_context","入口附近细节"),
    ("occlusion","文字与图标遮挡"),("target_identification","目标建筑定位"),
    ("detail_access","近景识别接入位置"),("context_detour","上下文判断绕行"),
    ("route_alignment","路线与地图对齐"),
)
FIGURES=(
    ("figure01_global.png","两条实际路线的全局对照","R1 两份实际路线几何，源 OSM 建筑和路网","way/161090899;node/476682043;node/13763096985;node/6897141353","EPSG:32651；折线端点原坐标"),
    ("figure02_origin.png","起点分歧及原生过街","analysis/topology.json；原生 OSM 线与实际折线","node/13763096985;way/39763758;way/39764359;way/654297629;way/1074409256;way/761403176","EPSG:32651；托管对应为几何证据"),
    ("figure03_plaza.png","南侧广场及线网接点","analysis/topology.json；冻结 OSM 关系、外围线和实际折线","relation/2385771;way/178721643;node/1890745480;node/1890935415;node/1890935454","EPSG:32651；三处连接只到边界"),
    ("figure04_endpoint.png","55 米末段缺口","analysis/endpoint_metrics.json；冻结馆舍、两末点和入口参考","way/161090899;way/178719573;node/1890732610;node/6897141353","EPSG:32651 展示；WGS84 椭球测距，不补路线"),
    ("figure05_visual_comparison.png","四张首轮无路线底图与人工观察","原始 1200×900 静态底图和用户原评分","P-872C;P-2CAE;way/161090899;relation/2385771;node/6897141353;node/6897145227","同尺度原图逐像素保留，图注来自用户"),
    ("figure06_layers.png","视觉、源对象、路网、路线分层证据","冻结 OSM 源要素和实际路线及邻接","relation/2385771;way/178721643;way/761403176;way/178719573;node/6897141353","证据流程图；未知处不连实线"),
)


def score_trace():
    data=SCORE.read_bytes()
    assert len(data)==1583 and sha256(data).hexdigest()==SCORE_SHA
    with SCORE.open(encoding="utf-8-sig",newline="") as stream:
        [row]=list(csv.DictReader(stream))
    values={side:[int(row[side+"_"+key]) for key,_ in ITEMS] for side in ("A","B")}
    assert [sum(values[side]) for side in ("A","B")]==[42,43]
    assert row["overall_preference"]=="相同"
    lines=[
        "# 第一轮用户原始评分与文字反馈",
        "",
        "评分来源是用户实际提交的文件。原文件逐字节保留，不做第二次评分。OBSERVED_USER 表示用户直接记录，属于 OBSERVED 的一类。原盲评映射 A＝Geoapify、B＝本地 OSM，以首轮图册与输入映射记录核验。",
        "",
        f"- 场景 {row['blind_scene_id']}，近景 {row['detail_pair_id']}，上下文 {row['context_pair_id']}。",
        f"- 原始记录时间 {row['scored_at_utc']}，即北京时间 2026-11-09 19:03:07.129。",
        f"- SHA256 `{SCORE_SHA}`。 [原始 CSV](inputs/{SCORE.name})",
        "",
        "| 原项 | A | B |",
        "| --- | ---: | ---: |",
    ]
    for (_,label),a,b in zip(ITEMS,values["A"],values["B"]):
        lines.append(f"| {label} | {a} | {b} |")
    lines.extend([
        f"| 九项合计 | {sum(values['A'])}/45 | {sum(values['B'])}/45 |",
        f"| 前八项算术小计 | {sum(values['A'][:-1])}/40 | {sum(values['B'][:-1])}/40 |",
        f"| 路线视觉明显不合理 | {row['A_route_visibly_unreasonable']} | {row['B_route_visibly_unreasonable']} |",
        f"| 总体偏好 | {row['overall_preference']} | {row['overall_preference']} |",
        "",
        "## 原文",
        "",
        "以下保留 `failure_reason` 原文。原 `remarks` 字段为空。",
        "",
    ])
    lines.extend("> "+line for line in row["failure_reason"].splitlines())
    lines.extend([
        "",
        "## 溯源说明",
        "",
        "- “北门没有标注”是用户对首轮图册的观察。OSM 源另有北西侧 node/6897145227，标为出口，现时公众可用性未知。",
        "- “标准答案”保留为用户原话。研究复算使用南侧 `entrance=main` 源参考，现场入口位置未核验。",
        "- A 走得更直接与 B 绕行可从两条实际折线复算。更直接的折线是否现实可通行未核验，两条线随后有共同的已制图过街位置。",
        "- 广场色块和路线算法能否穿越是两层问题。当前能核验的是三个边界接点和本地图的内部缺边。",
        "",
    ])
    (ROOT/"03_USER_FEEDBACK_TRACEABILITY.md").write_text("\n".join(lines),encoding="utf-8")


def figure_manifest():
    with (ROOT/"figure_manifest.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        csv_=csv.writer(stream)
        csv_.writerow(["path","title","source_artifact","native_ids","scope","width_px","height_px","bytes","sha256","evidence_status"])
        for name,title,source,ids,scope in FIGURES:
            path=ROOT/"figures"/name
            data=path.read_bytes()
            with Image.open(path) as image:
                width,height=image.size
                image.verify()
            csv_.writerow([f"figures/{name}",title,source,ids,scope,width,height,len(data),
                           sha256(data).hexdigest(),"OBSERVED" if name.startswith("figure05") else "RECOMPUTED"])


if __name__=="__main__":
    score_trace()
    figure_manifest()
