"use strict";
const NS="http://www.w3.org/2000/svg";
const LABELS={
  H:"H 强遮蔽",G:"G 局部几何缺失",S:"S 语义缺失",N:"N 障碍反例",H0:"H0 历史导出",NATURAL:"自然缺标"
};
const C={
  park:["#e2eadb","#a1b59b",.65],plaza:["#d9ebed","#8baeb2",.7],grass:["#cfe0c4","#9cac89",.6],
  water:["#c9e0ec","#7dabbf",.9],building:["#e9e2d4","#9f9380",.65],
  road:["none","#bbb6a9",1.4,"5 3"],way:["none","#456870",1.28],
  obstacle:["#e5c6c3","#9b625f",1.15],continuation:["none","#147a73",2.6,"5 2"],
  "score-domain":["none","#33546a",1.45,"5 3"],"source-boundary":["none","#33455d",1.2,"3 3"],"mask-domain":["none","#994f7e",1.5,"4 4"],
  "state-native":["#69a8b6","#508c9b",.65],"state-inferred":["#70c397","#326f55",.7],
  "state-restricted":["#db9a91","#ae746e",.65],"state-unknown":["#eedbb0","#af9b66",.65],
  "route-native":["none","#215970",2.8],"route-inferred":["none","#94452d",3,"5 2"],
  "route-derived":["none","#6b5895",2.8,"5 3"],"route-unknown":["none","#775840",2.5,"2 3"],
  "base-route":["none","#575767",1.9,"2 3"],reference:["#e2add7","#983e80",2.1,"7 3"],
  cell:["#fff","#226759",.5]
};
const TAB={
  context:["A · 街区上下文与局部细节","左图保留 160 米街区视野，右图显示固定 30 米预测／评分域。灰层只供人工阅读，与观察圈相交的合法原生面可按合同保留完整几何。"],
  mask:["B · 同目标、不同遮蔽","左右使用相同街区视野与名义观察半径。青色加粗标示 G 保留而 H 删除的外部道路延续。历史 H0 只提供名义 40 米，参考默认关闭。"],
  method:["C · 同输入、M0 与 M1","左右使用同一任务、同一观察、同一 30 米域。点击格片查看是否引用外围拓扑对象。"],
  business:["D · 业务与失败案例","固定入口包括北门自然缺标、原零路网、原单路段、中心线和已知障碍。没有参考的北门只展示条件结果。"]
};
const LEGEND={
  road:"人工背景机动车线",way:"可见步行线",continuation:"G 保留的延续",clip:"观察裁切", "mask-end":"遮蔽切点",
  "source-limit":"原裁片边缘", "source-boundary":"冻结来源覆盖边界", "context-circle":"观察圈","score-domain":"30 m 预测／评分圈","mask-domain":"声明的遮蔽边界",
  "state-native":"原生","state-inferred":"推断","state-restricted":"受限","state-unknown":"未知",
  "route-native":"原生路线","route-derived":"面派生路线","route-inferred":"推断路线","route-unknown":"未知接缝","base-route":"无推断基线",
  reference:"独立参考",exit:"登记出口"
};
const state={tab:"context",task:null,radius:"160",mode:"H",other:"H",method:"M1",query:"",focus:null,zoom:1,full:false};
const $=id=>document.getElementById(id);
const s=(name, attrs={})=>{const el=document.createElementNS(NS,name);for(const [k,v] of Object.entries(attrs)){if(v!==null&&v!==undefined)el.setAttribute(k,v);}return el};
const n=(tag, text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el};
let D;
let views=[];
let exportMeta;

