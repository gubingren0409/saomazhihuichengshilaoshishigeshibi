# 证据版本入口

当前主诊断以`results/FINALIZED.json`绑定的最终机器文件及根CSV为准；其状态中的UI_PENDING只反映主诊断冻结当时，后续地图作者、独立浏览器和封包回执分开绑定。不要把这份核心清单当作全项目实时状态。

`results/map_diagnosis_materialized.json`是最终聚合器的中间输入，保留用于追查/重建；`results/map_diagnosis.json`是最终大机器数据；`results/map_ui.json`与`visuals/map_payload_manifest.json`是无损共享池和实际HTML显示版本。页面不新增求路，完整原结果见根CSV。

`audit/*phase1*`、`*_first_*`、`*_initial_*`和独立初次报警是历史/修复实物，不替代最终结果。源码修改时点、原8调用的后绑定事实和0额外SSSP均保留于各自记录，不伪造事前登记。`audits/independent_browser_layout_before_fix.json`保留已发现的布局失败；`independent_browser_layout.json`为绑定新HTML SHA的最终四案例复验。

ZIP本身的SHA不能写入其自身成员形成循环，最后解包复验和最终状态在`delivery/`包外，均须核对所指ZIP的SHA。新包为增量证据；历史原始数据/来源独立核验仍需另提供SHA固定的R1 ZIP，不宣称整个历史自包含。
