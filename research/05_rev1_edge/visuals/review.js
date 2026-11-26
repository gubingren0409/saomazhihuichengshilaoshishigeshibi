"use strict";

const data = window.REV1_DATA;
const MAIN = "R1_AREA_EDGE_MAIN";
const MUSEUM = "sh-huangpu-01";
const SOUTH_DOOR = "6897141353";
const NORTH_DOOR = "6897145227";
const NS = "http://www.w3.org/2000/svg";
const PANELS = {
  overview: {title:"01　地图信息总览", note:"保留馆舍、南北步行面、草地内环、原生步道和已登记门。圈点可打开原生接点证据。", view:"overview"},
  compare: {title:"02　旧 R4 与修订机制同图对照", note:"两幅图共用视野和比例尺。左幅保留历史线网，右幅读取所选运行的允许域、派生边和实际路线。", view:"overview"},
  "south-route": {title:"03　从冻结起点到南门", note:"选择三个原生接点之一，查看同一起点经过该接点的实际折线。原生段、面派生段与门前端口分色。", view:"context"},
  "south-terminal": {title:"04　南门末端放大", note:"查看原门坐标、最后端口与建筑边界。点选终端线检查其净空条件与原始记录。", view:"terminal"},
  north: {title:"05　西北出口与未知间隙", note:"实线表示可达的已保存路线，点虚线只量距离。门外能否接近和能否由此入馆分别记录。", view:"north"},
  matrix: {title:"06　参数、跨病例与失败", note:"同时查看 1、3、5 米试验带宽、消融结果、原始图回归和保留的拒绝。代理点仅供局部诊断。", view:"overview"},
};

const LAYERS = {
  building:["周边建筑","#e0dcd5","#b7b1a5",""],
  road:["原生道路","#fffdf8","#c9c0b4",""],
  plaza:["源步行面","#D3EAF5","#5B9FBE",""],
  grass:["草地／花坛","#d8e6cf","#a6b89c",""],
  water:["源水体","#c1dfeb","#77a7bc",""],
  domain:["允许边缘带","#D7D3EA","#8177A8","3 2"],
  target:["目标馆舍","#F5D9B8","#a87039",""],
  walk:["原生步道","none","#537e87",""],
  fence:["围栏／墙","none","#8a5c50","2 2"],
  crossing:["过街标签","#FFFDFC","#426b77",""],
  gate:["原生栅门","#FFFDFC","#9b5d4b",""],
  derived:["面派生边","none","#8177A8","4 2"],
  terminal_edge:["派生端口","none","#B97589","2 2"],
  historical:["旧 R4 诊断／路线","none","#486b80","8 4"],
  hosted:["历史 Geoapify","none","#D49757","1 3"],
  route_native:["实际路线 · 原生段","none","#2d6074",""],
  route_derived:["实际路线 · 面派生段","none","#544182","7 3"],
  route_terminal:["实际路线 · 门前端口","none","#9b3f64","2 2"],
  route_conflict:["原生段 · 有平面冲突","none","#a1573c","8 3 1 3"],
  gap:["未支持间隙 · 不入路由","none","#b1314d","2 5"],
  supplement:["原生段避障复查 · 单独诊断","none","#407866","3 4"],
  contact:["原生接点","#FFFDFC","#4b6796",""],
  endpoint:["实际折线末点","#D7D3EA","#615581",""],
  origin:["冻结起点","#bce2d6","#2f6456",""],
  entrance:["已登记入口 main／yes","#E8C7D3","#9b3f64",""],
  exit:["已登记出口 exit","#FFFDFC","#9b3f64",""],
  proxy:["冻结代理点","#FFFDFC","#92643c",""],
  road_label:["道路名称","none","#605e57",""],
  area_label:["步行面名称","none","#41677d",""],
  building_label:["建筑名称","none","#755b46",""],
  gap_label:["缺口数值","none","#a03245",""],
};
const INSPECT = new Set(["target","plaza","domain","fence","gate","derived","terminal_edge","route_native",
  "route_derived","route_terminal","route_conflict","gap","supplement","contact","endpoint","origin","entrance","exit","proxy","historical","hosted"]);
const USER_LAYERS = Object.keys(LAYERS).filter(key=>!key.endsWith("_label"));
const DEFAULT_HIDDEN = ["hosted","crossing","gate","supplement"];
const titles = {
  H0_FROZEN_B0:"冻结 B0",
  H1_R4_STRICT_LINES:"旧 R4 · 原生线门禁",
  R1_AREA_EDGE_MAIN:"REV1 · 面派生",
  R1_WITHOUT_DERIVED_EDGES:"消融 · 移除派生边",
  NORTH_APPROACH_AUDIT:"北侧接近诊断",
};
const sids = Object.fromEntries(data.scenes.map(scene=>[scene.id, scene]));
const $ = id=>document.getElementById(id);
const state = {scene:MUSEUM, panel:"compare", variant:MAIN, width:3, contact:"", zoom:1, dx:0, dy:0,
  layers:new Set(USER_LAYERS.filter(x=>!DEFAULT_HIDDEN.includes(x)))};
