from pathlib import Path
import sys,json,zipfile,csv,io,gzip,math
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'baseline_runtime'))
from src.region import STATES,polygons
from src.free_surface import partition_roads
from shapely.geometry import shape,box,Point
Z=zipfile.ZipFile(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
rows=list(csv.DictReader(io.StringIO(Z.read('results/sample_results.csv').decode('utf-8-sig'))));r=next(x for x in rows if x['request_id']=='APP-03'and x['mode']=='CONDITIONAL_SEAMS');d=json.loads(Z.read(r['response_path']));p=d['planning_region'];domain=shape(p['domain'])
masks={STATES[0]:shape(p['native']),STATES[1]:shape(p['assumed']),STATES[2]:shape(p['restricted'])};masks[STATES[3]]=domain.difference(masks[STATES[0]]).difference(masks[STATES[1]]).difference(masks[STATES[2]])
c=json.loads(Z.read('data/connectivity/sh-huangpu-01_full_common.json'));roads=[x for x in c['road_centerlines']if shape(x['geometry']).intersects(domain)]
print('STATES',STATES,'ROADS',len(roads),flush=True)
cells={};k=0
x0,y0,x1,y1=domain.bounds
for i in range(math.floor(x0),math.ceil(x1)):
 for j in range(math.floor(y0),math.ceil(y1)):
  for state in STATES:
   parts=partition_roads(box(i,j,i+1,j+1).intersection(masks[state]),roads)
   for g in (p for part in parts for p in polygons(part.intersection(masks[state]))):
    if g.area<=1e-8:continue
    ident=f'cell/{i}/{j}/{k}';k+=1
    cells[ident]={'xy':list(g.representative_point().coords)[0],'state':state}
comp=list(csv.DictReader(io.StringIO(Z.read('results/component_statistics.csv').decode('utf-8-sig'))));rec=next(x for x in comp if x['door_id']=='node/6897145227'and x['mode']=='CONDITIONAL_SEAMS');snap=json.loads(rec['local_topology'])
actual=[json.loads(s)['id']for s in gzip.decompress(Z.read(snap['path'])).decode().splitlines()if json.loads(s)['kind']=='node'];expected=[x for x in actual if x.startswith('cell/')]
missing=[x for x in expected if x not in cells];print('CELL_COUNT',k,'LOCAL_CELLS',len(expected),'MISSING',len(missing),missing[:5])
errs=[]
import itertools
for uv,group in itertools.groupby(d['route']['segments'],key=lambda s:(s.get('u'),s.get('v'))):
 sg=list(group);s=sg[0]
 for key,xy in [(uv[0],sg[0]['xy'][0]),(uv[1],sg[-1]['xy'][-1])]:
  if key in cells:errs.append(math.dist(xy,cells[key]['xy']))
print('ROUTE_XY_ERRORS',max(errs,default=0),len(errs));(ROOT/'results/local_probe.json').write_text(json.dumps({'missing':missing,'max_route_xy_error':max(errs,default=0),'cells':cells}),encoding='utf-8')
