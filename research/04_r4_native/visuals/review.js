"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const STAGES = ["B0", "B1", "B2", "B3"];
const STAGE_NAMES = {B0:"原始网络", B1:"有证据的边缘连接", B2:"边缘与原生内部步行线", B3:"已登记入口联合可达"};
const ROUTE_COLORS = {B0:"#245998", B1:"#146762", B2:"#6346a7", B3:"#332e53", HOSTED:"#b55225", B0_DIAGNOSTIC:"#5484b5"};
const LAYERS = {
  building:["建筑","#dfd9cf"], target_building:["目标建筑","#be9d78"], plaza:["开放空间面","#7fbdc3"],
  grass:["草地／花坛","#a6c693"], water:["水体","#83b9d8"], fence:["围栏／墙","#724c3f"],
  obstacle:["算法障碍证据","#b57459"],
  walk:["有步行标签的线","#558370"], crossing:["过街标签","#9c6a1d"], network:["B0 实验路网","#6b7884"],
  candidate:["待审边界","#aa8a59"], baseline_evidence:["已有 B0 的原生线","#4d777b"], rejected:["被拒绝的原生线","#a36438"],
  added:["已接纳新增边","#bd2467"], added_node:["已接纳边端点","#bd2467"], contact:["接点候选","#cb852b"],
  route:["当前实验折线","#275493"], hosted:["留存托管折线","#b55225"],
  diagnostic:["历史接近诊断","#5484b5"], frozen:["B0 冻结请求回放","#6f7f9a"],
  entry:["已登记入口","#913754"], proxy:["冻结代理点","#73727d"],
  origin:["起点","#07584a"], end:["折线末点","#42296b"]
};
const DRAW_ORDER = Object.keys(LAYERS);
const CLICKABLE = new Set(["candidate","added","added_node","baseline_evidence","rejected","contact","entry","proxy","origin","end","route","hosted","diagnostic","frozen"]);
const DEFAULT_LAYERS = new Set(DRAW_ORDER);
const state = {scene:"sh-huangpu-01", variant:"B0", view:"detail", layers:new Set(DEFAULT_LAYERS)};
const byId = new Map(R4_DATA.scenes.map(scene => [scene.id, scene]));
const $ = selector => document.querySelector(selector);

function node(name, text, attrs = {}) {
  const element = document.createElement(name);
  if (text != null) element.textContent = text;
  for (const [key,value] of Object.entries(attrs)) element.setAttribute(key, value);
  return element;
}

function svgNode(name, attrs = {}, text) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key,value] of Object.entries(attrs)) if (value !== undefined && value !== null) element.setAttribute(key, value);
  if (text != null) element.textContent = text;
  return element;
}

