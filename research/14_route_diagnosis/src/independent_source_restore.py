"""Stream source-topology provenance/weight restoration without author imports."""
from pathlib import Path
import zipfile,json,csv,io,gzip,math,hashlib,gc,argparse
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
P=Transformer.from_crs(4326,32651,always_xy=True)
def rawid(n):return int(n.split('/')[1].split('@')[0])if n.startswith('node/')else None
def grade(n):
    if '@layer='not in n:return('0','0')
    return tuple(n.split('@layer=')[1].split('@level='))
def main():
    rows=[]
    with zipfile.ZipFile(ARCHIVE)as z:
        policy_sha=hashlib.sha256(z.read('src/frozen_scene/local_route.py')).hexdigest()
        components=list(csv.DictReader(io.StringIO(z.read('results/component_statistics.csv').decode('utf-8-sig'))))
        for scene in ['sh-huangpu-01','sh-library']:
            raw=json.loads(z.read('data/scenes/'+scene+'/source.osm.json'))
            original={'node/'+str(n['id']):P.transform(n['lon'],n['lat'])for n in raw['elements']if n['type']=='node'}
            xy=dict(original);adjacent=set();mapped={};maxcoord=0.;mappedrows=0;nonstraight=0;lengthdelta=0.;endings={}
            for way in raw['elements']:
                if way['type']=='way':
                    for a,b in zip(way['nodes'],way['nodes'][1:]):adjacent.add((a,b));adjacent.add((b,a))
                    tags=way.get('tags',{});layer=tags.get('layer','1'if tags.get('bridge')not in(None,'no')else'-1'if tags.get('tunnel')not in(None,'no')else'0');level=tags.get('level','0')
                    for node in (way['nodes'][0],way['nodes'][-1]):endings.setdefault(node,set()).add((layer,level))
            del raw;gc.collect()
            with gzip.GzipFile(fileobj=io.BytesIO(z.read('data/scenes/'+scene+'/mapped_edges.jsonl.gz')))as stream:
                for line in stream:
                    r=json.loads(line);u,v=r['u'],r['v'];coords=r['coordinates_metric'];mappedrows+=1;nonstraight+=len(coords)!=2
                    lengthdelta=max(lengthdelta,abs(sum(math.dist(a,b)for a,b in zip(coords,coords[1:]))-r['length_m']))
                    for n,p in zip((u,v),coords):
                        if n in original:maxcoord=max(maxcoord,math.dist(original[n],p))
                        xy[n]=tuple(p)
                    mapped[(u,v)]=min(mapped.get((u,v),math.inf),r['length_m'])
                    if r['direction']=='BIDIRECTIONAL':mapped[(v,u)]=min(mapped.get((v,u),math.inf),r['length_m'])
            source=json.loads(next(r for r in components if r['scene_id']==scene)['source_topology']);data=z.read(source['path'])
            if hashlib.sha256(data).hexdigest()!=source['sha256']:raise ValueError('SOURCE_TOPOLOGY_SHA')
            missing=[];native=both=derived=arcs=transitions=0;maxweight=0.;transition_rows=[]
            with gzip.GzipFile(fileobj=io.BytesIO(data))as stream:
                for line in stream:
                    r=json.loads(line)
                    if r['kind']=='node':
                        n=r['id']
                        if n not in xy and rawid(n)is not None:xy[n]=xy['node/'+str(rawid(n))]
                        continue
                    u,v=r['u'],r['v'];arcs+=1;rawpair=(rawid(u),rawid(v));options=[]
                    if rawpair in adjacent:
                        options.append(math.dist(original['node/'+str(rawpair[0])],original['node/'+str(rawpair[1])]))
                        if (u,v)in mapped:both+=1
                        else:native+=1
                    if (u,v)in mapped:
                        options.append(mapped[u,v])
                        if rawpair not in adjacent:derived+=1
                    if not options and rawpair[0]is not None and rawpair[0]==rawpair[1] and grade(u)[1]==grade(v)[1] and grade(u)in endings.get(rawpair[0],set()) and grade(v)in endings.get(rawpair[0],set()):
                        options.append(0.);transitions+=1;transition_rows.append({'u':u,'v':v,'source_node_id':rawpair[0],'same_level':grade(u)[1],'source_way_endpoints_verified':True})
                    if not options:missing.append((u,v));continue
                    restored=math.dist(xy[u],xy[v]);maxweight=max(maxweight,abs(restored-min(options)))
            rows.append({'scene':scene,'source_arcs':arcs,'native_raw_adjacent_only':native,'mapped_pair_only':derived,'native_and_mapped_candidates':both,
                'unexplained_source_arcs':missing,'max_per_arc_restored_length_error_m':maxweight,'max_mapped_native_XY_roundtrip_error_m':maxcoord,
                'frozen_shared_native_endpoint_zero_transitions':transitions,'zero_transition_records':transition_rows,
                'mapped_rows':mappedrows,'mapped_non_two_point_rows':nonstraight,'mapped_max_stored_length_error_m':lengthdelta,
                'status':'PASS_WITH_DECLARED_FLOATING_TOLERANCE'if not missing and nonstraight==0 and maxweight<=1e-8 and maxcoord<=1e-8 else'REQUIRES_INSPECTION'})
            del xy,original,adjacent,mapped,endings;gc.collect()
    report={'reviewer':'/root/r2_independent','APP_solver_calls':0,'new_SSSP_calls':0,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'rows':rows,
        'status':'PASS_FOR_SOURCE_WEIGHT_AND_SEGMENT_PROVENANCE_SCOPE'if all(r['status'].startswith('PASS')for r in rows)else'REQUIRES_INSPECTION',
        'frozen_zero_transition_contract':{'path':'src/frozen_scene/local_route.py','sha256':policy_sha,'rule':'_build_graph explicitly connects same raw native way endpoint at equal level across layer tags with zero length; no 2D intersection or interior grade-separated node creates this edge'},
        'initial_transition_alarm_preserved':'audits/independent_source_weight_initial_transition_alarm.json',
        'limits':['No fresh full-source collision/permission filter run: exact SHA-bound source topology is inherited from R1','Per-arc floating reconstruction errors are quantified, not a claim of bit-identical full attributed graphs','Mapped native/derived source weights are unit length per frozen source adapter; no source-base hypothesis multipliers. Query-local/overlay options audited separately.','Zero shared-endpoint layer transitions are inherited frozen source policy, not new R2 inferred cross-layer links or field height verification.']}
    (ROOT/'audits/independent_source_weight_restoration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,default=ARCHIVE);ARCHIVE=ap.parse_args().baseline;main()
