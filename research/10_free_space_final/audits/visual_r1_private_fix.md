# R1权限面修复：当前与R0历史地图

制图角色 `/root/free_visuals` 读取实际新预测和封存R0预测，未调用区域分类器、图构造器或寻路器。生产的最后两次区域构建及总预算由父任务独立记账；此渲染阶段新增预测构建为0。

启用当前图之前，实际核对 `access_policy_FINAL_R1.json` 的 `PASS_SOURCE_ACCESS_REPAIR_WITH_LIMITS` 和独立输入审查的PASS，精确SHA绑定在 `config/visual_release.json`。这只用于允许显示已实际完成的源约束修复，不代替父任务的最终全量评价和冷重放审核。

当前页面包含26个案例，78个当前主方法载荷和3个R0历史方法载荷。专用 `#privatefix` 四图将同一观测、同一参考及查询下的 R0-F0 与当前 M1-C/F0/F1 并列。`#risk` 可切换 R0/R1，旧共同约束和新V3共同约束分别显示，原始门／端点不移动。

R0实际预测、原约束和图来自 `runs/superseded/W7_PRIVATE_R0/`；原Atlas来自 `runs/production_versions/R0_SEALED/visuals/index.html`。`visuals/r0_index.html` 是原Atlas的逐字节副本，原固定R0包SHA为 `2b5154e9e80afccd8a04901e7d3e81630dddbe7f50964c6f2ba005a5ce8b595b`。旧07图不覆盖，页面将其明确称为R0历史反例。

V3将原生 `access=private, amenity=parking` 的 `way/178730989` 闭合面作为负约束实际提供给预测器。当前三个方法在30m域内均将约128.388559m²标为RESTRICTED；新图不再说“当前算法未看到”或“当前仍未修”。原R0-F0的同一位置仍按其实际旧预测显示为假设可行，不重写历史。

独立制图载荷脚本重新计算当前格片与原面相交，限制面积128.38855916047m²；残余约6.8e-10m²为数值误差，低于1e-6m²合同容差。Q1/Q2选中路线进入private内部的长度仍为0m。26案例及3个历史载荷共1,306,088个顶点核对通过，最大显示取整误差0.00069495m。

首次R1目视检查发现图例仍沿用R0“非算法输入”的旧短句，尽管当前标题、数据字段和开关已正确。修正为“权限核对：R0漏导／V3已导入”，随后重新构建当前页面、重算几何并执行file/HTTP、版本切换、四图、SVG和PNG导出测试。该修正未修改生产预测或原七张图。

`scripts/check_free_visuals.py --fix-only` 仅生成 `08-private-before-after.png/svg` 和一个PNG导出验证样例，不重画前七张。冷重放使用同一参数，可配合 `--figure-output` 将核验图写到独立目录。

本图只说明这个已发现的地图负约束导出遗漏已修。它不证明未标障碍都已排除、不证明公众当前可走、不把北门exit变成入馆入口，也不改变同源配对诊断的评价身份。最终页面SHA、浏览器检查及ZIP重放结论以最新对应回执为准。
