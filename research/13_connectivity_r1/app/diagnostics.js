/* Read-only actual source/regression evidence. No route synthesis or answer cache. */
'use strict';
const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
let payload=null,support=null,current=null,mode='failures',view=null,drag=null,suppressClick=false;
const MOTOR=new Set(['motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road']);

function element(type,attrs,record){const e=document.createElementNS(NS,type);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(record)e.addEventListener('click',ev=>{if(suppressClick)return;ev.stopPropagation();$('evidence').textContent=JSON.stringify(record,null,2)});return e}
function path(g){if(!g)return'';const seq=points=>points.map((p,i)=>(i?'L':'M')+p[0]+','+(-p[1])).join(' ');switch(g.type){case'LineString':return seq(g.coordinates);case'MultiLineString':return g.coordinates.map(seq).join(' ');case'Polygon':return g.coordinates.map(r=>seq(r)+' Z').join(' ');case'MultiPolygon':return g.coordinates.map(p=>p.map(r=>seq(r)+' Z').join(' ')).join(' ');case'GeometryCollection':return g.geometries.map(path).join(' ');default:return''}}
function positions(g){if(!g)return[];if(g.type==='GeometryCollection')return g.geometries.flatMap(positions);const out=[];const walk=a=>{if(typeof a[0]==='number')out.push(a);else a.forEach(walk)};walk(g.coordinates);return out}
function fitBounds(b,pad=0){let[x0,y0,x1,y1]=b,w=Math.max(x1-x0+pad*2,6),h=Math.max(y1-y0+pad*2,6);const aspect=Math.max($('diag-map').clientWidth,1)/Math.max($('diag-map').clientHeight,1);if(w/h<aspect)w=h*aspect;else h=w/aspect;view=[(x0+x1-w)/2,-(y0+y1+h)/2,w,h];draw()}
function fitPoints(p,pad=4){if(!p.length)return;const xs=p.map(x=>x[0]),ys=p.map(x=>x[1]);fitBounds([Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)],pad)}
function features(){return current?.features?.features||[]}
function isDomain(f){return f.properties?.kind==='FIXED_30M_PREDICTION_AND_SCORE_DOMAIN'}
function frontiers(){return features().filter(f=>f.properties?.kind==='REJECTED_PLANAR_CANDIDATE_NOT_ROUTE')}
function style(f){const p=f.properties||{},t=p.tags||{},k=p.kind||'',g=f.geometry;
 if(isDomain(f))return{fill:'none',stroke:'#826334',width:1.4,dash:[6,4]};
 if(k==='REJECTED_PLANAR_CANDIDATE_NOT_ROUTE')return{fill:'none',stroke:'#a23d45',width:2.4,dash:[3,3]};
 if(k==='SOURCE_PERMISSION_AREA'||k.includes('RESTRICT'))return{fill:g.type.includes('Polygon')?'#e6c1cb':'none',stroke:'#a05169',width:1.4,opacity:.78};
 if(k.includes('BUILDING')||t.building)return{fill:'#c6c0b5',stroke:'#9d958b',width:.8};
 if(k.includes('GRASS')||t.landuse==='grass'||k==='FLOWERBED')return{fill:'#d3e3b1',stroke:'#acc28f',width:.65};
 if(k.includes('PEDESTRIAN')||k.includes('WALKABLE'))return{fill:'#eddfbc',stroke:'#c9b38b',width:.7};
 if(k==='PARK')return{fill:'#e6ecd1',stroke:'#c4d2ab',width:.6};
 if(k.includes('WATER'))return{fill:'#b8d8e3',stroke:'#85afc0',width:.7};
 if(k.includes('BARRIER'))return{fill:'none',stroke:'#75475f',width:1.7};
 if(t.highway==='steps')return{fill:'none',stroke:'#a9501d',width:3};
 if(MOTOR.has(t.highway))return{fill:'none',stroke:mode==='road'?'#777b82':'#a4a49b',width:mode==='road'?2.8:1.9};
 if(p.layer==='native'||k.includes('NATIVE'))return{fill:'none',stroke:'#347da0',width:1.7};
 return{fill:g.type.includes('Polygon')?'#edf0df':'none',stroke:'#b5bfa9',width:.6}}
