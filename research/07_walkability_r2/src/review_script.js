"use strict";
const payload=JSON.parse(document.getElementById("payload").textContent);
const $=id=>document.getElementById(id);
const style={
 park:["#eef0d9","#879869","2 2","公园范围"], plaza:["#d3eaf5","#6498a9","","登记步行面"],
 grass:["#d7e1c8","#8b9c70","","背景草地"], building:["#eadbc8","#9b826b","","建筑"],
 road:["none","#aab0ac","","道路"], walk:["none","#77a2a5","","源步道"],
 fence:["none","#745f54","2 2","墙／围栏"], water:["#bcd7e9","#6f9cba","","水体"],
 label:["none","#41535b","","地名"], observed:["none","#668f9a","","可见路网"],
 window:["none","#856955","1 3","独立搜索窗口"], candidate:["none","#899aaf","3 3","条件候选未选"],
 domain:["#ebdbbc","#977037","4 2","局部搜索域"], historic:["none","#8e9296","4 3","旧条带"],
 native:["none","#17506b","","原生路线"], restored:["none","#2d7350","","恢复步道"],
 derived:["none","#796895","4 2","既有面派生"], inferred:["none","#ad5a27","6 3","条件推断"],
 rejected:["none","#9f495e","1 3","拒绝／未选"], reference:["none","#6855a3","4 2","隐藏参考（事后）"],
 gap:["none","#707679","2 3","缺口测距"], origin:["#217552","#fff","","冻结起点"],
 door:["#893c65","#fff","","原登记门／出口"], anchor:["#d38932","#fff","","候选接点"]
};
const groups={basemap:["park","plaza","grass","building","road","walk","fence","water","label","observed"],
 domain:["window","domain","historic"], lines:["candidate","native","restored","derived","inferred","rejected","gap","reference"],
 points:["origin","door","anchor"]};
