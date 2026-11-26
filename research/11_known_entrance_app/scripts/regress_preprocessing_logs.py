"""Two independent cold CLI executions test append-only preprocessing receipts.

The historical APP-07 response is comparison evidence only. Both processes run
the current original CLI and actual solver; this is repair regression, not two
additional APP acceptance samples or a new experiment panel.
"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,subprocess,sys,time,zipfile
ROOT=Path(__file__).resolve().parents[1]
CORE=('region.py','context_policy.py','free_surface.py','free_routing.py','common_constraints.py','region_routing.py')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8')as f:json.dump(value,f,ensure_ascii=False,indent=2)
def logs():return {p.relative_to(ROOT).as_posix():sha(p)for p in sorted((ROOT/'runs/preprocessing').glob('*.json'))}
def unchanged(before,after):return [k for k,v in before.items()if after.get(k)!=v]

def main(args):
    started=datetime.now().astimezone().isoformat();begin=time.perf_counter()
    artifact=ROOT/'AUDIT/preprocessing_log_fix_regression.json'
    if artifact.exists():raise FileExistsError('Preserve the earlier regression; choose a new explicit script/run before retrying')
    old_zip=args.reference_zip.resolve();archive_sha=sha(old_zip);member='runs/acceptance/APP-07.response.json'
    with zipfile.ZipFile(old_zip)as z:
        data=z.read(member);entry=next(x for x in json.loads(z.read('MANIFEST.json'))['entries']if x['path']==member)
        assert hashlib.sha256(data).hexdigest()==entry['sha256']and len(data)==entry['bytes']
        old=json.loads(data)
    assert old['request_id']=='APP-07'
    request=next(q for q in read(ROOT/'runs/acceptance/fixed_requests.json')['requests']if q['request_id']=='APP-07')
    semantic=('scene_id','door_id','start_id','purpose','method')
    assert all(request[k]==old['input'][k]for k in semantic)
    protected_initial=logs();planner_before=sha(ROOT/'src/planner.py');config_before={p.relative_to(ROOT).as_posix():sha(p)for p in sorted((ROOT/'config').glob('*.json'))}
    expected_by_task=[read(p)['code_bindings']for p in sorted((ROOT/'runs/benchmark/R2_unified').glob('*/result.json'))]
    assert len(expected_by_task)==25
    core_hashes={f'src/{n}':sha(ROOT/'src'/n)for n in CORE}
    assert all(all(j[k]==v for k,v in core_hashes.items())for j in expected_by_task)
    rows=[];responses=[]
    for n in (1,2):
        label=f'logfix_cli_{n}';request_file=ROOT/'runs/acceptance'/f'{label}.request.json';output=ROOT/'runs/acceptance'/f'{label}.response.json'
        if request_file.exists()or output.exists():raise FileExistsError('Refusing to replace '+label)
        body={**request,'request_id':f'LOGFIX-CLI-{n}','regression_role':'REPAIR_REGRESSION_EXISTING_APP07_NOT_NEW_SAMPLE'}
        write(request_file,body);before=logs();tick=time.perf_counter()
        command=[sys.executable,'-X','utf8','-B',str(ROOT/'scripts/plan.py'),'--request',str(request_file),'--output',str(output)]
        done=subprocess.run(command,cwd=ROOT,encoding='utf-8',capture_output=True,timeout=300)
        if done.returncode:raise RuntimeError(done.stderr)
        response=read(output);after=logs()
        assert not unchanged(before,after),'An existing preprocessing receipt was replaced'
        assert not unchanged(protected_initial,after),'An initially protected receipt changed'
        assert response['solver']['invoked']and response['solver']['answer_source']=='CURRENT_REQUEST_SOLVER'
        assert not response['route_answer_cache']['enabled']and not response['route_answer_cache']['hit']
        assert response['preprocessing_cache']['hit']is False,'Each fresh CLI must have a cold in-memory preprocessing cache'
        key=response['preprocessing_cache']['key'];added=sorted(set(after)-set(before))
        matching=[p for p in added if read(ROOT/p).get('cache_key')==key]
        assert len(matching)==1,'Expected one individually attributable new receipt for this cold CLI key'
        metadata=read(ROOT/matching[0]);prep_id=metadata['preprocessing_run_id']
        assert prep_id.startswith('PREP-')and matching[0].endswith(key+'-'+prep_id+'.json')
        assert metadata['cache_key']==key and metadata['route_answers_stored']is False
        comparisons={field:response[field]==old[field]for field in ('status','normalized_request','start','door','bindings','route','planning_region','graph')}
        comparisons.update(surface_sha256=response['versions']['surface_sha256']==old['versions']['surface_sha256'],
                           unweighted_graph_sha256=response['versions']['unweighted_graph_sha256']==old['versions']['unweighted_graph_sha256'])
        assert all(comparisons.values()),'A logging-only repair changed route/region/graph or endpoint semantics'
        assert response['validation']['passed']and response['validation']['whole_route_checked']
        rows.append({'request_id':response['request_id'],'run_id':response['run_id'],'solver_invocation_id':response['solver']['invocation_id'],
                     'process_mode':'NEW_CLI_PROCESS_COLD_IN_MEMORY_CACHE','status':response['status'],'cache_key':key,'new_preprocessing_log':matching[0],
                     'preprocessing_run_id':prep_id,'preprocessing_log_sha256':after[matching[0]],'other_concurrent_new_logs':[p for p in added if p not in matching],
                     'protected_before_this_process_count':len(before),'existing_log_hash_changes':[],'response_path':output.relative_to(ROOT).as_posix(),
                     'response_sha256':sha(output),'request_path':request_file.relative_to(ROOT).as_posix(),'command':['python','-X','utf8','-B','scripts/plan.py','--request',request_file.relative_to(ROOT).as_posix(),'--output',output.relative_to(ROOT).as_posix()],
                     'wall_s':time.perf_counter()-tick,'route_length_m':response['route']['length_m'],'layer_lengths_m':response['route']['layer_lengths_m'],
                     'end_residual_m':response['route']['end_residual_m'],'same_as_archived_APP07':comparisons})
        responses.append(response)
        print(label,'ACTUAL_SOLVER',response['run_id'],'PREP',prep_id,'length',response['route']['length_m'],flush=True)
    assert rows[0]['cache_key']==rows[1]['cache_key']
    assert len({r['run_id']for r in rows})==2 and len({r['solver_invocation_id']for r in rows})==2
    assert len({r['preprocessing_run_id']for r in rows})==2 and len({r['new_preprocessing_log']for r in rows})==2
    assert responses[0]['route']==responses[1]['route']and responses[0]['planning_region']==responses[1]['planning_region']
    assert planner_before==sha(ROOT/'src/planner.py')
    assert config_before=={p.relative_to(ROOT).as_posix():sha(p)for p in sorted((ROOT/'config').glob('*.json'))}
    final_logs=logs();assert not unchanged(protected_initial,final_logs)
    receipt={'role':'AUTHOR_LOGGING_CORRECTNESS_REPAIR_REGRESSION_NOT_INDEPENDENT_REPLAY_OR_NEW_APP_SAMPLE','status':'PASS',
             'started_at':started,'finished_at':datetime.now().astimezone().isoformat(),'wall_s':time.perf_counter()-begin,
             'reference':{'archive_path':old_zip.relative_to(ROOT).as_posix(),'archive_sha256':archive_sha,'member':member,'member_sha256':hashlib.sha256(data).hexdigest()},
             'planner_sha256':planner_before,'core_algorithm_hashes':core_hashes,'same_six_core_hashes_for_all_25_R2_workers':True,
             'config_hashes':config_before,'protected_preexisting_preprocessing_files':protected_initial,'protected_initial_count':len(protected_initial),
             'all_preexisting_sha_unchanged':True,'two_independent_cold_processes':True,'same_stable_cache_key':True,'two_distinct_append_only_PREP_receipts':True,
             'query_answer_cache_enabled':False,'actual_graph_search_count':2,'new_app_sample_count':0,'results':rows,
             'main25_rerun':'NOT_RERUN: benchmark workers do not import planner; the six algorithm module hashes/configs are unchanged. Logging-only path change is checked here.',
             'limits':['Author regression only; failed first archive and independent frozen-member check remain unchanged','Final corrected ZIP still requires independent clean-unpack genuine new-request verification','Same APP07 semantic query repeated; no extra generalization or field evidence']}
    write(artifact,receipt)
    note=ROOT/'AUDIT/preprocessing_log_fix_regression.md'
    if note.exists():raise FileExistsError(note)
    note.write_text('# 预处理执行记录追加写修复：作者回归\n\n'
                    '原CLI在两个独立冷进程中各执行一次原APP-07语义请求。两次都真实进入求解器、禁用路线答案缓存，产生不同run_id、solver invocation ID和PREP记录。\n\n'
                    '两次稳定预处理cache key相同；只把执行ID加入日志文件名，没有让时间或PREP-ID参与区域/图缓存键。每次执行前所有已存在的预处理文件SHA保持不变，包括第一次新产物在第二次执行后也未改变。\n\n'
                    '两次路线、分层长度、规划区域、无权图、原门与用途均与首个固定ZIP中的APP-07完全相同。六算法模块SHA与25个R2 worker记录一致，配置未变，故不重跑不导入planner的25父任务回归。\n\n'
                    '这是两次同请求的工程修复回归，不是新增APP样本。旧首封包、失败回执与独立冻结文件检查均保留；当前通过不替代修正封包的独立解包验收。\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','same_cache_key':True,'distinct_PREP_receipts':2,'existing_sha_changed':0,'actual_solver_calls':2,'new_APP_samples':0},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference-zip',type=Path,default=ROOT/'delivery/OPEN_REVIEW.zip');main(p.parse_args())
