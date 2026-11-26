"""Build an offline, north-up MapLibre viewer over permitted local images and routes."""

import argparse
from base64 import b64encode
import json
from math import isfinite
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_TYPES = {".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg"}
ATTRIBUTION = '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'
GEOAPIFY_ATTRIBUTION = '路线服务 <a href="https://www.geoapify.com/">Geoapify</a>'

HTML = """<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>路线叠加与尺度核验</title>
<link rel="stylesheet" href="{css}">
<style>
:root{{color-scheme:light;font:15px/1.5 system-ui,sans-serif;color:#17312d;background:#edf2ee}}
body{{margin:0}}main{{max-width:1280px;margin:24px auto;padding:0 16px}}
h1{{font-size:1.55rem;margin:0 0 .3rem}}p{{margin:.3rem 0 .7rem}}
.panel{{background:white;border:1px solid #d4dfd8;border-radius:9px;padding:14px}}
.controls{{display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;margin:.6rem 0}}
select,input,button{{font:inherit}}select,button{{padding:.25rem .5rem}}
.status{{padding:8px;background:#ecf5ee;border-radius:5px}}
.scroll{{overflow:auto;border:1px solid #c9d5ca;min-height:220px;margin-top:8px;background:#e9ece5}}
#map{{position:relative}}.label{{font-weight:650}}.local{{color:#1d62a3}}.geoapify{{color:#a24420}}
.meta{{font:12px/1.5 system-ui,sans-serif;margin-top:7px}}
</style>
<body><main>
<p class="label">OSM × Geoapify · 技术核验</p>
<h1>同一底图上的路线叠加</h1>
<p>地图展示已有 WGS84 路线，不重新计算。此页公开来源名称，人工盲评请使用匿名图册。</p>
<section class="panel" aria-label="路线视野">
<div class="controls">
<label>场景 <select id="scene"></select></label>
<label>视野 <select id="view"><option value="detail">近景</option><option value="context">上下文</option></select></label>
<label class="local"><input id="local" type="checkbox" checked> 本地步行路线</label>
<label class="geoapify"><input id="geoapify" type="checkbox" checked> Geoapify 步行路线</label>
<label><input id="diagnostic" type="checkbox" checked> 仅到路网候选的诊断路线</label>
</div>
<div id="status" class="status" role="status" aria-live="polite">初始化本地 MapLibre</div>
<div class="scroll"><div id="map" aria-label="北向地图与路线"></div></div>
<div class="meta" id="meta"></div>
<p class="meta">端点诊断：蓝色圆点是设定起点，红色圆点是入口参考，橙色圆点是最近路网候选。路网候选与入口参考分开记录。橙红实线绘制服务返回的路线，其终点与入口参考分开核对。<br>地图背景来自本轮本地 OSM 渲染。{attribution} · MapLibre GL JS 5.12.0</p>
</section></main>
<script id="cases" type="application/json">{cases}</script>
<script src="{js}"></script>
<script>
"use strict";
const cases=JSON.parse(document.getElementById("cases").textContent);
const byId=id=>document.getElementById(id);
const makeOption=(value,text)=>new Option(text,value);
const providers=["local","geoapify","diagnostic"];
const state={{map:null,generation:0,summary:null}};
const routeColors={{local:"#2464a3",geoapify:"#b3512e",diagnostic:"#376e66"}};
function setStatus(text){{byId("status").textContent=text;}}
function render(){{
  const generation=++state.generation;
  if(state.map){{state.map.remove();state.map=null;}}
  state.summary=null;
  if(!window.maplibregl){{setStatus("MapLibre 本地资源不可用。");return;}}
  const item=cases[Number(byId("scene").value)];
  const key=byId("view").value,v=item?.viewports[key];
  if(!v){{setStatus("当前视野没有实际地图记录。");return;}}
  const [w,s,e,n]=v.bounds, root=byId("map");
  root.style.width=v.width+"px";
  root.style.height=v.height+"px";
  const sources={{}},layers=[{{id:"background",type:"background",paint:{{"background-color":"#e9ece5"}}}}];
  if(v.image){{
    sources.basemap={{type:"image",url:v.image,coordinates:[[w,n],[e,n],[e,s],[w,s]]}};
    layers.push({{id:"basemap",type:"raster",source:"basemap",paint:{{"raster-fade-duration":0}}}});
  }}
  for(const provider of providers){{
    const geometry=item.routes[provider];
    byId(provider).disabled=!geometry;
    if(!geometry)continue;
    sources[provider]={{type:"geojson",data:{{type:"Feature",geometry,properties:{{}}}}}};
    layers.push({{id:provider,type:"line",source:provider,
      layout:{{"line-cap":"round","line-join":"round",visibility:byId(provider).checked?"visible":"none"}},
      paint:{{"line-color":routeColors[provider],"line-width":4,"line-opacity":.92, ...(provider==="diagnostic"?{{"line-dasharray":[2,1.2]}}:{{}})}}}});
  }}
  if(item.diagnostics.length){{
    sources.diagnostics={{type:"geojson",data:{{type:"FeatureCollection",features:item.diagnostics}}}};
    layers.push({{id:"diagnostics",type:"circle",source:"diagnostics",paint:{{
      "circle-radius":6,"circle-stroke-color":"#fff","circle-stroke-width":2,
      "circle-color":["match",["get","role"],"start","#2474b7","target","#ad3c32","#d48a2f"]
    }}}});
  }}
  byId("meta").textContent="画布 "+v.width+"×"+v.height+" CSS px · 地图朝北 · WGS84 边界 "+v.bounds.join(", ");
  setStatus("载入本地地图与路线。");
  try {{
    const map=state.map=new maplibregl.Map({{
      container:root,style:{{version:8,sources,layers}},bearing:0,pitch:0,
      bounds:[[w,s],[e,n]],fitBoundsOptions:{{padding:0,duration:0}},
      interactive:false,attributionControl:false,renderWorldCopies:false,
      maxZoom:24,fadeDuration:0
    }});
    map.addControl(new maplibregl.ScaleControl({{maxWidth:150,unit:"metric"}}),"bottom-left");
    let layerError=false;
    map.once("idle",()=>{{
      if(state.generation!==generation)return;
      const observed=map.getBounds();
      const route_counts=Object.fromEntries(providers.map(p=>[p,item.routes[p]?.coordinates.length??0]));
      const cornerPixels=[[w,n],[e,s]].map(point=>map.project(point));
      const boundsError=Math.max(Math.hypot(cornerPixels[0].x,cornerPixels[0].y),
        Math.hypot(cornerPixels[1].x-v.width,cornerPixels[1].y-v.height));
      const displayed=Object.keys(sources).filter(id=>!providers.includes(id)||byId(id).checked);
      const loaded=!layerError && displayed.every(id=>map.isSourceLoaded(id));
      state.summary={{scene_id:item.scene_id,view:key,route_counts,
        bounds:[observed.getWest(),observed.getSouth(),observed.getEast(),observed.getNorth()],
        loaded,image_present:!!v.image,bearing:map.getBearing(),pitch:map.getPitch(),
        bounds_match:boundsError<=1,max_corner_error_css_px:boundsError,diagnostic_points:item.diagnostics.length,
        visible_layers:Object.fromEntries(providers.map(p=>[p,map.getLayer(p)?.id===p]))}};
      const local=route_counts.local>0?"本地路线可见":"本地完整路线未取得";
      const remote=route_counts.geoapify>0?"Geoapify 路线可见":"Geoapify 无可展示路线";
      if(!loaded){{setStatus("MapLibre 图层加载异常。请检查本地文件和浏览器 WebGL 支持。");return;}}
      if(boundsError>1){{setStatus("VIEWPORT_MISMATCH · 画布边界与冻结范围不匹配");return;}}
      const diagnostic=route_counts.diagnostic>0?" · 诊断路线只到路网候选":"";
      setStatus((v.image?"本地底图已加载":"无可展示底图")+" · "+local+" · "+remote+diagnostic);
    }});
    map.on("error",()=>{{
      layerError=true;
      if(state.generation===generation)setStatus("MapLibre 图层加载异常。请检查本地文件和浏览器 WebGL 支持。");
    }});
  }}catch(_err){{setStatus("无法初始化 MapLibre。请检查浏览器 WebGL 支持。");}}
}}
byId("scene").replaceChildren(...cases.map((item,i)=>makeOption(i,item.label||item.scene_id)));
byId("scene").onchange=render;
byId("view").onchange=render;
for(const p of providers)byId(p).onchange=()=>{{
  if(state.map?.getLayer(p))state.map.setLayoutProperty(p,"visibility",byId(p).checked?"visible":"none");
}};
window.PilotRouteViewer=Object.freeze({{summary:()=>state.summary}});
render();
</script></body></html>
"""


