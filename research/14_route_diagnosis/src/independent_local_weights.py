"""Independent frozen local-cell/arc weight reconstruction; no router imports."""
from pathlib import Path
import json,zipfile,csv,io,gzip,math,hashlib,gc,argparse
from shapely.geometry import shape,box,LineString,Point
from shapely.ops import split
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
def polygons(g):
    if g.geom_type=='Polygon':
        if g.area>1e-8:yield g
    else:
        for c in getattr(g,'geoms',[]):yield from polygons(c)
def lines(g):
    if g.geom_type=='LineString':
        if g.length>1e-6:yield g
    else:
        for c in getattr(g,'geoms',[]):yield from lines(c)
def main():
    report=[];errors=[]
    with zipfile.ZipFile(ARCHIVE)as z:
        samples=list(csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))))
        comps=list(csv.DictReader(io.StringIO(z.read('results/component_statistics.csv').decode('utf-8-sig'))))
        for case,app in [('south','APP-01'),('north_near','APP-03'),('library','APP-07')]:
            record=next(r for r in samples if r['request_id']==app and r['mode']=='FROZEN_FULL_FACE');body=json.loads(z.read(record['response_path']));scene=record['scene_id'];pr=body['planning_region'];domain=shape(pr['domain']);masks=[shape(pr[k])for k in('native','assumed','restricted')];masks.append(domain.difference(masks[0]).difference(masks[1]).difference(masks[2]))
            common=json.loads(z.read('data/connectivity/'+scene+'_full_common.json'));roads=[shape(r['geometry'])for r in common['road_centerlines']if shape(r['geometry']).intersects(domain)]
            xy={};edges={}
            with gzip.open(ROOT/f'data/{case}_query_graph.jsonl.gz','rt',encoding='utf-8')as f:
                for line in f:
                    row=json.loads(line)
                    if row['kind']=='node':xy[row['id']]=row['xy']
                    elif row['u'].startswith('cell/')or row['v'].startswith('cell/'):edges[row['u'],row['v']]=row['options']
            cells={};k=0;x0,y0,x1,y1=domain.bounds
            for i in range(math.floor(x0),math.ceil(x1)):
                for j in range(math.floor(y0),math.ceil(y1)):
                    for mask in masks:
                        initial=box(i,j,i+1,j+1).intersection(mask);parts=list(polygons(initial))
                        for road in roads:
                            nextparts=[]
                            for part in parts:
                                if part.intersects(road):
                                    try:nextparts.extend(polygons(split(part,road)))
                                    except ValueError:nextparts.append(part)
                                else:nextparts.append(part)
                            parts=nextparts
                        for part in parts:
                            for fixed in polygons(part.intersection(initial)):
                                for geom in polygons(fixed.intersection(mask)):
                                    if geom.area<=1e-8:continue
                                    cells[f'cell/{i}/{j}/{k}']=tuple(geom.representative_point().coords)[0];k+=1
            topology=json.loads(next(r for r in comps if r['scene_id']==scene and r['door_id']==body['door']['id'])['local_topology']);data=z.read(topology['path']);assert hashlib.sha256(data).hexdigest()==topology['sha256']
            coordmax=0.;costmax=0.;checked=nodes=0;bad=[]
            with gzip.GzipFile(fileobj=io.BytesIO(data))as f:
                for line in f:
                    row=json.loads(line)
                    if row['kind']=='node':
                        if row['id'].startswith('cell/'):
                            nodes+=1;delta=math.dist(xy[row['id']],cells[row['id']]);coordmax=max(coordmax,delta)
                            if delta>1e-8:bad.append(['CELL_XY',row['id'],delta])
                        continue
                    u,v=row['u'],row['v'];linegeom=LineString([xy[u],xy[v]]);length=linegeom.length;hyp=0.;valid=True
                    if length>1e-6:
                        if linegeom.intersection(masks[2]).length>1e-6 or linegeom.difference(domain).length>1e-6:valid=False
                        cuts={0.,length}
                        for mask in(masks[0],masks[1],masks[3]):
                            for frag in lines(linegeom.intersection(mask)):
                                cuts.update(linegeom.project(Point(p))for p in(frag.coords[0],frag.coords[-1]))
                        total=0.;unknown=0.
                        for a,b in zip(sorted(cuts),sorted(cuts)[1:]):
                            if b-a<=1e-6:continue
                            mid=linegeom.interpolate((a+b)/2);piece=math.dist(linegeom.interpolate(a).coords[0],linegeom.interpolate(b).coords[0]);total+=piece
                            if masks[0].covers(mid):pass
                            elif masks[1].covers(mid):hyp+=piece
                            elif masks[3].covers(mid):unknown+=piece;hyp+=piece
                            else:valid=False
                        valid=valid and unknown<=1e-6;length=total
                    options=edges.get((u,v),[]);residual=min((max(abs(o[0]-length),abs(o[1]-hyp))for o in options),default=math.inf);costmax=max(costmax,residual);checked+=1
                    if not valid or residual>1e-7:bad.append(['LOCAL_WEIGHT',u,v,length,hyp,residual,valid])
            report.append({'case':case,'local_topology_sha256':topology['sha256'],'cell_nodes_reconstructed':nodes,'all_generated_cells':len(cells),'local_arcs_recomputed':checked,'max_node_xy_error_m':coordmax,'max_length_or_hypothesis_error_m':costmax,'errors':bad});errors.extend(bad);del xy,edges,cells;gc.collect()
    out={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_solver_calls':0,'new_SSSP_calls':0,'status':'PASS_FOR_ALL_FROZEN_LOCAL_CELL_AND_ARC_WEIGHTS'if not errors else'REQUIRES_INSPECTION','rows':report,'errors':errors,'scope':'All three unique local namespaces; independently rebuild unit-grid fragments split by raw recorded road lines and source masks, compare cell IDs/representative coordinates, whole local arc restricted/domain checks, interval evidence lengths and hypothesis costs. Does not resurvey real-world constraints or optimize endpoint attachment.'}
    (ROOT/'audits/independent_local_weight_restoration.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':out['status'],'rows':report},ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,default=ARCHIVE);ARCHIVE=ap.parse_args().baseline;main()
