# OSM–Geoapify R4-REV1

[打开地图同图对照](visuals/index.html) · [南北门与参数结果](RESULTS.md) · [逐门机器记录](data/entrance_approach.json)

本轮修订在冻结的 OSM 步行面内生成受约束的边缘计算边。上海博物馆南侧三个原生接点分别试走，北西出口单列外部接近与入馆角色。旧 R4 与 Geoapify 仍作为历史对照，原始入口坐标沿用。

## 离线重跑

在本目录或解包后的根目录运行。Python 3.12.6 与固定依赖见 [requirements.txt](requirements.txt)。输出路径应为新的目录。

```powershell
python -X utf8 -B -m src.run_rev1 --input-root frozen_r4 --output-root replay_r4rev1 --config config/rev1_main.json
python -X utf8 -B -m src.audit_native_prefix --input-root frozen_r4 --result-root replay_r4rev1 --output-root replay_r4rev1
python -X utf8 -B -m src.report_rev1 --root replay_r4rev1
python -X utf8 -B -m src.build_visuals --input-root frozen_r4 --run-root replay_r4rev1 --output-root replay_r4rev1/visuals --browser
python -X utf8 -B -m pytest -q -p no:cacheprovider
```

审查包内 `frozen_r4/` 是原 R4 归档中必要文件的逐字节副本，原输入归档 SHA 和每项源字节身份由清单绑定。核心重放无需原 Windows 路径、外部请求或账户。原始城市 PBF 和托管 PNG 由历史归档引用，页面采用冻结 OSM 矢量底图。

[研究合同与方法](SCOPE_AND_METHOD.md) · [源清单](data/source_manifest.json) · [独立审核](audits/INDEPENDENT_REVIEW.md) · [自然语言验收](USER_REVIEW_NOTES.md)
