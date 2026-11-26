# API、渲染与离线复现

## 本地分支

1. 先执行一条有界只读 Overpass 查询，HTTP 502，回执保留。改用 Geofabrik 上海日期版 PBF。首次传输到 17,038,870 字节时超时，通过同一版本 Range 续传 9,040,360 字节。源总量 26,079,230 字节，SHA256 `e4b83f15cc358d347c47708239f8c556d9819a69f43ff32f42a23c405733e8f6`。源内复制时间 2026-11-08T21:21:00Z。 [Geofabrik 上海](https://download.geofabrik.de/asia/china/shanghai.html)
2. pyosmium 4.3.2 局部裁片保留 OSM 原生节点和 way ID、关系及标签。源 PBF 仅在本机运行目录。裁片 58,006 个元素，审查包带裁片及 ODbL 署名、许可。
3. Valhalla 可执行文件和可用容器守护进程在本机未取得。采用 NetworkX 3.6.1 Dijkstra 和 pyproj WGS84 椭球长度。步行图采用保守 OSM 标签 profile，按有向边和原生 ID 连接，保留接入距离、裁片范围和未建边原因。
4. Pillow 10.2.0 用原生投影与固定图幅输出同范围底图、诊断叠加、北箭头、比例尺和署名。线宽是样式像素值。MapLibre GL JS 5.12.0 通过本地离线包加载原图及同一 GeoJSON，负责显示。 [MapLibre 文档](https://maplibre.org/maplibre-gl-js/docs/)

## 托管分支

服务端固定 Geoapify 官方 HTTPS，密钥只放 `x-api-key` 请求头。首例最多一次步行和两幅带原署名的静态图。已固定地理点，搜索预算为零。失败保留脱敏分类，禁止自动重试付费或配额失败。授权、文件类型、静态图实际范围和人工评分各自留痕。 [Geoapify API 文档](https://apidocs.geoapify.com/)

## 版本与检查

Windows，Python 3.12.6。依赖见 `requirements.txt`。使用系统字体绘制中文，字体文件不入包。不同系统的字形可能导致 PNG SHA 不同，几何合同不受影响。与版式一致性相关的初版和修订 SHA 见 `audits/overlay_label_revision.json`。