function rank(f){const k=f.properties?.kind||'';if(k==='PARK')return 0;if(k.includes('PEDESTRIAN'))return 1;if(k.includes('GRASS'))return 2;if(f.geometry.type.includes('Polygon'))return 3;if(isDomain(f))return 5;if(k==='REJECTED_PLANAR_CANDIDATE_NOT_ROUTE')return 8;return 4}

function draw(){if(!view||!current)return;const svg=$('diag-map');svg.replaceChildren();svg.setAttribute('viewBox',view.join(' '));const u=view[2]/Math.max(svg.clientWidth,1);
 const bb=current.view_bounds,cx=(bb[0]+bb[2])/2,cy=(bb[1]+bb[3])/2;
 svg.append(element('circle',{cx,cy:-cy,r:50,fill:'none',stroke:'#b9c1b3','stroke-width':u,'stroke-dasharray':`${2*u} ${5*u}`},{identity:'DISPLAY_CLIP_ONLY',radius_m:50,not_prediction_or_score_domain:true}));
 const seen=new Set();
 for(const f of [...features()].sort((a,b)=>rank(a)-rank(b))){const p=f.properties||{},k=p.kind||'';if(f.geometry.type==='Point')continue;if(k==='REJECTED_PLANAR_CANDIDATE_NOT_ROUTE'&&!$('show-frontier').checked)continue;if((p.layer==='native'||k.includes('NATIVE_LINEAR'))&&!$('show-native').checked)continue;const key=(p.source_id||p.id||'')+JSON.stringify(f.geometry);if(seen.has(key))continue;seen.add(key);const s=style(f);svg.append(element('path',{d:path(f.geometry),fill:s.fill,stroke:s.stroke,'stroke-width':s.width*u,'fill-opacity':s.opacity??1,'fill-rule':'evenodd',...(s.dash?{'stroke-dasharray':s.dash.map(v=>v*u).join(' ')}:{})},p))}
 for(const f of current.focus_features||[]){const p=f.properties||{},old=mode==='grass'&&$('semantic-version').value==='S0',s=old?{stroke:'#888a85',width:5,dash:[4,4]}:{stroke:mode==='private'?'#1d8873':'#216b8b',width:5};svg.append(element('path',{d:path(f.geometry),fill:'none',stroke:'#fff','stroke-width':8*u},null));svg.append(element('path',{d:path(f.geometry),fill:'none',stroke:s.stroke,'stroke-width':s.width*u,...(s.dash?{'stroke-dasharray':s.dash.map(x=>x*u).join(' ')}:{})},{...p,display_semantics:old?'S0_REJECTED_NATIVE_LINE_SHOWN_FOR_DIAGNOSTIC_ONLY':'RETAINED_ORIGINAL_NATIVE_SOURCE_GEOMETRY_NOT_A_NEW_LINK'}))}
 if(mode==='failures'){
  for(const [end,label,color,shapeKind]of[[current.source,'S','#245d89','circle'],[current.target,'T','#793f29','diamond']]){
   const[x,y]=end.xy;if(current.failed_endpoint_ids.includes(end.id))svg.append(element('circle',{cx:x,cy:-y,r:10*u,fill:'#fff9ed',stroke:'#b95f27','stroke-width':2*u},end));
   if(shapeKind==='circle')svg.append(element('circle',{cx:x,cy:-y,r:5*u,fill:color,stroke:'white','stroke-width':1.8*u},end));
   else svg.append(element('path',{d:`M${x},${-y-6*u} L${x+6*u},${-y} L${x},${-y+6*u} L${x-6*u},${-y} Z`,fill:color,stroke:'white','stroke-width':1.8*u},end));
   const text=element('text',{x:x+11*u,y:-y-8*u,'font-size':12*u,'font-weight':700,fill:color,stroke:'#fff','stroke-width':3*u,'paint-order':'stroke'},end);text.textContent=label;svg.append(text)
  }
 }
 const metres=view[2]/6,base=10**Math.floor(Math.log10(metres));const len=[1,2,5,10].map(x=>x*base).find(x=>x>=metres*.5&&x<=metres*1.5)||base;$('scale').textContent=`${len} m`;$('scale').style.width=(len/u)+'px';
}

