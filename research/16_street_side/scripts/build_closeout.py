"""Assemble bounded-round explanation from actual saved evidence, without solving."""
import datetime as dt
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))

def main():
    t=read('results/trial_summary.json')
    assert t['formal_attempts']==24 and t['repair_retests']==6
    now=dt.datetime.now().astimezone().isoformat()
    brief='''# PG1有限续执行：先看到了什么，仍缺什么

**旧交付链COMPLETE；本轮方法接入准备度PARTIAL_WITH_EVIDENCE。** 三个预锁定窗口的有界拓扑小试已经实际运行，物理侧向位置与同侧接口仍未证实。原38文件和commit保持；首次公开、视觉验收、分组冻结没有自动通过。

1. **先看真实地图。** 打开[index.html](index.html)，对照同一源图上的R0道路轴、R1原生/标签侧向表示和R2条件侧道。可点选对象、切换六个固定查询、开关六层并导出查询与视野。页面显示真实保存结果，不声称新求路。旧六场景由53511服务从固定ZIP只读展示，未恢复旧工作目录11个缺失图件。
2. **新候选做到了什么。** 原生步道控制在三个变体下保持源路径；安福路的明确侧别标签可建立逻辑同侧通道；兴国路缺标段在R1没有端点，在R2可建立条件同侧通道。R0两次把左右两侧当同一轴线点的零长度结果不是过街成功，R1/R2没有相应依据时不互通。不强制围成街区环。
3. **还不能说什么。** 4米偏移只是SCHEMATIC。没有可靠路宽，不能证明侧向净空或精确步程。真实三个窗口没有准入的侧道过街接口，过街及多路口隔离仅有合成核验。原生步道源ID保留、明确separate标签不重复派生已检查，但未有road↔独立步道关联，不能证明不存在空间上的平行重复；同侧广场/步道接口仍NOT_VERIFIED。没有新完整到门业务路线，也不将候选提升默认方法。
4. **为什么需要继续这个方向。** 只读核对四条旧业务任务×F0/F1的8份真实结果，全部用过道路轴：博物馆三任务轴长约52.17、125.56、116.81米，图书馆约116.92米。它们是源轴几何使用量，不是危险率或真实人行道步程；全库道路比例不能替代此核验。
5. **数据准备分模块推进。** 纽约两候选已有建筑和人行面，可检源到图一致性，并为道路侧别/面线衔接准备部分输入；仍缺道路线、原生关系和独立参考。Helsinki当前保留建筑，Kallio仅元数据。没有门坐标不否定B/C研究，有建筑也不代表已知门整链就绪。所有候选仍EXPOSED，不冻结独立组。

固定主矩阵18格：R0四个非零连通、两个零长度别名；R1三个连通、一个断开、两个端点不可用；R2四个连通、两个断开。这些是图内机制结果，不是物理通行成功率，不能单凭4/6对3/6宣布优胜。

实际执行首跑18次+恢复R0冻结代价的6次修复重测，共24次尝试、22次Dijkstra；2次端点不可用未调用求解器。合成两轮19个用例、4次SSSP。旧8次成本探针未重跑。R0成本修复后缺标同侧的源轴参考代价从530.617恢复265.309；R2假设侧道F1代价仍530.617，均不解释为精确步程收益。没有新数据、API、费用、训练、Push或Blind。

作者检查、独立技术核验、GPT审核与用户视觉判断分开。审核记录见reviews/；独立角色检查不代表实际人行通行验证。

**建议保留R0默认。** R1/R2只作为开发候选。下一次若获批准，应优先补足道路—原生步道对应关系、明确侧别与面线接口参考；未执行补取方案见contracts/next_acquisition_proposal.md。本轮结束后等待GPT与用户判断。
'''
    (ROOT/'DECISION_BRIEF.md').write_text(brief,encoding='utf-8')
    # A lightweight offline explanation page; map remains the primary interaction.
    paragraphs=[]
    for p in brief.strip().split('\n\n'):
        if p.startswith('# '):paragraphs.append('<h1>'+html.escape(p[2:])+'</h1>')
        else:paragraphs.append('<p>'+html.escape(p)+'</p>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PG1有限续执行简报</title><style>body{max-width:1000px;margin:38px auto;padding:0 24px;font:17px/1.85 system-ui;background:#fcfaf7;color:#183d38}h1{font-size:30px}p{white-space:pre-wrap}a{color:#236b7b}</style><nav><a href="index.html">打开真实地图对照</a> · <a href="DECISION_BRIEF.md">Markdown原文</a> · <a href="reviews/independent_review.md">独立审核</a></nav>'''+''.join(paragraphs)+'</html>'
    (ROOT/'decision.html').write_text(page,encoding='utf-8')
    exp='''# Experiment Brief

本轮仅在已暴露上海开发材料上验证街区侧拓扑候选；来源为六份冻结OSM裁片，按原生步道/正向侧别标签/缺标普通道路三层锁定博物馆周边、安福路、兴国路三个320m窗口，每窗两查询。窗口在新图与新结果前锁定，不据结果选样。

R0复用旧逐段准入和原native成本，保留SHARED_STREET_ASSUMPTION事实身份；R1保留原生步道并依明确侧别标签派生逻辑侧道；R2仅对符合普通地面道路及既有权限/层级/准入条件的缺标轴增加条件侧道。道路两侧用road_id+side+level独立编码；有歧义的多道路过街节点不把各侧自动合并。不假设新的过街，不强制闭环。父方法完整面穿行、精确接口和30m门前F0域均未修改或重建。

主成本固定F1；同时保存F0/F1边权。新假设侧道F1=2×F0；源轴参考长度只作逻辑成本代理。旧R0源native轴的原代价不因证据名SHARED而被新加惩罚。没有调参搜索。

最终结果、原首跑、修复回归、逐边来源与证书分别见results/、audit/experiment_registry.jsonl及reviews/。24次正式尝试中的6次为R0成本恢复，最终配对矩阵仍18格；6次状态和边序列均未改变，仅一项代理代价恢复。原生控制路径约266.103m为地图折线长度，不是实走验证。没有推断真实门，没有移动登记点或将exit当入馆入口。

结论仅为拓扑机制可执行及其限制：R2能让缺标道路同侧条件连通，R1/R2能保留无过街时的侧别断开；没有证明完整街区侧向网与广场/已知门整链，也没有精确步程改进或跨域泛化证据。原生源身份不丢失，但空间平行重复的消解需要道路↔步道关系参考。

候选合同20行、既有14份源/许可证据均作只读核验；无新增取得的数据。下一次小规模补取仅为未执行提案。
'''
    (ROOT/'EXPERIMENT_BRIEF.md').write_text(exp,encoding='utf-8')
    process='''# 实际执行与修复记录

- 2026-11-13 03:17+08开始只读核验；权限等待期间不编造文件或实验。03:33确认可写，创建独立续执行目录，从旧bundle克隆本地隔离分支，旧Git工作区不改。
- 对固定输入和旧Foundation ZIP、实际包外回执及依赖复验输出核验；补写旧delivery/FINAL_STATUS.json和RECOVERY_REPORT.md。历史PENDING及blocked保留；Bad Request根因UNKNOWN。旧工作root11个地图/浏览器文件缺失与封存包证据分开记录，不恢复原位置。
- 实际角色：root负责恢复、旧业务路线使用核验、集成、服务、版本和封包；street_trial实现与执行小试；data_visual核验模块合同及制图；resume_review独立读源、证书/反例和交付检查。未把作者自查称作独审，也未虚构用户验收。
- 源结构锁定三个窗口后，先9项合成检查，再运行18次主尝试。发现潜在多路共用过街节点误合并，增加歧义保护及反例；实际9张图不变，无新正式查询。第二轮10项合成检查通过；共19项、4次合成SSSP。
- 纠正报告中把R0道路轴几何长度称为physical_route_length的字段，保留首跑注册表；示意/轴线不再报告真实步行长度。权限分类词表与冻结原规则对齐；15个清单记录重新分类，实际九图未变。
- 作者与独立角色确认R0共享轴成本曾被错误加倍；从真实旧源码/路线核对后恢复原成本，仅用预留6次R0修复重测。首18条与首图不删，其他12项R1/R2不重跑，总正式24次、实际Dijkstra22次。没有把修复说成新方法收益。
- 浏览器检查工具首先遇到缺失的Playwright捆绑浏览器，改用本机Chrome，没有下载。随后修正测试脚本的窗口选项值和未绑定比例尺对象定位；它们是测试脚本问题。最终实际检查三窗口六查询、图层、缩放、证据导出及离线打开。页面不触发求解器，不以静态图冒充新计算。
- 新只读服务53511实测HTTP200；旧53501拒绝连接，没有声称旧服务仍在线，也没有停止旧/无关进程。新服务从固定ZIP只读展示六场景，缺失工作副本不被静默恢复。
- 后续完成源码SHA/本地Commit绑定、作者与独立审核、固定ZIP解包核验。封包回执记录实际覆盖与未核验项；公开Push、许可选择、新取数、盲集及下一阶段均停止。

精确时间、输入/代码/图哈希、成本变化与实际调用见audit/、results/各修复回执及最终独立解包记录。本记录保留真实失败，不根据Bad Request补造因果。研究预算保守从03:17计，不因权限恢复重置。
'''
    (ROOT/'PROCESS_RECORD.md').write_text(process,encoding='utf-8')
    status=read('STATUS.json')
    status.update({'status':'PARTIAL_WITH_EVIDENCE','old_delivery':'COMPLETE','bounded_topology_execution':'COMPLETE_WITH_REPAIRS',
        'physical_side_interface_readiness':'NOT_VERIFIED','current_stage':'FINAL_REVIEW_AND_PACKAGE',
        'last_checkpoint_at':now,'route_budget':{'main_max':18,'repair_max':6,'executed':24,'actual_dijkstra':22},
        'trial_counts':t,'default_method':'R0_NOT_UPGRADED','G0_PUBLICATION':'PENDING_USER_APPROVAL',
        'G1_VISUAL_ACCEPTANCE':'PENDING_USER_REVIEW','G2_SPLIT_FREEZE':'NOT_APPROVED','PARENT_GOAL_COMPLETE':False})
    (ROOT/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'written_at':now,'status':status['status'],'formal_attempts':24},ensure_ascii=False))

if __name__=='__main__':main()
