/* Target-anchored frozen OSM viewer. No routing, graph building or external request. */
(() => {
 'use strict';
 const NS='http://www.w3.org/2000/svg',DATA=window.RECON_MAP_INPUT,$=id=>document.getElementById(id);
 const panels=['context','R0','R1','R2'];
 const scene=DATA.scene, native=DATA.trial.windows.find(w=>w.window_id==='native'),views=scene.views;
 let qi=0,view=null,selection=null,drag=null,viewId='target_overview';
 const ctx=()=>scene,win=()=>native,query=()=>native.queries[qi];
 const specs=[['target_identity','目标博物馆/原门','#b97589','fill'],['buildings','建筑','#d1cfca','fill'],
 ['road_centerlines','原生道路中心线','#555b61','line'],['road_areas','原生道路面','#d9d6cf','fill'],['road_names','道路名称/分类','#2d3238','line'],
 ['native_walkways','原生步行线','#5b9fbe','line'],['sidewalks','独立人行道','#5b9fbe','line'],['crossings','原生过街','#b97589','line'],
 ['traffic_facilities','交通信号/设施','#b97589','line'],['pedestrian_areas','步行面/广场','#f5d9b8','fill'],['vegetation','公园/草地','#dfe9d6','fill'],
 ['water','水体','#d3eaf5','fill'],['barriers','墙/围栏/障碍','#8177a8','line'],['railway','铁路/地下轨道','#70757a','dash'],
 ['restrictions','原始限制标签','#8177a8','dash'],['cycleways','车道/自行车属性(不造几何)','#70757a','line'],['levels','层级属性','#70757a','line'],
 ['poi','地点/POI','#70757a','line'],['other_context','其他源上下文','#70757a','line'],
 ['R0','原R0诊断','#2d3238','line'],['R1','原R1诊断','#8177a8','dash'],['R2','原R2条件侧道','#d49757','dash'],['route_markers','旧诊断路线/非门端点','#2d3238','line']];
 const enabled=new Set(specs.map(x=>x[0]));
 const roadIds=new Set(scene.road.road_way_ids),bboxCache=new Map();
 const number=x=>Number(x).toFixed(2), idOf=f=>f.source_id||`${f.type}/${f.id}`;
 function el(tag,attrs={},parent){let e=document.createElementNS(NS,tag);for(let[k,v]of Object.entries(attrs))if(v!==undefined&&v!==null)e.setAttribute(k,String(v));if(parent)parent.appendChild(e);return e;}
 function text(parent,x,y,value,size,attrs={}){let e=el('text',{x,y,'font-size':size,'paint-order':'stroke',stroke:'#fcfaf7','stroke-width':size*.28,'stroke-linejoin':'round',...attrs},parent);e.textContent=value;return e;}
 function linePath(cs){return cs.map((p,i)=>`${i?'L':'M'}${p[0]},${-p[1]}`).join(' ');}
 function geomPath(g){if(!g)return'';let c=g.coordinates;switch(g.type){case'LineString':return linePath(c);case'MultiLineString':return c.map(linePath).join(' ');case'Polygon':return c.map(r=>linePath(r)+'Z').join(' ');case'MultiPolygon':return c.flatMap(p=>p.map(r=>linePath(r)+'Z')).join(' ');default:return'';}}
 function coords(g){if(!g)return[];switch(g.type){case'Point':return[g.coordinates];case'MultiPoint':return g.coordinates;case'LineString':return g.coordinates;case'MultiLineString':return g.coordinates.flat();case'Polygon':return g.coordinates[0]||[];case'MultiPolygon':return g.coordinates.flatMap(p=>p[0]||[]);case'GeometryCollection':return(g.geometries||[]).flatMap(coords);default:return[];}}
 function inView(p){return p[0]>=view[0]&&p[0]<=view[2]&&p[1]>=view[1]&&p[1]<=view[3];}
 function featureFamilies(f){return f.families||f.kind||['other_context'];}
 function displayFamily(f){const fs=featureFamilies(f),primary=['water','vegetation','pedestrian_areas','road_areas','buildings','crossings','traffic_facilities','road_centerlines','sidewalks','native_walkways','railway','barriers','restrictions','poi','other_context'].find(x=>fs.includes(x));return enabled.has(primary)?primary:null;}
 function isArea(g){return g&&['Polygon','MultiPolygon'].includes(g.type);}
 function style(f,fam){let t=f.tags||{},poly=isArea(f.geometry),s={fill:'none',stroke:'#70757a',width:1,dash:null};
  if(fam==='buildings')s={fill:poly?'#d1cfca':'none',stroke:'#858782',width:.9};
  if(fam==='vegetation')s={fill:poly?(t.landuse==='grass'||t.landcover==='grass'?'#e7efde':'#dfe9d6'):'none',stroke:'#9aaa8b',width:.8};
  if(fam==='water')s={fill:poly?'#d3eaf5':'none',stroke:'#5b9fbe',width:poly?.8:1.7};
  if(fam==='pedestrian_areas')s={fill:poly?'#f5d9b8':'none',stroke:'#b7a183',width:.8};
  if(fam==='road_areas')s={fill:poly?'#dedbd5':'none',stroke:'#93908b',width:1};
  if(fam==='road_centerlines'){let h=t.highway||'';let width=/^(motorway|trunk|primary)/.test(h)?4.5:/^secondary/.test(h)?3.5:/^tertiary/.test(h)?3.1:/^(residential|unclassified|living_street)/.test(h)?2.5:1.5;s={fill:'none',stroke:'#555b61',width,dash:t.tunnel==='yes'?'6 3':null};}
  if(fam==='native_walkways'||fam==='sidewalks')s={fill:poly?'#f5d9b8':'none',stroke:'#4386a2',width:1.8,dash:t.highway==='steps'?'2 2':null};
  if(fam==='crossings')s={fill:'none',stroke:'#b97589',width:2.6,dash:'3 2'};
  if(fam==='traffic_facilities')s={fill:'#fffdfc',stroke:'#b97589',width:1.4};
  if(fam==='railway')s={fill:'none',stroke:'#70757a',width:1.7,dash:t.tunnel==='yes'||Number(t.layer)<0?'2 4':'7 3'};
  if(fam==='restrictions')s={fill:poly?'none':'#8177a8',stroke:'#8177a8',width:1.5,dash:'3 3'};
  if(fam==='barriers')s={fill:'none',stroke:'#8177a8',width:2,dash:t.barrier==='fence'?'3 2':null};
  if(fam==='poi'||fam==='other_context')s={fill:poly?'none':'#70757a',stroke:poly?'#92999a':'#fcfaf7',width:poly?.8:.6};return s;
 }
 function sha256(value){
  const bytes=new TextEncoder().encode(value),length=bytes.length,words=[];
  for(let i=0;i<length;i++)words[i>>2]=(words[i>>2]||0)|(bytes[i]<<(24-(i%4)*8));
  words[length>>2]=(words[length>>2]||0)|(0x80<<(24-(length%4)*8));
  words[(((length+8)>>6)+1)*16-1]=length*8;
  const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],ro=(x,n)=>(x>>>n)|(x<<(32-n));
  for(let p=0;p<words.length;p+=16){let w=[];for(let i=0;i<64;i++){if(i<16)w[i]=words[p+i]|0;else{let x=w[i-15],y=w[i-2];w[i]=(w[i-16]+(ro(x,7)^ro(x,18)^(x>>>3))+w[i-7]+(ro(y,17)^ro(y,19)^(y>>>10)))|0;}}
   let[a,b,c,d,e,f,g,z]=h;for(let i=0;i<64;i++){let t1=(z+(ro(e,6)^ro(e,11)^ro(e,25))+((e&f)^((~e)&g))+K[i]+w[i])|0,t2=((ro(a,2)^ro(a,13)^ro(a,22))+((a&b)^(a&c)^(b&c)))|0;z=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;}for(let[i,x]of[a,b,c,d,e,f,g,z].entries())h[i]=(h[i]+x)|0;
  }return h.map(x=>(x>>>0).toString(16).padStart(8,'0')).join('');
 }
 function geometryVisible(g){let key=g.coordinates||g;if(!bboxCache.has(key)){let ps=coords(g);bboxCache.set(key,ps.length?[Math.min(...ps.map(p=>p[0])),Math.min(...ps.map(p=>p[1])),Math.max(...ps.map(p=>p[0])),Math.max(...ps.map(p=>p[1]))]:null);}let b=bboxCache.get(key);return b&&b[0]<=view[2]&&b[2]>=view[0]&&b[1]<=view[3]&&b[3]>=view[1];}
 function sourceFeature(id){return scene.features.find(f=>idOf(f)===id);}
 function originalObjectEvidence(f){return {identity:'ORIGINAL_FROZEN_OSM_TARGET_CONTEXT',OSM_type_id:idOf(f),source:scene.source,
  target_building_id:scene.target.building_id,raw_tags:f.tags,geometry_type:f.geometry?.type,
  graph_reference_roles:Object.fromEntries(['R0','R1','R2'].map(v=>[v,{source_edge_ids:native.variants[v].edges.filter(e=>e.source_id===idOf(f)&&e.geometry_status==='SOURCE_GEOMETRY').map(e=>e.edge_id),derived_parent_ids:native.variants[v].edges.filter(e=>e.source_id===idOf(f)&&e.geometry_status==='SCHEMATIC').map(e=>e.edge_id)}])),
  graph_reference_scope:'Original northwest-sidewalk diagnostic only, not a new museum-door query',...f};}
 function sourceEvidence(f){return originalObjectEvidence(f);}
 function evidence(obj){selection=obj;$('evidence').textContent=JSON.stringify(obj,null,2);window.RECON_MAP_SELECTION=obj;}
 function labelAnchor(f){let points=coords(f.geometry).filter(inView);if(points.length)return points[Math.floor(points.length/2)];return null;}
 function drawTarget(parent,unit){if(!enabled.has('target_identity'))return;
  let building=sourceFeature(scene.target.building_id),geometry=scene.target.geometry;
  if(geometryVisible(geometry)){let g=el('g',{'class':'target-identity target-outline','data-target-building-id':scene.target.building_id,'data-source-id':scene.target.building_id},parent);
   el('path',{d:geomPath(geometry),fill:'#e8c7d3',stroke:'#b97589','stroke-width':3.3,'fill-opacity':'.72','fill-rule':'evenodd','vector-effect':'non-scaling-stroke'},g);
   g.addEventListener('click',ev=>{ev.stopPropagation();evidence({...originalObjectEvidence(building),target_binding:scene.target});});
   let ps=coords(geometry),center=scene.target.centroid_xy||scene.target.target?.centroid_xy;if(!Array.isArray(center))center=[ps.reduce((s,p)=>s+p[0],0)/ps.length,ps.reduce((s,p)=>s+p[1],0)/ps.length];
   if(inView(center)){text(g,center[0],-center[1]-7*unit,'上海博物馆',18*unit,{'text-anchor':'middle','font-weight':'700',fill:'#7b354e'});text(g,center[0],-center[1]+10*unit,'人民广场馆 · way/161090899',10.6*unit,{'text-anchor':'middle',fill:'#7b354e'});}
  }
  for(let door of scene.target.doors){let p=door.xy;if(!inView(p))continue;let exit=door.tags.entrance==='exit',g=el('g',{'class':'target-marker','data-source-id':door.source_id,'data-door-id':door.source_id,'data-door-role':door.tags.entrance},parent),r=5*unit;
   if(exit)el('path',{d:`M${p[0]},${-p[1]-r}L${p[0]+r},${-p[1]+r}L${p[0]-r},${-p[1]+r}Z`,fill:'#b97589',stroke:'#fffdfc','stroke-width':1.7,'vector-effect':'non-scaling-stroke'},g);
   else el('circle',{cx:p[0],cy:-p[1],r,fill:'#28647c',stroke:'#fffdfc','stroke-width':1.7,'vector-effect':'non-scaling-stroke'},g);
   let label=exit?'北侧 EXIT · 仅门外':'南门 · entrance=main';text(g,p[0]+8*unit,-p[1]+(exit?-9:16)*unit,label,12*unit,{'font-weight':'700',fill:exit?'#7b354e':'#28647c'});
   text(g,p[0]+8*unit,-p[1]+(exit?-22:29)*unit,door.source_id,9.5*unit,{fill:'#5a5b5f'});
   g.addEventListener('click',ev=>{ev.stopPropagation();evidence({identity:'VERIFIED_REGISTERED_ORIGINAL_DOOR',...door,source:scene.source,coordinates_moved:false,not_entry_if_exit:exit});});
  }
 }
 function roadLabel(f){let p=labelAnchor(f);if(!p)return null;let t=f.tags||{},label=t.name||t['name:zh'];if(!label)return null;
  if(t.oneway&&t.oneway!=='no')label+=' · 单向';if(enabled.has('levels')&&t.tunnel==='yes')label+=' · 隧道';
  if(enabled.has('sidewalks')&&t.sidewalk)label+=' [sidewalk='+t.sidewalk+']';
  if(enabled.has('cycleways')&&t.cycleway)label+=' [cycleway='+t.cycleway+']';return {p,label};}
 function sourcePoiLabel(f){let t=f.tags||{},name=t.name||t['name:zh'];if(!name)return null;
  if(t.highway==='platform'||t.public_transport==='platform')name+=t.railway==='platform'?'（轨道站台）':'（公交站台）';
  else if(t.highway==='bus_stop')name+='（公交站）';
  else if(t.public_transport==='stop_position'&&t.bus==='yes')name+='（公交停靠点）';
  else if(t.railway==='subway_entrance')name+='（地铁出入口）';
  else if(t.railway==='station'||t.railway==='halt')name+='（轨道车站）';
  if(scene.target.conflicting_place_ids?.includes(idOf(f)))name+='（非目标）';return name;
 }
 function drawBase(svg,unit){let group=el('g',{'class':'base-context','data-scene-id':'shanghai-museum-peoples-square','data-base-map-sha256':DATA.base_map_sha256},svg),ids=[];
  let exact=JSON.stringify(view)===JSON.stringify(currentView().bounds_xy)?new Set(currentView().source_ids):null;
  let features=scene.features.filter(f=>exact?exact.has(idOf(f)):geometryVisible(f.geometry)),order=['water','vegetation','pedestrian_areas','road_areas','buildings','road_centerlines','sidewalks','native_walkways','crossings','traffic_facilities','railway','barriers','restrictions','poi','other_context'];
  for(let family of order)for(let f of features){if(displayFamily(f)!==family)continue;let g=renderFeature(group,f,family,unit);ids.push(idOf(f));if(roadIds.has(idOf(f))){for(let p of g.querySelectorAll('path'))if(p.getAttribute('stroke')!=='#fffdfc'){p.setAttribute('stroke','#d49757');p.setAttribute('stroke-width','3.7');p.setAttribute('data-road-identity','HUANGPI_NORTH_ROAD_SOURCE_CENTERLINE');}}}
  if(enabled.has('road_names')){let labels=el('g',{'class':'source-labels'},group),used=[];
   let named=features.filter(f=>featureFamilies(f).includes('road_centerlines')).sort((a,b)=>Number(roadIds.has(idOf(b)))-Number(roadIds.has(idOf(a))));
   for(let f of named){if(!enabled.has('road_centerlines'))continue;let lab=roadLabel(f);if(!lab)continue;let[pX,pY]=lab.p,size=(roadIds.has(idOf(f))?12.4:11.3)*unit,w=lab.label.length*size*.65;if(used.some(([x,y,width])=>Math.abs(x-pX)<(w+width)/2&&Math.abs(y-pY)<size*1.6))continue;used.push([pX,pY,w]);text(labels,pX,-pY,lab.label,size,{'text-anchor':'middle','font-weight':roadIds.has(idOf(f))?'700':'400',fill:roadIds.has(idOf(f))?'#82501d':'#2d3238','data-label-source-id':idOf(f)});}
   for(let f of features){if(!enabled.has('poi')||!featureFamilies(f).includes('poi')||idOf(f)===scene.target.building_id)continue;let name=sourcePoiLabel(f),p=labelAnchor(f);if(!name||!p)continue;let size=10.2*unit,w=Math.min(22,name.length)*size*.65;if(used.some(([x,y,width])=>Math.abs(x-p[0])<(w+width)/2&&Math.abs(y-p[1])<size*1.6))continue;used.push([p[0],p[1],w]);text(labels,p[0],-p[1],name.length>22?name.slice(0,22)+'…':name,size,{'text-anchor':'middle',fill:'#596064','data-label-source-id':idOf(f)});}
  }
  if(enabled.has('restrictions'))for(let f of features){if(!featureFamilies(f).includes('restrictions'))continue;let d=geomPath(f.geometry);if(!d)continue;let mark=el('path',{d,fill:'none',stroke:'#8177a8','stroke-width':1.4,'stroke-dasharray':'3 4','vector-effect':'non-scaling-stroke','class':'source-restriction-tag','data-source-id':idOf(f)},group);mark.addEventListener('click',ev=>{ev.stopPropagation();evidence({...originalObjectEvidence(f),restriction_identity:'RAW_SOURCE_TAG_NOT_NEW_ROUTE_CLASSIFICATION'});});}
  drawTarget(group,unit);group.setAttribute('data-source-ids',JSON.stringify(ids.sort()));return ids.sort();
 }
 function edgeStyle(e){if(e.geometry_status==='SCHEMATIC'||e.hypothesis)return{stroke:e.hypothesis?'#d49757':'#8177a8',dash:e.hypothesis?'7 4':'4 3',width:2.1};return{stroke:e.layer==='road_axis'?'#2d3238':e.layer==='crossing'?'#b97589':'#5b9fbe',width:2.1};}
 function lineVisible(xy){return geometryVisible({type:'LineString',coordinates:xy});}
 function drawOverlay(svg,variant,unit){let graph=native.variants[variant],result=query().results[variant],g=el('g',{'class':'algorithm-overlay','data-variant':variant,'data-request-scope':'OLD_NW_SIDEWALK_DIAGNOSTIC_NOT_MUSEUM_DOOR_ROUTE'},svg),visible=0;
  if(enabled.has(variant))for(let e of graph.edges){if(!lineVisible(e.xy))continue;visible++;let s=edgeStyle(e),p=el('path',{d:linePath(e.xy),fill:'none',stroke:s.stroke,'stroke-width':s.width,'stroke-dasharray':s.dash,'vector-effect':'non-scaling-stroke','class':'algorithm-edge','data-edge-id':e.edge_id},g);p.addEventListener('click',ev=>{ev.stopPropagation();evidence({identity:'ORIGINAL_FROZEN_NORTHWEST_SIDEWALK_EDGE',variant,query_id:query().query_id,scope:'NOT_MUSEUM_DOOR_ROUTE',...e});});}
  if(enabled.has('route_markers')){let byid=new Map(graph.edges.map(e=>[e.edge_id,e]));for(let id of result.edge_ids||[]){let e=byid.get(id);if(!e)throw Error('Frozen result edge missing '+id);if(!lineVisible(e.xy))continue;let d=linePath(e.xy),dash=e.geometry_status==='SCHEMATIC'||e.hypothesis?'8 4':null;el('path',{d,fill:'none',stroke:'#fffdfc','stroke-width':5.7,'vector-effect':'non-scaling-stroke'},g);el('path',{d,fill:'none',stroke:'#2d3238','stroke-width':3.3,'stroke-dasharray':dash,'vector-effect':'non-scaling-stroke','class':'saved-route-edge','data-edge-id':id},g);}
   let bind=query().bindings[variant];for(let[key,label]of[['start','旧诊断起点'],['end','旧诊断终点']]){let p=graph.nodes[bind[key]]||native.nodes[bind[key]];if(!p||!inView(p))continue;el('circle',{cx:p[0],cy:-p[1],r:3.2*unit,fill:'#fffdfc',stroke:'#2d3238','stroke-width':1.5,'vector-effect':'non-scaling-stroke','data-old-query-node':bind[key]},g);text(g,p[0]+5*unit,-p[1]-5*unit,label,9.4*unit,{fill:'#2d3238'});}
  }return visible;
 }
 function frame(svg,unit){let width=view[2]-view[0],scale=width>750?200:width>350?100:width>180?50:20,x=view[0]+13*unit,y=-view[1]-17*unit;el('path',{d:`M${x},${y}h${scale}`,stroke:'#2d3238','stroke-width':2,'vector-effect':'non-scaling-stroke'},svg);text(svg,x,y-5*unit,scale+' m · 源几何尺度',10.3*unit);text(svg,view[2]-20*unit,-view[3]+22*unit,'N ↑',11*unit,{'text-anchor':'middle'});}
 function count(f){return scene.features.filter(x=>featureFamilies(x).includes(f)).length;}
 function available(k){return ['target_identity','road_names','route_markers','R0','R1','R2'].includes(k)||count(k)>0;}
 function updateLayers(){let d=$('layers');d.replaceChildren();for(let[k,label,color,kind]of specs){let ok=available(k),l=document.createElement('label'),i=document.createElement('input'),s=document.createElement('span'),t=document.createElement('span');i.type='checkbox';i.dataset.layer=k;i.checked=ok&&enabled.has(k);i.disabled=!ok;l.className=ok?'':'unavailable';s.className='swatch'+(kind==='fill'?' fill':'');s.style.borderColor=color;if(kind==='fill')s.style.background=color;if(kind==='dash')s.style.borderTopStyle='dashed';t.textContent=label+(!['target_identity','road_names','route_markers','R0','R1','R2'].includes(k)?' ('+count(k)+')':'')+(ok?'':' · NOT_PRESENT_IN_FROZEN_SOURCE');l.append(i,s,t);d.appendChild(l);i.onchange=()=>{i.checked?enabled.add(k):enabled.delete(k);render();};}}
 function finalRecord(v){return DATA.registry.filter(r=>r.query_id===query().query_id&&r.variant===v).sort((a,b)=>a.formal_attempt-b.formal_attempt).at(-1);}
 function currentView(){return views.find(v=>v.id===viewId);}
 function render(){try{$('error').textContent='';let info=[],viewportHash=sha256(JSON.stringify({crs:'EPSG:32651',bounds_xy:view}));
  for(let panel of panels){let svg=$('map-'+panel);svg.replaceChildren();svg.setAttribute('viewBox',`${view[0]} ${-view[3]} ${view[2]-view[0]} ${view[3]-view[1]}`);svg.setAttribute('preserveAspectRatio','xMidYMid meet');let ctm=svg.getScreenCTM(),unit=1/Math.abs(ctm.a),ids=drawBase(svg,unit),n=panel==='context'?0:drawOverlay(svg,panel,unit);frame(svg,unit);let visibleHash=sha256(DATA.base_map_sha256+'|'+JSON.stringify(ids)+'|'+JSON.stringify([...enabled].filter(k=>!['R0','R1','R2','route_markers'].includes(k)).sort()));svg.setAttribute('data-base-map-sha256',visibleHash);svg.setAttribute('data-viewport-sha256',viewportHash);info.push({panel,source_ids:ids,base_map_sha256:visibleHash,full_source_base_sha256:DATA.base_map_sha256,viewport_sha256:viewportHash,extent:[...view],meters_per_css_px:unit,diagnostic_edges_in_view:n});
   if(panel!=='context'){let r=query().results[panel],rec=finalRecord(panel);$('summary-'+panel).textContent=`旧${query().query_id} · #${rec.formal_attempt} ${r.status} · ${n?`${n}条原诊断边位于当前视野`:'OUTSIDE_VIEW：无旧诊断边；未生成到门路线'}`;}
  }
  if(new Set(info.map(x=>x.base_map_sha256)).size!==1||new Set(info.map(x=>x.viewport_sha256)).size!==1)throw Error('Method base/viewport mismatch');
  let targetPoints=coords(scene.target.geometry),diagnostic={scene_id:'shanghai-museum-peoples-square',view_id:viewId,query_id:query().query_id,target_building_id:scene.target.building_id,target_visible:geometryVisible(scene.target.geometry),target_fully_inside:targetPoints.every(inView),doors_visible:Object.fromEntries(scene.target.doors.map(d=>[d.source_id,inView(d.xy)])),panels:info,base_sets_equal:true,viewport_hash:viewportHash,viewport_hash_scheme:"SHA256(JSON.stringify({crs:'EPSG:32651',bounds_xy:currentBounds}))",base_hash_scheme:'SHA256(fullCanonicalSourceHash|orderedRenderedSourceIDs|sortedEnabledSourceLayerKeys)',extent:[...view],algorithm_runs_added:0,solver_calls_added:0};window.RECON_MAP_DIAGNOSTICS=diagnostic;
  $('view-note').textContent=`${currentView().label} · EPSG:32651 · ${view.map(number).join(', ')} m · 四面板同一底图/范围/比例 · ${number(info[0].meters_per_css_px)} m/CSS px`;
  $('source-note').textContent=`源快照 ${scene.source.timestamp||scene.source.source_timestamp||'FROZEN'} · SHA256 ${scene.source.sha256||scene.source.source_sha256} · 全街区 ${scene.features.length}个源对象`;
  $('source-status').textContent=`道路面：${count('road_areas')?'仅源中登记面':'NOT_PRESENT_IN_FROZEN_SOURCE'}。road surface/width unavailable in frozen source；线宽不代表实测路幅。`;
  $('identity-note').textContent=`原门坐标：${scene.target.doors.map(d=>d.source_id+' ['+d.wgs84.join(', ')+'] '+d.tags.entrance).join('；')}。坐标未移动。`;
  $('road-note').textContent='黄陂北路原生道路段：'+[...roadIds].join('、')+'。同名公交platform不当作道路。车道/自行车标签仅为源属性，不生成新几何。';
  window.RECON_MAP_CURRENT_EXPORT={identity:'TARGET_ANCHORED_VIEW_NO_SOLVER',target:scene.target,source:scene.source,view:currentView(),current_bounds_xy:view,diagnostic,old_diagnostic_query:query(),old_diagnostic_scope:'NORTHWEST_SIDEWALK_ONLY_NOT_MUSEUM_DOOR_ROUTE',frozen_trial_sha256:DATA.frozen_trial_sha256};$('request').textContent=JSON.stringify(window.RECON_MAP_CURRENT_EXPORT,null,2);
  let body=$('result-body');body.replaceChildren();for(let v of ['R0','R1','R2']){let r=query().results[v],tr=document.createElement('tr');for(let value of[v,finalRecord(v).formal_attempt,r.status,info.find(x=>x.panel===v).diagnostic_edges_in_view,r.cost_f1_proxy==null?'N/A':number(r.cost_f1_proxy)]){let td=document.createElement('td');td.textContent=String(value);tr.appendChild(td);}body.appendChild(tr);}
  let familyBody=$('family-body');familyBody.replaceChildren();for(let[k,label]of specs.filter(x=>!['target_identity','road_names','R0','R1','R2','route_markers'].includes(x[0]))){let tr=document.createElement('tr'),total=count(k),visible=scene.features.filter(f=>featureFamilies(f).includes(k)&&geometryVisible(f.geometry)).length;for(let value of[label,total,visible,total?'PRESENT_IN_FROZEN_SOURCE':'NOT_PRESENT_IN_FROZEN_SOURCE']){let td=document.createElement('td');td.textContent=String(value);tr.appendChild(td);}familyBody.appendChild(tr);}
  updateHistory();
 }catch(e){$('error').textContent='目标地图绘制失败：'+(e.stack||e.message||e);console.error(e);}}
 function updateHistory(){let old=DATA.registry.find(r=>r.query_id===query().query_id&&r.variant==='R0'&&r.formal_attempt<=18);$('history-record').textContent=$('history').value==='original'?JSON.stringify({identity:'SUPERSEDED_RECORD_NOT_MAIN_MAP',original_R0:old,effective_R0:finalRecord('R0'),scope:'Originalnorthwestsidewalkdiagnostic; museumdoorsareNOTitsendpoints'},null,2):'主图保持最终有效冻结结果；旧诊断不重绑为博物馆到门任务。';}
 function options(select,rows){select.replaceChildren();for(let[value,label]of rows){let o=document.createElement('option');o.value=value;o.textContent=label;select.appendChild(o);}}
 function chooseView(id){viewId=id;let v=currentView();if(!v)throw Error('Unknown target anchored view '+id);view=[...v.bounds_xy];$('view').value=id;render();}
 function navigate(){let id=location.hash.slice(1),map={'overview':'target_overview','block-context':'block_context','huangpi-north-road':'huangpi_detail','south-entrance':'south_detail','north-exit':'north_detail','r0-r1-r2':'block_context'};if(map[id])chooseView(map[id]);if(id==='source-lineage'){let f=sourceFeature(scene.target.building_id);evidence(originalObjectEvidence(f));$('source-lineage').scrollIntoView({block:'start'});}}
 function download(value,name){let b=new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type:typeof value==='string'?'image/svg+xml':'application/json'}),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 function setup(){if(!scene?.target?.geometry||scene.target.building_id!=='way/161090899')throw Error('Target identity gate failed');options($('view'),views.map(v=>[v.id,v.label]));options($('query'),native.queries.map((q,i)=>[i,q.query_id+' · 旧西北步道诊断']));$('view').onchange=()=>chooseView($('view').value);$('query').onchange=()=>{qi=Number($('query').value);render();};$('reset').onclick=()=>chooseView(viewId);$('layer-controls-toggle').onclick=()=>{let d=$('layer-controls');d.open=!d.open;if(d.open)d.scrollIntoView({block:'start',behavior:'smooth'});};$('history').onchange=updateHistory;$('variant').onchange=()=>$('map-'+$('variant').value).scrollIntoView({block:'nearest',behavior:'smooth'});$('export').onclick=()=>download({...window.RECON_MAP_CURRENT_EXPORT,enabled_layers:[...enabled],selected_object:selection},'shanghai-museum-'+viewId+'-view.json');$('export-svg').onclick=()=>download(new XMLSerializer().serializeToString($('map-'+$('variant').value)),viewId+'-'+$('variant').value+'.svg');$('export-evidence').onclick=()=>download(selection||{message:'先点选目标建筑、原门或原始对象'},'target-object-evidence.json');
  for(let panel of panels){let svg=$('map-'+panel);svg.addEventListener('wheel',e=>{e.preventDefault();let p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;p=p.matrixTransform(svg.getScreenCTM().inverse());let x=p.x,y=-p.y,w=view[2]-view[0],h=view[3]-view[1],tx=(x-view[0])/w,ty=(y-view[1])/h,f=e.deltaY>0?1.2:1/1.2;view=[x-tx*w*f,y-ty*h*f,x+(1-tx)*w*f,y+(1-ty)*h*f];render();},{passive:false});svg.addEventListener('pointerdown',e=>{if(e.button===0)drag={x:e.clientX,y:e.clientY,view:[...view],moved:false};});svg.addEventListener('pointermove',e=>{if(!drag)return;if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)<4&&!drag.moved)return;drag.moved=true;svg.setPointerCapture(e.pointerId);let m=svg.getScreenCTM(),dx=(e.clientX-drag.x)/m.a,dy=(e.clientY-drag.y)/m.d;view=[drag.view[0]-dx,drag.view[1]+dy,drag.view[2]-dx,drag.view[3]+dy];render();});svg.addEventListener('pointerup',()=>drag=null);svg.addEventListener('pointercancel',()=>drag=null);}
  updateLayers();chooseView('target_overview');navigate();window.addEventListener('hashchange',navigate);window.addEventListener('resize',render);window.RECON_MAP_READY=true;window.RECON_SHA256=sha256;
 }
 try{setup();}catch(e){$('error').textContent='目标绑定/初始化失败：'+(e.stack||e);console.error(e);}
 function renderFeature(parent,f,fam,unit){const g=f.geometry,s=style(f,fam),group=el('g',{'class':'source-feature','data-source-id':idOf(f),'data-family':fam,'data-geometry-type':g?.type},parent);
  const attach=()=>group.addEventListener('click',ev=>{ev.stopPropagation();evidence(sourceEvidence(f));});
  if(g?.type==='GeometryCollection'){for(let child of g.geometries||[])draw(child);}
  else draw(g);attach();return group;
  function draw(geom){if(!geom)return;let d=geomPath(geom);if(d){if(fam==='road_centerlines')el('path',{d,fill:'none',stroke:'#fffdfc','stroke-width':s.width+2.4,'vector-effect':'non-scaling-stroke'},group);el('path',{d,fill:s.fill,stroke:s.stroke,'stroke-width':s.width,'stroke-dasharray':s.dash,'fill-rule':'evenodd','vector-effect':'non-scaling-stroke'},group);}
   else for(let p of coords(geom)){if(!inView(p))continue;let r=(fam==='crossings'?3:fam==='traffic_facilities'?3:2.1)*unit;if(fam==='traffic_facilities')el('rect',{x:p[0]-r,y:-p[1]-r,width:2*r,height:2*r,fill:'#fffdfc',stroke:s.stroke,'stroke-width':s.width,'vector-effect':'non-scaling-stroke'},group);else if(fam!=='crossings')el('circle',{cx:p[0],cy:-p[1],r,fill:s.fill==='none'?'#fffdfc':s.fill,stroke:s.stroke,'stroke-width':s.width,'vector-effect':'non-scaling-stroke'},group);if(fam==='crossings'){el('path',{d:`M${p[0]-r},${-p[1]-r}l${2*r},${2*r}m0,${-2*r}l${-2*r},${2*r}`,stroke:s.stroke,'stroke-width':2,'vector-effect':'non-scaling-stroke'},group);}if(fam==='traffic_facilities'){el('circle',{cx:p[0],cy:-p[1],r:r*.33,fill:'#b97589'},group);}}
  }
 }

})();
