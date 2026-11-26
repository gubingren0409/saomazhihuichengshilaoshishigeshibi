"""Run independent checks and emit scoped review; no author PASS is consumed."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main(args):
    root=args.root.resolve()
    rows=[]
    jobs=[("metrics",["src/score_free.py","--require-main"]),("geometry_graph_isolation",["src/audit_free.py","--graphs","--require-main"])]
    jobs.extend([("historical_common_bridge",["scripts/review_historical_bridge.py","--require-main"]),
                 ("budget_surface_cache",["scripts/review_budget_cache.py","--cache","data/classifier_cache/NORTH_160.json"])])
    if args.source_dir:
        jobs.insert(0,("raw_guard_sources",["src/audit_free.py","--guards-only","--source-dir",str(args.source_dir.resolve())]))
        jobs.insert(1,("closed_access_source_scope",["scripts/audit_closed_access_domain.py","--source-dir",str(args.source_dir.resolve())]))
    jobs.append(("source_known_access_graph_impact",["scripts/review_known_access_graphs.py"]))
    for name,command in jobs:
        result=subprocess.run([sys.executable,"-X","utf8","-B",*command],cwd=root,capture_output=True,text=True,encoding="utf8")
        (root/"audits"/("independent_"+name+".log")).write_text(result.stdout+result.stderr,encoding="utf8")
        rows.append({"check":name,"command":[sys.executable,"-X","utf8","-B",*command],"exit_code":result.returncode,
                     "receipt":"audits/independent_"+name+".log"})
        print(name,"PASS" if result.returncode==0 else "FAIL",flush=True)
    passed=all(v["exit_code"]==0 for v in rows)
    scope_path=root/"audits/closed_access_D30_independent.json"
    gaps=json.loads(scope_path.read_text(encoding="utf8")).get("eligible_independent_area_assumed_overlaps",[]) if scope_path.exists() else []
    report={"status":"PARTIAL_WITH_EVIDENCE" if passed and gaps else "PASS_SCOPED" if passed else "REQUIRES_REPAIR","reviewer":"/root/free_evaluation",
            "review_identity":"Separate actual agent execution context; did not author classifier, graph builder, solver or common constraints",
            "timestamp_local":datetime.now().astimezone().isoformat(),"checks":rows,"unresolved_common_constraint_gaps":gaps,
            "numerical_and_structure_checks_passed":passed,
            "limits":["Same-source exposed diagnostic, not blind or field navigation validation",
                      "Whole new local graph and actual route segments; old full natural graph is verified through input hashes and used-edge provenance, not rerun independently as a city network",
                      "Only explicit mapped constraints can be checked; unmapped barriers, current public access and levels remain unverified",
                      "Application input audit is not an OS sandbox",
                      "Human natural-language acceptance is pending; this review does not substitute for it"]}
    (root/"audits/free_review_receipt.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    status="数值/结构核验通过，但源权限共同约束存在未修复缺口：PARTIAL_WITH_EVIDENCE" if passed and gaps else "通过本记录所列内部核验" if passed else "发现待修复项，不能据此宣布通过"
    md=f"""# 独立技术复核

审查者：`/root/free_evaluation`，独立实际代理上下文；未编写主分类器、路由器或共同约束提取函数。

状态：**{status}**。执行时间：{report['timestamp_local']}。

## 实际核验

"""
    for row in rows:
        md+=f"- {row['check']}：exit={row['exit_code']}，实际记录 `{row['receipt']}`。\n"
    md+="""
固定输入字节、30米域、1米格网和原查询分母由原封包清单对照。默认区域由独立Shapely几何运算检查是否等于有效域减共同限制；F0/F1区域、接口及无权图身份和有限代价可达集合分别对照。区域覆盖、参考外未证实扩张、路线坐标、逐段长度、原生有向边来源、终端及共同障碍/道路政策由独立代码重算。拒读探针及先冻结区域后读查询检查实际读取事件。

完整JSON回执给出本轮到底检查了哪些输入、图段、路线和有限权重；不能把抽样、源哈希或局部图检查扩大描述成全市原始拓扑独立重建。

北门沿用同一观测字节的历史M0/M1纯区域缓存，W7修复沿用同一masked观测首跑的纯M0/M1缓存；缓存均不含旧路线、query、reference、read_log或features。原分类源码、配置锁、区域cells/hash及旧日志“先冻区域后读query”独立核查。W7最初实际分类已执行，本次只是重新导入独立负面源约束后各新构建M1-C/F0一次；不能称R1重新执行25个分类器或新盲测。中断上界与合成计数更正均追加记录，不改写旧收据，不重置预算。