def _coordinate(value, max_lat=90):
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(type(x) in (int, float) and isfinite(x) for x in value)
            and abs(value[0]) <= 180 and abs(value[1]) <= max_lat)


def _bounds(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 4
            or not _coordinate(value[:2], 85.05112878) or not _coordinate(value[2:], 85.05112878)
            or value[0] >= value[2] or value[1] >= value[3]):
        raise ValueError("view bounds must be [west,south,east,north] within Web Mercator")
    return list(value)


def _geometry(value):
    if not isinstance(value, dict):
        return None
    geometry = value if value.get("type") == "LineString" else value.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2 or not all(_coordinate(x) for x in coordinates):
        raise ValueError("route must be a WGS84 LineString")
    return {"type": "LineString", "coordinates": coordinates}


def _diagnostics(route):
    if not isinstance(route, dict):
        return []
    snap = route.get("snap_end") or {}
    points = {"start": route.get("requested_start"), "target": route.get("requested_target"),
              "network_candidate": snap.get("position")}
    return [{"type": "Feature", "properties": {"role": role},
             "geometry": {"type": "Point", "coordinates": coords}}
            for role, coords in points.items() if _coordinate(coords)]


def _embed_image(path, output, project_root):
    if not path:
        return None
    rel = Path(path)
    if rel.is_absolute() or ":" in str(path) or "?" in str(path) or "#" in str(path):
        raise ValueError("view image must be a relative path without a query or fragment")
    source = (output.parent / rel).resolve()
    if not source.is_relative_to(project_root) or source.suffix.lower() not in IMAGE_TYPES:
        raise ValueError("view image must be inside the pilot and use PNG or JPEG")
    if source.stat().st_size > 8_000_000:
        raise ValueError("view image too large")
    media = IMAGE_TYPES[source.suffix.lower()]
    return f"data:{media};base64," + b64encode(source.read_bytes()).decode("ascii")


