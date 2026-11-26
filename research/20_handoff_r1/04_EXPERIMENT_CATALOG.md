# 逐轮实验目录

每轮按实际问题、数据和结果整理；这是实验记录目录，不是汇报结构建议。时间、单位、失败及版本纠正均与正结果一起保留。

## NAV_END_V1

**日期／来源**：2026-11-08T15:58:31.453612+00:00 — 2026-11-08T16:19:24.426061+00:00 (UTC；北京时间+08:00)

**状态**：CURRENT_HISTORICAL_BASELINE

**Question**：开放地图截图能否支持已知入口接近、未知入口候选和条件几何路径？

**Motivation**：商业截图采集未获许可，先形成可追溯开放地图截图工具和原型。

**Baseline**：B0同起终点直线

**Intervention**：M0/B1来源几何；M1/B2图像解析+给定入口；M2/B3图像解析+K3候选

**Data and sample unit**：苏黎世、Midwood、剑桥三空间组；120栋/240图，每楼两视野；有入口参考14栋/28图。

**Actual result**：实际240张主库截图；M1/B2来源几何独立通过23/28；M2/B3到自选候选独立通过208/240；入口Top1 9/28、Top3 16/28。

**Positive evidence**：开放源浏览器建库和二维候选条件接近可实现。

**Negative/inconclusive evidence**：B3可到候选不等于候选是真门；已知入口有2条来源碰撞；没有现场与导航终止记录。

**What it supports**：开放源浏览器建库和二维候选条件接近可实现。

**What it does not support**：真实门识别、公众通行、跨城泛化、商业App截图自动成功。

**Decision/status**：作为后续V2回归；旧留出已暴露，不可在PG1重新称盲测。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-e01346ae0c0f12](source_materials/experiment_reports/NAV_END_V1/stage_results_e01346ae.md)；[S-c2460701abfa65](source_materials/metrics/NAV_END_V1/summary_metrics_c2460701.json)；[S-e643770a916934](source_materials/metrics/NAV_END_V1/route_metrics_e643770a.csv)；[S-8b46a190102994](source_materials/metrics/NAV_END_V1/failure_cases_8b46a190.csv)；[S-22caf49d7af885](source_materials/metrics/NAV_END_V1/dataset_validation_22caf49d.json)；[S-aae0956fffd5af](source_materials/metrics/NAV_END_V1/claims_to_artifacts_aae0956f.csv)；[S-99b25ed5a13bab](source_materials/review_reports/NAV_END_V1/independent_review_99b25ed5.md)；[S-b6ccc5dc49b558](source_materials/review_reports/NAV_END_V1/author_review_b6ccc5dc.md)；[R-NAV-END-V1](evidence/claims.html#R-NAV-END-V1)。

**原图**：[F-c7b3e7dd6d8c44](figures/maps/NAV_END_V1/contact_cam_c7b3e7dd.png)；[F-8d6202b86ae3c4](figures/maps/NAV_END_V1/contact_nym_8d6202b8.png)；[F-0d8c1a71a7eb8a](figures/maps/NAV_END_V1/contact_zrh_0d8c1a71.png)。

## NAV_END_V2

**日期／来源**：2026-11-09T05:12:10.610197+00:00 — 2026-11-09T05:26:46.076594+00:00 (UTC；北京时间+08:00)

**状态**：CURRENT_HISTORICAL_PROTOTYPE

**Question**：跨样式解析、候选排序和通路约束能否改进V1？

**Motivation**：V1通路缺证据、微小穿楼与图式依赖需要分开处理。

**Baseline**：A0原解析/原路径与K3首可达；V1只读回归

**Intervention**：C0终端避障修复；A1-r2自适应图式；G5候选规则；严格/偏好通路

**Data and sample unit**：旧240图回归；新样式96图；新增24栋48图；确认子集3栋6图，样式确认48图另计。

**Actual result**：C0旧已知任务通过25/28；新样式A1-r2已知19/24，未知24/48；新增建筑确认C0和G5均登记参考联合2/6，没有选择提升。

**Positive evidence**：样式适配与特定几何修复可改善局部结果；通路偏好改变证据组成。

**Negative/inconclusive evidence**：严格通路旧未知只2/216、已知0/28；A1不能全局替代原解析；新样式未知有11条来源碰撞；新增确认已知入口0/6。

**What it supports**：样式适配与特定几何修复可改善局部结果；通路偏好改变证据组成。

**What it does not support**：未知候选是真门、截图中默认空白可真实通行、全局替换解析已可靠。

**Decision/status**：默认保留K3首可达；G5未在新增确认获得收益；商业私有图另包不进入同学包。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-002e6c34e7fbd2](source_materials/experiment_reports/NAV_END_V2/stage_results_002e6c34.md)；[S-b75a79353a86a0](source_materials/metrics/NAV_END_V2/metric_summary_b75a7935.json)；[S-10f3e93e5c1f09](source_materials/metrics/NAV_END_V2/route_metrics_10f3e93e.csv)；[S-b90cffd121d9dd](source_materials/metrics/NAV_END_V2/v1_counterexamples_b90cffd1.json)；[S-a5d3b102f26529](source_materials/review_reports/NAV_END_V2/independent_review_a5d3b102.md)；[S-6c77fc9152592e](source_materials/method_docs/NAV_END_V2/new_source_audit_6c77fc91.md)；[S-99a900c72194ff](source_materials/method_docs/NAV_END_V2/confirmation_freeze_99a900c7.json)；[S-6b1ae3aca9c48c](source_materials/method_docs/NAV_END_V2/style_pair_lock_6b1ae3ac.json)；[R-NAV-END-V2](evidence/claims.html#R-NAV-END-V2)。

**原图**：[F-c2a3030c547722](figures/system/NAV_END_V2/contact_new_buildings_c2a3030c.png)；[F-dd6eee4f061edb](figures/system/NAV_END_V2/contact_styles_dd6eee4f.png)；[F-519bb9241996aa](figures/system/NAV_END_V2/contact_v1_regression_519bb924.png)。

## OSM_GEOAPIFY_PILOT_R1

**日期／来源**：2026-11-09T17:55:38+08:00；STATUS.start_local

**状态**：FINAL_AB_COMPLETION_SUPERSEDES_INITIAL_PARTIAL

**Question**：本地OSM与Geoapify能否同场景同尺度取得地图和步行结果？

**Motivation**：需要合法公开图面与可核验的地图/路线比较。

**Baseline**：本地OSM矢量渲染+保守步行线网

**Intervention**：Geoapify原静态图及归档walk响应，同合同两视野

**Data and sample unit**：上海博物馆人民广场馆1栋/2视野；固定入口任务1个。

**Actual result**：最终2/2双侧视野已补齐；本地入口请求0/1，诊断线1416.719m；Geoapify接口964m、独立折线961.819m，末端仍距南门54.986m。

**Positive evidence**：双路径同尺度制图与真实接口接通，最后一段缺口可显式定位。

**Negative/inconclusive evidence**：早期04和旧OPEN_REVIEW的双侧0/2已被09与AB_COMPLETION替代；HTTP200不表示到入口；实际credits未知。

**What it supports**：双路径同尺度制图与真实接口接通，最后一段缺口可显式定位。

**What it does not support**：完整到门、付费余额已确认、两种独立地理数据源。

**Decision/status**：保留两路，进入路线差异诊断；现场0。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-74da92ea351ea5](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R1/09_AB_COMPLETION_RESULTS_74da92ea.md)；[S-9d08040f94af85](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R1/04_EXPERIMENT_RESULTS_9d08040f.md)；[S-7088239669af63](source_materials/metrics/OSM_GEOAPIFY_PILOT_R1/STATUS_70882396.json)；[S-b8bda13a310911](source_materials/metrics/OSM_GEOAPIFY_PILOT_R1/local_route_b8bda13a.json)；[S-5e3e7c22ee108f](source_materials/metrics/OSM_GEOAPIFY_PILOT_R1/geoapify_walk_probe_proxy_5e3e7c22.json)；[S-c1095ffa88bac6](source_materials/review_reports/OSM_GEOAPIFY_PILOT_R1/INDEPENDENT_AB_COMPLETION_c1095ffa.md)；[S-69612882cbf754](source_materials/review_reports/OSM_GEOAPIFY_PILOT_R1/INDEPENDENT_REVIEW_69612882.md)；[S-efbded8336df58](source_materials/review_reports/OSM_GEOAPIFY_PILOT_R1/OPEN_REVIEW_AB_COMPLETION_VERIFICATION_efbded83.json)；[R-OSM-GEOAPIFY-PILOT-R1](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R1)。