const visible={basemap:true,domain:true,lines:true,points:true};
let tab="grass", view="near", zoom=1, comparator="I2", caseId=payload.cases[0]?.id;
const elem=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
const svg=(tag,attrs)=>{const n=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n};
function paneBounds(bounds){
 const [x,y,w,h]=bounds, ww=w/zoom, hh=h/zoom;
 return [x+(w-ww)/2,y+(h-hh)/2,ww,hh];
}
function info(f){
 const p=f.props||{}, box=$("inspector");box.replaceChildren(elem("strong",p.label||p.native_id||p.id||style[f.layer]?.[3]||"地图对象"));
 const keys=["S0_status","S1_status","background_overlap_m","source_id","native_id","candidate_id","variant","status","decision","reason","kind","length_m","wgs84","grade_status","same_level_assumption","evidence_status","source_ids","tags"];
 for(const k of keys)if(p[k]!==undefined && p[k]!==null)box.append(elem("div",k+" · "+(typeof p[k]==="object"?JSON.stringify(p[k]):String(p[k]))));
}
function paint(container,features,bounds){
 container.replaceChildren();container.setAttribute("viewBox",bounds.join(" "));container.setAttribute("preserveAspectRatio","xMidYMid meet");
 const [x,y,w,h]=bounds, pixel=w/680;
 container.append(svg("rect",{x,y,width:w,height:h,fill:"#f2f2e9"}));
 const used=new Set(Object.entries(visible).filter(([,v])=>v).flatMap(([g])=>groups[g]));
 for(const f of features){
  if(!used.has(f.layer)||!style[f.layer])continue;
  const [fill,stroke,dash,label]=style[f.layer], p=f.props||{};
  const item=svg("g",{tabindex:"0",role:"button","aria-label":p.native_id||p.id||label,"data-layer":f.layer});
  const title=svg("title",{});title.textContent=[label,p.native_id||p.source_id||p.id,p.reason||p.status].filter(Boolean).join(" · ");item.append(title);
  for(const part of f.shape){
   if(part.d) item.append(svg("path",{d:part.d,fill:part.area?fill:"none",stroke,"stroke-width":(["native","inferred","derived","reference","restored"].includes(f.layer)?3.5:1.25),"stroke-dasharray":dash,"vector-effect":"non-scaling-stroke","fill-rule":"evenodd","stroke-linecap":"round","stroke-linejoin":"round","fill-opacity":f.layer==="domain"?.32:1}));
   if(part.point){
    const [cx,cy]=part.point;
    if(f.layer==="label"){
     const t=svg("text",{x:cx,y:cy,fill:stroke,"font-size":10*pixel,"paint-order":"stroke",stroke:"#fbfaf0","stroke-width":2*pixel,"stroke-linejoin":"round"});t.textContent=p.label||p.name||"";item.append(t);
    } else {
     const r=([ "door","origin"].includes(f.layer)?4.4:3.3)*pixel;
     item.append(f.layer==="door"?svg("rect",{x:cx-r,y:cy-r,width:r*2,height:r*2,fill,stroke,"stroke-width":pixel}):svg("circle",{cx,cy,r,fill,stroke,"stroke-width":pixel}));
    }
   }
  }
  item.addEventListener("click",()=>info(f));item.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();info(f);}});
  container.append(item);
 }
 const nice=[1,2,5,10,20,25,50,100,200,500].filter(m=>m<w*.21).at(-1)||.5;
 const a=x+13*pixel,b=y+h-13*pixel;
 container.append(svg("rect",{x:a-5*pixel,y:b-20*pixel,width:(nice+44*pixel),height:28*pixel,fill:"#fffdfa","fill-opacity":.88}));
 container.append(svg("path",{d:"M"+a+","+b+"h"+nice,stroke:"#213b43","stroke-width":2*pixel}));
 for(const [text,tx,ty] of [[nice+" m",a,b-5*pixel],["↑ N",x+w-39*pixel,y+21*pixel]]){
  const t=svg("text",{x:tx,y:ty,"font-size":13*pixel,fill:"#28424a","font-weight":"650","paint-order":"stroke",stroke:"#fffefa","stroke-width":1.5*pixel});t.textContent=text;container.append(t);
 }
}
function table(headers,rows){
 const outer=elem("div");outer.className="table";const t=elem("table"),head=elem("thead"),h=elem("tr"),body=elem("tbody");
 for(const value of headers)h.append(elem("th",value));head.append(h);t.append(head);
 for(const row of rows){const tr=elem("tr");for(const value of row)tr.append(elem("td",value??"—"));body.append(tr);}
 t.append(body);outer.append(t);return outer;
}
function update(){
 const s=tab==="cases"?payload.cases.find(x=>x.id===caseId):payload[tab];
 $("title").textContent=s?.title??"暂无可审查案例";$("intro").textContent=s?.intro??"";
 if(!s)return;
 const actual=tab==="north"?s.pairs[comparator]||s.pairs.I2:s.pair;
 $("left-head").textContent=actual.left.title;$("right-head").textContent=actual.right.title;
 $("left-summary").textContent=actual.left.note||"";$("right-summary").textContent=actual.right.note||"";
 const bounds=paneBounds(s.views[view]);
 paint($("map-left"),[...s.base,...(actual.left.features||[])],bounds);
 paint($("map-right"),[...s.base,...(actual.right.features||[])],bounds);
 $("details").replaceChildren();
 for(const v of s.tables||[]){$("details").append(elem("h3",v.title),table(v.headers,v.rows));}
 $("compare-controls").replaceChildren();
 if(tab==="north"){
  const select=elem("select");select.setAttribute("aria-label","北门右图变体");
  for(const k of Object.keys(s.pairs)){const opt=elem("option",k);opt.value=k;opt.selected=k===comparator;select.append(opt);}
  select.addEventListener("change",()=>{comparator=select.value;update()});$("compare-controls").append(select);
 } else if(tab==="cases"){
  const select=elem("select");select.setAttribute("aria-label","受控案例");
  for(const c of payload.cases){const opt=elem("option",c.id+" · "+c.label);opt.value=c.id;opt.selected=c.id===caseId;select.append(opt);}
  select.addEventListener("change",()=>{caseId=select.value;zoom=1;update()});$("compare-controls").append(select);
 }
}
function activate(){
 const hash=location.hash.slice(1);tab=["grass","north","cases"].includes(hash)?hash:"grass";zoom=1;view="near";
 for(const n of document.querySelectorAll("[data-tab]"))n.setAttribute("aria-current",n.dataset.tab===tab?"page":"false");
 for(const n of document.querySelectorAll("[data-view]"))n.setAttribute("aria-pressed",String(n.dataset.view===view));
 update();
}
function exportPanel(){
 const root=svg("svg",{xmlns:"http://www.w3.org/2000/svg",width:1420,height:540,viewBox:"0 0 1420 540"});
 root.append(svg("rect",{width:1420,height:540,fill:"#fffdfa"}));
 const title=svg("text",{x:12,y:23,"font-size":20,"font-family":"Microsoft YaHei, Arial",fill:"#21313a"});title.textContent=$("title").textContent;root.append(title);
 for(const [index,side] of ["left","right"].entries()){
  const x=index*710+7,t=svg("text",{x,y:49,"font-size":15,"font-family":"Microsoft YaHei, Arial",fill:"#243139"});t.textContent=$(side+"-head").textContent+" · "+$(side+"-summary").textContent;root.append(t);
  const clone=$("map-"+side).cloneNode(true);clone.setAttribute("x",x);clone.setAttribute("y",58);clone.setAttribute("width",700);clone.setAttribute("height",455);root.append(clone);
 }
 const c=svg("text",{x:13,y:531,"font-size":11,"font-family":"Arial",fill:"#51616a"});c.textContent="© OpenStreetMap contributors · EPSG:32651 · frozen OSM / conditional inference";root.append(c);
 return new XMLSerializer().serializeToString(root);
}
window.exportPanel=exportPanel;
for(const [g,caption] of Object.entries({basemap:"原生底图",domain:"候选域与旧条带",lines:"路线和证据线",points:"端点与接点"})){
 const l=elem("label"),c=elem("input");c.type="checkbox";c.checked=true;c.addEventListener("change",()=>{visible[g]=c.checked;update()});l.append(c,document.createTextNode(caption));$("layers").append(l);
}
for(const [k,[fill,stroke,dash,caption]] of Object.entries(style)){
 if(!["grass","park","plaza","building","restored","native","derived","inferred","candidate","rejected","reference","window","domain","gap","origin","door","anchor"].includes(k))continue;
 const label=elem("span"), icon=elem("i");icon.className="swatch";icon.style.background=fill==="none"?"none":fill;icon.style.borderTop="2px "+(dash?"dashed":"solid")+" "+stroke;label.append(icon,document.createTextNode(caption));$("legend").append(label);
}
for(const n of document.querySelectorAll("[data-view]"))n.addEventListener("click",()=>{view=n.dataset.view;zoom=1;for(const item of document.querySelectorAll("[data-view]"))item.setAttribute("aria-pressed",String(item===n));update()});
$("zoom-plus").onclick=()=>{zoom=Math.min(5,zoom*1.35);update()};$("zoom-minus").onclick=()=>{zoom=Math.max(.55,zoom/1.35);update()};$("reset").onclick=()=>{zoom=1;update()};
$("export").onclick=()=>{const blob=new Blob([exportPanel()],{type:"image/svg+xml;charset=utf-8"}),url=URL.createObjectURL(blob),a=elem("a");a.href=url;a.download="walkability-r2-"+tab+".svg";a.click();setTimeout(()=>URL.revokeObjectURL(url),5000)};
window.addEventListener("hashchange",activate);activate();