function plain(value) {
  if (value === undefined || value === null || value === "") return "—";
  if (Array.isArray(value)) return value.map(plain).join(" / ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function numeric(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function meter(value) {
  return numeric(value) ? value.toFixed(2) + " m" : "—";
}

function metric(record, ...keys) {
  for (const key of keys) {
    for (const obj of [record, record?.metrics, record?.graph, record?.connectivity]) {
      if (obj && obj[key] !== undefined && obj[key] !== null) return obj[key];
    }
  }
  return undefined;
}

function routesOf(record) {
  for (const field of ["routes", "entrance_routes", "route_results", "entry_routes", "entrance_access"]) {
    if (Array.isArray(record?.[field])) return record[field];
    if (record?.[field] && typeof record[field] === "object") return Object.values(record[field]);
  }
  if (record?.route) return [record.route];
  return [];
}

function stageOf(p) {
  const s = String(p.variant || "");
  return /^B[0-3](?:$|_)/.test(s) && !["B0_DIAGNOSTIC","B0_FROZEN"].includes(s) ? s.slice(0,2) : s;
}

function layerOf(feature) {
  if (feature.layer === "route") {
    if (stageOf(feature.properties) === "HOSTED") return "hosted";
    if (stageOf(feature.properties) === "B0_DIAGNOSTIC") return "diagnostic";
    if (stageOf(feature.properties) === "B0_FROZEN") return "frozen";
  }
  return feature.layer;
}

function visible(feature, variant, layers, preset) {
  const layer = layerOf(feature);
  if (!layers.has(layer)) return false;
  const stage = stageOf(feature.properties);
  if (layer === "route" || (layer === "end" && STAGES.includes(stage))) return preset === "routes" || !stage || stage === variant;
  if (["added","added_node"].includes(layer) && STAGES.includes(stage)) return preset !== "failure" && variant >= stage;
  if (["candidate","baseline_evidence","rejected"].includes(layer) && STAGES.includes(stage)) return variant === "B0" || stage <= variant;
  return true;
}

function displayId(properties) {
  return plain(properties.edge_id || properties.native_ids || properties.native_id || properties.target_native_id);
}

function statusLabel(record) {
  return plain(record?.status || record?.reason || record?.state);
}

function featureStyle(layer, item, variant) {
  const p = item.properties;
  const color = LAYERS[layer][1];
  const denied = p.eligible === false || /EXCLUDED|UNSUITABLE|INELIGIBLE/.test(String(p.status));
  const routeColor = ROUTE_COLORS[stageOf(p)] || ROUTE_COLORS[variant];
  const base = {fill:"none", stroke:color, "stroke-linecap":"round", "stroke-linejoin":"round"};
  const style = {
    building:{fill:color, stroke:"#c2b9aa", "stroke-width":.45},
    target_building:{fill:"#cfb897", stroke:"#a66e3b", "stroke-width":1.6},
    plaza:{fill:"#cbe8e8", stroke:"#45929e", "stroke-width":1.6, "fill-opacity":.77, "stroke-dasharray":"6 2"},
    grass:{fill:"#dceacd", stroke:"#a8c296", "stroke-width":.55},
    water:{fill:"#c3dfeb", stroke:"#98c7dc", "stroke-width":.6},
    fence:{"stroke-width":1.3, "stroke-dasharray":"3 2"},
    obstacle:{fill:p.evidence?.includes("BUILDING") ? "none" : "#f0c2aa","fill-opacity":.22,"stroke-width":.8,"stroke-dasharray":"4 2"},
    walk:{"stroke-width":1.15, "stroke-opacity":.83},
    crossing:{fill:color, "stroke-width":1.15},
    network:{stroke:["#707b8a","#527f8f","#886f83","#65866d"][Number(p.component_id || 1)%4],"stroke-width":1.3,"stroke-opacity":.9},
    candidate:{"stroke-width":2.2, "stroke-dasharray":"5 5", "stroke-opacity":.9},
    baseline_evidence:{"stroke-width":2.5,"stroke-dasharray":"6 2","stroke-opacity":.85},
    rejected:{stroke:p.reason === "NON_GROUND_OR_UNRESOLVED_LAYER" ? "#a52350" : color,"stroke-width":p.reason === "NON_GROUND_OR_UNRESOLVED_LAYER" ? 3.8 : 2,"stroke-dasharray":"2 4","stroke-opacity":.9},
    added_node:{fill:"#fbe7ef","stroke-width":1.8},
    added:{stroke:stageOf(p) === "B2" ? "#8f43b1" : color, "stroke-width":4, "stroke-dasharray":"8 3"},
    contact:{fill:"#fff4d7", "stroke-width":1.9},
    route:{stroke:routeColor, "stroke-width":4.4, "stroke-opacity":.95},
    hosted:{stroke:color, "stroke-width":3, "stroke-dasharray":"1 5", "stroke-opacity":.9},
    diagnostic:{stroke:color, "stroke-width":3, "stroke-dasharray":"7 5", "stroke-opacity":.8},
    frozen:{stroke:color,"stroke-width":2.6,"stroke-dasharray":"6 5","stroke-opacity":.82},
    entry:{fill:denied ? "#f5f2ee" : "#f9d2e2", stroke:denied ? "#66666a" : color, "stroke-width":2.25},
    proxy:{fill:"#f0eff3", "stroke-width":1.8, "stroke-dasharray":"3 2"},
    origin:{fill:"#d1edc9", "stroke-width":2},
    end:{fill:"#e5dcfb", stroke:routeColor, "stroke-width":1.9}
  }[layer];
  return {...base, ...style};
}

function renderFeature(group, feature, layer, variant, interactive) {
  const p = feature.properties;
  const style = featureStyle(layer, feature, variant);
  const mark = svgNode("g", {"data-feature":"", "data-status":p.status, "data-native-ids":displayId(p)});
  const label = LAYERS[layer][0] + " · " + displayId(p) + " · " + statusLabel(p);
  mark.append(svgNode("title", {}, label));
  for (const g of feature.geometry) {
    if (g.d) {
      mark.append(svgNode("path", {...style, d:g.d, "fill-rule":g.area ? "evenodd" : undefined}));
      if (interactive && CLICKABLE.has(layer) && !g.area) {
        mark.append(svgNode("path", {d:g.d, fill:"none", stroke:"transparent", "stroke-width":12}));
      }
    } else {
      const [x,y] = g.point;
      const radius = ["entry","origin","proxy"].includes(layer) ? 5.5 : layer === "crossing" ? 2.5 : 4.2;
      if (layer === "entry" || layer === "end") {
        mark.append(svgNode("path", {...style, d:"M"+x+","+(y-radius)+"L"+(x+radius)+","+y+"L"+x+","+(y+radius)+"L"+(x-radius)+","+y+"Z"}));
      } else if (layer === "proxy") {
        mark.append(svgNode("rect", {...style, x:x-radius,y:y-radius,width:radius*2,height:radius*2}));
      } else {
        mark.append(svgNode("circle", {...style,cx:x,cy:y,r:radius}));
      }
    }
  }
  if (interactive && (CLICKABLE.has(layer) || layer === "network")) {
    if (CLICKABLE.has(layer)) mark.setAttribute("tabindex", "0");
    mark.setAttribute("role", "button");
    mark.setAttribute("aria-label", label);
    mark.addEventListener("click", () => inspect(feature));
    mark.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        inspect(feature);
      }
    });
  }
  group.append(mark);
}

