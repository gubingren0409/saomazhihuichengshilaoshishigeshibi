# 研究历程与可核验时间线

日期优先采用运行字段或明确的原报告日期。ZIP统一归档时间不冒充实验时钟；Context轮精确启动时刻未核验。本轮只整理历史，未产生新的路线实验。

## 前期证据背景

2026年10月的Goal9A验收汇总了NYC关系匹配、N1/A3规范化、P1条件几何路径，以及Southampton/Gapwise入口登记参考恢复和质量边界。后续NYC同域实测区分“能构造条件链”和“全段有来源支持”，再开展跨来源接入比较。这些先导结果仍保留原任务身份，未混入上海指标。

## NAV_END_V1

时间：2026-11-08T15:58:31.453612+00:00 — 2026-11-08T16:19:24.426061+00:00 (UTC；北京时间+08:00)；时间依据：`execution_trace.jsonl#/utc min,max`。

问题：开放地图截图能否支持已知入口接近、未知入口候选和条件几何路径？。

起因与实际变化：商业截图采集未获许可，先形成可追溯开放地图截图工具和原型。 M0/B1来源几何；M1/B2图像解析+给定入口；M2/B3图像解析+K3候选。

结果与后续决定：实际240张主库截图；M1/B2来源几何独立通过23/28；M2/B3到自选候选独立通过208/240；入口Top1 9/28、Top3 16/28。 作为后续V2回归；旧留出已暴露，不可在PG1重新称盲测。 [R-NAV-END-V1](evidence/claims.html#R-NAV-END-V1)

## NAV_END_V2

时间：2026-11-09T05:12:10.610197+00:00 — 2026-11-09T05:26:46.076594+00:00 (UTC；北京时间+08:00)；时间依据：`execution_trace.jsonl#/utc min,max`。

问题：跨样式解析、候选排序和通路约束能否改进V1？。

起因与实际变化：V1通路缺证据、微小穿楼与图式依赖需要分开处理。 C0终端避障修复；A1-r2自适应图式；G5候选规则；严格/偏好通路。

结果与后续决定：C0旧已知任务通过25/28；新样式A1-r2已知19/24，未知24/48；新增建筑确认C0和G5均登记参考联合2/6，没有选择提升。 默认保留K3首可达；G5未在新增确认获得收益；商业私有图另包不进入同学包。 [R-NAV-END-V2](evidence/claims.html#R-NAV-END-V2)

## OSM_GEOAPIFY_PILOT_R1

时间：2026-11-09T17:55:38+08:00；STATUS.start_local；时间依据：`09_AB_COMPLETION_RESULTS.md`。

问题：本地OSM与Geoapify能否同场景同尺度取得地图和步行结果？。

起因与实际变化：需要合法公开图面与可核验的地图/路线比较。 Geoapify原静态图及归档walk响应，同合同两视野。

结果与后续决定：最终2/2双侧视野已补齐；本地入口请求0/1，诊断线1416.719m；Geoapify接口964m、独立折线961.819m，末端仍距南门54.986m。 保留两路，进入路线差异诊断；现场0。 [R-OSM-GEOAPIFY-PILOT-R1](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R1)

## OSM_GEOAPIFY_PILOT_R2

时间：2026-11-09T19:14:44+08:00；STATUS.start_local；时间依据：`01_ROUTE_DIFFERENCE_DIAGNOSIS.md`。

问题：为什么起点不同路，两条线都离南门约55m？。

起因与实际变化：用户已给实际视觉评分，图面质量和路线质量需要拆开。 同源拓扑/方向/广场边界及折线分段只读诊断。

结果与后续决定：本地黄陂北路轴线未纳入保守步行图；南广场可见但内部未建可路由边；本地与托管末点相差0.038m；用户总分42/45与43/45、总体相同。 进入多建筑双路径诊断；保留原始人工反馈不重评分。 [R-OSM-GEOAPIFY-PILOT-R2](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R2)

## OSM_GEOAPIFY_PILOT_R3

时间：2026-11-09；01_SOURCE_AND_PERMISSION_AUDIT.md核验日期；时间依据：`03_PAIRED_COMPARISON_RESULTS.md`。

问题：扩展不同建筑后，两条路径是否存在足以淘汰一方的明显差异？。

起因与实际变化：单博物馆不足说明不同城市建筑形态表现。 新增5栋非校园：武康、上海中心、新世界城、图书馆、展览中心；同尺度双路径。

结果与后续决定：新增本地返回4/5，托管5/5；10/10视野同尺度；25/25HTTP200；新增请求目标仅1/5具原生登记入口，其余代理/未知。 INCONCLUSIVE，保留双路径；下一步研究开放空间接入。 [R-OSM-GEOAPIFY-PILOT-R3](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R3)

## OSM_GEOAPIFY_R4

时间：2026-11-10T10:33:28+08:00；STATUS.started_asia_shanghai；时间依据：`04_EXPERIMENT_RESULTS.md`。

问题：开放空间边缘如何接到步行图？。

起因与实际变化：R2/R3暴露广场内部缺边与跨分量问题。 B1有源线边缘；B2有源线内部；B3多登记门。

结果与后续决定：B1、B2新增均0，25已在B0、8拒绝；严格登记门B0/B1/B2均1/2；B3不适用。 后续R4-REV1明确允许来源步行面内计算边，本轮作为受限规则负结果保留。 [R-OSM-GEOAPIFY-R4](evidence/claims.html#R-OSM-GEOAPIFY-R4)

## OSM_GEOAPIFY_R4_REV1

时间：2026-11-10T11:33:00+08:00；STATUS.started_asia_shanghai；时间依据：`RESULTS.md`。

问题：已标步行面可否生成绕障碍的边缘计算图？。

起因与实际变化：旧R4过严原生线规则导致0新增，需真正利用来源步行面。 3m边缘带0.5m网格8邻域，保留内环障碍；1/5m敏感性、移除派生层消融。

结果与后续决定：主设置155226计算边记录、310448有向弧；南3/3条件接通但仅2/3平面清洁；最短有效1067.37m；北仍缺7.9522m。 作为边缘带冻结历史基线；后续草地修复与FULL_FACE继续修订。 [R-OSM-GEOAPIFY-R4-REV1](evidence/claims.html#R-OSM-GEOAPIFY-R4-REV1)

## OSM_GEOAPIFY_R4_NORTH_ACCESS_R1

时间：2026-11-10T13:30:00+08:00；STATUS.started_asia_shanghai；时间依据：`04_RESULTS.md`。

问题：北exit约7.95m缺口加空间约束能否比直线更合理？。

起因与实际变化：北出口在步行面外，需保留原坐标、exit与未知事实。 N2出口12m范围×接入方向半宽2m条带，裁公园、扣障碍，可见图。

结果与后续决定：N2允许域31.80m²，选线与N1同7.9522m；全程1245.77m，门残差0；楼层与通行证据仍未知，假设身份未升级。 保留假设连接；后续R2/R3将研究对象改为独立候选/区域生成。 [R-OSM-GEOAPIFY-R4-NORTH-ACCESS-R1](evidence/claims.html#R-OSM-GEOAPIFY-R4-NORTH-ACCESS-R1)

## WALKABILITY-R2

时间：2026-11-10 14:36+08；时间依据：`STATUS.json:started_asia_shanghai`。

问题：修复背景草地误杀已标步道，并比较缺标连接推断。

起因与实际变化：北门既有前段被草地面排除，7.95m末段缺口仍存在 S1保留有效原生步道；I2独立搜索域多接点受约束推断。

结果与后续决定：377原生片段/754有向弧恢复；北前段1237.81→1166.10m；I2自然完整条件1168.98m，I1为1174.05m；受控I2 5/14，I1 3/14 保留S修复；I1简单基线和I2条件原型；外审/用户待验收 [R-WALKABILITY-R2](evidence/claims.html#R-WALKABILITY-R2)

## WALKABILITY-R3

时间：2026-11-10 21:01:07+08；时间依据：`STATUS.json:began_client`。

问题：真正区域级四态恢复能否支持多个外围接点，而不围旧直线buffer。

起因与实际变化：上一轮I2主要输出连接线，不能回答区域范围与复用 独立于终路端点冻结30m四态格网区域，再接多个接口并求路；消融区域图/上下文。

结果与后续决定：北门推断180.96m²，165.05m²位于旧直线1m缓冲外；自然条件1166.92m；主面覆盖18.88/3996.53m²(0.47%)；区域19/41路线，I-LINE29/41 保留S与线基线；I-REGION仅可审查原型 [R-WALKABILITY-R3](evidence/claims.html#R-WALKABILITY-R3)

## WALKABILITY-R4-CONTEXT

时间：R3之后、FREE-SPACE-R1之前；精确启动时刻NOT_VERIFIED；时间依据：`固定ZIP成员统一日期2026-11-11只作归档字段，非精确实验时钟；源版本链确证先后。`。

问题：看40/80/160m上下文、只补30m固定域，能否改善区域恢复。

起因与实际变化：强遮蔽误删整个way，放大观察可能把答案重新漏入 修订合法外段保留、防泄漏；M1显式使用外围拓扑和临街关系；固定1m格网/评分域/参考。

结果与后续决定：G80面覆盖M0 0.77%→M1 0.92%；线覆盖6.25%→16.22%；两者均20/33正例到达；M1使用推断替代路径2→4 M0保留简单基线，M1条件比较，不晋升通用方法 [R-WALKABILITY-R4-CONTEXT](evidence/claims.html#R-WALKABILITY-R4-CONTEXT)

## FREE-SPACE-R1-FINAL

时间：2026-11-11 13:39:29–15:46:53+08；时间依据：`delivery/FINAL_STATUS.json:started_at/updated_at`。

问题：排除已知约束后默认允许缺标局部空间，是否改善条件规划。

起因与实际变化：正向证据区域恢复过于保守，仍未知的空间不自动禁止研究性规划 F0默认可行；F1完全同区域节点边接口，仅假设段有限代价；修复漏导private负约束。

结果与后续决定：M1-C20/33，F0/F1同26/33，新增6失去0；面覆盖100%来自假设扩张；F1同26查询少24.65m假设、多4.67m几何 最终R1修复版保留F0透明基线/F1有限成本分支；用户/GPT待验收 [R-FREE-SPACE-R1-FINAL](evidence/claims.html#R-FREE-SPACE-R1-FINAL)

## KNOWN-ENTRANCE-E2E-R1-FIXED

时间：2026-11-11 18:34:45+08起，最终回执另列；时间依据：`STATUS.json:started_at + delivery/ACTIVE_REVIEW.json`。

问题：把已有机制统一成可提交新请求、实际求路的CLI/HTTP/APP。

起因与实际变化：静态图册与旧JSON回放不构成可操作原型，七失败需逐项收敛 统一约束/原生/已标面/F0/F1/端点，禁路线答案缓存；通用接口修复；真实页面与CLI/HTTP验收。

结果与后续决定：8/8合法应用返回路线；主M1-C20/33、F0/F1 26/33保持；七失败逐项定位stairs-only未知同层；唯一回归路线29.340291→26.296502m精确绑定修正 条件已知入口原型；首包故障不可作最终，最终R1_FIXED+UI增量 [R-KNOWN-ENTRANCE-E2E-R1-FIXED](evidence/claims.html#R-KNOWN-ENTRANCE-E2E-R1-FIXED)

## PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED

时间：2026-11-11 21:43:20–23:26:08+08；时间依据：`STATUS.json:started_at + delivery/FINAL_COMPLETION.json`。

问题：在已登记步行面完整合法内部穿行能否减少边缘带绕行。

起因与实际变化：3m边缘带把可用面内部漏出规划空间 带洞合法多边形可见图接完整图、多接点重新选择；FULL_FACE×F0/F1；同Ω/障碍/权限/层级/净空。

结果与后续决定：6/8缩短、2/8持平。南159.195600→148.863122m；北近F0 331.647435→299.531450，F1 331.922336→300.784185；图书馆180.581119不变 最终内核R2/固定包c5472838...，独立新请求解包通过带明确数值裁决 [R-PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED](evidence/claims.html#R-PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED)

## PED-AREA-CONNECTIVITY-R1

时间：2026-11-12 00:09:06–03:57:27+08；时间依据：`delivery/DELIVERY_STATUS.json:budget_started_at/completed_at`。

问题：已存在原生步行面是否漏读，面线/面面接口能否进图并改变业务路线。

起因与实际变化：完整面穿行之后仍疑似沿远路，需分开源面发现/图准入/实际路线 B1完整源面；B2精确线面/面面衔接；B3受约束条件小接缝；同F0/F1成本。

结果与后续决定：源面新增82唯一；机制B0 3/8、B1 4/8、B2/B3 5/8；四业务任务完整路线四模式逐段相同 104主完成、16复放、1中断，共121尝试，92实际正式solver；最终后封包回执通过 [R-PED-AREA-CONNECTIVITY-R1](evidence/claims.html#R-PED-AREA-CONNECTIVITY-R1)

## PED-AREA-CONNECTIVITY-R2

时间：2026-11-12 12:29–13:32:24+08；时间依据：`delivery/FINAL_STATUS.json:finished_at/wall_minutes_to_delivery`。

问题：为什么新增82面、机制3/8→5/8，业务四路线却没变。

起因与实际变化：不能以对象更多或接点更多推断业务改善，需路线走廊和有向图证据 仅四业务端点F0/F1的B3诊断、正反SSSP、接口强制替代、源面归属、删类证书；通用诊断材料化最小修复。

结果与后续决定：82中36在业务两scene面池，46池外；36分为更贵19、其他有向分量16、无当前owner1；8最优代价全重现；32删类同最优证书 不为制造变短放宽限制；保留原结果；外审/用户观察PENDING [R-PED-AREA-CONNECTIVITY-R2](evidence/claims.html#R-PED-AREA-CONNECTIVITY-R2)

## SMART_CITY_WALKABILITY_FOUNDATION_PG1

时间：2026-11-12（原最终记录；封包后的恢复另记）；时间依据：`phase1/execution_receipt.json、phase2/collection_receipt.json及包外最终状态`。

问题：现有地图信息被保留到哪一步，独立验证数据是否已经可用？。

起因与实际变化：先区分导入、路由准入、显示与独立评价，避免继续用失真的图判断算法。 逐对象信息审计；已有输出重绘；非校园数据发现；8次有限代价探针。

结果与后续决定：53624个源对象有可显示几何，30420个原生线段准入；5候选中4矢量1元数据，1235feature=1063建筑+172人行面；可冻结完整合同0；批量成本构建7/8更慢。 G0公开、G1视觉、G2分组仍待批准；两轨继续按门禁管理。 [R-SMART-CITY-WALKABILITY-FOUNDATION-PG1](evidence/claims.html#R-SMART-CITY-WALKABILITY-FOUNDATION-PG1)

## PG1_RESUME_STREET_SIDE_R1

时间：2026-11-13 03:39:13+08（trial_summary完成字段）；时间依据：`results/trial_summary.json:completed_at`。

问题：缺少明确人行道几何时，侧别身份与条件沿街通道能否避免道路轴错误合并？。

起因与实际变化：原轴线表示会丢失道路两侧区别；原业务路线确实使用过道路轴。 R1原生/明确侧别；R2加缺标假设侧道；跨路不新增假设过街。

结果与后续决定：R0：4连通+2零长度侧别别名；R1：3连通+1断开+2端点缺失；R2：4连通+2断开。R0默认未变。 候选R1/R2不自动升级；保留R0及全部失败、零长度和成本修正。 [R-PG1-RESUME-STREET-SIDE-R1](evidence/claims.html#R-PG1-RESUME-STREET-SIDE-R1)

## PG1_MAP_CONTEXT_VISUAL_REPAIR_R1

时间：2026-11-13（固定包及收尾记录）；时间依据：`delivery/FINAL_STATUS.json`。

问题：把街区底图完整恢复后，三个方法能否在相同底图比较？。

起因与实际变化：上一轮图过度只显示算法选线，读者难认真实场景。 恢复原始地图上下文；同窗同尺度四层呈现；未求路。

结果与后续决定：补全源—图对象保留清单与真实PNG/SVG；但native以way/39764359步道定窗，原320m窗不含实际博物馆建筑。 对应Museum场景解释由RECONSTRUCTION-R2正式替换；历史图醒目标记保留。 [R-PG1-MAP-CONTEXT-VISUAL-REPAIR-R1](evidence/claims.html#R-PG1-MAP-CONTEXT-VISUAL-REPAIR-R1)

## PG1_MAP_CONTEXT_RECONSTRUCTION_R2

时间：2026-11-13 05:36–06:17+08（实际任务记录）；时间依据：`delivery/FINAL_STATUS.json:closed_at/elapsed_minutes`。

问题：实际显示的是否真正是上海博物馆人民广场馆，其与黄陂北路关系是否正确？。

起因与实际变化：上轮地图绑定了附近步道，不能以对象画全代替场景正确。 建筑way/161090899+原南main/北exit+完整七段黄陂北路共同定窗；五视野同底图。

结果与后续决定：建筑及两门身份核对；七段黄陂tertiary组成约638.126m源中心线；全景820×820m；旧诊断明确在西北步道。 技术材料交付完成，GPT与用户验收仍待；本交接轮不更改门禁。 [R-PG1-MAP-CONTEXT-RECONSTRUCTION-R2](evidence/claims.html#R-PG1-MAP-CONTEXT-RECONSTRUCTION-R2)
