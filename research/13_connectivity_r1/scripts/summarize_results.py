"""Read real formal receipts and response geometry; never invokes a solver."""
from pathlib import Path
import json,csv,collections,hashlib,statistics
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in row.items()})
def main():
    registry=ROOT/'results/formal_registry.jsonl';original_records=[json.loads(x)for x in registry.read_text(encoding='utf-8').splitlines()]
    replay_path=ROOT/'results/formal_replay_registry.jsonl'
    replay_records=[json.loads(x)for x in replay_path.read_text(encoding='utf-8').splitlines()]if replay_path.exists()else[]
    replacements={r['supersedes_attempt_id']:r for r in replay_records}
    records=[replacements.get(r['attempt_id'],r)for r in original_records]
    rows=[];segments=[];evidence_rows=[];pairs=collections.defaultdict(dict);cost_groups=collections.defaultdict(list)
    interface_records={};interface_usage=collections.Counter();errata=[]
    for rec in records:
        q=rec['request'];d=read(ROOT/rec['path'])if rec.get('path')else{};r=d.get('route')or{};sg=r.get('segments',[])
        c=d.get('connectivity_evidence',{});req=d.get('normalized_request',q)
        expected_parent={'EXACT_STITCH':'SOURCE_COMPLETE','CONDITIONAL_SEAMS':'EXACT_STITCH'}.get(q['connectivity_mode'])
        if expected_parent and 'parent_mode'in c and c.get('parent_mode')!=expected_parent:
            errata.append({'run_id':d.get('run_id'),'response_path':rec.get('path'),'response_sha256':rec.get('result_sha256'),
                'field':'connectivity_evidence.parent_mode','raw_reported_value':c.get('parent_mode'),'correct_conceptual_parent_mode':expected_parent,
                'authoritative_trace':'runs/preprocessing/*: cache_key and parent_cache_key; actual overlay list construction in frozen planner',
                'impact':'Inherited descriptive header only; original response not edited. Graph/parent-cache construction, costs and mode control are unchanged.'})
        row={'attempt_id':rec['attempt_id'],'role':rec['role'],'scene_id':req.get('scene_id',d.get('query',{}).get('scene_id')),
            'request_id':q.get('request_id'),'mechanism_id':q.get('mechanism_id'),'method':q.get('method'),'mode':q['connectivity_mode'],'seam_max_m':q.get('seam_max_m',2),
            'start_id':q.get('start_id',d.get('query',{}).get('start',{}).get('id')),'door_or_target_id':q.get('door_id',d.get('query',{}).get('end',{}).get('id')),
            'purpose':q.get('purpose','NETWORK_MECHANISM_NOT_ENTRANCE'),'status':d.get('status',rec['status']),'run_id':rec.get('run_id'),
            'solver_invoked':d.get('solver',{}).get('invoked',False),'length_m':r.get('length_m'),'cost_m':r.get('cost_weighted_m'),
            'native_m':sum(s['length_m']for s in sg if s['layer']=='native'),'mapped_derived_m':sum(s['length_m']for s in sg if s['layer']=='derived'),
            'conditional_seam_m':sum(s['length_m']for s in sg if s.get('geometry_kind')in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')),
            'door_front_hypothesis_m':sum(s['length_m']for s in sg if s['layer']in('inferred','unknown','assumed')and s.get('geometry_kind')not in('CONDITIONAL_GAP_LINK','CONDITIONAL_GAP_PATCH')),
            'exact_interface_m':sum(s['length_m']for s in sg if s.get('geometry_kind')=='SOURCE_SUPPORTED_INTERFACE'),
            'whole_validation_passed':d.get('validation',{}).get('passed'),'max_continuity_gap_m':r.get('max_continuity_gap_m'),
            'interface_ids_used':r.get('interface_ids_used',[]),'failure':d.get('failure'),'elapsed_s':d.get('elapsed_s'),
            'preprocessing_hit':d.get('preprocessing_cache',{}).get('hit'),'preprocessing_s':d.get('preprocessing_cache',{}).get('load_or_prepare_s'),
            'unweighted_graph_sha256':d.get('versions',{}).get('unweighted_graph_sha256',d.get('graph',{}).get('unweighted_sha256')),
            'response_path':rec.get('path'),'response_sha256':rec.get('result_sha256')}
        rows.append(row)
        namespace_door=q.get('door_id')
        for interface in r.get('interface_ids_used',[]):interface_usage[(row['scene_id'],namespace_door,row['mode'],row['seam_max_m'],interface)]+=1
        for kind in ('interfaces','seams','face_relations'):
            for item in c.get(kind,[]):
                signature=hashlib.sha256(json.dumps({'scene':row['scene_id'],'namespace_door':namespace_door,'mode':row['mode'],'threshold':row['seam_max_m'],'kind':kind,'item':item},sort_keys=True).encode()).hexdigest()
                if signature not in interface_records:interface_records[signature]={'scene_id':row['scene_id'],'namespace_door_id':namespace_door,'mode':row['mode'],'seam_max_m':row['seam_max_m'],'record_kind':kind,**item,'response_path':row['response_path'],'response_sha256':row['response_sha256'],
                    'used_in_bound_response':item.get('id')in r.get('interface_ids_used',[])}
        recorded={x.get('id')for x in c.get('interfaces',[])}
        for s in sg:
            if s.get('geometry_kind')!='SOURCE_SUPPORTED_INTERFACE'or s.get('interface_id')in recorded:continue
            # Query attachment is a derived edge, not a query-independent portal.
            item={'id':s['interface_id'],'kind':'SOURCE_SUPPORTED_INTERFACE','relation':'ORIGINAL_BOUNDARY_QUERY_VISIBILITY_ATTACHMENT',
                'geometry':{'type':'LineString','coordinates':s['xy']},'source_area_ids':s.get('source_area_ids',[s.get('source_area_id')]),
                'accepted':True,'entered_graph':True,'generation_scope':'QUERY_ENDPOINT_ATTACHMENT_NOT_SOURCE_INDEPENDENT_INTERFACE',
                'reason':'Exact locked raw boundary node; complete segment covered by declared source Ω and joint domain; see route and bindings.'}
            signature=hashlib.sha256(json.dumps({'scene':row['scene_id'],'namespace_door':namespace_door,'mode':row['mode'],'kind':'query_attachment','item':item},sort_keys=True).encode()).hexdigest()
            interface_records[signature]={'scene_id':row['scene_id'],'namespace_door_id':namespace_door,'mode':row['mode'],'seam_max_m':row['seam_max_m'],'record_kind':'interfaces',**item,'response_path':row['response_path'],'response_sha256':row['response_sha256'],'used_in_bound_response':True}
        for i,s in enumerate(sg):segments.append({'attempt_id':rec['attempt_id'],'run_id':rec.get('run_id'),'index':i,**s})
        if rec['role']in('BASELINE_POSITIVE','SOURCE_INTERFACE_MECHANISM','GAP_COST_PAIR','HISTORICAL_LONG_QUERY_NOT_SCREENSHOT_BOUND'):
            key=(rec['role'],row['scene_id'],row['start_id'],row['door_or_target_id'],row['purpose'],row['method'])
            pairs[key][row['mode']]=row
        if row['unweighted_graph_sha256']:cost_groups[(row['scene_id'],row['start_id'],row['door_or_target_id'],row['purpose'],row['mode'],row['seam_max_m'])].append(row)
    write_csv(ROOT/'results/sample_results.csv',rows);write_csv(ROOT/'results/segment_evidence.csv',segments)
    write_csv(ROOT/'results/evidence_field_errata.csv',errata)
    comparison=[];modes=['FROZEN_FULL_FACE','SOURCE_COMPLETE','EXACT_STITCH','CONDITIONAL_SEAMS']
    for key,values in pairs.items():
        r={'role':key[0],'scene_id':key[1],'start_id':key[2],'target_id':key[3],'purpose':key[4],'method':key[5]}
        for mode in modes:
            d=values.get(mode,{})
            for k in ['status','length_m','cost_m','conditional_seam_m','exact_interface_m']:r[mode+'_'+k]=d.get(k)
        for a,b in zip(modes,modes[1:]):
            x=values.get(a,{});y=values.get(b,{})
            if x.get('cost_m')is not None and y.get('cost_m')is not None:r[a+'_to_'+b+'_cost_delta_m']=y['cost_m']-x['cost_m']
        comparison.append(r)
    write_csv(ROOT/'results/paired_comparison.csv',comparison)
    interfaces=list(interface_records.values())
    source_indexes={};source_manifest={s['scene_id']:s for s in read(ROOT/'data/scene_manifest.json')['scenes']}
    for item in interfaces:
        item['actual_route_usage_count']=interface_usage.get((item['scene_id'],item['namespace_door_id'],item['mode'],item['seam_max_m'],item.get('id')),0)
        item['usage_count_scope']='ALL_PRIMARY_QUERIES_SAME_SCENE_DOOR_NAMESPACE_MODE_AND_THRESHOLD; F0/F1 SHARE GRAPH'
        scene=item['scene_id']
        if scene not in source_indexes:
            raw=read(ROOT/source_manifest[scene]['source_path'])
            source_indexes[scene]={f"{r['type']}/{r['id']}":{'id':f"{r['type']}/{r['id']}",'version':r.get('version'),'tags':r.get('tags',{}),'source_object_role':'RAW_OSM_OBJECT'}for r in raw['elements']}
        ids=set(item.get('source_area_ids',[])+item.get('source_ids',[]))
        item['source_objects']=[source_indexes[scene].get(s,{'id':s,'version':None,'source_object_role':'DERIVED_OR_UNRESOLVED_PARENT_ID_NOT_RAW_OSM_OBJECT'})for s in sorted(ids)]
        item['source_clip_sha256']=source_manifest[scene]['source_sha256']
    write_csv(ROOT/'results/interface_evidence.csv',interfaces)
    # RFC7946 geographic export: calculations remain metric; export only transforms.
    from pyproj import Transformer
    from shapely.geometry import shape,mapping
    from shapely.ops import transform
    project=Transformer.from_crs(32651,4326,always_xy=True).transform
    for name,kind in [('conditional_seams','seams'),('exact_interfaces','interfaces')]:
        features=[]
        for item in interfaces:
            if item['record_kind']!=kind or not item.get('geometry'):continue
            properties={k:v for k,v in item.items()if k!='geometry'}
            properties['calculation_crs']='EPSG:32651';properties['public_passage_verified']=False
            features.append({'type':'Feature','geometry':mapping(transform(project,shape(item['geometry']))),'properties':properties})
        (ROOT/'results'/f'{name}.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    graphpairs=[]
    for key,group in cost_groups.items():
        methods={r['method']for r in group}
        if methods>={'F0','F1'}:graphpairs.append({'group':key,'same_unweighted_graph':len({r['unweighted_graph_sha256']for r in group})==1,'hashes':sorted({r['unweighted_graph_sha256']for r in group})})
    totals={}
    for role in sorted({r['role']for r in rows}):
        totals[role]={mode:{'attempted':len(v:= [r for r in rows if r['role']==role and r['mode']==mode]),'routed':sum(str(r['status']).startswith('ROUTED')for r in v),'solver_invocations':sum(r['solver_invoked']for r in v),'statuses':dict(collections.Counter(r['status']for r in v))}for mode in modes}
    interrupted=[read(p)for p in sorted((ROOT/'results').glob('interrupted_formal_*.json'))]
    summary={'formal_attempts':len(original_records)+len(replay_records)+len(interrupted),'formal_completed':len(rows),'formal_replays':len(replay_records),'formal_interrupted':interrupted,'formal_cap':128,
        'solver_invocations_primary':sum(r['solver_invoked']for r in rows),'solver_invocations':sum(r.get('solver_invoked',False)for r in original_records+replay_records),'engineering_exceptions':sum(r['status']=='ENGINEERING_EXCEPTION'for r in rows),
        'by_role_and_mode':totals,'F0_F1_graph_pairs':graphpairs,'all_paired_graphs_equal':all(r['same_unweighted_graph']for r in graphpairs),
        'response_geometry_only':'No new route was computed by this aggregation. No route accuracy/IoU claimed without independent reference.',
        'registry_sha256':hashlib.sha256(registry.read_bytes()).hexdigest(),
        'replay_registry_sha256':hashlib.sha256(replay_path.read_bytes()).hexdigest()if replay_path.exists()else None}
    (ROOT/'results/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:summary[k]for k in('formal_attempts','solver_invocations','engineering_exceptions','all_paired_graphs_equal')},ensure_ascii=False))
if __name__=='__main__':main()