function mapTitle(scene, variant, view) {
  return scene.label + " · " + variant + " " + STAGE_NAMES[variant] + " · " + (view === "detail" ? "开放空间细节" : "完整路线范围");
}

function svgText(x,y,text,attrs = {}) {
  return svgNode("text", {x,y,fill:"#17383b","font-family":"Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif", ...attrs}, text);
}

function renderMap(scene, variant, view, layers, interactive = false, preset = "default") {
  const w = R4_DATA.width;
  const h = R4_DATA.height;
  const map = scene.maps[view];
  const label = mapTitle(scene, variant, view) + (preset === "conflict" ? " · 跨层拒绝" : "");
  const footerHeight = 70;
  const out = svgNode("svg", {xmlns:SVG_NS, width:w, height:h + footerHeight, viewBox:"0 0 "+w+" "+(h+footerHeight), role:"img",
    "aria-label":label, "data-scene":scene.id, "data-variant":variant, "data-view":view});
  out.append(svgNode("title", {}, label));
  out.append(svgNode("desc", {}, "CRS "+R4_DATA.crs+" · "+scene.machine_geometry+" · © OpenStreetMap contributors · Geoapify historical routing"));
  out.append(svgNode("metadata", {}, JSON.stringify({scene_id:scene.id,variant,view,layers:[...layers],
    source_clip:scene.source_clip,machine_geometry:scene.machine_geometry,machine_geometry_sha256:scene.machine_geometry_sha256})));
  out.append(svgNode("rect", {width:w,height:h+footerHeight,fill:"#f3f5ef"}));
  const mapItems = new Map(DRAW_ORDER.map(layer => [layer, []]));
  for (const feature of map.features) {
    if (preset === "conflict" && feature.layer === "rejected" && feature.properties.reason !== "NON_GROUND_OR_UNRESOLVED_LAYER") continue;
    if (visible(feature, variant, layers, preset)) mapItems.get(layerOf(feature)).push(feature);
  }
  for (const [layer, items] of mapItems) {
    if (!items.length) continue;
    const group = svgNode("g", {"data-layer":layer});
    for (const item of items) renderFeature(group,item,layer,variant,interactive);
    out.append(group);
  }
  if (!interactive && preset !== "routes") {
    for (const feature of mapItems.get("entry")) {
      const p = feature.properties;
      const [[x,y]] = feature.geometry.filter(g => g.point).map(g => g.point);
      const start = x < w - 170;
      out.append(svgText(x + (start ? 9 : -9), y - 10, displayId(p)+" · "+(p.status === "EXCLUDED" ? "排除" : "适用"),
        {"font-size":11,"text-anchor":start ? "start" : "end","font-weight":700,stroke:"#fcfbf5","stroke-width":3,"paint-order":"stroke"}));
    }
  }
  const gap = map.scale_bar_m / map.meters_per_pixel;
  const boxWidth = Math.max(102,gap+20);
  out.append(svgNode("rect", {x:8,y:h-42,width:boxWidth,height:34,rx:3,fill:"#fbfbf3",opacity:.92}));
  out.append(svgNode("path",{d:"M17,"+(h-14)+"h"+gap,stroke:"#274b4c","stroke-width":3}));
  out.append(svgText(17,h-20,map.scale_bar_m+" m",{"font-size":13}));
  out.append(svgNode("rect", {x:w-45,y:10,width:33,height:32,rx:3,fill:"#fbfbf3",opacity:.92}));
  out.append(svgText(w-39,32,"↑ N",{"font-size":13,"font-weight":700}));
  if (!interactive) {
    out.append(svgNode("rect",{x:8,y:9,width:460,height:31,rx:3,fill:"#fbfbf3",opacity:.92}));
    out.append(svgText(17,30,label,{"font-size":15,"font-weight":700}));
    const footer = preset === "conflict" ? "洋红点线 · 原生线层级非地面或未解析 · 拒绝入图" : [
      "已接纳新增边 " + plain(metric(scene.variants[variant],"added_edges","new_edges","added_edges_count","edge_count_added")),
      "登记入口 " + scene.entrances.filter(e => e.eligible).length,
      "候选与新边需逐条核验"
    ].join(" · ");
    out.append(svgNode("rect",{x:13,y:44,width:350,height:22,rx:3,fill:"#fbfbf3",opacity:.88}));
    out.append(svgText(19,59,footer,{"font-size":11}));
  }
  out.append(svgNode("rect", {x:0,y:h,width:w,height:footerHeight,fill:"#e8f1eb"}));
  const preferred = ["target_building","plaza","grass","fence","network","candidate","rejected","added","contact","entry","proxy","route","diagnostic","frozen","hosted","end"];
  const keys = preferred.filter(k => mapItems.get(k).length);
  for (const [i,key] of keys.entries()) {
    const x = 12 + (i%8)*123;
    const y = h+15+Math.floor(i/8)*18;
    const [name,color] = LAYERS[key];
    out.append(svgNode("rect",{x,y:y-7,width:10,height:7,fill:key === "rejected" && preset === "conflict" ? "#a52350" : color}));
    out.append(svgText(x+14,y,name,{"font-size":10.5}));
  }
  out.append(svgText(11,h+58,R4_DATA.crs+" · © OpenStreetMap contributors · Geoapify 历史折线 · "+scene.id,{"font-size":12}));
  return out;
}

