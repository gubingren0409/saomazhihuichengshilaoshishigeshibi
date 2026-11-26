from pathlib import Path
import json
R=Path(r'E:/智慧城市和位置服务/_task_runtime/PG1_MIDTERM_RESEARCH_MATERIALS_R2')
rows=json.loads((R/'working/figure_selection.json').read_text(encoding='utf8'))
from playwright.sync_api import sync_playwright
from PIL import Image,ImageDraw
import base64
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True)
 page=b.new_page(viewport={'width':2200,'height':1700},device_scale_factor=1)
 for i in [16,17,19,20,27,28,29,30,31,35,36]:
  r=rows[i];f=R/'working'/r['package_path']
  data=base64.b64encode(f.read_bytes()).decode()
  page.set_content('<html><body style="margin:0;background:white"><img style="display:block;width:2200px;height:auto" src="data:image/svg+xml;base64,'+data+'"></body></html>')
  page.locator('img').wait_for();page.wait_for_function('document.images[0].complete');page.locator('img').screenshot(path=str(R/f'working/render_{i}.png'))
 b.close()
thumbs=[]
for p in R.glob('working/render_*.png'):
 im=Image.open(p).convert('RGB');im.thumbnail((680,450));thumbs.append((p.stem,im))
for start in range(0,len(thumbs),6):
 out=Image.new('RGB',(1400,3*500),'#eee');d=ImageDraw.Draw(out)
 for j,(n,im) in enumerate(thumbs[start:start+6]):
  x=j%2*700;y=j//2*500;d.text((x,y),n,fill='black');out.paste(im,(x,y+25))
 out.save(R/f'working/svg_contact_{start}.jpg')
print('Done',len(thumbs))
for sub in ['metrics/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/route_variants_47498bef.geojson','metrics/OSM_GEOAPIFY_R4_REV1/routes_1f472826.geojson']:
 d=json.loads((R/'working/source_materials'/sub).read_text(encoding='utf8'));print(sub,len(d['features']));print([f['properties'] for f in d['features']][:12])
