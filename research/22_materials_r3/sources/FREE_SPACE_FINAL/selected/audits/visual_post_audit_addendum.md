# 权限面导出遗漏：可视化增量

源数据角色最终审核发现，`W7a6b5a10076_G_080` 的原观测导出没有包含 `way/178730989` 的闭合停车场权限面。原始标签为 `access=private, amenity=parking`。这不是新下载地图或现场资料。

本增量仅消费 `data/access_area_interpretations.json` 与 `audits/access_area_prediction_impact.json` 的审后源证据；不改变预测器输入、区域、图、门、查询或路线，不再构建区域。

原停车面416.8123084959293m²；固定30m域内128.38855916051673m²。独立制图载荷检查重新相交原metric格片与该停车面，M1-C在此为UNKNOWN，F0/F1均为ASSUMED_PASSABLE，面积128.38855916128438m²（浮点差约7.7e-10m²）。这是来源中已记录权限限制没有进入观测导出的已知区域冲突，不能继续声称所有权限检查完整。

重新检查本例两条查询Q1/Q2：F0/F1确实相对M1-C新增可达，但选中路线进入private内部的长度均为0m。不得把这一区域误放写成两条实际路线违规，也不得据此抹掉区域权限缺陷。

页面独立红斜纹层名为 `POST_AUDIT_SOURCE_RESTRICTION`，`predictor_input=false`、`data-visibility=post-audit-review-only`。它与原模型的杏色／灰色区域同时显示，可单独关闭。关闭该层不改变原表面或图hash。页面顶部和此案例同时标注“1/25主任务权限面导出gap待修”；没有将所有参考外扩张归为错误。

`#risk` 默认打开该案例。仅新增 `07-private-parking-gap.png/svg`，六张原已验图保持原字节。原六图的网页与浏览器回执保存为 `visual_*_before_postaudit.json`；其案例数据仍有效，新的顶部说明与图例属于本次增量。

最终新增页面SHA与实际浏览器核验以 `visual_build.json`、`visual_geometry_check.json`、`visual_browser_check.json` 为准。执行 `python -X utf8 -B scripts/check_free_visuals.py --audit-only` 只生成第七张，仍对新页面进行file/HTTP和交互测试。此图是审后负结果展示，不是已经修复算法或补齐输入的证明。