function makeTable(headers, rows) {
  const table = node("table");
  const head = node("thead"), hr = node("tr"), body = node("tbody");
  for (const title of headers) hr.append(node("th",title,{scope:"col"}));
  head.append(hr);
  for (const row of rows) {
    const tr = node("tr");
    for (const cell of row) tr.append(node("td",plain(cell)));
    body.append(tr);
  }
  table.append(head,body);
  return table;
}

function inspect(feature) {
  const p = feature.properties;
  const layer = layerOf(feature);
  const rows = [
    ["图层",LAYERS[layer][0]],["原生 ID",p.native_ids || p.native_id],["边 ID",p.edge_id],
    ["变体",p.variant],["判定",p.status],["证据",p.evidence || p.evidence_status],
    ["理由",p.reason || p.failure_reason],["候选距离",meter(p.distance_m)],
    ["长度",meter(p.length_m)],["分量",p.component_id],["入口等级",p.entrance_grade || p.grade],
    ["入口适用",p.eligible],["几何检查",p.geometry_check || p.geometry_valid],
    ["拓扑检查",p.topology_check || p.topology_valid],["原始标签",p.tags || p.native_tags]
  ].filter(([,value]) => plain(value) !== "—");
  const remaining = Object.entries(p).filter(([k,v]) => plain(v) !== "—" && ![
    "kind","variant","status","evidence","evidence_status","reason","failure_reason","distance_m","length_m",
    "component_id","entrance_grade","grade","eligible","geometry_check","geometry_valid","topology_check","topology_valid",
    "tags","native_tags","edge_id","native_id","native_ids"
  ].includes(k));
  $("#inspector").replaceChildren(node("p","对象证据",{class:"eyebrow"}),node("h3",displayId(p),{id:"inspect-heading"}),makeTable(["字段","留存值"],rows.concat(remaining)));
}

