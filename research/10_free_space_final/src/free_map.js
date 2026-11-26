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
  "state-native":["#D3EAF5","#5B9FBE",.65],"state-inferred":["#F5D9B8","#D49757",.6],
  "state-restricted":["#E8C7D3","#B97589",.65],"state-unknown":["#DDE3E7","#70757A",.6],
  "route-native":["none","#2D6380",2.8],"route-inferred":["none","#A46124",3,"5 2"],
  "route-derived":["none","#8177A8",2.8,"5 3"],"route-unknown":["none","#70757A",2.5,"2 3"],
  "base-route":["none","#575767",1.9,"2 3"],reference:["#e2add7","#983e80",2.1,"7 3"],
  cell:["#fff","#8177A8",.35],
  "unverified-expansion":["url(#expansion-pattern)","#B97589",.45],
  "road-guard":["none","#B97589",1.6,"3 2"],"common-guard":["none","#B97589",.9,"3 2"],
  "post-audit-restriction":["url(#post-audit-pattern)","#B04C61",1.6,"4 2"]
};
const TAB={
  north:["A · 街区与固定局部","左图保留 160 米街区阅读视野，右图显示 30 米预测域。切换方法保持视野；北门只检验到登记出口外，不代表可从此入馆。"],
  compare:["B · 相同输入，三种规划规则","M1-C 保留正向证据分类并统一几何代价。F0 排障后默认允许条件寻路；F1 使用完全相同区域和图，仅提高假设路段的有限每米代价。"],
  risk:["C · 排除了什么，还假设了什么","受限区域、原生步道和默认可行残余分别显示。参考外扩张不是自动错误，也不是已证实可走；地图未标障碍仍未知。"],
  privatefix:["D · 原权限遗漏与实际修复","同一观测、同一参考与查询：R0旧F0对照V3共同负约束后的M1-C、F0、F1。只补原生private负约束，不生成新入口，不把现场通行未知改为已知。"]
};
const LEGEND={
  way:"原生步行线",clip:"观察裁切", "mask-end":"遮蔽切点","score-domain":"30 m 预测／评分圈",
  "state-native":"原生支持面","state-inferred":"条件可走，未经验证","state-restricted":"实体／政策限制","state-unknown":"证据未知，未放行",
  "route-native":"原生路线","route-derived":"已标面内派生","route-inferred":"假设空间路段","route-unknown":"有界未知接缝","base-route":"无新增区域基线",
  reference:"评价参考",exit:"登记出口",interface:"真实网络接口","road-guard":"车道横穿政策","unverified-expansion":"参考外未证实扩张",
  "post-audit-restriction":"审后权限面，非算法输入"
};
const state={tab:"north",task:null,radius:"160",mode:"H",other:"H",method:"F1",query:"",focus:null,zoom:1,full:false,history:false};
const $=id=>document.getElementById(id);
const s=(name, attrs={})=>{const el=document.createElementNS(NS,name);for(const [k,v] of Object.entries(attrs)){if(v!==null&&v!==undefined)el.setAttribute(k,v);}return el};
const n=(tag, text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el};
let D;
let views=[];
let exportMeta;

