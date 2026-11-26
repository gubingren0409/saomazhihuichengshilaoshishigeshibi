"""Separate review checks; never invokes the author's route/classification functions."""
from __future__ import annotations
import argparse, collections, csv, datetime, gzip, hashlib, json, math, pathlib, subprocess, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'SMART_CITY_WALKABILITY_FOUNDATION_PG1'

def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def old_delivery():
    archive = OLD / 'delivery/PG1_FOUNDATION_REVIEW.zip'
    receipt_path = OLD / 'delivery/INDEPENDENT_DELIVERY_RECEIPT.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    failures = []
    checks = {'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
              'receipt_sha256': sha(receipt_path), 'historical_receipt_time': receipt['at_utc']}
    if checks['archive_sha256'] != '7c9ed58766177e8906defc257555b0d7ba0d92c8e97129a691f9f6e72dffef7c': failures.append('archive SHA mismatch')
    if receipt['archive_sha256'] != checks['archive_sha256']: failures.append('receipt archive binding')
    with zipfile.ZipFile(archive) as z:
        checks['members'] = len(z.infolist())
        checks['CRC'] = z.testzip()
        manifest = json.loads(z.read('MANIFEST_SHA256.json'))
        checks['manifest_count'] = len(manifest['files'])
        names = set(z.namelist())
        expected = {i['path'] for i in manifest['files']} | {'MANIFEST_SHA256.json'}
        if names != expected: failures.append('manifest/member set mismatch')
        for i in manifest['files']:
            name = pathlib.PurePosixPath(i['path'])
            if name.is_absolute() or '..' in name.parts: failures.append('unsafe member:' + str(name))
            data = z.read(i['path'])
            if len(data) != i['bytes'] or hashlib.sha256(data).hexdigest() != i['sha256']: failures.append('member:' + i['path'])
        current_checked = 0
        working_warnings = []
        for i in manifest['files']:
            current = OLD / i['path']
            if not current.is_file() or current.stat().st_size != i['bytes'] or sha(current) != i['sha256']:
                working_warnings.append({'path': i['path'], 'exists': current.is_file(), 'expected_sha256': i['sha256'], 'actual_sha256': sha(current) if current.is_file() else None})
            current_checked += 1
        checks['original_root_manifest_files_checked'] = current_checked
        checks['original_root_warnings'] = working_warnings
        checks['working_root_scope_note'] = 'Historical receipt bound the sealed archive and prior actual replay. Current missing working-map files are recorded separately; no claim that all343 mutable working files exist now. Sealed copies remain present and verified.'
    if checks['members'] != 344 or checks['manifest_count'] != 343 or checks['CRC'] is not None: failures.append('member/CRC/count mismatch')
    evidence = []
    for e in receipt['evidence']:
        p = OLD / 'delivery' / pathlib.Path(e['path'])
        row = {'path': str(p), 'exists': p.is_file()}
        if row['exists']: row.update(bytes=p.stat().st_size, sha256=sha(p))
        row['pass'] = row['exists'] and row['bytes'] == e['bytes'] and row['sha256'] == e['sha256']
        if not row['pass']: failures.append('receipt evidence:' + e['path'])
        evidence.append(row)
    checks['referenced_evidence'] = evidence
    machine = json.loads((OLD / 'delivery/INDEPENDENT_MACHINE_REPLAY_RECEIPT.json').read_text(encoding='utf-8-sig'))
    extracted = pathlib.Path(machine['extracted_root'])
    replay = []
    for step in machine['steps']:
        p = extracted / 'reviews' / (step['name'] + '.json')
        src = extracted / 'reviews/src' / (step['name'] + '.py')
        row = {'name': step['name'], 'output_path': str(p), 'source_path': str(src), 'output_exists': p.is_file(), 'source_exists': src.is_file()}
        if p.is_file(): row['output_sha256'] = sha(p)
        if src.is_file(): row['source_sha256'] = sha(src)
        row['pass'] = row.get('output_sha256') == step['replayed_output_sha256'] and row.get('source_sha256') == step['frozen_review_source_sha256']
        if not row['pass']: failures.append('machine replay actual files:' + step['name'])
        replay.append(row)
    checks['replay_actual_files'] = replay
    inventory = list(csv.DictReader((OLD / 'audit/PUBLIC_FILE_INVENTORY.csv').open(encoding='utf-8-sig', newline='')))
    checks['public_inventory_count'] = len(inventory)
    for i in inventory:
        p = OLD / 'repository' / i['path']
        if not p.is_file() or sha(p) != i['sha256'] or p.stat().st_size != int(i['bytes']): failures.append('original public file:' + i['path'])
    head = subprocess.run(['git', '-C', str(OLD / 'repository'), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    checks['old_local_head'] = head
    if head != receipt['final_local_commit']: failures.append('old HEAD changed')
    checks.update(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), reviewer='/root/resume_review',
                  scope='Fresh archive bytes/CRC/all343 manifest rows; nine receipt dependencies; five actual replay outputs and five reviewer sources; original38 files and local HEAD. No new historical scientific runs.',
                  new_solver_calls=0, new_sssp_calls=0, new_network_requests=0, bad_request_cause='UNKNOWN', failures=failures,
                  status='PASS_FOR_OLD_FIXED_DELIVERY_EVIDENCE' if not failures else 'FAIL')
    out = ROOT / 'reviews/independent_old_delivery.json'
    out.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:checks[k] for k in ['status','archive_sha256','members','manifest_count','public_inventory_count','failures']}, ensure_ascii=False))
    return not failures