function entryRows(scene) {
  if (!scene.entrances.length) return [["—","—","PROXY_OR_UNCERTAIN / UNKNOWN","否","无适用已登记入口进入主指标"]];
  return scene.entrances.map(e => [e.native_id,e.tags?.entrance,e.entrance_grade,e.eligible,e.reason]);
}

function resultRows(record) {
  const rows = routesOf(record);
  if (!rows.length) return [["—",statusLabel(record),"—","—","—","—",record.reason || record.failure_reason || "无适用路线记录"]];
  return rows.map(r => [
    r.target_native_id || r.entrance_native_id || r.native_id || r.entrance_id,
    statusLabel(r),meter(r.length_m ?? r.route_length_m),plain(r.route_end || r.end || r.route_endpoint),
    meter(r.target_gap_m ?? r.entrance_gap_m ?? r.endpoint_gap_m),meter(r.baseline_nearest_network_gap_m),r.failure_reason || r.reason
  ]);
}

function stageMetricLabels(record) {
  return [
    ["图节点",metric(record,"nodes","node_count","graph_nodes")],
    ["图边",metric(record,"edges","edge_count","graph_edges")],
    ["弱连通分量",metric(record,"weak_components","components","component_count","weakly_connected_components")],
    ["新增边",metric(record,"added_edges_count","edge_count_added","new_edges_count","added_edges","new_edges")],
    ["可达登记入口",metric(record,"valid_entry_route_count","reachable_entrances","reached","reachable_count","reachable_entrance_count")]
  ].filter(([,value]) => numeric(value) || typeof value === "string");
}

function historicalRows(scene) {
  const row = scene.extra.local_b0_frozen_replay || {};
  const data = [["B0 冻结请求回放",statusLabel(row),meter(row.length_m),meter(row.target_gap_m)]];
  const diagnostics = scene.maps.context.features.filter(f => f.layer === "route" && ["HOSTED","B0_DIAGNOSTIC"].includes(stageOf(f.properties)));
  for (const f of diagnostics) data.push([LAYERS[layerOf(f)][0],statusLabel(f.properties),meter(f.properties.length_m),meter(f.properties.distance_m)]);
  return data;
}

function edgeRows(scene,variant) {
  const features = scene.maps.context.features.filter(f => ["added","candidate","contact","baseline_evidence","rejected"].includes(f.layer));
  return features.filter(f => visible(f,variant,DEFAULT_LAYERS,"default")).map(f => {
    const p = f.properties;
    return [LAYERS[f.layer][0],displayId(p),p.variant,p.status,p.evidence || p.evidence_status,meter(p.distance_m ?? p.length_m),p.reason || p.failure_reason];
  });
}

