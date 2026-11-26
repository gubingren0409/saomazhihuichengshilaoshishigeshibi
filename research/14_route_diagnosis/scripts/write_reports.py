"""Read finalized diagnosis evidence and write the four requested narrative files."""
from pathlib import Path
import json,csv,hashlib,collections,datetime,math
ROOT=Path(__file__).resolve().parents[1]
LABEL={'south':'博物馆南门','north_near':'北出口近起点','north_far':'北出口远起点','library':'图书馆登记门'}
def read(n):return json.loads((ROOT/n).read_text(encoding='utf-8-sig'))
def rows(n):
 with (ROOT/n).open(encoding='utf-8-sig',newline='')as f:return list(csv.DictReader(f))
def yes(v):return str(v).lower()=='true'
def finite(v):
 try:return math.isfinite(float(v))
 except(TypeError,ValueError):return False
def num(v,d=3):return f'{float(v):.{d}f}'if v not in(None,'')else'—'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def table(headers,rs):return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(map(str,r))+' |'for r in rs)+'\n'
def main():
 finalized=read('results/FINALIZED.json');s=read('results/summary.json')
 if s.get('formal_solver_count')!=8 or s.get('SSSP_traversals')!=16:raise ValueError('FORMAL_EXECUTION_INCOMPLETE')
 faces=rows('NEW_FACE_ROUTE_RELEVANCE.csv');alts=rows('ALTERNATIVE_ROUTES.csv');lineage=read('results/graph_lineage.json')['lineage']
 stats=[];text=[];method_rows=[]
 for case in s['cases']:
  name=case['case'];f=[r for r in faces if r['case']==name and r['method']=='F0'and yes(r['in_query_scene'])]
  near=sum(yes(r['within_20m'])for r in f);connected=sum(finite(r['forced_arc_cost_lower_bound_m'])for r in f)
  stats.append([LABEL[name],len(f),near,connected])
  for method,m in case['methods'].items():
   method_rows.append([LABEL[name],method,num(m['reference_cost_m'],6),num(m['minimum_cost_m'],6),f"{m['reference_error_m']:.3g}",m['explicit_tag_used']])
  f0=case['methods']['F0'];f1=case['methods']['F1']
  reasons=f0['interface_reasons']
  text.append(f"### {LABEL[name]}\n\n自身场景新增面记录{len(f)}条，20米走廊内{near}条，具有起点正向与门侧反向可达归属的面记录{connected}条。F0最小代价{num(f0['minimum_cost_m'],6)}，F1为{num(f1['minimum_cost_m'],6)}加权米，均重现原值。B3接口审计中，严格更贵{reasons.get('D_EXISTING_ROUTE_STRICTLY_CHEAPER',0)}条、其他有向分量{reasons.get('B_OTHER_DIRECTED_COMPONENT',0)}条、等价{reasons.get('TIED_EQUIVALENT',0)}条。这里数的是接口证据记录，方向、namespace和方法的重复不等于独立物理地点。\n")
  unknown=sum(v for k,v in reasons.items()if k.startswith('G_'))
  text[-1]+=(f"F0另有G类证据不足记录{unknown}条，保持未知，不把它们自动判为R1实现错误。\n\n"if unknown else 'F0本命名空间未残留G类记录。\n\n')
 face_table=table(['业务端点任务','自身场景新增面记录','20m内','有经面owner弧有限walk证据'],stats)
 face_table+='\n最后一列要求某条面归属弧的正向距离+弧代价+反向距离有限，避免仅凭两个不同节点分别可达就说可经此面。它仍是模型walk证据，不自动等于无重复节点的简单替代路线。\n'
 global_ids={v['source_area_id']for v in faces if yes(v['global_unique_new'])}
 relevant_ids={v['source_area_id']for v in faces if yes(v['global_unique_new'])and yes(v['in_query_scene'])}
 reachable_ids={v['source_area_id']for v in faces if yes(v['global_unique_new'])and yes(v['in_query_scene'])and finite(v['forced_arc_cost_lower_bound_m'])}
 face_table+=f'\n按全局source身份去重，共{len(global_ids)}个新增面；其中{len(relevant_ids)}个出现在业务使用的两个场景面池，{len(global_ids-relevant_ids)}个不在这两个面池。{len(reachable_ids)}个具备经面弧的有限完整walk证据；详细其他分量/无owner记录见原表，不能把场景新增27条直接叫82中的27个。\n'
 other=read('audits/independent_other_scene_geometry.json')
 face_table+=f"\n独立检查也覆盖了其他场景：{other['outside_query_pool_unique_new_IDs']}个池外新身份、{other['outside_scene_object_route_rows']}条对象—路线关系中，20米以内有{other['outside_near_any_business_route_within20m']}条；最近Ω距离{num(other['nearest'][0]['omega_distance_m'])}米。这不是仅凭scene标签判远，仍不把距离单独当无捷径证明。\n"
 population=s['global_new_business_scene_overlap']['unique_reasons']
 face_table+=f"\n36个业务场景池内新身份的实际分类：经面更贵{population.get('EXISTING_ROUTE_STRICTLY_CHEAPER',0)}个、其他有向分量{population.get('OTHER_DIRECTED_COMPONENT',0)}个、未形成当前query owner弧{population.get('NOT_PRESENT_IN_QUERY_NAMESPACE',0)}个。\n"
 isolated=read('results/unconnected_face_evidence.json');part=isolated['face']['components'][0]
 face_table+=f"\n未接入案例{isolated['face']['source_id']}并非源对象缺失或Ω为空：固定PREP记录为ADMITTED，合法面积{num(part['area_m2'])}平方米，但portal/reflex/roadmap节点/弧均为0。保留其源身份，当前没有可用接点；不能据此断言现实没有通路。实际PREP成员及SHA见results/unconnected_face_evidence.json。\n"
 min_table=table(['任务','方法','R1代价','新求解最小代价','差值','显式tag采用记录数'],method_rows)
 alt_table=table(['任务','方法','实际状态','几何长m','代价','假设长m','代价差m'],[[LABEL.get(r['case'],r['case']),r['method'],r['status'],num(r.get('length_m'),6),num(r.get('cost_m'),6),num(r.get('hypothesis_m'),6),num(r.get('slack_m'),9)]for r in alts])
 far=[r for r in faces if r['case']=='north_far'and r['method']=='F0'and yes(r['in_query_scene'])and r['source_area_id']in('way/161090905','way/178721645')]
 far_table=table(['原生面','拥有图节点','从起点可达','能继续到门','经面弧代价下界','较原路线多'],[[r['source_area_id'],r['owned_node_count'],r['in_start_component'],r['in_goal_component'],num(r['forced_arc_cost_lower_bound_m'],6),num(r['slack_lower_bound_m'],6)]for r in far])
 cf=s['counterfactual_status_counts']
 bounds=('最优性只针对SHA绑定的重建有限图、原R1首个合格端点附着和原F0/F1代价，不是连续空间全局最短或现场通行证明。'
  '北出口node/6897145227仍为entrance=exit，仅APPROACH_OUTSIDE；公众权限、开放状态和未记录高差继续未知。'
  'P、Ω、30米门前域、障碍、权限、层级及净空均未放宽。')
 (ROOT/'ROUTE_DIAGNOSIS.md').write_text('# 为什么补齐对象后，业务路线仍未改变\n\n本轮重新完成8个固定B3诊断调用（每次正/反2次SSSP，共16次），不是重跑R1的104项。全部重现原最小代价。独立证书核验与作者求解分开。\n\n'+face_table+'\n'+min_table+'\n'+''.join(text)+'\n## 北远的两个关键面\n\n'+far_table+'\n这一区分很关键：一个面处于其他分量；另一个确实接入业务可达网络，但经它更贵。接入不等于改善。\n\n## 解释与修复范围\n\n本轮没有证明需要修改R1路由算法的通用缺陷；修正的是本轮诊断器的强制平行option材料化及无显式interface标签的portal归属判读。原8次距离运行保留，不伪造新solver。更细的未知记录保留G类，不凭元数据缺失认定漏接。\n\n局部M02/M04属于其他固定机制端点，M04终点不是入口；3/8→5/8不能与四业务端点任务混合分母。\n\n'+bounds+'\n\n用户观察仍PENDING_USER_OBSERVATION，截图精确请求仍SCREENSHOT_REQUEST_UNBOUND。\n',encoding='utf-8')
 (ROOT/'BUSINESS_ROUTE_OPPORTUNITY.md').write_text('# 业务路线的替代机会与边界\n\n'+min_table+'\n## 代价证据\n\n对每个有向option(u,v)，按原代价计算 d_s(u)+c(u,v)+d_t(v)。正slack说明经过它不可能改善当前最优；零slack说明等价机会，不能自动说产生新通道。前后链重复节点时只是强制经过walk，不冒充简单替代路线。\n\n新增面几何下界为 dist(s,Ω)+dist(Ω,t)，它忽略障碍及面内行程，是保守下界。独立结果见audits/independent_face_lower_bounds.json：南门、北近、图书馆全部新增面已被下界排除；北远两个面再用图证书辨别。\n\n## 有限替代路线\n\n'+alt_table+'\n只做事前有界的候选材料化，没有无限K最短枚举；未找到不等于所有更贵简单替代都不存在。毫米或更小几何差异不构成业务收益，不报告现实最优到达误差。完整几何/逐段约束见results/materialized_*与ALTERNATIVE_ROUTES.csv。\n\n## 删类反事实\n\n实际证书状态：'+json.dumps(cf,ensure_ascii=False)+'。删除新增option时保留同端点原native/旧derived平行选择。用B3最优下界与删类图中等成本原B0路径见证夹逼其最优值，不额外调用SSSP。具体删除集合及逐弧见证以机器可读counterfactual文件为准，不把一句“原路径还在”替代证书。\n\n'+bounds+'\n',encoding='utf-8')
 group=collections.defaultdict(list)
 for v in lineage:group[(v['case'],v['from_mode'],v['to_mode'])].append(v)
 ll=[]
 for (case,a,b),rs in group.items():
  into=collections.defaultdict(set);out=collections.defaultdict(set)
  for v in rs:into[v['new_component']].add(v['old_component']);out[v['old_component']].add(v['new_component'])
  ll.append([LABEL[case],a+'→'+b,sum(v['common_node_count']for v in rs),sum(len(x)>1 for x in into.values()),sum(len(x)>1 for x in out.values())])
 (ROOT/'COMPONENT_LINEAGE.md').write_text('# 分量与对象的谱系\n\n'+table(['任务','父→子模式','共同图节点映射数','多旧分量汇入一新分量','一旧分量流向多个新分量'],ll)+'\n共同图节点包含原有派生节点，不能全部叫原生实地点；原生node/ID及grade alias的专项映射见额外native-anchor证据。编号只是当次图的标签，标签改变不自动代表拓扑合并。新增节点可能形成孤立分量，使总数上升；需查共同对象实际归属。\n\n逐接口表在query-bound图上检查起点正向、门侧反向可达；prepared before-binding组件总数不能直接代替门的可达性。Point portal可能沿已有native接点接入，没有新的interface_id弧也不能直接认定漏接。\n\n'+bounds+'\n',encoding='utf-8')
 topology=read('results/query_component_lineage.json');anchors=read('results/graph_lineage.json')['native_anchor_summary']
 with (ROOT/'COMPONENT_LINEAGE.md').open('a',encoding='utf-8')as f:
  f.write('\n## 原生身份锚点与已绑定端点\n\n'+table(['任务','父→子','共同原生token数'],[[LABEL[v['case']],v['from_mode']+'→'+v['to_mode'],v['common_native_tokens']]for v in anchors]))
  f.write('\n原生token保留node/ID及@layer/@level，不能按相同XY或去掉grade后合并身份。\n\n'+table(['任务','模式','节点/弧','弱/强分量','起点弱标签','原门弱标签'],[[LABEL[v['case']],v['mode'],str(v['nodes'])+'/'+str(v['arcs']),str(v['weak_components'])+'/'+str(v['strong_components']),v['start_component'],v['door_component']]for v in topology]))
  f.write('\n弱标签相同只说明弱连通；实际有向可达与最优性另由ds/dt有限集合、全弧Bellman不等式和前驱primal证书验证。绑定原ID和坐标、0位移及原返回attachment均保留在原记录。\n')
 with (ROOT/'ROUTE_DIAGNOSIS.md').open('a',encoding='utf-8')as f:
  f.write('\n## 下一步建议\n\n建议阶段性冻结当前衔接组件，不再为了让这四条已最优的固定路线变短而继续扩算法。对象完整性改善和局部拓扑收益仍保留；它们没有转化为本组业务收益，并非需要放宽限制来纠正的负结果。\n\n下一阶段更值得优先明确整链原型的业务输入覆盖、固定端点附着契约及结果解释，并处理真实可见的冷构图成本。现场同层/公众通行可靠性仍需独立证据，不能以计算连通替代。当前证据支持结束这组任务的衔接优化，不支持宣告通用复杂建筑到达已解决；下一模块由GPT和用户审核决定，本轮不自动启动。\n')
 (ROOT/'README.md').write_text('''# R2路线诊断审查入口

打开 http://127.0.0.1:53451/ 查看四个固定业务任务。离线可打开visuals/index.html：源背景与诊断payload内嵌，不调用外部地图。选择卡片、F0/F1、B0/B1/B2/B3，切换5/10/20米诊断走廊与图层，点选面/接口查看分量、采用与未采用理由，再查看有限替代线。诊断走廊不是新可行域。

这是只读诊断器：主线是R1保存路线；替代分析来自R2实际8次求解。界面切换不会偷偷新增求路或冒称当前实时运行。

在本目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53451
```

前台服务用Ctrl+C停止；已运行后台服务先从/api/health确认service=PED_AREA_CONNECTIVITY_R2_DIAGNOSIS再按其pid停止。不要停止旧53421/53431/53441。运行与证书复验入口见src/diagnose.py、src/certificates.py与src/independent*.py；不得无意重复8正式求解。requirements.txt记录实际环境版本，不代表本轮安装了软件。

本包为增量诊断，完整原始R1固定包不重复内嵌；从源重建需要另行提供R1 ZIP，SHA256必须是d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed。新薄图、证书、结果、地图和必要源码在包内；不宣称整个历史自包含。原图数据© OpenStreetMap contributors · ODbL，frozen 2026-11-08T21:21:00Z，计算EPSG:32651米。

ROUTE_DIAGNOSIS.md解释四条路线；BUSINESS_ROUTE_OPPORTUNITY.md列替代和反事实；COMPONENT_LINEAGE.md解释分量。三份根CSV为完整逐对象证据。audits/INDEPENDENT_REVIEW.md记录真实独立范围；最终固定ZIP的解包回执放包外，绑定其SHA。包内候选状态保留封包前时序，用户验收和现场验证仍待定。
''',encoding='utf-8')
 inputs=['results/FINALIZED.json','results/summary.json','results/graph_lineage.json','results/unconnected_face_evidence.json','NEW_FACE_ROUTE_RELEVANCE.csv','INTERFACE_USAGE_AUDIT.csv','ALTERNATIVE_ROUTES.csv','audits/independent_other_scene_geometry.json']
 receipt={'at':datetime.datetime.now().astimezone().isoformat(),'generator_sha256':sha(Path(__file__)),'inputs':[{'path':n,'sha256':sha(ROOT/n)}for n in inputs],'outputs':[{'path':n,'sha256':sha(ROOT/n)}for n in ['README.md','ROUTE_DIAGNOSIS.md','BUSINESS_ROUTE_OPPORTUNITY.md','COMPONENT_LINEAGE.md']],'new_solver_calls':0}
 (ROOT/'audit/report_bindings.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'written':4,'input_case_count':len(s['cases']),'formal_solver_count':s['formal_solver_count']}))
if __name__=='__main__':main()