async function load(){
  const bytes=Uint8Array.from(atob($("payload").textContent.trim()),x=>x.charCodeAt(0));
  const body=new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  const data=JSON.parse(await new Response(body).text());
  if(data.surfaces)for(const model of data.models){
    const surface=data.surfaces[model.surface_index];model.states=surface.states;model.cells=surface.cells;
  }
  return data;
}
const human=(x,d=0)=>Number.isFinite(x)?x.toLocaleString("zh-CN",{maximumFractionDigits:d,minimumFractionDigits:d}):"—";
const frac=x=>Number.isFinite(x)?human(x*100,2)+"%":"—";
const selected=(case_,mode,radius)=>case_.inputs[mode]?.[radius]||null;
const radii=(case_, mode)=>Object.keys(case_.inputs[mode]||{}).sort((a,b)=>+a-+b);
const methodOf=(item,m)=>{const index=item?.models?.[m]??item?.historical_models?.[m];return Number.isInteger(index)?D.models[index]:null};
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
  state.mode=Object.hasOwn(D.cases[id].inputs,"G")?"G":Object.keys(D.cases[id].inputs)[0];
  state.radius=D.cases[id].label==="NATURAL"?"160":"80";
  state.other="H";
  state.focus=null;
  state.zoom=1;
  state.full=false;
  state.query="";
  state.history=false;
  $("ref-toggle").checked=false;
  render();
}
function activation(){
  const tab=location.hash.slice(1);
  const old=state.tab;
  state.tab=Object.hasOwn(TAB,tab)?tab:"north";
  for(const a of document.querySelectorAll("[data-tab]")){
    if(a.dataset.tab===state.tab)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
  }
  state.zoom=1;state.focus=null;state.full=false;$("ref-toggle").checked=false;
  if(old!==state.tab&&state.tab==="north"&&D.natural)chooseTask(D.natural);
  else if(old!==state.tab&&state.tab==="compare"&&rootCase().label==="NATURAL")chooseTask(D.preset.find(x=>D.cases[x])||Object.keys(D.cases)[0]);
  else if(old!==state.tab&&(state.tab==="risk"||state.tab==="privatefix")&&(D.post_audit?.case||D.negative))chooseTask(D.post_audit?.case||D.negative);
  else render();
}
function statusRoute(m,query,base=false){return (base?m?.base_routes:m?.routes)?.[query]||null}
function metaFor(item,m,query){
  if(!item)return "这个模式在本任务没有可核验观察。";
  const meta=["观察 "+item.radius+" m",item.counts.arcs+" 条有向边"];
  if(item.counts.derived_arcs_aggregated_for_display)meta.push("旧面派生网以原面概绘");
  if(m){
    meta.push("固定 30 m");
    if(!query)meta.push("原合同无路线查询，仅评价区域");
    const r=statusRoute(m,query);
    const check=m.route_audit?.[query];
    if(r){
      const layers=r.layer_lengths||{},assumed=(layers.inferred||0)+(layers.assumed||0)+(layers.unknown||0);
      meta.push(check&&r.reached&&!check.valid_reached?"路线未通过评分核对":
        r.reached?"条件到达 "+human(r.length_m,2)+" m · 假设 "+human(assumed,2)+" m · 代价 "+human(r.cost_m,2):"查询 "+(r.status||"未接通"));
    }
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
  const visibility=options.ghost?"human-background":f.layer==="post-audit-restriction"?(props.predictor_input?"current-source-constraint-review":"post-audit-review-only"):f.layer==="reference"||props.observation==="AUDIT_ONLY_EXACT_MASK"?"evaluation-only":
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
        else group.append(s("circle",{cx:x,cy:y,r,fill:f.layer==="exit"?"#672a53":f.layer==="interface"?"#D49757":"#236673",stroke:"#fff",
          "stroke-width":1.1,"vector-effect":"non-scaling-stroke"}));
      }
    }
    if(p.d){
      const style=C[f.layer]||["none","#646c65",1.2];
      let fill=p.area?style[0]:"none";
      if(f.layer==="unverified-expansion")fill="url(#expansion-pattern-"+svg.id+")";
      if(f.layer==="post-audit-restriction")fill="url(#post-audit-pattern-"+svg.id+")";
      if(f.layer.endsWith("domain"))fill="none";
      group.append(s("path",{d:p.d,fill,stroke:style[1],"stroke-width":style[2],"stroke-dasharray":style[3],
        "fill-rule":"evenodd","stroke-linejoin":"round","stroke-linecap":"round","vector-effect":"non-scaling-stroke",
        "fill-opacity":isCell?.005:(f.layer==="reference"?.19:f.layer.startsWith("state-")?.78:.84),
        "stroke-opacity":isCell?.09:1}));
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
  svg.setAttribute("data-stage",model?.stage||"CURRENT");
  svg.onclick=event=>{if(item)focusPoint(event,svg)};
  svg.append(s("rect",{x:box[0],y:box[1],width:box[2],height:box[3],fill:"#f7f6ef"}));
  const pattern=s("pattern",{id:"expansion-pattern-"+svg.id,width:1.5,height:1.5,patternUnits:"userSpaceOnUse"});
  pattern.append(s("path",{d:"M0,0L1.5,1.5",stroke:"#B97589","stroke-width":.2}));
  const pdefs=s("defs");pdefs.append(pattern);svg.append(pdefs);
  const auditPattern=s("pattern",{id:"post-audit-pattern-"+svg.id,width:1.15,height:1.15,patternUnits:"userSpaceOnUse"});
  auditPattern.append(s("path",{d:"M0,1.15L1.15,0",stroke:"#B04C61","stroke-width":.25}));pdefs.append(auditPattern);
  if(!item){scale(svg,box,local);return}
  if(full&&$("gray-toggle").checked){
    for(const f of case_.full_background||[])feature(f,svg,box[2],{ghost:true});
  }
  const outside=item.background?.length?{visible:item.background}:selected(case_,item.mode,"160");
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
    for(const f of model.states)if(f.layer!=="unverified-expansion"||$("expansion-toggle").checked)feature(f,svg,box[2]);
    if(local)for(const f of model.cells){
      const links=f.props.context_witnesses;
      const detail=links?.map(id=>model.witnesses?.[id]).filter(Boolean);
      feature(detail?.length?{...f,props:{...f.props,actual_outer_witnesses:detail}}:f,svg,box[2]);
    }
  }
  const historical=model?.stage==="R0_HISTORICAL";
  if($("constraint-toggle").checked)for(const f of (historical?item.historical_guards:item.guards)||[])feature(f,svg,box[2]);
  if($("post-audit-toggle").checked)for(const f of case_.post_audit_features||[]){
    const props=historical?{...f.props,predictor_input:false,observation:"R0_POST_AUDIT_SOURCE_RESTRICTION",
      algorithm_input_status:"R0_HISTORICAL_EXPORT_OMITTED_THIS_AREA",per_method_state_overlaps:f.props.r0_per_method_state_overlaps,
      per_method_route_private_interior_m:f.props.r0_per_method_route_private_interior_m}:f.props;
    feature({...f,props},svg,box[2]);
  }
  for(const f of item.visible)if(["way","label","clip","mask-end","source-limit","exit","endpoint"].includes(f.layer))feature(f,svg,box[2]);
  if($("interface-toggle").checked&&model)for(const f of model.portals||[])feature(f,svg,box[2]);
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
function routeFact(model,query){
  const r=statusRoute(model,query);
  if(!r)return "未运行";
  if(!r.reached)return r.status||"未接通";
  const l=r.layer_lengths||{};
  return human(r.length_m,2)+" m · 假设 "+human((l.inferred||0)+(l.assumed||0)+(l.unknown||0),2)+" m · 代价 "+human(r.cost_m,2);
}
function stats(case_,item){
  const names=state.tab==="privatefix"?["R0-F0","M1-C","F0","F1"]:
    ["M1-C","F0","F1"].map(k=>state.history&&item.historical_models?"R0-"+k:k);
  const ms=names.map(k=>[k,methodOf(item,k)]);
  const pills=[pill("预测／评分","30 m · 1 m"),pill("观察",item.radius+" m"),
    pill("可见节点／弧",human(item.counts.nodes)+" / "+human(item.counts.arcs))];
  for(const [name,m] of ms)if(m){
    pills.push(pill(name+" 条件区域",human(m.area.INFERRED_WALKABLE,2)+" m²"));
  }
  const prefix=state.history&&item.historical_models?"R0-":"";
  const f0=methodOf(item,prefix+"F0"),f1=methodOf(item,prefix+"F1");
  if(f0&&f1)pills.push(pill("F0/F1 区域哈希",f0.sha256===f1.sha256?"一致":"不一致，需审查"));
  $("measure").replaceChildren(...pills);
  const table=n("table"),head=n("tr");
  for(const v of ["同一固定查询",...ms.map(x=>x[0])])head.append(n("th",v));table.append(head);
  for(const q of Object.keys(case_.queries)){
    const tr=n("tr");tr.append(n("td",q));for(const [,m] of ms)tr.append(n("td",routeFact(m,q)));table.append(tr);
  }
  const details=n("details"),summary=n("summary","输入、区域与无权图指纹 · 点击展开");details.append(summary);
  const t=n("table");
  for(const [k,v] of [["任务",case_.parent+" · "+case_.kind+" · "+case_.split],["观测输入",item.observed_sha256],
    ["评价参考",item.reference_sha256||"自然案例无独立现场通行参考"],["查询",item.query_sha256],
    ["独立于本任务的六裁片语义回归",D.semantic_regression?
      "原生片段保留 "+D.semantic_regression.restored_unique_segments+"；草地内有效步道 "+human(D.semantic_regression.restored_grass_overlap_m,2)+" m。不是本30m区域恢复量或现场通行证明。":"本页面未加载回执"],
    ...ms.flatMap(([k,m])=>m?[[k+" 区域",m.sha256],[k+" 无权图",m.graph_sha256||JSON.stringify(m.graph)]]:[])]){
    const tr=n("tr");tr.append(n("th",k),n("td",v||"未提供"));t.append(tr);
  }
  details.append(t);$("detail").replaceChildren(table,details);
}
function render(){
  if(state.tab==="privatefix"&&D.post_audit?.case)state.task=D.post_audit.case;
  const c=rootCase();state.task=c.parent;
  options($("case"),Object.values(D.cases).filter(x=>state.tab!=="privatefix"||x.parent===D.post_audit?.case).map(x=>[x.parent,caseLabel(x)]),state.task);
  const modes=Object.keys(c.inputs);state.mode=options($("mode"),modes.map(x=>[x,LABELS[x]||x]),state.mode);
  const rs=radii(c,state.mode);if(!rs.includes(state.radius))state.radius=rs.includes("80")?"80":rs.at(-1);
  state.radius=options($("radius"),rs.map(x=>[x,x+" m"]),state.radius);
  const item=selected(c,state.mode,state.radius),methods=Object.keys(item.models);
  if(!item.historical_models)state.history=false;
  if(state.tab==="privatefix")state.history=false;
  $("stage-label").hidden=!item.historical_models||state.tab==="privatefix";
  $("stage").value=state.history?"R0":"CURRENT";
  if(!methods.includes(state.method))state.method=methods.includes("F1")?"F1":methods[0];
  options($("method"),methods.map(x=>[x,x]),state.method);
  const qs=Object.keys(c.queries);if(!qs.includes(state.query))state.query=qs[0]||"";
  options($("query"),qs.length?qs.map(x=>[x,x]):[["","无冻结查询"]],state.query);
  $("query-label").hidden=!qs.length;
  $("ref-toggle").disabled=!c.reference;
  if(!c.reference)$("ref-toggle").checked=false;
  const compare=state.tab!=="north";
  const quad=state.tab==="privatefix";
  $("maps").classList.toggle("triple",compare&&!quad);$("maps").classList.toggle("quad",quad);
  $("third-pane").hidden=!compare;$("fourth-pane").hidden=!quad;
  $("method-label").hidden=compare;
  $("full-route").hidden=compare||c.label!=="NATURAL";$("full-route").setAttribute("aria-pressed",state.full);
  const [title,intro]=TAB[state.tab];$("title").textContent=title;
  $("intro").textContent=state.tab==="north"&&state.full?
    "左图按原起点到出口的真实路线外包络展开；灰色大背景只供阅读，不是区域预测输入。右图始终固定30米。路线仍是条件规划，到出口外不代表可从此入馆。":intro;
  $("source-gap").hidden=!D.post_audit;
  $("source-gap").textContent=D.private_fix?"R0曾漏导1个主任务的private停车面；本轮已实际补入V3共同负约束，128.39m²在三法中均禁止。R0旧错误与07图保留作历史。本项修复不是现场通行证明，也不证明所有未标障碍已排除。":D.post_audit?"来源复核发现1/25主任务有权限面导出遗漏：F0/F1将128.39m²的private停车面纳入默认可行。该例2条新增路线未进入其内部。区域权限gap待修；不将所有参考外扩张视为错误。":"";
  const auditNote=state.history&&c.post_audit_history_note?"R0历史版本，已被当前修复替代："+c.post_audit_history_note:c.post_audit_note||null;
  $("case-gap").hidden=!auditNote;$("case-gap").textContent=auditNote||"";
  $("fix-nav").hidden=!D.private_fix;$("r0-atlas-link").hidden=!D.private_fix;
  $("post-audit-toggle").parentElement.lastChild.textContent=D.private_fix?" 权限面核对（R0漏导／当前V3已导入）":" 审后权限面（非算法输入）";
  views=[];
  const viewed=name=>state.history&&item.historical_models?"R0-"+name:name;
  const arrangement=quad?[["left","R0-F0",true],["right","M1-C",true],["third","F0",true],["fourth","F1",true]]:
    compare?[["left",viewed("M1-C"),true],["right",viewed("F0"),true],["third",viewed("F1"),true]]:
    [["left",viewed(state.method),false],["right",viewed(state.method),true]];
  for(const [side,name,local] of arrangement){
    const m=methodOf(item,name);
    $(side+"-title").textContent=compare?name+(name.startsWith("R0-")?" · 历史漏导版本":name==="M1-C"?" · 当前正向证据":name==="F0"?" · 当前默认可行，λ=1":" · 当前同图步道优先，λ=2"):
      (local?"30 m 固定局部 · ":state.full?"完整原起点路线 · ":"160 m 街区阅读 · ")+name;
    $(side+"-note").textContent=metaFor(item,m,state.query);
    map(side,c,item,m,local);
  }
  updateCrosshair();stats(c,item);
  const buttons=[[D.natural,"北门"],[D.preset[0],"图书馆"],[D.preset[1],"新世界"],[D.preset[2],"中心线"],[D.negative,"水体／建筑"],[D.post_audit?.case,"权限遗漏"]];
  $("shortcuts").replaceChildren(...buttons.filter(([id])=>D.cases[id]).map(([id,label])=>{
    const b=n("button",label);b.onclick=()=>chooseTask(id);return b;
  }));
  const exit=item.visible.find(f=>f.layer==="exit");
  $("source").textContent=D.source+(c.snapshot?" · 源快照 "+c.snapshot:"")+" · 灰色圈外背景只供人工阅读，不是预测输入 · 参考仅在评价层加载"+
    (exit?" · "+exit.props.id+" "+JSON.stringify(exit.props.wgs84||exit.props.xy)+" entrance=exit；只评价门外到达":"");
  exportMeta={title,case:c.parent,tab:state.tab,method:state.method,mode:state.mode,radius:state.radius,full:state.full,
    ref:$("ref-toggle").checked,summary:$("measure").innerText,auditNote,stage:state.history?"R0_HISTORICAL":"CURRENT_R1"};
  window.freeReview={...exportMeta,query:state.query,anchor:c.anchor,visibleMethods:arrangement.map(a=>a[1]),
    f0Surface:f0hash(item,state.history?"R0-F0":"F0"),f1Surface:f0hash(item,state.history?"R0-F1":"F1"),methods,
    privateFixed:!!D.post_audit?.fixed};
}
function f0hash(item,name){return methodOf(item,name)?.sha256||null}
function buildSVG(){
  const quad=state.tab==="privatefix";
  const sides=quad?["left","right","third","fourth"]:state.tab==="north"?["left","right"]:["left","right","third"];
  const width=quad?1260:sides.length*620+20,height=quad?1410:780,lower=quad?630:0;
  const svg=s("svg",{xmlns:NS,viewBox:"0 0 "+width+" "+height,width,height});
  svg.append(s("rect",{width,height,fill:"#FCFAF7"}));
  const text=(x,y,content,size)=>{const t=s("text",{x,y,"font-size":size,"font-family":"Microsoft YaHei, sans-serif",fill:"#2D3238"});t.textContent=content;svg.append(t)};
  text(18,28,exportMeta.title+" · "+exportMeta.case,21);
  text(18,51,exportMeta.auditNote||"相同观测／公共约束／30 m 域／1 m 格网 · 参考"+(exportMeta.ref?"显示":"关闭")+" · 条件可走不等于现场通行证明",12);
  for(const [i,side] of sides.entries()){
    const x=10+(quad?i%2:i)*620,y=quad?Math.floor(i/2)*630:0;text(x+5,77+y,$(side+"-title").textContent,15);
    text(x+5,96+y,$(side+"-note").textContent,11);
    const map=$(side+"-map").cloneNode(true);map.setAttribute("x",x);map.setAttribute("y",106+y);map.setAttribute("width",610);map.setAttribute("height",574);svg.append(map);
  }
  const legends=["state-native","state-inferred","state-restricted","state-unknown","route-native","route-derived","route-inferred","reference"];
  for(const [i,key] of legends.entries()){
    const x=18+i*(width-36)/8,v=C[key];svg.append(s("rect",{x,y:692+lower,width:14,height:7,fill:v[0],stroke:v[1],"stroke-dasharray":v[3]}));text(x+19,700+lower,LEGEND[key],10);
  }
  const lines=exportMeta.summary.replaceAll("\n"," · ").match(/.{1,135}/g)||[];
  lines.slice(0,2).forEach((line,i)=>text(18,722+lower+i*16,line,11));
  text(18,765+lower,D.source,11);
  return new XMLSerializer().serializeToString(svg);
}
function saveBlob(blob,name){const url=URL.createObjectURL(blob),a=n("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)}
function svgDownload(){saveBlob(new Blob([buildSVG()],{type:"image/svg+xml"}),"FREE_SPACE_"+state.task+"_"+state.tab+".svg")}
async function pngDownload(){
  const blob=new Blob([buildSVG()],{type:"image/svg+xml"}),url=URL.createObjectURL(blob),img=new Image();
  try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url});
    const canvas=document.createElement("canvas");canvas.width=img.width;canvas.height=img.height;
    canvas.getContext("2d").drawImage(img,0,0);
    const png=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));if(!png)throw Error("PNG export unavailable");
    saveBlob(png,"FREE_SPACE_"+state.task+"_"+state.tab+".png");
  }finally{URL.revokeObjectURL(url)}
}
async function main(){
  D=await load();
  if(D.private_fix)LEGEND["post-audit-restriction"]="权限核对：R0漏导／V3已导入";
  makeLegend();
  if(D.natural)state.task=D.natural;
  $("case").onchange=e=>chooseTask(e.target.value);
  $("mode").onchange=e=>{state.mode=e.target.value;render()};$("radius").onchange=e=>{state.radius=e.target.value;render()};
  $("method").onchange=e=>{state.method=e.target.value;render()};$("query").onchange=e=>{state.query=e.target.value;render()};
  $("stage").onchange=e=>{state.history=e.target.value==="R0";render()};
  for(const id of ["ref-toggle","gray-toggle","constraint-toggle","route-toggle","base-toggle","region-toggle","expansion-toggle","interface-toggle","post-audit-toggle"])$(id).onchange=render;
  $("zoom-in").onclick=()=>{state.zoom=Math.min(5,state.zoom*1.3);render()};$("zoom-out").onclick=()=>{state.zoom=Math.max(1,state.zoom/1.3);render()};
  $("reset").onclick=()=>{state.zoom=1;state.focus=null;state.full=false;render()};$("full-route").onclick=()=>{state.full=!state.full;render()};
  $("download").onclick=svgDownload;$("download-png").onclick=()=>pngDownload().catch(e=>{$("inspect").textContent="PNG导出失败："+e;throw e});
  window.addEventListener("hashchange",activation);activation();
}
main().catch(e=>{$("title").textContent="地图加载失败";$("intro").textContent=String(e);throw e});