function updateResults(scene, variant) {
  const record = scene.variants[variant];
  $("#variant-status").textContent = statusLabel(record);
  $("#variant-metrics").replaceChildren(...stageMetricLabels(record).map(([title,value]) => node("span",title+" "+plain(value))));
  $("#route-table").replaceChildren(makeTable(["目标原生 ID","状态","长度","实际折线末点 WGS84","末点—入口","B0 最近路网差","失败原因"],resultRows(record)));
  $("#frozen-table").replaceChildren(makeTable(["产物","状态","历史长度","末点—冻结请求点"], historicalRows(scene)));
  $("#entry-table").replaceChildren(makeTable(["原生 ID","原始入口标签","等级","适用","依据"],entryRows(scene)));
  const rows = edgeRows(scene,variant);
  $("#edge-table").replaceChildren(makeTable(["类型","原生或边 ID","变体","状态","证据","距离或长度","理由"],
    rows.length ? rows : [["—","—",variant,"无边界或新增边记录","—","—","查看跨场景输入能力"]]));
}

function render() {
  const scene = byId.get(state.scene);
  const {variant,view,layers} = state;
  $("#scene-heading").textContent = scene.label;
  $("#scene-meta").textContent = "原生建筑 "+scene.native_building_id+" · 关注空间 "+plain(scene.focus_space_ids);
  $("#mode-caption").textContent = variant+" "+STAGE_NAMES[variant]+" · "+scene.maps[view].meters_per_pixel.toFixed(3)+" 米／图内像素";
  $("#map").replaceChildren(renderMap(scene,variant,view,layers,true));
  const shown = new Set([...$("#map svg").querySelectorAll("[data-layer]")].map(e => e.dataset.layer));
  $("#legend").replaceChildren(...DRAW_ORDER.filter(k => shown.has(k)).map(k => {
    const item = node("span");
    const mark = node("i"); mark.style.backgroundColor = LAYERS[k][1];
    item.append(mark,document.createTextNode(LAYERS[k][0]));
    return item;
  }));
  updateResults(scene,variant);
}

function select(scene, variant, view) {
  if (!byId.has(scene) || !STAGES.includes(variant) || !["detail","context"].includes(view)) throw Error("UNKNOWN_REVIEW_SELECTION");
  state.scene = scene; state.variant = variant; state.view = view;
  $("#scene").value = scene;
  $('input[name="variant"][value="'+variant+'"]').checked = true;
  $('input[name="view"][value="'+view+'"]').checked = true;
  $("#inspector").replaceChildren(node("p","对象证据",{class:"eyebrow"}),node("h3","点击边、接点或入口",{id:"inspect-heading"}),
    node("p","可用 Tab 定位，Enter 打开详情。"));
  render();
}

function topologyPreset(preset) {
  const layers = new Set(DEFAULT_LAYERS);
  if (["topology","failure","conflict"].includes(preset)) {
    layers.delete("hosted"); layers.delete("diagnostic"); layers.delete("walk");
    if (preset === "conflict") layers.delete("baseline_evidence");
  }
  if (preset === "routes") {
    layers.delete("candidate"); layers.delete("contact"); layers.delete("crossing");
  }
  return layers;
}

function serial(svg) {
  return new XMLSerializer().serializeToString(svg);
}

function staticSVG(sceneId, variant, view, preset) {
  return serial(renderMap(byId.get(sceneId),variant,view,topologyPreset(preset),false,preset));
}

function matrixRows() {
  return R4_DATA.scenes.map(s => [
    s.label,s.native_building_id,s.focus_space_ids.length,s.entrances.filter(e => e.eligible).length,
    ...STAGES.map(v => statusLabel(s.variants[v]))
  ]);
}