const runKeys = width=>width===3 ? MAIN : "R1_WIDTH_"+width+"M";
const idString = id=>String(id??"").split("/").at(-1);
const num = value=>typeof value==="number" && Number.isFinite(value) ? value.toFixed(2) : "—";
const safeText = value=>value===undefined || value===null || value==="" ? "—" :
  typeof value==="object" ? JSON.stringify(value) : String(value);
const allRuns = data.experiment?.runs ?? {};
const rowsOf = run=>Array.isArray(run?.scenes) ? run.scenes : Object.values(run?.scenes ?? {});
const sceneRun = (run,sid)=>rowsOf(allRuns[run]).find(row=>(row.scene_id??row.id)===sid) ?? {};
const formatId = id => {
  if (Array.isArray(id)) return id.join(" · ");
  return safeText(id);
};
const outcome = (kind)=>{
  const row=data.outcomes?.[kind] ?? {};
  return kind==="south"?row.selected??{}:row.main??{};
};
const role = row=>row?.inbound_eligibility ?? row?.inbound_status ?? row?.role_status ?? "—";
const exterior = row=>row?.exterior_approach ?? row?.exterior_status ?? row?.status ?? "—";
const gap = row=>row?.gap_m ?? row?.target_gap_m ?? row?.residual_m ?? row?.nearest_gap_m ?? row?.route?.gap_m;
const length = row=>row?.length_m ?? row?.total_length_m ?? row?.route?.length_m;
const stateNames = {
  EXTERIOR_REACHED_CONDITIONAL:"条件到达原登记坐标", ELIGIBLE_CONDITIONAL:"角色适用 · 条件连接成立", REGISTERED_ROLE_SUITABLE_ROUTE_REQUIRED:"角色适用 · 需路线证据", REACHED:"到达原登记坐标", REACHED_ORIGINAL_ENTRANCE:"到达原登记坐标", REACHED_EXACT:"到达原登记坐标",
  MAPPED_ENTRY_REACHED:"到达原登记坐标", CONDITIONALLY_REACHED:"条件到达", APPROACH_WITH_GAP:"已到附近，仍有缺口",
  PLANAR_CONFLICT_ROUTE_REQUIRES_REVIEW:"精确到点 · 原生段有平面冲突", GAP_UNSUPPORTED:"间隙缺证", NO_ROUTE:"无完整路线", NOT_APPLICABLE:"不适用", EXIT_NOT_ELIGIBLE:"出口 · 入馆不适用",
  NOT_ELIGIBLE_EXIT:"出口 · 入馆不适用", UNKNOWN:"未知", PASS:"通过", FROZEN_MATCH:"与冻结结果一致",
};
function human(value) {
  if (value && typeof value==="object") value=value.status ?? value.code ?? value.result;
  return stateNames[value] || safeText(value);
}
function el(tag,textValue,attrs={}) {
  const node=document.createElement(tag);
  if(textValue!==null) node.textContent=textValue;
  for(const [key,val] of Object.entries(attrs)) node.setAttribute(key,val);
  return node;
}
function svg(tag,attrs={},textValue) {
  const node=document.createElementNS(NS,tag);
  for(const [key,val] of Object.entries(attrs)) node.setAttribute(key,val);
  if(textValue!==undefined) node.textContent=textValue;
  return node;
}
function opts(select,rows) { select.replaceChildren(...rows.map(([id,label])=>el("option",label,{value:id}))); }
function activeRun(value=state.variant,width=state.width) { return value===MAIN?runKeys(width):value; }
function mainContacts(width=state.width) {
  const row=sceneRun(runKeys(width),MUSEUM);
  const src=row.south_contacts ?? data.outcomes?.south?.all_contacts ?? [];
  return Array.isArray(src)?src:Object.values(src);
}
function contactId(row) { return row.contact_id ?? row.native_id ?? row.node_id ?? row.contact ?? row.id; }
function exactContactRows(scene) {
  const ids=new Map();
  for (const c of scene.contacts) {
    const key=c.native_id ?? (c.native_ids ?? []).find(id=>id.startsWith("node/"));
    if (key) ids.set(idString(key), key);
  }
  for (const c of mainContacts()) if(contactId(c)) ids.set(idString(contactId(c)),contactId(c));
  return [...ids];
}
function selectedContact() {
  if(state.contact) return state.contact;
  const candidates=mainContacts().filter(row=>row.status==="EXTERIOR_REACHED_CONDITIONAL" && typeof length(row)==="number");
  if (candidates.length) return idString(contactId([...candidates].sort((a,b)=>length(a)-length(b))[0]));
  return "";
}
function displayRun(run) { return run===MAIN ? "REV1 · "+state.width+" 米" : titles[run] ?? run; }
function mapKind(props,layer) {
  const p=props;
  return p.native_id ?? p.edge_id ?? p.id ?? p.route_id ?? p.source_area_id ?? (p.native_ids ?? []).join(" · ") ?? LAYERS[layer][0];
}
function inspect(feature) {
  const p=feature.props, label=LAYERS[feature.layer][0];
  const panel=$("inspector");
  panel.replaceChildren(el("span","对象证据",{class:"eyebrow"}),el("h3",p.label ?? label));
  const fields=[
    ["图层",label],["对象或边 ID",mapKind(p,feature.layer)],["原生 ID",formatId(p.native_ids ?? p.source_ids ?? p.source_area_id ?? p.parent_area_id)],
    ["原始 WGS84 [经度，纬度]",p.original_coordinate ?? p.wgs84 ?? p.coordinates_wgs84 ?? p.coordinate],
    ["证据类别",p.kind ?? p.edge_class ?? p.evidence_status ?? p.evidence],
    ["运行／带宽",p.run_id? p.run_id+" / "+(p.width_m??"—")+" 米":null],["长度（m）",p.length_m??p.gap_m??p.distance_m],
    ["父源 SHA256",p.source_sha256??p.parent_input_sha256??p.source_clip_sha256],
    ["原始标签",p.tags??p.original_tags??p.source_tags],["层级／假设",p.layer_status??p.layer_assumption??p.assumptions],
    ["净空（m）",p.clearance_m??p.min_clearance_m],["面与障碍检查",p.checks??p.validation??p.coverage_check??[p.coverage,p.obstacle_ids,p.clearance_exception_rule]],
    ["判定",p.status??p.reason??p.reject_reason],
  ];
  const info=el("dl",null);
  for(const [k,v] of fields) if(v!==null&&v!==undefined&&v!=="—"&&v!==""){
    info.append(el("dt",k),el("dd",safeText(v)));
  }
  panel.append(info,el("details",null));
  panel.lastElementChild.append(el("summary","完整记录"),el("code",JSON.stringify(p,null,2)));
}
function modeFilter(feature,run,panel,scene,chosenContact) {
  const p=feature.props, layer=feature.layer;
  if(layer==="road_label" && !state.layers.has("road") && panel!=="overview" && panel!=="compare" && panel!=="south-route") return false;
  if(layer==="area_label" && !state.layers.has("plaza")) return false;
  if(layer==="building_label" && !state.layers.has("target")) return false;
  if(layer==="gap_label" && !state.layers.has("gap")) return false;
  if(!layer.endsWith("_label") && !state.layers.has(layer)) return false;
  if(!p.run_id) {
    if(layer==="historical" && !["H0_FROZEN_B0","H1_R4_STRICT_LINES","R1_WITHOUT_DERIVED_EDGES"].includes(run)) return false;
    if(layer==="contact" && scene.id===MUSEUM && idString(p.native_id)===SOUTH_DOOR) return false;
    return true;
  }
  if (panel==="overview") return false;
  if(layer==="supplement") {
    const north=String(p.route_id??"").endsWith(":NORTH");
    return run===MAIN && ((panel==="north" && north) || (panel.startsWith("south-") && !north));
  }
  if (p.run_id!==run && !(p.run_id==="NORTH_APPROACH_AUDIT" && panel==="north" && run===MAIN)) return false;
  const door=idString(p.entrance_id ?? p.door_id ?? p.target_id);
  const route=String(p.route_id ?? "");
  if(panel==="north" && (door===SOUTH_DOOR || route.includes("south"))) return false;
  if(["south-route","south-terminal"].includes(panel) && (door===NORTH_DOOR || layer==="gap"&&route.includes("north") || route.includes("north"))) return false;
  if(panel==="compare" && scene.id===MUSEUM && (door===NORTH_DOOR || route.includes("north"))) return false;
  const directContact=idString(p.contact_id ?? p.source_contact_id ?? p.anchor_id);
  if(layer.startsWith("route") && chosenContact && directContact && directContact!==chosenContact) return false;
  return true;
}
function pointGlyph(layer,x,y,unit) {
  const r=5.4*unit;
  if(layer==="entrance"||layer==="exit"||layer==="proxy") {
    if(layer==="exit") return svg("path",{d:"M"+(x-r)+","+(y-r)+"h"+2*r+"v"+2*r+"h"+(-2*r)+"Z"});
    if(layer==="proxy") return svg("path",{d:"M"+x+","+(y-r)+"l"+r+","+2*r+"h"+(-2*r)+"Z"});
    return svg("path",{d:"M"+x+","+(y-r)+"l"+r+","+r+"l"+(-r)+","+r+"l"+(-r)+","+(-r)+"Z"});
  }
  return svg("circle",{cx:x,cy:y,r:layer==="contact"?r*.74:r});
}
function decorateFeature(feature,node,interactive) {
  if(!interactive || !INSPECT.has(feature.layer)) return;
  const title=String(feature.props.label ?? mapKind(feature.props,feature.layer) ?? LAYERS[feature.layer][0]);
  node.setAttribute("role","button"); node.setAttribute("tabindex","0");
  node.setAttribute("aria-label",title);
  node.setAttribute("data-layer",feature.layer);
  node.append(svg("title",{},title));
  node.addEventListener("click",()=>inspect(feature));
  node.addEventListener("keydown",event=>{
    if(event.key==="Enter" || event.key===" "){event.preventDefault();inspect(feature);}
  });
}
function styleGeometry(node,layer,pathArea) {
  const [,fill,stroke,dash]=LAYERS[layer];
  const width={
    target:1.45,road:2.2,walk:1.24,fence:1.4,derived:1.1,terminal_edge:1.4,historical:2,
    hosted:1.8,route_native:3.8,route_derived:3.9,route_terminal:4.5,route_conflict:3.8,gap:2.8,
  }[layer] ?? (pathArea ? .85 : 1.55);
  node.setAttribute("fill",pathArea ? fill : (node.nodeName==="circle" || ["entrance","exit","proxy"].includes(layer) ? fill : "none"));
  node.setAttribute("stroke",stroke); node.setAttribute("stroke-width",width);
  if(dash) node.setAttribute("stroke-dasharray",dash);
  node.setAttribute("stroke-linecap","round"); node.setAttribute("stroke-linejoin","round");
  node.setAttribute("vector-effect","non-scaling-stroke");
  if(pathArea) node.setAttribute("fill-rule","evenodd");
  if(layer==="domain") node.setAttribute("fill-opacity",".68");
}
function labelAt(layer,props,x,y,unit) {
  const text=props.label;
  if(!text || !["origin","entrance","exit","area_label","road_label","building_label","gap_label"].includes(layer)) return null;
  const street=layer==="road_label";
  const shifted=!layer.endsWith("_label")||layer==="gap_label";
  const size=(street?11.4:13)*unit;
  return svg("text",{x:x+(shifted?7*unit:0),y:y+(shifted?-7*unit:0),fill:layer==="gap_label"?"#a03245":street?"#4f4a45":"#2D3238",
     "font-size":size,"font-weight":street?550:720,"text-anchor":shifted?"start":"middle",
     "paint-order":"stroke","stroke":"#FCFAF7","stroke-width":size*.29,"stroke-linejoin":"round"},text);
}
function camera(view,zoom,dx,dy) {
  const [x,y,w,h]=view;
  return [x+w/2-w/(2*zoom)+dx,y+h/2-h/(2*zoom)+dy,w/zoom,h/zoom];
}
function viewBoxOf(scene,panel,custom=null) {
  return custom ?? camera(scene.bounds[PANELS[panel].view],state.zoom,state.dx,state.dy);
}
function niceScale(w) {
  return [500,250,100,50,25,10,5,2,1].find(n=>n<=w*.22) ?? 1;
}
function addMapFurniture(node,view,unit) {
  const [x,y,w,h]=view, length=niceScale(w), lx=x+12*unit, ly=y+h-16*unit;
  node.append(svg("rect",{x:lx-5*unit,y:ly-19*unit,width:Math.max(length+10*unit,54*unit),height:27*unit,rx:3*unit,fill:"#FFFDFC","fill-opacity":.93}));
  node.append(svg("path",{d:"M"+lx+","+ly+"h"+length,stroke:"#2D3238","stroke-width":2.8,"vector-effect":"non-scaling-stroke"}));
  node.append(svg("text",{x:lx,y:ly-5*unit,fill:"#2D3238","font-size":11*unit},length+" m"));
  node.append(svg("text",{x:x+w-32*unit,y:y+20*unit,"font-size":14*unit,"font-weight":750,fill:"#2D3238"},"↑ N"));
}
function buildMap(scene,panel,variant,interactive=true,options={}) {
  const view=viewBoxOf(scene,panel,options.view), unit=view[2]/660;
  const run=activeRun(variant,options.width ?? state.width);
  const contacts=options.contact ?? (["compare","south-route","south-terminal"].includes(panel) ? selectedContact() : "");
  const attrs={viewBox:view.join(" "),xmlns:NS,role:"img","aria-label":scene.label+" "+PANELS[panel].title,
    "data-run":run,"data-panel":panel,"data-source-sha256":scene.source_sha256,
    "font-family":"Microsoft YaHei, Arial, sans-serif"};
  const map=svg("svg",attrs);
  map.append(svg("rect",{x:view[0],y:view[1],width:view[2],height:view[3],fill:"#f0efe9"}));
  const batch = new Map(Object.keys(LAYERS).map(key=>[key,[]]));
  for(const feature of scene.features) if(modeFilter(feature,run,panel,scene,contacts)) batch.get(feature.layer).push(feature);
  const labels=[];
  for(const [layer,features] of batch) {
    const group=svg("g",{"data-map-layer":layer});
    for(const f of features) {
      for(const command of f.shape) {
        let elem;
        if(command.point) {
          const [x,y]=command.point;
          const label=labelAt(layer,f.props,x,y,unit);
          if(label) labels.push(label);
          if(layer.endsWith("_label")) continue;
          elem=pointGlyph(layer,x,y,unit);
        } else {
          elem=svg("path",{d:command.d});
        }
        styleGeometry(elem,layer,command.area);
        decorateFeature(f,elem,interactive);
        group.append(elem);
      }
    }
    if(group.children.length) map.append(group);
  }
  map.append(...labels);
  addMapFurniture(map,view,unit);
  return map;
}
function legendItem(layer) {
  const holder=el("span",null,{class:"legend-item"}), demo=svg("svg",{viewBox:"0 0 30 12"});
  const area=["building","plaza","grass","water","domain","target"].includes(layer);
  const point=["entrance","exit","proxy","origin","contact","endpoint","gate","crossing"].includes(layer);
  const mark=area?svg("rect",{x:4,y:2,width:22,height:8,rx:1}):point?pointGlyph(layer,15,6,.72):svg("path",{d:"M2,6H28"});
  styleGeometry(mark,layer,area); demo.append(mark); holder.append(demo,el("span",LAYERS[layer][0]));
  return holder;
}
function visibleLegend(maps) {
  const used=new Set(maps.flatMap(map=>[...map.querySelectorAll("g[data-map-layer]")].map(g=>g.dataset.mapLayer)));
  return Object.keys(LAYERS).filter(layer=>used.has(layer));
}
function mapCard(scene,panel,variant) {
  const card=el("figure",null,{class:"map-card"}), map=buildMap(scene,panel,variant,true);
  card.append(el("figcaption",panel==="overview"?"冻结地图源信息":displayRun(variant)),map);
  return [card,map];
}
function statusCells(row) {
  return [human(exterior(row)),human(role(row)),num(length(row)),num(gap(row)),
    safeText(row?.coordinate ?? row?.original_coordinate ?? row?.target),safeText(row?.endpoint ?? row?.route_end ?? row?.actual_endpoint)];
}
function table(headers,rows) {
  const out=el("table",null), head=el("thead",null), body=el("tbody",null);
  const row=el("tr",null);
  headers.forEach(h=>row.append(el("th",h)));
  head.append(row);
  for(const values of rows) {
    const tr=el("tr",null);
    values.forEach(value=>tr.append(el("td",safeText(value))));
    body.append(tr);
  }
  out.append(head,body); return out;
}
function summaryCells(runId) {
  const museum=sceneRun(runId,MUSEUM);
  const r=rowsOf(allRuns[runId]);
  const south=museum.entrances?.["node/"+SOUTH_DOOR] ?? museum.strict_entrances?.["node/"+SOUTH_DOOR] ?? {};
  const north=museum.entrances?.["node/"+NORTH_DOOR] ?? museum.strict_entrances?.["node/"+NORTH_DOOR] ?? {};
  const totals=allRuns[runId]?.totals ?? allRuns[runId]?.summary ?? {};
  const counts=r.map(row=>row.truly_added_edges_unique ?? row.added_edges);
  const n=counts.every(x=>typeof x==="number")?counts.reduce((a,b)=>a+b,0):([ "H0_FROZEN_B0","R1_WITHOUT_DERIVED_EDGES"].includes(runId)?0:totals.derived_edges);
  return [displayRun(runId),r.length || "—",n ?? "—",human(exterior(south)),num(length(south)),num(gap(north))];
}
function matrixRows() {
  return ["H0_FROZEN_B0","H1_R4_STRICT_LINES","R1_WIDTH_1M",MAIN,"R1_WIDTH_5M","R1_WITHOUT_DERIVED_EDGES"].map(summaryCells);
}
function resultTable(scene,panel) {
  $("detail-title").textContent=panel==="matrix"?"参数与六病例回归":"当前病例的实跑记录";
  const area=$("detail");
  if (data.preview) {
    area.replaceChildren(el("p","源数据开发图。正式路线、间隙与派生边待实验产物进入页面。",{class:"empty"}));
    return;
  }
  if(panel==="matrix") {
    const heads=["保存的运行","病例数","新增边数／记录口径","博物馆南门外","南门路线（m）","北侧残差（m）"];
    const cases=data.scenes.map(s=>{
      const old=s.old_result.local_b0_frozen_replay??{}, updated=sceneRun(MAIN,s.id);
      const registered=updated.entrances??{};
      const target=Object.values(registered).find(e=>e&&typeof e==="object"&&e.coordinate)??{};
      const statuses=Object.values(registered).filter(e=>e&&typeof e==="object").map(e=>human(exterior(e))).join(" / ");
      const listed=(updated.areas??[]).map(a=>safeText(a.area_id)+" "+safeText(a.status)+" "+safeText(a.rejected)).join(" / ");
      return [s.label,s.building_id,human(old.status),s.focus_ids.join(" · ") || "无冻结焦点步行面",statuses||human(exterior(target)),listed||"—"];
    });
    area.replaceChildren(table(heads,matrixRows()),el("h3","冻结病例和保留的拒绝"),table(["病例","原生建筑","冻结 B0","盘点的源面","严格原门状态","焦点面状态"],cases));
    return;
  }
  const run=sceneRun(activeRun(),scene.id);
  let selected=panel==="north"?outcome("north"):panel.startsWith("south-")?outcome("south"):null;
  if(panel==="north") selected=run.entrances?.["node/"+NORTH_DOOR] ?? run.strict_entrances?.["node/"+NORTH_DOOR] ?? selected;
  if(panel.startsWith("south-")) selected=run.entrances?.["node/"+SOUTH_DOOR] ?? run.strict_entrances?.["node/"+SOUTH_DOOR] ?? selected;
  const rows=[];
  if(scene.id===MUSEUM && selected) rows.push([panel==="north"?"西北门 · exit":"南门 · main",...statusCells(selected)]);
  if(!selected) {
    const source=run.entrances??run.strict_entrances??{};
    for(const [key,item] of Object.entries(source)) {
      if(item && typeof item==="object") rows.push([item.native_id??item.entrance_id??key,...statusCells(item)]);
    }
    if(!rows.length && scene.id==="sh-library" && Object.keys(outcome("library")).length) rows.push(["图书馆登记入口",...statusCells(outcome("library"))]);
  }
  const heads=["登记点","到门外","入馆角色","路线（m）","末点残差（m）","原登记坐标","实际末点"];
  const display=rows.length?table(heads,rows):el("p","此视图保留地图上下文和冻结请求。无对应的合格登记点结果。",{class:"empty"});
  area.replaceChildren(display);
  if(scene.id===MUSEUM && panel.startsWith("south-")){
    const contacts=mainContacts().map(c=>[contactId(c),human(c.status??exterior(c)),num(length(c)),num(gap(c)),
      safeText(c.section_lengths_m ?? c.length_by_kind_m ?? c.sections_m),human(c.reason??c.failure_reason),safeText(c.obstacle_conflicts)]);
    if(contacts.length) area.append(el("h3","三个原生接点的单独尝试"),table(["原生接点","状态","总长（m）","残差（m）","各段长度（m）","阻断","已知障碍冲突"],contacts));
  }
  if(scene.id===MUSEUM && panel==="north") {
    const evidence=selected?.gap_evidence;
    if(evidence) area.append(el("p","测距线 "+num(evidence.length_m)+" 米，其中未支持 "+num(evidence.unsupported_length_m)+" 米。虚线不入路由。西北门保留 OSM 的 exit 标签。"));
    if(selected?.obstacle_conflicts && Object.keys(selected.obstacle_conflicts).length) area.append(el("p","原生路线平面告警 "+safeText(selected.obstacle_conflicts)));
  }
  if(scene.id===MUSEUM && (panel==="north" || panel.startsWith("south-"))) {
    const records=data.outcomes?.supplement ?? [];
    const item=records.find(row=>row.subject===(panel==="north"?"NORTH_APPROACH":"SOUTH_CONTACT"));
    if(item) {
      const alt=panel==="north" ? item.alternate_to_same_point ?? item.alternate_native_prefix ?? item.alternate ?? {} : {};
      const total=item.total_m ?? alt.length_m;
      const phrase=panel==="north" ? "可切换原生段避障复查，替代线到同一可达点，门前间隙保留。" : "可切换原生段避障复查。接点 "+item.contact_id+" 改用另一原生前缀，派生后缀相同。";
      area.append(el("p",phrase+(total===undefined?"":" 复查路线 "+num(total)+" 米。")+" 正式对照仍保留首跑。"));
    }
  }
}
function hero() {
  const south=outcome("south"), north=outcome("north");
  const contacts=mainContacts(3);
  const reached=contacts.filter(c=>gap(c)===0).length;
  const clear=contacts.filter(c=>c.status==="EXTERIOR_REACHED_CONDITIONAL").length;
  $("south-metric").textContent=contacts.length?reached+" / "+contacts.length+" 到点 · "+clear+" 条无已知冲突":human(exterior(south));
  $("south-caption").textContent=length(south)===undefined?"固定门坐标 · 按接点逐段复查":"主设置完整路线 "+num(length(south))+" 米";
  $("north-metric").textContent=gap(north)===undefined?human(exterior(north)):num(gap(north))+" 米";
  $("north-caption").textContent="西北出口 · "+human(exterior(north));
  const b0=rowsOf(allRuns.H0_FROZEN_B0);
  $("b0-metric").textContent=b0.length?b0.filter(row=>row.matches_frozen).length+" / "+b0.length+" 与冻结一致":"六个冻结源病例";
}
function render() {
  const scene=sids[state.scene], p=PANELS[state.panel];
  $("panel-title").textContent=p.title;
  $("panel-note").textContent=p.note+(data.preview?"　当前为源数据开发图。":"");
  for(const tab of $("panel-tabs").children) tab.setAttribute("aria-current",tab.dataset.panel===state.panel?"page":"false");
  const mapGrid=$("map-grid");
  const variants=state.panel==="compare"?["H1_R4_STRICT_LINES",state.variant]:[state.variant];
  const cards=variants.map(variant=>mapCard(scene,state.panel,variant));
  mapGrid.classList.toggle("paired",cards.length===2);
  mapGrid.replaceChildren(...cards.map(c=>c[0]));
  $("legend").replaceChildren(...visibleLegend(cards.map(c=>c[1])).map(legendItem));
  $("contact").disabled=scene.id!==MUSEUM || !state.panel.startsWith("south-");
  $("width").disabled=state.variant!==MAIN;
  resultTable(scene,state.panel);
}
function resetCamera() {state.zoom=1;state.dx=0;state.dy=0;}
function viewSelection() {
  const value=location.hash.slice(1);
  state.panel=PANELS[value]?value:"compare";
  if (["south-route","south-terminal","north"].includes(state.panel)) {
    state.scene=MUSEUM; $("scene-select").value=MUSEUM;
  }
  resetCamera();
  render();
}
function exportSVG(panel=state.panel,scene=sids[state.scene],options={}) {
  const paired=panel==="compare";
  const which=paired?["H1_R4_STRICT_LINES",options.variant??state.variant]:[options.variant??state.variant];
  const mapWidth=paired?760:1100, mapHeight=mapWidth/1.48, left=26, top=86;
  const totalWidth=mapWidth*which.length+left*(which.length+1);
  const visual=svg("svg",{viewBox:"0 0 "+totalWidth+" "+(top+mapHeight+128),width:totalWidth,
    height:top+mapHeight+128,xmlns:NS,"font-family":"Microsoft YaHei, Arial, sans-serif",
    "data-panel":panel,"data-evidence-sha256":data.sources.routes??"preview",
    "data-source-clip-sha256":scene.source_sha256});
  visual.append(svg("rect",{width:"100%",height:"100%",fill:"#FCFAF7"}));
  visual.append(svg("text",{x:left,y:31,fill:"#2D3238","font-size":25,"font-weight":750},PANELS[panel].title));
  visual.append(svg("text",{x:left,y:55,fill:"#505961","font-size":13},scene.label+"　"+PANELS[panel].note));
  const maps=[];
  which.forEach((v,index)=>{
    const x=left+index*(mapWidth+left);
    const map=buildMap(scene,panel,v,false,options);
    map.setAttribute("x",x);map.setAttribute("y",top);map.setAttribute("width",mapWidth);map.setAttribute("height",mapHeight);
    visual.append(svg("text",{x,y:77,fill:"#2D3238","font-size":14,"font-weight":650},displayRun(v)),map);
    maps.push(map);
  });
  let x=left, y=top+mapHeight+22;
  for(const key of visibleLegend(maps)){
    const lab=LAYERS[key][0], slot=20+13*lab.length;
    if(x+slot>totalWidth-left) {x=left;y+=20;}
    const mark=svg("path",{d:"M"+x+","+y+"h15"});
    styleGeometry(mark,key,false);
    visual.append(mark,svg("text",{x:x+19,y:y+4,fill:"#2D3238","font-size":11},lab));
    x+=slot+10;
  }
  visual.append(svg("text",{x:left,y:top+mapHeight+116,fill:"#59616a","font-size":11},
    "EPSG:32651 · © OpenStreetMap contributors · Geoapify 历史服务路线 · 派生结果为地图条件研究"));
  return new XMLSerializer().serializeToString(visual);
}
function exportMatrix() {
  const w=1160,h=630, output=svg("svg",{width:w,height:h,viewBox:"0 0 "+w+" "+h,xmlns:NS,
    "font-family":"Microsoft YaHei, Arial, sans-serif","data-panel":"matrix","data-evidence-sha256":data.sources.experiment??"preview"});
  output.append(svg("rect",{width:w,height:h,fill:"#FCFAF7"}));
  output.append(svg("text",{x:25,y:40,"font-size":28,"font-weight":750,fill:"#2D3238"},PANELS.matrix.title));
  const marks=[24,280,418,610,885,1020];
  const labels=["运行","病例数","新增边数","南门门外状态","南门长度 m","北侧残差 m"];
  labels.forEach((text,i)=>output.append(svg("text",{x:marks[i],y:84,"font-size":13,"font-weight":700,fill:"#2D3238"},text)));
  for(const [index,row] of matrixRows().entries()){
    const y=117+index*41;
    if(index%2===0) output.append(svg("rect",{x:20,y:y-21,width:w-40,height:36,fill:"#D3EAF5","fill-opacity":.55}));
    row.forEach((text,i)=>output.append(svg("text",{x:marks[i],y,"font-size":13,fill:"#2D3238"},safeText(text))));
  }
  output.append(svg("text",{x:24,y:386,"font-size":17,"font-weight":750,fill:"#2D3238"},"冻结病例与原生建筑"));
  for(const [i,scene] of data.scenes.entries()){
    const y=415+i*29;
    output.append(svg("text",{x:24,y,"font-size":13,fill:"#2D3238"},scene.label+" · "+scene.building_id));
    output.append(svg("text",{x:424,y,"font-size":13,fill:"#2D3238"},"焦点步行面 "+(scene.focus_ids.join(" · ")||"无冻结焦点面")));
  }
  output.append(svg("text",{x:24,y:h-17,"font-size":11,fill:"#59616a"},"六个开发／回归病例 · 缺失值保留 · 现场核验为零"));
  return new XMLSerializer().serializeToString(output);
}
function download() {
  const text=state.panel==="matrix"?exportMatrix():exportSVG();
  const url=URL.createObjectURL(new Blob([text],{type:"image/svg+xml;charset=utf-8"}));
  const link=el("a",null,{href:url,download:"rev1-"+state.scene+"-"+state.panel+".svg"});
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function setup() {
  for(const [key,item] of Object.entries(PANELS)){
    const tab=el("a",item.title,{href:"#"+key,"data-panel":key});$("panel-tabs").append(tab);
  }
  opts($("scene-select"),data.scenes.map(scene=>[scene.id,scene.label]));
  opts($("variant"),[[MAIN,"REV1 · 面派生"],["H1_R4_STRICT_LINES","旧 R4 · 原生线门禁"],["R1_WITHOUT_DERIVED_EDGES","消融 · 移除派生边"],["H0_FROZEN_B0","冻结 B0"]]);
  $("variant").value=MAIN;
  opts($("contact"),[["","最短的已保存完整路线"],...exactContactRows(sids[MUSEUM])]);
  $("scene-select").addEventListener("change",event=>{state.scene=event.target.value;resetCamera();render();});
  $("variant").addEventListener("change",event=>{state.variant=event.target.value;render();});
  $("width").addEventListener("change",event=>{state.width=Number(event.target.value);render();});
  $("contact").addEventListener("change",event=>{state.contact=event.target.value;render();});
  for(const key of USER_LAYERS){
    const check=el("input",null,{type:"checkbox",value:key,"data-layer-toggle":key});
    check.checked=state.layers.has(key);
    check.addEventListener("change",()=>{if(check.checked)state.layers.add(key);else state.layers.delete(key);render();});
    const label=el("label",null);label.append(check,el("span",LAYERS[key][0]));$("layers").append(label);
  }
  const zoom=factor=>{state.zoom=Math.max(.58,Math.min(5,state.zoom*factor));render();};
  $("zoom-in").addEventListener("click",()=>zoom(1.32)); $("zoom-out").addEventListener("click",()=>zoom(1/1.32));
  $("zoom-reset").addEventListener("click",()=>{resetCamera();render();});
  $("map-grid").addEventListener("wheel",event=>{if(event.ctrlKey){event.preventDefault();zoom(event.deltaY<0?1.13:1/1.13);}},{passive:false});
  $("export").addEventListener("click",download);
  for(const [name,panel] of Object.entries(data.figures)) $("figure-links").append(el("a",PANELS[panel].title,{href:"figures/"+name}));
  window.addEventListener("hashchange",viewSelection);
  hero();
  viewSelection();
}
window.rev1Review={
  exportPanel(panel,scene=MUSEUM) {
    const layers=new Set(state.layers);
    state.layers=new Set(USER_LAYERS.filter(x=>!["hosted","crossing","gate"].includes(x)));
    try {
      return panel==="matrix"?exportMatrix():exportSVG(panel,sids[scene],{
        variant:MAIN,width:3,view:sids[scene].bounds[PANELS[panel].view],contact:selectedContact()});
    } finally { state.layers=layers; }
  },
  renderState(){return {scene:state.scene,panel:state.panel,variant:state.variant,width:state.width,zoom:state.zoom};}
};
setup();