async function load(){
  const bytes=Uint8Array.from(atob($("payload").textContent.trim()),x=>x.charCodeAt(0));
  const body=new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(body).text());
}
const human=(x,d=0)=>Number.isFinite(x)?x.toLocaleString("zh-CN",{maximumFractionDigits:d,minimumFractionDigits:d}):"—";
const frac=x=>Number.isFinite(x)?human(x*100,2)+"%":"—";
const selected=(case_,mode,radius)=>case_.inputs[mode]?.[radius]||null;
const radii=(case_, mode)=>Object.keys(case_.inputs[mode]||{}).sort((a,b)=>+a-+b);
const methodOf=(item,m)=>Number.isInteger(item?.models?.[m])?D.models[item.models[m]]:null;
function options(select, values, value){
  select.replaceChildren(...values.map(([k,v])=>{const x=n("option",v);x.value=k;return x}));
  if(values.some(([k])=>String(k)===String(value)))select.value=value;
  select.disabled=values.length<=1;
  return select.value;
}
function caseLabel(item){
  const known={sh_library:"图书馆","sh-library":"上海图书馆","sh-newworld":"新世界","sh-huangpu-01":"上海博物馆周边",
    "sh-tower":"上海中心周边","sh-wukang":"武康路周边"};
  const suffix=item.parent===D.preset[0]?" · 原零路网":item.parent===D.preset[1]?" · 原单路段":
    item.label==="NEGATIVE"?" · 障碍反例":item.label==="NATURAL"?" · 自然缺标":"";
  return (known[item.group]||item.group||"")+" · "+item.parent+suffix;
}
function rootCase(){
  const ids=Object.keys(D.cases);
  return D.cases[state.task]||D.cases[D.preset.find(x=>D.cases[x])]||D.cases[ids[0]];
}
function chooseTask(id){
  if(!D.cases[id])return;
  state.task=id;
  state.mode=Object.hasOwn(D.cases[id].inputs,"H")?"H":Object.keys(D.cases[id].inputs)[0];
  state.other="H";
  state.focus=null;
  state.zoom=1;
  state.full=false;
  state.query="";
  $("ref-toggle").checked=false;
  render();
}
function activation(){
  const tab=location.hash.slice(1);
  const old=state.tab;
  state.tab=Object.hasOwn(TAB,tab)?tab:"context";
  for(const a of document.querySelectorAll("[data-tab]")){
    if(a.dataset.tab===state.tab)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
  }
  state.zoom=1;state.focus=null;state.full=false;$("ref-toggle").checked=false;
  if(old!==state.tab&&state.tab==="business"&&D.natural)chooseTask(D.natural);
  else if(old!==state.tab&&state.tab==="mask"&&rootCase().label==="NATURAL")chooseTask(D.preset.find(x=>D.cases[x])||Object.keys(D.cases)[0]);
  else render();
}
function statusRoute(m,query,base=false){return (base?m?.base_routes:m?.routes)?.[query]||null}
function metaFor(item,m,query){
  if(!item)return "这个模式在本任务没有可核验观察。";
  const meta=[item.old?"历史 40 m 对象选取，未按新合同裁线":"观察 "+item.radius+" m",item.counts.arcs+" 条有向边"];
  if(item.counts.derived_arcs_aggregated_for_display)meta.push("旧面派生网以原面概绘");
  if(m){
    meta.push("固定 30 m");
    const r=statusRoute(m,query);
    const check=m.route_audit?.[query];
    if(r)meta.push(check&&r.reached&&!check.valid_reached?"路线未通过评分核对":
      r.reached?"所选查询条件到达 "+human(r.length_m,2)+" m":"所选查询 "+(r.status||"未接通"));
  }
  return meta.join(" · ");
}
function makeLegend(){
  const items=Object.entries(LEGEND);
  $("legend").replaceChildren(...items.map(([id,title])=>{
    const x=n("span"), box=n("i");box.className="swatch";
    const color=C[id];
    box.style.background=(color?.[0]&&color[0]!=="none")?color[0]:"transparent";
    const extra={"context-circle":"#467577",clip:"#456870","mask-end":"#994f7e","source-limit":"#313d52",exit:"#682e56"};
    box.style.borderBottom="2px "+(color?.[3]||id==="context-circle"?"dashed":"solid")+" "+(color?.[1]||extra[id]||"#56696b");
    x.append(box,n("span",title));
    return x;
  }));
}
function fixedView(w,h,z=1,focus=null){
  const cx=focus?.[0]||0,cy=focus?.[1]||0;
  return [cx-w/(2*z),cy-h/(2*z),w/z,h/z];
}
function feature(f, svg, width, options={}){
  if(!f)return;
  const props=f.props||{};
  const isLabel=f.layer==="label";
  const isCell=f.layer==="cell";
  const visibility=options.ghost?"human-background":f.layer==="reference"||props.observation==="AUDIT_ONLY_EXACT_MASK"?"evaluation-only":
    isCell||f.layer.startsWith("state-")||f.layer.startsWith("route-")||f.layer==="base-route"?"run-output":
    f.layer.endsWith("domain")||f.layer==="source-boundary"?"review-metadata":"prediction-visible";
  const group=s("g",{"data-layer":f.layer,"data-name":props.region_id||props.source_id||props.id||props.label||"",
    "data-visibility":visibility,"data-outer-witness":props.context_witnesses?.length?"true":null});
  if(options.ghost)group.setAttribute("opacity",.25);
  if(!options.ghost&&!isLabel){
    group.setAttribute("tabindex","0");
    group.setAttribute("role","button");
    group.setAttribute("aria-label",props.region_id||props.source_id||props.id||f.layer);
    group.addEventListener("keydown",ev=>{if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();inspect(f);}});
  }
  if(options.ghost)group.setAttribute("pointer-events","none");
  for(const p of f.shape){
    if(p.point){
      const [x,y]=p.point, scale=width/350;
      if(isLabel){
        const t=s("text",{x,y,fill:props.observation==="DISPLAY_ONLY_MOTOR_ROAD"?"#746b5a":"#334a4d",
          "font-size":Math.max(scale*6.2,.72),stroke:"#f7f5ed","stroke-width":Math.max(scale*1.1,.18),"paint-order":"stroke",
          "text-anchor":"middle","font-family":"Microsoft YaHei, sans-serif"});
        t.textContent=props.label||"";
        group.append(t);
      }else{
        const r=Math.max(scale*(f.layer==="exit"?2.7:1.65),.32);
        if(f.layer==="clip")group.append(s("path",{d:"M"+x+","+(y-r)+"L"+(x+r)+","+y+"L"+x+","+(y+r)+"L"+(x-r)+","+y+"Z",
          fill:"#fff",stroke:"#405e6a","stroke-width":1,"vector-effect":"non-scaling-stroke"}));
        else if(f.layer==="mask-end"||f.layer==="source-limit")group.append(s("rect",{x:x-r,y:y-r,width:r*2,height:r*2,
          fill:f.layer==="mask-end"?"#b8799e":"#344961",stroke:"#fff","stroke-width":.8,"vector-effect":"non-scaling-stroke"}));
        else group.append(s("circle",{cx:x,cy:y,r,fill:f.layer==="exit"?"#672a53":"#236673",stroke:"#fff",
          "stroke-width":1.1,"vector-effect":"non-scaling-stroke"}));
      }
    }
    if(p.d){
      const style=C[f.layer]||["none","#646c65",1.2];
      let fill=p.area?style[0]:"none";
      if(f.layer.endsWith("domain"))fill="none";
      group.append(s("path",{d:p.d,fill,stroke:style[1],"stroke-width":style[2],"stroke-dasharray":style[3],
        "fill-rule":"evenodd","stroke-linejoin":"round","stroke-linecap":"round","vector-effect":"non-scaling-stroke",
        "fill-opacity":isCell?.005:(f.layer==="reference"?.19:f.layer.startsWith("state-")?.78:.84),
        "stroke-opacity":isCell?.22:1}));
    }
  }
  if(!options.ghost&&!isLabel)group.addEventListener("click",ev=>{focusPoint(ev,svg);inspect(f);ev.stopPropagation();});
  const title=s("title");title.textContent=(props.source_id||props.id||props.region_id||f.layer)+
    (props.observation?" · "+props.observation:"");group.append(title);
  (options.parent||svg).append(group);
}
function inspect(f){
  const p=f.props||{};
  for(const obj of document.querySelectorAll("svg .evidence-focus"))obj.classList.remove("evidence-focus");
  if(f.layer==="cell"&&Array.isArray(p.evidence_sources)){
    const ids=new Set(p.evidence_sources);
    for(const obj of document.querySelectorAll("svg [data-name]"))if(ids.has(obj.dataset.name)&&obj.dataset.visibility==="prediction-visible")obj.classList.add("evidence-focus");
  }
  $("inspect").replaceChildren(n("strong",p.region_id||p.source_id||p.id||p.label||LEGEND[f.layer]||f.layer));
  const dl=n("dl");
  for(const [k,v] of Object.entries(p)){
    if(v===null||v===undefined||k==="label")continue;
    dl.append(n("dt",k),n("dd",typeof v==="object"?JSON.stringify(v):String(v)));
  }
  $("inspect").append(dl);
}
function focusPoint(event,svg){
  const pt=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
  state.focus=[pt.x,pt.y];
  updateCrosshair();
}
function updateCrosshair(){
  for(const {svg,box} of views){
    svg.querySelector(".link-crosshair")?.remove();
    if(!state.focus)continue;
    const [x,y]=state.focus,[ax,ay,w,h]=box;
    if(x<ax||x>ax+w||y<ay||y>ay+h)continue;
    const len=w/65, g=s("g",{class:"link-crosshair","pointer-events":"none"});
    g.append(s("path",{d:"M"+(x-len)+","+y+"H"+(x+len)+"M"+x+","+(y-len)+"V"+(y+len),
      fill:"none",stroke:"#922b64","stroke-width":1.3,"vector-effect":"non-scaling-stroke"}));
    svg.append(g);
  }
}
function contextCircle(svg,item){
  const radius=item.radius;
  const rings=(item.context_outline||[]).map(p=>p.d).filter(Boolean);
  const attrs={fill:"none",stroke:"#477477","stroke-width":1.5,
    "stroke-dasharray":"7 4","vector-effect":"non-scaling-stroke","data-layer":"context-circle",
    "data-radius":radius,"pointer-events":"none"};
  svg.append(rings.length?s("path",{d:rings.join(" "),...attrs}):s("circle",{cx:0,cy:0,r:radius,...attrs}));
}
function scale(svg,box,local){
  const [x,y,w,h]=box,pad=w*.025;
  const steps=local?[5,10,20,30]:[20,40,80,120];
  const len=steps.reduce((old,a)=>a<=w*.23?a:old,local?5:20);
  const g=s("g",{"pointer-events":"none","data-layer":"scale"});
  g.append(s("rect",{x:x+pad*.6,y:y+h-pad*3.1,width:len+pad*1.6,height:pad*2.62,fill:"#fffdf4",opacity:.9}),
    s("path",{d:"M"+(x+pad)+","+(y+h-pad*.82)+"h"+len,stroke:"#263f42","stroke-width":2,
      "vector-effect":"non-scaling-stroke"}));
  const t=s("text",{x:x+pad,y:y+h-pad*1.22,"font-size":pad*.9,"font-family":"Microsoft YaHei, sans-serif",
    fill:"#243f43","font-weight":"600"});
  t.textContent=len+" m";g.append(t);
  const compass=s("text",{x:x+w-pad*2.35,y:y+pad*1.65,"font-size":pad*1.05,fill:"#23464b",
    "font-family":"Microsoft YaHei, sans-serif","font-weight":"600"});
  compass.textContent="↑ N";g.append(compass);svg.append(g);
}
function map(side, case_, item, model, local){
  const svg=$(side+"-map");
  const focus=state.zoom===1||local&&state.focus&&Math.hypot(...state.focus)>30?null:state.focus;
  let box=fixedView(local?70:350,local?66:350,state.zoom,focus);
  const route=statusRoute(model,state.query);
  const full=side==="left"&&state.full&&case_.label==="NATURAL"&&route?.extent;
  if(full){
    const a=route.extent,b=[Math.min(a[0],-175),Math.min(a[1],-175),Math.max(a[2],175),Math.max(a[3],175)];
    const x=b[0]-16,y=b[1]-16;
    box=[x,y,b[2]-x+16,b[3]-y+16];
  }
  views.push({svg,box});
  svg.replaceChildren();
  svg.setAttribute("viewBox",box.join(" "));
  svg.setAttribute("data-extent",local?"local-30m":full?"full-route":"context-160m");
  svg.setAttribute("data-observed",item?.id||"");
  svg.setAttribute("data-state-sha256",model?.sha256||"");
  svg.onclick=event=>{if(item)focusPoint(event,svg)};
  svg.append(s("rect",{x:box[0],y:box[1],width:box[2],height:box[3],fill:"#f7f6ef"}));
  if(!item){scale(svg,box,local);return}
  const outside=selected(case_,item.mode,"160");
  if($("gray-toggle").checked&&!local&&outside&&item.radius<160){
    const id="outside-"+side;
    const clip=s("clipPath",{id});
    const r=item.radius, outline=(item.context_outline||[]).map(p=>p.d).filter(Boolean).join(" ");
    const circle="M-"+r+",0 A"+r+","+r+" 0 1 0 "+r+",0 A"+r+","+r+" 0 1 0 -"+r+",0 Z";
    const d="M-500,-500H500V500H-500Z "+(outline||circle);
    clip.append(s("path",{d,"clip-rule":"evenodd","fill-rule":"evenodd"}));
    const defs=s("defs");defs.append(clip);svg.append(defs);
    const group=s("g",{"clip-path":"url(#"+id+")","data-layer":"unobserved-context","aria-label":"圈外人工背景，预测不可见"});svg.append(group);
    for(const f of outside.visible)feature(f,svg,box[2],{ghost:true,parent:group});
  }
  for(const f of item.visible)if(!["way","label","clip","mask-end","source-limit","exit","endpoint"].includes(f.layer))feature(f,svg,box[2]);
  if($("gray-toggle").checked)for(const f of case_.context_road)feature(f,svg,box[2],{ghost:true});
  if($("region-toggle").checked&&model){
    for(const f of model.states)feature(f,svg,box[2]);
    if(local)for(const f of model.cells){
      const links=f.props.context_witnesses;
      const detail=links?.map(id=>model.witnesses[id]).filter(Boolean);
      feature(detail?.length?{...f,props:{...f.props,actual_outer_witnesses:detail}}:f,svg,box[2]);
    }
  }
  for(const f of item.visible)if(["way","label","clip","mask-end","source-limit","exit","endpoint"].includes(f.layer))feature(f,svg,box[2]);
  if(state.tab==="mask")for(const f of item.restored||[])feature(f,svg,box[2]);
  if(!local)contextCircle(svg,item);
  feature(case_.window,svg,box[2]);
  feature(item.source_boundary,svg,box[2]);
  feature(item.mask_scope,svg,box[2]);
  if($("ref-toggle").checked){feature(item.mask_reveal,svg,box[2]);feature(case_.reference,svg,box[2]);}
  if($("base-toggle").checked)for(const f of statusRoute(model,state.query,true)?.lines||[])feature({...f,layer:"base-route"},svg,box[2]);
  if($("route-toggle").checked)for(const f of statusRoute(model,state.query)?.lines||[])feature(f,svg,box[2]);
  for(const f of case_.queries[state.query]||[])feature(f,svg,box[2]);
  scale(svg,box,local);
}
function pill(caption,value){
  const x=n("span");x.className="pill";x.append(n("span",caption+" "),n("strong",value));return x;
}
function stats(case_,item,left,right){
  const list=[];
  if(item){
    const c=item.counts;
    list.push(pill("可见节点／有向边",human(c.nodes)+" / "+human(c.arcs)),pill("可见步行线",human(c.road_length_m,1)+" m"),
      pill("裁切／遮蔽切点",human(c.cuts)+" / "+human(c.mask_cuts)),pill("评价域","30 m · 1 m"));
    const inv=item.inventory||{};
    const comps=inv.component_count??inv.components??inv.network_components??inv.weak_components;
    if(Number.isFinite(comps))list.push(pill("可见组件",human(comps)));
    if(item.restored?.length)list.push(pill("保留的历史删除段",human(item.restored.length)+" 条 · "+human(inv.restored_legal_outer_length_m,1)+" m"));
  }
  if(left&&right&&state.tab==="method"){
    list.push(pill("M0 → M1 推断面积",human(left.area.INFERRED_WALKABLE,2)+" → "+human(right.area.INFERRED_WALKABLE,2)+" m²"),
      pill("M1 新判格片",human(right.features.changed_cells)));
    if(Number.isFinite(left.metrics.area_recall)&&Number.isFinite(right.metrics.area_recall))
      list.push(pill("固定域面积覆盖",frac(left.metrics.area_recall)+" → "+frac(right.metrics.area_recall)));
    if(Number.isFinite(left.metrics.line_recall)&&Number.isFinite(right.metrics.line_recall))
      list.push(pill("固定域中心线覆盖",frac(left.metrics.line_recall)+" → "+frac(right.metrics.line_recall)));
  }
  if(right&&!(left&&state.tab==="method")){
    const m=right.metrics;
    list.push(pill("推断",human(right.area.INFERRED_WALKABLE,2)+" m²"),pill("未知",human(right.area.UNKNOWN,2)+" m²"));
    if(Number.isFinite(m.area_recall))list.push(pill("固定域面积覆盖",frac(m.area_recall)));
    if(Number.isFinite(m.line_recall))list.push(pill("固定域中心线覆盖",frac(m.line_recall)));
  }
  $("measure").replaceChildren(...list);
  const details=n("details"), title=n("summary","输入与计分账 · 固定对象、范围和方法");
  details.append(title);
  const table=n("table"), head=n("tr");for(const t of ["核对项","当前观察／结果"])head.append(n("th",t));table.append(head);
  const rows=[
    ["任务",case_.parent+" · "+case_.kind+" · "+case_.split],
    ["遮蔽合同",item?.mode+" · "+(item?.mask_basis||"未提供")+" · "+(item?.mask_sha256||"不适用／未提供")],
    ["语义缺失适用性",JSON.stringify(D.semantic_status||"未声明")],
    ["预测与评分",item?.evaluation_sha256||"固定 30 m"],
    ["观察输入",item?.observed_sha256||"未提供"],
    ["独立参考",item?.reference_sha256||"本任务无独立参考"],
    ["上下文账",item?JSON.stringify(item.inventory):"无"],
    ["左图冻结表面",left?.sha256||"仅观察"],
    ["右图冻结表面",right?.sha256||"未运行或仅观察"],
    ["右图计分",right?JSON.stringify(right.metrics):"无"],
    ["外围特征",right?JSON.stringify(right.features):"无"]
  ];
  for(const [k,v] of rows){const tr=n("tr");tr.append(n("td",k),n("td",String(v)));table.append(tr)}
  details.append(table);
  const sizes=n("table"), sizeHead=n("tr");
  for(const label of ["同遮蔽观察","节点／弧","组件","30 m 域外步行线","冻结来源覆盖","有推断后新接通"]){sizeHead.append(n("th",label))}
  sizes.append(sizeHead);
  for(const [radius, current] of Object.entries(case_.inputs[state.mode]||{})){
    const r=n("tr"), inv=current.inventory;
    const computed=methodOf(current,state.method)?.metrics||{};
    for(const v of [radius+" m",current.counts.nodes+" / "+current.counts.arcs,human(inv.component_count),
      human(inv.road_length_outside_fixed_domain_m,1)+" m",frac(inv.source_available_fraction),
      human(computed.route_new_with_inference)])r.append(n("td",v));
    sizes.append(r);
  }
  $("detail").replaceChildren(sizes,details);
}
function render(){
  const case_=rootCase();
  state.task=case_.parent;
  const cases=Object.values(D.cases).map(x=>[x.parent,caseLabel(x)]);
  options($("case"),cases,state.task);
  const modes=Object.keys(case_.inputs).sort((a,b)=>["H","G","S","N","H0","NATURAL"].indexOf(a)-["H","G","S","N","H0","NATURAL"].indexOf(b));
  state.mode=options($("mode"),modes.map(k=>[k,LABELS[k]||k]),state.mode);
  const available=radii(case_,state.mode);
  if(!available.includes(state.radius))state.radius=available.at(-1);
  state.radius=options($("radius"),available.map(x=>[x,x+" 米"]),state.radius);
  const item=selected(case_,state.mode,state.radius);
  const methods=Object.keys(item?.models||{});
  if(!methods.includes(state.method))state.method=methods.includes("M1")?"M1":methods[0]||"M0";
  options($("method"),methods.length?methods.map(x=>[x,x]):[["M0","无已运行方法"]],state.method);
  const aligned=modes.filter(x=>selected(case_,x,state.radius));
  options($("other"),aligned.map(x=>[x,LABELS[x]||x]),state.other);
  state.other=$("other").value;
  if(state.other===state.mode&&aligned.length>1&&state.tab==="mask"){
    state.other=aligned.find(x=>x!==state.mode);
    $("other").value=state.other;
  }
  const qs=[...new Set([...Object.keys(case_.queries),...methods.flatMap(m=>Object.keys(methodOf(item,m)?.routes||{}))])];
  if(!qs.includes(state.query))state.query=qs[0]||"";
  options($("query"),qs.length?qs.map(x=>[x,x]):[["","无路线查询"]],state.query);
  $("query-label").hidden=!qs.length;
  $("full-route").hidden=state.tab!=="business"||case_.label!=="NATURAL";
  $("full-route").setAttribute("aria-pressed",state.full);
  $("other-label").hidden=state.tab!=="mask";
  $("method-label").hidden=state.tab==="method"||state.tab==="mask";
  $("ref-toggle").disabled=!case_.reference;
  if(!case_.reference)$("ref-toggle").checked=false;
  const [title,intro]=TAB[state.tab];$("title").textContent=title;
  const sUnavailable=state.tab==="mask"&&!modes.includes("S")&&D.semantic_status;
  $("intro").textContent=intro+(sUnavailable?" 本任务的 S 缺少独立合法的中性轮廓，记录为不适用。":"");
  views=[];
  let left=item,right=item,leftM=null,rightM=methodOf(item,state.method),leftLocal=false,rightLocal=true;
  let leftTitle="街区视野 · 160 m",rightTitle="固定局部 · "+state.method;
  if(state.tab==="mask"){
    left=selected(case_,state.other,state.radius);
    rightLocal=false;rightM=null;leftTitle=LABELS[state.other]||state.other;rightTitle=LABELS[state.mode]||state.mode;
  }
  if(state.tab==="business"&&case_.label==="NATURAL"){
    leftM=rightM;
    if(state.full)leftTitle="全程路线 · 圈外底图仅按已加载观察显示";
  }
  if(state.tab==="method"){
    leftM=methodOf(item,"M0");rightM=methodOf(item,"M1");
    leftLocal=true;leftTitle="M0 · 冻结区域法";rightTitle="M1 · 外围拓扑与空间关系";
  }
  $("left-title").textContent=leftTitle;$("right-title").textContent=rightTitle;
  $("left-note").textContent=metaFor(left,leftM,state.query);
  $("right-note").textContent=metaFor(right,rightM,state.query)+(state.tab==="method"&&!rightM?" · 本输入未运行 M1":"");
  map("left",case_,left,leftM,leftLocal);map("right",case_,right,rightM,rightLocal);
  updateCrosshair();stats(case_,item,leftM,rightM);
  const buttons=[
    [D.natural,"北门"],[D.preset[0],"原零路网"],[D.preset[1],"原单路段"],[D.preset[2],"中心线"],[D.negative,"障碍"],[D.example?.id,"有覆盖样例",D.example]
  ];
  $("shortcuts").replaceChildren(...buttons.filter(([id])=>D.cases[id]).map(([id,t,example])=>{
    const b=n("button",t);b.type="button";b.dataset.task=id;b.onclick=()=>{
      chooseTask(id);
      if(example){
        state.mode=example.mode;state.radius=example.radius;state.method=example.method;render();
      }
    };
    return b;
  }));
  const exit=item?.visible.find(x=>x.layer==="exit");
  const exitLabel=exit?.props.wgs84?" · "+exit.props.id+" ["+exit.props.wgs84.join(", ")+"] "+exit.props.tags?.entrance:"";
  $("source").textContent=D.source+(case_.snapshot?" · "+case_.snapshot:"")+exitLabel+" · 图中参考由评价层单独加载";
  exportMeta={title,case:case_.parent,method:state.method,radius:state.radius,mode:state.mode,
    ref:$("ref-toggle").checked,summary:$("measure").innerText};
  window.contextReview={task:case_.parent,mode:state.mode,radius:state.radius,method:state.method,tab:state.tab,
    rightModel:rightM?.sha256||null,changedCells:rightM?.features?.changed_cells||0,reference:$("ref-toggle").checked,anchor:case_.anchor};
}
function svgDownload(){
  const width=1420,height=690, svg=s("svg",{xmlns:NS,viewBox:"0 0 "+width+" "+height,width,height});
  svg.append(s("rect",{width,height,fill:"#f8faf5"}));
  const text=(x,y,contents,size)=>{
    const node=s("text",{x,y,"font-size":size,"font-family":"Microsoft YaHei, sans-serif",fill:"#243d3e"});
    node.textContent=contents;svg.append(node)
  };
  text(20,28,exportMeta.title+" · "+exportMeta.case,22);
  text(20,51,exportMeta.mode+" · "+exportMeta.radius+" m · 参考"+(exportMeta.ref?"已显示":"关闭"),13);
  for(const [i,side] of ["left","right"].entries()){
    const x=12+i*704;
    text(x,76,$(side+"-title").textContent,16);text(x,95,$(side+"-note").textContent,12);
    const map=$(side+"-map").cloneNode(true);
    map.setAttribute("x",x);map.setAttribute("y",104);map.setAttribute("width",695);map.setAttribute("height",520);svg.append(map);
  }
  const symbols=["way","continuation","score-domain","state-native","state-inferred","state-restricted","state-unknown",
    "route-native","route-derived","route-inferred","reference"];
  for(const [i,key] of symbols.entries()){
    const x=20+i*124, style=C[key];
    svg.append(s("rect",{x,y:630,width:15,height:7,fill:style[0],stroke:style[1],"stroke-dasharray":style[3]}));
    text(x+19,637,LEGEND[key],10);
  }
  text(20,656,exportMeta.summary.replaceAll("\n"," · "),12);
  text(20,671,D.source,12);
  const blob=new Blob([new XMLSerializer().serializeToString(svg)],{type:"image/svg+xml"});
  const url=URL.createObjectURL(blob),a=n("a");
  a.href=url;a.download="R4_CONTEXT_"+exportMeta.case+"_"+state.tab+".svg";a.click();
  setTimeout(()=>URL.revokeObjectURL(url),30000);
}
async function main(){
  D=await load();makeLegend();
  window.contextReviewPairs=Object.values(D.cases).flatMap(c=>Object.entries(c.inputs).flatMap(([mode,values])=>
    Object.entries(values).filter(([,x])=>methodOf(x,"M0")&&methodOf(x,"M1")).map(([radius,x])=>
      ({id:c.parent,mode,radius,changed:methodOf(x,"M1").features.changed_cells||0,
        beyond40:Object.values(methodOf(x,"M1").witnesses).some(w=>!String(w.radius_band).startsWith("0"))}))));
  $("case").onchange=e=>chooseTask(e.target.value);
  $("radius").onchange=e=>{state.radius=e.target.value;render();};
  $("mode").onchange=e=>{state.mode=e.target.value;$("ref-toggle").checked=false;render();};
  $("other").onchange=e=>{state.other=e.target.value;render();};
  $("method").onchange=e=>{state.method=e.target.value;render();};
  $("query").onchange=e=>{state.query=e.target.value;render();};
  for(const id of ["ref-toggle","gray-toggle","route-toggle","base-toggle","region-toggle"])$(id).onchange=render;
  $("zoom-in").onclick=()=>{state.zoom=Math.min(5,state.zoom*1.3);render();};
  $("zoom-out").onclick=()=>{state.zoom=Math.max(1,state.zoom/1.3);render();};
  $("reset").onclick=()=>{state.zoom=1;state.focus=null;state.full=false;render();};
  $("full-route").onclick=()=>{state.full=!state.full;render();};
  $("download").onclick=svgDownload;
  window.addEventListener("hashchange",activation);
  activation();
}
main().catch(error=>{$("title").textContent="地图加载失败";$("intro").textContent=String(error);throw error;});
