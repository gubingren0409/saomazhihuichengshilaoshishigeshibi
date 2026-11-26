"""Verify and safely unpack a fixed archive, then actually rerun five representative inputs.

Core canonical hashes and route objects must match exactly. Runtime fields and
gzip headers are deliberately not claimed byte-reproducible.
"""
import argparse,hashlib,json,shutil,subprocess,sys,tempfile,time,zipfile,stat,gzip,base64
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
CASES=['Wc4183046a70_G_080','W6daddd19fdb_G_080','W745941f0f92_G_080','W0440b97497a_N_080','W7a6b5a10076_G_080','NORTH_160']
def read(p):return json.loads(p.read_text(encoding='utf8'))
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def extract(archive,out,verify_manifest=True):
    if out.exists():raise FileExistsError(out)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();assert len(infos)==len(set(x.filename for x in infos));assert z.testzip() is None
        for x in infos:
            p=PurePosixPath(x.filename);assert not p.is_absolute() and '..' not in p.parts and ':' not in x.filename and not stat.S_ISLNK(x.external_attr>>16)
        if verify_manifest:
            rows=json.loads(z.read('MANIFEST.json'))['entries'];assert {x['path'] for x in rows}==set(z.namelist())-{'MANIFEST.json'}
            for x in rows:
                with z.open(x['path']) as f:
                    h=hashlib.sha256();size=0
                    for b in iter(lambda:f.read(1024*1024),b''):h.update(b);size+=len(b)
                assert h.hexdigest()==x['sha256'] and size==x['bytes']
        z.extractall(out)
