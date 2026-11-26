# 上海博物馆北侧出口门前接入 R1

[打开同底图对照](visuals/index.html) · [实测结果](04_RESULTS.md) · [独立审核](audits/INDEPENDENT_REVIEW.md)

范围只覆盖原登记出口 `node/6897145227` 和北侧铺装步道之间的约 7.95 米。N0、N1、N2 共用此前小试的原生路网前缀。R4-REV1 与此前小试均为冻结来源。本轮现场核验与新外部请求均为 0。

## 离线运行

Python 3.12.6，依赖见 requirements.txt。审查包提供便携源文件，运行时输出到新目录。

```powershell
python -X utf8 -B src/run_experiment.py --input-root inputs/source --prior-root inputs/prior_trial --output-root replay_north --config config/frontage.json
python -X utf8 -B src/build_visuals.py --input-root inputs/source --run-root replay_north --output replay_north/visuals/index.html
python -X utf8 -B -m pytest -q -p no:cacheprovider tests
```

原页面在 `visuals/index.html`，可直接打开。图内灰色虚线显示 N0 的未接缺口，橙色虚线和紫色虚线分别表示 N1 和 N2 的假设路线。近景与全程共享相同底图和视野。证据记录可在页面查看或下载。

[输入审计](01_INPUT_AUDIT.md) · [原始空间关系](02_NORTH_FRONTAGE_EVIDENCE.md) · [方法](03_N1_N2_METHODS.md) · [决策和边界](05_LIMITATIONS_AND_DECISION.md)
