import json, pathlib, urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1]
requests=[]
def add(source, name, url, basis, cap=1800000):
    requests.append(dict(source_id=source,url=url,path=f'samples/{name}.json',max_bytes=cap,license_basis=basis))
for name,bbox in [('nyc_grand_central',[-73.98,40.749,-73.971,40.756]),('nyc_lincoln_center',[-73.99,40.769,-73.979,40.776])]:
    w,s,e,n=bbox
    for layer,dataset in [('buildings','5zhs-2jue'),('sidewalk','52n9-sdep')]:
        query={'$where':f"intersects(the_geom, 'POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))')",'$limit':500}
        add('NYC',name+'_'+layer,'https://data.cityofnewyork.us/resource/'+dataset+'.geojson?'+urllib.parse.urlencode(query),'NYC OpenData terms + official Open Data Technical Standards 2.3.2; local audit sample; public release review pending')
for name,bbox in [('hel_oodi',[24.930,60.170,24.943,60.178]),('hel_meilahti',[24.897,60.186,24.914,60.195]),('hel_kallio',[24.946,60.180,24.960,60.187])]:
    for layer,types in [('buildings','Rakennukset_alue'),('pedestrian','YLRE_Katu_ja_viherosat_kevytliikenne_alue'),('roads','YLRE_Katu_ja_viherosat_ajorata_alue'),('green','YLRE_Viherosat_alue')]:
        query=dict(service='WFS',version='1.0.0',request='GetFeature',typeName='avoindata:'+types,outputFormat='application/json',srsName='EPSG:4326',bbox=','.join(map(str,bbox)),maxFeatures=400)
        add('HELSINKI',name+'_'+layer,'https://kartta.hel.fi/ws/geoserver/avoindata/wfs?'+urllib.parse.urlencode(query),'CC BY 4.0; primary HRI/national catalog indexed metadata; buildings and YLRE; attribution required')
query='[out:json][timeout:30][maxsize:8000000];nwr(52.504,13.366,52.511,13.380);out body geom;'
add('OSM','berlin_potsdamer','https://overpass-api.de/api/interpreter?'+urllib.parse.urlencode({'data':query}),'ODbL 1.0; © OpenStreetMap contributors; tiny bbox; no meta/user/changeset output',3000000)
(ROOT/'sample_requests.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2),encoding='utf-8')
print('bounded requests',len(requests),'providers',len(set(r['source_id'] for r in requests)))