function sheet(title,subtitle,headers,rows,widths) {
  const w = 1200, h = 132 + rows.length * 42;
  const svg = svgNode("svg",{xmlns:SVG_NS,width:w,height:h,viewBox:"0 0 "+w+" "+h,role:"img"});
  svg.append(svgNode("title",{},title),svgNode("desc",{},subtitle),svgNode("rect",{width:w,height:h,fill:"#f6f8f6"}));
  svg.append(svgText(22,33,title,{"font-size":23,"font-weight":700}));
  svg.append(svgText(22,55,subtitle,{"font-size":13}));
  const headY = 69;
  svg.append(svgNode("rect",{x:12,y:headY,width:w-24,height:34,fill:"#e1efe9"}));
  let col = 22;
  for (const [j,head] of headers.entries()) {
    svg.append(svgText(col,headY+22,head,{"font-size":12,"font-weight":700}));
    col += widths[j];
  }
  for (const [i,row] of rows.entries()) {
    const yy = headY+34+i*42;
    if (i%2===1) svg.append(svgNode("rect",{x:12,y:yy,width:w-24,height:42,fill:"#edf3ee"}));
    col = 22;
    for (const [j,v] of row.entries()) {
      const label = plain(v);
      const max = Math.floor(widths[j]/7);
      const words = label.length > max ? [label.slice(0,max),label.slice(max,max*2)] : [label];
      for (const [k,word] of words.entries()) svg.append(svgText(col,yy+17+k*12,word,{"font-size":11}));
      col += widths[j];
    }
  }
  svg.append(svgText(22,h-10,"© OpenStreetMap contributors · R4 机器结果 · 人工与现场核验分开",{"font-size":11}));
  return serial(svg);
}

function matrixSVG() {
  return sheet("跨场景概览","关注空间与适用原生入口仅统计冻结对象。",
    ["建筑","原生建筑 ID","关注空间","适用入口",...STAGES],matrixRows(),[125,100,60,56,190,190,190,235]);
}

function resultsSVG() {
  const rows = [];
  for (const scene of R4_DATA.scenes) {
    for (const v of STAGES) {
      const rec = scene.variants[v];
      const rr = routesOf(rec);
      const ids = rr.map(r => r.target_native_id || r.entrance_native_id || r.native_id || r.entrance_id).filter(Boolean);
      const lengths = rr.map(r => r.length_m ?? r.route_length_m).filter(numeric).map(meter);
      rows.push([scene.label,v,statusLabel(rec),metric(rec,"weak_components","components","component_count","weakly_connected_components"),ids,lengths]);
    }
  }
  return sheet("各变体连通性与实际路线长度","无路线和不适用保留在表中；长度来自机器产物。",
    ["建筑","变体","状态","弱连通分量","登记目标","路线长度"],rows,[145,48,290,95,250,320]);
}

function downloadSVG() {
  const text = serial($("#map svg"));
  const url = URL.createObjectURL(new Blob([text],{type:"image/svg+xml;charset=utf-8"}));
  const link = node("a",null,{href:url,download:state.scene+"_"+state.variant+"_"+state.view+".svg"});
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url),200);
}

for (const s of R4_DATA.scenes) $("#scene").append(node("option",s.label,{value:s.id}));
for (const [k,[label]] of Object.entries(LAYERS)) {
  const control = node("input",null,{type:"checkbox",id:"layer-"+k});
  control.checked = state.layers.has(k);
  control.addEventListener("change", () => {
    if (control.checked) state.layers.add(k); else state.layers.delete(k);
    render();
  });
  const lab = node("label",null,{for:control.id});
  lab.append(control,document.createTextNode(label)); $("#layer-list").append(lab);
}
$("#scene").addEventListener("change", e => select(e.target.value,state.variant,state.view));
$("#variants").addEventListener("change", e => select(state.scene,e.target.value,state.view));
$("#views").addEventListener("change", e => select(state.scene,state.variant,e.target.value));
$("#export").addEventListener("click",downloadSVG);
$("#matrix").replaceChildren(makeTable(["建筑","原生建筑 ID","关注空间","适用入口",...STAGES],matrixRows()));
window.R4_REVIEW = {select,staticSVG,matrixSVG,resultsSVG};
select(state.scene,state.variant,state.view);