**原图**：[F-4ca6170a61c07a](figures/maps/OSM_GEOAPIFY_PILOT_R1/sh-huangpu-01_context_base_4ca6170a.png)；[F-51d2261473c835](figures/routes/OSM_GEOAPIFY_PILOT_R1/sh-huangpu-01_context_route_51d22614.png)；[F-c80e9934e40ddc](figures/maps/OSM_GEOAPIFY_PILOT_R1/sh-huangpu-01_detail_base_c80e9934.png)。

## OSM_GEOAPIFY_PILOT_R2

**日期／来源**：2026-11-09T19:14:44+08:00；STATUS.start_local

**状态**：READ_ONLY_DIAGNOSIS

**Question**：为什么起点不同路，两条线都离南门约55m？

**Motivation**：用户已给实际视觉评分，图面质量和路线质量需要拆开。

**Baseline**：R1原始OSM与托管折线、原始评分

**Intervention**：同源拓扑/方向/广场边界及折线分段只读诊断

**Data and sample unit**：1栋/2视野；两条历史折线；用户原表9项各5分

**Actual result**：本地黄陂北路轴线未纳入保守步行图；南广场可见但内部未建可路由边；本地与托管末点相差0.038m；用户总分42/45与43/45、总体相同。

**Positive evidence**：视觉相似不保证完整路线；开放空间面线接入是明确机制缺口。

**Negative/inconclusive evidence**：托管内部图/权重/快照未知，不能把差异单归因渲染或数据；55.135m旧球面值改为54.986m椭球。

**What it supports**：视觉相似不保证完整路线；开放空间面线接入是明确机制缺口。

**What it does not support**：任何一方更优、托管内部吸附策略已证明、地图颜色等于路由可达。

**Decision/status**：进入多建筑双路径诊断；保留原始人工反馈不重评分。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-3d1c56c1e93089](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R2/01_ROUTE_DIFFERENCE_DIAGNOSIS_3d1c56c1.md)；[S-ebdd6a25fb2a27](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R2/02_MAP_VISUAL_VS_ROUTE_QUALITY_ebdd6a25.md)；[S-1bf927026da0e2](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R2/03_USER_FEEDBACK_TRACEABILITY_1bf92702.md)；[S-193b7ae63b38f0](source_materials/metrics/OSM_GEOAPIFY_PILOT_R2/endpoint_gap_audit_193b7ae6.csv)；[S-8d0b11bb1b04fc](source_materials/metrics/OSM_GEOAPIFY_PILOT_R2/coordinate_and_snap_audit_8d0b11bb.csv)；[S-eb80865554310c](source_materials/metrics/OSM_GEOAPIFY_PILOT_R2/plaza_connectivity_audit_eb808655.csv)；[S-402fd8fab94917](source_materials/metrics/OSM_GEOAPIFY_PILOT_R2/route_segment_differences_402fd8fa.csv)；[S-3465779db906ee](source_materials/metrics/OSM_GEOAPIFY_PILOT_R2/osm_feature_inventory_3465779d.csv)；[R-OSM-GEOAPIFY-PILOT-R2](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R2)。

**原图**：[F-93390b907404bb](figures/routes/OSM_GEOAPIFY_PILOT_R2/figure01_global_93390b90.png)；[F-fa98ba37fb7a10](figures/routes/OSM_GEOAPIFY_PILOT_R2/figure02_origin_fa98ba37.png)；[F-f580eb6b1aa102](figures/routes/OSM_GEOAPIFY_PILOT_R2/figure03_plaza_f580eb6b.png)。

## OSM_GEOAPIFY_PILOT_R3

**日期／来源**：2026-11-09；01_SOURCE_AND_PERMISSION_AUDIT.md核验日期

**状态**：INCONCLUSIVE_RETAIN_BOTH

**Question**：扩展不同建筑后，两条路径是否存在足以淘汰一方的明显差异？

**Motivation**：单博物馆不足说明不同城市建筑形态表现。

**Baseline**：R1博物馆历史单例保留

**Intervention**：新增5栋非校园：武康、上海中心、新世界城、图书馆、展览中心；同尺度双路径

**Data and sample unit**：新增5栋/10视野，博物馆1栋/2历史视野另计

**Actual result**：新增本地返回4/5，托管5/5；10/10视野同尺度；25/25HTTP200；新增请求目标仅1/5具原生登记入口，其余代理/未知。

**Positive evidence**：两路工程差异真实存在；可用共同接口表示输入与未知字段。

**Negative/inconclusive evidence**：本地与托管状态定义不同，无路径真值与实体门核验；新世界城不同分量；中心大厦平面冲突告警；不能据5/5对4/5选赢家。

**What it supports**：两路工程差异真实存在；可用共同接口表示输入与未知字段。

**What it does not support**：托管优于本地、双独立地图源、真实入口可达率4/5或5/5。

**Decision/status**：INCONCLUSIVE，保留双路径；下一步研究开放空间接入。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-b5a692a6ce3029](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R3/03_PAIRED_COMPARISON_RESULTS_b5a692a6.md)；[S-6e8ffa21efe8e0](source_materials/experiment_reports/OSM_GEOAPIFY_PILOT_R3/05_DECISION_ON_TWO_PATHS_6e8ffa21.md)；[S-c56c7d12005012](source_materials/metrics/OSM_GEOAPIFY_PILOT_R3/comparison_c56c7d12.csv)；[S-817a3bb1758872](source_materials/metrics/OSM_GEOAPIFY_PILOT_R3/hosted_results_817a3bb1.json)；[S-82d971eae40e56](source_materials/metrics/OSM_GEOAPIFY_PILOT_R3/local_newworld_topology_82d971ea.json)；[S-58eb37374e7d70](source_materials/review_reports/OSM_GEOAPIFY_PILOT_R3/OPEN_REVIEW_VERIFICATION_58eb3737.json)；[S-71beb9c29b35f1](source_materials/method_docs/OSM_GEOAPIFY_PILOT_R3/01_SOURCE_AND_PERMISSION_AUDIT_71beb9c2.md)；[S-9f708078aa938e](source_materials/method_docs/OSM_GEOAPIFY_PILOT_R3/02_SAMPLE_AND_VIEWPORT_CONTRACT_9f708078.md)；[R-OSM-GEOAPIFY-PILOT-R3](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R3)。

**原图**：[F-4c517edb1de950](figures/maps/OSM_GEOAPIFY_PILOT_R3/sh-exhibition_context_base_4c517edb.png)；[F-81b0a5277ff2ae](figures/routes/OSM_GEOAPIFY_PILOT_R3/sh-exhibition_context_route_81b0a527.png)；[F-1fa8ba877a8674](figures/maps/OSM_GEOAPIFY_PILOT_R3/sh-exhibition_detail_base_1fa8ba87.png)。

## OSM_GEOAPIFY_R4

**日期／来源**：2026-11-10T10:33:28+08:00；STATUS.started_asia_shanghai

