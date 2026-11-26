# OSM–Geoapify R4

开放空间边缘接入与已登记入口可达性。开发对象为上海博物馆人民广场馆南侧广场，适用性对照沿用 R3 冻结五栋。

[打开交互审查页面](visuals/index.html) · [实验结果](04_EXPERIMENT_RESULTS.md) · [逐边证据](data/added_edges.csv) · [逐入口结果](data/entrance_access.csv)

## 阅读顺序

1. [研究合同](01_RESEARCH_CONTRACT_AND_SCOPE.md)和[开放空间审计](02_OPEN_SPACE_FEATURE_AUDIT.md)。
2. [边缘连接方法](03_EDGE_CONNECTION_METHOD.md)、[实验结果](04_EXPERIMENT_RESULTS.md)及[两侧数据能力](05_DUAL_PATH_INPUT_CAPABILITY.md)。
3. [局限与后续判断](06_LIMITATIONS_AND_NEXT_DECISIONS.md)、[独立审核](audits/INDEPENDENT_REVIEW.md)。

## 离线复跑

交互页面直接用浏览器打开。包内保留六个原生裁片、冻结场景和旧路线，完整上海 PBF 与历史托管 PNG 以源路径和 SHA 引用。以下实验重放无需账户或网络。

```powershell
python -X utf8 -B -m src.run_experiment
python -X utf8 -B -m src.run_dual_paths
python -X utf8 -B -m src.build_visuals
python -X utf8 -B -m pytest -q -p no:cacheprovider
```

`src.prepare_sources` 与 `src.prepare_ir` 是原工作区可用的取证脚本，依赖同级历史目录与原始任务附件。已解包的审查目录可用留存的冻结输入直接执行实验和制图。Python 及库版本见 requirements.txt。底层 OSM 矢量遵循 ODbL。托管几何保留来源与署名，许可边界沿用 R3 审计。

[原始资料索引](data/manifest.csv) · [R3 接口取证](audits/ir_evidence.csv) · [R3 许可记录](inputs/r3/01_SOURCE_AND_PERMISSION_AUDIT.md)
