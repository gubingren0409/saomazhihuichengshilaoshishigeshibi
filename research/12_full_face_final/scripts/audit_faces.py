"""Source-only face/clearance audit without building the dense legacy graph."""
from pathlib import Path
import argparse,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from shapely.geometry import LineString,mapping,shape
from src.face_geometry import (_source,read,lock_selection,compile_faces,
                               serializable_face,metrics)
from src.scene_data import restricted,non_ground,area_role,source_coverage,MOTOR
from src.frozen_scene.semantics import obstacle_kind
from src.common_constraints import build_contract

def source_contract(scene_id):
    source,row=_source(scene_id);raw=read(ROOT/row['source_path'])
    obstacles,unlocated=source.obstacles([])
    context={'hard':[],'background':[],'support':[]};seen=set();gates={}
    for obj in obstacles:
        kind=obstacle_kind(obj);layer='hard'
        if kind=='BACKGROUND_GRASS':kind='GRASS';layer='background'
        elif kind=='AREA':kind='MAPPED_NON_RESTRICTED_AREA';layer='support'
        sid=obj['id'];context[layer].append({'id':sid,'kind':kind,'tags':obj.get('tags',{}),'geometry':mapping(obj['geometry']),'gates':obj.get('gates',[])})
        seen.add(sid)
        if obj['kind']=='BARRIER'and sid.startswith('way/'):
            gate_rows=[]
            for nid in source.ways[int(sid.split('/')[1])].get('nodes',[]):
                n=source.nodes.get(nid)
                if n is None:continue
                t=n.get('tags',{})
                if t.get('barrier')not in{'gate','lift_gate','swing_gate','kissing_gate','bollard','cycle_barrier','entrance'}:continue
                gate_rows.append({'id':f'node/{nid}','xy':list(source.projected[nid]),'tags':t,'allowed':not restricted(t)and not non_ground(t),
                    'evidence':'SOURCE_GATE_NODE_MEMBER_OF_BARRIER_WAY','permission_status':'SOURCE_CONDITIONAL_NOT_FIELD_VERIFIED'})
            if gate_rows:gates[sid]=gate_rows
        elif obj.get('gates'):gates[sid]=obj['gates']
    areas=[];roads=[]
    for kind,objects in [('way',source.ways),('relation',source.relations)]:
        for number,obj in objects.items():
            t=obj.get('tags',{});sid=f'{kind}/{number}';refs=obj.get('nodes',[])
            closed=kind=='relation'and t.get('type')=='multipolygon'or len(refs)>=4 and refs[0]==refs[-1]
            if restricted(t)and closed and area_role(t):
                g=source.area(sid)
                if g is None:unlocated.append(sid)
                else:
                    areas.append({'source_id':sid,'geometry':mapping(g),'tags':t,'source_clip_sha256':row['source_sha256']})
                    if sid not in seen:context['hard'].append({'id':sid,'kind':'RESTRICTED','tags':t,'geometry':mapping(g),'gates':[]});seen.add(sid)
            elif restricted(t)and kind=='way'and len(refs)>1 and all(n in source.projected for n in refs)and sid not in seen:
                context['hard'].append({'id':sid,'kind':'RESTRICTED_LINEAR_ACCESS','tags':t,'geometry':mapping(LineString([source.projected[n]for n in refs])),'gates':[]});seen.add(sid)
            face=t.get('highway')=='pedestrian'and t.get('area')=='yes'or t.get('area:highway')in{'pedestrian','footway','path'}
            support=t.get('leisure')in{'park','garden','recreation_ground'}or t.get('surface')in{'paved','paving_stones','concrete','asphalt'}
            if closed and(face or support)and sid not in seen:
                g=source.area(sid)
                if g is not None:
                    typ='PEDESTRIAN_AREA'if face else'PARK'if t.get('leisure')else'PAVING'
                    context['support'].append({'id':sid,'kind':typ,'tags':t,'geometry':mapping(g),'gates':[]});seen.add(sid)
            if kind=='way'and len(refs)>1 and all(n in source.projected for n in refs)and t.get('highway')in MOTOR and t.get('area')!='yes'and not non_ground(t):
                roads.append({'source_id':sid,'kind':'MOTOR_ROAD_CENTERLINE','geometry':mapping(LineString([source.projected[n]for n in refs])),'tags':t})
    coverage=mapping(source_coverage(raw['bounds_wsen']))
    obs={'task_id':'APP/'+scene_id,'crs':'EPSG:32651','domain':{'anchor_xy':[0,0]},'nodes':[],'edges':[],'context':context}
    guards={'crs':'EPSG:32651','source_sha256':row['source_sha256'],'source_parse_status':'PARSED','coverage_geometry':coverage,'access_areas':areas,'barrier_gates':gates,'road_centerlines':roads,'native_road_access_points':[]}
    cfg=read(ROOT/'config/frozen_region.json')
    common=build_contract(obs,guards,cfg,domain=coverage)
    return {'scene_id':scene_id},common,cfg,unlocated

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--scene',default='sh-huangpu-01');a=ap.parse_args();start=time.perf_counter()
    lock=lock_selection();data,common,cfg,unlocated=source_contract(a.scene)
    faces=compile_faces(data,common,cfg)
    dest=ROOT/'data/faces'/a.scene;dest.mkdir(parents=True,exist_ok=True)
    features=[];records=[]
    for f in faces:
        rec=serializable_face(f);records.append(rec)
        if f.get('source_geometry')is not None:features.append({'type':'Feature','geometry':mapping(f['source_geometry']),'properties':{'id':f['id'],'role':'SOURCE_PEDESTRIAN_FACE'}})
        features.append({'type':'Feature','geometry':mapping(f['omega']),'properties':{'id':f['id'],'role':'FULL_FACE_OMEGA','status':f['status']}})
    (dest/'face_geometry.json').write_text(json.dumps({'crs':'EPSG:32651','faces':records},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (dest/'face_geometry.geojson').write_text(json.dumps({'type':'FeatureCollection','crs':{'type':'name','properties':{'name':'EPSG:32651'}},'features':features},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    summary={'role':'SOURCE_ONLY_GEOMETRY_AUDIT_NO_NATIVE_OR_ROUTE_GRAPH_BUILD','scene_id':a.scene,'elapsed_s':time.perf_counter()-start,'source_unlocated':unlocated,
        'new_external_requests':0,'solver_calls':0,'whole_source_constraints':True,'native_permission_boundary_exceptions':'Not needed for new derived face geometry; runtime uses actual full source native graph and full_common',
        'faces':[{'id':f['id'],'status':f['status'],'source':f.get('source_metrics'),'omega':f.get('metrics'),'components':[r['metrics']for r in f['components']],
                  'barriers':len(f.get('barriers',[])),'roads_intersecting_omega':len(f.get('road_constraints',[])),'source_holes':len(f.get('source_holes',[])),'geometry_hash':f['geometry_hash']}for f in faces]}
    (ROOT/'audits'/f'face_source_{a.scene}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
