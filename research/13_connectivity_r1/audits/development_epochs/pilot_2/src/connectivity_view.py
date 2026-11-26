"""Read-only source-object display export; never participates in routing."""
from pathlib import Path
import json
from functools import lru_cache
from pyproj import Transformer
from shapely.geometry import shape,mapping
from shapely.ops import transform,nearest_points
ROOT=Path(__file__).resolve().parents[1]
TO_METRIC=Transformer.from_crs(4326,32651,always_xy=True).transform
@lru_cache(maxsize=6)
def diagnosis_data(scene_id):
    name='museum_diagnostic.geojson'if scene_id=='sh-huangpu-01'else scene_id+'_diagnostic.geojson'
    path=ROOT/'data/connectivity'/name
    if not path.is_file():return {'type':'FeatureCollection','features':[],'scene_id':scene_id,'status':'SOURCE_DIAGNOSTIC_NOT_YET_AVAILABLE'}
    raw=json.loads(path.read_text(encoding='utf-8'));features=[]
    for f in raw['features']:
        if f.get('geometry')is None:continue
        features.append({**f,'geometry':mapping(transform(TO_METRIC,shape(f['geometry']))),
            'properties':{**f['properties'],'display_crs':'EPSG:32651','display_only_reprojection':True}})
    result={'type':'FeatureCollection','features':features,'scene_id':scene_id,'working_crs':'EPSG:32651',
        'user_observation':'PENDING_USER_OBSERVATION','screenshot_request_binding':'SCREENSHOT_REQUEST_UNBOUND',
        'note':'原生对象诊断，尚不能仅凭截图确定真实请求；距离取源盘点表，显示投影不进入求路。'}
    if scene_id=='sh-huangpu-01':
        south=next((shape(f['geometry'])for f in features if f['properties'].get('source_id')=='relation/2385771'and f['properties'].get('geometry_role')=='SOURCE_P'),None)
        east=next((shape(f['geometry'])for f in features if f['properties'].get('source_id')=='way/564255372'and f['properties'].get('geometry_role')=='INDEPENDENT_NATIVE_SOURCE_LINE'),None)
        door=next((shape(f['geometry'])for f in features if f['properties'].get('id')=='node/6897141353'and f['properties'].get('geometry_role')=='UNCHANGED_REGISTERED_DOOR'),None)
        if south is not None and east is not None:
            a,b=nearest_points(south,east);result['focus_xy']=[(a.x+b.x)/2,(a.y+b.y)/2]
        if door is not None:result['registered_door_xy']=list(door.coords[0])
    return result
