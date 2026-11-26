# 中期研究材料R2｜总索引

仅整理已有研究材料，不制作PPT、讲稿或新增实验。全部地图源于冻结OSM，不是高德截图或现场照片。

**事件5的拟定因果关系缺少历史证据，不作为已验证叙事；其余事件有可用主图。**

离线查看：[图像总览](index.html)。先读[网页版GPT交接说明](HANDOFF_FOR_GPT_WEB.md)。

1. [研究问题：复杂建筑的“到门”为什么难](01_problem_definition/caption_zh.md)

   已知建筑位置和登记门，仍不等于外部步行网络能连续接到门。

   [主图](01_problem_definition/main_figure.png) · [数据](01_problem_definition/metrics.csv) · [来源](01_problem_definition/source_traceability.md)

2. [初始真实失败：南门有登记，但线网未接通](02_line_only_failure/caption_zh.md)

   旧 R4 的南门存在于地图，原生线网却没有入口图节点。

   [主图](02_line_only_failure/main_figure.png) · [数据](02_line_only_failure/metrics.csv) · [来源](02_line_only_failure/source_traceability.md)

3. [步行线不是全部：广场面是另一类空间输入](03_walkable_area_needed/caption_zh.md)

   南广场已标为步行面，但“画得出面”和“能在面内寻路”是两回事。

   [主图](03_walkable_area_needed/main_figure.png) · [数据](03_walkable_area_needed/metrics.csv) · [来源](03_walkable_area_needed/source_traceability.md)

4. [第一版保守策略：先在步行面边缘寻路](04_conservative_edge_band/caption_zh.md)

   R4-REV1 在已标步行面内派生边缘网络，并保留内环和门前端口检查。

   [主图](04_conservative_edge_band/main_figure.png) · [数据](04_conservative_edge_band/metrics.csv) · [来源](04_conservative_edge_band/source_traceability.md)

5. [早期未到南门：可证实的结果与解释缺口](05_early_endpoint_and_evidence_gap/caption_zh.md)

   能确认早期南门未接通；不能确认“只恢复北侧”是既有实验事实。

   [主图](05_early_endpoint_and_evidence_gap/main_figure.png) · [数据](05_early_endpoint_and_evidence_gap/metrics.csv) · [来源](05_early_endpoint_and_evidence_gap/source_traceability.md)

6. [南广场参与计算后：南门条件接通](06_south_plaza_connection/caption_zh.md)

   在 R4-REV1 中，南广场派生边和门前端口实际参加路线，终点到原南门残差为零。

   [主图](06_south_plaza_connection/main_figure.png) · [数据](06_south_plaza_connection/metrics.csv) · [来源](06_south_plaza_connection/source_traceability.md)

7. [草地背景不能抹掉已有步道](07_native_walkway_grass_fix/caption_zh.md)

   WALKABILITY-R2 恢复原生有效步道后，同一北侧接点路线减少约71.72米。

   [主图](07_native_walkway_grass_fix/main_figure.png) · [数据](07_native_walkway_grass_fix/metrics.csv) · [来源](07_native_walkway_grass_fix/source_traceability.md)

8. [北出口7.95米：条件接入不等于通行证明](08_north_exit_conditional_access/caption_zh.md)

   N1和N2均补成条件路线；N2没有在本例增加同层或通行证据。

   [主图](08_north_exit_conditional_access/main_figure.png) · [数据](08_north_exit_conditional_access/metrics.csv) · [来源](08_north_exit_conditional_access/source_traceability.md)

9. [从边缘绕行到完整合法步行面](09_full_face_routing/caption_zh.md)

   同源、同起终点与约束下，完整面路线可减少表示方式造成的绕行。

   [主图](09_full_face_routing/main_figure.png) · [数据](09_full_face_routing/metrics.csv) · [来源](09_full_face_routing/source_traceability.md)

10. [局部机制改善，不保证业务路线收益](10_local_vs_business_gain/caption_zh.md)

   新增面即使接入了图，也可能更贵、处于其他分量，或没有当前可用接口。

   [主图](10_local_vs_business_gain/main_figure.png) · [数据](10_local_vs_business_gain/metrics.csv) · [来源](10_local_vs_business_gain/source_traceability.md)

11. [当前阶段与下一阶段](11_current_stage/caption_zh.md)

   当前OSM末段规划线以规则、空间表示与典型场景原型为主，多场景独立验证仍待开展。

   [主图](11_current_stage/main_figure.png) · [数据](11_current_stage/metrics.csv) · [来源](11_current_stage/source_traceability.md)

12. [阶段推进链与证据边界](12_research_progress/caption_zh.md)

   阶段推进来自空间表示和实现修复；每一步都有适用范围，未形成普遍到达证明。

   [主图](12_research_progress/main_figure.png) · [数据](12_research_progress/metrics.csv) · [来源](12_research_progress/source_traceability.md)