def contracts():
    """Recount retained source responses, not source-author summary functions."""
    rows=json.loads((ROOT/'contracts/module_contracts.json').read_text(encoding='utf-8-sig'))
    receipt=json.loads((ROOT/'contracts/source_verification.json').read_text(encoding='utf-8-sig'))
    candidates=json.loads((OLD/'phase2/candidate_registry.json').read_text(encoding='utf-8-sig'))
    failures=[];counts={};file_checks=[]
    for c in candidates:
        actual={}
        for rel,expected in c['source_hashes'].items():
            p=OLD/'phase2'/rel
            h=sha(p);data=json.loads(p.read_text(encoding='utf-8-sig'))
            layer='sidewalk' if 'sidewalk' in rel else 'buildings'
            actual[layer]=len(data['features'])
            if h!=expected: failures.append('candidate source:'+rel)
        counts[c['scene_id']]=actual
        numeric_counts={k:v for k,v in c['object_counts'].items() if isinstance(v,int)}
        if actual!=numeric_counts: failures.append('source vs candidate numeric counts:'+c['scene_id'])
    for r in receipt['verified_files']:
        p=pathlib.Path(r['path']);ok=p.is_file()and p.stat().st_size==r['bytes']and sha(p)==r['sha256']
        file_checks.append({'path':str(p),'pass':ok})
        if not ok:failures.append('referenced file:'+str(p))
    if len(rows)!=20 or len({(r['candidate_id'],r['module']) for r in rows})!=20: failures.append('expected5x4module rows')
    for r in rows:
        cid=r['candidate_id']
        if r['retained_counts']!=counts[cid]:failures.append('module count:'+cid)
        if r['split']!='UNASSIGNED_NOT_FROZEN' or r['public_release']!='NOT_APPROVED' or not r['input_exposure'].startswith('EXPOSED'):failures.append('exposure/gate:'+cid)
        if r['module']=='D' and r['status']!='MISSING_INPUT_AND_REFERENCE':failures.append('door maturity overclaim:'+cid)
        if r['module'] in {'B','C'} and cid.startswith('nyc') and not r['status'].startswith('PARTIAL_'):failures.append('NYCpartial module:'+cid)
    proposal=json.loads((ROOT/'contracts/next_acquisition_proposal.json').read_text(encoding='utf-8-sig'))
    if proposal['new_requests_this_round']!=0 or proposal['new_bytes_this_round']!=0:failures.append('unexpected newacquisition')
    if sum(x['requests_max'] for x in proposal['sites'])!=proposal['total_requests_max']:failures.append('proposalrequestbudget')
    if sum(x['read_bytes_max'] for x in proposal['sites'])!=proposal['total_read_bytes_max']:failures.append('proposalbytebudget')
    out={'reviewer':'/root/resume_review','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_response_counts':counts,'source_and_terms_files_checked':file_checks,'module_rows':len(rows),'proposal_not_executed':True,'new_network_requests':0,'new_solver_calls':0,'failures':failures,'status':'PASS_FOR_EXISTING_SOURCE_MODULE_CONTRACTS'if not failures else'FAIL','limits':['Source geometry counts/hash and readiness boundary checked; no new legal opinion, source acquisition, independently surveyed reference or accuracy evaluation.','Future200mwindows are proposed not frozen exact coordinates; require next authorization and pre-result lock.']}
    (ROOT/'reviews/independent_contracts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False));return not failures

def trial():
    """Check every saved graph edge and shortest-path dual certificate without solving."""
    lock=json.loads((ROOT/'audit/window_lock.json').read_text(encoding='utf-8-sig'))
    records=[json.loads(x) for x in (ROOT/'audit/experiment_registry.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    failures=[];checks=[];edge_count=0;native_count=0;side_count=0;cross_count=0;cert_count=0
    executed_source=ROOT/'results/pre_fix/executed_street_side.py'
    executed_sha=sha(executed_source) if executed_source.is_file() else sha(ROOT/'scripts/street_side.py')
    engineering=json.loads((ROOT/'results/engineering_fix_receipt.json').read_text(encoding='utf-8-sig')) if (ROOT/'results/engineering_fix_receipt.json').is_file() else None
    if engineering and engineering['parent_code_sha256']!=executed_sha:failures.append('engineering parent source binding')
    metric=json.loads((ROOT/'results/metric_qualification_receipt.json').read_text(encoding='utf-8-sig')) if (ROOT/'results/metric_qualification_receipt.json').is_file() else None
    repair=json.loads((ROOT/'results/R0_cost_repair_receipt.json').read_text(encoding='utf-8-sig')) if (ROOT/'results/R0_cost_repair_receipt.json').is_file() else None
    if metric:
        first18=b''.join((ROOT/'audit/experiment_registry.jsonl').read_bytes().splitlines(keepends=True)[:18])
        if hashlib.sha256(first18).hexdigest()!=metric['source_registry_sha256_unchanged']:failures.append('first18 original registry changed by reporting correction')
        if not repair and sha(ROOT/'scripts/street_side.py')!=metric['final_source_sha256']:failures.append('corrected final source binding')
        csvp=ROOT/'results/pre_R0_cost_fix/query_results.csv' if repair else ROOT/'results/query_results.csv'
        mapp=ROOT/'results/pre_R0_cost_fix/trial_map_data.json' if repair else ROOT/'maps/trial_map_data.json'
        if sha(csvp)!=metric['csv_after_sha256']or sha(mapp)!=metric['map_after_sha256']:failures.append('corrected reporting outputs historical binding')
        normalized=list(csv.DictReader((ROOT/'results/query_results.csv').open(encoding='utf-8-sig',newline='')))
        for row in normalized:
            if row['scope']=='TOPOLOGY_ONLY_SCHEMATIC'and row['physical_route_length_m']!='':failures.append('axis/schematic misreported as physical walking length')
    motor={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road'}
    ordinary={'residential','service','living_street','unclassified'}
    if len(lock['windows'])>3 or len(records)>24:failures.append('budget exceeded')
    if lock['new_graphs_or_routes_before_lock']!=0:failures.append('lock scope')
    for window in lock['windows']:
        mode=window['window_id'];ip=ROOT/window['input_path'];p=json.loads(ip.read_text(encoding='utf-8-sig'))
        if sha(ip)!=window['input_sha256']:failures.append('input hash:'+mode)
        if sha(p['source_path_original'])!=window['source_sha256']:failures.append('raw source hash:'+mode)
        raw=json.loads(pathlib.Path(p['source_path_original']).read_text(encoding='utf-8-sig'))
        original_objects={(o['type'],str(o['id'])):o for o in raw['elements']}
        for k,o in p['ways'].items():
            if o!=original_objects.get(('way',k)):failures.append('native way changed:'+mode+':'+k)
        for k,o in p['nodes'].items():
            if o!=original_objects.get(('node',k)):failures.append('native node changed:'+mode+':'+k)
        del raw,original_objects
        historical={}
        with gzip.open(OLD/'phase1/data'/window['scene_id']/'native_admission.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                row=json.loads(line);historical[(row['source_id'],row['segment_index'])]=row
        local={}
        for row in p['native_admission']:
            key=(row['source_id'],row['segment_index']);local[key]=row
            if historical.get(key)!=row:failures.append('frozen admission changed:'+mode+':'+str(key))
        del historical
        variants={}
        for variant in ['R0','R1','R2']:
            gp=ROOT/'results/graphs'/f'{mode}_{variant}.json';g=json.loads(gp.read_text(encoding='utf-8-sig'));variants[variant]=g
            ids=set();native_keys=set();side_ids=set()
            for e in g['edges']:
                edge_count+=1
                if e['edge_id']in ids:failures.append('duplicate edgeid:'+e['edge_id'])
                ids.add(e['edge_id'])
                if e['u']==e['v'] or e['u']not in g['nodes']or e['v']not in g['nodes']:failures.append('invalid graph endpoint:'+e['edge_id'])
                expected=e['cost_f0']*(2 if e['hypothesis'] else 1)
                if not math.isclose(expected,e['cost_f1'],rel_tol=1e-12):failures.append('hypothesis cost identity:'+e['edge_id'])
                if ':native:'in e['edge_id']:
                    native_count+=1;idx=int(e['edge_id'].rsplit(':',1)[1]);row=local.get((e['source_id'],idx))
                    if row is None or row['status']!='KEEP_NATIVE':failures.append('native lacks frozen admission:'+e['edge_id']);continue
                    if row['xy']!=e['xy']or row['source_node_ids']!=e['source_node_ids']or row['directions']!=e['directions']or row['evidence']!=e['evidence']:failures.append('native geometry/evidence mutation:'+e['edge_id'])
                    if e['geometry_status']!='SOURCE_GEOMETRY':failures.append('native display identity:'+e['edge_id'])
                    native_keys.add((e['source_id'],idx))
                elif ':side:'in e['edge_id']:
                    side_count+=1;t=p['ways'][e['source_id'].split('/')[1]]['tags'];side=e['side'];side_ids.add((e['source_id'],side,int(e['edge_id'].rsplit(':',1)[1])))
                    if e['geometry_status']!='SCHEMATIC'or e['layer']not in {'tag_derived','hypothesis'}:failures.append('side mislabeled:'+e['edge_id'])
                    if e['u'].split(':node/')[0]!=e['source_id']+':'+side or e['v'].split(':node/')[0]!=e['source_id']+':'+side:failures.append('side identity merge:'+e['edge_id'])
                    if e['layer']=='hypothesis':
                        if variant!='R2'or t.get('highway')not in ordinary or any(k.startswith('sidewalk')for k in t)or not e['hypothesis']:failures.append('default policy violation:'+e['edge_id'])
                    else:
                        val=t.get('sidewalk:'+side,t.get('sidewalk:both',t.get('sidewalk')))
                        if val not in {'yes','both',side}or e['hypothesis']:failures.append('tag support missing:'+e['edge_id'])
                    if any(t.get(k)not in {None,'','0','no','false'}for k in ['layer','level','bridge','tunnel','indoor','repeat_on']):failures.append('non-ground side admitted:'+e['edge_id'])
                    if t.get('foot',t.get('access'))in {'no','private','customers','delivery','agricultural','forestry'}:failures.append('forbidden side:'+e['edge_id'])
                elif ':crossing:'in e['edge_id']:
                    cross_count+=1;n=int(e['source_id'].split('/')[1]);nt=p['nodes'][str(n)].get('tags',{});road=p['ways'][e['road_source_id'].split('/')[1]]
                    if not(nt.get('highway')=='crossing'or nt.get('footway')=='crossing')or n not in road['nodes']:failures.append('invented crossing:'+e['edge_id'])
                    if e['geometry_status']!='SCHEMATIC'or e['evidence']!='SOURCE_CROSSING_NODE_TOPOLOGY_ONLY':failures.append('crossing geometry overclaim:'+e['edge_id'])
                    if e['u'].split(':node/')[0]!=e['road_source_id']+':'+e['side']or not e['v'].startswith('native:'+str(n)+':'):failures.append('crossing merges wrong side:'+e['edge_id'])
                else:failures.append('unapproved graph edge:'+e['edge_id'])
            expected={(r['source_id'],r['segment_index'])for r in p['native_admission']if r['status']=='KEEP_NATIVE'and(variant=='R0'or p['ways'][r['source_id'].split('/')[1]]['tags'].get('highway')not in motor)}
            if native_keys!=expected:failures.append('native lost/duplicated:'+mode+variant)
            checks.append({'window':mode,'variant':variant,'edges':len(g['edges']),'native_segment_identities':len(native_keys),'side_segment_identities':len(side_ids),'graph_file_sha256':sha(gp)})
        # All formal outcomes, including negative and zero aliases, must have checkable certificates.
        for rec in [r for r in records if r['window_id']==mode]:
            cert_count+=1
            if repair and rec['formal_attempt']<=18:
                g=json.loads((ROOT/'results/pre_R0_cost_fix/graphs'/f"{mode}_{rec['variant']}.json").read_text(encoding='utf-8-sig'))
            else:g=variants[rec['variant']]
            r=rec['result'];start=rec['binding']['start'];end=rec['binding']['end'];ed={e['edge_id']:e for e in g['edges']}
            canonical=hashlib.sha256(json.dumps(g,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if rec.get('graph_sha256')!=canonical:failures.append('formal graph hash:'+rec['query_id']+rec['variant'])
            expected_source=repair['final_code_sha256'] if repair and rec['formal_attempt']>18 else executed_sha
            if rec['code_sha256']!=expected_source:failures.append('formal executed source hash:'+rec['query_id']+rec['variant'])
            if rec['input_sha256']!=window['input_sha256']:failures.append('formal source lock:'+rec['query_id'])
            if rec['at']<lock['locked_at']:failures.append('formal before lock')
            if r['status']=='ENDPOINT_UNAVAILABLE':
                if start in g['nodes']and end in g['nodes']:failures.append('false unavailable')
                if r['solver_invoked']:failures.append('unavailable solver accounting')
                continue
            labels=r.get('distance_labels',{})
            if labels.get(start)!=0:failures.append('certificate startlabel')
            for e in g['edges']:
                dirs=[]
                if 1 in e['directions']:dirs.append((e['u'],e['v']))
                if -1 in e['directions']:dirs.append((e['v'],e['u']))
                for a,b in dirs:
                    if a in labels and (b not in labels or labels[b]>labels[a]+e['cost_f1']+1e-7):failures.append('certificate directed triangle/reachable closure:'+rec['query_id']+':'+e['edge_id'])
            if r['status']=='DISCONNECTED':
                if end in labels:failures.append('false disconnected')
                continue
            if end not in labels or not math.isclose(labels[end],r['cost_f1_proxy'],abs_tol=1e-7):failures.append('certificate targetcost')
            path=r['node_path'];cost=0.;f0=0.
            if not path or path[0]!=start or path[-1]!=end or len(path)!=len(r['edge_ids'])+1:failures.append('path endpoint/cardinality');continue
            for a,b,eid in zip(path,path[1:],r['edge_ids']):
                e=ed[eid]
                if not((a,b)==(e['u'],e['v'])and 1 in e['directions']or(a,b)==(e['v'],e['u'])and -1 in e['directions']):failures.append('path direction/continuity:'+eid)
                cost+=e['cost_f1'];f0+=e['cost_f0']
            if not math.isclose(cost,r['cost_f1_proxy'],abs_tol=1e-7)or not math.isclose(f0,r['cost_f0_proxy'],abs_tol=1e-7):failures.append('pathcost')
            if any(ed[k]['geometry_status']=='SCHEMATIC'for k in r['edge_ids'])and r['physical_route_length_m']is not None:failures.append('schematic physical length overclaim')
    if repair:
        if sha(ROOT/'scripts/street_side.py')!=repair['final_code_sha256']or sha(repair['parent_code'])!=repair['parent_code_sha256']:failures.append('R0 frozen parent/final source SHA')
        if len(records)!=24 or sum(x['result']['solver_invoked']for x in records)!=22:failures.append('24attempt/22solver budget accounting')
        for window in lock['windows']:
            g=json.loads((ROOT/'results/graphs'/f"{window['window_id']}_R0.json").read_text(encoding='utf-8-sig'))
            for e in g['edges']:
                if not math.isclose(e['cost_f0'],e['cost_f1'],abs_tol=1e-10):failures.append('R0 parentnativecost policy not restored')
                if e['evidence']=='SHARED_STREET_ASSUMPTION'and not e.get('epistemic_assumption'):failures.append('R0 epistemic assumption erased')
    out={'reviewer':'/root/resume_review','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS_FOR_BOUNDED_SAVED_TOPOLOGY_TRIAL'if not failures else'FAIL','windows':len(lock['windows']),'formal_outcome_certificates_checked':cert_count,'graph_edges_checked':edge_count,'native_edge_records_checked':native_count,'side_edge_records_checked':side_count,'source_crossing_interface_records_checked':cross_count,'graphs':checks,'failures':failures,'executed_source_sha256':executed_sha,'current_delivery_source_sha256':sha(ROOT/'scripts/street_side.py'),'engineering_fix':engineering,'metric_qualification':metric,'R0_repair':repair,'new_independent_solver_or_sssp_calls':0,'new_independent_BFS_calls':0,'certificate_passes':cert_count,'independent_original_source_admission_comparisons':True,'limits':['Shortest path optimality is certified within saved logical graph via directed edge inequalities and matching path, not real-world navigation optimality.','All schematic side positions lack verified width/clearance; absence of mapped conflict is not physical passage proof.','Native identity preservation does not prove there are no separately mapped physically parallel paths without a source association.','Same-side cross-road/plaza/native interface binding is not implemented here; parent full-face method remains frozen and unused by this local probe.','No independence/generalization accuracy claim, no user visual acceptance or publication approval.']}
    (ROOT/'reviews/independent_trial.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False));return not failures

def business():
    report=json.loads((ROOT/'results/business_route_axis_usage.json').read_text(encoding='utf-8-sig'));failures=[];checks=[]
    motor={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','service','living_street','road'}
    for row in report['rows']:
        p=pathlib.Path(row['old_result_path'])
        if sha(p)!=row['old_result_sha256']:failures.append('old resultSHA:'+row['request_id'])
        result=json.loads(p.read_text(encoding='utf-8-sig'));segments=result['route']['segments']
        axis=[s for s in segments if s.get('tags',{}).get('highway')in motor and s.get('source_class')=='native']
        length=sum(s['length_m']for s in axis)
        if len(axis)!=row['road_axis_segments']or not math.isclose(length,row['road_axis_length_m'],abs_tol=1e-8):failures.append('business axis count/length:'+row['request_id'])
        checks.append({'request_id':row['request_id'],'historical_result_sha256':sha(p),'road_axis_segments':len(axis),'road_axis_geometric_length_m':length,'axis_fraction':length/result['route']['length_m']})
    out={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reviewer':'/root/resume_review','status':'PASS_HISTORICAL_BUSINESS_AXIS_USAGE_RECOUNT'if not failures else'FAIL','historical_records_checked':len(checks),'checks':checks,'failures':failures,'new_solver_calls':0,'new_network_requests':0,'limits':['Historical saved route source tags and lengths recounted; native is source line provenance, not a dedicated sidewalk/public safety guarantee.','No current side graph full business solve or physical walk was performed.']}
    (ROOT/'reviews/independent_business_axis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False));return not failures

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode', choices=['old','contracts','trial','business']); args=parser.parse_args()
    raise SystemExit(0 if {'old':old_delivery,'contracts':contracts,'trial':trial,'business':business}[args.mode]() else 1)
