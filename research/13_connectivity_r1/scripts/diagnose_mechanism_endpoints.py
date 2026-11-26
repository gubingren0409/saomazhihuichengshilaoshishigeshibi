"""Explain frozen endpoint refusals from raw source and common masks, no search."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from shapely.geometry import Point,LineString,shape
from src.frozen_scene.native_adapter import Source
from src.common_constraints import parsed_contract,edge_conflicts
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    manifest={s['scene_id']:s for s in read(ROOT/'data/scene_manifest.json')['scenes']};queries=read(ROOT/'data/connectivity/mechanism_request_endpoints_lock.json')['queries'];cache={};rows=[]
    for q in queries:
        sid=q['scene_id']
        if sid not in cache:
            source=Source(read(ROOT/manifest[sid]['source_path']));common=read(ROOT/f'data/connectivity/{sid}_full_common.json')
            # Export contains contract fields, not parsed geometry objects.
            if 'contract'in common:common=common['contract']
            cache[sid]=(source,common,parsed_contract(common),read(ROOT/f'data/connectivity/{sid}_native_lines.json'))
        source,common,parsed,lines=cache[sid];coverage=shape(common['coverage_geometry'])
        for side in ('start','end'):
            e=q[side];number=int(e['native_id'].split('/')[1]);point=Point(e['xy']);incident=[]
            for way in lines:
                ns=way.get('nodes',[])
                if number not in ns:continue
                for i,(a,b)in enumerate(zip(ns,ns[1:])):
                    if number not in (a,b)or a not in source.projected or b not in source.projected:continue
                    line=LineString([source.projected[a],source.projected[b]])
                    incident.append({'source_id':way['source_id'],'segment_index':i,'nodes':[a,b],'source_eligibility':way['status'],
                        'whole_segment_coverage':coverage.covers(line),'whole_segment_common_reasons':edge_conflicts(line,parsed,native=True,tags=way['tags'],source_id=way['source_id']),
                        'tags':way['tags'],'geometry':{'type':'LineString','coordinates':list(line.coords)}})
            rows.append({'mechanism_id':q['mechanism_id'],'scene_id':sid,'side':side,'original_endpoint':e,'source_xy_exact':list(source.projected[number])==e['xy'],
                'point_in_actual_coverage':coverage.covers(point),'distance_to_coverage_m':coverage.distance(point),'incident_raw_segments':incident,
                'scope':'SOURCE_AND_COMMON_MASK_DIAGNOSTIC; NO_SOLVER_OR_ENDPOINT_RESELECTION; map absence/refusal does not establish physical no-path.'})
    target=ROOT/'results/mechanism_endpoint_diagnosis.json';target.write_text(json.dumps({'rows':rows,'solver_calls':0},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'rows':len(rows),'outside_endpoint_ids':[r['original_endpoint']['id']for r in rows if not r['point_in_actual_coverage']],'path':str(target)}))
if __name__=='__main__':main()
