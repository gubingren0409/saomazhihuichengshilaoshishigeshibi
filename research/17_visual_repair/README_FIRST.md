# 先看完整街区，再看冻结算法叠加

本轮：PG1-MAP-CONTEXT-VISUAL-REPAIR-R1，属于原PG1的G1可视化整改。只提取和重绘既有数据，没有重新求路、修改算法或下载地图。R0仍为默认，父Goal未完成，用户视觉验收仍待完成。

- [交互地图总览](index.html)：四个视图使用同一底图与视野。A为原始上下文，其余为R0/R1/R2冻结叠加。默认两列，便于正常屏幕阅读。
- [整改报告](VISUAL_REPAIR_REPORT.md)
- [对象保留清单CSV](audit/source_to_figure_inventory.csv) / [JSON](audit/source_to_figure_inventory.json)
- [冻结结果未改变核验](audit/protection_and_drift.json)
- [独立审核目录](reviews/)

页面支持三窗口、六查询、全景/路侧局部、19类图层、对象原生ID和来源检查，以及当前视野/查询JSON和SVG导出。历史首跑R0只在历史记录区显示，主地图始终使用最终有效结果；选择历史记录不会替换当前算法结果。

## 打开和停止

本机实际服务：`http://127.0.0.1:53521/`。也可以直接双击index.html离线打开；不需要在线瓦片、API Key、CDN或地图服务。

在本目录前台启动：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53521
```

前台按Ctrl+C停止。本次隐藏服务PID为119704，仅停止这一实例可用 `Stop-Process -Id 119704`。旧53511服务没有被停止或修改。

## 只重建地图的命令

```powershell
python -X utf8 -B scripts/extract_context.py --fragments
python -X utf8 -B scripts/render_maps.py
python -X utf8 -B scripts/extract_context.py --finalize-inventory
python -X utf8 -B scripts/build_page.py
```

这些命令只解析包内原始OSM片段、绘制已保存边和组织页面；不构图或调用求路。不要在本轮运行历史算法、verify-graphs或合成路线实验。

每个窗口的figures子目录有context_full、三个方法单图、R0_R1_R2_same_extent和local_detail，各有PNG及可编辑SVG，共18PNG+18SVG。交互地图可调整视野；静态全景保持原固定320m窗口，局部图150m。x/y采用同一米制比例，不能把4m示意偏移当实测路宽。

## 输入与边界

冻结结果来自PG1_RESUME_STREET_SIDE_R1_REVIEW_FIXED.zip，SHA256 `6b2db66e8347603c2aa346810846f4d6c5cf39e2e830f12a162b0e6c6e9485ab`；冻结结果本地Commit为 `1ab7fd75704d98e85fe4e69a85dc828e7df2ffb5`。旧24次尝试、22次实际求解不变。

本包包含三窗口OSM源片段和原生引用、来源和导入lineage、必要冻结显示输入、制图代码和图件。可离线重建本轮地图；从全量原始裁片重新穷举窗口覆盖仍依赖原工程三个全源文件，按SHA引用，不声称整个历史工程离线自包含。

“完整”指固定窗口内已有源对象的保留与呈现，不是现实道路调查已完整。窗口名称来自原始场景，目标建筑可能不在该固定窗口内；原生POI“上海市历史博物馆”不是目标“上海博物馆”。没有为包含目标馆而扩大窗口。

© OpenStreetMap contributors，沿用既有ODbL来源记录。道路面、已核验宽度/路缘信息在这些窗口缺失，未伪造。源码许可证未由用户选择；本包为本地私有审查材料，不是获批公开文件清单，不可直接替代原38项公开候选。
