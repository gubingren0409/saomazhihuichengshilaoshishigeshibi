"use strict";
const m=JSON.parse(document.getElementById("payload").textContent),$=(s)=>document.querySelector(s);
const NS="http://www.w3.org/2000/svg",maps=[$("#map-left"),$("#map-right")];
const groups={park:"公园场地范围",plaza:"明确步行面",walk:"原生步道与道路",obstacle:"障碍与内环",building:"建筑",corridor:"N2 候选走廊",grade:"未知层级与测距",route:"路线和原出口",labels:"地名标注"};
const state={variant:"N2",view:"near",zoom:1,layers:new Set(Object.keys(groups))};
const style={
 park:["#ecf0db","#87916a",1.3,"4 4","park"],plaza:["#d3eaf5","#608c9b",1.3,null,"plaza"],
 grass:["#d4dfc4","#9bad89",.85,null,"obstacle"],water:["#c9e1e7","#91aebb",.9,null,"obstacle"],
 road:["none","#c5b7a5",1.9,null,"walk"],walk:["none","#637f79",1.2,null,"walk"],crossing:["#7d9593","#fffefa",1,null,"walk"],
 building:["#e7e0d7","#b0a193",.85,null,"building"],target:["#f1dbc2","#997451",1.4,null,"building"],
 fence:["none","#825e52",1.5,"3 2","obstacle"],gate:["#906154","#fffefa",1,null,"obstacle"],obstacle:["#ae907525","#906154",1.4,"3 2","obstacle"],
 search_strip:["none","#a38769",1.1,"5 4","corridor"],corridor:["#f0d6a655","#a16a30",1.5,"5 2","corridor"],
 gap:["none","#687680",1.6,"3 4","grade"],grade:["none","#555663",1.1,"2 3","grade"],grade_point:["#65526e","#fffefa",1.6,null,"grade"],
 native_approach:["none","#23627a",3.4,null,"route"],approach_point:["#23627a","#fffefa",1.8,null,"route"],exit:["#8a4b69","#fffefa",1.8,null,"route"]
};
const order=["park","grass","water","road","plaza","building","target","walk","fence","obstacle","gate","crossing","search_strip","corridor","gap","grade","grade_point"];
const wording={NATIVE_MAPPED_WALKWAY:"原生步行线",DERIVED_FROM_MAPPED_PEDESTRIAN_AREA:"步行面派生",DERIVED_FROM_MAPPED_PARK_AREA:"公园面派生",HYPOTHETICAL_NOT_VERIFIED:"假设 · 未验证",HYPOTHETICAL_CANDIDATE:"假设候选",UNKNOWN:"未知",NO_MAPPED_CONFLICT:"未见已记录冲突",UNKNOWN_NO_CONTINUOUS_LEVEL_HEIGHT_EVIDENCE:"连续楼层与高差未知",ORIGINAL_EXIT_BOUNDARY_TOUCH_ONLY:"仅触出口墙边",REJECTED_OBSTACLE_OR_LEVEL_CONFLICT:"障碍或层级冲突拒绝",NOT_VERIFIED:"未核实"};
const text=(value)=>wording[value]??(value??"—"),fmt=(value)=>value===null||value===undefined||value===""?"—":Number(value).toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2});
function el(name,value){const n=document.createElement(name);if(value!==undefined)n.textContent=value;return n}
function svg(name,attrs={},value){const n=document.createElementNS(NS,name);for(const [k,v] of Object.entries(attrs))if(v!==null&&v!==undefined)n.setAttribute(k,v);if(value!==undefined)n.textContent=value;return n}
function point(p,r,a,rect=false){return rect?svg("rect",{x:p[0]-r,y:p[1]-r,width:2*r,height:2*r,...a}):svg("circle",{cx:p[0],cy:p[1],r,...a})}
function label(x,y,size,value,anchor="start"){return svg("text",{x,y,"font-size":size,"text-anchor":anchor,"font-weight":650,class:"label"},value)}
function inspect(p,group){
 const n=$("#inspector"),identity=p.native_id??p.source_id??p.role??group;
 n.replaceChildren(el("strong",identity+"　"+(groups[group]??group)));
 for(const [k,v] of [["标签",p.tags],["证据",p.evidence_status],["源语义",p.source_scope_grade],["楼层",p.level_status],["障碍",p.obstacle_status],["拓扑",p.topology_status]]){
  if(v===null||v===undefined)continue;
  n.append(document.createTextNode("　"+k+" "),el("code",typeof v==="object"?JSON.stringify(v):text(v)));
 }
}
function drawFeature(target,f,w,pattern){
 const {layer,shape,props:p}=f;
 const spec=layer==="connector"?["none",p.variant==="N1"?"#83426c":"#ac501a",4,p.variant==="N1"?"9 4":"3 4","route"]:style[layer];
 if(!spec)return;
 const [fill,stroke,weight,dash,group]=spec,g=target.get(group);
 const n=svg("g",{class:"feature","data-feature":layer,"data-variant":p.variant});
 n.append(svg("title",{},String(p.native_id??p.source_id??p.role??layer)));
 n.addEventListener("click",()=>inspect(p,group));
 if(["connector","corridor","approach_point","exit","grade_point"].includes(layer)){
  n.setAttribute("tabindex","0");n.setAttribute("role","button");n.setAttribute("aria-label",String(p.native_id??p.source_id??p.role??layer));
  n.addEventListener("keydown",(e)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();inspect(p,group)}});
 }
 const a={fill,stroke,"stroke-width":weight,"stroke-dasharray":dash,"stroke-linejoin":"round","stroke-linecap":"round","vector-effect":"non-scaling-stroke","fill-rule":"evenodd"};
 for(const part of shape){
  if(part.d){
   if(["native_approach","connector"].includes(layer))n.append(svg("path",{d:part.d,...a,stroke:"#fffefa","stroke-width":weight+2.5,"stroke-dasharray":null}));
   n.append(svg("path",{d:part.d,...a}));
   if(layer==="corridor"&&state.layers.has("grade"))n.append(svg("path",{d:part.d,fill:"url(#"+pattern+")","fill-rule":"evenodd","pointer-events":"none"}));
  }
  if(part.point){
   n.append(point(part.point,["gate","crossing"].includes(layer)?w*.003:w*.009,a,["exit","grade_point"].includes(layer)));
   if(layer==="grade_point"&&state.view==="near")n.append(label(part.point[0]+w*.017,part.point[1]+w*.019,w*.020,p.label));
  }
 }
 g.append(n);
}
function box(){const [x,y,w,h]=m.viewboxes[state.view],z=state.zoom;return [x+w*(1-z)/2,y+h*(1-z)/2,w*z,h*z]}
function decorate(map,[x,y,w,h],variant){
 const s=w*.023, [ax,ay]=m.points.snap,[dx,dy]=m.points.exit;
 if(state.layers.has("route")){
  if(state.view==="near"){
   map.append(label(ax-w*.024,ay-w*.019,s,"原网末点","end"),label(dx+w*.022,dy+w*.027,s,"西北出口 · exit"));
   if(variant!=="N0"&&m.variants[variant].connector_m!==null)map.append(label((ax+dx)/2+w*.037,(ay+dy)/2-w*.043,s*.95,fmt(m.variants[variant].connector_m)+" 米 · 假设"));
  }else{
   const [sx,sy]=m.points.start;map.append(point([sx,sy],w*.007,{fill:"#fffefa",stroke:"#23627a","stroke-width":2,"vector-effect":"non-scaling-stroke"}),label(sx+w*.015,sy-w*.015,s,"冻结起点"),label(dx+w*.017,dy-w*.016,s,"西北出口 · exit"));
  }
 }
 const scale=[100,50,20,10,5,2,1].find(d=>d<=w*.24)??1,bx=x+w*.055,by=y+h*.923;
 map.append(svg("path",{d:"M"+bx+","+by+"h"+scale,stroke:"#23363f","stroke-width":2.3,"vector-effect":"non-scaling-stroke"}),label(bx,by-h*.025,s*.78,scale+" 米"),label(x+w*.95,y+h*.092,s,"↑ 北","end"));
}
function draw(map,variant,i){
 const area=box(),w=area[2],pattern="hatch-"+i;
 map.setAttribute("viewBox",area.join(" "));map.replaceChildren();
 const defs=svg("defs"),h=svg("pattern",{id:pattern,patternUnits:"userSpaceOnUse",width:1,height:1,patternTransform:"rotate(40)"});
 h.append(svg("path",{d:"M0 0v1",stroke:"#83592c","stroke-opacity":.57,"stroke-width":.12}));defs.append(h);map.append(defs);
 const target=new Map();
 for(const key of ["park","obstacle","walk","plaza","building","corridor","grade","labels","route"]){
  const group=svg("g",{"data-layer":key});group.style.display=state.layers.has(key)?"":"none";target.set(key,group);map.append(group);
 }
 for(const layer of order){
  if((layer==="corridor"||layer==="search_strip")&&variant!=="N2")continue;
  if(layer==="gap"&&variant!=="N0")continue;
  for(const f of m.features)if(f.layer===layer)drawFeature(target,f,w,pattern);
 }
 for(const f of m.features)if(f.layer.endsWith("_label")&&state.view==="full")for(const part of f.shape)if(part.point)target.get("labels").append(label(...part.point,w*.019,f.props.label??""));
 const prefix=m.route_features.find(f=>f.layer==="native_approach"&&f.props.variant==="N0")??m.route_features.find(f=>f.layer==="native_approach");
 if(prefix)drawFeature(target,prefix,w,pattern);
 for(const f of m.route_features){
  if(f.layer==="connector"&&f.props.variant===variant)drawFeature(target,f,w,pattern);
  if(["approach_point","exit"].includes(f.layer)&&(!f.props.variant||f.props.variant==="N0"))drawFeature(target,f,w,pattern);
 }
 decorate(map,area,variant);
}
function refresh(){
 for(const [i,v] of ["N0",state.variant].entries()){
  const result=m.variants[v],map=maps[i],card=map.closest(".pane");
  card.querySelector("h3").textContent=v+" · "+m.case_labels[v];
  card.querySelector("p").textContent=fmt(result.length_m)+" 米全程  ·  门前 "+fmt(result.connector_m)+" 米  ·  距原出口 "+fmt(result.residual_m)+" 米";
  map.setAttribute("aria-label",v+" "+m.case_labels[v]+"地图");draw(map,v,i);
 }
 for(const b of document.querySelectorAll("button[data-variant]"))b.setAttribute("aria-pressed",String(b.dataset.variant===state.variant));
 for(const b of document.querySelectorAll("button[data-view]"))b.setAttribute("aria-pressed",String(b.dataset.view===state.view));
}
function table(rows,columns,where){
 const t=el("table"),head=el("thead"),hr=el("tr"),body=el("tbody");
 for(const [,title] of columns)hr.append(el("th",title));head.append(hr);t.append(head);
 for(const r of rows){const tr=el("tr");for(const [key] of columns)tr.append(el("td",text(r[key])));body.append(tr)}
 if(!rows.length){const tr=el("tr"),td=el("td","无此类记录");td.colSpan=columns.length;tr.append(td);body.append(tr)}
 t.append(body);$(where).replaceChildren(t);
}
function chart(rows,where){
 const h=44+rows.length*23,plot=svg("svg",{viewBox:[0,0,750,h].join(" "),class:"figure","aria-label":"门前连接长度（米）"});
 const axis=180,max=Math.max(1,...rows.map(r=>Number(r.connector_m)))*1.12;
 plot.append(svg("path",{d:"M"+axis+",19v"+(h-28),stroke:"#bdc8c8"}),svg("text",{x:axis-6,y:13,"text-anchor":"end"},"0 米"));
 rows.forEach((r,i)=>{
  const y=30+i*23;
  plot.append(svg("text",{x:6,y:y+4},r.id));
  if(r.connector_m===null||r.connector_m===undefined){plot.append(svg("text",{x:axis+12,y:y+4},"无候选"));return}
  const end=axis+Number(r.connector_m)/max*460,color=r.id.startsWith("N1")?"#83426c":"#ac501a";
  plot.append(svg("path",{d:"M"+axis+","+y+"H"+end,stroke:color,"stroke-width":2.5,"stroke-dasharray":r.id.startsWith("N1")?"9 4":"3 4"}),svg("circle",{cx:end,cy:y,r:4,fill:color}),svg("text",{x:end+11,y:y+4},fmt(r.connector_m)+" 米"));
 });
 $(where).replaceChildren(plot);
}
for(const [v,r] of Object.entries(m.variants)){
 const card=el("article");card.append(el("small",v+" · "+m.case_labels[v]),el("strong",fmt(r.length_m)+" 米"),el("p","距登记出口 "+fmt(r.residual_m)+" 米"+(v==="N0"?"，原网":"，假设路线")));$("#overview").append(card);
}
$("#frontage").textContent="候选段 "+fmt(m.variants.N1.connector_m)+" 米。公园场地覆盖 "+fmt(m.source_geometry.park_coverage_m)+" 米，明确步行线或步行面覆盖 "+fmt(m.source_geometry.explicit_walkway_coverage_m)+" 米。"+(m.comparison.same_connector_geometry?"N2 受约束计算得到与 N1 相同的门前线。":"各变体按实际几何绘制。")+" 原出口 node/6897145227，entrance=exit，入馆不适用。坐标 ["+m.exit_coord.join(", ")+"]。";
for(const [key,value] of Object.entries(groups)){
 const wrap=el("label"),input=el("input");input.type="checkbox";input.checked=true;input.dataset.toggle=key;
 input.addEventListener("change",()=>{if(input.checked)state.layers.add(key);else state.layers.delete(key);refresh()});
 wrap.append(input,document.createTextNode(value));$("#layers").append(wrap);
}
for(const b of document.querySelectorAll("button[data-variant]"))b.addEventListener("click",()=>{state.variant=b.dataset.variant;refresh()});
for(const b of document.querySelectorAll("button[data-view]"))b.addEventListener("click",()=>{state.view=b.dataset.view;state.zoom=1;refresh()});
$("#zoom-in").addEventListener("click",()=>{state.zoom=Math.max(.28,state.zoom*.75);refresh()});
$("#zoom-out").addEventListener("click",()=>{state.zoom=Math.min(3,state.zoom/.75);refresh()});
$("#reset").addEventListener("click",()=>{state.zoom=1;refresh()});
const segments=[["variant","变体"],["section","路段"],["source_ids","源对象"],["length_m","米"],["evidence_status","证据等级"],["source_scope_grade","来源语义"],["walkability_status","步行语义"],["obstacle_status","障碍"],["level_status","楼层"],["topology_status","拓扑"]];
table(m.evidence.segments.filter(r=>!String(r.section).toLowerCase().includes("native")),segments,"#connector-rows");
table(m.evidence.segments,segments,"#all-rows");
table(m.evidence.obstacles.filter(r=>!String(r.section).toLowerCase().includes("native")),[["variant","变体"],["source_id","源对象"],["source_kind","类别"],["contact_type","接触几何"],["intersection_m","相交米数"],["status","障碍核验"]],"#obstacle-rows");
table(m.evidence.levels.filter(r=>!String(r.section).toLowerCase().includes("native")),[["variant","变体"],["source_id","源对象"],["tags","原标签"],["relation","空间关系"],["distance_m","距离 m"],["level_status","楼层核验"]],"#level-rows");
chart([{id:"N1 直线假设",connector_m:m.variants.N1.connector_m},{id:"N2 主设定",connector_m:m.variants.N2.connector_m}],"#strip");
chart(m.sensitivities,"#sensitivity-chart");
table(m.sensitivities,[["id","配置"],["radius_m","范围 m"],["half_width_m","半宽 m"],["obstacle_clearance_m","障碍余量 m"],["corridor_area_m2","域面积 m²"],["status","状态"],["connector_m","门前段 m"],["length_m","全程 m"],["level_status","楼层"],["evidence_status","证据等级"]],"#sensitivity-rows");
refresh();
