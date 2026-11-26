"""Draw a same-viewport A/B comparison from the frozen map and trial GeoJSON."""
import argparse
import html
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.with_name("OSM_GEOAPIFY_R4_REV1")
MUSEUM = "sh-huangpu-01"
PROJECT = Transformer.from_crs(4326, 32651, always_xy=True).transform

LAYERS = {
    "park": ('fill="#edf0dc" stroke="#86956c" stroke-width="1.25" stroke-dasharray="4 4"',),
    "grass": ('fill="#d3dfc4" stroke="#aab99e" stroke-width=".65"',),
    "water": ('fill="#c9e1e6" stroke="#9cbdc7" stroke-width=".65"',),
    "road": ('fill="none" stroke="#c7bba8" stroke-width="2"',),
    "plaza": ('fill="#d3eaf5" stroke="#639cb0" stroke-width="1.15"',),
    "building": ('fill="#e7dfd4" stroke="#b4a99b" stroke-width=".85"',),
    "target": ('fill="#f1dbc2" stroke="#a8764a" stroke-width="1.35"',),
    "walk": ('fill="none" stroke="#688b88" stroke-width="1.05"',),
    "fence": ('fill="none" stroke="#93675e" stroke-width="1.25" stroke-dasharray="3 2"',),
}

CSS = """
:root{color:#2d3238;background:#fcfaf7;font:15px/1.55 'Microsoft YaHei','PingFang SC',sans-serif;--ink:#253f4d;--muted:#54616a;--line:#d9e0e3}
*{box-sizing:border-box}body{margin:0}header,main,footer{width:min(1320px,calc(100% - 36px));margin:auto}
header{padding:30px 0 19px;border-bottom:1px solid var(--line)}header small{font-weight:750;color:#455d6a}h1{font-size:clamp(25px,4vw,47px);letter-spacing:-.04em;margin:5px 0 8px}
h2,h3,p{margin:0}p{color:var(--muted)}a{color:#254f72;text-underline-offset:3px}button{font:inherit}
.controls{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:19px 0 9px}
.controls [role=group]{display:flex;gap:5px}button{border:1px solid #a6b9c1;border-radius:5px;padding:6px 11px;background:white;cursor:pointer}button[aria-pressed=true]{background:#d3eaf5;color:#1c485b;font-weight:750}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}.card,.evidence{background:#fffdfa;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.card h3{padding:11px 13px 0;font-size:17px}.card p{padding:2px 13px 10px;font-size:13px}
.card svg{display:block;width:100%;height:auto;background:#f5f1e9;border-top:1px solid #e0ddd4}
.card svg text{font-family:'Microsoft YaHei','PingFang SC',sans-serif}.map-label{paint-order:stroke;stroke:#fcfaf7;stroke-width:.22em;stroke-linejoin:round;fill:#2b3a43}
.legend{margin:9px 0 12px;display:flex;gap:7px 16px;flex-wrap:wrap;color:#4e5960;font-size:13px}.legend span{display:flex;align-items:center;gap:6px}
.i{display:inline-block;width:18px;height:9px}.route{border-top:3px solid #236583}.hyp{border-top:3px dashed #b95f23}.park{background:#edf0dc;border:1px dashed #86956c}.plaza{background:#d3eaf5;border:1px solid #639cb0}.exit{width:9px;background:#955272;border:1px solid #602e46}.grass{background:#d3dfc4;border:1px solid #aab99e}
.evidence{margin-top:15px;padding:13px 15px}.evidence h2{font-size:19px;margin-bottom:4px}
dl{display:grid;grid-template-columns:minmax(94px,max-content) 1fr;gap:6px 12px;margin:10px 0 1px}dt{font-weight:700;color:var(--ink)}dd{margin:0;color:var(--muted);overflow-wrap:anywhere}
footer{padding:17px 0 26px;color:var(--muted);font-size:12px}.sources{display:flex;gap:7px 13px;flex-wrap:wrap;margin-top:6px}
[hidden]{display:none!important}@media(max-width:700px){.pair{grid-template-columns:1fr}.controls{margin-top:12px}}
"""

JS = """
const views = [...document.querySelectorAll('[data-view]')];
const controls = [...document.querySelectorAll('[data-set-view]')];
for (const button of controls) {
  button.addEventListener('click', () => {
    for (const view of views) view.hidden = view.dataset.view !== button.dataset.setView;
    for (const item of controls) item.setAttribute('aria-pressed', String(item === button));
  });
}
"""


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe(text):
    return html.escape(str(text), quote=True)


def path_data(points, closed=False):
    return "M" + "L".join(f"{x:.4f},{y:.4f}" for x, y in points) + ("Z" if closed else "")


def map_label(x, y, value, size, *, anchor="start", color=None):
    fill = f' style="fill:{color}"' if color else ""
    return (f'<text class="map-label" x="{x:.4f}" y="{y:.4f}" font-size="{size:.4f}" '
            f'text-anchor="{anchor}" font-weight="650"{fill}>{safe(value)}</text>')