**状态**：SUPERSEDED_METHOD_BY_R4_REV1_HISTORICAL_NEGATIVE

**Question**：开放空间边缘如何接到步行图？

**Motivation**：R2/R3暴露广场内部缺边与跨分量问题。

**Baseline**：B0原生图

**Intervention**：B1有源线边缘；B2有源线内部；B3多登记门

**Data and sample unit**：6固定场景，33源线段-面候选对；2适用登记入口

**Actual result**：B1、B2新增均0，25已在B0、8拒绝；严格登记门B0/B1/B2均1/2；B3不适用。

**Positive evidence**：原生线规则边界和现有数据不足可清楚记账。

**Negative/inconclusive evidence**：把每一段新边都要求同位置原生线，未实际发挥已标步行面的面积支持；零新增不能反证面派生不可行。

**What it supports**：原生线规则边界和现有数据不足可清楚记账。

**What it does not support**：开放空间算法无用、所有面内都不可走、真实到门率。

**Decision/status**：后续R4-REV1明确允许来源步行面内计算边，本轮作为受限规则负结果保留。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-f382104ac14f38](source_materials/experiment_reports/OSM_GEOAPIFY_R4/04_EXPERIMENT_RESULTS_f382104a.md)；[S-7f44e771f3394b](source_materials/metrics/OSM_GEOAPIFY_R4/summary_7f44e771.json)；[S-004a313fa8bdbb](source_materials/metrics/OSM_GEOAPIFY_R4/added_edges_004a313f.csv)；[S-e9afe0ed2054f8](source_materials/metrics/OSM_GEOAPIFY_R4/edge_candidate_evidence_e9afe0ed.csv)；[S-ccda535e32fdec](source_materials/metrics/OSM_GEOAPIFY_R4/entrance_access_ccda535e.csv)；[S-f7e9b7338ec0e8](source_materials/metrics/OSM_GEOAPIFY_R4/connectivity_changes_f7e9b733.csv)；[S-086055f80475d0](source_materials/review_reports/OSM_GEOAPIFY_R4/INDEPENDENT_REVIEW_086055f8.md)；[S-eabcfa20859016](source_materials/review_reports/OSM_GEOAPIFY_R4/OPEN_REVIEW_VERIFICATION_eabcfa20.json)；[R-OSM-GEOAPIFY-R4](evidence/claims.html#R-OSM-GEOAPIFY-R4)。

**原图**：[F-54e7ed69c3b79c](figures/routes/OSM_GEOAPIFY_R4/10_interactive_preview_54e7ed69.png)。

## OSM_GEOAPIFY_R4_REV1

**日期／来源**：2026-11-10T11:33:00+08:00；STATUS.started_asia_shanghai

**状态**：HISTORICAL_EDGE_BAND_BASELINE_LATER_CORRECTNESS_REVISED

**Question**：已标步行面可否生成绕障碍的边缘计算图？

**Motivation**：旧R4过严原生线规则导致0新增，需真正利用来源步行面。

**Baseline**：H0原线图、H1旧R4

**Intervention**：3m边缘带0.5m网格8邻域，保留内环障碍；1/5m敏感性、移除派生层消融

**Data and sample unit**：6已观察开发场景；博物馆南广场3原生接点试走

**Actual result**：主设置155226计算边记录、310448有向弧；南3/3条件接通但仅2/3平面清洁；最短有效1067.37m；北仍缺7.9522m。

**Positive evidence**：面可作为计算边来源，门外可达与exit入馆资格可拆开。

**Negative/inconclusive evidence**：一条南原生前缀穿围栏；北前缀草地过滤后变长；后续S轮修复草地误排有效步道，不把本轮过滤规则视为最终正确默认。

**What it supports**：面可作为计算边来源，门外可达与exit入馆资格可拆开。

**What it does not support**：155226独立通道/建筑样本、现实全程可走、exit可入馆、现场核验。

**Decision/status**：作为边缘带冻结历史基线；后续草地修复与FULL_FACE继续修订。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-7836a324bddfb2](source_materials/experiment_reports/OSM_GEOAPIFY_R4_REV1/RESULTS_7836a324.md)；[S-b8344583b25e25](source_materials/metrics/OSM_GEOAPIFY_R4_REV1/summary_b8344583.json)；[S-5d82fe70661663](source_materials/metrics/OSM_GEOAPIFY_R4_REV1/entrance_approach_5d82fe70.json)；[S-005eeaf3c95048](source_materials/metrics/OSM_GEOAPIFY_R4_REV1/native_prefix_diagnostic_005eeaf3.json)；[S-1f47282643e5d4](source_materials/metrics/OSM_GEOAPIFY_R4_REV1/routes_1f472826.geojson)；[S-6a5d6479803f48](source_materials/review_reports/OSM_GEOAPIFY_R4_REV1/INDEPENDENT_REVIEW_6a5d6479.md)；[S-962e34d2b9b770](source_materials/review_reports/OSM_GEOAPIFY_R4_REV1/INDEPENDENT_ARCHIVE_VERIFICATION_962e34d2.json)；[S-dd5b9af3401e8d](source_materials/review_reports/OSM_GEOAPIFY_R4_REV1/OPEN_REVIEW_REPLAY_dd5b9af3.json)；[R-OSM-GEOAPIFY-R4-REV1](evidence/claims.html#R-OSM-GEOAPIFY-R4-REV1)。

**原图**：[F-0266f72a9aa724](figures/routes/OSM_GEOAPIFY_R4_REV1/07_interactive_preview_0266f72a.png)。

## OSM_GEOAPIFY_R4_NORTH_ACCESS_R1

**日期／来源**：2026-11-10T13:30:00+08:00；STATUS.started_asia_shanghai

**状态**：HISTORICAL_CONDITIONAL_CONNECTOR_NOT_AREA_RECOVERY

**Question**：北exit约7.95m缺口加空间约束能否比直线更合理？

**Motivation**：北出口在步行面外，需保留原坐标、exit与未知事实。

**Baseline**：N0原图；N1直线假设

**Intervention**：N2出口12m范围×接入方向半宽2m条带，裁公园、扣障碍，可见图

**Data and sample unit**：博物馆北出口1个开发案例；N0/N1/N2三变体，5组参数

**Actual result**：N2允许域31.80m²，选线与N1同7.9522m；全程1245.77m，门残差0；楼层与通行证据仍未知，假设身份未升级。

**Positive evidence**：约束可记录可搜索范围和障碍检查；同一条合法直线本来就是最短。

**Negative/inconclusive evidence**：N2区域围绕预定连接条带生成，不能当独立区域级空间恢复；没有连续步行/同层证据，复杂算法未创造证据。

**What it supports**：约束可记录可搜索范围和障碍检查；同一条合法直线本来就是最短。

**What it does not support**：真实通路、同层已证实、北门入馆、区域恢复已完成。

**Decision/status**：保留假设连接；后续R2/R3将研究对象改为独立候选/区域生成。

**修正关系**：详见版本修正登记；历史身份保留。

**Evidence references**：[S-03dd8ce5ed7234](source_materials/experiment_reports/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/04_RESULTS_03dd8ce5.md)；[S-2b1e89d37cc3e2](source_materials/experiment_reports/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/05_LIMITATIONS_AND_DECISION_2b1e89d3.md)；[S-024551aa0c2a2f](source_materials/metrics/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/experiment_024551aa.json)；[S-71978000709e8c](source_materials/metrics/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/segment_evidence_71978000.csv)；[S-2b312276b41673](source_materials/metrics/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/level_evidence_2b312276.csv)；[S-1a1ded4156e256](source_materials/metrics/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/obstacle_intersections_1a1ded41.csv)；[S-47498bef55bc9c](source_materials/metrics/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/route_variants_47498bef.geojson)；[S-b6db8eccdf5e77](source_materials/review_reports/OSM_GEOAPIFY_R4_NORTH_ACCESS_R1/INDEPENDENT_REVIEW_b6db8ecc.md)；[R-OSM-GEOAPIFY-R4-NORTH-ACCESS-R1](evidence/claims.html#R-OSM-GEOAPIFY-R4-NORTH-ACCESS-R1)。

## WALKABILITY-R2

**日期／来源**：2026-11-10 14:36+08

**状态**：保留S修复；I1简单基线和I2条件原型；外审/用户待验收

**Question**：修复背景草地误杀已标步道，并比较缺标连接推断

**Motivation**：北门既有前段被草地面排除，7.95m末段缺口仍存在

**Baseline**：S0草地旧排除；I0不补线/I1最近直连

**Intervention**：S1保留有效原生步道；I2独立搜索域多接点受约束推断

**Data and sample unit**：六冻结裁片；14遮蔽正例、4障碍负例；自然北exit单列

**Actual result**：377原生片段/754有向弧恢复；北前段1237.81→1166.10m；I2自然完整条件1168.98m，I1为1174.05m；受控I2 5/14，I1 3/14

**Positive evidence**：草地不能抹去有效原生步道；条件连接可真实参与整图选路

**Negative/inconclusive evidence**：确认组I1/I2同2/4；唯一登记门正例I2未恢复；移除上下文开发+选择恢复增加但门槛过保守

**What it supports**：草地不能抹去有效原生步道；条件连接可真实参与整图选路

**What it does not support**：不证明I2确认集优于I1，不证明现实同层/通行或可入馆

**Decision/status**：保留S修复；I1简单基线和I2条件原型；外审/用户待验收

**修正关系**：后续R3改为独立区域表示，R2不冒充区域级恢复

**Evidence references**：[S-b16284ce69d904](source_materials/experiment_reports/WALKABILITY-R2/RESULTS_b16284ce.md)；[S-11a4ed3c2c9769](source_materials/experiment_reports/WALKABILITY-R2/README_11a4ed3c.md)；[S-97150217cd86e0](source_materials/method_docs/WALKABILITY-R2/SCOPE_AND_METHOD_97150217.md)；[S-19ec50468ef820](source_materials/review_reports/WALKABILITY-R2/INDEPENDENT_REVIEW_19ec5046.md)；[S-a462d92d5731c5](source_materials/metrics/WALKABILITY-R2/semantics_a462d92d.json)；[S-d8ef5c0bede424](source_materials/metrics/WALKABILITY-R2/masking_evaluation_d8ef5c0b.json)；[S-be0d1393c5f3a6](source_materials/metrics/WALKABILITY-R2/semantics_edges_be0d1393.csv)；[S-744df6b6dd7bb1](source_materials/metrics/WALKABILITY-R2/inference_candidates_744df6b6.csv)；[R-WALKABILITY-R2](evidence/claims.html#R-WALKABILITY-R2)。

**原图**：[F-c395f35f8b7818](figures/maps/WALKABILITY-R2/06-rejected-conflict_c395f35f.png)。

## WALKABILITY-R3

**日期／来源**：2026-11-10 21:01:07+08

**状态**：保留S与线基线；I-REGION仅可审查原型

**Question**：真正区域级四态恢复能否支持多个外围接点，而不围旧直线buffer

**Motivation**：上一轮I2主要输出连接线，不能回答区域范围与复用

**Baseline**：S1及I-LINE

**Intervention**：独立于终路端点冻结30m四态格网区域，再接多个接口并求路；消融区域图/上下文

**Data and sample unit**：25受控任务=7面+14线+4障碍；41固定查询；自然北exit单列

**Actual result**：北门推断180.96m²，165.05m²位于旧直线1m缓冲外；自然条件1166.92m；主面覆盖18.88/3996.53m²(0.47%)；区域19/41路线，I-LINE29/41

**Positive evidence**：可复用区域表示/证据/多端点条件路由机制成立

**Negative/inconclusive evidence**：7面均未达半覆盖，确认2面覆盖0；区域无新增可达正例集合，19/41与S1相同；未知占比均值61.19%

**What it supports**：可复用区域表示/证据/多端点条件路由机制成立

**What it does not support**：当前规则恢复能力不充分，不是稳定通行恢复算法，不是新独立验证

**Decision/status**：保留S与线基线；I-REGION仅可审查原型

**修正关系**：仅地理导出数值修复，区域类别、固定查询与路线不变；后续Context保留0.47%历史身份

**Evidence references**：[S-c70f9e940c5afb](source_materials/experiment_reports/WALKABILITY-R3/RESULTS_c70f9e94.md)；[S-e0bad12aa7d573](source_materials/experiment_reports/WALKABILITY-R3/README_e0bad12a.md)；[S-ba3f3a08ff6bf4](source_materials/method_docs/WALKABILITY-R3/SCOPE_AND_METHOD_ba3f3a08.md)；[S-d10e07003100a3](source_materials/method_docs/WALKABILITY-R3/REGION_RECONSTRUCTION_d10e0700.md)；[S-374c4d8a6502a1](source_materials/review_reports/WALKABILITY-R3/INDEPENDENT_REVIEW_374c4d8a.md)；[S-4c5f516cf7e7e5](source_materials/review_reports/WALKABILITY-R3/LEAKAGE_REVIEW_4c5f516c.md)；[S-a87b0bfef06c40](source_materials/metrics/WALKABILITY-R3/benchmark_evaluation_a87b0bfe.json)；[S-0c2c1ee6be7669](source_materials/metrics/WALKABILITY-R3/benchmark_run_registry_0c2c1ee6.json)；[R-WALKABILITY-R3](evidence/claims.html#R-WALKABILITY-R3)。

**原图**：[F-b142ee67f2c20a](figures/maps/WALKABILITY-R3/01-grass-native-walkways_b142ee67.png)；[F-580fbb31151cb1](figures/maps/WALKABILITY-R3/02-north-walkability-states_580fbb31.png)；[F-30a98bf114c007](figures/maps/WALKABILITY-R3/03-shared-region-multiple-queries_30a98bf1.png)。

## WALKABILITY-R4-CONTEXT

**日期／来源**：R3之后、FREE-SPACE-R1之前；精确启动时刻NOT_VERIFIED

**状态**：M0保留简单基线，M1条件比较，不晋升通用方法

**Question**：看40/80/160m上下文、只补30m固定域，能否改善区域恢复

**Motivation**：强遮蔽误删整个way，放大观察可能把答案重新漏入

**Baseline**：冻结M0；H强遮蔽/G局部几何遮蔽分开

**Intervention**：修订合法外段保留、防泄漏；M1显式使用外围拓扑和临街关系；固定1m格网/评分域/参考

**Data and sample unit**：25父任务=7面14线4负例；41查询；138观察输入；282主区域运行非独立样本

**Actual result**：G80面覆盖M0 0.77%→M1 0.92%；线覆盖6.25%→16.22%；两者均20/33正例到达；M1使用推断替代路径2→4

**Positive evidence**：外围信息实际进入区域判断；合法外段保留有效

**Negative/inconclusive evidence**：面参考外扩张37.93→66.86m²；正例新增可达0；放大范围本身不改善M0区域；旧确认已暴露

**What it supports**：外围信息实际进入区域判断；合法外段保留有效

**What it does not support**：不能把圈外绕行新增到达当局部恢复；不能把138或282当独立场景数

**Decision/status**：M0保留简单基线，M1条件比较，不晋升通用方法

**修正关系**：H和G任务难度不同单报；后续FREE_SPACE以M1-C统一约束成本，不冒充原M1性能

**Evidence references**：[S-6c96d25681b2ce](source_materials/experiment_reports/WALKABILITY-R4-CONTEXT/RESULTS_6c96d256.md)；[S-90ce295c3269d8](source_materials/experiment_reports/WALKABILITY-R4-CONTEXT/README_90ce295c.md)；[S-1869518d40b2d1](source_materials/method_docs/WALKABILITY-R4-CONTEXT/SCOPE_AND_METHOD_1869518d.md)；[S-264f09bcac3898](source_materials/review_reports/WALKABILITY-R4-CONTEXT/INDEPENDENT_REVIEW_264f09bc.md)；[S-7a5638753aaa26](source_materials/metrics/WALKABILITY-R4-CONTEXT/context_metrics_7a563875.csv)；[S-885fbbe17b131a](source_materials/metrics/WALKABILITY-R4-CONTEXT/context_metrics_885fbbe1.json)；[S-276acf2301bbdb](source_materials/metrics/WALKABILITY-R4-CONTEXT/e0_replay_276acf23.json)；[S-15b943cf4d6123](source_materials/metrics/WALKABILITY-R4-CONTEXT/e5_north_regression_15b943cf.json)；[R-WALKABILITY-R4-CONTEXT](evidence/claims.html#R-WALKABILITY-R4-CONTEXT)。

**原图**：[F-9749cf8c0747c9](figures/maps/WALKABILITY-R4-CONTEXT/01-context-and-local_9749cf8c.png)；[F-116247724176e8](figures/maps/WALKABILITY-R4-CONTEXT/02-masking-comparison_11624772.png)；[F-ed25ed15e1e606](figures/maps/WALKABILITY-R4-CONTEXT/03-m0-m1-comparison_ed25ed15.png)。

## FREE-SPACE-R1-FINAL

**日期／来源**：2026-11-11 13:39:29–15:46:53+08

**状态**：最终R1修复版保留F0透明基线/F1有限成本分支；用户/GPT待验收

**Question**：排除已知约束后默认允许缺标局部空间，是否改善条件规划

**Motivation**：正向证据区域恢复过于保守，仍未知的空间不自动禁止研究性规划

**Baseline**：统一约束/成本M1-C，历史原M1另保留

**Intervention**：F0默认可行；F1完全同区域节点边接口，仅假设段有限代价；修复漏导private负约束

**Data and sample unit**：25主任务41查询=33正例8障碍查询；北门自然8查询单列

**Actual result**：M1-C20/33，F0/F1同26/33，新增6失去0；面覆盖100%来自假设扩张；F1同26查询少24.65m假设、多4.67m几何

**Positive evidence**：透明假设允许条件求路；约束导出完整性关键；成本能改变偏好但不改变同图可达集合

**Negative/inconclusive evidence**：F0/F1七面参考外未证实扩张10278.99m²；R0漏导128.39m² private面，最终修复；七正例仍不通；未知高差/公众权限/漏标障碍

**What it supports**：透明假设允许条件求路；约束导出完整性关键；成本能改变偏好但不改变同图可达集合

**What it does not support**：100%覆盖非100%现实可走；F1不是风险概率或安全保证

**Decision/status**：最终R1修复版保留F0透明基线/F1有限成本分支；用户/GPT待验收

**修正关系**：原OPEN_REVIEW_R0_PARTIAL SHA2b5154...保留故障历史；最终SHA1d4110...；预算旧32合成估计追加更正为实30，未扩大200上限

**Evidence references**：[S-5b9c05d41b6232](source_materials/experiment_reports/FREE-SPACE-R1-FINAL/RESULTS_5b9c05d4.md)；[S-29a4eeae89e2b6](source_materials/experiment_reports/FREE-SPACE-R1-FINAL/README_29a4eeae.md)；[S-7e6d26065a3d06](source_materials/method_docs/FREE-SPACE-R1-FINAL/SCOPE_AND_METHOD_7e6d2606.md)；[S-ca506ee4e35ced](source_materials/review_reports/FREE-SPACE-R1-FINAL/INDEPENDENT_REVIEW_ca506ee4.md)；[S-4a30e429a979c7](source_materials/review_reports/FREE-SPACE-R1-FINAL/LEAKAGE_REVIEW_4a30e429.md)；[S-849b1688bd62c2](source_materials/method_docs/FREE-SPACE-R1-FINAL/INDEPENDENT_SOURCE_CROSSCHECK_849b1688.md)；[S-8576b819bbfae0](source_materials/metrics/FREE-SPACE-R1-FINAL/decision_numbers_8576b819.json)；[S-4af31e11c2a312](source_materials/metrics/FREE-SPACE-R1-FINAL/paired_metrics_4af31e11.csv)；[R-FREE-SPACE-R1-FINAL](evidence/claims.html#R-FREE-SPACE-R1-FINAL)。

**原图**：[F-dd742e5478249d](figures/routes/FREE-SPACE-R1-FINAL/01-north-full-route_dd742e54.png)；[F-3d13bf381ebb62](figures/maps/FREE-SPACE-R1-FINAL/02-north-three-methods_3d13bf38.png)；[F-9dde01cdb6cf40](figures/maps/FREE-SPACE-R1-FINAL/03-library-expansion_9dde01cd.png)。

## KNOWN-ENTRANCE-E2E-R1-FIXED

**日期／来源**：2026-11-11 18:34:45+08起，最终回执另列

**状态**：条件已知入口原型；首包故障不可作最终，最终R1_FIXED+UI增量

**Question**：把已有机制统一成可提交新请求、实际求路的CLI/HTTP/APP

**Motivation**：静态图册与旧JSON回放不构成可操作原型，七失败需逐项收敛

**Baseline**：冻结FREE_SPACE最终修复版

**Intervention**：统一约束/原生/已标面/F0/F1/端点，禁路线答案缓存；通用接口修复；真实页面与CLI/HTTP验收

**Data and sample unit**：六目标中两栋共3登记门、四目标无登记门；4端点用途任务×F0/F1=8合法请求；5拒绝；主25父41查询×3方法=123评估、122实际搜索

**Actual result**：8/8合法应用返回路线；主M1-C20/33、F0/F1 26/33保持；七失败逐项定位stairs-only未知同层；唯一回归路线29.340291→26.296502m精确绑定修正

**Positive evidence**：真实新请求求解链/分段来源/失败原因已实现，冻结规则内通用修复

**Negative/inconclusive evidence**：七条仍NO_PATH，来自4父任务网络节点而非七门；冷预处理约22.85–87.02s；只有现有少数登记门

**What it supports**：真实新请求求解链/分段来源/失败原因已实现，冻结规则内通用修复

**What it does not support**：8/8功能验收非导航可靠率；北exit仅门外；不支持缺门生成或全城

**Decision/status**：条件已知入口原型；首包故障不可作最终，最终R1_FIXED+UI增量

**修正关系**：首包cold日志同key被覆盖FAIL；R1仅修追加计时日志，结果不变。随后加载切用途/方法空地图UI缺陷独立修复，见hotfix34a6df...；新SHORTER继承该修复

**Evidence references**：[S-9e750398609712](source_materials/experiment_reports/KNOWN-ENTRANCE-E2E-R1-FIXED/RESULTS_9e750398.md)；[S-71d9dba2995078](source_materials/experiment_reports/KNOWN-ENTRANCE-E2E-R1-FIXED/README_71d9dba2.md)；[S-08db11b0424f03](source_materials/method_docs/KNOWN-ENTRANCE-E2E-R1-FIXED/SCOPE_AND_VERSION_08db11b0.md)；[S-f42b5dde3b27f6](source_materials/method_docs/KNOWN-ENTRANCE-E2E-R1-FIXED/INPUT_OUTPUT_CONTRACT_f42b5dde.md)；[S-ac0d94b424d4a5](source_materials/experiment_reports/KNOWN-ENTRANCE-E2E-R1-FIXED/EXPERIMENT_BRIEF_ac0d94b4.md)；[S-c198b83e9319db](source_materials/method_docs/KNOWN-ENTRANCE-E2E-R1-FIXED/NOTICE_c198b83e)；[S-b80efc8ae09c6c](source_materials/review_reports/KNOWN-ENTRANCE-E2E-R1-FIXED/INDEPENDENT_REVIEW_b80efc8a.md)；[S-3623f673e92251](source_materials/metrics/KNOWN-ENTRANCE-E2E-R1-FIXED/FAILURE_DIAGNOSIS_3623f673.csv)；[R-KNOWN-ENTRANCE-E2E-R1-FIXED](evidence/claims.html#R-KNOWN-ENTRANCE-E2E-R1-FIXED)。

**原图**：[F-6f08cd73536733](figures/system/KNOWN-ENTRANCE-E2E-R1-FIXED/independent_browser_exports.computed-full_6f08cd73.png)；[F-5de78b69a0e43f](figures/system/KNOWN-ENTRANCE-E2E-R1-FIXED/independent_browser_exports.computed-door_5de78b69.png)；[F-75546f6d0f00ca](figures/system/KNOWN-ENTRANCE-E2E-R1-FIXED/independent_browser_inspect_75546f6d.png)。

## PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED

**日期／来源**：2026-11-11 21:43:20–23:26:08+08

**状态**：最终内核R2/固定包c5472838...，独立新请求解包通过带明确数值裁决

**Question**：在已登记步行面完整合法内部穿行能否减少边缘带绕行

**Motivation**：3m边缘带把可用面内部漏出规划空间

**Baseline**：EDGE_BAND×F0/F1

**Intervention**：带洞合法多边形可见图接完整图、多接点重新选择；FULL_FACE×F0/F1；同Ω/障碍/权限/层级/净空

**Data and sample unit**：4业务起终点用途×F0/F1=8请求、每请求2模式共16主求解；7预锁局部面点对；10拒绝检查

**Actual result**：6/8缩短、2/8持平。南159.195600→148.863122m；北近F0 331.647435→299.531450，F1 331.922336→300.784185；图书馆180.581119不变

**Positive evidence**：已标面完整内部与整图接点能减少表示造成的绕行

**Negative/inconclusive evidence**：北门保留9.68–12.53m条件假设；其他4目标无登记门；截图未唯一绑定，883.48→682.44仅真实旧日志相似演示

**What it supports**：已标面完整内部与整图接点能减少表示造成的绕行

**What it does not support**：非现实全局最短/公众可进；局部7点对不是新门；无新Geoapify服务比较

**Decision/status**：最终内核R2/固定包c5472838...，独立新请求解包通过带明确数值裁决

**修正关系**：初149.0338m历史诊断SUPERSEDED，最终148.8631m；R1→R2角点/平行候选修复主表不变；最终浮差警报按预登记1e-8m原约定证明，不改路线阈值

**Evidence references**：[S-9febf86d9add70](source_materials/experiment_reports/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/RESULTS_9febf86d.md)；[S-8011107870d14d](source_materials/experiment_reports/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/README_80111078.md)；[S-8efa537cfc5dae](source_materials/method_docs/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/SCOPE_AND_METHOD_8efa537c.md)；[S-c198b83e9319db](source_materials/method_docs/KNOWN-ENTRANCE-E2E-R1-FIXED/NOTICE_c198b83e)；[S-0ea000fcefbd14](source_materials/review_reports/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/independent_review_0ea000fc.md)；[S-47b3d04dc31313](source_materials/metrics/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/performance_47b3d04d.csv)；[S-2651a95a42e91b](source_materials/metrics/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/run_registry_2651a95a.csv)；[S-4332ab8364494e](source_materials/metrics/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/independent_main_matrix_R2_4332ab83.json)；[R-PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED](evidence/claims.html#R-PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED)。

**原图**：[F-2fefe578827f8f](figures/routes/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/APP-01_2fefe578.png)；[F-4848acc3d033a1](figures/routes/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/APP-03_4848acc3.png)；[F-64ede9ff990f23](figures/routes/PEDESTRIAN-AREA-SHORTEST-R1-FINAL-FIXED/APP-07_64ede9ff.png)。

## PED-AREA-CONNECTIVITY-R1

**日期／来源**：2026-11-12 00:09:06–03:57:27+08

**状态**：104主完成、16复放、1中断，共121尝试，92实际正式solver；最终后封包回执通过

**Question**：已存在原生步行面是否漏读，面线/面面接口能否进图并改变业务路线

**Motivation**：完整面穿行之后仍疑似沿远路，需分开源面发现/图准入/实际路线

**Baseline**：B0冻结FULL_FACE

**Intervention**：B1完整源面；B2精确线面/面面衔接；B3受约束条件小接缝；同F0/F1成本

**Data and sample unit**：6冻结场景；130场景对象去重88唯一原生面，新增82唯一；8局部机制；4业务端点任务×F0/F1×4模式=32主响应

**Actual result**：源面新增82唯一；机制B0 3/8、B1 4/8、B2/B3 5/8；四业务任务完整路线四模式逐段相同

**Positive evidence**：源信息完整性和局部接口机制改善可独立成立

**Negative/inconclusive evidence**：新增面不等于入图、入图不等于使用；M03未绑定，M08原生layer1分量非零度孤点；B3本组未获业务收益；冷构图最长数分钟

**What it supports**：源信息完整性和局部接口机制改善可独立成立

**What it does not support**：不能宣称补82栋或82条门路线，不能把3/8→5/8叫整链效果

**Decision/status**：104主完成、16复放、1中断，共121尝试，92实际正式solver；最终后封包回执通过

**修正关系**：独审发现gap内fence漏洞在formal前修复Freeze2；connectivity_evidence.parent_mode描述勘误不改图/成本；旧零度孤点假说被反证

**Evidence references**：[S-3719581ef3bb5c](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R1/RESULTS_3719581e.md)；[S-ecd6c27850fba9](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R1/README_ecd6c278.md)；[S-66c3e817f51ad0](source_materials/method_docs/PED-AREA-CONNECTIVITY-R1/SCOPE_AND_METHOD_66c3e817.md)；[S-f94f643c49088c](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R1/EXPERIMENT_BRIEF_f94f643c.md)；[S-8589ed19c0473d](source_materials/method_docs/PED-AREA-CONNECTIVITY-R1/METHOD_8589ed19.md)；[S-c198b83e9319db](source_materials/method_docs/PED-AREA-CONNECTIVITY-R1/NOTICE_c198b83e.md)；[S-2e653ed32ab393](source_materials/review_reports/PED-AREA-CONNECTIVITY-R1/independent_review_2e653ed3.md)；[S-2e653ed32ab393](source_materials/review_reports/PED-AREA-CONNECTIVITY-R1/independent_review_2e653ed3.md)；[R-PED-AREA-CONNECTIVITY-R1](evidence/claims.html#R-PED-AREA-CONNECTIVITY-R1)。

**原图**：[F-e9b218bc5269bb](figures/routes/PED-AREA-CONNECTIVITY-R1/business_north_same_route_e9b218bc.png)；[F-071dfe368c0762](figures/routes/PED-AREA-CONNECTIVITY-R1/business_south_no_route_change_071dfe36.png)；[F-9458a50535f2ec](figures/routes/PED-AREA-CONNECTIVITY-R1/historical_F1_same_route_9458a505.png)。

## PED-AREA-CONNECTIVITY-R2

**日期／来源**：2026-11-12 12:29–13:32:24+08

**状态**：不为制造变短放宽限制；保留原结果；外审/用户观察PENDING

**Question**：为什么新增82面、机制3/8→5/8，业务四路线却没变

**Motivation**：不能以对象更多或接点更多推断业务改善，需路线走廊和有向图证据

**Baseline**：冻结R1 B0/B1/B2/B3原路线

**Intervention**：仅四业务端点F0/F1的B3诊断、正反SSSP、接口强制替代、源面归属、删类证书；通用诊断材料化最小修复

**Data and sample unit**：4业务端点任务×F0/F1=8formal求解/16SSSP；32删类证书；82新增唯一面逐案关联

**Actual result**：82中36在业务两scene面池，46池外；36分为更贵19、其他有向分量16、无当前owner1；8最优代价全重现；32删类同最优证书

**Positive evidence**：对象/局部机制改善与固定业务不变可同时成立；该固定有限图原路线已最优

**Negative/inconclusive evidence**：没有业务收益；有限替代多为毫米或以下差，无现实意义；图书馆有限候选未找到simple替代，不宣称不存在所有替代

**What it supports**：对象/局部机制改善与固定业务不变可同时成立；该固定有限图原路线已最优

**What it does not support**：最优性不延伸连续空间/现场通行，也不证明其他端点无收益

**Decision/status**：不为制造变短放宽限制；保留原结果；外审/用户观察PENDING

**修正关系**：只修本轮诊断导出平行option材料化/portal归属，未改路由算法或原R1路线

**Evidence references**：[S-d75083292af3b2](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R2/README_d7508329.md)；[S-3068b2de39fd8a](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R2/ROUTE_DIAGNOSIS_3068b2de.md)；[S-95d1ca1169a18a](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R2/BUSINESS_ROUTE_OPPORTUNITY_95d1ca11.md)；[S-f21ced4a9c374a](source_materials/method_docs/PED-AREA-CONNECTIVITY-R2/COMPONENT_LINEAGE_f21ced4a.md)；[S-7ce29799951ae3](source_materials/experiment_reports/PED-AREA-CONNECTIVITY-R2/REPRODUCIBILITY_7ce29799.md)；[S-0620aa5158fc9b](source_materials/review_reports/PED-AREA-CONNECTIVITY-R2/INDEPENDENT_REVIEW_0620aa51.md)；[S-4ef0ae1fcc75f4](source_materials/review_reports/PED-AREA-CONNECTIVITY-R2/AUTHOR_REVIEW_4ef0ae1f.md)；[S-4ebef3f7e70688](source_materials/method_docs/PED-AREA-CONNECTIVITY-R2/independent_source_weight_restoration_4ebef3f7.json)；[R-PED-AREA-CONNECTIVITY-R2](evidence/claims.html#R-PED-AREA-CONNECTIVITY-R2)。

**原图**：[F-75bb84915534d7](figures/maps/PED-AREA-CONNECTIVITY-R2/library_75bb8491.png)；[F-50e2bcc6f57b1b](figures/maps/PED-AREA-CONNECTIVITY-R2/north_far_50e2bcc6.png)；[F-b35be000636260](figures/maps/PED-AREA-CONNECTIVITY-R2/north_near_b35be000.png)。

## SMART_CITY_WALKABILITY_FOUNDATION_PG1

**日期／来源**：2026-11-12（原最终记录；封包后的恢复另记）

**状态**：INITIAL_FOUNDATION_DELIVERED_GATES_PENDING

**Question**：现有地图信息被保留到哪一步，独立验证数据是否已经可用？

**Motivation**：先区分导入、路由准入、显示与独立评价，避免继续用失真的图判断算法。

**Baseline**：六个冻结开发裁片及CONNECTIVITY-R1/R2历史输出

**Intervention**：逐对象信息审计；已有输出重绘；非校园数据发现；8次有限代价探针

**Data and sample unit**：6个已暴露上海scene；跨裁片306927原始记录（非去重独立对象）；5个新候选街区；8个工程探针

**Actual result**：53624个源对象有可显示几何，30420个原生线段准入；5候选中4矢量1元数据，1235feature=1063建筑+172人行面；可冻结完整合同0；批量成本构建7/8更慢。

**Positive evidence**：可以追查源对象—适配器—准入—渲染，不再把道路未入人行图当作地图被删除。

**Negative/inconclusive evidence**：没有可靠道路面/宽度/路缘；六上海裁片共享原生对象；无合格独立Blind；8探针无稳定加速。

**What it supports**：信息完整性审计、按模块的数据合同、工程代价负结果。

**What it does not support**：跨城泛化已证、5候选是5个已验证目标、公开Push已获准。

**Decision/status**：G0公开、G1视觉、G2分组仍待批准；两轨继续按门禁管理。

**修正关系**：后续修复交付回执闭合；不把封包前PENDING改成当时已通过。

**Evidence references**：[S-225a13e82717e6](source_materials/experiment_reports/SMART_CITY_WALKABILITY_FOUNDATION_PG1/FOUNDATION_REVIEW_225a13e8.md)；[S-87616d5a64b287](source_materials/experiment_reports/SMART_CITY_WALKABILITY_FOUNDATION_PG1/audit_findings_87616d5a.md)；[S-23ad32ebca2f91](source_materials/experiment_reports/SMART_CITY_WALKABILITY_FOUNDATION_PG1/README_23ad32eb.md)；[S-cfdf9552b34477](source_materials/metrics/SMART_CITY_WALKABILITY_FOUNDATION_PG1/family_lineage_cfdf9552.csv)；[S-4c9b674ebfb248](source_materials/metrics/SMART_CITY_WALKABILITY_FOUNDATION_PG1/current_graph_inventory_4c9b674e.json)；[S-fcaa11736043d4](source_materials/metrics/SMART_CITY_WALKABILITY_FOUNDATION_PG1/candidate_registry_fcaa1173.csv)；[S-15c06f988f6243](source_materials/metrics/SMART_CITY_WALKABILITY_FOUNDATION_PG1/dimension_contract_15c06f98.csv)；[S-91a25434b550be](source_materials/metrics/SMART_CITY_WALKABILITY_FOUNDATION_PG1/field_inventory_91a25434.csv)；[R-SMART-CITY-WALKABILITY-FOUNDATION-PG1](evidence/claims.html#R-SMART-CITY-WALKABILITY-FOUNDATION-PG1)。

**原图**：[F-9c6b727f017d64](figures/maps/SMART_CITY_WALKABILITY_FOUNDATION_PG1/sh-exhibition_9c6b727f.png)；[F-6e439695961fb1](figures/maps/SMART_CITY_WALKABILITY_FOUNDATION_PG1/sh-huangpu-01_6e439695.png)；[F-17ac7b954d3c84](figures/maps/SMART_CITY_WALKABILITY_FOUNDATION_PG1/sh-library_17ac7b95.png)。

## PG1_RESUME_STREET_SIDE_R1

**日期／来源**：2026-11-13 03:39:13+08（trial_summary完成字段）

**状态**：CANDIDATE_TOPOLOGY_ONLY_DEFAULT_R0

**Question**：缺少明确人行道几何时，侧别身份与条件沿街通道能否避免道路轴错误合并？

**Motivation**：原轴线表示会丢失道路两侧区别；原业务路线确实使用过道路轴。

**Baseline**：R0冻结道路轴／共享街道表示

**Intervention**：R1原生/明确侧别；R2加缺标假设侧道；跨路不新增假设过街

**Data and sample unit**：3预锁窗口×2查询×3方法=18格最终主矩阵；含6精确原生控制和12仅拓扑请求；24历史尝试/22实际solver

**Actual result**：R0：4连通+2零长度侧别别名；R1：3连通+1断开+2端点缺失；R2：4连通+2断开。R0默认未变。

**Positive evidence**：原生控制路径保持；缺标同侧可表达条件通道，缺证据不互通两侧。

**Negative/inconclusive evidence**：4m偏移只是SCHEMATIC；没有可靠道路宽度/路缘/road↔原生步道关联；无新增完整到门任务。

**What it supports**：道路轴与侧向逻辑身份分开是可实现的机制。

**What it does not support**：精确人行道位置、侧向净空或实走变短；4/6对3/6并非导航优胜。

**Decision/status**：候选R1/R2不自动升级；保留R0及全部失败、零长度和成本修正。

**修正关系**：首6个R0代价有错误，6次重测修复；累计24尝试不等于24个最终有效请求。旧native窗口后来确认不是博物馆门口。

**Evidence references**：[S-5d234c33dc5ec8](source_materials/experiment_reports/PG1_RESUME_STREET_SIDE_R1/DECISION_BRIEF_5d234c33.md)；[S-13375c19b0d9f7](source_materials/experiment_reports/PG1_RESUME_STREET_SIDE_R1/EXPERIMENT_BRIEF_13375c19.md)；[S-27910b4f02ba47](source_materials/experiment_reports/PG1_RESUME_STREET_SIDE_R1/street_side_findings_27910b4f.md)；[S-5805373c0d0cb7](source_materials/experiment_reports/PG1_RESUME_STREET_SIDE_R1/business_route_axis_usage_5805373c.md)；[S-4ca28e81fc1406](source_materials/experiment_reports/PG1_RESUME_STREET_SIDE_R1/module_contracts_4ca28e81.md)；[S-c104865a9cae28](source_materials/experiment_reports/PG1_RESUME_STREET_SIDE_R1/next_acquisition_proposal_c104865a.md)；[S-fbbb5258703043](source_materials/metrics/PG1_RESUME_STREET_SIDE_R1/query_results_fbbb5258.csv)；[S-f8bfc5c09295f9](source_materials/metrics/PG1_RESUME_STREET_SIDE_R1/trial_summary_f8bfc5c0.json)；[R-PG1-RESUME-STREET-SIDE-R1](evidence/claims.html#R-PG1-RESUME-STREET-SIDE-R1)。

**原图**：[F-f8f8e6f915a2be](figures/maps/PG1_RESUME_STREET_SIDE_R1/missing_comparison_f8f8e6f9.png)；[F-5331ea6942dba5](figures/maps/PG1_RESUME_STREET_SIDE_R1/missing_detail_5331ea69.png)；[F-b114e3c05cc076](figures/maps/PG1_RESUME_STREET_SIDE_R1/native_comparison_b114e3c0.png)。

## PG1_MAP_CONTEXT_VISUAL_REPAIR_R1

**日期／来源**：2026-11-13（固定包及收尾记录）

**状态**：SUPERSEDED_SCENE_BINDING_FOR_MUSEUM

**Question**：把街区底图完整恢复后，三个方法能否在相同底图比较？

**Motivation**：上一轮图过度只显示算法选线，读者难认真实场景。

**Baseline**：冻结街区侧R0/R1/R2结果

**Intervention**：恢复原始地图上下文；同窗同尺度四层呈现；未求路

**Data and sample unit**：3旧窗口；新增求路0；旧24次尝试22次solver不变

**Actual result**：补全源—图对象保留清单与真实PNG/SVG；但native以way/39764359步道定窗，原320m窗不含实际博物馆建筑。

**Positive evidence**：源到显示一致性可检查，图层保留改善。

**Negative/inconclusive evidence**：场景绑定错误，不能将该native窗称上海博物馆人民广场馆；视觉内部一致不等于真实目标正确。

**What it supports**：旧窗口内部的信息呈现机制。

**What it does not support**：目标馆体正确、门口接近路线、现实地理精度。

**Decision/status**：对应Museum场景解释由RECONSTRUCTION-R2正式替换；历史图醒目标记保留。

**修正关系**：必须与后续TARGET_SCENE_CORRECTION.md同读，不作为最新博物馆图。

**Evidence references**：[S-59bb26dccabfb9](source_materials/experiment_reports/PG1_MAP_CONTEXT_VISUAL_REPAIR_R1/VISUAL_REPAIR_REPORT_59bb26dc.md)；[S-802d8b2d8e0889](source_materials/review_reports/PG1_MAP_CONTEXT_VISUAL_REPAIR_R1/FINAL_STATUS_802d8b2d.json)；[R-PG1-MAP-CONTEXT-VISUAL-REPAIR-R1](evidence/claims.html#R-PG1-MAP-CONTEXT-VISUAL-REPAIR-R1)。

**原图**：[F-e9aaec36a29eb8](figures/maps/PG1_MAP_CONTEXT_VISUAL_REPAIR_R1/context_full_e9aaec36.png)；[F-582857f03c850d](figures/maps/PG1_MAP_CONTEXT_VISUAL_REPAIR_R1/R0_R1_R2_same_extent_582857f0.png)；[F-2017a02e796675](figures/maps/PG1_MAP_CONTEXT_VISUAL_REPAIR_R1/context_full_2017a02e.png)。

## PG1_MAP_CONTEXT_RECONSTRUCTION_R2

**日期／来源**：2026-11-13 05:36–06:17+08（实际任务记录）

**状态**：READY_FOR_GPT_REVIEW_G1_USER_PENDING

**Question**：实际显示的是否真正是上海博物馆人民广场馆，其与黄陂北路关系是否正确？

**Motivation**：上轮地图绑定了附近步道，不能以对象画全代替场景正确。

**Baseline**：冻结源及旧R0/R1/R2记录；不改算法、不求路

**Intervention**：建筑way/161090899+原南main/北exit+完整七段黄陂北路共同定窗；五视野同底图

**Data and sample unit**：914个全景源对象；5视野；8PNG+8SVG；新算法/求路/下载/API均0

**Actual result**：建筑及两门身份核对；七段黄陂tertiary组成约638.126m源中心线；全景820×820m；旧诊断明确在西北步道。

**Positive evidence**：目标、范围、标签和源到图对应已校正；干净解包26份输出逐字节一致。

**Negative/inconclusive evidence**：REAL_WORLD_GEOMETRY_UNVERIFIED；旧诊断不是到门业务任务；现实开放、同层和公众通行未知。

**What it supports**：固定源中的目标身份、上下文与三变体正确地理叠加。

**What it does not support**：现场精度/公众可达已验证、整个PG1通过。

**Decision/status**：技术材料交付完成，GPT与用户验收仍待；本交接轮不更改门禁。

**修正关系**：正式纠正VISUAL_REPAIR-R1的native场景解释；24/22记录及原门坐标保持。

**Evidence references**：[S-e3ea42c0caa509](source_materials/experiment_reports/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/TARGET_SCENE_CORRECTION_e3ea42c0.md)；[S-88317d47d99d88](source_materials/experiment_reports/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/TARGET_IDENTITY_AUDIT_88317d47.md)；[S-7aa91ef8cd8c13](source_materials/experiment_reports/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/REAL_SCENE_VALIDATION_7aa91ef8.md)；[S-0d2be6fb393362](source_materials/experiment_reports/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/source_reference_comparison_0d2be6fb.md)；[S-ea3ae0c8850e0d](source_materials/metrics/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/target_objects_ea3ae0c8.json)；[S-f384ec3aa22281](source_materials/metrics/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/huangpi_north_road_objects_f384ec3a.json)；[S-f9911f68cb1686](source_materials/metrics/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/window_definition_f9911f68.json)；[S-b3f868c5136b1d](source_materials/metrics/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/source_to_render_inventory_b3f868c5.csv)；[R-PG1-MAP-CONTEXT-RECONSTRUCTION-R2](evidence/claims.html#R-PG1-MAP-CONTEXT-RECONSTRUCTION-R2)。

**原图**：[F-a04b3d9a76d787](figures/maps/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/R0_R1_R2_same_extent_a04b3d9a.png)；[F-667badf9a2f6ab](figures/maps/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/huangpi_north_road_detail_667badf9.png)；[F-9f000c24cb0941](figures/maps/PG1_MAP_CONTEXT_RECONSTRUCTION_R2/north_exit_detail_9f000c24.png)。
