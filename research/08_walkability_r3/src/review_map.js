"use strict";
const data = JSON.parse(document.getElementById("payload").textContent);
const el = id => document.getElementById(id);
const html = (tag, value) => {const n = document.createElement(tag); if (value !== undefined) n.textContent = value; return n;};
const svg = (tag, attrs) => {const n = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k,v] of Object.entries(attrs)) n.setAttribute(k, v); return n;};
const scheme = {
  park:["#e7ebd7","#a0ad81","1 2",1,"公园范围"], plaza:["#e0e9eb","#91a5ae","","1","登记步行面"],
  grass:["#d8e3c9","#93a577","",1,"草地或花坛"], building:["#e7d9cb","#b29a85","",1,"建筑"],
  water:["#c6e0ef","#759db4","",1,"水体"], road:["none","#b3ad9f","",1.4,"道路"],
  walk:["none","#8ca4a6","",1.3,"原生步道"], "walk-grade":["none","#674c8b","2 3",2.2,"原生明确层级"], fence:["none","#6e504b","3 2",2,"墙或围栏"],
  gate:["#8e7762","#fff","",1,"源闸口"], crossing:["#8f9cac","#fff","",1,"源过街"],
  label:["none","#49616b","",1,"地图文字"], domain:["none","#474e68","4 4",1.8,"搜索域边界"],
  "state-native":["#88bdc7","#48909c","",0.55,"NATIVE · 原生"],
  "state-inferred":["#56af8b","#276f55","",0.65,"INFERRED · 推断"],
  "state-restricted":["#e6aaa3","#b66b66","",0.55,"RESTRICTED · 受限"],
  "state-unknown":["#f0daab","#b58c4c","1 2",0.6,"UNKNOWN · 未知"],
  "route-native":["none","#12536c","",3.8,"原生路线"],
  "route-derived":["none","#67509d","4 2",3.5,"旧面派生路线"],
  "route-inferred":["none","#bd4b2a","7 3",3.8,"推断区域内路线"],
  "route-line":["none","#953e65","6 3",3.8,"I-LINE 假设直连"],
  "route-derived-new":["none","#745d9b","2 2",3.5,"已标面内新图段"],
  "route-unknown":["none","#a05b00","2 3",3.6,"有条件经过未知"],
  restored:["none","#247450","",3.3,"修复保留原生步道"],
  rejected:["none","#a43d61","3 2",2.8,"旧规则删除／被拒绝"],
  gap:["none","#793c4d","2 4",2.2,"仅测距的缺口"],
  reference:["none","#43448a","5 3",2.2,"事后揭示参考面"],
  "reference-line":["none","#43448a","5 3",2.9,"事后揭示参考线"],
  start:["#1a6657","#fff","",1.5,"固定起点"],
  exit:["#712b60","#fff","",1.5,"原登记出口"],
  endpoint:["#5a43a3","#fff","",1.5,"查询端点"],
  interface:["#9c571c","#fff","",1.5,"外围接点"]
};
const groupBy = {
  "底图":["park","plaza","grass","building","water","road","walk","walk-grade","fence","gate","crossing","label"],
  "区域与搜索域":["domain","state-native","state-inferred","state-restricted","state-unknown"],
  "路线与参考":["route-native","route-derived","route-derived-new","route-line","route-inferred","route-unknown","restored","rejected","reference","reference-line","gap"],
  "起点／出口／接点":["start","exit","endpoint","interface"]
};
const descriptions = {
  grass:["01 · 草地背景与原生步道","同一起点和北侧原接网点。虚线显示旧规则因草地而排除的已标片段，右图显示恢复的原生步道。"],
  region:["02 · 北门局部区域","深灰虚线是搜索范围。右图逐单元标出原生、推断、受限和未知。原生步道线仍在线层，面积只统计面。橙色虚线为冻结区域内的条件路线。"],
  pairs:["03 · 同一冻结区域的多端点查询","两幅图复用同一区域对象。可切换实际外围接点对和事先按区域几何选取的控制端点，后者用于检验推断区内部寻路。控制点只作查询，不是入口。"],
  mask:["04 · 受控缺标恢复","左图只显示预测可见输入，右图叠加区域结果和事后揭示的参考。线遮蔽的面积只按明确的评价代理解释。"],
  limits:["05 · 明确障碍和未知","左图显示原始可见障碍和地图上下文，右图显示区域分类、对照几何与结果。暖黄保留未知身份；下拉中的上下文核查与正式负例分别标注。"],
  route:["06 · 完整路线分层","同一起点、原出口及视野对照。蓝色是原生路线，紫色是冻结步行面派生路线，橙色是本轮推断部分。"]
};
const legendLayers = {
  grass:["grass","walk","rejected","restored","route-native","start","interface"],
  region:["building","park","plaza","grass","domain","state-native","state-inferred","state-restricted","state-unknown","route-native","route-derived","route-derived-new","route-line","route-inferred","route-unknown","interface","exit"],
  pairs:["domain","state-native","state-inferred","state-restricted","state-unknown","route-native","route-derived","route-derived-new","route-line","route-inferred","route-unknown","interface","endpoint"],
  mask:["walk","building","state-native","state-inferred","state-restricted","state-unknown","reference","reference-line","route-inferred","endpoint"],
  limits:["building","water","fence","walk-grade","grass","park","state-inferred","state-restricted","state-unknown","reference","reference-line","gap"],
  route:["route-native","route-derived","route-derived-new","route-line","route-inferred","route-unknown","gap","start","exit","interface"]
};
const enabled = new Set(Object.keys(groupBy));
const figures = Object.keys(descriptions);
let active = "grass", view = "full", zoom = 1, offset = [0,0], methodLeft = "I-LINE", methodRight = "I-REGION";
let pairLeft, pairRight, positiveCase, negativeCase;
const north = data.north;
const queries = north.summary.queries;
const focusPoints = north.points.filter(p=>!p.props.variant||p.props.variant==="I-REGION");
const door = queries.includes("NORTH-DOOR") ? "NORTH-DOOR" : queries.find(q=>q.toLowerCase().includes("door"));
const pairs = queries.filter(q=>q!==door && (q.includes("PAIR") || q.includes("CONTROL")));
const control = pairs.find(q=>q.includes("CONTROL"));
const caseIds = Object.keys(data.benchmark);
const caseType = id => String(data.benchmark[id].summary.case_type || "");
const positives = caseIds.filter(id=>!caseType(id).includes("NEGATIVE") && !id.startsWith("N-"));
const negatives = caseIds.filter(id=>caseType(id).includes("NEGATIVE") || id.startsWith("N-"));
const limitContext = positives.filter(id=>data.benchmark[id].base.some(f=>["fence","walk-grade","grass"].includes(f.layer)) || data.benchmark[id].right.some(f=>f.layer==="state-unknown"));