def draw_map(features, park_path, route, approach, door, extent, use_gap, full, gap):
    x, y, w, h = extent
    label_size = w * .025
    marker = w * .008
    # The source polygons may extend beyond either view. SVG clips them without changing geometry.
    layers = []
    if park_path:
        layers.append(f'<path d="{park_path}" {LAYERS["park"][0]} fill-rule="evenodd" vector-effect="non-scaling-stroke"><title>人民广场范围 · leisure=park</title></path>')
    for layer, (style,) in LAYERS.items():
        if layer == "park":
            continue
        for feature in features:
            if feature["layer"] != layer:
                continue
            title = safe(feature["props"].get("native_id", layer))
            layers.extend(
                f'<path d="{safe(part["d"])}" {style} fill-rule="evenodd" vector-effect="non-scaling-stroke"><title>{title}</title></path>'
                for part in feature["shape"] if "d" in part)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.4f} {y:.4f} {w:.4f} {h:.4f}" aria-label="{"全程" if full else "近景"}{"，加假设连接" if use_gap else "，原路网"}">',
        *layers,
    ]
    if full:
        for feature in features:
            if feature["layer"] in {"road_label", "building_label"}:
                label = feature["props"].get("label", "")
                for part in feature["shape"]:
                    if "point" in part:
                        a, b = part["point"]
                        svg.append(map_label(a, b, label, label_size * .61))
    d = path_data(route)
    svg.append(f'<path d="{d}" fill="none" stroke="#fffefa" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>')
    svg.append(f'<path d="{d}" fill="none" stroke="#236583" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"><title>冻结原生路网路线</title></path>')
    if use_gap:
        d = path_data([approach, door])
        svg.append(f'<path d="{d}" fill="none" stroke="#fffefa" stroke-width="7" stroke-linecap="round" vector-effect="non-scaling-stroke"/>')
        svg.append(f'<path class="candidate" d="{d}" fill="none" stroke="#b95f23" stroke-width="4" stroke-dasharray="7 4" stroke-linecap="round" vector-effect="non-scaling-stroke"><title>{gap:.2f} 米门前假设连接</title></path>')
    ax, ay = approach
    dx, dy = door
    svg.append(f'<circle cx="{ax:.4f}" cy="{ay:.4f}" r="{marker:.4f}" fill="#236583" stroke="#fffefa" stroke-width="2" vector-effect="non-scaling-stroke"><title>原路网末点</title></circle>')
    svg.append(f'<rect x="{dx-marker:.4f}" y="{dy-marker:.4f}" width="{marker*2:.4f}" height="{marker*2:.4f}" fill="#955272" stroke="#fffefa" stroke-width="2" vector-effect="non-scaling-stroke"><title>西北出口原坐标 · entrance=exit</title></rect>')
    if full:
        sx, sy = route[0]
        svg.append(f'<circle cx="{sx:.4f}" cy="{sy:.4f}" r="{marker:.4f}" fill="#fffefa" stroke="#236583" stroke-width="2" vector-effect="non-scaling-stroke"/>')
        svg.append(map_label(sx + marker*2, sy - marker, "冻结起点", label_size*.81))
        svg.append(map_label(dx + marker*2, dy - marker*1.3, "西北出口", label_size*.83))
    else:
        svg.append(map_label(ax - marker*1.7, ay - marker*1.55, "原路网末点", label_size, anchor="end"))
        svg.append(map_label(dx + marker*1.9, dy + marker*1.4, "西北出口 · exit", label_size))
        if use_gap:
            svg.append(map_label((ax+dx)/2+marker*2.0, (ay+dy)/2-marker*.9, f"{gap:.2f} 米 · 假设", label_size*.94, color="#9a4d1a"))
        svg.append(map_label(x+w*.08, y+h*.14, "北侧已标步行面", label_size*.86))
        svg.append(map_label(x+w*.57, y+h*.78, "上海博物馆", label_size*.93))
    scale = 100 if full else 5
    bx, by = x+w*.055, y+h*.91
    svg.append(f'<path d="M{bx:.4f},{by:.4f}h{scale:g}" fill="none" stroke="#2b3a43" stroke-width="2.2" vector-effect="non-scaling-stroke"/>')
    svg.append(map_label(bx, by-h*.021, f"{scale} 米", label_size*.72))
    svg.append(map_label(x+w*.94, y+h*.10, "↑ 北", label_size*.81, anchor="end"))
    return "".join(svg) + "</svg>"


