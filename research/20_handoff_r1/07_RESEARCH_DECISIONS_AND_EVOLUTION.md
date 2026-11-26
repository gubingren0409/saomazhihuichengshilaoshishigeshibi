# 研究决策与版本演化

以下是记录中真实发生的取舍与修正，不是替团队作新的研究决策。

|决定|实际依据|后续处理|证据|
|---|---|---|---|
|双路径保留|R3本地/托管差异存在，但状态、目标及内部引擎不等价，缺独立路线真值|保留本地OSM与Geoapify，不宣布赢家|[R-OSM-GEOAPIFY-PILOT-R3](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R3)|
|从严格原线转向合法面派生|旧R4要求每条新边都有同位置原线，新增0不能证明面无用|REV1允许已标步行面内计算边；后来FULL_FACE替代主要边缘带限制|[R-OSM-GEOAPIFY-R4-REV1](evidence/claims.html#R-OSM-GEOAPIFY-R4-REV1)|
|草地语义修复|背景草地覆盖不应删除有效原生步道|保留S修复；不是开放整片草坪|[M-S377](evidence/claims.html#M-S377)|
|连接线与区域恢复分开|北门N2围预定线的允许域不等于端点无关区域|R3建立区域级状态，低覆盖率原样报告|[M-R3AREA](evidence/claims.html#M-R3AREA)|
|上下文与评分域分开|扩大观察不等于扩大成果分母，局部遮蔽不能删掉所有合法way延续|固定30m/1m格网，分别报告遮蔽任务与上下文；仍非新盲测|[M-CONTEXT](evidence/claims.html#M-CONTEXT)|
|缺标规划允许与事实分开|正向证据过保守，但无标签也不是真实可走证明|F0/F1明示假设；同图有限代价，不称风险概率|[M-FREE-REACH](evidence/claims.html#M-FREE-REACH)|
|保留权限漏导错误|旧F0把128.39m² private面漏导，路线未穿它也不代表区域正确|同Goal修复后限制恢复，旧反例标SUPERSEDED|[M-FREE-PRIVATE](evidence/claims.html#M-FREE-PRIVATE)|
|对象、接口和业务收益分开|补82面、局部3/8→5/8而四业务路线不变|真实走廊/分量/替代证书解释，不为变短放宽限制|[M-DIAG-82](evidence/claims.html#M-DIAG-82)|
|侧别候选不自动升级|缺宽度只支持拓扑，R0零长度是侧别合并而非过街成功|保留R0默认；R1/R2候选等审核|[PG1-I06](evidence/claims.html#PG1-I06)|
|正式承认地图场景绑定错误|上轮native320m窗不含实际Museum|R2以真实馆体/原门/道路定窗，旧诊断不改成新门路线|[PG1-I10](evidence/claims.html#PG1-I10)|

## 关键版本身份

- PILOT-R1原OPEN_REVIEW未完成，由AB_COMPLETION补齐；旧状态不追认为当时通过。
- 北门N2仍为假设连接，后续区域恢复研究不反向提升它的证据等级。
- FREE-SPACE的R0权限漏导图是旧反例；最终修复版与旧PARTIAL不同。
- E2E首包存在计时日志覆盖故障；真正最终包是R1_FIXED，加载时切用途/方法的UI修复是其后独立增量。
- FULL_FACE最早149.0338m诊断不作最终南门长度；最终为148.8631m。完整比较见原指标。
- 街区侧R0初始6次代价错误已以6次重测更正；最终主表18行，历史尝试24行全部保留。
- VISUAL_REPAIR-R1的native馆体解释已被RECONSTRUCTION-R2正式纠正；旧图在图册有历史/错误标记。

各版本精确固定包SHA与嵌套位置见 [固定包版本清单](evidence/ARCHIVE_INDEX.csv)。没有找到NAV-END-V1/V2原固定审查ZIP，但现有报告、指标和图件已逐文件哈希；这不等于已经核验它们的原封包。
