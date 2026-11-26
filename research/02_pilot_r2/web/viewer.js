"use strict";

const data = window.R2_EVIDENCE;
const byId = (name) => document.getElementById(name);
const node = (name, text, cls) => {
  const el = document.createElement(name);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
};
const svg = (name, attrs = {}) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, v));
  return el;
};
const W = 1040;
const H = 660;
const layers = {
  buildings: ["建筑","#cfc8b5"],
  plaza: ["广场面","#8bc1a1"],
  road: ["机动车道参考","#ac9784"],
  walk: ["步行源线","#91a491"],
  route_geoapify: ["A · Geoapify","#b75b32"],
  route_local: ["B · 本地诊断","#265e91"],
  crossing: ["过街证据","#a47722"],
  reference: ["起终点及参考","#993d4f"],
  diagnostic: ["直线诊断","#a9475c"]
};
const defaults = new Set(Object.keys(layers));
const style = `
  .paper{fill:#f5f5eb}
  .grid{stroke:#e2e5d9;stroke-width:1}
  .geom{stroke-linecap:round;stroke-linejoin:round}
  .buildings{fill:#dcd4c1;stroke:#a59e8b;stroke-width:1.15;fill-rule:evenodd}
  .plaza{fill:#bee0c6;fill-opacity:.72;stroke:#629778;stroke-width:1.4;fill-rule:evenodd}
  .road{fill:none;stroke:#b39a83;stroke-width:2;stroke-opacity:.54}
  .walk{fill:none;stroke:#74937d;stroke-width:1.85;stroke-opacity:.72}
  .crossing{fill:none;stroke:#a47722;stroke-width:4}
  .route_geoapify{fill:none;stroke:#b75b32;stroke-width:4.8}
  .route_local{fill:none;stroke:#265e91;stroke-width:4.2;stroke-dasharray:8 3}
  .diagnostic{fill:none;stroke:#a9475c;stroke-width:2.7;stroke-dasharray:5 5}
  .reference{fill:#993d4f;stroke:white;stroke-width:2.3}
  .reference.start{fill:#18634b}
  .reference.geoapify_end{fill:none;stroke:#b75b32;stroke-width:3}
  .reference.local_end{fill:none;stroke:#265e91;stroke-width:2.5}
  .reference.entry{fill:#993d4f;stroke:white}
  circle.crossing{fill:#f1c775;stroke:#a47722;stroke-width:1.8}
  circle.diagnostic{fill:#a9475c;stroke:white;stroke-width:1.8}
  .maptext{font:600 14px "Segoe UI","Microsoft YaHei",sans-serif;fill:#20382d;paint-order:stroke;stroke:#fbfaf3;stroke-width:3.4;stroke-linejoin:round;pointer-events:none}
  .smalltext{font:600 11px "Segoe UI","Microsoft YaHei",sans-serif;fill:#243c30;pointer-events:none}
  .mapnote{fill:#fffdf5;stroke:#d7ddcd;stroke-width:1;pointer-events:none}
  .scale{stroke:#213c31;stroke-width:2;fill:none}
  .active{stroke:#ac7916!important;stroke-width:5!important}
`;
const layerOrder = ["plaza","buildings","road","walk","crossing","route_local","route_geoapify","diagnostic","reference"];
const presetTitles = {overview:"全局",origin:"起点分歧",plaza:"南侧广场",endpoint:"入口缺口"};
const scoreLabels = [
  ["building_outline","建筑轮廓清晰度"],["building_road_separation","建筑与道路区分度"],
  ["pedestrian_visibility","步行通道可辨性"],["entrance_context","入口附近细节充分性"],
  ["occlusion","文字或图标遮挡"],["target_identification","目标建筑定位"],
  ["detail_access","近景接入位置"],["context_detour","上下文绕行空间"],
  ["route_alignment","路线与地图对齐程度"]
];
let activePreset = "overview";
let viewport;
let selected;

function project([lon,lat]) {
  const radians = Math.PI/180;
  return [6378137*lon*radians,6378137*Math.log(Math.tan(Math.PI/4 + lat*radians/2))];
}