function showSummary(){if(!current)return;$('diag-title').textContent=current.title;$('diag-subtitle').textContent=current.subtitle;$('failure-picker').style.display=mode==='failures'?'block':'none';$('support-toggle').style.display=mode==='grass'?'block':'none';$('road-note').style.display=mode==='road'?'block':'none';$('show-prediction').disabled=mode!=='failures';$('show-block').disabled=mode!=='failures';$('show-frontier').disabled=mode!=='failures';$('components').style.display=mode==='failures'?'block':'none';$('panel-role').textContent=mode==='failures'?'BENCHMARK REGRESSION / DIAGNOSTIC DISPLAY':'SOURCE / HISTORICAL CORRECTNESS REGRESSION';
 $('source-hash').textContent=`${current.source_clip||support?.source_clip||''}\nSHA256: ${current.source_sha256||support?.source_sha256||''}\nCRS: EPSG:32651 · 地图事实与当前现场状态分开。`;$('source-hash').style.whiteSpace='pre-line';
 if(mode==='failures'){
  $('diag-status').textContent=`历史 ${current.old_status} → 当前 ${current.new_status}\n${current.root_cause}`;
  $('diag-note').textContent=current.meaning+' 50米仅供看图；固定预测/评分半径仍为30米。';
  $('boundary-message').textContent='7条属于4个父任务，都是固定网络端点查询；不能称为7栋楼、7个门或7次现场到达。楼梯仍在原生网络中，未接通不等于现实不能走。';
  const metrics=[['源点',current.source.id],['目标',current.target.id],['相关原生楼梯',current.stairs_source_ids.join(', ')],['被拒接入端点',current.failed_endpoint_ids.join(', ')]];
  $('diag-metrics').replaceChildren(...metrics.map(([name,value])=>{const d=document.createElement('div');d.className='statbox';const l=document.createElement('div');l.className='label';l.textContent=name;const v=document.createElement('div');v.className='value';v.textContent=value;d.append(l,v);return d}));
  const table=document.createElement('table');const head=table.createTHead().insertRow();for(const t of['端点','原生图分量 / 大小','局部图','组合图分量 / 大小','自由接口资格']){const th=document.createElement('th');th.textContent=t;head.append(th)}const body=table.createTBody();for(const c of current.components){const r=body.insertRow();for(const v of[c.id,c.native.present?`${c.native.component} / ${c.native.size}`:'不在图中',c.local.present?`${c.local.component} / ${c.local.size}`:'未绑定',c.combined_before.present?`${c.combined_before.component} / ${c.combined_before.size}`:'不在图中',c.visible_eligible?'原观测中可核对兼容步道':'仅楼梯；未确认同层接口']){r.insertCell().textContent=v}}$('component-table').replaceChildren(table)
 }else{
  const summary=current.summary||{};$('diag-status').textContent=mode==='grass'?`原几何不变：S0 ${summary.old_status} → S1 ${summary.new_status}\n跨六裁片去重保留 ${summary.unique_native_grass_segments_all_six_clips} 段原生步道。`:mode==='private'?`原源权限面 ${summary.source_area_m2?.toFixed(2)} m²\n准确沿边原生线 ${summary.exact_allowed_native_boundary_length_m?.toFixed(3)} m；零缓冲。`:'道路中心线只是一条轴线。已知零宽约束用于避免新增横穿，不代表实际车行范围已被完整排除。';
  $('diag-metrics').textContent='';$('diag-note').textContent=mode==='road'?'灰色轴线来自真实原源 highway way。点选可查看标签；图上显示线宽不是测得道路宽度。当前地图级接近路线不等于现实可走或完整避车保证。':summary.meaning;
  $('boundary-message').textContent=mode==='grass'?'这里只修正地图语义：原生步道保留，并未允许在整个草坪任意抄近路。此处为来源回归，不是新增入口请求。':'只允许准确来源支持的沿边原生线；不允许穿进私有面内部，不将权限面边界直接当实体墙。此处为来源/历史回归，不是新的公众通行证据。';
 }
 $('evidence').textContent='点选地图对象，查看其原生ID、tags、来源和判定。红色短虚线是未采用候选，不是已计算路线。';
}
function chooseCase(index){const cases=payload?.cases||[];if(!cases.length)return;index=(index+cases.length)%cases.length;$('case-select').selectedIndex=index;current=cases[index];showSummary();fitBounds(current.view_bounds,2)}
function switchMode(next){mode=next;for(const key of['failures','grass','private','road'])$('tab-'+key).setAttribute('aria-selected',String(key===mode));if(mode==='failures')chooseCase($('case-select').selectedIndex);else if(support){current=support.cases.find(c=>c.id===(mode==='grass'?'source-S-grass':'source-private'));if(mode==='road')current={...current,title:'道路中心线：知道一条线，不等于知道整条车道',subtitle:'真实地图数据的表示边界；不推断不存在的车行面'};showSummary();fitBounds(current.view_bounds,2)}else{$('diag-status').textContent='来源支持材料尚未被服务加载；七条失败诊断仍可查看。'}}

