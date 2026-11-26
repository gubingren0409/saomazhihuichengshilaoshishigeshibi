# 源完整性与路线对照图设计记录

本组包含两张源图和六张真实路线对照图。源对象、机制查询及端点沿用冻结集合；绘图没有调用求解器、地图服务或外部 API。图中路线直接读取保存的正式响应，输出旁的 JSON 记录实际文件 SHA、运行 ID、代码版本和原生端点坐标。

| 图 | 要回答的问题 | 正式输入与显示范围 |
|---|---|---|
| museum_source_overview | 两旧面及东北侧步道的直接间隙，与源中已有线链是否能区分？ | 冻结源 P、Ω、原始线及共享原生节点。已有源线链不等于整链进入当前图。 |
| six_scene_source_inventory | 六裁片的遗漏、层级拒绝和覆盖拒绝是否完整守恒？ | 149 场景候选 = 6 旧准入 + 124 新准入 + 7 层级拒绝 + 12 覆盖拒绝；130 准入场景记录按版本及时间戳去重为 88 个源对象，其中全局新增 82 个。 |
| mechanism_M02_source_complete | 纳入遗漏的明确步行面后，同端点路线如何变化？ | FORMAL-065 / 066：33.34 → 27.14 m。保留原未变数学核的真实代码 SHA。 |
| mechanism_M04_exact_stitch | 共边面精确接图是否恢复完整路线？ | FORMAL-074 / REPLAY-FORMAL-075：图不连通 → 158.20 m。终点是原生节点，明确标为非门。 |
| mechanism_M06_no_route_change | 已入图的条件接缝是否实际用于路线？ | REPLAY-FORMAL-083 / 084：均 171.37 m；真实约 1.00 m 接缝已入图，但路线未用。 |
| business_south_no_route_change | 南门业务请求是否受新增边影响？ | FORMAL-001 / 004：均 148.86 m，新增接口和接缝使用长度均为 0；细节图显示两路线原先就使用的共享节点。 |
| business_north_same_route | 使用精确接口是否等于几何路线改善？ | FORMAL-009 / 012：均 299.53 m，逐段坐标相同。B3 精确接口约 0.099 m；原有门前假设段 12.53 m 未变。原登记出口只作到门外请求。 |
| historical_F1_same_route | 已锁历史长查询能否改善？ | FORMAL-057 / 060：均 682.44 m，逐段坐标相同；B3 精确接口 4.20 m、条件接缝 0 m。历史请求尚未唯一绑定用户截图。 |

## 视觉编码与候选取舍

遵循任务提供的 Visual System v2.8 和已安装 publication-plots Skill，采用确切 P2 色板。Paper `#FCFAF7`、Ink `#2D3238`、Blue `#D3EAF5`、Apricot `#F5D9B8`、Rose `#E8C7D3`、Violet `#D7D3EA`；中文使用 Microsoft YaHei。源 P 轮廓与合法计算面 Ω 分开；源草地、公园、建筑和水体保持独立语义。机动车中心线不代表路宽或新放行步行边。

六幅全裁片地理图曾实际导出并查看：三公里范围内的步行面过小，读图负担高，因此正式盘点图改为互斥计数条形图。完整六场景原始几何仍可在交互诊断中查看。博物馆源图采用街区总览加两处真实细节。路线采用同底图、同端点、同视野的并排对照，使不连通结果、路线未变和条件假设都能保留；没有声称另一个路线布局已经实际试制。

地图统一为 EPSG:32651，坐标与比例尺单位为米。源边界、门和原生端点均未移动；没有平滑路线、补画道路或扩张 P/Ω。对照路线为玫瑰色虚线，比较路线为墨色实线，条件接缝与原有门前假设用不同橙色线型表示。

## 输出、审查与限制

正式发布目录仅为 `visuals/`，每图提供 PNG、完整矢量 SVG、PDF 与机器可读 JSON。SVG 经本机 Edge 原生渲染检查，包含零个位图 image 元素；浏览器阻断全部网络请求。PNG/SVG 是主要审查入口。

PDF 为避免已实际观察到的后端填充、虚线与裁剪笔画失真，对背景、非准入上下文线及 P 的虚线轮廓使用同图 300 dpi 栅格显示；Ω、准入原生步行线、真实路线和文字保持矢量。此格式回退不改变源数据或分析结果，不将 PDF 宣称为全矢量。最终逐页 200 dpi 检查及未完成事项以 `exports_qa.json` 为准。

`design_and_review.json` 保存实际读取的设计规范与 Skill、候选取舍、输出身份、版本兼容说明和修复记录；`route_comparison_spec.json` 固定六例顺序及实际响应路径。截图绑定仍为 `SCREENSHOT_REQUEST_UNBOUND`，用户观察仍为 `PENDING_USER_OBSERVATION`，同事审查不替代用户确认。

重建命令：

```powershell
python -X utf8 -B scripts/plot_connectivity.py --source-only --comparison-spec visuals/route_comparison_spec.json --output-dir visuals --check-exports
```

检查用 PDF/SVG 渲染页留在 `figures/visuals/render_checks/`，不重复收入正式图件目录或 ZIP。
