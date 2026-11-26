# R4-WALKABILITY-R3 审查入口

打开 [离线交互地图](visuals/index.html)。同一页面包含草地修复、北门四态区域、多端点查询、受控遮蔽、负例及全程分层六张图。若本地文件链接无法在 Codex 中打开，从解包目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py
```

使用终端打印的本机链接。服务只监听 127.0.0.1。前台终端可用 Ctrl+C 停止。离线 HTML 和导出图不需要外部地图服务。

- [实测结果](RESULTS.md)
- [区域对象与路线](REGION_RECONSTRUCTION.md)
- [方法与评价边界](SCOPE_AND_METHOD.md)
- [自然语言验收](USER_REVIEW_NOTES.md)
- [独立技术复核](audits/INDEPENDENT_REVIEW.md)
- [防泄漏复核](audits/LEAKAGE_REVIEW.md)

## 从固定包复现

使用 Python 3.12 和 `requirements.txt` 中的依赖。交付包保留一份精确 R2 审查 ZIP，其内含 R4-REV1 和北门 R1 冻结包，运行时各解包一次。历史工程的 Windows 路径只用作本机保护回执。

```powershell
python -X utf8 -B scripts/replay_review.py <OPEN_REVIEW.zip的路径> <新目录> --browser '<Edge或Chromium程序路径>'
```

重放包含新目录验包、S 重跑、独立 S 核验、北门推断、遮蔽任务、几何核验、交互页重画和本轮合成测试。机器可读文件与网页均用 EPSG:32651 计算米和面积，导出 GeoJSON 为 WGS84。

来源为冻结 OpenStreetMap © OpenStreetMap contributors。Geoapify 仅保留已存档的服务比较记录。
