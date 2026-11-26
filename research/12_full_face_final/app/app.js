const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
let scenes=[],data=null,last=null,view=null,drag=null,serial=0,features=[],route=[],region=null;
let mapSerial=0,mapLoading=false,mapReady=false,mapError='',planning=false;
let comparison=null,faceLayers=[],portals=[];
function node(type,attrs,props){let n=document.createElementNS(NS,type);for(let[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(props)n.onclick=e=>{if(drag?.moved)return;e.stopPropagation();$('evidence').textContent=JSON.stringify(props,null,2)};return n}
function coords(g){if(g.type==='GeometryCollection')return g.geometries.flatMap(coords);if(g.type==='Point')return[g.coordinates];let a=[];function r(x){if(typeof x[0]==='number')a.push(x);else x.forEach(r)}r(g.coordinates);return a}
function path(g){if(!g)return'';if(g.type==='GeometryCollection')return g.geometries.map(path).join(' ');if(g.type==='Point')return'';let seq=x=>x.map((p,i)=>(i?'L':'M')+p[0]+','+(-p[1])).join(' ');if(g.type==='LineString')return seq(g.coordinates);if(g.type==='MultiLineString')return g.coordinates.map(seq).join(' ');if(g.type==='Polygon')return g.coordinates.map(x=>seq(x)+' Z').join(' ');if(g.type==='MultiPolygon')return g.coordinates.map(p=>p.map(x=>seq(x)+' Z').join(' ')).join(' ');return''}
function fit(points,pad=25){if(!points.length)return;let xs=points.map(p=>p[0]),ys=points.map(p=>-p[1]);let x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;let ratio=$('svg').clientWidth/$('svg').clientHeight;w=Math.max(w+pad*2,80);h=Math.max(h+pad*2,80);if(w/h<ratio)w=h*ratio;else h=w/ratio;view=[x-pad-(w-(Math.max(...xs)-x+pad*2))/2,y-pad-(h-(Math.max(...ys)-y+pad*2))/2,w,h];draw()}
function whole(){let pts=route.flatMap(s=>s.xy);if(comparison)for(const r of comparison.results)pts.push(...(r.route?.segments||[]).flatMap(s=>s.xy));if(data?.doors)pts.push(...data.doors.map(d=>d.xy));if($('start').selectedOptions[0]?.dataset.xy)pts.push(JSON.parse($('start').selectedOptions[0].dataset.xy));if(pts.length)fit(pts,60);else if(features.length)fit(features.flatMap(f=>coords(f.geometry)).filter((_,i)=>i%5===0),15)}
function close(){let d=data?.doors?.find(x=>x.id===$('door').value);if(d)fit([d.xy],38)}
function color(p){let k=p.kind||'',t=p.tags||{};if(k==='ROAD')return{stroke:'#a9a59a',fill:'none',width:2.4};if(k==='NATIVE_WALKWAY')return{stroke:'#6791a4',fill:'none',width:1.2};if(k.includes('BUILDING')||t.building)return{stroke:'#9d978d',fill:'#c6c1b6',width:.65};if(k.includes('GRASS')||k==='FLOWERBED'||t.landuse==='grass')return{stroke:'#abc48c',fill:'#d5e5b9',width:.5};if(k.includes('PEDESTRIAN')||k.includes('WALKABLE'))return{stroke:'#d1b98e',fill:'#ede0bf',width:.6};if(k==='PARK')return{stroke:'#bbd1a6',fill:'#e8edd2',width:.5};if(k.includes('WATER'))return{stroke:'#8eb8c4',fill:'#bfdee3',width:.5};if(k.includes('RESTRICT')||k.includes('BARRIER'))return{stroke:'#9c5b6a',fill:k.includes('LINE')||k.includes('BARRIER')?'none':'#ead6dc',width:1.2};return{stroke:'#b4bbac',fill:'none',width:.5}}
function layerRank(p){let k=p.kind||'',t=p.tags||{};if(k==='PARK')return 0;if(k.includes('GRASS')||k==='FLOWERBED')return 1;if(k.includes('PEDESTRIAN')||k==='PAVING')return 2;if(k.includes('WATER'))return 3;if(k.includes('BUILDING')||t.building)return 4;if(p.layer==='hard')return 5;if(k==='ROAD')return 6;return 7}
function draw(){if(!view)return;const svg=$('svg');svg.replaceChildren();svg.setAttribute('viewBox',view.join(' '));let unit=view[2]/Math.max(svg.clientWidth,1);
 for(let f of features){let p=f.properties||{};if(p.kind==='NATIVE_WALKWAY'&&!$('native').checked)continue;if(p.layer==='hard'&&!$('constraints').checked)continue;let c=color(p);svg.append(node('path',{d:path(f.geometry),stroke:c.stroke,fill:c.fill,'stroke-width':c.width*unit,'fill-rule':'evenodd'},p))}
 drawFaceLayers(svg,unit);
 if(region&&$('areas').checked){for(let[name,c]of[['assumed','#e6b36a'],['native','#80b9ac'],['restricted','#af6a80']])svg.append(node('path',{d:path(region[name]),fill:c,'fill-opacity':name==='restricted'?.26:.25,stroke:c,'stroke-width':.5*unit,'fill-rule':'evenodd'},{state:name,identity:name==='assumed'?'DEFAULT_FREE_POLICY_CONDITIONAL_NOT_SOURCE_FACT':'SOURCE_OR_POLICY',radius_m:30}));svg.append(node('path',{d:path(region.domain),fill:'none',stroke:'#856a39','stroke-width':unit,'stroke-dasharray':`${5*unit} ${4*unit}`},{role:'FIXED_DOOR_CENTRED_PREDICTION_DOMAIN',radius_m:30}))}
 if(data?.coverage_geometry)svg.append(node('path',{d:path(data.coverage_geometry),fill:'none',stroke:'#61716c','stroke-width':1.3*unit,'stroke-dasharray':`${10*unit} ${5*unit}`},{role:'ACTUALLY_ACQUIRED_SOURCE_CLIP_COVERAGE_NOT_COMPLETE_SURVEY'}));
 if(comparison){const other=comparison.results.find(r=>r.area_routing!==$('area-mode').value);for(const s of other?.route?.segments||[])svg.append(node('path',{d:path({type:'LineString',coordinates:s.xy}),fill:'none',stroke:'#687776','stroke-width':5*unit,'stroke-dasharray':`${7*unit} ${4*unit}`},{comparison_area_mode:other.area_routing,...s}))}
 for(let s of route){let p={type:'LineString',coordinates:s.xy},c=s.layer==='native'?'#1767a4':s.geometry_kind==='DERIVED_WITHIN_MAPPED_PEDESTRIAN_FACE'?'#7e3fba':s.layer==='derived'?'#008b82':'#e35837';svg.append(node('path',{d:path(p),fill:'none',stroke:'#ffffff','stroke-width':6*unit}));svg.append(node('path',{d:path(p),fill:'none',stroke:c,'stroke-width':3.4*unit,'stroke-linecap':'round',...(s.layer==='inferred'?{'stroke-dasharray':`${6*unit} ${3*unit}`}:{})},s))}
 const door=data?.doors?.find(d=>d.id===$('door').value);if(door){let x=door.xy[0],y=-door.xy[1];svg.append(node('circle',{cx:x,cy:y,r:8*unit,fill:'#fff',stroke:'#972c26','stroke-width':unit},door));let star=node('text',{x,y:y+5*unit,'text-anchor':'middle','font-size':17*unit,fill:'#a9352a'},door);star.textContent='★';svg.append(star)}
 let st=$('start').selectedOptions[0];if(st?.dataset.xy){let xy=JSON.parse(st.dataset.xy);svg.append(node('circle',{cx:xy[0],cy:-xy[1],r:5*unit,fill:'#243e92',stroke:'white','stroke-width':2*unit},{role:'EXACT_SELECTED_NATIVE_START',id:st.value,xy}))}
 let metres=view[2]/6,base=10**Math.floor(Math.log10(metres)),len=[1,2,5,10].map(x=>x*base).find(x=>x>=metres/2&&x<=metres*1.5)||base;$('scale').style.width=(len/unit)+'px';$('scale').textContent=len+' m';
}
function syncMapControls(){
 $('compute').disabled=mapLoading||!mapReady||planning||!$('start').value||!$('door').value;
 $('compare').disabled=$('compute').disabled;
 $('start').disabled=mapLoading||!mapReady||!$('start').value;
 $('map-notice').hidden=mapReady&&!mapLoading;
 $('map-notice-text').textContent=mapLoading?'正在载入地图和可选起点，请稍候…':mapError||'地图尚未载入。';
 $('retry-map').hidden=mapLoading||mapReady;
 $('svg').setAttribute('aria-busy',String(mapLoading));
}
function stale(){
 // Route inputs invalidate route answers, never an unrelated map request.
 serial++;last=null;comparison=null;route=[];region=null;$('json').disabled=$('geojson').disabled=true;
 $('status').textContent=mapLoading?'正在载入地图和可选起点，请稍候…':!mapReady?mapError||'地图尚未就绪。': '输入已变化。点击计算，生成本次新路线。';
 $('metrics').textContent='';syncMapControls();draw();
}
async function loadScene(){
 const token=++mapSerial,sceneId=$('scene').value,doorId=$('door').value;
 mapLoading=true;mapReady=false;mapError='';data=null;features=[];view=null;faceLayers=[];portals=[];
 $('svg').replaceChildren();$('start').replaceChildren(new Option('地图载入后可选择起点',''));
 stale();
 try{
  let url='/api/scene?scene_id='+encodeURIComponent(sceneId);
  if(doorId)url+='&door_id='+encodeURIComponent(doorId);
  const r=await fetch(url),d=await r.json();
  // Only a scene/door change supersedes map data. Method/purpose changes do not.
  if(token!==mapSerial)return;
  if(!r.ok)throw Error(d.error||'HTTP '+r.status);
  const layers=Array.isArray(d.map_layers)?d.map_layers:d.map_layers?.features;
  if(!Array.isArray(layers)||!Array.isArray(d.starts))throw Error('地图或起点响应不完整');
  data=d;features=layers.slice().sort((a,b)=>layerRank(a.properties||{})-layerRank(b.properties||{}));
  $('start').replaceChildren();
  const diagnostic=d.starts.filter(s=>s.distance_to_door_m>=50&&s.distance_to_door_m<=200);
  for(const s of diagnostic.length?diagnostic:d.starts){
   const o=new Option(`${s.label||s.id} · ${s.distance_to_door_m?.toFixed(1)||'?'}m`,s.id);
   o.dataset.xy=JSON.stringify(s.xy);$('start').add(o);
  }
  if(!$('start').options.length)$('start').add(new Option('当前目标没有可用的规划起点',''));
  mapLoading=false;mapReady=true;syncMapControls();
  $('status').textContent=d.doors?.length? '地图和起点已就绪。请选择起点，再计算路线。':'该目标建筑没有原生登记门。地图仍可查看。';
  $('record').textContent=JSON.stringify({source:d.source_info,doors:d.doors,shown_starts:Array.from($('start').options).filter(o=>o.value).length,available_starts:d.starts.length},null,2);
  whole();
 }catch(e){
  if(token!==mapSerial)return;
  mapLoading=false;mapReady=false;mapError='地图载入失败：'+e.message;
  $('status').textContent=mapError+'。请点击“重新加载地图”。';syncMapControls();
 }
}
function doorsForScene(){let s=scenes.find(s=>s.scene_id===$('scene').value);$('door').replaceChildren();for(let d of s?.doors||[])$('door').add(new Option(`${d.id} · ${d.tags?.entrance||'入口'}${d.tags?.entrance==='exit'?'（仅门外）':''}`,d.id));if(!$('door').options.length)$('door').add(new Option('无适用登记门',''));loadScene()}
function drawFaceLayers(svg,unit){
 if($('show-faces').checked)for(const f of faceLayers){if(!f.omega)continue;svg.append(node('path',{d:path(f.omega),fill:'#8bb9dd','fill-opacity':.21,stroke:'#446a9c','stroke-width':1.1*unit,'fill-rule':'evenodd'},{source_area_id:f.source_id,geometry_sha256:f.geometry_hash,domain:'FULL_LEGAL_MAPPED_PEDESTRIAN_FACE',clearance_m:f.clearance_m,holes_retained:true}))}
 if($('show-band').checked)for(const f of faceLayers){if(f.edge_band_geometry)svg.append(node('path',{d:path(f.edge_band_geometry),fill:'#c79555','fill-opacity':.3,stroke:'#a37d43','stroke-width':.6*unit,'fill-rule':'evenodd'},{source_area_id:f.source_id,domain:'OLD_3M_BAND_GEOMETRY_REFERENCE_ACTUAL_OLD_GRAPH_FROZEN'}))}
 if($('show-portals').checked)for(const p of portals)svg.append(node('circle',{cx:p.xy[0],cy:-p.xy[1],r:2.2*unit,fill:'#376d4e',stroke:'#fff','stroke-width':.7*unit},p));
}
function summaryText(r){
 if(!r.route)return r.area_routing+'：'+r.status+'；'+JSON.stringify(r.failure);
 const x=r.route;return r.area_routing+'：'+x.length_m.toFixed(2)+' m；代价 '+x.cost_weighted_m.toFixed(2)+' 加权米；完整面穿行 '+(x.source_lengths_m?.full_face_derived||0).toFixed(2)+' m；旧带外 '+(x.full_face_outside_old_band_m||0).toFixed(2)+' m；假设 '+(x.layer_lengths_m.inferred+x.layer_lengths_m.unknown).toFixed(2)+' m';
}
async function calculate(compare){
 if(mapLoading||!mapReady||!$('start').value||!$('door').value||planning){syncMapControls();return}
 const n=++serial;planning=true;last=null;comparison=null;route=[];region=null;syncMapControls();$('json').disabled=$('geojson').disabled=true;draw();
 const input={scene_id:$('scene').value,door_id:$('door').value,start_id:$('start').value,method:$('method').value,purpose:$('purpose').value};
 const selectedMode=$('area-mode').value,modes=compare?['EDGE_BAND','FULL_FACE']:[selectedMode],results=[];
 const start=Date.now();const timer=setInterval(()=>{if(n===serial)$('status').textContent='正在实际计算 '+modes[results.length]+'，已等待 '+Math.floor((Date.now()-start)/1000)+' 秒。首次建图较慢；每种模式均调用真实求解器。'},1000);
 try{
  for(const mode of modes){const request={...input,area_routing:mode,request_id:'UI-'+crypto.randomUUID()};$('status').textContent='正在实际计算 '+mode+'…';const response=await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});const r=await response.json();if(n!==serial)return;if(!response.ok)throw Error(r.detail||r.error);results.push(r)}
  last=results.find(r=>r.area_routing===selectedMode)||results[0];comparison=compare?{input,selectedMode,results}:null;
  route=last.route?.segments||[];region=last.planning_region||null;
  const full=results.find(r=>r.area_routing==='FULL_FACE');faceLayers=full?.mapped_faces||last.mapped_faces||faceLayers;portals=full?.face_network?.portals||last.face_network?.portals||[];
  $('json').disabled=false;$('geojson').disabled=!results.some(r=>r.route);$('status').textContent=(compare?'两种模式均已实际计算':'本次计算完成')+' · 当前主线 '+last.area_routing+'\n'+last.status+' · '+last.run_id;
  let text=results.map(summaryText).join('\n');if(compare&&results.every(r=>r.route)){const old=results[0].route,fresh=results[1].route;text+='\n同起终点几何缩短 '+(old.length_m-fresh.length_m).toFixed(2)+' m；代价减少 '+(old.cost_weighted_m-fresh.cost_weighted_m).toFixed(2)+' 加权米'}
  $('metrics').textContent=text;$('metrics').style.whiteSpace='pre-line';$('record').textContent=JSON.stringify({comparison:!!comparison,results:results.map(r=>({request:r.normalized_request||r.input,run_id:r.run_id,solver:r.solver,cache:r.preprocessing_cache,versions:r.versions,failure:r.failure,face_network:r.face_network}))},null,2);whole();
 }catch(e){if(n===serial)$('status').textContent='本次计算失败：'+e.message}
 finally{clearInterval(timer);planning=false;syncMapControls()}
}
$('compute').onclick=()=>calculate(false);$('compare').onclick=()=>calculate(true);
function download(value,name){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}
$('json').onclick=()=>last&&download(comparison||last,last.run_id+(comparison?'-comparison':'')+'.json');$('geojson').onclick=()=>{if(!last)return;const rs=comparison?comparison.results:[last];download({type:'FeatureCollection',crs:{type:'name',properties:{name:'EPSG:32651'}},features:rs.flatMap(r=>(r.route?.geojson.features||[]).map(f=>({...f,properties:{...f.properties,area_routing:r.area_routing,run_id:r.run_id}})))},last.run_id+'.geojson')};$('scene').onchange=doorsForScene;$('door').onchange=loadScene;for(let k of['start','purpose','method','area-mode'])$(k).onchange=stale;for(let k of['areas','native','constraints','show-faces','show-band','show-portals'])$(k).onchange=draw;$('full').onclick=whole;$('close').onclick=close;$('face-view').onclick=()=>{let points=faceLayers.flatMap(f=>f.source_geometry?coords(f.source_geometry):[]);if(points.length)fit(points,12);else whole()};
$('svg').onwheel=e=>{e.preventDefault();if(!view)return;let a=e.deltaY>0?1.18:.85,r=$('svg').getBoundingClientRect(),fx=(e.clientX-r.left)/r.width,fy=(e.clientY-r.top)/r.height;view=[view[0]+view[2]*fx*(1-a),view[1]+view[3]*fy*(1-a),view[2]*a,view[3]*a];draw()};$('svg').onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,v:view?.slice(),moved:false};};$('svg').onpointermove=e=>{if(!drag?.v)return;let dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3){drag.moved=true;$('svg').setPointerCapture(e.pointerId)}view=[drag.v[0]-dx*drag.v[2]/$('svg').clientWidth,drag.v[1]-dy*drag.v[3]/$('svg').clientHeight,drag.v[2],drag.v[3]];draw()};$('svg').onpointerup=()=>setTimeout(()=>drag=null,0);window.onresize=draw;
async function initialise(){
 mapLoading=true;mapReady=false;mapError='';syncMapControls();
 $('status').textContent='正在读取场景和地图…';
 try{
  const r=await fetch('/api/scenes');if(!r.ok)throw Error('场景接口HTTP '+r.status);
  const d=await r.json();scenes=Array.isArray(d)?d:d.scenes;
  if(!Array.isArray(scenes)||!scenes.length)throw Error('没有可用场景');
  $('scene').replaceChildren();
  for(const item of scenes)$('scene').add(new Option(item.name||item.label||item.scene_id,item.scene_id));
  doorsForScene();
 }catch(e){mapLoading=false;mapReady=false;mapError='服务或场景载入失败：'+e.message;$('status').textContent=mapError;syncMapControls()}
}
$('retry-map').onclick=()=>scenes.length?loadScene():initialise();
if(location.protocol==='file:'){
 mapError='请先启动本地计算服务，再打开127.0.0.1地址。';syncMapControls();$('retry-map').hidden=true;$('status').textContent=mapError;
}else initialise();