北门第一次路由只有3/8可达，5个原可见端点被16个通用接口截断，并非新障碍或区域被限制。修复只在原query读入后，为精确存在于同一可见源图且层级/权限兼容的端点提供同容差整段终端绑定；它不产生新门，不改原角色/坐标。原3/8结果保留，原区域与无权图不变。此次路由续算实际加载整份旧prediction作冻结元数据及历史对账，旧路线未传入新router；继承的分类读取日志与实际resume日志分开核查，不能冒称本次重新触发原来的拒读探针。最终纯输入ZIP重放另核修复无需旧路线。LOCAL基线原合同未计算，不把它当作原生不可达，也不把自然多端点到达称为隐藏参考恢复。

## 发现与修复的承接

首轮发现负例水体的格片分割产生微小假设区域交叠：`free_geometry_defect_R0.json`保留原SHA和具体格片；受影响结果应修复后重新构建，不能通过提高指标阈值隐去。该记录是历史缺陷，最新复核结果见当前回执，不把旧失败覆盖成当时通过。

R0来源复核发现真实缺口：W7漏导原源已登记private停车面，F0/F1曾开放其内部128.39平方米，图中574条有向片段涉及其内部。原固定两条查询恰好没用这些片段，不能掩盖区域违规。R0封包和PARTIAL结论完整保留。其后最终ZIP冷计数实证合成全套为14次fixture/28次区域构建，原15/30是手估错误；加单项2后实际研究合成为30，研究上界因此是198而非200。独立核对后仅使用余下2次在同Goal修复W7的共同负面源导出：同原observed和分类缓存，同一完整private面给三组，只新构建M1-C/F0各一次，F1仍同图代价。未改cap、参考、分母或旧R0结果。最新是否修复以`closed_access_D30_independent.json`及`source_access_graph_impact.json`实际重算为准，不能因复现PASS就省略权限门禁。

北门另一处7/8评分争议来自把闭合private停车面外环误当墙。已核foot=yes步道沿共享原节点的精确边界走，停车面内部穿越0；仅允许该具体原生共边，私有内部及真实非闭合限制线继续检查，无native或foot=yes通配豁免。R0停车区域违规与北门边界解释是不同问题，两者分别存证。

## 未核验范围

这批参考已暴露，属于同源受控配对诊断。未核验现实中漏标障碍、公众许可、实时开放和全部同层关系；已知4个障碍控制服从约束不能证明未知空间安全。北门仍是原`entrance=exit`，到门外路线不等于可以入馆。完整自然案例旧前段图按哈希和实际采用边的方向、坐标核验，本记录不声称重新独立构建全市网络。最终ZIP解包复放有单独收据；未生成收据前不宣称通过。用户自然语言验收仍待完成。
"""
    (root/"audits/INDEPENDENT_REVIEW.md").write_text(md,encoding="utf8")
    (root/"audits/LEAKAGE_REVIEW.md").write_text("""# 输入与评价隔离复核

独立角色：`/root/free_evaluation`。原始参考只由评价器读入。实际worker开放日志检查observed/common guards/config在区域冻结前读取，query和自然案例完整前段图在冻结后读取；reference和提前query拒读探针必须实际触发。F0/F1复用相同冻结区域和无权图，参考不能决定障碍、候选域、权重和接口。

共同道路补导逐条从原始OSM节点序列重建后，只按固定观测上下文裁切；禁止把隐藏目标或成员way原样导回，也不使用参考形状刻出孔洞。独立道路与隐藏路径共享坐标时，独立道路几何可保留，其隐藏节点ID、成员数组不会被序列化为预测输入。原v1过度删除共享节点道路的版本留存，正式以v2来源审查回执为准。

这里是应用层文件打开审计和已记录几何依赖检查，不是操作系统隔离或未知事实的证明。可执行状态和覆盖数量见`free_review_receipt.json`、`free_input_identity.json`、`free_guard_source_audit_v2.json`和`free_independent_checks.json`。未完成或失败不得用本段说明替代通过记录。

自然北门另允许显式标记的旧observed-only classifier surface缓存；其observed、源码及配置绑定必须相同，且纯surface载荷中不能有旧查询/路线/参考。缓存身份与本轮新分类执行分开，旧表面在历史阶段的冻结先于query；当前MC/F0仍在当前query/full-route-graph之前冻结。实际载荷审查与预算阶段证明见`free_budget_cache_review.json`，不把这一缓存通道推广到受控隐藏目标。

北门随后ROUTE_ONLY_RESUME是断点修复角色，确实读取旧prediction整份元数据，其范围不伪装成observed-only分类器或操作系统沙箱。原分类阶段拒读日志是继承证据，本次实际read_bytes/GZIP日志单列，区域/图/固定query的原哈希及父prediction哈希逐项核对。独立源码检查确认旧routes只用于历史可达数对账，新绑定只使用可见源图精确ID/坐标与整段约束。最终ZIP中从纯observed和surface-only缓存重放北门，才是新增无旧路线输入的复验。
""",encoding="utf8")
    if not passed:
        raise SystemExit(1)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--source-dir",type=Path)
    main(p.parse_args())
