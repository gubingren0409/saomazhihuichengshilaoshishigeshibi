from pathlib import Path
import json,zipfile,csv,io,hashlib,collections,math,re
B=Path(r'E:/智慧城市和位置服务/_task_runtime');O=B/'PG1_MIDTERM_RESEARCH_MATERIALS_R3/working/independent'
SZ=B/'PG1_RESUME_STREET_SIDE_R1/delivery/PG1_RESUME_STREET_SIDE_R1_REVIEW_FIXED.zip';QZ=B/'PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115/delivery/PG1_SUPPLEMENTARY_Q2_Q6_Q7_Q8_20261115_REVIEW.zip'
s=zipfile.ZipFile(SZ);q=zipfile.ZipFile(QZ)
def sh(b):return hashlib.sha256(b).hexdigest()
def records(z,n):return list(csv.DictReader(io.StringIO(z.read(n).decode('utf-8-sig'))))
def lines(z,n):return [json.loads(l) for l in z.read(n).decode('utf8').splitlines() if l.strip()]
facts=[]
def fact(label,value,z,n,field,scope):facts.append({'claim':label,'value':value,'member':n,'member_sha256':sh(z.read(n)),'field_or_rule':field,'scope':scope})
r=lines(s,'audit/experiment_registry.jsonl');assert len(r)==24
actual=sum(bool(x['result']['solver_invoked']) for x in r);assert actual==22
fact('formal_attempts',len(r),s,'audit/experiment_registry.jsonl','count all JSONL rows','18 initial plus6R0 cost repair; same6query families repeated')
fact('actual_formal_solver_calls',actual,s,'audit/experiment_registry.jsonl','sum(result.solver_invoked)','No new shortest path computation performed by reviewer')
cur=records(s,'results/query_results.csv');print('current fields',list(cur[0]));assert len(cur)==18
fact('current_matrix_requests',len(cur),s,'results/query_results.csv','row count','6 fixed query types × R0/R1/R2; retrospective development')
graphchecks=[]
for win in ['native','tagged','missing']:
 for variant in ['R0','R1','R2']:
  n=f'results/graphs/{win}_{variant}.json';g=json.loads(s.read(n));bad=[]
  for e in g['edges']:
   if ':left:' in e['u'] and ':right:' in e['v'] or ':right:' in e['u'] and ':left:' in e['v']:bad.append(e['edge_id'])
  graphchecks.append({'window':win,'variant':variant,'edge_count':len(g['edges']),'direct_left_to_right_edges':bad,'sha256':sh(s.read(n))})
assert all(not x['direct_left_to_right_edges'] for x in graphchecks)
# Source reports already distinguish schematic geometry from exact source polylines; inspect declared graph edge statuses.
status=collections.Counter()
for win in ['native','tagged','missing']:
 for variant in ['R1','R2']:
  for e in json.loads(s.read(f'results/graphs/{win}_{variant}.json'))['edges']:status[(e.get('geometry_status'),e.get('layer'))]+=1
fact('graph_display_geometry_status',str(dict(status)),s,'results/graphs/tagged_R2.json','geometry_status and layer on all six R1/R2 saved graphs','SCHEMATIC is not measured curb location or physical path clearance')
raw=lines(q,'Q7-DYNAMIC-CLOSURE-SIMULATION-R1/raw_results.jsonl') if 'Q7-DYNAMIC-CLOSURE-SIMULATION-R1/raw_results.jsonl' in q.namelist() else []
primary=records(q,'Q7-DYNAMIC-CLOSURE-SIMULATION-R1/dynamic_route_results.csv');ids=json.loads(q.read('Q7-DYNAMIC-CLOSURE-SIMULATION-R1/outputs/primary_result_ids.json'));assert set(x['run_id'] for x in primary)==set(ids)
adapter=[r for r in primary if r['control_variant']=='STATE_INJECTION_ADAPTER'];nc=[r for r in primary if r['control_variant']!='STATE_INJECTION_ADAPTER'];counter=collections.Counter(r['status'] for r in adapter)
assert len(adapter)==36 and counter=={'PASS':18,'NO_PATH':18} and len(nc)==2
fact('dynamic_adapter_outcomes',dict(counter),q,'Q7-DYNAMIC-CLOSURE-SIMULATION-R1/dynamic_route_results.csv','filter control_variant=STATE_INJECTION_ADAPTER; count status','2sites×6states×3repeats=36; not36independent geographical requests')
neg=[]
for r in nc:
 out=json.loads(q.read('Q7-DYNAMIC-CLOSURE-SIMULATION-R1/'+r['output_file']));assert out['input']['dynamic_state']['closed_doors']==[out['door']['id']];assert out['status']=='ROUTED_NATIVE_OR_MAPPED';assert out['solver']['invoked']
 neg.append({'request_id':r['run_id'],'reported_test':r['status'],'actual_algorithm_status':out['status'],'closed_door':out['input']['dynamic_state']['closed_doors'],'api_scope':'Python P.plan call; HTTP behavior not directly retested','member_sha256':sh(q.read('Q7-DYNAMIC-CLOSURE-SIMULATION-R1/'+r['output_file']))})
