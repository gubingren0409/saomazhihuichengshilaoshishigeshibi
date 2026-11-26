'use strict';
(() => {
 const NS='http://www.w3.org/2000/svg';
 const data=window.TRIAL_DATA;
 const $=id=>document.getElementById(id);
 const layers=[['road_axis','道路轴','#70757a',''],['native','原生步道','#5b9fbe',''],['tag_derived','标签派生侧向通道','#8177a8','5 3'],['hypothesis','默认假设侧向通道','#d49757','7 5'],['crossing','原有过街','#b97589',''],['constraints','原始地图约束','#857d70','']];
 let wi=0,qi=0,view=null,drag=null;
 const enabled=new Set(layers.map(x=>x[0]));
 function kind(e){let l=String(e.layer||e.evidence||e.kind||'').toLowerCase();
  if(/cross/.test(l))return 'crossing';if(/hyp|conditional|default/.test(l))return 'hypothesis';
  if(/side.*tag|tag.*side|tag_derived|tag_supported|tagged_side|explicit_side/.test(l))return 'tag_derived';
  if(/native|footway|sidewalk/.test(l))return 'native';if(/road|axis|shared/.test(l))return 'road_axis';
  return e.side&&e.side!=='axis'?'tag_derived':'native';}
 function geomOf(f){return f.geometry||f.geom||null;}
 function baseKind(f){const t=f.tags||{};if(t.highway==='crossing'||t.crossing)return 'crossing';if(t.highway&&['footway','path','pedestrian','steps','cycleway'].includes(t.highway)){return t.footway==='crossing'?'crossing':'native';}if(t.highway)return 'road_axis';return 'constraints';}
 function create(tag,attrs,parent){let e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs||{}))e.setAttribute(k,v);if(parent)parent.appendChild(e);return e;}
 function pathLine(xy){return (xy||[]).map((p,i)=>(i?'L':'M')+p[0]+','+(-p[1])).join(' ');}
 function pathGeom(g){if(!g)return '';let c=g.coordinates||[];if(g.type==='LineString')return pathLine(c);if(g.type==='MultiLineString')return c.map(pathLine).join(' ');if(g.type==='Polygon')return c.map(r=>pathLine(r)+' Z').join(' ');if(g.type==='MultiPolygon')return c.flatMap(p=>p.map(r=>pathLine(r)+' Z')).join(' ');return '';}
 function points(g){if(!g)return [];let c=g.coordinates;if(g.type==='Point')return [c];if(g.type==='MultiPoint'||g.type==='LineString')return c;if(g.type==='Polygon'||g.type==='MultiLineString')return c.flat();if(g.type==='MultiPolygon')return c.flat(2);return [];}
 function allXY(){let w=data.windows[wi];return (w.source_features||[]).flatMap(f=>points(geomOf(f)));}
 function reset(){const w=data.windows[wi];let b=w.bounds_xy;if(!b){const p=allXY();b=[Math.min(...p.map(x=>x[0])),Math.min(...p.map(x=>x[1])),Math.max(...p.map(x=>x[0])),Math.max(...p.map(x=>x[1]))];}let m=.025*Math.max(b[2]-b[0],b[3]-b[1]);view=[b[0]-m,b[1]-m,b[2]+m,b[3]+m];render();}
 function query(){return (data.windows[wi].queries||[])[qi]||{};}
 function showEvidence(value){$('evidence').textContent=JSON.stringify(value,null,2);}
 function summary(w,v){let q=query(),r=(q.results||{})[v]||{};let edges=(w.variants[v]||{}).edges||[];
  let counts={};for(let e of edges){let k=kind(e);counts[k]=(counts[k]||0)+1;}
  return {query:q.query_id,description:q.description,status:r.status||'NO_SAVED_RESULT',edge_count:edges.length,layer_counts:counts,result:r};}
 function fmtCost(r){if(r.cost_f1_proxy!=null)return 'F1 代理代价 '+Number(r.cost_f1_proxy).toFixed(2);if(r.cost_f1!=null)return 'F1 拓扑代价 '+Number(r.cost_f1).toFixed(2);if(r.cost!=null)return '拓扑代价 '+Number(r.cost).toFixed(2);return '';}
 function render(){if(!view)return;let w=data.windows[wi];const width=view[2]-view[0],height=view[3]-view[1];
  $('window-note').textContent=(w.label||w.window_id)+' · '+w.scene_id+' · '+(w.source_timestamp||'时相见原始来源')+' · EPSG:32651 米制工作坐标';
  $('source-hash').textContent='冻结来源 SHA256：'+(w.source_sha256||'见逐源证据表');
  for(let variant of ['R0','R1','R2']){let svg=$('map-'+variant);svg.replaceChildren();svg.setAttribute('viewBox',[view[0],-view[3],width,height].join(' '));
   let s=summary(w,variant),r=s.result; $('summary-'+variant).textContent=(r.status||'未提供本查询结果')+(r.status==='ZERO_LENGTH_COLLAPSED_SIDE_ALIAS'?'（侧别被压成同点，不能算成功）':'')+' · '+s.edge_count+' 条图边'+(fmtCost(r)?' · '+fmtCost(r):'');
   let base=create('g',{},svg);const stroke=width/700;
   for(let f of w.source_features||[]){let k=baseKind(f),g=geomOf(f);if(!g||!enabled.has(k))continue;let t=f.tags||{},poly=/Polygon/.test(g.type);
    let fill=poly?(t.building?'#d7d3cf':t.landuse==='grass'||t.natural==='wood'||t.leisure==='garden'?'#dce6d0':t.natural==='water'?'#d3eaf5':t.highway==='pedestrian'||t.area==='yes'?'#d3eaf580':'#f5d9b860'):'none';
    let p=create('path',{d:pathGeom(g),fill,'fill-rule':'evenodd',stroke:poly?'#aaa297':k==='native'?'#5b9fbe':k==='crossing'?'#b97589':'#969b9f','stroke-width':poly?stroke*.6:stroke*1.2,'opacity':poly?'.9':k==='native'?'.35':'.7'},base);
    if(!pathGeom(g)&&g.type==='Point'){p.remove();p=create('circle',{cx:g.coordinates[0],cy:-g.coordinates[1],r:stroke*2,fill:'#857d70'},base);}
    p.addEventListener('click',e=>{e.stopPropagation();showEvidence({identity:'FROZEN_SOURCE_OBJECT',...f});});
    if(k==='road_axis'&&t.name&&g.type==='LineString'){const c=g.coordinates,p0=c[Math.floor(c.length/2)];let text=create('text',{x:p0[0],y:-p0[1],fill:'#70757a','font-size':width/46,'paint-order':'stroke',stroke:'#fcfaf7','stroke-width':stroke*1.3},base);text.textContent=t.name;}
   }
   let edges=(w.variants[variant]||{}).edges||[],byId=new Map(edges.map(e=>[String(e.edge_id),e]));
   for(let e of edges){let k=kind(e);if(!enabled.has(k))continue;let l=layers.find(x=>x[0]===k)||layers[1];let xy=e.xy||e.coordinates||(e.geometry||{}).coordinates;if(!xy)continue;let p=create('path',{d:pathLine(xy),fill:'none',stroke:l[2],'stroke-width':stroke*2,'stroke-dasharray':l[3]?l[3].split(' ').map(x=>Number(x)*stroke).join(' '):'',opacity:'.85'},svg);p.addEventListener('click',ev=>{ev.stopPropagation();showEvidence({variant,identity:e.geometry_status||'SEE_EVIDENCE',...e});});}
   let routeids=r.edge_ids||r.path_edge_ids||[];
   if($('show-route').checked)for(let eid of routeids){let e=byId.get(String(eid));if(!e)continue;let k=kind(e),xy=e.xy||e.coordinates||(e.geometry||{}).coordinates;if(!xy)continue;create('path',{d:pathLine(xy),fill:'none',stroke:'#fcfaf7','stroke-width':stroke*6},svg);let p=create('path',{d:pathLine(xy),fill:'none',stroke:'#2d3238','stroke-width':stroke*3.2,'stroke-dasharray':k==='hypothesis'?[6*stroke,4*stroke].join(' '):e.geometry_status==='SCHEMATIC'?[3*stroke,2*stroke].join(' '):''},svg);p.addEventListener('click',ev=>{ev.stopPropagation();showEvidence({identity:'SAVED_FORMAL_ROUTE_EDGE',variant,query_id:query().query_id,...e});});}
   let bind=(query().bindings||{})[variant]||{};for(let [name,id,col]of [['起',bind.start,'#2d3238'],['终',bind.end,'#a24860']]){let np=(w.nodes||{})[id];if(np&&np.xy)np=np.xy;if(!np)continue;create('circle',{cx:np[0],cy:-np[1],r:stroke*5,fill:col,stroke:'#fcfaf7','stroke-width':stroke*1.4},svg);let text=create('text',{x:np[0]+7*stroke,y:-np[1]-5*stroke,'font-size':stroke*15,fill:col},svg);text.textContent=name;}
   let bar=width*.18,power=10**Math.floor(Math.log10(bar));bar=Math.max(power,Math.round(bar/power)*power);let bx=view[0]+width*.04,by=-view[1]-height*.055;create('path',{d:`M${bx},${by}h${bar}m-${bar},-${stroke*3}v${stroke*6}m${bar},-${stroke*6}v${stroke*6}`,stroke:'#2d3238','stroke-width':stroke*1.2,fill:'none'},svg);let st=create('text',{x:bx,y:by-stroke*6,'font-size':stroke*12,fill:'#2d3238'},svg);st.textContent=bar+' m（原始底图尺度）';
  }
  $('request').textContent=JSON.stringify({identity:'SAVED_FORMAL_QUERY_DISPLAY_NO_NEW_SOLVER_CALL',window_id:w.window_id,query:query(),display_bounds_xy:view,layers:[...enabled]},null,2);
  let rows=['<tr><th>变体</th><th>状态</th><th>边数</th><th>事实/假设</th></tr>'];for(let v of ['R0','R1','R2']){let s=summary(w,v);rows.push(`<tr><td>${v}</td><td>${s.status}</td><td>${s.edge_count}</td><td>${JSON.stringify(s.layer_counts)}</td></tr>`);} $('results').innerHTML=rows.join('');
 }
 function exportJSON(value,filename){let blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
 function setQueries(){let w=data.windows[wi];$('query').replaceChildren();for(let [i,q]of(w.queries||[]).entries()){let o=document.createElement('option');o.value=i;o.textContent=q.query_id+' · '+(q.description||'');$('query').appendChild(o);}qi=0;}
 try{if(!data||!data.windows||!data.windows.length)throw Error('没有生成本轮地图数据。请先运行构图实验，再运行 build_visuals.py --maps；页面不会以空白冒充成功。');
  for(let [i,w]of data.windows.entries()){let o=document.createElement('option');o.value=i;o.textContent=w.label||w.window_id;$('window').appendChild(o);}
  for(let [id,name,col,dash]of layers){let label=document.createElement('label'),input=document.createElement('input'),mark=document.createElement('span');input.type='checkbox';input.checked=true;mark.className='swatch';mark.style.borderColor=col;if(dash)mark.style.borderTopStyle='dashed';label.append(input,mark,document.createTextNode(name));$('layers').appendChild(label);input.addEventListener('change',()=>{input.checked?enabled.add(id):enabled.delete(id);render();});}
  $('window').onchange=()=>{wi=Number($('window').value);setQueries();reset();};$('query').onchange=()=>{qi=Number($('query').value);render();};$('show-route').onchange=render;$('reset').onclick=reset;
  $('export').onclick=()=>exportJSON({identity:'SAVED_FORMAL_QUERY_DISPLAY_NO_NEW_SOLVER_CALL',window_id:data.windows[wi].window_id,query:query(),display_bounds_xy:view,visible_layers:[...enabled],source_sha256:data.windows[wi].source_sha256},'street-side-request-view.json');
  $('evidence-export').onclick=()=>{try{exportJSON(JSON.parse($('evidence').textContent),'selected-object-evidence.json');}catch(e){showEvidence({message:'请先点选地图中的具体对象。'});}};
  for(let v of ['R0','R1','R2']){let svg=$('map-'+v);svg.addEventListener('wheel',e=>{e.preventDefault();let p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;p=p.matrixTransform(svg.getScreenCTM().inverse());let ww=view[2]-view[0],hh=view[3]-view[1],cx=p.x,cy=-p.y,x=(cx-view[0])/ww,y=(cy-view[1])/hh,f=e.deltaY>0?1.2:1/1.2;view=[cx-x*ww*f,cy-y*hh*f,cx+(1-x)*ww*f,cy+(1-y)*hh*f];render();},{passive:false});svg.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,view:[...view],moved:false};});svg.addEventListener('pointermove',e=>{if(!drag)return;if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)<=4&&!drag.moved)return;drag.moved=true;svg.setPointerCapture(e.pointerId);let matrix=svg.getScreenCTM(),dx=(e.clientX-drag.x)/matrix.a,dy=(e.clientY-drag.y)/matrix.d;view=[drag.view[0]-dx,drag.view[1]+dy,drag.view[2]-dx,drag.view[3]+dy];render();});svg.addEventListener('pointerup',()=>drag=null);svg.addEventListener('pointercancel',()=>drag=null);}
  setQueries();reset();showEvidence({message:'点击道路、原生步道、派生侧向边或约束对象查看来源；橙色虚线是条件假设，偏移不是测得的人行道位置。'});window.STREET_VIEWER={data,render,reset,getState:()=>({wi,qi,view:[...view]})};
 }catch(e){$('error').textContent=e.message;console.error(e);}
})();
