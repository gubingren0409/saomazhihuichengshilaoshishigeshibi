# OSM 与 Geoapify 同场景小试

[匿名图册](visuals/blind_review/index.html) · [人工评分](visuals/blind_review/score.html) · [空白 CSV](06_USER_SCORE_SHEET.csv) · [MapLibre 路线查看](visuals/route_comparisons/index.html)

双侧实图已补齐，当前证据见 [双侧补齐记录](09_AB_COMPLETION_RESULTS.md)。

首例为上海博物馆人民广场馆。图册中的两档视野共享同一场景。源署名可能透露服务身份。评分表为空，用户确认前私有映射不进入公开审核包。

## 复跑与恢复

在本试验目录运行。源裁片已包含在审查包，离线复跑无需全市下载、服务 Key 或 OSM 公共瓦片。

```powershell
python -X utf8 -B -m src.run_local --output runtime/replay
python -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp runtime/test_isolated tests
```

审查包里的图册为封存版，直接打开即可。图册重建在原试验目录进行，以沿用私有映射和空表编号。

在原试验目录续接 Geoapify 时，通过本机 `.env` 提供 `GEOAPIFY_API_KEY`。已确认该项目可用免费额度足够时，运行：

```powershell
python -X utf8 -B -m src.run_geoapify --confirmed-free
python -X utf8 -B -m src.prepare_gallery
```

首例执行器预算为两个静态图和一次步行。真实尝试留下占额锁。遇到许可、权限、配额、网络或范围证据问题时查看回执，再决定是否有条件继续。自动化只处理工程指标和公开授权允许的地图用途。用户视觉判断仍按独立流程填写。

| 文档 | 内容 |
| --- | --- |
| [来源及许可](01_SOURCE_AND_PERMISSION_AUDIT.md) | 产品条款、OSM 数据与公共瓦片、额度 |
| [样本与视野合同](02_SAMPLE_AND_VIEWPORT_CONTRACT.md) | 冻结点、WGS84 与目标身份 |
| [工程实现](03_API_AND_RENDER_IMPLEMENTATION.md) | 引擎、投影、工具与离线复现 |
| [试验结果](04_EXPERIMENT_RESULTS.md) | 分支、失败、精度和代价 |
| [盲评说明](05_HUMAN_REVIEW_GUIDE.md) | 空表、评分凭证及揭盲条件 |
| [保留结论](08_DECISION_AND_NEXT_STEPS.md) | 当前证据边界和补证 |
| [独立技术审核](audits/INDEPENDENT_REVIEW.md) | 几何、输入与离线页面审核 |
