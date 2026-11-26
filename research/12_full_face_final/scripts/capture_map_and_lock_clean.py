"""Read-only local scene-view export, then pre-solver stable unused-start lock."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.planner import scene_view
def main():
    folder=ROOT/'data/map_views';folder.mkdir(exist_ok=True)
    path=folder/'sh-huangpu-01.json'
    if not path.exists():
        view=scene_view('sh-huangpu-01','node/6897141353')
        path.write_text(json.dumps(view,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    else:view=json.loads(path.read_text(encoding='utf-8'))
    known=set();old=ROOT.parent/'OSM_GEOAPIFY_KNOWN_ENTRANCE_E2E_R1/runs/app';n=0
    for base in(ROOT/'runs/app',old):
        for p in base.glob('*.json'):
            q=json.loads(p.read_text(encoding='utf-8')).get('input',{})
            if q.get('scene_id')=='sh-huangpu-01':known.add(q.get('start_id'));n+=1
    door=next(d for d in view['doors']if d['id']=='node/6897141353')
    import math
    choices=sorted((s for s in view['starts']if 50<=math.dist(s['xy'],door['xy'])<=200 and s['id']not in known),key=lambda s:s['id'])
    if not choices:raise ValueError('NO_UNUSED_ELIGIBLE_START')
    s=choices[0];q={'scene_id':'sh-huangpu-01','start_id':s['id'],'door_id':door['id'],'purpose':'APPROACH_OUTSIDE','method':'F1','area_routing':'FULL_FACE','request_id':'CLEAN-NEW-START-LOCKED'}
    destination=ROOT/'data/clean_new_request.json'
    if destination.exists():raise FileExistsError('Preserve existing clean-query lock')
    destination.write_text(json.dumps(q,indent=2),encoding='utf-8')
    receipt={'selection':'Stable native ID first among50-200m source starts absent from old/current request logs; locked before first solver call',
        'selected':s,'prior_logs_read':n,'prior_start_IDs':sorted(x for x in known if x),'unused_eligible_count':len(choices),'request':q,
        'map_source_sha256':view['source_info']['source_sha256'],'map_view_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'route_solver_calls':0,'new_external_requests':0,'map_capture_repair':'Direct local scene_view export after prior HTTP snapshot was interrupted by premature own-service stop; same function/data, no image substitute'}
    (ROOT/'audits/clean_new_start_selection.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'view_bytes':path.stat().st_size,'start':s['id'],'unused_choices':len(choices)}))
if __name__=='__main__':main()
