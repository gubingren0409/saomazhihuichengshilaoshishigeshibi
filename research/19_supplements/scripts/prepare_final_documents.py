"""Finalize factual indexes only after all declared workers have completed."""
from pathlib import Path
import json,csv,hashlib,datetime,collections,platform,subprocess,sys,os
import psutil
ROOT=Path(__file__).resolve().parents[1];Q8=ROOT/'Q8-SCALE-LATENCY-BENCHMARK-R1'
sys.path.insert(0,str(ROOT/'frozen_runtime'))
from src.planner import IMPORTED_CODE_SHA
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return[json.loads(z)for z in Path(p).read_text(encoding='utf-8').splitlines()if z.strip()]
def table(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig')))
def write(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def csvout(p,rs,fields=None):
 fields=fields or list(dict.fromkeys(k for r in rs for k in r))
 with Path(p).open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows([{k:json.dumps(v,ensure_ascii=False)if isinstance(v,(dict,list))else v for k,v in r.items()}for r in rs])
for name,n in [('manager_progress.json',44),('medium_progress.json',44),('replan_progress.json',11),('top3_phased_progress.json',11),('joint_progress.json',11)]:
 assert read(Q8/'outputs'/name)['completed_workers']==n,('BENCHMARK_NOT_FINISHED',name)
now=datetime.datetime.now().astimezone().isoformat();status=read(ROOT/'STATUS.json');summary8=read(Q8/'summary.json');assert not summary8['draft_while_workers_running']
env=read(ROOT/'audit/environment.json');env.update(finalization_metadata_at=now,node_runtime='NOT_USED',database_runtime='NOT_USED',GPU='NOT_USED',processor=platform.processor(),machine=platform.machine(),python_hash_seed=os.environ.get('PYTHONHASHSEED','UNSET_UNCONTROLLED'),field_data_used=False,old_algorithm_source_modified=False,new_experiment_adapters=['Dynamic state injection','Input-only exact crop merge/coverage union','Yen Top-3 enumeration','K2 sequential per-door cost selection','Delegating phase timing hooks'],existing_public_APP_changed=False)
write(ROOT/'environment.json',env)
for p in ROOT.glob('Q*'):
 if p.is_dir():write(p/'environment.json',env)
try:
 head=subprocess.run(['git','rev-parse','HEAD'],cwd=str(ROOT.parents[1]),capture_output=True,text=True,timeout=15);git=subprocess.run(['git','status','--porcelain','-uno'],cwd=str(ROOT.parents[1]),capture_output=True,timeout=15);git_info={'timestamp':now,'workspace_HEAD_informational_only':head.stdout.strip(),'status_command_exit':git.returncode,'tracked_status_lines':len(git.stdout.splitlines()),'status_stdout_sha256':hashlib.sha256(git.stdout).hexdigest(),'Git_write_commands_this_round':False,'not_runtime_code_binding':'Runtime is bound to frozen archive/member SHA and new driver hashes, not assumed identical to workspace HEAD'}
except Exception as e:git_info={'timestamp':now,'read_only_git_check_error':repr(e),'Git_write_commands_this_round':False}
write(ROOT/'audit/read_only_git_inspection.json',git_info)
write(ROOT/'audit/final_resources.json',{'timestamp':now,'memory':dict(psutil.virtual_memory()._asdict()),'disk':dict(psutil.disk_usage(str(ROOT))._asdict()),'benchmark_processes_should_be_stopped_before_sealing':True})
code=[]
for folder in('scripts','audit'):
 for p in sorted((ROOT/folder).glob('*')):
  if p.is_file()and p.suffix in('.py','.html'):code.append({'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size,'role':'EXECUTED_OLD_DRIVER_SNAPSHOT'if p.name.startswith(('EXECUTED_','RUN_BENCHMARK_SOURCE_EXECUTED'))else'NEW_EXPERIMENT_CODE_OR_TEMPLATE'})
csvout(ROOT/'audit/NEW_CODE_MANIFEST.csv',code)
primary=rows(Q8/'raw_results.jsonl');run_bindings=[]
for r in primary:
 if r['run_id'].startswith('Q8-A1-'):script='benchmark_worker.py';manager='audit/RUN_BENCHMARK_SOURCE_EXECUTED_A1.py'
 elif r['run_id'].startswith('Q8-MEDIUM-'):script='benchmark_medium_worker.py';manager='scripts/run_supplementary_benchmarks.py'
 elif r['run_id'].startswith('Q8-TOP3-'):script='benchmark_topk_worker.py';manager='scripts/run_topk_phased_benchmark.py'
 elif r['run_id'].startswith('Q8-REPLAN-'):script='benchmark_replan_worker.py';manager='scripts/run_replan_benchmark.py'
 else:script='benchmark_joint_worker.py';manager='scripts/run_joint_benchmark.py'
 run_bindings.append({'run_id':r['run_id'],'worker_file':'scripts/'+script,'worker_sha256':sha(ROOT/'scripts'/script),'manager_file':manager,'manager_sha256':sha(ROOT/manager),'frozen_code_sha256':IMPORTED_CODE_SHA,'input_graph_sha256':r['unweighted_graph_sha256'],'random_seed':'NOT_USED_DETERMINISTIC','python_hash_seed':'UNSET_UNCONTROLLED','hardware_file':'environment.json','hardware_sha256':sha(ROOT/'environment.json'),'cache':'NO_ROUTE_ANSWER_CACHE; preprocessing per row','scene_id':r['scene_id'],'source_timestamp':'2026-11-08T21:21:00Z'})
csvout(Q8/'run_code_bindings.csv',run_bindings)
inputs={r['member']:r for r in table(Q8/'input_manifest.csv')}
for p in sorted((ROOT/'medium_runtime').rglob('*')):
 if not p.is_file()or'runs'in p.parts or'derived_graphs'in p.parts or'__pycache__'in p.parts:continue
 inputs[p.relative_to(ROOT).as_posix()]={'source_archive_sha256':'DERIVED_FROM_TWO_VERIFIED_FROZEN_CROPS','member':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size,'role':'DERIVED_MEDIUM_INPUT_OR_BYTE_IDENTICAL_CORE_COPY'}
csvout(Q8/'input_manifest.csv',list(inputs.values()))
q2=ROOT/'Q2-LOCAL-ENTRY-AUDIT-R1';q7=ROOT/'Q7-DYNAMIC-CLOSURE-SIMULATION-R1';q6=ROOT/'Q6-LOCAL-MAP-CONSISTENCY-R1'
q2raw=rows(q2/'raw_results.jsonl');q7raw=rows(q7/'raw_results.jsonl');q7primary=rows(q7/'dynamic_route_results.jsonl');counts=[]
for unit,data,scope in [('Q2 raw records',q2raw,'Contains audit events and superseded checker records; not independent samples'),('Q7 primary state requests',[r for r in q7primary if r.get('control_variant')=='STATE_INJECTION_ADAPTER'],'2 fixed sites x 6 states x 3 repeats'),('Q7 all retained raw records',q7raw,'Includes 19 secondary original museum pressure rows and one repeated baseline'),('Q8 primary observations',primary,'Includes excluded warmups; repetitions, not independent sites')]:counts.append({'unit':unit,'n':len(data),'status_counts':dict(collections.Counter(r['status']for r in data)),'scope':scope})
csvout(ROOT/'audit/ACTUAL_EXECUTION_COUNTS.csv',counts)
all_index=[]
for p in ROOT.glob('Q*/raw_results.jsonl'):
 for i,r in enumerate(rows(p),1):all_index.append((p,r,i))
claims=[]
def claim(text,key,filename,selector,limit,run_selector=None):
 file=ROOT/filename;matches=[(p,r,i)for p,r,i in all_index if p.parent.name==key and(run_selector is None or run_selector(r))]
 claims.append({'claim':text,'experiment_id':key,'file':filename,'file_sha256':sha(file),'row_or_field_selector':selector,'run_ids':[r['run_id']for _,r,_ in matches],'raw_result_lines_1based':[i for _,_,i in matches],'scene_ids':sorted({r['scene_id']for _,r,_ in matches}),'support_scope':limit,'not_supported':'Independent field truth/current public entry/general navigation/production SLA'})
claim('三个原登记门源身份吻合且边界距离0米',q2.name,'Q2-LOCAL-ENTRY-AUDIT-R1/outputs/identity_recheck_A1.json','3 current A1 recheck rows','Original raw source IDs/tags/coordinates only',lambda r:r['run_id'].startswith('Q2-IDENTITY-RECHECK-A1-'))
claim('9个终点定义请求：6条条件路线、3个中心点NO_PATH',q2.name,'Q2-LOCAL-ENTRY-AUDIT-R1/target_definition_comparison.csv','All 9 primary target rows','Fixed controls, 3 registered targets in 2 buildings',lambda r:r['run_id'].startswith('Q2-TARGET-'))
claim('旧窗口与真博物馆不匹配',q2.name,'Q2-LOCAL-ENTRY-AUDIT-R1/window_binding_audit.csv','museum rows','Historical window source comparison, not changing old routes',lambda r:r['run_id'].startswith('Q2-IDENTITY-RECHECK-A1-'))
claim('377条恢复原生片段与754有向弧声明对齐',q6.name,'Q6-LOCAL-MAP-CONSISTENCY-R1/restored_native_edges.csv','377 source-ID/geometry rows','Declared directions and frozen source, not real-world same-level proof',lambda r:r['run_id']in('Q6-AUDIT-WALKABILITY-R2','Q6-GRASS-CURRENT-FROZEN-POLICY-377'))
claim('当前冻结草地策略重新保留377条已标步道，4个单元检查通过',q6.name,'Q6-LOCAL-MAP-CONSISTENCY-R1/outputs/grass_policy_recheck_summary.json','result.source_segments/S0_reject_S1_keep/unit_tests','Exact source segments plus separately labelled synthetic tests',lambda r:r['run_id']=='Q6-GRASS-CURRENT-FROZEN-POLICY-377')
claim('82个新增唯一面，36个在保存业务池',q6.name,'Q6-LOCAL-MAP-CONSISTENCY-R1/added_face_usage.csv','82 source rows; in_business_face_pool','Saved owner/component evidence rechecked against source, not new SCC replay',lambda r:r['run_id']=='Q6-AUDIT-PED-AREA-CONNECTIVITY-R1')
claim('353组保存几何：316有限PASS、37不确定',q6.name,'Q6-LOCAL-MAP-CONSISTENCY-R1/replay_comparison.csv','All rows; 29 missing scene, 8 aggregated decomposition unavailable','Related saved files, not 353 independent trips',lambda r:r['run_id'].startswith('Q6-AUDIT-')or r['run_id']=='Q6-AUDITOR-A3-AGGREGATE-SCHEMA-RECHECK')
claim('现场真值0条，六行仅未填写调查槽位', 'Q6-FIELD-TRUTH-COMPARISON-R1','Q6-FIELD-TRUTH-COMPARISON-R1/summary.json','actual_field_routes/actual_field_segments','No real-world metrics can be calculated',lambda r:True)
claim('动态主表36次状态请求，旧接口主负控2次FAIL',q7.name,'Q7-DYNAMIC-CLOSURE-SIMULATION-R1/dynamic_route_results.csv','primary_result_ids.json selects exact primary set','New state adapter and original plan interface distinguished',lambda r:r['run_id']in set(read(q7/'outputs/primary_result_ids.json')))
claim('博物馆步道/模拟障碍封闭后151.961米条件绕行',q7.name,'Q7-DYNAMIC-CLOSURE-SIMULATION-R1/fallback_route_comparison.csv','Museum primary S2/S3','Conditional mapped-model result, not actual public walkability',lambda r:r['run_id'].startswith('Q7-A1-NATIVE-WALKWAY-0-S2')or r['run_id'].startswith('Q7-A1-NATIVE-WALKWAY-0-S3'))
claim('正式性能分布与一秒门槛逐配置报告',Q8.name,'Q8-SCALE-LATENCY-BENCHMARK-R1/latency_distribution.csv','formal rows only; p95 AND max gate','Observed local CLI scopes, nested timers; no HTTP/city SLA',lambda r:not r.get('warmup'))
claim('两相邻裁片兼容字段并集合并，无同字段冲突覆盖',Q8.name,'Q8-SCALE-LATENCY-BENCHMARK-R1/outputs/medium_merge_audit.json','unique_objects/overlapping_ids/conflicts/coverage','Overlapping exposed inputs, not independent validation samples',lambda r:r['run_id'].startswith('Q8-MEDIUM-'))
claim('K2为新增门外逐门求路择代价适配器，exit未当入馆门',Q8.name,'Q8-SCALE-LATENCY-BENCHMARK-R1/outputs/joint_protocol.json','scope/candidates/algorithm','K2 museum outside approach only, original public APP unmodified',lambda r:r['run_id'].startswith('Q8-JOINT-K2-'))
claim('K10/K100、同合同城市级及独立现场缺输入',Q8.name,'audit/MISSING_AND_UNTESTED.csv','Blocked rows','NOT_RUN, not negative route outcomes',lambda r:False)
csvout(ROOT/'CLAIM_EVIDENCE_MAP.csv',claims)
note='''# 数据版本与纠错身份

- Q2入口身份主表和9条主请求使用米制坐标，一直保留。补充审计A0误把Source.coord经纬度当米：其3条上下文PASS和3条身份FAIL均失效，字节与源码仍在；当前使用entry_constraint_context_A1.csv及outputs/identity_recheck_A1.json。Q2_SUPERSESSION_MAP记录对应关系，不把审计器错误算入口错误。
- Q6初次审计器字段错误和8个聚合schema假FAIL保留；A3改为INCONCLUSIVE，没有改原算法/旧值。
- Q7首版博物馆封闭了residential道路轴，19行作为secondary压力测试；A1按源标签关闭footway。图书馆原19行合格，主表38行。两版干预不同，不能称方法优化。原始raw包含所有版本。
- Q8 A0暖机/正式ID碰撞，38条记录整批不用于主计时，3个独立暖机输出无法恢复。主小图A1不包含A0。Top3首版43次有效整体计时保留secondary；A2同图同算法补阶段时钟作为主版，不按快慢选留。
- K2、Top3、状态注入、合并输入是本轮新增实验适配器，不是冻结APP已部署的产品功能。旧核心、源对象坐标/标签及历史报告未修改。
'''
(ROOT/'DATA_VERSION_NOTES.md').write_text(note,encoding='utf-8')
(ROOT/'INDEPENDENCE_SCOPE.md').write_text('# 核验身份与边界\n\n本轮均由当前作者上下文执行。使用另写检查脚本、新Python进程、真实Chrome和最终ZIP干净解包交叉核验，不能因此称为独立人员或独立代理审核。没有新独立调查员、现场照片/轨迹或物理通行核验。历史独立审核材料只保留其历史身份。本轮等待GPT后续审核与用户验收。\n',encoding='utf-8')
(ROOT/'SOURCE_LICENSES.md').write_text('# 来源与传播边界\n\n所用地图是已取得的冻结OpenStreetMap源及派生几何，保留原生ID、来源快照和SHA。© OpenStreetMap contributors；源元数据声明ODbL，来源说明见各源JSON。没有新增Geoapify/高德API请求、下载、商业底图图片或付费。没有字体文件、凭据、Cookie或浏览器配置被纳入包。没有为项目选新许可证、没有公开Push。本包是本地研究审查产物，不代表独立现场通行认证。\n',encoding='utf-8')
(ROOT/'AUTHOR_REVIEW.md').write_text('# 作者审核\n\n检查输入/原生身份/CRS与单位、端点未移动、全路线分段约束、草地例外范围、动态失效边与障碍、恢复几何、主次版本及固定分母、原模型/源码保护、分阶段时钟、缺失现场/城市数据和离线图文一致。实际机器检查见audit/validation.json，最终ZIP校验见包外回执。所有纠错见DATA_VERSION_NOTES，不把作者校验冒充独立角色审核。\n',encoding='utf-8')
for p in(q2,q7):
 with(p/'README.md').open('a',encoding='utf-8')as f:f.write('\n版本修正请先读根目录 DATA_VERSION_NOTES.md。Q2只用A1补充审计；Q7只用primary_result_ids标记主表。原始raw保留失效/次要版本，不能直接按全部行汇总业务指标。\n')
for p in ROOT.glob('Q*'):
 if not p.is_dir():continue
 files=[f.relative_to(p).as_posix()for f in(p/'outputs').glob('*.json')]
 write(p/'logs/record_locations.json',{'timestamp':now,'actual_per_request_records':files,'console_stdout_fully_archived':p.name==Q8.name,'note':'Raw JSONL/individual JSON contain actual solver timing/failures. This is an index, not fabricated terminal output. Field branch has no survey runs.'})
elapsed=(datetime.datetime.now().astimezone()-datetime.datetime.fromisoformat(status['started_at'])).total_seconds()/60
status.update(status='INCONCLUSIVE',phase='RESEARCH_FINISHED_AWAITING_PACKAGE_VERIFICATION',research_finished_at=now,elapsed_minutes_so_far=elapsed,available_input_experiments_finished=True,scientific_status_by_experiment={p.name:read(p/'summary.json')['status']for p in ROOT.glob('Q*')if p.is_dir()},field_truth_used=False,large_network_tested=False,new_network_requests=0,new_API_calls=0,old_source_or_algorithm_modified=False,new_experimental_adapters_added=True,public_APP_modified=False,Git_writes=False,auto_start_next_goal=False,requires_GPT_review=True,independent_reviewer_this_round=False)
write(ROOT/'STATUS.json',status);(ROOT/'CHECKPOINT.md').write_text('研究与所有已声明工作进程已完成。下一步仅最终图文/作者验证、固定ZIP与干净解包真实求路；不得重启实验或自动下一Goal。主次版本见DATA_VERSION_NOTES。现场/大网络缺项保留。',encoding='utf-8')
(ROOT/'EXPERIMENT_BRIEF.md').write_text(f'''# 补充实验简报

本轮已完成可执行的地图内部核验、保存几何审计、模拟状态测试及性能测量；现场项和同合同城市级/10/100候选仍受阻。

- Q2：3门源身份一致；9主请求6条条件路线、3个楼内中心目标NO_PATH。
- Q6A：377/754原生恢复声明、82新增面源身份复核；353保存组316有限PASS、37不确定。不是现场真值或全历史图重建。
- Q6B：0条独立现场路线，不能计算现实准确率。
- Q7：主适配器36次结果{read(q7/'summary.json').get('primary_adapter_outcomes')}；博物馆S2/S3条件绕行151.961米，图书馆保留NO_PATH；原APP动态接口负控FAIL。
- Q8：{summary8['formal_observations']}正式观测，{summary8['warmups_excluded']}热身排除；另保留原版/错误记录。总体一秒目标不通过，逐配置p95/max见性能报告；不是生产SLA。

新增的是实验适配器，旧APP和历史算法没改。没有联网/API/训练/现场采集/Git写操作。请先打开index.html，再读RESEARCH_REVIEW.md、DATA_VERSION_NOTES.md和CLAIM_EVIDENCE_MAP.csv。当前累计约{elapsed:.1f}分钟，封包与复验时间另记。
''',encoding='utf-8')
(ROOT/'PROCESS_RECORD.md').write_text(f'''# 实际执行记录

初始化记录：{status['started_at']}；研究收尾：{now}。所有中断、修复和等待计入累计时间。

1. 完整读取用户协议，核对本机旧工程与固定ZIP；仅复制49个必要冻结源码/配置/源成员到新运行区。
2. 非主B3构图诊断超过512秒后主动停止，保留未完成记录，不算完整延迟。
3. 固定Q2三门/九请求及Q7状态试验；原APP闭门参数被忽略，记录负控FAIL。
4. Q6六归档只读审计。两次新审计器接口/字段错误保留；聚合schema假FAIL纠正为信息不足，原表保留。
5. 性能A0运行ID碰撞后整批隔离，38原始行保留；新A1区分WARMUP/FORMAL。
6. 两裁片初次严格字典相等因缺元数据受阻；仅在共同字段一致时填缺字段，并使用真实窗口并集覆盖。
7. 按顺序完成小图、Top3、合并图、删边计时；没有并发正式基准工作进程。桌面及作者轻量审计/制图负载未隔离。
8. Top3首版未细分读取/索引，保留43次为secondary；A2补同输入阶段时钟，不按速度选留。
9. 新补充Q2审计混用度/米被交叉检查抓到；保留6个失效记录并以Source.projected重算A1。原9条路线不受影响。
10. 博物馆首版干预选错原生对象类型，保留19行为压力测试；按源footway规则预锁后重跑状态组。核心算法不变，干预变化不算算法改进。
11. K2只用同馆两登记门的APPROACH_OUTSIDE，原exit身份不变；预处理缓存每请求复核源/配置/代码身份，不缓存路线答案。
12. 最终作者/Chrome/ZIP复验单列；没有新独立现场/独立代理身份，没有Git写入或下轮自动执行。

实际run_id、行号与文件由audit/RUN_INDEX.csv和CLAIM_EVIDENCE_MAP.csv提供，不能把本记录当成现场或未运行实验的证据。
''',encoding='utf-8')
print('FINAL_DOCUMENTS_PREPARED',{'elapsed_minutes':elapsed,'primary_Q8_formal':summary8['formal_observations'],'code_files':len(code),'claims':len(claims)})
