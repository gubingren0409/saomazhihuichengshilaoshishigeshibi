"""Independent primal/dual check of TA-PG1-01. No shortest-path routine imported."""
from pathlib import Path
import gzip,hashlib,json,zipfile,os
from datetime import datetime,timezone
import numpy as np

ROOT=Path(__file__).resolve().parents[2];TA=ROOT/'track_a/TA-PG1-01'
SOURCE=Path(os.environ.get('PG1_REVIEW_R2_ZIP',ROOT.parent/'PED_AREA_CONNECTIVITY_R2_ROUTE_DIAGNOSIS/delivery/OPEN_REVIEW.zip'))
EXPECTED='3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED
protocol=json.loads((TA/'protocol.json').read_text(encoding='utf8'))
registry=json.loads((TA/'registry.json').read_text(encoding='utf8'))
assert registry['formal_calls']==registry['SSSP_calls']==registry['cap']==8 and registry['complete']
results=[]
with zipfile.ZipFile(SOURCE) as z:
    historical=json.loads(z.read('results/solver_registry.json'))['formal_invocations']
    for case in dict.fromkeys(r['case'] for r in historical):
        xy={};arcs=[]
        for line in gzip.decompress(z.read(f'data/{case}_query_graph.jsonl.gz')).splitlines():
            row=json.loads(line)
            if row['kind']=='node':xy[row['id']]=row['xy']
            else:arcs.append(row)
        ids=list(xy);idx={s:i for i,s in enumerate(ids)}
        raw_u=np.array([idx[r['u']]for r in arcs]);raw_v=np.array([idx[r['v']]for r in arcs])
        options={(r['u'],r['v']):r['options']for r in arcs}
        for old in (r for r in historical if r['case']==case):
            method=old['method'];penalty=0 if method=='F0'else 1
            current=next(r for r in registry['rows']if r['case']==case and r['method']==method)
            run=json.loads((TA/'runs'/(current['invocation_id']+'.json')).read_text(encoding='utf8'))
            certificate=TA/(case+'_'+method+'_certificate.npz')
            with np.load(certificate,allow_pickle=False) as c:
                assert c['ids'].tolist()==ids
                assert np.array_equal(c['u'],raw_u) and np.array_equal(c['v'],raw_v)
                expected=np.array([min(float(o[0])+penalty*float(o[1])for o in a['options'])for a in arcs])
                assert np.array_equal(c['cost'],expected)
                assert np.all(np.isfinite(expected)) and np.all(expected>=0)
                ds=c['ds'];start=idx[old['start_id']];goal=idx[old['door_id']]
                assert ds[start]==0 and np.isfinite(ds[goal])
                finite_source=np.isfinite(ds[raw_u])
                assert np.all(np.isfinite(ds[raw_v[finite_source]]))
                slack=ds[raw_v[finite_source]]-ds[raw_u[finite_source]]-expected[finite_source]
                assert float(slack.max(initial=-np.inf))<=1e-7
                assert run['start_id']==old['start_id'] and run['door_id']==old['door_id']
                assert run['start_xy']==xy[old['start_id']] and run['door_xy']==xy[old['door_id']]
                assert run['source_archive_sha256']==EXPECTED
                assert run['source_code_hashes']==protocol['code']
                assert run['split']=='EXPOSED_DEVELOPMENT_ONLY'
                assert run['answer_cache'] is False and run['new_geometry_admission'] is False and run['new_solver_calls']==1
                path=[old['start_id']];length=hypothesis=cost=0.0
                for seg in run['segments']:
                    assert seg['u']==path[-1] and seg['v']not in path
                    assert seg['xy']==[xy[seg['u']],xy[seg['v']]]
                    choices=options[(seg['u'],seg['v'])]
                    matching=[o for o in choices if o==[seg['length_m'],seg['hypothesis_m'],seg['source_area_ids'],seg['interface_ids'],seg['geometry_kind']]]
                    assert matching and abs(seg['cost_m']-min(o[0]+penalty*o[1]for o in choices))<1e-10
                    length+=seg['length_m'];hypothesis+=seg['hypothesis_m'];cost+=seg['cost_m'];path.append(seg['v'])
                assert path[-1]==old['door_id']
                assert abs(cost-float(ds[goal]))<1e-7 and abs(cost-run['cost_m'])<1e-7
                assert abs(length-run['length_m'])<1e-7 and abs(hypothesis-run['hypothesis_m'])<1e-7
                previous=json.loads(z.read('runs/'+old['invocation_id']+'.json'))['minimum']['cost_m']
                assert abs(cost-previous)<1e-7
                results.append({'case':case,'method':method,'status':'PASS_PRIMAL_DUAL_FOR_FIXED_GRAPH','arcs':len(arcs),'finite_source_arcs_checked':int(finite_source.sum()),'unreachable_source_arcs_excluded_from_inf_subtraction':int((~finite_source).sum()),'max_bellman_violation_m':max(0.0,float(slack.max(initial=-np.inf))),'path_arcs':len(path)-1,'cost_m':cost,'historical_cost_error_m':cost-previous,'source_certificate_sha256':hashlib.sha256(certificate.read_bytes()).hexdigest(),'original_executed_code_hashes':protocol['code']})
out={'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'independent all-arc min-option weights, finite-source Bellman inequalities and original-endpoint path witness; no author function or shortest path call','new_reviewer_solver_calls':0,'formal_author_calls':8,'checks':results,'constraints':'inherit original R2 graph only; no physical/public-access validation','result':'NO_BUSINESS_GAIN_CLAIMED; timing decision belongs to measured weight construction; no validation/blind inference'}
(ROOT/'reviews/independent_track_a.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
assert len(results)==8
print(json.dumps({'verified_requests':8,'arcs_checked':sum(r['arcs']for r in results),'new_reviewer_solver_calls':0}))
