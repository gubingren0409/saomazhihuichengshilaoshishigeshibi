# 来源、许可和额度核查

核查日期为 2026-11-09（北京时间）。本轮比较本地 OSM 快照与 Geoapify 的托管渲染和步行服务。Geoapify 静态图来自 OSM，不能用两套结果互证地理真值。托管快照时间、当前步行后端具体版本和图层过滤规则没有公开到足以逐场景追溯的粒度。Geoapify 的专属部署页面列出 Valhalla 和 OpenTripPlanner，本轮据此只说明供应商具备这些技术，不认定普通托管步行端点的精确构建版本。 [Geoapify Static Maps](https://www.geoapify.com/static-maps-api/) · [Geoapify Routing](https://www.geoapify.com/routing-api/) · [Geoapify 专属部署](https://www.geoapify.com/maps-geocoging-routing-on-premise-installations/)

## 按用途判定

| 用途 | 本地 OSM | Geoapify |
| --- | --- | --- |
| 本地矢量、步行路线与在线展示 | ALLOWED_WITH_CONDITIONS。矢量数据遵循 ODbL 1.0，提供 OSM 署名和许可链接。 | ALLOWED_WITH_CONDITIONS。依使用计划、数据源及样式要求提供署名。 |
| 试验地图截图、原始静态图 | ALLOWED_WITH_CONDITIONS。使用自己的渲染或合规底图，保留署名。 | ALLOWED_WITH_CONDITIONS。此项只覆盖 Static Maps API 原始静态图片的正常保存或展示，及用该产品提供的制图叠加方式。浏览器截屏或其他地图产品不自动套用此条。 |
| 短期缓存与长期保存 | ALLOWED_WITH_CONDITIONS。保留来源、许可和公开分发条件。 | ALLOWED_WITH_CONDITIONS。Static Maps 产品页明确允许缓存和保存带所需署名的静态图，未列统一期限。Routing 产品页同样明确支持保存路线结果。 |
| 地图绘制和人工图册、课堂展示 | ALLOWED_WITH_CONDITIONS。Produced Work保留可见署名和许可链接。 | ALLOWED_WITH_CONDITIONS。正常地图展示、保留原图署名的课堂图册、路线覆盖展示属于产品所述用途。 |
| 常规技术质检 | ALLOWED_WITH_CONDITIONS。可核对尺寸、坐标、文件完整性和地图合规性。 | ALLOWED_WITH_CONDITIONS。核对响应类型、图幅、署名及地理配准，范围限于本轮静态图的制图质检。内容判断交给用户。 |
| 图像 CV、像素批量抽取或训练 | NOT_CHECKED。当前不做，原始 OSM 数据若另作模型训练需核对 ODbL 及衍生数据库要求。 | REQUIRES_PROVIDER_CONFIRMATION。静态图保存许可没有明确覆盖这一用途。 |
| 派生数据库、长期研究数据集 | ALLOWED_WITH_CONDITIONS。根据 ODbL 判定衍生数据库，公开使用时遵循同许可和可得性要求。本轮只发布可复现样本。 | REQUIRES_PROVIDER_CONFIRMATION。保存静态图和具体路线的许可不自动延伸到从其重建数据库、批量制备研究数据集。 |
| 对外发布、再分发与审查包 | ALLOWED_WITH_CONDITIONS。保留公开 Produced Work 署名，随包原数据或衍生数据库遵循 ODbL。 | ALLOWED_WITH_CONDITIONS。产品页允许发布带署名的静态图与路线结果，分发对象限于原图或制图用途及正常路线结果。为减少披露，本轮包只纳入明确许可、可复核的成果与脱敏信息。 |
| 传给第三方 AI 或 VLM 处理真实图像 | NOT_CHECKED。本轮范围禁止。 | REQUIRES_PROVIDER_CONFIRMATION。没有将图像提供给第三方 AI 的公开专门许可，本轮范围同时禁止。 |
| 抓取 OSM 公共栅格瓦片、离线预取和归档 | NOT_ALLOWED。OSMF 公共瓦片政策明确禁止。 | NOT_CHECKED。本轮只用 Static Maps 与 Routing 官方端点。 |

OSM 开放的是数据库数据。本地可采用来自 Planet、区域提取或有界 Overpass 查询的矢量，实际数据提供方、下载时间、对象时间与哈希另由本轮清单记录。公共栅格瓦片政策独立适用。静态图一般属于 Produced Work，快照及发布的 OSM 衍生数据库按 ODbL 判断。 [OSM 版权与许可](https://www.openstreetmap.org/copyright) · [OSMF 署名指引](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines) · [公共瓦片政策](https://operations.osmfoundation.org/policies/tiles/) · [Planet 与区域提取](https://wiki.openstreetmap.org/wiki/Planet.osm) · [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)

Geoapify 的 Terms and Conditions 当前公开版本为 2024-02-02 第 5 版。Attribution 小节要求始终提供 OSM 署名，Free 计划还要求 Geoapify 署名，样式所需署名由具体接口说明给出。默认静态图右下角署名保留。选定的 `osm-bright-smooth` 样式使用 OpenMapTiles，因而同时保留 © OpenStreetMap contributors、© OpenMapTiles 和 Powered by Geoapify。可见署名优先于盲评匿名。评分时以随机 ID 与列位置为准，用户可能从版权行或画风辨认提供方。 [服务条款](https://www.geoapify.com/terms-and-conditions/) · [静态图产品保存说明](https://www.geoapify.com/static-maps-api/) · [静态图署名文档](https://apidocs.geoapify.com/docs/maps/static/#attribution) · [路线结果保存说明](https://www.geoapify.com/routing-api/)

## 技术约束和费用

- 静态图固定用 `maps.geoapify.com/v1/staticmap`，官方标准端点最高支持 4096×4096，本轮请求 1200×900、PNG、二维、零旋转、scaleFactor 1、默认署名，不放目标或路线覆盖物。采用 `area=rect:west,south,east,north` 请求冻结区域。官方将此描述为让视图涵盖给定区域，未见返回精确边界的保证或验收元数据。实际 PNG 尺寸可独立验收，范围和尺度须用同图控制点或其他独立可核查证据确认；仅凭请求矩形不能宣布 A/B 像素配准。 [静态图 API](https://apidocs.geoapify.com/docs/maps/static/) · [官方静态图制图说明](https://apidocs.geoapify.com/how-to/maps/create-static-map/)
- 路线固定 `api.geoapify.com/v1/routing`、两个冻结点、`mode=walk`、`type=balanced`、`units=metric`、`format=geojson`。请求显式采用文档支持的 `lonlat:`，响应 WGS84 坐标按 GeoJSON 顺序处理，保留每条 LineString 和段间缺口。进入目标地块与到达实体门是两个问题。两个固定点已知时本轮无需 Places/Search。 [Routing API](https://apidocs.geoapify.com/docs/routing/)
- Free 计划公开为每天 3,000 credits，最多 5 请求/秒，无需信用卡。1200×900 单图的参考估算为 1 次静态图请求加所需瓦片数除以 4，零标记，约 5.12 credits，实际取决于覆盖瓦片等。普通短程两点步行参考为 1 credit。首栋两个视野和一次步行，约 11.24 credits。6 栋满额约 67.44 credits。这些数值是文档公式的面积近似，实际 credits 未出现可核验回执时保留空值。 [Geoapify Pricing](https://www.geoapify.com/pricing/) · [Pricing Details](https://www.geoapify.com/pricing-details/) · [静态图成本公式](https://www.geoapify.com/static-maps-api/)
- 服务条款保留超量时暂停服务或收取额外费用的权利。只在用户核对本机 Key 所属项目有适用免费额度且能够确保不产生新增付费后启动。适配器以本机环境读取密钥，用 HTTPS `x-api-key` 头，禁重定向，单实例最多 18 次，串行、每秒至多一次，不自动重试。不得绕过账户限流或配额。公开套餐不能用来推断当前项目的额度余额。 [服务条款](https://www.geoapify.com/terms-and-conditions/) · [Geoapify 服务端认证说明](https://www.geoapify.com/geoapify-openapi-specifications-ai-coding-tools/)
- Valhalla 软件采用 MIT 许可，MapLibre GL JS 采用 BSD-3-Clause。软件许可不代替 OSM 数据及第三方样式、字体、图标的许可。本地实际使用的引擎、渲染实现和固定版本见工程记录。 [Valhalla 许可说明](https://valhalla.github.io/valhalla/#license) · [MapLibre 许可](https://github.com/maplibre/maplibre-gl-js/blob/main/LICENSE.txt)

依据上述适用产品条款，本轮有真实响应时可保存并分发附必要署名的原始 Geoapify 静态图与路线结果。可疑响应、实际边界未核验、人工视觉未评分都须单独标记。最终技术审查只处理代码、指标和许可允许的最小证据，无 VLM 图片处理。