def build(old, output):
    result = read(output / "trial.json")
    role = {f["properties"]["role"]: f["geometry"]["coordinates"] for f in read(output / "trial.geojson")["features"]}
    route, candidate = role["native_approach"], role["candidate"]
    door = role["exit"]
    approach = role["approach_point"]
    if [route[-1], candidate[0], candidate[-1]] != [approach, approach, door]:
        raise ValueError("Route or candidate endpoints disagree with the trial")
    scene = next(s for s in read(old / "frozen_r4/runs/source_scene_contracts.json")["scenes"] if s["scene_id"] == MUSEUM)
    source_js = (old / "visuals/scene_data.js").read_text(encoding="utf-8")
    basemap = json.JSONDecoder().raw_decode(source_js[source_js.index("{"):])[0]
    model = next(s for s in basemap["scenes"] if s["id"] == MUSEUM)
    building = transform(PROJECT, shape(scene["building_footprint"]))
    ox, oy = building.centroid.x, building.centroid.y

    def position(coordinate):
        x, y = PROJECT(*coordinate)
        return x - ox, oy - y

    park_id = result.get("site_area_id") or "way/404709025"
    clip = read(old / "frozen_r4" / scene["osm_clip"])["elements"]
    park = next(r for r in clip if f"{r['type']}/{r['id']}" == park_id)
    nodes = {r["id"]: (r["lon"], r["lat"]) for r in clip if r["type"] == "node"}
    park_path = path_data((position(nodes[i]) for i in park["nodes"]), closed=True)
    route = [position(p) for p in route]
    approach, door = position(approach), position(door)
    gap = result["gap_m"]
    center = ((approach[0]+door[0])/2, (approach[1]+door[1])/2)
    close_extent = (center[0]-24, center[1]-18, 48, 36)
    route_x, route_y = zip(*route, door)
    width = max(max(route_x)-min(route_x)+65, (max(route_y)-min(route_y)+60)*1.34)
    height = width/1.34
    full_extent = ((min(route_x)+max(route_x)-width)/2, (min(route_y)+max(route_y)-height)/2, width, height)

    def panel(extent, full):
        left, right = (draw_map(model["features"], park_path, route, approach, door, extent, choice, full, gap)
                       for choice in (False, True))
        return f"""<div class="pair" data-view="{'full' if full else 'close'}"{' hidden' if full else ''}>
<section class="card"><h3>A · 不加入门前连接</h3><p>沿原路网 {result['baseline_approach_m']:,.2f} 米，到末点后仍距出口 {gap:.2f} 米。</p>{left}</section>
<section class="card"><h3>B · 加入一条假设连接</h3><p>原路线加 {gap:.2f} 米，模型路线 {result['hypothetical_total_m']:,.2f} 米。</p>{right}</section></div>"""

    # Keep identifiers beside the prose so the area semantics are traceable from the frozen OSM clip.
    content = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>上海博物馆西北出口 · {gap:.2f} 米门前接入小试</title><style>{CSS}</style></head>
<body><header><small>R4-REV1 追加小试 · 上海博物馆人民广场馆</small>
<h1>西北出口前的 {gap:.2f} 米</h1><p>两侧共用冻结底图与原路线。右侧橙线是新增的门前假设连接。</p></header>
<main><div class="controls"><h2>同视野地图对照</h2><div role="group" aria-label="地图范围">
<button type="button" data-set-view="close" aria-pressed="true">门前近景</button>
<button type="button" data-set-view="full" aria-pressed="false">从起点看全程</button></div></div>
<div class="legend" aria-label="图例"><span><i class="i route"></i>原路网路线</span>
<span><i class="i hyp"></i>门前假设连接</span><span><i class="i exit"></i>原登记出口</span>
<span><i class="i plaza"></i>已标步行面</span><span><i class="i park"></i>人民广场范围（leisure=park）</span>
<span><i class="i grass"></i>源数据草地</span></div>
{panel(close_extent, False)}{panel(full_extent, True)}
<section class="evidence"><h2>整段证据</h2><dl>
<dt>人民广场范围</dt><dd>候选段有 {result.get('site_cover_m', 0):.2f} 米落在人民广场 <code>{safe(park_id)}</code>（<code>leisure=park</code>）中。该标签描述广场场地范围。</dd>
<dt>步行标注</dt><dd>已标步行面 <code>relation/2153738</code> 只在步道端相接。整段受已标步行面或步行线覆盖的长度约 {result['walkable_covered_m']:.2f} 米。</dd>
<dt>层级</dt><dd>冻结源数据未见明确层级冲突。同层、台阶及高差仍待核验。</dd>
<dt>障碍</dt><dd>冻结源数据中，候选段未穿入建筑、草地、水体，也未与已标围栏相交。只在原出口点触及馆舍边界。</dd>
<dt>原登记出口</dt><dd><code>{safe(result['entrance_id'])}</code> · <code>entrance=exit</code> · WGS84 [经度，纬度] <code>{safe(result['entrance_coordinate'])}</code>。入馆资格仍为不适用。</dd>
</dl></section>
</main><footer><div>© OpenStreetMap contributors · 冻结源数据 · 米制投影 EPSG:32651</div>
<div class="sources"><a href="trial.json">逐段证据 JSON</a><a href="trial.geojson">原路线与候选 GeoJSON</a></div></footer><script>{JS}</script></body></html>"""
    (output / "index.html").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--old-root", type=Path, default=OLD)
    cli.add_argument("--output-root", type=Path, default=ROOT / "public")
    args = cli.parse_args()
    build(args.old_root.resolve(), args.output_root.resolve())