function fit(bounds) {
  const [x0,y0] = project(bounds.slice(0,2));
  const [x1,y1] = project(bounds.slice(2,4));
  const width = Math.max(20,x1-x0);
  const height = Math.max(20,y1-y0);
  return {cx:(x0+x1)/2,cy:(y0+y1)/2,s:Math.min((W-36)/width,(H-36)/height)};
}

function toPixel(point) {
  const [x,y] = project(point);
  return [(x-viewport.cx)*viewport.s+W/2,(viewport.cy-y)*viewport.s+H/2];
}

function onScreen(geom) {
  const visit = (coords, box) => {
    if (typeof coords[0] === "number") {
      const p=toPixel(coords);
      box[0]=Math.min(box[0],p[0]); box[1]=Math.min(box[1],p[1]);
      box[2]=Math.max(box[2],p[0]); box[3]=Math.max(box[3],p[1]);
    } else coords.forEach((child)=>visit(child,box));
  };
  const box=[Infinity,Infinity,-Infinity,-Infinity];
  visit(geom.coordinates,box);
  return box[0]<=W+20&&box[1]<=H+20&&box[2]>=-20&&box[3]>=-20;
}

function pathLine(coordinates,closed=false) {
  return coordinates.map((v,i)=> {
    const p=toPixel(v).map((x)=>x.toFixed(2));
    return (i===0?"M":"L")+p.join(",");
  }).join(" ")+(closed?" Z":"");
}

function symbols(geometry,props) {
  const point=(p) => {
    const [cx,cy]=toPixel(p);
    return svg("circle",{cx,cy,r:props.role==="geoapify_end"?11:props.role==="local_end"?6:props.role==="entry"?7:5});
  };
  switch(geometry.type) {
    case "Point": return [point(geometry.coordinates)];
    case "MultiPoint": return geometry.coordinates.map(point);
    case "LineString": return [svg("path",{d:pathLine(geometry.coordinates)})];
    case "MultiLineString": return geometry.coordinates.map((l)=>svg("path",{d:pathLine(l)}));
    case "Polygon": return [svg("path",{d:geometry.coordinates.map((l)=>pathLine(l,true)).join(" ")})];
    case "MultiPolygon": return geometry.coordinates.map((polygon)=>svg("path",{d:polygon.map((l)=>pathLine(l,true)).join(" ")}));
    default: return [];
  }
}

function textSvg(str,x,y,cls="smalltext",attrs={}) {
  const item=svg("text",{x,y,class:cls,...attrs});
  item.textContent=str;
  return item;
}

function showFeature(props,elem) {
  const target=byId("selection");
  target.replaceChildren(node("p","要素检查器","eyebrow"),node("h3",props.label || props.id || "图面要素"));
  document.querySelectorAll("#map .active").forEach((el)=>el.classList.remove("active"));
  if (elem) elem.classList.add("active");
  selected=props.id;
  const fields=[["对象 ID",props.id],["图层",layers[props.layer]?.[0]],["来源",props.source],["证据",props.evidence],
      ["用途",props.note],["原生节点",props.node_ids?.join?.(", ")]];
  const list=node("dl");
  for (const [key,value] of fields) {
    if (value!==undefined&&value!==null&&value!=="") list.append(node("dt",key),node("dd",String(value)));
  }
  target.append(list);
  if (props.tags&&Object.keys(props.tags).length) target.append(node("pre",JSON.stringify(props.tags,null,2)));
}

function visible(props) {
  if (!defaults.has(props.layer)) return false;
  const side=byId("route-side").value;
  return !(side==="geoapify"&&props.layer==="route_local" || side==="local"&&props.layer==="route_geoapify");
}