function length(value, suffix=" m") {
  return value === null || value === undefined ? "—" :
    Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-CN", {minimumFractionDigits:2,maximumFractionDigits:2})+suffix : String(value);
}
function route(variant, query) {
  return north.routes[variant+"|"+query] || [];
}
function summary(variant, query) {
  return north.summary.variants[variant]?.routes?.[query] || {};
}
function note(variant, query) {
  const r=summary(variant,query);
  const features=route(variant,query).filter(f=>f.layer.startsWith("route-"));
  const totals=features.reduce((a, f)=>a+Number(f.props.length_m||0),0);
  const distance=features.length ? " · "+length(r.length_m ?? totals) : "";
  const residual=Number(r.residual_m ?? r.gap_m);
  const titles = {ROUTED:"已完成条件图查询",APPROACH_WITH_GAP:"到达邻近路网，仍有缺口",INFERRED_CONDITIONAL_EXTERIOR_REACH:"条件推断到原出口外侧",NO_REGION_GRAPH:"未建立区域图",LOCAL_REUSABLE_REGION_NOT_AVAILABLE:"单线基线无可复用区域"};
  return (titles[r.status] || r.status || (features.length ? "已输出实际折线" : "本变体无此路线"))+distance+
    (residual>0.005?" · 终点余隙 "+length(residual):"");
}
function region(method="I-REGION") {
  return north.regions[method==="I-REGION-NET-ABL"?"I-REGION":method] || [];
}
function bounds(camera) {
  const [x,y,w,h]=camera, ww=w/zoom, hh=h/zoom;
  return [x+(w-ww)/2+offset[0],y+(h-hh)/2+offset[1],ww,hh];
}
function inspect(feature) {
  const p=feature.props, target=el("inspect");
  target.replaceChildren(html("strong",p.region_id||p.source_id||p.native_id||p.id||p.label||scheme[feature.layer][4]));
  const list=html("dl");
  for(const key of ["walkability_state","variant","query_id","sequence","role","area_m2","length_m",
    "decision_reason","evidence_sources","hard_conflicts","assumptions","uncertainty_level","source_status",
    "kind","geometry_kind","status","source_id","source_ids","native_id","tags","S0_status","S1_status","background_overlap_m","wgs84","coordinates",
    "source_node_id","components","endpoint_status","connection_status","reason"]){
    if(p[key]===null || p[key]===undefined || p[key]==="")continue;
    const v=typeof p[key]==="object"?JSON.stringify(p[key]):String(p[key]);
    list.append(html("dt",key),html("dd",v));
  }
  target.append(list);
}
function paint(map,features,box) {
  map.replaceChildren();
  map.setAttribute("viewBox",box.join(" "));
  map.setAttribute("preserveAspectRatio","xMidYMid meet");
  const [x,y,w,h]=box,pixel=w/700;
  map.append(svg("rect",{x,y,width:w,height:h,fill:"#f7f6ef"}));
  const chosen=new Set([...enabled].flatMap(key=>groupBy[key]));
  const ordered = features.filter(f=>f.layer!=="label").concat(features.filter(f=>f.layer==="label"));
  for(const feature of ordered) {
    if(!chosen.has(feature.layer) || !scheme[feature.layer] || (feature.props.near_only && view!=="near"))continue;
    const [fill,stroke,dash,width,label]=scheme[feature.layer],p=feature.props;
    const name=p.region_id||p.source_id||p.native_id||p.id||p.label||label;
    const attrs={"data-layer":feature.layer,"data-name":name};
    if(feature.layer!=="label")Object.assign(attrs,{tabindex:"0",role:"button","aria-label":name+" · "+label});
    const g=svg("g",attrs);
    const title=svg("title",{}); title.textContent=name+" · "+label; g.append(title);
    for(const part of feature.shape) {
      if(part.d) {
        const overlay=feature.layer.startsWith("state-");
        const isOpenArea=feature.layer==="domain";
        const shape=svg("path",{d:part.d,fill:part.area ? fill : "none",stroke,"stroke-width":width,
          "stroke-dasharray":dash,"vector-effect":"non-scaling-stroke","fill-rule":"evenodd",
          "stroke-linecap":"round","stroke-linejoin":"round","fill-opacity":overlay?.66:1});
        if(isOpenArea)shape.setAttribute("pointer-events","stroke");
        g.append(shape);
      }
      if(part.point) {
        const [cx,cy]=part.point;
        if(feature.layer==="label") {
          const t=svg("text",{x:cx,y:cy,fill:stroke,"font-size":11*pixel,"paint-order":"stroke",
            stroke:"#f7f6ef","stroke-width":2.8*pixel,"pointer-events":"none","stroke-linejoin":"round"});
          t.textContent=p.label||name; g.append(t);
        } else {
          const r=(["exit","start","endpoint"].includes(feature.layer)?5:3.4)*pixel;
          g.append(feature.layer==="exit"
            ? svg("rect",{x:cx-r,y:cy-r,width:2*r,height:2*r,fill,stroke,"stroke-width":1.1*pixel})
            : svg("circle",{cx,cy,r,fill,stroke,"stroke-width":1.1*pixel}));
        }
      }
    }
    g.addEventListener("click",()=>inspect(feature));
    g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();inspect(feature);}});
    map.append(g);
  }
  const nice=[.5,1,2,5,10,20,25,50,100,200,500].filter(m=>m<w*.22).at(-1)||.25;
  const sx=x+13*pixel,sy=y+h-14*pixel;
  map.append(svg("rect",{x:sx-4*pixel,y:sy-20*pixel,width:nice+22*pixel,height:26*pixel,fill:"#fffef6","fill-opacity":.9}));
  map.append(svg("path",{d:"M"+sx+","+sy+"h"+nice,stroke:"#254047","stroke-width":2*pixel}));
  for(const [value,tx,ty] of [[nice+" m",sx,sy-4*pixel],["↑ N",x+w-34*pixel,y+20*pixel]]) {
    const t=svg("text",{x:tx,y:ty,"font-size":13*pixel,"font-weight":"700",fill:"#29434b",
      "paint-order":"stroke",stroke:"#fffefa","stroke-width":1.7*pixel});
    t.textContent=value; map.append(t);
  }
}
function select(label,values,current,update) {
  const wrapper=html("label",label+" "), choice=html("select");
  choice.setAttribute("aria-label",label);
  for(const [key,title] of values) {
    const option=html("option",title); option.value=key; option.selected=key===current; choice.append(option);
  }
  choice.addEventListener("change",()=>{update(choice.value);draw();});
  wrapper.append(choice);el("choices").append(wrapper);
}
function metrics(values) {
  el("metrics").replaceChildren(...values.map(([key,value])=>{
    const item=html("span",key+" ");item.className="metric";item.append(html("strong",value));return item;
  }));
}
function details(title, headers, rows) {
  const wrap=html("details"), list=html("div"), table=html("table"), head=html("thead"), body=html("tbody"), tr=html("tr");
  headers.forEach(v=>tr.append(html("th",v)));head.append(tr);
  for(const row of rows) {const line=html("tr"); row.forEach(v=>line.append(html("td",v??"—")));body.append(line);}
  table.append(head,body);list.className="table";list.append(table);wrap.append(html("summary",title),list);el("detail").append(wrap);
}
function legend() {
  el("legend").replaceChildren(...legendLayers[active].map(key=>{
    const [fill,stroke,dash,,label]=scheme[key],item=html("span"), sample=html("i");
    sample.className="swatch";sample.style.background=fill;sample.style.borderTop="2px "+(dash?"dashed":"solid")+" "+stroke;
    item.append(sample,document.createTextNode(label));return item;
  }));
}
function statusMetrics() {
  return [["原生",length(north.areas_m2.NATIVE_WALKABLE||0," m²")],
          ["推断",length(north.areas_m2.INFERRED_WALKABLE||0," m²")],
          ["受限",length(north.areas_m2.RESTRICTED||0," m²")],
          ["未知",length(north.areas_m2.UNKNOWN||0," m²")],
          ["30 m 搜索范围",length(north.window_area_m2," m²")]];
}
function variantRows(query) {
  return north.variants.map(variant=>{
    const records=route(variant,query);
    const layerSum = name=>records.filter(f=>f.layer==="route-"+name).reduce((a,f)=>a+Number(f.props.length_m||0),0);
    const lengths=["native","derived","derived-new","line","inferred","unknown"].map(layerSum);
    const s=summary(variant,query);
    return [variant,s.status || "—",length(lengths.reduce((a,b)=>a+b,0)),...lengths.map(v=>length(v)),length(s.residual_m??s.gap_m)];
  });
}
function caseLabel(id) {
  const s=data.benchmark[id].summary, roles={
    AREA_AND_INTERNAL_LINES_MASKED:"面及内部线遮蔽", LINE_MASK_WITH_RETAINED_SUPPORT:"遮线、保留面",
    LINE_MASK_NO_AREA_SUPPORT:"遮线、无步行面", MAPPED_OBSTACLE_NEGATIVE:"已知障碍负例"
  };
  return id+" · "+(roles[s.case_type]||s.case_type||"真实冻结任务");
}
function draw() {
  el("choices").replaceChildren();el("detail").replaceChildren();
  el("title").textContent=descriptions[active][0];el("intro").textContent=descriptions[active][1];
  el("inspect").textContent="点选区域、接点、路线或底图对象查看来源及判定。";
  let dataset,left,right,common;
  if(active==="grass") {
    dataset=data.semantics;common=dataset.base;[left,right]=dataset.panels;
    metrics([["恢复原生段（六裁片去重）",dataset.restored_count],["固定北侧接点少走",length(dataset.lengths.S0-dataset.lengths.S1)]]);
  } else if(active==="mask"||active==="limits") {
    const candidates=active==="mask"?positives:[...negatives,...limitContext];
    const fallback=candidates[0]||caseIds[0];
    const preferredArea=candidates.includes("W2b809bbe6b8")?"W2b809bbe6b8":candidates.find(id=>caseType(id)==="AREA_AND_INTERNAL_LINES_MASKED");
    const current=active==="mask"?(positiveCase||preferredArea||fallback):(negativeCase||negatives.find(id=>data.benchmark[id].base.some(f=>f.layer==="building")&&data.benchmark[id].base.some(f=>f.layer==="walk-grade"))||fallback);
    if(!current)throw new Error("无受控地图结果");
    select("冻结样例",candidates.map(id=>[id,caseLabel(id)+(active==="limits"&&limitContext.includes(id)?" · 上下文核查，非负例":"")]),current,id=>{if(active==="mask")positiveCase=id;else negativeCase=id;zoom=1;offset=[0,0];});
    dataset=data.benchmark[current];common=dataset.base;
    left={title:"预测可见输入",note:"真实 OSM 观察子集",features:[]};
    right={title:"分类与事后参考",note:caseLabel(current),features:dataset.right};
    const s=dataset.summary,m=s.metrics||{};
    const percent=x=>x==null?"—":(100*x).toFixed(2)+"%";
    const measure = caseType(current).includes("NEGATIVE")
      ? [["冲突面积",length(m.overlap_m2," m²")],["负例误判",m.negative_false_inferred==null?"—":m.negative_false_inferred?"有":"无"]]
      : caseType(current).startsWith("AREA")
        ? [["推断覆盖参考",percent(m.area_recall)],["重叠面积",length(m.overlap_m2," m²")],["参考→推断边界 P90",length(m.reference_boundary_p90_m)]]
        : [["推断覆盖中心线",percent(m.inferred_centerline_coverage)],["原生面辅助覆盖",percent(m.native_assisted_centerline_coverage)]];
    metrics([["任务",current],...measure,["未知占比",percent(m.unknown_fraction)],
      ["有效路线",s.query_count==null?"—":s.route_successes+"/"+s.query_count]]);
    const facts=Object.entries({...s,...m}).filter(([k,v])=>v!==null && ["string","number","boolean"].includes(typeof v) && k!=="case_type");
    details("任务指标与来源",["字段","结果"],[...facts.map(([k,v])=>[k,String(v)]),["参考对象",JSON.stringify(s.source_ids||[])]]);
    details("查询与路线证据",["查询","状态","有效到达","长度","终点余隙"],(s.routes||[]).map(q=>[
      q.query_id,q.status,q.valid_reached?"是":"否",length(q.length_m),length(q.residual_m)]));
    if(m.proxy_widths?.length)details("线宽敏感性 · 评价代理",["中心线缓冲半径","代理面积","推断覆盖"],
      m.proxy_widths.map(w=>[length(w.proxy_buffer_radius_m),length(w.proxy_area_m2," m²"),percent(w.area_recall)]));
  } else {
    dataset=north;common=[...north.base];
    if(active==="pairs") {
      const first=pairLeft||pairs[0], second=pairRight||control||pairs[1]||pairs[0];
      const pairLabel=k=>k?.includes("CONTROL") ? k+" · 区域内部控制" : k+" · 现有接点对";
      const values=pairs.map(k=>[k,pairLabel(k)]);
      select("左图端点对",values,first,id=>{pairLeft=id;});
      select("右图端点对",values,second,id=>{pairRight=id;});
      const routeFor=query=>({
        title:query?pairLabel(query):"无此端点对",note:note("I-REGION",query),
        features:[...region(),...north.domain,...route("I-REGION",query),
          ...focusPoints.filter(p=>p.layer!=="endpoint"||p.props.query_id===query)]
      });
      left=routeFor(first);right=routeFor(second);
      const inferredMeters=query=>route("I-REGION",query).filter(p=>p.layer==="route-inferred").reduce((a,p)=>a+Number(p.props.length_m||0),0);
      metrics([["冻结面 SHA256",(north.summary.surface.sha256||"").slice(0,12)],["可浏览端点对",pairs.length],["使用推断区的端点对",pairs.filter(k=>inferredMeters(k)>.005).length],["外围接点",focusPoints.filter(p=>p.layer==="interface").length]]);
      details("各端点对路线状态",["查询","结果","路线内推断长度"],pairs.map(k=>[k,note("I-REGION",k),length(inferredMeters(k))]));
    } else if(active==="region") {
      left={title:"原生地图与搜索范围",note:"虚线圈只表示研究位置",features:[...north.domain,...focusPoints.filter(p=>p.layer!=="endpoint")]};
      right={title:"分类结果 · I-REGION",note:note("I-REGION",door),
             features:[...region(),...north.domain,...route("I-REGION",door),...focusPoints.filter(p=>p.layer!=="endpoint")]};
      metrics(statusMetrics());
    } else {
      const options=north.variants.map(m=>[m,m]);
      select("左图方法",options,methodLeft,v=>{methodLeft=v;});
      select("右图方法",options,methodRight,v=>{methodRight=v;});
      const byVariant=v=>({title:v,note:note(v,door),
                           features:[...(view==="near"?[...region(v),...north.domain]:[]),...route(v,door),...north.points.filter(p=>p.layer!=="endpoint"&&(!p.props.variant||p.props.variant===v))]});
      left=byVariant(methodLeft);right=byVariant(methodRight);
      metrics([[methodLeft,note(methodLeft,door)],[methodRight,note(methodRight,door)]]);
      details("同一原出口的分层长度对照",["变体","状态","全程","原生","旧面派生","已标面内新图段","单线假设","推断区域","未知","终点余隙"],variantRows(door));
    }
  }
  el("left-title").textContent=left.title;el("right-title").textContent=right.title;
  el("left-note").textContent=left.note;el("right-note").textContent=right.note;
  const extent=bounds(dataset.views[view]);
  paint(el("left-map"),[...common,...left.features],extent);
  paint(el("right-map"),[...common,...right.features],extent);
  legend();
  for(const button of document.querySelectorAll("[data-view]")) button.setAttribute("aria-pressed",String(button.dataset.view===view));
}
function activate() {
  const hash=location.hash.slice(1);
  active=figures.includes(hash)?hash:"grass";view=["grass","route"].includes(active)?"full":"near";zoom=1;offset=[0,0];
  for(const link of document.querySelectorAll("nav a")) link.setAttribute("aria-current",link.dataset.figure===active?"page":"false");
  draw();
}
for(const group of Object.keys(groupBy)) {
  const wrapper=html("label"), input=html("input");input.type="checkbox";input.checked=true;
  input.addEventListener("change",()=>{if(input.checked)enabled.add(group);else enabled.delete(group);draw();});
  wrapper.append(input,document.createTextNode(group));el("layers").append(wrapper);
}
for(const button of document.querySelectorAll("[data-view]")) button.onclick=()=>{view=button.dataset.view;zoom=1;offset=[0,0];draw();};
el("plus").onclick=()=>{zoom=Math.min(7,zoom*1.35);draw();};
el("minus").onclick=()=>{zoom=Math.max(.6,zoom/1.35);draw();};
el("reset").onclick=()=>{zoom=1;offset=[0,0];draw();};
for(const map of [el("left-map"),el("right-map")]){
  let from;
  map.addEventListener("pointerdown",e=>{if(e.button===0)from=[e.clientX,e.clientY];});
  map.addEventListener("pointerleave",()=>{from=null;});
  map.addEventListener("pointerup",e=>{
    if(!from)return;
    const dx=e.clientX-from[0],dy=e.clientY-from[1];from=null;
    if(Math.hypot(dx,dy)<8)return;
    const w=map.viewBox.baseVal.width,scale=w/map.getBoundingClientRect().width;
    offset=[offset[0]-dx*scale,offset[1]-dy*scale];draw();
  });
}
window.addEventListener("hashchange",activate);
if(data.snapshot_time)el("map-source").textContent+=" · 快照 "+data.snapshot_time;
activate();
