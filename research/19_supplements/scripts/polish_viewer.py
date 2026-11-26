from pathlib import Path
p=Path(__file__).with_name('viewer_template.html');s=p.read_text(encoding='utf-8')
if 'const drawnNames=new Set()'not in s:
 s=s.replace('records=[];const s=current()','records=[];const drawnNames=new Set();const s=current()')
 s=s.replace("checked&&isline&&t.name){","checked&&isline&&t.name&&!drawnNames.has(t.name)){")
 s=s.replace('ctx.fillText(t.name,x,y)','if(x>0&&y>0&&x<canvas.width&&y<canvas.height){ctx.fillText(t.name,x,y);drawnNames.add(t.name)}')
 s=s.replace('ctx.stroke(p);records.push([p,f]);','ctx.stroke(p);records.push([p,f]);if(f.properties.target&&f.geometry.type==="Polygon"){const a=f.geometry.coordinates[0],mean=a.reduce((z,q)=>[z[0]+q[0]/a.length,z[1]+q[1]/a.length],[0,0]),xy=project(mean);ctx.font="bold "+17*devicePixelRatio+"px Microsoft YaHei";ctx.fillStyle="#374b40";ctx.fillText(t.name||f.properties.source_id,xy[0]-35,xy[1]);}')
 s=s.replace('if(v.obstacle){','if(v.closed_segment){let p=path({type:"LineString",coordinates:v.closed_segment.xy});ctx.strokeStyle="#c52e33";ctx.lineWidth=5*devicePixelRatio;ctx.setLineDash([7*devicePixelRatio,4*devicePixelRatio]);ctx.stroke(p);ctx.setLineDash([]);records.push([p,{properties:{...v.closed_segment,simulation_status:"CLOSED_FOR_THIS_STATE_NOT_FIELD_FACT"},geometry:{type:"LineString",coordinates:v.closed_segment.xy}}]);}if(v.obstacle){')
 s=s.replace('const row=v.row;','let metres=10**Math.floor(Math.log10((bounds[2]-bounds[0])/4));if((bounds[2]-bounds[0])/metres>12)metres*=5;else if((bounds[2]-bounds[0])/metres>7)metres*=2;const u=project([bounds[0],bounds[1]]),w=project([bounds[0]+metres,bounds[1]]),bx=25*devicePixelRatio,by=canvas.height-30*devicePixelRatio;ctx.strokeStyle="#263d32";ctx.lineWidth=3*devicePixelRatio;ctx.beginPath();ctx.moveTo(bx,by);ctx.lineTo(bx+w[0]-u[0],by);ctx.stroke();ctx.font=12*devicePixelRatio+"px Microsoft YaHei";ctx.fillStyle="#263d32";ctx.fillText(metres+" m",bx,by-7*devicePixelRatio);ctx.fillText("N ↑",canvas.width-48*devicePixelRatio,24*devicePixelRatio);const row=v.row;')
 p.write_text(s,encoding='utf-8')
print('VIEWER_POLISH_APPLIED')