function marginalia(target) {
  const lat = Math.atan(Math.sinh(viewport.cy/6378137));
  const pixelsPerGroundMeter = viewport.s/Math.cos(lat);
  const step = [10,20,25,50,100,200,250,500,1000].filter((m)=>m*pixelsPerGroundMeter<145).at(-1) || 5;
  const scaleWidth=step*pixelsPerGroundMeter;
  target.replaceChildren(
    svg("rect",{x:12,y:603,width:210,height:45,rx:5,class:"mapnote"}),
    textSvg(step+" m · 中心纬度近似",25,619),
    svg("path",{d:"M25 637v-6m0 3h"+scaleWidth.toFixed(1)+"m0 3v-6",class:"scale"}),
    svg("rect",{x:982,y:12,width:45,height:63,rx:5,class:"mapnote"}),
    textSvg("N",1004,29,"smalltext",{"text-anchor":"middle"}),
    svg("path",{d:"M1004 35l-8 24 8-5 8 5z",fill:"#213c31"}),
    svg("rect",{x:641,y:609,width:387,height:39,rx:5,class:"mapnote"}),
    textSvg("© OpenStreetMap contributors · R2",652,625),
    textSvg(visible({layer:"route_geoapify"})?"Powered by Geoapify":"本地 R2 几何与诊断",652,640),
    svg("rect",{x:12,y:12,width:191,height:26,rx:5,class:"mapnote"}),
    textSvg("上海博物馆 · "+presetTitles[activePreset],24,29)
  );
}

function draw() {
  const g=byId("map-geometries");
  const items=document.createDocumentFragment();
  const labels=document.createDocumentFragment();
  let count=0;
  const grid=svg("g",{});
  for (let i=120;i<W;i+=120) grid.append(svg("path",{d:`M${i} 0V${H}`,class:"grid"}));
  for (let i=110;i<H;i+=110) grid.append(svg("path",{d:`M0 ${i}H${W}`,class:"grid"}));
  items.append(grid);
  for (const layer of layerOrder) {
    const group=svg("g",{"data-layer":layer});
    for (const feature of data.features) {
      if (!feature.geometry||feature.properties.layer!==layer||!visible(feature.properties)||!onScreen(feature.geometry)) continue;
      const props=feature.properties;
      count++;
      for (const elem of symbols(feature.geometry,props)) {
        elem.setAttribute("class",["geom",layer,props.role||"",selected&&selected===props.id?"active":""].join(" "));
        elem.setAttribute("tabindex","0");
        elem.setAttribute("role","button");
        elem.setAttribute("aria-label",props.label||props.id||layer);
        elem.dataset.featureId=props.id||"";
        const title=svg("title");
        title.textContent=[props.label,props.id].filter(Boolean).join(" · ");
        elem.append(title);
        elem.addEventListener("click",()=>showFeature(props,elem));
        elem.addEventListener("keydown",(event)=>{
          if(event.key==="Enter"||event.key===" ") {event.preventDefault();showFeature(props,elem);}
        });
        group.append(elem);
      }
      if(props.label_map&&feature.geometry.type==="Point") {
        const [x,y]=toPixel(feature.geometry.coordinates);
        const offsets=props.role==="geoapify_end"?[12,-13]:props.role==="local_end"?[12,17]:[12,-10];
        labels.append(textSvg(props.label,x+offsets[0],y+offsets[1],"maptext"));
      }
    }
    items.append(group);
  }
  items.append(labels);
  g.replaceChildren(items);
  marginalia(byId("map-marginalia"));
  byId("map-message").textContent=`显示 ${count} 个源要素和诊断标记。虚线距离用于量测。地图层仅表示快照及已保存响应。`;
}

function go(preset) {
  if(!Array.isArray(data.presets[preset])) return;
  activePreset=preset;
  viewport=fit(data.presets[preset]);
  document.querySelectorAll("[data-view]").forEach((item)=>item.setAttribute("aria-pressed",String(item.dataset.view===preset)));
  draw();
}

function exportMap() {
  const copy=byId("map").cloneNode(true);
  copy.setAttribute("width",String(W));
  copy.setAttribute("height",String(H));
  copy.querySelectorAll("[tabindex]").forEach((e)=>e.removeAttribute("tabindex"));
  copy.querySelectorAll(".active").forEach((e)=>e.classList.remove("active"));
  const source=new XMLSerializer().serializeToString(copy);
  const url=URL.createObjectURL(new Blob([source],{type:"image/svg+xml;charset=utf-8"}));
  const a=node("a");
  a.href=url;
  a.download=`shanghai-museum-r2-${activePreset}.svg`;
  a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
}

