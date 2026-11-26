# OSM–Geoapify R2 路线差异与视觉评价

[交互诊断页与六张证据图](web/index.html) · [路线差异诊断](01_ROUTE_DIFFERENCE_DIAGNOSIS.md) · [视觉与路线功能](02_MAP_VISUAL_VS_ROUTE_QUALITY.md) · [评分与原文溯源](03_USER_FEEDBACK_TRACEABILITY.md) · [第二轮判断](04_NEXT_EXPERIMENT_DECISIONS.md)

上海博物馆人民广场馆，冻结一栋、两个视野。本轮仅处理首轮已有真实文件。输入 ZIP、首轮封包、裁片、静态图和用户 CSV 都先校验哈希。首轮 HTTP 路由响应的原始正文未留存，保留的是真实返回折线、距离摘要和脱敏请求回执；托管内部图保持未知。没有新 API 请求。

原输入证据见 `source_evidence_index.csv`。输入图像保留原署名。首轮原评分 CSV 逐字节放在 `inputs/` 下。副本供同一审查使用，第二轮意见请另存。首轮待确认的内部图和现场状态保持未知。当前证据不足以选定正式数据源。

## 离线复现

在本目录运行。Windows 参考 Python 3.12.6，项目依赖见 `requirements.txt`。使用系统中文字体，字体文件不打包。

```powershell
python -X utf8 -B -m src.endpoint_audit
python -X utf8 -B src/topology.py
python -X utf8 -B -m src.make_figures
python -X utf8 -B src/build_viewer.py
python -X utf8 -B -m src.build_reports
python -X utf8 -B audits/check_viewer.py
```

静态图和交互页无需网络。SVG 导出保存当前中性诊断图层，原底图仍可通过图册链接查看。首轮封包只记录哈希与原位置；已核验的最小工作副本随包，复现无需解压整个首轮工程。许可证见 `inputs/r1/data/LICENSE_NOTICE.md` 和 `inputs/r1/visuals/geoapify/ATTRIBUTION.md`。
