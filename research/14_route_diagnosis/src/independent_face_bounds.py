"""Independent conservative Euclidean cost bounds, not new route calls."""
from pathlib import Path
import argparse,csv,hashlib,io,json,zipfile
from shapely.geometry import shape,Point
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(r'E:/智慧城市和位置服务/_task_runtime/PED_AREA_CONNECTIVITY_R1/delivery/PED_AREA_CONNECTIVITY_R1_OPEN_REVIEW.zip')
def main(archive=ARCHIVE):
    rows=[]
    with zipfile.ZipFile(archive)as z:
        lock={s['scene_id']:s for s in json.loads(z.read('data/connectivity/source_selection_lock.json'))['scenes']}
        for q in csv.DictReader(io.StringIO(z.read('results/sample_results.csv').decode('utf-8-sig'))):
            if q['role']!='BASELINE_POSITIVE'or q['mode']!='CONDITIONAL_SEAMS':continue
            body=json.loads(z.read(q['response_path']));segments=body['route']['segments']
            start=Point(segments[0]['xy'][0]);end=Point(segments[-1]['xy'][-1]);cost=body['route']['cost_weighted_m']
            for face in json.loads(z.read('data/connectivity/'+q['scene_id']+'_faces.json')):
                if face['source_id']not in lock[q['scene_id']]['added_area_ids']:continue
                omega=shape(face['omega']);bound=None if omega.is_empty else start.distance(omega)+end.distance(omega)
                rows.append({'request_id':q['request_id'],'source_id':face['source_id'],'scene_id':q['scene_id'],
                    'euclidean_lower_bound_m':bound,'baseline_cost_m':cost,'strict_cost_exclusion':bound is not None and bound>cost+1e-8})
    summary={q:{'face_count':len(v:=[r for r in rows if r['request_id']==q]),
        'euclidean_cost_excluded':sum(r['strict_cost_exclusion']for r in v),
        'min_bound_m':min(r['euclidean_lower_bound_m']for r in v if r['euclidean_lower_bound_m']is not None)}
        for q in sorted({r['request_id']for r in rows})}
    output={'reviewer':'/root/r2_independent','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'Geometric lower bound for routes visiting an admitted new Omega; does not constrain exact interfaces on old faces',
        'proof':'Cost >= geometric length >= dist(start,Omega)+dist(Omega,end); all frozen multipliers >=1. Separate distance minima weaken the bound, never strengthen it.',
        'APP_solver_calls':0,'rows':rows,'summary':summary}
    (ROOT/'audits/independent_face_lower_bounds.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,default=ARCHIVE);args=parser.parse_args();main(args.baseline)