def execute(root,output,cases):
    sys.path.insert(0,str(root))
    results=[];started=time.perf_counter()
    manifest=read(root/'data/task_manifest.json')['instances']
    output.mkdir(parents=True,exist_ok=False)
    test=subprocess.run([sys.executable,'-X','utf8','-B','scripts/run_tests_receipt.py','--out',str(output)],cwd=root,capture_output=True,text=True,timeout=120)
    (output/'test_execution.txt').write_text(test.stdout+test.stderr,encoding='utf8');assert test.returncode==0,test.stderr
    test_receipt=read(output/'test_receipt.json')
    for ident in cases:
        row=next(x for x in manifest if x['id']==ident)
        work=output/ident;work.mkdir()
        files={'observed.json':root/row['observed'],'query.json':root/row['query'],'guards.json':root/row.get('guards',f'data/common_guards_v2/{ident}.json'),'config.json':root/'config/frozen_region.json','historical_methods.json':root/'config/historical_methods.json'}
        if row.get('natural'):
            files['route_graph.json']=root/row['route_graph']
            files['classifier_surface_cache.json']=root/'data/classifier_cache/NORTH_160.json'
        elif row.get('classifier_cache'):files['classifier_surface_cache.json']=root/row['classifier_cache']
        for dst,src in files.items():shutil.copyfile(src,work/dst)
        code=hashlib.sha256(''.join(sha(p) for p in sorted((root/'src').glob('*.py'))).encode()).hexdigest()
        conf=hashlib.sha256(''.join(sha(root/p) for p in ('config/frozen_region.json','config/historical_methods.json','config/contract.json')).encode()).hexdigest()
        cmd=[sys.executable,'-X','utf8','-B',str(root/'src/predict_free.py'),'--input-id',ident,'--radius',str(row['context_radius_m']),'--code-sha',code,'--config-sha',conf]
        if (root/'data/predictions'/ident/'F1-L1.json').is_file():cmd.append('--sensitivity')
        if row.get('natural'):cmd.extend(['--natural','--natural-cache'])
        elif row.get('classifier_cache'):cmd.append('--classifier-cache')
        done=subprocess.run(cmd,cwd=work,text=True,capture_output=True,timeout=600)
        (work/'execution.txt').write_text(done.stdout+done.stderr,encoding='utf8');assert done.returncode==0,done.stderr
        methods=[]
        for p in sorted(work.glob('*.prediction.json')):
            method=p.name.replace('.prediction.json','');expected=root/'data/predictions'/ident/(method+'.json')
            if not expected.exists():continue
            actual=read(p);old=read(expected)
            checks={field:digest(actual[field])==digest(old[field]) for field in ('surface','routes','base_routes')}
            checks['unweighted_graph_exact']=actual['graph']['graph_sha256']==old['graph']['graph_sha256']
            checks['terminal_graph_exact']=actual['graph']['terminal_graph_sha256']==old['graph']['terminal_graph_sha256']
            if 'reference' in row:
                from src.score_free import score_reference
                a=score_reference(actual,read(root/row['reference']))[0];b=score_reference(old,read(root/row['reference']))[0]
                checks['metrics_exact']=digest(a)==digest(b)
            gap_replay=None
            if ident=='W7a6b5a10076_G_080':
                from shapely.geometry import shape,LineString
                from shapely.ops import unary_union
                evidence=read(root/'audits/access_area_prediction_impact.json')
                private=shape(evidence['source_geometry'])
                assumed=unary_union([shape(c['geometry']) for c in actual['surface']['cells'] if c['walkability_state']=='INFERRED_WALKABLE'])
                overlap=assumed.intersection(private).area
                expected_assumed=unary_union([shape(c['geometry']) for c in old['surface']['cells'] if c['walkability_state']=='INFERRED_WALKABLE'])
                expected_overlap=expected_assumed.intersection(private).area
                crossings=sum(LineString(s['xy']).intersection(private.buffer(-1e-7)).length for q in actual['routes'].values() for s in q['edges'])
                restricted=unary_union([shape(c['geometry']) for c in actual['surface']['cells'] if c['walkability_state']=='RESTRICTED'])
                restricted_overlap=restricted.intersection(private).area
                needed=private.intersection(shape(actual['surface']['domain'])).area
                repaired=bool(row.get('guards'))
                checks['known_policy_gap_exact_scope_reproduced']=abs(overlap-expected_overlap)<=1e-5 and crossings<=1e-5
                if repaired:checks['source_permission_repair_reproduced']=overlap<=1e-5 and restricted_overlap>=needed-1e-5
                gap_replay=dict(source_id=evidence['source_id'],assumed_private_overlap_m2=overlap,actual_private_route_interior_m=crossings,
                                restricted_private_overlap_m2=restricted_overlap,required_source_private_area_m2=needed,
                                regional_policy_status='REPAIRED_KNOWN_SOURCE_PERMISSION_AREA' if repaired else 'NOT_PASSED_KNOWN_GAP' if overlap>1e-5 else 'NO_ASSUMED_ACCESS_OVERLAP',
                                acceptance='REPRODUCED_VERSION_AND_SOURCE_POLICY_NOT_FIELD_SAFETY_PROOF')
            assert all(checks.values()),(ident,method,checks)
            methods.append({'method':method,'checks':checks,'surface_sha256':actual['surface']['sha256'],'routes_sha256':digest(actual['routes']),'known_gap_replay':gap_replay})
        results.append(dict(id=ident,methods=methods,region_builds=read(work/'execution.json')['region_builds']));print('REPLAY',ident,'PASS',len(methods),flush=True)
    # The page builder reads only packaged observations/guards/results/display background.
    visual_before={p.relative_to(root).as_posix():sha(p) for p in (root/'visuals').glob('*') if p.is_file() and p.suffix in ('.html','.js','.svg','.png')}
    from src.build_free_visuals import assemble
    visual_data=assemble(root);visual_data.pop('build_index')
    payload=json.dumps(visual_data,ensure_ascii=False,separators=(',',':')).encode()
    rebuilt=(root/'src/free_map.html').read_text(encoding='utf8').replace('__PAYLOAD__',base64.b64encode(gzip.compress(payload,mtime=0)).decode()).replace('__SCRIPT__',(root/'src/free_map.js').read_text(encoding='utf8'))
    (output/'rebuilt_index.html').write_text(rebuilt,encoding='utf8')
    page_exact=sha(output/'rebuilt_index.html')==sha(root/'visuals/index.html')
    assert page_exact,'Rebuilt page differs from packaged authoritative data'
    visual_after={rel:sha(root/rel) for rel in visual_before}
    visual_checks={rel:visual_before[rel]==visual_after[rel] for rel in visual_before}
    result=dict(status='PASS',cases=results,tests=test_receipt,elapsed_s=time.perf_counter()-started,
        comparison='EXACT_CANONICAL_CORE_SURFACE_GRAPH_ROUTES_METRICS; volatile process/runtime and gzip bytes excluded',
        scope='4 controlled representatives plus W7 source-permission repair and natural north; main methods and only existing cost comparisons; not whole matrix rerun. Preserved R0 defect and final corrected source policy are versioned separately; not field safety proof.',
        replay_region_builds=sum(x['region_builds'] for x in results)+test_receipt['synthetic_region_builds'],build_budget_role='FINAL_ARCHIVE_REPLAY_SEPARATE_FROM_EXPERIMENT_CAP',
        rebuilt_page_byte_checks=visual_checks,rebuilt_index_exact=page_exact,
        figure_scope='Page actually reassembled to runtime, immutable packaged members untouched. PNG/SVG exports separately browser-replayed to external output; six earlier figures remain original verified exports.')
    (output/'replay_receipt.json').write_text(json.dumps(result,indent=2),encoding='utf8');return result
def main(a):
    if a.archive:
        archive=a.archive.resolve();out=a.out.resolve();extract(archive,out)
        frozen=out/'input_contract/frozen/R4_CONTEXT_OPEN_REVIEW.zip';assert sha(frozen)=='40f8e18d76d04819d66a3bd526ecb2b74fc83201b3b58452881a6576b6651cbf'
        extract(frozen,out/'frozen_context')
        receipt=execute(out,out/'runtime/final_replay',a.cases or CASES)
        receipt['archive_sha256']=sha(archive)
        a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,indent=2),encoding='utf8')
    else:execute(ROOT,a.out.resolve(),a.cases or CASES)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--receipt',type=Path,default=ROOT/'delivery/replay_receipt.json');p.add_argument('--cases',nargs='+');main(p.parse_args())
