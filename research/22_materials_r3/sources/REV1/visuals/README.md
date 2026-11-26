# R4-REV1 地图审查页

直接打开 [index.html](index.html)。可以按 [南门完整路线](index.html#south-route)、[南门末端](index.html#south-terminal)、[西北出口](index.html#north) 分别查看。旧 R4、REV1 与消融共用地图投影和镜头。1、3、5 米选项读取实际运行记录。南侧各接点可分别选择。西北点的测距虚线和避障复查线路为独立证据层。

图件由冻结的六份原生 OSM 裁片、旧 R4 的源面与路线、REV1 保存的逐段路线和允许域生成。底图含原生建筑、草地、道路名称和步行面。输入为 WGS84 `[经度, 纬度]`，显示及比例尺为 EPSG:32651。页面抽样显示主设置中每块面至多 900 条非端口派生边，并保留全部终端连接、完整结果路线和各带宽的允许域。抽样仅影响呈现。逐边几何见 `../data/derived_edges.geojson`，对应原始坐标、来源、检查记录见 `../data/edge_evidence.jsonl`。边线面显示使用当前视野，GIS 文件保留实际输出。

[图件清单](figure_manifest.json) · [开发图浏览器检查](../audits/visual_development_check.json) · [正式图浏览器检查](../audits/visual_author_check.json)

从项目根目录可离线重建：

```powershell
python -X utf8 -B -m src.build_visuals --input-root frozen_r4 --run-root . --output-root rebuilt_visuals --browser
```

静态 SVG 与交互使用同一个绘制器，原生线与计算线采用不同颜色和线型。Edge 是实测浏览器。用户可直接提供自然语言反馈。