function setupControls() {
  byId("map-style").textContent=style;
  for(const [id,[name,color]] of Object.entries(layers)) {
    const check=node("input");
    check.type="checkbox";check.checked=true;check.id="layer-"+id;
    check.addEventListener("change",()=>{if(check.checked)defaults.add(id);else defaults.delete(id);draw();});
    const label=node("label",undefined,"check");
    label.htmlFor=check.id;
    const chip=node("i",undefined,"swatch");chip.style.background=color;
    label.append(check,chip,node("span",name));
    byId("layers").append(label);
  }
  byId("route-side").addEventListener("change",draw);
  document.querySelectorAll("[data-view]").forEach((button)=>button.addEventListener("click",()=>go(button.dataset.view)));
  byId("zoom-in").addEventListener("click",()=>{viewport.s*=1.26;draw();});
  byId("zoom-out").addEventListener("click",()=>{viewport.s/=1.26;draw();});
  byId("download").addEventListener("click",exportMap);
}

function setupBasemaps() {
  if(!data.originalMaps) return;
  function pick() {
    const side=byId("base-side").value;
    const view=byId("base-view").value;
    const path=data.originalMaps[view][side];
    byId("base-image").src=path;
    byId("base-original").href=path;
    byId("base-credit").textContent="© OpenStreetMap contributors"+(side==="A"?" · © OpenMapTiles · Powered by Geoapify":"")+" · 首轮原图";
  }
  for(const id of ["base-side","base-view"]) byId(id).addEventListener("change",pick);
  byId("base-detail").addEventListener("toggle",()=>{if(byId("base-detail").open) pick();});
}

function showScores() {
  const target=byId("score-body");
  if (!data.score) {
    target.append(node("p","原始评分文件未核实。"));
    return;
  }
  const {row,filename,sha256,totals,visualTotals}=data.score;
  const source=node("a",filename);
  source.href="../inputs/"+filename;
  byId("score-source").append(source);
  const left=node("div");
  left.append(node("h3","原始分项分数"),node("p",`合计 A ${totals.A}/45 · B ${totals.B}/45 · 总体偏好 ${row.overall_preference}`,"score-summary"));
  left.append(node("p",`八项视觉与场景分数的算术拆分 A ${visualTotals.A}/40 · B ${visualTotals.B}/40`,"score-summary"));
  const table=node("table");
  const head=node("tr");
  ["评分项","A","B"].forEach((s)=>head.append(node("th",s)));
  const body=node("tbody");
  for(const [key,title] of scoreLabels) {
    const tr=node("tr");
    tr.append(node("td",title),node("td",row["A_"+key]),node("td",row["B_"+key]));
    body.append(tr);
  }
  const route=node("tr");
  route.append(node("td","路线是否明显不合理"),node("td",row.A_route_visibly_unreasonable),node("td",row.B_route_visibly_unreasonable));
  body.append(route);
  const thead=node("thead");
  thead.append(head);
  table.append(thead,body);
  left.append(table);
  const feedback=node("div",undefined,"feedback");
  feedback.append(node("h3","原始文字 · failure_reason"),node("blockquote",row.failure_reason));
  if(row.remarks) feedback.append(node("p","remarks"),node("blockquote",row.remarks));
  feedback.append(node("p",`${row.blind_scene_id} · ${row.detail_pair_id} / ${row.context_pair_id} · ${row.scored_at_utc}`,"meta"),
    node("p","SHA256 "+sha256,"meta"));
  target.append(left,feedback);
}

function showLinks() {
  for(const item of data.metrics || []) {
    const box=node("div",undefined,"kpi");
    box.append(node("p",item.label,"eyebrow"),node("strong",item.value));
    if(item.note) box.append(node("span",item.note));
    byId("metrics").append(box);
  }
  for(const [index,item] of data.figures.entries()) {
    const link=node("a",undefined,"figure-card");
    link.href="../figures/"+item.path;
    link.target="_blank";
    link.rel="noopener";
    const desc=node("div");
    desc.append(node("strong",item.title),node("span",item.note));
    link.append(node("span",String(index+1).padStart(2,"0"),"num"),desc);
    byId("figure-list").append(link);
  }
}

if (data&&Array.isArray(data.features)&&data.presets?.overview) {
  setupControls();
  setupBasemaps();
  showLinks();
  showScores();
  go("overview");
} else {
  byId("map-message").textContent="证据数据未加载。请重新构建本地页面数据。";
  byId("download").disabled=true;
}