$('case-select').onchange=()=>chooseCase($('case-select').selectedIndex);$('prev').onclick=()=>chooseCase($('case-select').selectedIndex-1);$('next').onclick=()=>chooseCase($('case-select').selectedIndex+1);for(const k of['failures','grass','private','road'])$('tab-'+k).onclick=()=>switchMode(k);for(const id of['show-native','show-frontier'])$(id).onchange=draw;$('semantic-version').onchange=()=>{draw();$('evidence').textContent=$('semantic-version').value==='S0'?'灰色断线表示旧S0将原生线排除；仍画出原几何用于审查，并非路线。':'蓝色粗线表示S1保留已登记原生步道；没有扩大其宽度或开放草地面。'};
$('show-display').onclick=()=>fitBounds(current.view_bounds,2);$('show-prediction').onclick=()=>{const f=features().find(isDomain);if(f)fitPoints(positions(f.geometry),3)};$('show-block').onclick=()=>{const focus=features().filter(f=>f.properties?.tags?.highway==='steps'||f.properties?.kind==='REJECTED_PLANAR_CANDIDATE_NOT_ROUTE');fitPoints(focus.flatMap(f=>positions(f.geometry)),4)};
$('diag-map').onwheel=e=>{e.preventDefault();if(!view)return;const a=e.deltaY>0?1.18:.85,r=$('diag-map').getBoundingClientRect(),fx=(e.clientX-r.left)/r.width,fy=(e.clientY-r.top)/r.height;view=[view[0]+view[2]*fx*(1-a),view[1]+view[3]*fy*(1-a),view[2]*a,view[3]*a];draw()};$('diag-map').onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,v:view?.slice(),moved:false}};$('diag-map').onpointermove=e=>{if(!drag?.v)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3){drag.moved=true;$('diag-map').setPointerCapture(e.pointerId)}view=[drag.v[0]-dx*drag.v[2]/$('diag-map').clientWidth,drag.v[1]-dy*drag.v[3]/$('diag-map').clientHeight,drag.v[2],drag.v[3]];draw()};$('diag-map').onpointerup=()=>{suppressClick=!!drag?.moved;drag=null;setTimeout(()=>suppressClick=false,0)};window.addEventListener('resize',draw);

async function main(){if(location.protocol==='file:')throw Error('请先按README启动本地服务，再打开 /diagnostics。file://只读文件不能访问实际后端。');const r=await fetch('/api/diagnostics');if(!r.ok)throw Error('诊断接口HTTP '+r.status);payload=await r.json();support=payload.support||null;if(!support){try{const q=await fetch('/api/diagnostics-support');if(q.ok)support=await q.json()}catch(_){/* Main seven-case evidence remains usable. */}}for(const c of payload.cases)$('case-select').add(new Option(c.title,c.id));if(!payload.cases.length)throw Error('没有真实诊断病例，未生成模拟图。');chooseCase(0)}
main().catch(e=>{$('load-error').style.display='block';$('load-error').textContent=e.message;$('diag-status').textContent='诊断资料未加载，未生成替代数据。'});
