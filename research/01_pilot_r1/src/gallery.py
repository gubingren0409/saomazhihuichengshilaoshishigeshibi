"""Build the local blind gallery and blank human-review materials from actual run artifacts."""

import argparse
import csv
import filecmp
import json
import os
from html import escape
from math import isfinite
from pathlib import Path
import re
from secrets import SystemRandom
import shutil


ROOT = Path(__file__).resolve().parents[1]
VIEWS = {"detail": ("近景", "建筑边界和入口接近区"), "context": ("上下文", "街区和可能的绕行空间")}
ATTRIBUTION = {
    "osm": "© OpenStreetMap contributors · ODbL",
    "geoapify": "Powered by Geoapify · © OpenStreetMap contributors",
}
STATUS = {
    "LIVE": "已取得当前服务结果",
    "LOCAL_REAL": "已取得本次真实结果",
    "OK": "已取得本次结果",
    "AVAILABLE": "已取得本次结果",
    "ZERO_COST_QUOTA_NOT_CONFIRMED": "免费额度待核实，未调用服务",
    "VIEWPORT_NOT_VERIFIED": "已取得图像，实际地理范围尚待核验",
    "BLOCKED_NO_KEY": "凭据未配置",
    "BLOCKED_KEY_MISSING": "凭据未配置",
    "NO_KEY": "凭据未配置",
    "MISSING_KEY": "凭据未配置",
    "GEOAPIFY_KEY_MISSING": "凭据未配置",
    "NOT_CONFIGURED": "凭据未配置",
    "CONFIG_REQUIRED": "凭据未配置",
    "BLOCKED_PERMISSION": "适用许可待确认",
    "BLOCKED_RETENTION": "适用许可待确认",
    "REQUIRES_PROVIDER_CONFIRMATION": "适用许可待确认",
    "VIEWPORT_MISMATCH": "视野不匹配，暂不作同尺度判读",
    "VIEWPORT_NOT_VERIFIED": "实际视野尚未核验",
    "UNAVAILABLE": "本次未取得结果",
    "NOT_RUN": "本次未运行",
    "PARTIAL": "部分结果缺失",
    "FAILED": "本次未取得可用结果",
    "BLOCKED": "本次结果受阻",
}
METRICS = (
    ("building_outline", "建筑轮廓清晰度", "轮廓看不清", "主要边界可见，局部模糊", "目标完整，边界清楚"),
    ("building_road_separation", "建筑与道路区分度", "建筑和道路容易混淆", "能区分主要图层", "靠近处也能清楚区分"),
    ("pedestrian_visibility", "步行通道可辨性", "几乎无法辨认步行通道", "部分通道可辨，连接不明", "主要步道及连接清楚"),
    ("entrance_context", "入口附近细节充分性", "缺少可用细节", "可看出附近构造，接入点仍不明", "附近细节足以判断接入位置"),
    ("occlusion", "文字与图标遮挡程度", "关键区域大面积被遮挡", "部分关键细节被遮挡", "关键区域几乎无遮挡"),
    ("target_identification", "目标建筑定位容易程度", "难以确定目标", "需要结合视野信息定位", "可迅速且明确定位"),
    ("detail_access", "近景识别接入位置的适用性", "近景无法支撑判断", "能看出大致接近范围", "可清楚判断具体接近位置"),
    ("context_detour", "上下文判断绕行的充分性", "无法判断绕行", "可判断一部分绕行方向", "主要外围通路及绕行空间清楚"),
    ("route_alignment", "路线与地图对齐程度", "折线明显偏离通道或穿越障碍", "大体对齐，局部不明", "可见段与步行空间一致"),
)
FIELDS = (
    "blind_scene_id", "detail_pair_id", "context_pair_id",
    *(f"{side}_{metric[0]}" for side in ("A", "B") for metric in METRICS),
    "A_route_visibly_unreasonable", "B_route_visibly_unreasonable",
    "overall_preference", "failure_reason", "remarks", "scored_at_utc",
)
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
LIVE_ALIAS = re.compile(r"/api/blind/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){0,4}\Z")


def page(title, body):
    return (
        '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title><link rel="stylesheet" href="style.css"></head>'
        f'<body>{body}</body></html>\n'
    )


