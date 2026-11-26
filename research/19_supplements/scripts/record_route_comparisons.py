from pathlib import Path
import json,csv,hashlib
from shapely.geometry import LineString,shape
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'Q7-DYNAMIC-CLOSURE-SIMULATION-R1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
rows=[json.loads(z)for z in(D/'dynamic_route_results.jsonl').read_text(encoding='utf-8').splitlines()];cases=read(D/'dynamic_scenarios.json')['cases'];out=[]
for r in rows:
 if r.get('control_variant')!='STATE_INJECTION_ADAPTER':continue
 case=next(c for c in cases if c['scene_id']==r['scene_id']);base=next(x for x in rows if x.get('scene_id')==r['scene_id']and x.get('state')=='S0'and x.get('repeat')==0 and x.get('control_variant')=='STATE_INJECTION_ADAPTER');base_doc=read(D/base['output_file']);selected=next(s for s in base_doc['route']['segments']if s.get('edge_id')==case['selected_native_edge_id']);closed=LineString(selected['xy']);doc=read(D/r['output_file']);segments=doc['route']['segments']if doc.get('route')else None
 out.append({'run_id':r['run_id'],'scene_id':r['scene_id'],'entrance_id':r['entrance_id'],'state':r['state'],'repeat':r['repeat'],'status':r['status'],'route_length_m':r['route_length_m'],'baseline_length_m':base['route_length_m'],'delta_length_m':r['route_length_m']-base['route_length_m']if r['route_length_m']is not None else None,'assumption_length_m':r['assumption_length_m'],'selected_source_id':selected['source_id'],'selected_source_highway':selected['tags'].get('highway'),'selected_edge_length_m':closed.length,'selected_edge_geometry_overlap_m':sum(LineString(s['xy']).intersection(closed).length for s in segments)if segments is not None else None,'simulated_obstacle_overlap_m':sum(LineString(s['xy']).intersection(shape(case['obstacle'])).length for s in segments)if segments is not None and r['state']=='S3'else None,'route_source_file':r['output_file'],'route_source_sha256':hashlib.sha256((D/r['output_file']).read_bytes()).hexdigest(),'meaning':'Source-mapped conditional model; no field truth. S2 removes directed native edge, not a measured real closure width.'})
with(D/'replanning_geometry_comparison.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
# Inventory of available model routes for a FUTURE field survey, never field observations.
field=ROOT/'Q6-FIELD-TRUTH-COMPARISON-R1';q2=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';available=[]
for i,kind in enumerate(['MAPPED_FACE_DOMINATED','CONTAINS_CONDITIONAL_ASSUMPTION','NATIVE_LINE_DOMINATED']):
 p=q2/f'outputs/Q2-TARGET-{i}-REGISTERED_DOOR.json';row=read(p)['row'];available.append({'source_run_id':row['run_id'],'scene_id':row['scene_id'],'building_id':row['building_id'],'entrance_id':row['entrance_id'],'route_profile':kind,'source_file':p.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'field_observed':False,'field_verification_status':'BLOCKED_BY_MISSING_INPUT','role':'Existing model-route inventory only; 3 routes in 2 buildings, not the requested 6 surveyed routes'})
with(field/'available_model_route_candidates.csv').open('w',encoding='utf-8-sig',newline='')as f:w=csv.DictWriter(f,fieldnames=list(available[0]));w.writeheader();w.writerows(available)
print('ROUTE_COMPARISONS_RECORDED',len(out),'FIELD_OBSERVATIONS',0)
