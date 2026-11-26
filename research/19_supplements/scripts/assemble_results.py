"""Summarize actual measurements, build offline review, never fill missing experiments."""
from pathlib import Path
import json,csv,collections,datetime,hashlib,sys,shutil,html
import numpy as np
import markdown
ROOT=Path(__file__).resolve().parents[1]
IDS={'q2':'Q2-LOCAL-ENTRY-AUDIT-R1','q6':'Q6-LOCAL-MAP-CONSISTENCY-R1','field':'Q6-FIELD-TRUTH-COMPARISON-R1','q7':'Q7-DYNAMIC-CLOSURE-SIMULATION-R1','q8':'Q8-SCALE-LATENCY-BENCHMARK-R1'}
D={k:ROOT/v for k,v in IDS.items()};draft='--draft'in sys.argv
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def table(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig')))if Path(p).exists()else[]
def raw(p):return[json.loads(s)for s in Path(p).read_text(encoding='utf-8').splitlines()if s.strip()]
def csvout(p,rows,fields=None):
 fields=fields or list(dict.fromkeys(k for r in rows for k in r));Path(p).parent.mkdir(parents=True,exist_ok=True)
 with Path(p).open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows([{k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in r.items()}for r in rows])
def mdtable(rows,keys):
 clean=lambda x:str(x).replace('|','/').replace('\n',' ')
 return'| '+' | '.join(keys)+' |\n| '+' | '.join('---'for k in keys)+' |\n'+'\n'.join('| '+' | '.join(clean(r.get(k,''))for k in keys)+' |'for r in rows)
def rel(p):return Path(p).relative_to(ROOT).as_posix()
def stats(values):
 a=np.array(values,dtype=float);return{'n':len(a),**{f'p{k}_ms':float(np.percentile(a,k))for k in(50,90,95,99)},'min_ms':float(a.min()),'max_ms':float(a.max()),'mean_ms':float(a.mean()),'std_population_ms':float(a.std())}

# Per-worker process time is the cold end-to-end clock, never the hot batch time.
q8=raw(D['q8']/'raw_results.jsonl');formal=[r for r in q8 if not r.get('warmup')]
manager=[]
top3_matrix='top3_phased_benchmark_matrix.csv'if(D['q8']/'top3_phased_benchmark_matrix.csv').exists()else'top3_benchmark_matrix.csv'
for name in('benchmark_matrix.csv',top3_matrix,'medium_benchmark_matrix.csv','replan_benchmark_matrix.csv','joint_benchmark_matrix.csv'):
 for row in table(D['q8']/name):
  row.setdefault('query_type','SINGLE_SHORTEST_PATH');row.setdefault('scale','SMALL_FROZEN_LIBRARY_ONLY');manager.append(row)
for row in formal:
 if row.get('temperature')=='COLD_PROCESS':
  candidates=[m for m in manager if all(str(m.get(k))==str(row.get(k))for k in('query_type','scale','mode','method','temperature','repeat'))]
  row['cold_process_end_to_end_ms']=float(candidates[0]['manager_wall_ms'])if len(candidates)==1 else None
  row['cold_manager_binding_matches']=len(candidates)
 row['building_id']=row.get('building_id')or('way/293434188'if row['scene_id']=='sh-library'else'')
 row['random_seed']='NOT_USED_DETERMINISTIC_ALGORITHM';row['python_hash_seed']='UNSET_UNCONTROLLED';row['code_binding']='audit/FROZEN_RUNTIME_MANIFEST.json + audit/NEW_CODE_MANIFEST.csv';row['hardware_binding']='environment.json';row['API_HTTP_UI_included']=False
csvout(D['q8']/'observations_normalized.csv',formal)
groups=collections.defaultdict(list)
for row in formal:groups[tuple(row.get(k)for k in('scale','query_type','mode','method','temperature'))].append(row)
distributions=[];quality=[]
for key,rows in groups.items():
 identity=dict(zip(('scale','query_type','mode','method','temperature'),key));counts=collections.Counter(r['status']for r in rows)
 for metric in('read_ms','graph_preprocessing_ms','index_ms','binding_and_graph_compose_ms','solver_ms','topk_ms','candidate_ranking_ms','validation_ms','end_to_end_worker_ms','cold_process_end_to_end_ms'):
  values=[r[metric]for r in rows if r.get(metric)is not None]
  if not values:continue
  s=stats(values);distributions.append({**identity,'timing_scope':metric,**s,'p95_and_max_under_1000ms':s['p95_ms']<=1000 and s['max_ms']<=1000,'observed_outcomes':dict(counts),'measurement_note':'Nested phase timers, not additive; CLI core, not HTTP. Cold process clock includes imports and file output; OS disk cache uncontrolled.'})
 quality.append({**identity,'formal_n':len(rows),'PASS_count':counts['PASS'],'NO_PATH_count':counts['NO_PATH'],'RUNTIME_ERROR_count':counts['RUNTIME_ERROR'],'FAIL_count':counts['FAIL'],'success_ratio':counts['PASS']/len(rows),'no_path_ratio':counts['NO_PATH']/len(rows),'runtime_error_ratio':counts['RUNTIME_ERROR']/len(rows),'route_lengths_m':sorted(set(r['route_length_m']for r in rows if r.get('route_length_m')is not None)),'graph_nodes':sorted(set(r['graph_nodes']for r in rows)),'graph_arcs':sorted(set(r['graph_arcs']for r in rows)),'input_graph_sha256':sorted(set(r['unweighted_graph_sha256']for r in rows)),'independent_sites':1,'independent_requests':1})
csvout(D['q8']/'latency_distribution.csv',distributions)
csvout(D['q8']/'memory_usage.csv',[{k:r.get(k)for k in('run_id','scale','query_type','mode','method','temperature','sampled_peak_rss_bytes')}for r in formal])
csvout(D['q8']/'route_quality_comparison.csv',quality)
worker_outcomes=[]
for m in manager:
 children=[r for r in q8 if all(str(r.get(k))==str(m.get(k))for k in('scale','query_type','mode','method','temperature'))and(m['temperature']=='HOT_PROCESS'or str(r.get('repeat'))==str(m.get('repeat')))]
 worker_outcomes.append({**m,'status_scope':'WORKER_PROCESS_EXIT_ONLY_NOT_ROUTE_SUCCESS','observed_child_statuses':dict(collections.Counter(r['status']for r in children)),'observed_child_rows_including_warmups':len(children)})
csvout(D['q8']/'worker_process_outcomes.csv',worker_outcomes)
csvout(D['q8']/'failure_and_timeout.csv',[r for r in formal if r['status']not in('PASS',)]+[m for m in manager if m['status']=='RUNTIME_ERROR'],['run_id','query_type','scale','mode','method','temperature','repeat','status','failure_reason','runtime_ms','manager_wall_ms','output_file','log'])

missing=[
 {'experiment_id':IDS['field'],'status':'BLOCKED_BY_MISSING_INPUT','item':'独立现场真值','result':'NOT_RUN','reason':'无独立调查人员提供的带时间戳照片/轨迹/逐段标签；6行仅待采集槽位；第3建筑及6个合格目标也未齐备'},
 {'experiment_id':IDS['q7'],'status':'INCONCLUSIVE','item':'两个场景均具独立接近方向和合法备用路线的前置资格','result':'NOT_CONFIRMED','reason':'已实跑36次状态请求，但未事先确认两场景均有合法备用通道；选定断边可能是瓶颈；没有成功替代路线证据'},
 {'experiment_id':IDS['q8'],'status':'BLOCKED_BY_MISSING_INPUT','item':'10 / 100 个合格登记候选','result':'NOT_RUN','reason':'6个冻结裁片只提供2栋目标建筑、3个登记门（其中1个exit）；不得复制或生成入口补足数量'},
 {'experiment_id':IDS['q8'],'status':'BLOCKED_BY_MISSING_INPUT','item':'多入口联合选择性能','result':'NOT_RUN','reason':'原接口一次只指定一个门，未提供联合候选选择实现及同用途候选合同；本轮没有用单门循环伪装联合算法'},
 {'experiment_id':IDS['q8'],'status':'BLOCKED_BY_MISSING_INPUT','item':'城市级当前合同大路网','result':'LARGE_NETWORK_NOT_AVAILABLE_IN_CURRENT_CONTRACT','reason':'缺可直接接受当前同域门身份、障碍、层级、步行面和覆盖合同的城市级输入；历史NYC数据没有被冒充当前APP的大规模实测'},
 {'experiment_id':IDS['q8'],'status':'NOT_APPLICABLE','item':'原APP原生Top-3及EDGE_BAND HTTP接口','result':'NOT_IMPLEMENTED_IN_FROZEN_PUBLIC_INTERFACE','reason':'本轮测的是明确新增的实验适配器，未修改旧APP并宣称已有该产品能力'},
 {'experiment_id':IDS['q6'],'status':'INCONCLUSIVE','item':'历史受控遮蔽图的全量重建及有向SCC独立重算','result':'NOT_RUN','reason':'读取和核对保存的准入/owner/分量证据，重新计算路线几何；未完整重跑各旧算法及遮蔽合同'},
 {'experiment_id':IDS['field'],'status':'NOT_APPLICABLE','item':'实时状态感知、现场门禁、人流及GPS','result':'NOT_TESTED','reason':'动态状态由实验注入，不是传感器或现场观测'},
]
joint_tested=any(r.get('query_type','').startswith('MULTI_ENTRANCE_K2')for r in formal)
if joint_tested:
 missing=[m for m in missing if m['item']!='多入口联合选择性能']
 missing.append({'experiment_id':IDS['q8'],'status':'NOT_APPLICABLE','item':'原APP多入口联合接口','result':'NOT_IMPLEMENTED_IN_FROZEN_PUBLIC_INTERFACE','reason':'新增适配器已测博物馆2个门的门外逐门求路后按代价选留；不是原APP能力，不是可扩展全局联合最短路算法，未测K10/100'})
if(D['q7']/'outputs/primary_result_ids.json').exists():
 for m in missing:
  if m['item']=='两个场景均具独立接近方向和合法备用路线的前置资格':m['reason']='A1博物馆S2/S3各3次有条件绕行，图书馆该断边仍NO_PATH；未确认两个场景均有独立实际备用通道，未用Top3相邻格网走法冒充物理独立通道'
csvout(ROOT/'audit/MISSING_AND_UNTESTED.csv',missing)
inventory=read(ROOT/'frozen_runtime/data/scene_manifest.json');csvout(D['q8']/'capacity_inventory.csv',[{'scene_id':r['scene_id'],'building_id':r['building_native_id'],'registered_door_count':r['registered_entrance_count'],'source_sha256':r['source_sha256'],'bounds_wsen':r['full_source_clip_bounds'],'independence_note':'Overlapping source clips are not independent buildings or validation groups'}for r in inventory['scenes']])
performance_sla=[r for r in distributions if(r['temperature']=='HOT_PROCESS'and r['timing_scope']in('solver_ms','topk_ms','end_to_end_worker_ms'))or(r['temperature']=='COLD_PROCESS'and r['timing_scope']=='cold_process_end_to_end_ms')]
scale_labels={'SMALL_FROZEN_LIBRARY_ONLY':'图书馆小裁片','SMALL_FROZEN_MUSEUM_TWO_DOORS':'博物馆双门','MEDIUM_TWO_OVERLAPPING_FROZEN_CROPS':'两裁片合并'}
query_labels={'SINGLE_SHORTEST_PATH':'单路径','TOP3_EXPERIMENTAL_ADAPTER':'Top3新适配器','REPLAN_AFTER_FIXED_NATIVE_EDGE_REMOVAL':'删边重求路','MULTI_ENTRANCE_K2_SEQUENTIAL_COST_SELECTION_ADAPTER':'双门新适配器'}
timing_labels={'solver_ms':'求解阶段','topk_ms':'Top3生成','end_to_end_worker_ms':'核心请求','cold_process_end_to_end_ms':'新进程端到端'}
perfrows=[{'规模':scale_labels.get(r['scale'],r['scale']),'任务':query_labels.get(r['query_type'],r['query_type']),'模式':('完整面'if r['mode']=='FULL_FACE'else'边缘带')+' / '+r['method'],'计时':('热 · 'if r['temperature']=='HOT_PROCESS'else'冷 · ')+timing_labels.get(r['timing_scope'],r['timing_scope']),'n':r['n'],'p95 ms':round(r['p95_ms'],2),'最慢 ms':round(r['max_ms'],2),'一秒门槛':'满足'if r['p95_and_max_under_1000ms']else'不满足','返回结果':' / '.join(k+'×'+str(v)for k,v in r['observed_outcomes'].items())}for r in performance_sla]
summary8={'status':'FAIL'if any(not r['p95_and_max_under_1000ms']for r in performance_sla if r['temperature']=='COLD_PROCESS')else'INCONCLUSIVE','raw_observations':len(q8),'warmups_excluded':sum(bool(r.get('warmup'))for r in q8),'formal_observations':len(formal),'formal_outcomes':dict(collections.Counter(r['status']for r in formal)),'configurations':quality,'large_tested':False,'joint_candidate_selector_tested':joint_tested,'joint_selector_is_new_experiment_adapter_not_original_APP':joint_tested,'candidate_counts_tested':sorted({r['candidate_count']for r in formal}),'field_validation':False,'independent_latency_test_sites':len({r['scene_id']for r in formal}),'primary_A0_excluded':True,'current_API_changed':False,'draft_while_workers_running':draft}
write(D['q8']/'summary.json',summary8)
q2summary=read(D['q2']/'summary.json');q6summary=read(D['q6']/'summary.json');q7summary=read(D['q7']/'summary.json')
q2targets=table(D['q2']/'target_definition_comparison.csv');identities=table(D['q2']/'entry_identity_audit.csv');q7rows=raw(D['q7']/'raw_results.jsonl');replay=table(D['q6']/'replay_comparison.csv')
if(D['q7']/'outputs/primary_result_ids.json').exists():q7primary=set(read(D['q7']/'outputs/primary_result_ids.json'));q7rows=[r for r in q7rows if r['run_id']in q7primary]
unit=read(D['q6']/'outputs/grass_policy_recheck_summary.json')if(D['q6']/'outputs/grass_policy_recheck_summary.json').exists()else{}
targettable=[{'场景':r['scene_id']+' / '+r['entrance_id'],'目标':r['target_definition'],'状态':r['status'],'长度 m':round(float(r['route_length_m']),3)if r['route_length_m']else'—','离登记门 m':round(float(r['endpoint_to_registered_door_m']),3),'run_id':r['run_id']}for r in q2targets]
q7tab=[]
for scene in ('sh-huangpu-01','sh-library'):
 for state in ('S0','S1','S2','S3','S4','S5'):
  rows=[r for r in q7rows if r.get('scene_id')==scene and r.get('state')==state and r.get('control_variant')=='STATE_INJECTION_ADAPTER'];q7tab.append({'场景':scene,'状态':state,'重复':len(rows),'结果':dict(collections.Counter(r['status']for r in rows)),'违规数':sum(r.get('forbidden_object_used',False)for r in rows),'run_id':rows[0]['run_id']if rows else''})
elapsed=(datetime.datetime.now().astimezone()-datetime.datetime.fromisoformat(read(ROOT/'STATUS.json')['started_at'])).total_seconds()/60
report=f'''# Q2 / Q6 / Q7 / Q8 统一研究审查报告

生成：{datetime.datetime.now().astimezone().isoformat()}。{'**运行中草稿：性能基准尚未全部完成。**'if draft else'**本轮已有可执行工作收尾；缺失输入和未完成资格单列，没有补造结果。**'}

## 1. 实验范围和未完成项目

本轮按用户附件执行5个独立ID，全部写入新目录。Q2是地图内部核验及新求路；Q6A是源身份、保存轨迹复算及当前冻结草地策略复核；Q6B因缺现场资料受阻；Q7包含新状态注入适配器和未修改APP的负控；Q8测小裁片、相邻两裁片合并、Top-3和指定断边重求路。不是现场导航验收，也不是新的盲测。

{mdtable([{'项目':k,'状态':v['status']}for k,v in [('Q2',q2summary),('Q6A',q6summary),('Q6B',read(D['field']/'summary.json')),('Q7 原接口',q7summary),('Q8 总体一秒要求',summary8)]],['项目','状态'])}

缺项及精确原因：[机器可读清单](audit/MISSING_AND_UNTESTED.csv)。不得将同一建筑多个门、重复计算或重叠裁片计为独立建筑。全轮仅2栋建筑提供合格登记门，Q2是3个门，Q8独立计时地点只有图书馆1处。

## 2. 输入数据和代码版本

主运行代码/6裁片来自固定 Connectivity-R1 ZIP，SHA256 `d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed`；49个冻结源码/配置/输入的逐文件SHA见 [冻结清单](audit/FROZEN_RUNTIME_MANIFEST.json)。版本身份采用内容哈希，不新建commit、不处理历史暂存。Q6另核验6个固定阶段归档SHA，见 [来源表]({IDS['q6']}/provenance.csv)。

本轮新增状态注入、CLI计时、Yen Top-3与合并输入适配器代码单列，见 scripts/ 和 audit/NEW_CODE_MANIFEST.csv；**不是“完全没有新增算法代码”**。旧源码、旧结果、入口标签及原坐标不改。原生线类包含原合同允许的道路轴，不能统一叫“已知人行道”。工作CRS为 EPSG:32651 米。Python/依赖、RAM、CPU和时钟见 environment.json。随机算法未使用，PYTHONHASHSEED未控制；图哈希与路线输出实际核对。没有下载新地图或调用API，没有训练。

初次B3非主分支构图在512.49秒被本轮主动中止，只能作为未完成诊断下界，不是完整求路耗时。随后按公开默认 FROZEN_FULL_FACE/B0 预先记录主协议修订。计时执行时已观察Q2性能，属于公开工程诊断，不是盲评。

## 3. Q2 入口坐标、门身份与接入结果

南门 node/6897141353、北出口 node/6897145227 均属于 way/161090899；图书馆门 node/11300000483 属于 way/293434188。三个点均在各自原生外环上，坐标和标签吻合，边界距离均0米。**main/exit不代表当前开放；北门只请求到门外，不能用于入馆。**

{mdtable(targettable,['场景','目标','状态','长度 m','离登记门 m','run_id'])}

相同起点/源/成本下，3个中心点均未能合法绑定到楼内目标而 NO_PATH；3个登记门请求都形成条件路线。原生接近点不是另一扇门，也不是同一门的替代真值；博物馆南门对照的原生点在楼旁另一位置，430米路线不能写成“最佳入口更差”。图书馆接近点与门重合，该次对照未观察到额外收益，不能外推“无需接入补全”。

证据：[身份表]({IDS['q2']}/entry_identity_audit.csv)、[目标对照]({IDS['q2']}/target_definition_comparison.csv)、[接入价值]({IDS['q2']}/entry_access_value.csv)。逐条原始响应 outputs/Q2-TARGET-*.json，raw_results.jsonl 中有同名run_id。距离对象分别是道路轴、原始步道和当前准入面Omega，不能当路缘/全部人行空间。补充的全源障碍/关系上下文见 entry_constraint_context.csv；原nearby_restrictions列只是way线筛查，不能据空列表称附近无障碍。

旧博物馆路侧窗口确有场景绑定错误：其范围未覆盖真正博物馆；本轮保留旧证据，并以正确目标建筑/登记门和源数据重新核验，不改旧路线。见 window_binding_audit.csv 和 outputs/window_definition_sources.json。

## 4. Q6A OSM内部一致性结果

核对6裁片306,927条源记录与保存的适配器清单，ID/标签匹配差异0。这个数量包含重复源对象，不是独立对象数。377条恢复原生片段的节点、源ID、标签、版本及长度一致，754是有向弧声明数；**不是754条独立步道，更不是现实同层已核验。** 本轮实际用当前冻结S0/S1策略再次评估377条，{unit.get('result',{}).get('S0_reject_S1_keep','尚未完成')}条表现为旧策略拒绝、修正策略保留；4项合成检查另列，不混作现场证据。未标通行线/私有步道/无桥水体反例仍拒绝。原生步道例外只适用于明确线对象，没有将草地面全部开放。

82个新增唯一登记面源身份均对齐，36个在保存的业务面池中；47个从未出现在保存的业务查询命名空间，19个涉及“旧路线严格更便宜”，16个涉及“其他有向分量”（各面原因集合详见 added_face_usage.csv）。这些是**重核原ID后的保存分量/owner/替代证据**，不是本轮新建所有历史SCC。新增面与路线几何相交也不等于路线使用了该面；池外与未采用不是漏读。

353组保存路线、13,924段重新计算几何。最终316组 PASS、37组 INCONCLUSIVE：29组不能可靠关联原始场景，8组聚合几何不能拆回原生/派生构成。分组数含同一请求/版本相关保存结果，不能当353条独立业务案例。已知场景的本轮二维源接触检查没有保留明确冲突标志，但这**不是全层级、全历史准入例外或现实可走证明**。严格1e-8数值差异与原1e-6约束容差同时保留，没有改旧值。

新审计器曾将8个聚合文件误判为缺layer的FAIL；只修了本轮解析口径，原错误表保留在 attempts/A2_AGGREGATE_SCHEMA_FALSE_FLAGS，改为信息不足的INCONCLUSIVE，未改旧算法。另两次审计器字段接口错误保留 RUNTIME_ERROR。104个旧响应的SHA绑定均匹配。

证据：[恢复表]({IDS['q6']}/restored_native_edges.csv)、[377条新策略复核]({IDS['q6']}/grass_policy_recheck.csv)、[82面]({IDS['q6']}/added_face_usage.csv)、[保存几何复算]({IDS['q6']}/replay_comparison.csv)、[约束审计]({IDS['q6']}/route_constraint_audit.csv)。各行包含run_id、stage、source_file。run `Q6-GRASS-CURRENT-FROZEN-POLICY-377` 与 `Q6-AUDITOR-A3-AGGREGATE-SCHEMA-RECHECK` 对应本轮检查。

## 5. Q6B 现场真值对照

**BLOCKED_BY_MISSING_INPUT。真实调查0栋、0条路线、0个逐段现场标签。** 六行route_level_comparison只是计划槽位，不能当实走分母。没有独立调查人员、带时戳照片/轨迹、同层/门禁状态，也没有第三栋建筑及足够目标。现实可走比例、假阳性、漏报、距离误差和假设段命中率均不可计算，表内留空，不填0。

证据：[现场协议]({IDS['field']}/field_protocol.md)、route_level_comparison.csv 和 raw_results.jsonl 中6条 BLOCKED记录。没有用地图/AI审核补造真值。

## 6. Q7 动态封闭与障碍模拟

2个场景 × 6状态 × 3次 = 36次新状态适配器请求；不是36个独立场景。封闭状态每次从S0单独构图，不累计；禁用答案缓存。S0/S5共12次PASS，S1–S4共24次NO_PATH；适配器违规使用被禁对象0次，S5六次都恢复S0几何。首次状态图构建/热重复与**进程冷启动**不同，Q7未冒称测了完整冷进程，Q8另测。

{mdtable(q7tab,['场景','状态','重复','结果','违规数','run_id'])}

**原APP功能检查FAIL**：2次未修改公开plan接口负控，传入closed_doors后仍返回该门路线，因为旧接口不处理动态状态参数。证据run `Q7-NATIVE-API-CONTROL-0`、`Q7-NATIVE-API-CONTROL-2`；原始响应保留。这说明当前产品缺动态状态入口，不能用新增实验包装器的0违规写成“现有APP动态容错已通过”。

前置“两个场景都有合法备用接近方向”未完整建立。选定边在这些请求下无法绕过，**没有证明成功备用路线恢复能力**，也没有证明现实无其他路。Top-3图书馆路径是节点序列不同的候选，仍共享主要走廊，不能补充为三个独立现场通道。没有自动感知关门、施工、人流/GPS或门禁。

证据：[逐次状态结果]({IDS['q7']}/dynamic_route_results.csv)、closure_edge_changes.csv、forbidden_object_usage.csv、fallback_route_comparison.csv、outputs/Q7-*.json。删除对象为保存edge_id的有向边，障碍是2米或更小的合成方框，不是新增现场障碍事实。

## 7. Q8 性能结果

当前计时结果：{len(q8)}次观测，其中{sum(bool(r.get('warmup'))for r in q8)}次warm-up排除，{len(formal)}次正式观测。正式观测的重复是性能重复，不是新的地理样本。小规模：图书馆单裁片；中规模：与武康相邻裁片按原生ID兼容字段合并，64,368个唯一源对象、36,107个共享ID，缺失元数据补齐而非任意版本覆盖，真实覆盖用两个采集窗口的几何并集，不把包围盒空角伪装为采集覆盖。合并后图仅有适度增大，不能冒称接近城市级规模。

每配置3次热身后30次热进程请求、10次新进程冷请求；冷构建较慢，采用协议允许的至少10次。F0/F1同图只改假设段代价。Top-3是本轮新增Yen实验适配器，只测小图FULL_FACE/F1，三个节点序列不同，不保证三个独立通道。指定断边后的重求路若NO_PATH，照样保留耗时，不能把它当成功导航。

{mdtable(perfrows,['规模','任务','模式','计时','n','p95 ms','最慢 ms','一秒门槛'])}

**不能宣称系统总体一秒返回。** 仅某配置某计时口径的p95和最慢值都≤1000ms才能称该配置达标；冷进程端到端包含Python启动/导入/读取/构图/绑定/求解/检查/写出/退出；热core时间不含之后的序列化落盘，不含HTTP/页面。求解器阶段不能代替完整请求时间。阶段计时相互包含，不能相加；读/索引计时钩子仅代理原操作，测量开销未扣。10ms RSS采样是观察峰值，不是系统连续精确峰值。OS文件缓存、桌面负载与hashseed未隔离，不能据此断言因果加速或生产SLA。

候选数只实测K=1；10/100真实登记候选缺失，多入口联合选择原接口未提供。大规模同合同数据未就绪，NOT_RUN。没有用其他城市旧网络替代。原接口没有的Top3/EDGE能力与实验适配明确分开。

证据：[全分布]({IDS['q8']}/latency_distribution.csv)、observations_normalized.csv、benchmark_matrix.csv、medium_benchmark_matrix.csv、top3_benchmark_matrix.csv、replan_benchmark_matrix.csv（存在时）、memory_usage.csv、route_quality_comparison.csv和failure_and_timeout.csv。原始每次输出使用同名run_id，Q8-A1为主小图、Q8-MEDIUM为合并图、Q8-TOP3-ADAPTER为新多路径适配器、Q8-REPLAN为指定边封闭。计时前缀不同不可混池。

第一次性能工程运行因warm-up与正式输出ID碰撞整批作废，保留在 attempts/ATTEMPT_A0_WARMUP_ID_COLLISION，不纳入主统计；修复只改本轮run_id命名。合并输入第一次严格全字典相等检查被缺元数据阻断，保留 medium_merge_A0_exact_equality_block.json；后续规则要求所有共有字段相同，仅填缺字段，无冲突坐标/标签覆盖。

## 8. 每个质询的状态和证据定位

Q2地图身份与终点对照 PASS（限地图内部）；Q6A INCONCLUSIVE（316/353保存组通过本轮有限复核，37组未足够核验）；Q6B BLOCKED_BY_MISSING_INPUT；Q7原接口 FAIL，新状态包装器仅完成无失效路线/恢复检查，备用方向资格 INCONCLUSIVE；Q8总体一秒目标 FAIL，K10/K100/城市网络/联合入口分支 BLOCKED_BY_MISSING_INPUT。

逐实验 summary.csv / summary.json、raw_results.jsonl、failures.csv 和 provenance.csv 对应各ID。run_id与输出文件逐条绑定；Q6保存几何的行级标识在replay_comparison.csv。旧阶段数值引用与本轮计算不同，不把旧结果写成本轮实跑。

## 9. 已解决的问题

完成三个原门地图身份核验及9条终点定义控制；核查旧窗口绑定偏差；核对恢复原生片段/新增面源身份；重算已保存几何；提供不伪装成旧APP功能的动态状态实验包装器；建立真实冷/热、单路径/Top3及两裁片输入计时。没有用数据对象计数充当业务收益。

## 10. 仍未达到要求的问题

缺现实真值；旧APP不处理关门/封路状态；两个动态场景未证明合法备用方向前提；37组保存轨迹未完整核验；冷启动不满足一秒；10/100候选、联合入口选择与城市级性能没有实测。负结果和受阻项均保留，不删分母。

## 11. 没有测试过的问题

现场门是否存在/当前开放/允许公众、真实同层和动态障碍、独立盲测、跨城泛化、HTTP并发/页面总延迟、生产资源隔离、真实主备通道多样性、精确路缘宽度和完整障碍普查均未测试。合并相邻裁片是已暴露开发数据，不产生新独立验证组。

## 12. 不允许作出的结论

不得称“证明真实可走”“公众一定能进”“OSM正确”“完整导航已完成”“系统总体一秒”“377或82个对象就是路线提升”“三条节点路径就是三条现实备用通道”。北门exit不能改称入馆门；假设段不能升级为原生事实；作者检查不能写成独立现场核验。

## 13. 后续最小必要实验

首先补独立、有时间戳的6条现场逐段记录及合格第三建筑；补37组保存轨迹缺少的关联/构成字段；若开发产品动态状态接口，另行验收参数实际生效与确有备选通道的场景；准备具有同域身份/约束合同的更大网络及真实候选集合后才做联合/城市级基准。这里是缺项说明，不自动执行下一轮。

本轮来源与结果核验是**作者检查及独立脚本/新进程交叉复算**，没有额外独立人员/代理，不能冒称独立角色审核。截止本报告记录起累计约{elapsed:.1f}分钟（含下载前旧资料定位、失败诊断、重试和等待；无本轮外网请求）。最终封包校验结果另见包外复验回执。
'''
report=report.replace('Q8独立计时地点只有图书馆1处。',f'Q8独立计时地点为{summary8["independent_latency_test_sites"]}处；同址重复不增加样本独立性。')
report=report.replace('相同起点/源/成本下，3个中心点', '登记南门路线包含58.302米原生段和90.561米面派生段；北出口为125.565米原生、165.537米面派生及9.682米假设段；图书馆为180.581米原生段。原生线类仍可能包含原合同允许的道路轴，不等于全程独立人行道。\n\n相同起点/源/成本下，3个中心点')
report=report.replace('3次warm-up排除','3次warm-up排除')
primary_adapter=[r for r in q7rows if r.get('control_variant')=='STATE_INJECTION_ADAPTER'];primary_controls=[r for r in q7rows if r.get('control_variant')=='UNMODIFIED_PUBLIC_APP_INTERFACE'];dynamic_counts=dict(collections.Counter(r['status']for r in primary_adapter))
report=report.replace('S0/S5共12次PASS，S1–S4共24次NO_PATH；',f'主表状态适配器的实际结果为{dynamic_counts}；')
if(D['q7']/'outputs/primary_result_ids.json').exists():
 report=report.replace('前置“两个场景都有合法备用接近方向”未完整建立。','博物馆A1 S2/S3各3次得到151.961475米条件绕行，比原148.863122米增加3.098353米，仍为原生/登记面派生且假设段0米；被删步道的几何重叠为0。图书馆相应S2/S3各3次仍NO_PATH，不能推断现实无路。\n\n前置“两个场景都有合法备用接近方向”未完整建立。')
 report=report.replace('前置“两个场景都有合法备用接近方向”未完整建立。','首版博物馆按“native”取中间边，实际取到residential道路轴，不符合原生步道封闭要求。保留首版19行（含旧接口负控）为secondary压力测试，按原baseline中的源标签锁定footway way/178737605后重跑博物馆组；图书馆way/1219527813本来就是footway，保留原19行。主表仍为38行（36状态请求+2接口负控），另存一次基线重核。关闭对象不同，不能把结果变化写成算法增强；原核心/目标/起点/成本不变。\n\n前置“两个场景都有合法备用接近方向”未完整建立。')
 report=report.replace('没有证明成功备用路线恢复能力', '没有证明两个场景均具现实备用路线恢复能力')
 report=report.replace('选定边在这些请求下无法绕过，**没有证明', '图上重求路结果逐行保留，**没有证明')
 report=report.replace('run `Q7-NATIVE-API-CONTROL-0`、`Q7-NATIVE-API-CONTROL-2`','主表run '+ '、'.join('`'+r['run_id']+'`'for r in primary_controls))
report=report.replace('entry_constraint_context.csv','entry_constraint_context_A1.csv')
report=report.replace('353组保存路线、13,924段','353组保存路线、13,924个保存段实例（不去重，不等于独立现实路段）')
report=report.replace('3个登记门请求都形成条件路线。','3个登记门请求都形成条件路线。该对照是终点定义与契约可行性控制，不是对现实导航方案优越性的准确率测试；身份注释另见target_definition_comparison_annotated.csv。')
report=report.replace('记录为负控FAIL。','记录为负控FAIL。')
if(ROOT/'audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json').exists():
 report=report.replace('旧博物馆路侧窗口确有场景绑定错误：','补充审计A0还发生了本轮新脚本的CRS错误：把Source.coord返回的经纬度与米制面比较，使上下文误空、身份重核出现约347万米假距离。原始6行保留但明确失效，错误版本不用于结论；A1改用Source.projected，重新得到3个边界距离0米及源上下文。原entry_identity_audit与9条规划请求本来就正确使用米制，未受影响。修正记录见 audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json；不能把测试器错误归因于入口或旧算法。\n\n旧博物馆路侧窗口确有场景绑定错误：')
report=report.replace('阶段计时相互包含，不能相加；','每个图/方法/任务配置先做3次热进程warm-up并排除；冷请求均从新Python进程开始，不在同一进程内预热，也不事后丢弃较慢冷启动。阶段计时相互包含，不能相加；')
report=report.replace('读/索引计时钩子仅代理原操作，测量开销未扣。','read_ms只计Path.read_bytes/read_text，gzip等内部IO未全部单独分离；index_ms只计STRtree构造，不代表所有数据结构索引。图预处理包含解析、约束、构图、哈希和收据写出，不是纯建图独占时间；这些相互嵌套，不能相加。钩子仅代理原操作，测量开销未扣。')
report=report.replace('候选数实测K=1和K=2。','计算图节点/有向弧包含格网、面派生可见边和接口，不等于真实路口/道路数量；博物馆单裁片的派生图比“两裁片合并”的图书馆图更密，不能按裁片个数推断规模。K2的solver_ms是两次原求解之和，不是一个门的一次求解；candidate_ranking_ms才是对两个代价值排序。\n\n候选数实测K=1和K=2。')
report=report.replace('每配置3次热身后30次热进程请求、10次新进程冷请求；','主单路径/Top3/指定断边配置3次热身后30次热进程请求、10次新进程冷请求；博物馆K2构建昂贵，预先采用允许的10次热、10次冷最小配置；')
report=report.replace(mdtable(perfrows,['规模','任务','模式','计时','n','p95 ms','最慢 ms','一秒门槛']),mdtable(perfrows,['规模','任务','模式','计时','n','p95 ms','最慢 ms','一秒门槛','返回结果']))
if joint_tested:
 report=report.replace('候选数只实测K=1；10/100真实登记候选缺失，多入口联合选择原接口未提供。','候选数实测K=1和K=2。K2是新增适配器：同一博物馆、同一原起点，对原登记南门/北出口分别按APPROACH_OUTSIDE求路，再按冻结F1代价/原生ID选留；北出口没有当入馆门。该实现保留两个按原门分别生成的预处理对象，不合并成新的全局多目标图。K2的图节点/弧数量报告单个候选图的最大值，不把重复全图相加制造规模。它与图书馆K1不是同图配对，不能据耗时比值推导候选数增长复杂度。10/100真实登记候选缺失，原APP仍未提供联合选择接口。')
 report=report.replace('联合入口选择与城市级性能没有实测。','原APP联合选择接口与城市级性能没有验证；新增K2逐门选择适配器不能冒充可扩展联合算法。')
 report=report.replace('Q8总体一秒目标 FAIL，K10/K100/城市网络/联合入口分支 BLOCKED_BY_MISSING_INPUT。','Q8总体一秒目标 FAIL；新增K2门外选择适配器实测，原APP接口未改变；K10/K100/城市网络 BLOCKED_BY_MISSING_INPUT。')
 report=report.replace('候选数实测K=1和K=2。','计算图节点/有向弧含格网、面派生可见边和接口，不等于真实路口/道路数；博物馆单裁片图比“两裁片合并”的图书馆图更密，不能按裁片数推断规模。K2的solver_ms是两次原求解之和，candidate_ranking_ms才是对两个代价值排序。\n\n候选数实测K=1和K=2。')
 report=report.replace('来源与结果核验是', '来源与结果核验是')
report=report.replace('第一次性能工程运行因warm-up与正式输出ID碰撞整批作废，保留在','第一次性能工程运行因3个warm-up与正式输出ID碰撞整批作废。38条当时原始行仍保留，但3个warm-up的独立输出文件曾被覆盖，不能冒称全部独立输出可恢复；留存实物在')
if(D['q8']/'secondary_results/top3_A1_uninstrumented_raw_results.jsonl').exists():
 report=report.replace('第一次性能工程运行因3个warm-up','Top-3 A1的43条观测保留为secondary_results版本，整体计时与路线仍有效；因缺读/索引分阶段时钟，预先记录原因后用同输入、同核心补测A2。主统计采用A2，原A1日志/输出/源码均保留，不混池、不按速度选留，也不称算法变强。\n\n第一次性能工程运行因3个warm-up')
 if(D['q8']/'top3_measurement_versions.csv').exists():
  version_rows=table(D['q8']/'top3_measurement_versions.csv');small=[{'版本':r['measurement_version'],'计时':r['timing_scope'],'温度':r['temperature'],'n':r['n'],'p95 ms':round(float(r['p95_ms']),2),'最慢 ms':round(float(r['max_ms']),2)}for r in version_rows];report=report.replace('## 8. 每个质询', 'Top3两次有效观测均披露；差异属于负载/测量版本变化，不是算法速度改善，也不能只挑较快的一版：\n\n'+mdtable(small,['版本','计时','温度','n','p95 ms','最慢 ms'])+'\n\n## 8. 每个质询')
report=report.replace('原始每次输出使用同名run_id，','各benchmark_matrix中的status只表示工作进程退出是否正常，不能当作路线成功；worker_process_outcomes.csv对齐子请求状态，实际NO_PATH见raw及route_quality表。原始每次输出使用同名run_id，')
report=report.replace('closures_edge_changes.csv','closure_edge_changes.csv')
report=report.replace('源覆盖、未知与无路的区别','源覆盖、未知与无路的区别')
report=report.replace('outputs/Q7-*.json。','outputs/Q7-*.json；逐条物理几何重叠和增距见 [replanning_geometry_comparison.csv]('+IDS['q7']+'/replanning_geometry_comparison.csv)。')
report=report.replace('原始响应保留。这说明','原始响应保留。本轮负控直接调用P.plan，没有另测HTTP服务器是否先拒绝未知字段；这说明')
(ROOT/'RESEARCH_REVIEW.md').write_text(report,encoding='utf-8')
performance='# Q8 性能报告\n\n'+report.split('## 7. Q8 性能结果')[1].split('## 8.')[0];(D['q8']/'performance_report.md').write_text(performance,encoding='utf-8')
# Required per-experiment indexes/manifests retain missing scopes instead of inventing data.
frozen=read(ROOT/'audit/FROZEN_RUNTIME_MANIFEST.json');input_rows=[{'source_archive_sha256':frozen['archive_sha256'],'member':m['member'],'sha256':m['sha256'],'bytes':m['bytes'],'role':'BYTE_FROZEN_SOURCE_OR_CODE'}for m in frozen['members']]
for key,path in D.items():
 rows=raw(path/'raw_results.jsonl');csvout(path/'input_manifest.csv',input_rows)
 if not(path/'provenance.csv').exists():csvout(path/'provenance.csv',input_rows)
 csvout(path/'failures.csv',[r for r in rows if r['status']!='PASS'])
 csvout(path/'missing_and_untested.csv',[r for r in missing if r['experiment_id']==IDS[key]],['experiment_id','status','item','result','reason'])
 summary=read(path/'summary.json');csvout(path/'summary.csv',[{'experiment_id':IDS[key],'status':summary['status'],'key':k,'value':v}for k,v in summary.items()])
 if key=='field':(path/'final_report.md').write_text(report.split('## 5. Q6B')[1].split('## 6.')[0],encoding='utf-8')
 (path/'README.md').write_text(f'# {IDS[key]}\n\n当前汇总状态：{summary["status"]}。\n\n本目录是新补充实验，原件未修改。定义和限制以 protocol.json、原始响应、结果表和根目录 RESEARCH_REVIEW.md 对应章节为准。raw_results 包含保留的工程失败记录，不能把事件行数当独立地理样本数。所有路线仍是冻结地图/条件模型输出，未与现场真值混同。\n\n核验身份：本轮作者及交叉脚本，未有独立现场或额外独立角色审核。\n',encoding='utf-8')
q7raw=q7rows;(D['q7']/'dynamic_route_results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in q7raw),encoding='utf-8')
q6failed=[dict(r,record_type='AUDIT_EXECUTION_EVENT')for r in raw(D['q6']/'raw_results.jsonl')if r['status']!='PASS']
q6failed.extend(dict(r,record_type='SAVED_ROUTE_GROUP_NOT_INDEPENDENT_NEW_ROUTE',output_file='replay_comparison.csv',failure_reason='SOURCE_SCENE_ASSOCIATION_OR_CONSTITUENT_LAYER_EVIDENCE_INCOMPLETE')for r in table(D['q6']/'route_constraint_audit.csv')if r['status']!='PASS')
csvout(D['q6']/'failures.csv',q6failed)
csvout(D['q7']/'runtime_log.csv',[{k:r.get(k)for k in('run_id','scene_id','state','repeat','control_variant','runtime_ms','state_overlay_build_ms','preprocessing_cache','state_overlay_cache','process_cold_start','solver_invoked','status')}for r in q7raw])
for name in('field_photos_or_tracks','entry_access_figures'):
 parent=D['field']if name.startswith('field')else D['q2'];folder=parent/name;folder.mkdir(exist_ok=True)
 (folder/'README.md').write_text('真实现场资料未提供，此目录没有照片/轨迹。'if name.startswith('field')else'实际PNG/SVG位于 ../figures/entry_targets_0..2。此处仅索引，不重复复制图件。',encoding='utf-8')
# Inline map data so file:// viewing does not depend on fetch or internet.
data=read(ROOT/'figures/viewer_data.json')
for idx in(0,2):
 for state in range(6):
  scene_id='sh-huangpu-01'if idx==0 else'sh-library';selected=next(r for r in q7rows if r['scene_id']==scene_id and r.get('state')=='S'+str(state)and r.get('repeat')==0 and r.get('control_variant')=='STATE_INJECTION_ADAPTER');item=read(D['q7']/selected['output_file']);case=next(c for c in data['dynamic']if c['request']['door_id']==data['scenes'][idx]['context']['door_id']);baseline_row=next(r for r in q7rows if r['scene_id']==selected['scene_id']and r.get('state')=='S0'and r.get('repeat')==0 and r.get('control_variant')=='STATE_INJECTION_ADAPTER');baseline=read(D['q7']/baseline_row['output_file'])['route'];closed=next(s for s in baseline['segments']if s.get('edge_id')==case['selected_native_edge_id']);data['scenes'][idx]['variants'].append({'label':'动态 S'+str(state)+'（新实验包装器）','row':item['row'],'route':item['route'],'target_xy':data['scenes'][idx]['context']['door_xy'],'obstacle':case['obstacle']if state==3 else None,'closed_segment':closed if state in(2,4)else None})
gallery=''.join(f'<figure><a href="{html.escape(rel(p))}"><img loading="lazy" src="{html.escape(rel(p))}" alt="{html.escape(p.stem)}"></a><figcaption>{html.escape(rel(p))} · <a href="{html.escape(rel(p.with_suffix(".svg")))}">SVG</a></figcaption></figure>'for p in sorted(ROOT.glob('Q*/figures/*.png')))
template=(ROOT/'scripts/viewer_template.html').read_text(encoding='utf-8');page=template.replace('__REPORT__',markdown.markdown(report,extensions=['tables','fenced_code'])).replace('__GALLERY__',gallery).replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
(ROOT/'index.html').write_text(page,encoding='utf-8')
print('ASSEMBLED',{'draft':draft,'formal_rows':len(formal),'distributions':len(distributions),'gallery':len(list(ROOT.glob('Q*/figures/*.png')))})