def blind_keys(root, scenes):
    """Retain the same anonymous labels across rebuilds, before any human scoring."""
    path = root / "07_BLIND_REVEAL_MAP_PRIVATE.csv"
    fields = ["scene_id", "blind_scene_id", "detail_pair_id", "context_pair_id", "A_provider", "B_provider"]
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = {r["scene_id"]: r for r in csv.DictReader(f)}
    else:
        rows = {}
    used = {value for row in rows.values() for key, value in row.items() if key.endswith("_id")}
    random = SystemRandom()

    def fresh(prefix):
        while True:
            value = f"{prefix}-{random.randrange(0x1000, 0x10000):04X}"
            if value not in used:
                used.add(value)
                return value

    for scene in scenes:
        ident = scene["scene_id"]
        if ident in rows:
            continue
        a, b = random.sample(list(ATTRIBUTION), 2)
        rows[ident] = dict(zip(fields, (ident, fresh("S"), fresh("P"), fresh("P"), a, b)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows.values())
    return rows


def alias(root, output, value, key):
    if not value:
        return None
    if LIVE_ALIAS.fullmatch(value):
        return value
    source = (root / value).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.suffix.lower() not in IMAGE_TYPES:
        raise ValueError("Gallery image must be an existing local artifact or a credential-free blind proxy route.")
    relative = Path("assets") / f"{key}{source.suffix.lower()}"
    dest = output / relative
    dest.parent.mkdir(exist_ok=True)
    if dest.exists() and filecmp.cmp(source, dest, shallow=False):
        return relative.as_posix()
    if dest.exists():
        dest.unlink()
    try:
        os.link(source, dest)
    except OSError:
        shutil.copyfile(source, dest)
    return relative.as_posix()


def status_text(data, has_image):
    status = data.get("status", "AVAILABLE" if has_image else "NOT_RUN")
    return STATUS.get(status, "已取得本次结果" if has_image else "本次未取得可用结果")


def authorized_ref(data, provider, layer):
    value = data.get(layer)
    if not value or provider != "geoapify":
        return value, None
    if data.get("human_display_verified") is not True:
        return None, "人工图册的图像展示许可待确认"
    if not LIVE_ALIAS.fullmatch(value) and data.get("local_retention_verified") is not True:
        return None, "本地图像留存许可待确认"
    return value, None


def tile(root, output, data, provider, pair, side, layer):
    source, policy_reason = authorized_ref(data, provider, layer)
    ref = alias(root, output, source, f"{pair}-{side}-{layer}")
    title = f"{side} 侧"
    if not ref:
        reason = policy_reason or status_text(data, False)
        if layer == "route" and data.get("base") and reason.startswith("已取得"):
            reason = "本侧未取得可用的路线叠加图"
        return (
            f'<figure><h4>{title}</h4><div class="unavailable"><span>未取得图像</span>'
            f'<p>{escape(reason)}</p></div></figure>'
        )
    credit = data.get("attribution") or ATTRIBUTION[provider]
    caption = escape(status_text(data, True))
    if layer == "route":
        identity = data.get("route_identity")
        if identity == "PARTIAL_DIAGNOSTIC_TO_NEAREST_MAPPED_SEGMENT":
            caption += " · 诊断折线只到路网候选"
        elif identity:
            caption += " · 返回的步行路线"
        offset = data.get("route_target_offset_m")
        if type(offset) in (int, float) and isfinite(offset) and offset >= 0:
            caption += f" · 折线终点距入口参考约 {offset:.0f} 米"
        if data.get("route_control_points") == 4:
            caption += " · 四个小圆点用于视野核验"
    if not data.get("attribution_burned_in"):
        caption += f' <span class="credit">{escape(credit)}</span>'
    return (
        f'<figure><h4>{title}</h4><a class="frame" href="{escape(ref, quote=True)}" target="_blank" rel="noopener"'
        f' aria-label="{title}原图"><img src="{escape(ref, quote=True)}" alt="{pair} {title}" loading="lazy"></a>'
        f'<figcaption>{caption} <span>点击看原图</span></figcaption></figure>'
    )


def number_list(raw, n):
    if not isinstance(raw, (list, tuple)) or len(raw) != n or any(type(v) not in (int, float) or not isfinite(v) for v in raw):
        return "未记录"
    return " / ".join(f"{v:.6f}" for v in raw)


def side_contract(side, data):
    if not data.get("base"):
        return f'<p>{side} 侧暂无实图，实际尺度待核验。</p>'
    qa = data.get("qa") or {}
    if not isinstance(qa, dict):
        qa = {}
    stats = {**qa, **data}
    keys = (
        (("pixel_size", "image_size", "dimensions"), "画布（宽／高）", 2),
        (("target_pixel_size", "building_pixel_size"), "建筑像素（宽／高）", 2),
        (("actual_bounds", "bounds"), "实际边界（西／南／东／北）", 4),
        (("meters_per_pixel", "m_per_px", "resolution_m_per_px"), "米／像素", 0),
        (("target_area_ratio", "building_area_ratio"), "目标面积占比", 0),
    )
    items = []
    for aliases, title, count in keys:
        value = next((stats[k] for k in aliases if stats.get(k) is not None), None)
        if count and value is not None:
            shown = number_list(value, count)
        elif type(value) in (int, float) and isfinite(value):
            shown = f"{value:.6f}"
        else:
            continue
        items.append(f'{title} {shown}')
    if not items:
        return f'<p>{side} 侧实测尺度见技术记录。</p>'
    return f'<p>{side} 侧 {" · ".join(items)}</p>'


def view_section(root, output, view, key, identity):
    title, description = VIEWS[key]
    pair = identity[f"{key}_pair_id"]
    by_provider = view.get("assets") or {}
    sides = ("A", "B")
    base, overlay, contracts = [], [], []
    for side in sides:
        provider = identity[f"{side}_provider"]
        data = by_provider.get(provider) or {}
        base.append(tile(root, output, data, provider, pair, side, "base"))
        overlay.append(tile(root, output, data, provider, pair, side, "route"))
        admitted, _ = authorized_ref(data, provider, "base")
        contracts.append(side_contract(side, data if admitted else {}))
    bounds = number_list(view.get("bounds"), 4)
    center = number_list(view.get("center"), 2)
    return (
        f'<section class="view"><div class="view-head"><div><h3>{title}</h3><p>{description}</p></div>'
        f'<code>{pair}</code></div><div class="map-pair">{"".join(base)}</div>'
        '<details><summary>展开同视野路线叠加</summary>'
        f'<div class="map-pair route-pair">{"".join(overlay)}</div></details>'
        '<details><summary>查看视野合同</summary>'
        f'<p>约定的 WGS84 边界（西／南／东／北） {bounds}</p><p>中心（经度／纬度） {center}</p>'
        f'{"".join(contracts)}'
        '<p>二维视野，正北朝上。路由折线用于地图判读。</p></details></section>'
    )


def write_blank(root, identities):
    path = root / "06_USER_SCORE_SHEET.csv"
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as f:
            old = list(csv.DictReader(f))
        ids_now = [tuple(row[k] for k in FIELDS[:3]) for row in identities]
        ids_before = [tuple(row.get(k) for k in FIELDS[:3]) for row in old]
        if ids_before == ids_now:
            return
        if any(
            ids_before[index] not in ids_now or any(row.get(k) for k in FIELDS[3:])
            for index, row in enumerate(old)
        ):
            raise ValueError("Existing score sheet contains user input or a different frozen cohort.")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(FIELDS)
        for ident in identities:
            writer.writerow([*(ident[k] for k in FIELDS[:3]), *("" for _ in FIELDS[3:])])


def select(name, options, label):
    return f'<select name="{name}" aria-label="{escape(label, quote=True)}"><option value="">留空</option>' + "".join(
        f'<option value="{escape(value, quote=True)}">{escape(display)}</option>' for value, display in options
    ) + "</select>"


def score_scene(identity):
    ident = identity["blind_scene_id"]
    table = []
    for key, label, low, mid, high in METRICS:
        def side_cell(side):
            return "<td>" + select(f"{side}_{key}", [(str(n), str(n)) for n in range(1, 6)], f"{ident} {side} 侧 {label}") + "</td>"
        table.append(f'<tr><th scope="row">{label}<small>1 分 {low} · 3 分 {mid} · 5 分 {high}</small></th>{side_cell("A")}{side_cell("B")}</tr>')
    options = [("是", "是"), ("否", "否"), ("不确定", "不确定")]
    unreasonable = "".join(
        f'<td>{select(f"{side}_route_visibly_unreasonable", options, f"{ident} {side} 侧视觉路线是否明显不合理")}</td>'
        for side in ("A", "B")
    )
    preference = select("overall_preference", [(v, v) for v in ("A", "B", "相同", "都不可用")], f"{ident} 总体偏好")
    return (
        f'<section class="score-scene" data-id="{ident}" data-detail="{identity["detail_pair_id"]}" data-context="{identity["context_pair_id"]}">'
        f'<h2>{ident}</h2><p>近景 {identity["detail_pair_id"]} · 上下文 {identity["context_pair_id"]}</p>'
        '<div class="score-scroll"><table><thead><tr><th>指标及锚点</th><th>A</th><th>B</th></tr></thead>'
        f'<tbody>{"".join(table)}<tr><th scope="row">视觉明显不合理路线</th>{unreasonable}</tr></tbody></table></div>'
        f'<label class="free">总体偏好 {preference}</label>'
        f'<label class="free" for="{ident}-failure">失败原因</label><textarea id="{ident}-failure" name="failure_reason" rows="2"></textarea>'
        f'<label class="free" for="{ident}-remarks">备注</label><textarea id="{ident}-remarks" name="remarks" rows="2"></textarea></section>'
    )


def build(root, run_path):
    root = root.resolve()
    data = json.loads(run_path.read_text(encoding="utf-8-sig"))
    scenes = data["scenes"]
    if not 1 <= len(scenes) <= 6 or len({s["scene_id"] for s in scenes}) != len(scenes):
        raise ValueError("Expected one to six unique real scene records.")
    output = root / "visuals" / "blind_review"
    output.mkdir(parents=True, exist_ok=True)
    keys = blind_keys(root, scenes)
    identities = [keys[s["scene_id"]] for s in scenes]
    write_blank(root, identities)
    cards = []
    completed = 0
    for scene, ident in zip(scenes, identities):
        label = escape(scene.get("label") or "固定场景")
        views = scene.get("views") or {}
        completed += sum(
            all(authorized_ref(((v.get("assets") or {}).get(provider) or {}), provider, "base")[0]
                for provider in ATTRIBUTION)
            for v in views.values()
        )
        sections = "".join(view_section(root, output, views.get(v, {}), v, ident) for v in VIEWS)
        cards.append(
            f'<article class="scene"><div class="scene-head"><div><p class="eyebrow">场景 {ident["blind_scene_id"]}</p>'
            f'<h2>{label}</h2></div></div>{sections}</article>'
        )
    gallery = (
        '<header class="hero"><div class="wrap"><p class="eyebrow">本地 · 同场景 · 人工评判</p>'
        '<h1>建筑周边地图对照</h1><p>先观察无路线图面，再展开折线。A/B 顺序在场景内固定，场景之间随机分配。'
        '图面署名照常保留。</p><div class="hero-meta">'
        f'<span>{len(scenes)} 个场景</span><span>{completed} / {2*len(scenes)} 组双侧底图</span>'
        '<span>PENDING_USER_REVIEW</span></div></div></header>'
        '<nav class="wrap actions"><a class="button" href="score.html">打开空白评分表</a>'
        '<a href="../../06_USER_SCORE_SHEET.csv" download>下载空白 CSV</a></nav>'
        '<main class="wrap"><aside class="note">只对实际可见的内容评分。缺少任一侧时，留空相应评分和总体偏好。'
        '路线在画面上的合理性由你判断。</aside>'
        f'{"".join(cards)}</main><footer class="wrap">人工评分独立记录。按用户确认顺序揭盲。</footer>'
    )
    score = (
        '<header class="hero"><div class="wrap"><p class="eyebrow">人工评判 · 空白表单</p><h1>地图对照评分</h1>'
        '<p>观察后选择 1–5 分。不确定的项保留空白。评分只在当前页面和你下载的本地文件中。</p>'
        '</div></header><main class="wrap"><nav class="actions"><a href="index.html">返回匿名图册</a>'
        '<a href="../../06_USER_SCORE_SHEET.csv" download>下载空白 CSV</a></nav>'
        f'<form id="score-form" data-fields="{escape(json.dumps(FIELDS), quote=True)}">{"".join(score_scene(i) for i in identities)}'
        '<button id="save" type="submit">下载我的评分与校验凭证</button>'
        '<p id="save-status" class="note" role="status" hidden></p></form>'
        '<p class="note">留好填写后的 CSV 和校验凭证，再由你决定何时揭盲。</p></main><script src="score.js" defer></script>'
    )
    (output / "index.html").write_text(page("建筑周边地图对照", gallery), encoding="utf-8")
    (output / "score.html").write_text(page("地图对照评分", score), encoding="utf-8")
    return {"scenes": len(scenes), "two_sided_base_pairs": completed, "human": "PENDING_USER_REVIEW"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run", type=Path)
    args = parser.parse_args()
    path = args.run or args.root / "runs" / "gallery_input.json"
    print(json.dumps(build(args.root, path), ensure_ascii=False))


if __name__ == "__main__":
    main()
