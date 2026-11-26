"""Direct geometry recomputation against frozen P/Omega, no author imports."""
from pathlib import Path
import argparse,zipfile,json,csv,io,hashlib,gc
from shapely.geometry import shape,LineString,Polygon
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
PROJECT=Transformer.from_crs(4326,32651,always_xy=True)
def sha(data):return hashlib.sha256(data).hexdigest()
def main(archive=ARCHIVE):
    routes={};rows=[];source_checks=[];errors=[]
    with zipfile.ZipFile(archive)as z:
        allrows=list(csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))))
        for r in allrows:
            if r['role']!='BASELINE_POSITIVE'or r['mode']!='CONDITIONAL_SEAMS':continue
            data=json.loads(z.read(r['response_path']));xy=[]
            for s in data['route']['segments']:
                for p in s['xy']:
                    if not xy or p!=xy[-1]:xy.append(p)
            line=LineString(xy);routes[r['request_id']]={'line':line,'scene':r['scene_id'],'buffer':{radius:line.buffer(radius)for radius in(5,10,20)}}
        lock=json.loads(z.read('data/connectivity/source_selection_lock.json'))
        oldids={a for s in lock['scenes']for a in s['old_area_ids']}
        globalnew=set()
        for scene in lock['scenes']:
            sid=scene['scene_id'];rawdata=z.read('data/scenes/'+sid+'/source.osm.json');raw=json.loads(rawdata)
            nodes={r['id']:PROJECT.transform(r['lon'],r['lat'])for r in raw['elements']if r['type']=='node'}
            ways={r['id']:r for r in raw['elements']if r['type']=='way'}
            faces=json.loads(z.read('data/connectivity/'+sid+'_faces.json'))
            for face in faces:
                source=face['source_id']
                if source not in scene['added_area_ids']:continue
                if source not in oldids:globalnew.add(source)
                p=shape(face['source_geometry']);omega=shape(face['omega']);rawcheck='INHERITED_R1_RELATION_RING_REVIEW'
                if source.startswith('way/'):
                    w=ways[int(source.split('/')[1])];ids=w['nodes']
                    if ids[0]!=ids[-1]or any(i not in nodes for i in ids):rawcheck='UNRESOLVED_RAW_MEMBERS'
                    else:
                        rebuilt=Polygon([nodes[i]for i in ids]);delta=rebuilt.symmetric_difference(p).area;hd=rebuilt.hausdorff_distance(p)
                        rawcheck='PASS'if delta<=1e-5 and hd<=1e-8 else'RAW_SOURCE_GEOMETRY_MISMATCH'
                        source_checks.append({'scene':sid,'source_id':source,'raw_way_version':w.get('version'),'symmetric_difference_m2':delta,'hausdorff_m':hd,'status':rawcheck})
                        if rawcheck!='PASS':errors.append([sid,source,rawcheck])
                for request,route in routes.items():
                    line=route['line'];distance=None if omega.is_empty else omega.distance(line)
                    rows.append({'request_id':request,'source_scene_id':sid,'source_id':source,'global_new_vs_any_old':source not in oldids,
                        'present_in_query_scene':sid==route['scene'],'P_distance_m':p.distance(line),'omega_distance_m':distance,'omega_empty':omega.is_empty,
                        'omega_route_overlap_m':omega.intersection(line).length,'corridor_5_area_m2':omega.intersection(route['buffer'][5]).area,
                        'corridor_10_area_m2':omega.intersection(route['buffer'][10]).area,'corridor_20_area_m2':omega.intersection(route['buffer'][20]).area,
                        'raw_P_check':rawcheck,'scope':'GEOMETRY_ONLY; corridor is not routable domain; graph reachability audited separately'})
            del raw,rawdata,nodes,ways,faces;gc.collect()
    report={'reviewer':'/root/r2_independent','script_sha256':sha(Path(__file__).read_bytes()),'status':'PASS_FOR_DIRECT_CORRIDOR_GEOMETRY'if not errors and len(globalnew)==82 else'REQUIRES_INSPECTION','APP_solver_calls':0,
        'global_new_unique_ID_count':len(globalnew),'scene_object_route_rows':len(rows),'source_checks':source_checks,'errors':errors,'rows':rows,
        'limits':['Uses frozen Omega geometry already source-checked in R1; does not recreate every constraint subtraction','New-way P reconstructed from raw native nodes; added relation relies on explicitly inherited R1 independent ring review','Different clipped copies not independent evidence; rows retain scene namespace','No topology or physical access inferred from geometric distance']}
    (ROOT/'audits/independent_corridor_geometry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k]for k in['status','global_new_unique_ID_count','scene_object_route_rows','errors']}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,default=ARCHIVE);args=parser.parse_args();main(args.baseline)
