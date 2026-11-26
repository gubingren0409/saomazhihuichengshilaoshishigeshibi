# OSM–Geoapify R3 工程选型小试

[匿名图册](visuals/blind_review/index.html) · [空白人工评分](visuals/blind_review/score.html) · [统一底图与细节](visuals/routes/index.html) · [失败和未知](visuals/failure_cases/index.html)

R3 与旧工程隔离。上海博物馆的旧评分和地图逐字节保留，其他场景在各路线请求前冻结。比较同一地理任务。底图、路由返回、实际末点、入口身份和现场通行分开记录。

## 技术证据

- [许可](01_SOURCE_AND_PERMISSION_AUDIT.md) · [样本合同](02_SAMPLE_AND_VIEWPORT_CONTRACT.md) · [实际结果](03_PAIRED_COMPARISON_RESULTS.md)
- [历史评分](04_USER_FEEDBACK_TRACEABILITY.md) · [双路径判断](05_DECISION_ON_TWO_PATHS.md) · [人工评分指南](06_HUMAN_REVIEW_GUIDE.md)
- [共同接口](08_COMMON_INTERMEDIATE_REPRESENTATION.md) · [下一阶段机制合同](09_DUAL_PATH_ALGORITHM_ROADMAP.md)

## 离线复现

Python 3.12.6，固定依赖见 requirements.txt。运行离线命令：

```powershell
python -X utf8 -B -m src.build_common_ir
python -X utf8 -B -m src.compare_r3
python -X utf8 -B -m src.build_reports
python -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp runtime/pytest tests
python -X utf8 -B -m src.browser_check_r3
```

图册已随包冻结，浏览器可直接打开。需要重建时在原 R3 工作目录执行 `python -X utf8 -B -m src.gallery_r3`，使用本机原私有映射，已有评分保持原样。单独解包时可复核冻结图册和真实结果。实际托管调用有单独有界账本，正常审查使用归档回放。完整城市 PBF 和本机服务凭据属于原运行依赖，审查包提供裁片、原图、路由、收据和哈希。现场核验数为 0。