def write_viewer(cases, output, project_root=ROOT):
    output, project_root = Path(output).resolve(), Path(project_root).resolve()
    normalized = []
    for case in cases:
        views = {}
        for name, view in case["viewports"].items():
            if name not in {"detail", "context"}:
                raise ValueError("expected detail or context")
            width, height = view.get("width", 1200), view.get("height", 900)
            if any(type(x) is not int or not 100 <= x <= 2400 for x in (width, height)):
                raise ValueError("unexpected view dimensions")
            views[name] = {"bounds": _bounds(view["bounds"]), "width": width, "height": height,
                           "image": _embed_image(view.get("image"), output, project_root)}
        normalized.append({"scene_id": str(case["scene_id"]), "label": str(case.get("label", "")),
                           "viewports": views, "routes": {p: _geometry(case.get("routes", {}).get(p))
                                                          for p in ("local", "geoapify", "diagnostic")},
                           "diagnostics": _diagnostics(case.get("routes", {}).get("local"))})
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    vendor = project_root / "visuals" / "route_comparisons" / "vendor"
    assets = {kind: Path(os.path.relpath(vendor / f"maplibre-gl.{kind}", output.parent)).as_posix()
              for kind in ("css", "js")}
    attribution = ATTRIBUTION
    if any(case["routes"]["geoapify"] for case in normalized):
        attribution += " · " + GEOAPIFY_ATTRIBUTION
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(HTML.format(**assets, cases=payload, attribution=attribution), encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_viewer(json.loads(args.input.read_text(encoding="utf-8-sig")), args.output)
    print(result)

