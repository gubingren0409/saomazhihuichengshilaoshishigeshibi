# R4-WALKABILITY-R2 审查入口

打开 [离线交互地图](visuals/index.html)，可切换草地步道、北门和受控案例。浏览器拒绝本地文件链接时，在本目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py
```

脚本只监听 `127.0.0.1`，自动分配空闲端口并打印地址。在另一终端运行 `python -X utf8 -B scripts/serve_review.py --stop` 停止，或在原终端按 Ctrl+C。端口仅在本机有效。单文件 HTML 可离线查看，也可打开 [静态图](visuals/figures/) 中的 SVG。

- [实测结果](RESULTS.md)
- [方法与证据边界](SCOPE_AND_METHOD.md)
- [自然语言验收入口](USER_REVIEW_NOTES.md)
- [作者检查](audits/AUTHOR_CHECK.md)
- [独立复核](audits/INDEPENDENT_REVIEW.md)

## 命令行复现

推荐 Python 3.12。在 ZIP 解包目录先安装 `requirements.txt` 所列依赖，再按下列命令复现。源码使用原生 OSM 节点/路段，既有两份冻结包在 `references/frozen_archives` 随附。交互页不需要 Python 依赖。

```powershell
python -X utf8 -B scripts/materialize_inputs.py
python -X utf8 -B -m src.run_semantics --output-root replay
python -X utf8 -B -m src.run_inference natural --output-root replay
python -X utf8 -B -m src.run_inference masked --output-root replay
python -X utf8 -B src/evaluate_masking.py --predictions replay/runs/masked_predictions.json --output replay/runs/masking_evaluation.json --visual replay/data/masking/review_cases.geojson
python -X utf8 -B -m pytest -q tests -p no:cacheprovider
```

从空目录核查整个审查包及重放可使用 `python -X utf8 -B scripts/replay_review.py <审查包ZIP> <全新目录> --browser <本机Chromium或Edge程序>`。浏览器存在时额外检验和重画实际页面。选择、推断和回放从原始几何执行，结果文档保留各样本分母及证据级别。

## 归属

开放数据 © OpenStreetMap contributors。保留冻结输入原有的来源和归属说明。Geoapify 仅引用冻结基线。本轮修改作用于结构化 OSM 输入。
