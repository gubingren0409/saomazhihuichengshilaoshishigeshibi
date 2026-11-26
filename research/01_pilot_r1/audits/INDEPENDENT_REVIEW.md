# 独立技术审核

审查者为 Codex 子代理 `/root/osm_review`，与本轮路线、图面、图册实现分别执行。审核覆盖输入包、公开许可、首栋实际源快照、冻结请求、路线证据和图面尺度。人工视觉评分为 `PENDING_USER_REVIEW`，现场核验为 0。

## 输入与许可

输入 ZIP 的 CRC、三项文件长度及清单 SHA256 均复验通过。ZIP SHA256 为 `98692b8ab937a22cf5bf64d1859f09c250de331a5b31146116695937c43cc84b`。

Geoapify 的 Static Maps 产品页明确允许缓存、保存、再分发和打印返回的静态图，条件是保留所需署名。所选非 `osm-carto` 样式须保留 OpenStreetMap contributors、OpenMapTiles，以及 Free 计划的 Powered by Geoapify。Routing 产品页另行允许保存和再分发路线结果，平台条款要求提供适用署名。Free 计划页面列出每日 3,000 credits 与最高 5 请求/秒，单个账户的可用额度仍须以账户状态确认。 [静态图产品说明](https://www.geoapify.com/static-maps-api/) · [静态图署名](https://apidocs.geoapify.com/docs/maps/static/#attribution) · [路线产品说明](https://www.geoapify.com/routing-api/) · [条款](https://www.geoapify.com/terms-and-conditions/) · [定价](https://www.geoapify.com/pricing/)

公开产品资料支持通常的带署名制图和展示。本次未找到适用于 Geoapify 图片 CV 训练、从图像重建数据库或把图像提供给第三方 AI 处理的专门许可。文档描述的矩形适配也没有给出可核验的实际 PNG 边界回执。当前没有 Geoapify 实际响应，无法确认图幅、地理配准或托管快照时点。 [静态图 API 参数](https://apidocs.geoapify.com/docs/maps/static/) · [服务条款](https://www.geoapify.com/terms-and-conditions/)

本地侧使用 ODbL 矢量数据和独立渲染。地图保留 OSM 署名，公开矢量裁片和来源应继续附数据许可。公共栅格瓦片政策另有独立要求。 [OSM 版权与许可](https://www.openstreetmap.org/copyright) · [OSMF 瓦片政策](https://operations.osmfoundation.org/policies/tiles/)

## 原生数据和路线复算

- 直接从 Geofabrik 原始 PBF 复验了 103 个节点、13 条 way，覆盖目标、端点吸附和诊断路线。原始文件为 26,079,230 字节，SHA256 为 `e4b83f15cc358d347c47708239f8c556d9819a69f43ff32f42a23c405733e8f6`，数据时点为 `2026-11-08T21:21:00Z`。冻结样本和矢量裁片的 SHA 关联一致。
- 目标 `way/161090899` 的原生轮廓有效。起点 `node/476682043` 是设定地图起点。目标 `node/6897141353` 在轮廓上且源标签为 `entrance=main`。场馆对南门的说明与目标选择方向一致，实体入口当前状态未现场核验。 [场馆到访说明](https://www.shanghaimuseum.cn/mu/frontend/pg/service/visit-west)
- 用 GeographicLib 从裁片独立枚举合规步行段与复算距离，目标到最近合规段的缺口为 55.02217444 米，超过预设 35 米。起点吸附为 0 米。主路线 GeoJSON 的 geometry 为空，`TARGET_SNAP_OUTSIDE_LIMIT` 的判定与源证据一致。
- 诊断折线只到已映射路网候选。独立复算为 1,416.71934283 米、90 个顶点、89 个 `MAPPED_PEDESTRIAN_WAY` 段，逐段核对原始 OSM way 及相邻节点。55.02217444 米末段未被补画。诊断折线在平面测试中与目标建筑内部无相交长度。同一裁片中 4,678 条有效建筑标签闭合 way 在扣除轮廓边缘后也无内部交叉。此复算未覆盖关系多边形、未登记障碍或现场条件。

## 视野和 PNG 技术核验

独立从 Web Mercator 变换和建筑原生多边形重算两档视野，核对四张实际 PNG 的尺寸、颜色差异、文件哈希与折线末点投影。近景显示的是局部接近区域，设定起点约在画布左侧 122 像素处。上下文视野包含设定起点与完整诊断折线。近景和上下文分别包含诊断折线投影长度的 62.31% 和 100%。

| 视野 | 尺寸 | 中心横向地面尺度 | 目标轮廓外接框 | 轮廓面积占画面比例 | 覆盖物改变像素 |
| --- | --- | --- | --- | --- | --- |
| 近景 | 1200×900 | 0.511090 m/px | 267.746×258.967 px | 3.0692% | 34,646 |
| 上下文 | 1200×900 | 2.044360 m/px | 66.936×64.742 px | 0.1918% | 24,333 |

自动颜色与尺寸检查、独立几何核验和人工可读性评分使用不同证据。当前完整 A/B 底图配对为 0，无法评价两种渲染的视觉差异、路径差异或最终选型。

独立复算入口与机器回执为 [independent_geometry.py](independent_geometry.py) 和 [independent_geometry.json](independent_geometry.json)。

## 独立离线浏览器复核

Edge 从实际文件打开匿名图册、人工评分页与 MapLibre 路线页。两档各有一张底图及一张叠加图，四张图均为 1200×900。界面显示 0/2 组双侧底图。21 个下拉项、2 个文本项及 CSV 的人工字段均为空。两档 MapLibre 底图加载完成，只有 90 顶点的诊断折线显示，四角配准误差小于 1 CSS 像素。校验拦截所有 HTTP/HTTPS 请求，实际外部请求为 0。该复核未填写人工分数。 [浏览器机器回执](independent_browser.json)