fact('unmodified_python_dynamic_negative_controls',neg,q,'scripts/run_entries_and_closures_v2.py','lines95-99 call native=P.plan(req2)','FAIL means requested closed target still routed; not a solver runtime failure')
obs=records(q,'Q8-SCALE-LATENCY-BENCHMARK-R1/observations_normalized.csv');assert len(obs)==420
raw8=lines(q,'Q8-SCALE-LATENCY-BENCHMARK-R1/raw_results.jsonl');assert len(raw8)==453 and sum(x['warmup'] for x in raw8)==33
fact('formal_latency_observations',len(obs),q,'Q8-SCALE-LATENCY-BENCHMARK-R1/observations_normalized.csv','row count (warmup excluded)','Repeated measurements, notindependent buildings; 11configurations')
lat=records(q,'Q8-SCALE-LATENCY-BENCHMARK-R1/latency_distribution.csv');checks=[]
def percentile(a,p):
 a=sorted(a);x=(len(a)-1)*p/100;k=int(math.floor(x));j=int(math.ceil(x));return a[k]+(a[j]-a[k])*(x-k)
for t in lat:
 group=[r for r in obs if all(r[k]==t[k] for k in ['scale','query_type','mode','method','temperature'])]
 vals=[float(r[t['timing_scope']]) for r in group if r.get(t['timing_scope']) not in [None,'','None']]
 if vals:
  assert len(vals)==int(t['n']),(t['timing_scope'],len(vals),t['n'])
  p95=percentile(vals,95);mx=max(vals);assert abs(p95-float(t['p95_ms']))<1e-6 and abs(mx-float(t['max_ms']))<1e-6,t
  checks.append({'scale':t['scale'],'query_type':t['query_type'],'mode':t['mode'],'method':t['method'],'temperature':t['temperature'],'timing_scope':t['timing_scope'],'n':len(vals),'p95_ms_recalculated':p95,'max_ms_recalculated':mx,'result':'MATCH'})
assert len(checks)==len(lat)
fact('latency_summary_rows_independently_recalculated',len(checks),q,'Q8-SCALE-LATENCY-BENCHMARK-R1/latency_distribution.csv','p95linearinterpolation/max from420 normalized rows','No new performance tests; cold process and worker internal clock separate; OSdiskcacheuncontrolled')
result={'reviewer':'/root/r3_independent','role':'INDEPENDENT_READ_ONLY_FACT_REVIEW_NO_AUTHOR_CLASSIFIER_NO_SOLVER','archives':[{'name':SZ.name,'sha256':sh(SZ.read_bytes()),'CRC':'PASS'},{'name':QZ.name,'sha256':sh(QZ.read_bytes()),'CRC':'PASS'}],'facts':facts,'graph_saved_edge_checks':graphchecks,'dynamic_negative_controls':neg,'latency_summary_checks':checks,'review_scope':['actual sourceZIP SHA/CRC','raw registry counts and final matrix','direct left/right graph edge checks only; no graph rebuild','primarydynamicCSV and saved negativecontrol actual response','all165 saved latency distribution rows recomputed from normalized existing observations'],'not_checked':['fieldwalkability/currentpermissions/continuouslevels','physicalparallel sidewalk deduplication','independent original machine performance','HTTPdynamicstatevalidation','newrouting/algorithmbehavior'],'new_solver_calls':0}
(O/'PRELIMINARY_INDEPENDENT_FACTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
with (O/'INDEPENDENT_LATENCY_RECALC.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
(O/'PRELIMINARY_INDEPENDENT_REVIEW.md').write_text('''# R3独立事实检查（封包前）

审查身份：`/root/r3_independent`，未编写主材料生成实现。只读封存包，未调用作者分类函数、求解器、HTTP或外部服务。

两个固定包实际SHA256和CRC均一致。独立重数街区侧24条正式注册=22次求解+2次无端点提前返回；当前矩阵18条。R0两条跨侧零长度别名不是有效过街；R1/R2保留侧别。9张保存图未发现直接左—右跨侧边；此有限检查不能证明现实所有跨路和障碍安全。4米SCHEMATIC偏移不能作为真实侧向位置或净空证据。原生步道几何、假设侧通道、道路轴必须分开。物理平行去重与同侧广场接口仍未验证。

Q7按原primary_result_ids核对38条主记录，其中36条状态注入适配器=18PASS/18NO_PATH；两条原Python P.plan负控返回ROUTED_NATIVE_OR_MAPPED且仍向closed_doors指定的目标求路，测试FAIL。没有直接复测HTTP动态参数行为。不能将适配器当成APP已支持动态导航。原博物馆A0删residential轴段与A1删footway是不同干预，不能写成算法性能提升。

Q8的420条正式观测、33条warmup与165行延迟分布核对；逐组独立计算p95与max全部一致。冷进程总计包含启动/导入/输出，热内核不包含所有后置序列化和日志。计时分项嵌套不可相加，OS文件缓存未控制；没有城市尺度/K10/K100测试。1秒全场景目标未通过。A1有效Top3总体时间与A2补分阶段计时不是算法优化前后。重复运行不是独立建筑样本。

本记录是材料事实检查，不是现场通行认证，也没有重跑算法。最终材料和固定ZIP尚待本角色检查后另出回执。
''',encoding='utf8')
print('DONE',len(checks),'latency rows;facts',len(facts))
