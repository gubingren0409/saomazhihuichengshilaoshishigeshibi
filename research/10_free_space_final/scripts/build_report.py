"""Write the concise interpretation from actual independently scored files."""
import json,csv,datetime,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    d=read(ROOT/'runs/free_metrics.json');rows=d['rows'];methods=('M1-C','F0','F1')
    summary={}
    for method in methods:
        rr=[r for r in rows if r['panel']=='MAIN_G80_N80' and r['method']==method]
        positive=[r for r in rr if r['label']=='POSITIVE'];area=[r for r in positive if r['reference_type']=='AREA'];line=[r for r in positive if r['reference_type']=='LINE'];neg=[r for r in rr if r['label']=='NEGATIVE']
        total=lambda rr,k:sum(r['metrics'].get(k) or 0 for r in rr)
        query={r['id']+'::'+k:v for r in positive for k,v in r['routes'].items()}
        summary[method]=dict(area_covered=total(area,'reference_area_covered_m2'),area_total=total(area,'reference_area_m2'),line_covered=total(line,'reference_length_covered_m'),line_total=total(line,'reference_length_m'),
            off_reference_area=sum(r['metrics'].get('raw_off_reference_area_m2',r['metrics'].get('unverified_expansion_m2')) or 0 for r in area),
            unverified_remaining=total(area,'unverified_expansion_m2'),line_proxy_1m_off=total(line,'line_proxy_1p0_unverified_expansion_m2'),default_area=total(positive,'assumed_area_m2'),
            known_obstacle_overlap=total(neg,'negative_overlap_m2'),raw_reached=sum(v['reached'] for v in query.values()),valid_reached=sum(v['valid_reached'] for v in query.values()),
            reached_ids=sorted(k for k,v in query.items() if v['valid_reached']),new_vs_native=sorted(k for k,v in query.items() if v['new_vs_native'] and v['valid_reached']),
            outside_only=sum(v['outer_native_detour_only'] and v['valid_reached'] for v in query.values()),queries=query,
            conflict_queries=sum(bool(v['hard_conflicts'] or v['source_failures']) for v in query.values()))
    common=set(summary['F0']['reached_ids'])&set(summary['F1']['reached_ids'])
    comparable={method:{k:sum(summary[method]['queries'][qid].get(k) or 0 for qid in common) for k in ('length_m','assumed_m','native_m','mapped_area_derived_m','cost')} for method in ('F0','F1')}
    added={m:sorted(set(summary[m]['reached_ids'])-set(summary['M1-C']['reached_ids'])) for m in ('F0','F1')}
    lost={m:sorted(set(summary['M1-C']['reached_ids'])-set(summary[m]['reached_ids'])) for m in ('F0','F1')}
    north={m:next(r for r in rows if r['panel']=='NORTH_NATURAL' and r['method']==m) for m in methods}
    executions=[{**read(p),'registry_path':p.relative_to(ROOT).as_posix(),'superseded':'superseded' in p.parts} for p in (ROOT/'runs').glob('**/executions/*.json')]
    builds=sum(r['region_builds'] for r in executions)+32+read(ROOT/'runs/budget_adjustments.json')['total_adjustment']
    active=sum(r.get('wall_s',0) for r in executions)
    result={'methods':{m:{k:v for k,v in x.items() if k!='queries'} for m,x in summary.items()},'paired_F0_F1_comparable_positive_queries':len(common),'paired_length_cost':comparable,'added_vs_M1_C':added,'lost_vs_M1_C':lost,'all_experiment_region_builds_including_failed_and_synthetic':builds,'worker_wall_s_excluding_unrecoverable_interrupted_wall':active,'north_main':{m:north[m]['routes']['NORTH-DOOR'] for m in methods}}
    impact=read(ROOT/'audits/access_area_prediction_impact.json')
    gap={m:next(x for x in impact['results'] if x['input_id']=='W7a6b5a10076_G_080' and x['method']==m) for m in methods}
    from shapely.geometry import shape,LineString
    from shapely.ops import unary_union
    private=shape(impact['source_geometry']);current={};current_route_crossings={}
    for m in methods:
        prediction=read(ROOT/'data/predictions/W7a6b5a10076_G_080'/(m+'.json'))
        current[m]={state:unary_union([shape(c['geometry']) for c in prediction['surface']['cells'] if c['walkability_state']==state]).intersection(private).area for state in ('INFERRED_WALKABLE','RESTRICTED')}
        current_route_crossings[m]=sum(LineString(s['xy']).intersection(private.buffer(-1e-7)).length for q in prediction['routes'].values() for s in q['edges'])
    repaired=all(v['INFERRED_WALKABLE']<=1e-5 and v['RESTRICTED']>=gap['F0']['domain_private_overlap_m2']-1e-5 for v in current.values())
    result['status']='READY_FOR_GPT_AND_USER_REVIEW' if repaired else 'PARTIAL_WITH_EVIDENCE'
    result['known_policy_gap']={'input_id':'W7a6b5a10076_G_080','source_id':impact['source_id'],'private_area_m2':gap['F0']['domain_private_overlap_m2'],
        'R0_assumed_overlap_m2':{m:gap[m]['state_area_overlaps_m2']['INFERRED_WALKABLE'] for m in methods},
        'R0_actual_private_route_crossing_m':{m:sum(q['private_interior_m'] for q in gap[m]['routes']) for m in methods},
        'current_actual_private_route_crossing_m':current_route_crossings,
        'remaining_unverified_area_expansion_m2':{m:summary[m]['unverified_remaining'] for m in methods},
        'resolution':'REPAIRED_WITHIN_ORIGINAL_CAP_AFTER_VERIFIED_COUNT_CORRECTION' if repaired else 'NOT_FIXED_AT_REGION_BUILD_CAP; original results retained, no sample removed',
        'current_region_overlaps_m2':current,'fixed':repaired,'R0_archive':'delivery/OPEN_REVIEW_R0_PARTIAL.zip','R0_sha256':'2b5154e9e80afccd8a04901e7d3e81630dddbe7f50964c6f2ba005a5ce8b595b'}
    (ROOT/'runs/decision_numbers.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 排障默认可行域：本轮实测','', '**PARTIAL_WITH_EVIDENCE：主25任务全部运行，但1/25存在已取得权限面漏导；区域构建记账上界已达200，未越界重建。**','',
        '原始OSM已标private的停车面没有进入W7a6b5a10076_G_080的观测与共同约束。F0/F1错误开放128.388559平方米；M1-C保持UNKNOWN。两条新增路线没有进入该面内部，故不删样本、不把路线谎记为违规，也不把区域风险藏在26/33之后。当前F0/F1不能作为权限完整的默认规划器验收。','',
        '以下是原声明共同约束下完整25任务、41个原查询（33正例、8障碍对照）的实测；不等于修正权限层后的重跑。全部为已暴露同源地图诊断，北门8查询单列。','', '| 方法 | 面参考内覆盖 | 线参考内覆盖 | 有效条件到达／33 | 七面参考外扩张总量 |','|---|---:|---:|---:|---:|']
    for m,x in summary.items():lines.append(f"| {m} | {x['area_covered']:.2f}/{x['area_total']:.2f} m²（{x['area_covered']/x['area_total']:.2%}） | {x['line_covered']:.2f}/{x['line_total']:.2f} m（{x['line_covered']/x['line_total']:.2%}） | {x['valid_reached']}/33 | {x['off_reference_area']:.2f} m² |")
    lines+=['',f"其中F0/F1参考外总扩张有{gap['F0']['domain_private_overlap_m2']:.2f} m²现在已确认是权限冲突；余{result['known_policy_gap']['remaining_unverified_area_expansion_m2']['F0']:.2f} m²仍未证实，不能将全部参考外扩张都叫错或都叫未知。该私有面与隐藏正例参考交集为0，不改变上表参考覆盖分子。",'',f"F0相对M1-C新增{len(added['F0'])}条有效查询，失去{len(lost['F0'])}条；F1分别为{len(added['F1'])}和{len(lost['F1'])}。逐查询ID与原网基线见 runs/decision_numbers.json / query_outcomes.csv。仅在圈外原网绕行、使用局部假设区的新接通、仅替代原来已可达路线分别记录。",'', 'F0确实采用有效域减声明共同限制，无公园/铺装/靠路口的正向放行条件；此次失败发生在共同约束漏导。F1直接复用F0同一区域与无权图，无法靠代价修好这个区域权限缺口。有限代价保持可达集合，lambda1复现。面积覆盖增大首先说明模型允许的空间更大，不能单凭覆盖叫作通行证据变强。','',f"在F0/F1共同有效的{len(common)}个正例查询上，F0/F1累计假设段为{comparable['F0']['assumed_m']:.2f}/{comparable['F1']['assumed_m']:.2f} m，几何总长{comparable['F0']['length_m']:.2f}/{comparable['F1']['length_m']:.2f} m。代价单独计量，不能把加罚后的数值称为路线米数。",'', '## 北门与多端点','']
    for m in methods:
        q=north[m]['routes']['NORTH-DOOR'];lines.append(f"- {m}：到原出口 {q['status']}；几何长度{q['length_m']} m，原生{q['native_m']:.2f} m、已标面派生{q['mapped_area_derived_m']:.2f} m、假设{q['assumed_m']:.2f} m；广义代价{q['cost']}。8查询有效{sum(v['valid_reached'] for v in north[m]['routes'].values())}/8。")
    lines+=['','原 `node/6897145227` 坐标及 `entrance=exit` 不变，只评价到原出口外；不是入馆资格、真实门或现场同层通行的证明。完整S1前段图在区域冻结后才读。北门不在这块漏导私有面内，全程仅沿原foot=yes共享边，不穿停车内部；面限制与线性共边例外分别核验。','', '## 保留与限制','',f"四个原已知障碍任务的假设区重叠面积：M1-C={summary['M1-C']['known_obstacle_overlap']:.9f}、F0={summary['F0']['known_obstacle_overlap']:.9f}、F1={summary['F1']['known_obstacle_overlap']:.9f} m²。这不包含新增查明的128.39 m²权限区域冲突，不能用4/4零误放覆盖它。道路中心线没有实测宽度，不能保证所有假设区域都避开真实车道边界。",'', '保留F0作为透明诊断基线，F1作为同图减少假设路段的代价分支；当前不建议把任一组当权限完整的默认规划器。先修共同权限面导出并有界回归，才能重新判断是否采用；本轮不自动执行后续。真实权限、平台高差、未标围挡及当前开放状态仍未知。','', '图书馆等失败及零查询区域任务全部保留。源上下文和固定接口限制下的未连通，不等于现实无路。历史M1与M1-C的公共约束、纯几何代价和构图桥接见 runs/historical_bridge.csv。','', 'S1实际回归保留377原生片段，南门旧路线不变。旧成果、Git暂存、原始坐标、模型与参考未改。Geoapify无新请求；本轮恢复属于结构化OSM核心，不能写成托管服务自动补出了通行空间。','', f'区域构建记账上界{builds}/200（含失败修复与32次合成区域构建，非32个新夹具）；中断实际完成数不确定，按源阶段上界保守记账。最终ZIP重放单列。H80与40/160补充实验不执行；不越上限修这1个已知区域缺口。主动计算上限4小时，实际耗时与运行资源见逐run及STATUS。','', '## 审查与复现','', '作者检查、独立来源/几何/拓扑/防泄漏检查、实际浏览器交互及固定ZIP重放分别记录。独立审核确认的是复算与已列限制，不代表区域权限缺口通过验收；重放PASS只是复现原结果（包括反例）。最终ZIP后的独立解包/重放回执保存在delivery，避免循环自包含哈希。']
    if repaired:
        lines=['# 排障默认可行域：最终R1实测','', '**READY_FOR_GPT_AND_USER_REVIEW。主25任务、41查询完整；自然北门单列。R0已知权限漏导在同一Goal内实际修复，原错误版本保留。**','',
            '| 方法 | 面参考内覆盖 | 线参考内覆盖 | 条件到达／33 | 七面参考外未证实扩张 |','|---|---:|---:|---:|---:|']
        for m,x in summary.items():lines.append(f"| {m} | {x['area_covered']:.2f}/{x['area_total']:.2f} m²（{x['area_covered']/x['area_total']:.2%}） | {x['line_covered']:.2f}/{x['line_total']:.2f} m（{x['line_covered']/x['line_total']:.2%}） | {x['valid_reached']}/33 | {x['unverified_remaining']:.2f} m² |")
        lines+=['', f"F0/F1相对M1-C新增{len(added['F0'])}条有效条件查询，失去{len(lost['F0'])}条；固定33正例与8障碍查询分开。逐查询原ID、旧原网是否可达、是否利用局部假设、圈外长度与失败都保留。100%面覆盖来自更大的规划假设，不等于100%现实可走。",'',
            f"同一{len(common)}条可达正例中，F0/F1假设路段{comparable['F0']['assumed_m']:.2f}/{comparable['F1']['assumed_m']:.2f} m，几何总长{comparable['F0']['length_m']:.2f}/{comparable['F1']['length_m']:.2f} m。F1少用{comparable['F0']['assumed_m']-comparable['F1']['assumed_m']:.2f} m假设空间，多走{comparable['F1']['length_m']-comparable['F0']['length_m']:.2f} m。区域、无权图及接口完全相同，只改有限代价；lambda1复现F0，有限lambda不改变可达集合。广义代价不当作米制路径长度。",'',
            '## 真实反例及同Goal修复','',
            'R0源审查查明W7原始OSM已有private停车面，但旧观测与共同约束漏导。F0/F1错误开放128.388559 m²，且存在574个可进入的有向图分段；当时两个固定路线恰未使用该块，不能掩盖区域错误。R0固定ZIP、原7输出、07图和独立冷重放证明均保留，原25分母不改。','',
            '首次账本把合成调用静态估多2次。R0固定包实际冷运行及两独立角色核实：12组场景合同、14次fixture实例构造（同一围栏的无门/开门/锁门子状态），完整suite为28区域构建，加专项test11两次，共30；原32估计及原包不改，用追加-2账本更正。还剩2次真实额度，遂在本Goal补导独立private负约束，复用同一masked-observed已冻结纯M1缓存，仅新建M1-C/F0各一次，F1重用同图。没有增加预算、改参考、扩大阈值或换场景。','',
            f"最终三组将该源面在D30内的{gap['F0']['domain_private_overlap_m2']:.2f} m²全部列为RESTRICTED，默认可行重叠0；私有图分段574→0，两条原查询仍可达，没靠虚增到达数证明修复。新增guard仅源private面/原tag/ID/SHA，无隐藏目标节点、成员或正向footway例外。当前新增数据来源范围与原observed/query/ref/域/格网哈希逐项绑定。",'',
            '## 北门与原生线回归','']
        for m in methods:
            q=north[m]['routes']['NORTH-DOOR'];lines.append(f"- {m}：原出口外条件路线{q['length_m']:.2f} m；原生{q['native_m']:.2f}、已标面派生{q['mapped_area_derived_m']:.2f}、假设{q['assumed_m']:.2f} m；8个固定查询有效{sum(v['valid_reached'] for v in north[m]['routes'].values())}/8。")
        lines+=['', '原node/6897145227坐标和entrance=exit不变，不能推荐为入馆门。北门原3/8是通用接口采样丢掉已有查询点的工程缺陷；冻结后精确核源ID/坐标并按同1.6m整段检查绑定，恢复8/8，原区域及预选接口不变。该工程恢复不算F0新增隐藏区域能力。完整S1图在freeze后读；缺level仍未知。', '',
            '北门全程只沿原foot=yes步道和私有停车面共有的5.634348m精确边界；停车内部0，不是通配foot=yes开放私有区域。5009源对象及新增权限类全路径审查、原OSM点/登记面派生点分层核验均有回执。S1实际六clip回归保留377片段/754有向弧，南门旧路线1067.371390m未变，旧CSV/GeoJSON逐字节一致。','',
            '## 结论与边界','', '保留F0作为透明默认假设基线、F1作为同图偏好原生通道的有限代价分支。本轮说明更多局部缺标空间可用于条件规划，并揭示其依赖约束导出完整性；F1不能代替障碍和权限检查。四个原已知障碍对照及补查权限类当前未见明确冲突，不能解释成对地图漏标障碍安全。','',
            '仍有约一万平方米参考外空间未经通行证实。缺失高差、开放时间、公众许可、未标围挡与真实门身份保持未知；道路只采用中心线拓扑限制，没有精确车道宽度，不能保证同侧空间都避开车道。所有样本已暴露，是同源配对诊断，不是新盲测、通用入口识别或完整导航。','',
            f'最终科学区域构建记账上界{builds}/200（含原失败、中断阶段上界、实际30次合成构建；旧32估计经独立证据追加更正）。H80与40/160补充未跑。最终ZIP实际六样例重放另计，含4原控、W7修复、北门及12组合成测试；实际次数从trace算，不重置研究预算。','',
            '旧M1原字节和25任务桥接保留：M1-C共享约束、统一几何代价和共用构图；不冒称原M1原样性能。W7与北门使用同观测纯分类surface缓存，不称本轮新分类器运行；其余原实际预测不变。旧数据/模型/结果与两个Git暂存保持只读，无新地图/API、训练、费用或新入口。标签文档核对两页单列，不冒称零网络。','',
            '作者、独立数值/结构/来源/防泄漏、实际浏览器及固定ZIP复验分别留痕。内部PASS只说明已列输入和程序行为通过，不替代GPT与用户自然语言验收。到本Goal停止。']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    registry=[]
    for r in executions:registry.append({'input_id':r.get('input_id'),'panel':r.get('panel','SUPERSEDED_OR_INTERRUPTED'),'region_builds':r['region_builds'],'wall_s':r.get('wall_s'),'code_sha256':r.get('code_sha256'),'status':r.get('status','SUPERSEDED_NOT_ACCEPTED' if r['superseded'] else 'COMPLETED'),'receipt_path':r['registry_path']})
    with (ROOT/'runs/experiment_registry.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(registry[0]));w.writeheader();w.writerows(registry)
    print(json.dumps({k:v for k,v in result.items() if k not in ('methods','added_vs_M1_C','lost_vs_M1_C')},ensure_ascii=False))
if __name__=='__main__':main()
