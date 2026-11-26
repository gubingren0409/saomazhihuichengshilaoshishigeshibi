# R3 数据来源与许可核验

核验日期：2026-11-09，北京时间。仅依据公开的官方条款、文档和本机首轮证据。研究比较共享 OSM 地理来源的两条工程路径。Geoapify 静态图由 OSM 数据渲染。其托管快照时点、路由图、图边和标签过滤规则保持 UNKNOWN。 [Geoapify Static Maps](https://www.geoapify.com/static-maps-api/) · [Geoapify Routing](https://www.geoapify.com/routing-api/)

## 使用范围

| 内容或行为 | 本轮决定 | 核验依据 |
| --- | --- | --- |
| 本地 OSM 矢量与衍生裁片 | 用已核验上海 PBF 本地裁切。随包保留原始 ID、来源、时间和 ODbL 署名及许可，复现无需复制首轮全市 PBF。 | [OSM 版权许可](https://www.openstreetmap.org/copyright) · [Geofabrik 上海提取](https://download.geofabrik.de/asia/china/shanghai.html) |
| OSM 公共瓦片 | 本轮为本地矢量渲染，公共瓦片请求为零。 | [OSMF 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/) |
| Geoapify 原静态 PNG 的保存、缓存、课堂展示、审核包和人工评分 | 官方产品说明允许缓存、存放和再分发原图，前提是必要署名。原响应 PNG 保持原样，图册保留随图版权与旁置链接。使用 osm-bright-smooth，保留 © OpenStreetMap contributors、© OpenMapTiles、Powered by Geoapify。必要署名可能被用户辨认，盲评只随机左右，不遮盖署名。 | [静态图产品许可与说明](https://www.geoapify.com/static-maps-api/) · [静态图 API 署名](https://apidocs.geoapify.com/docs/maps/static/#attribution) · [服务条款](https://www.geoapify.com/terms-and-conditions/) |
| Geoapify 路由响应、实际折线、人工图上对照 | 官方路由说明允许保存和再分发结果。保留 OSM 和 Geoapify 署名。成功原始 JSON 在本地经凭据字段扫描后才保存，规范化折线与原始响应可互相追溯。 | [Routing API 产品说明](https://www.geoapify.com/routing-api/) · [路由请求参数](https://apidocs.geoapify.com/docs/routing/) |
| 图像工程核验 | 检查 PNG 完整性、尺寸及项目自己指定的控制点、折线颜色和视野偏差。几何控制点由冻结合同给定，只用来验收地图相机和叠加线。图面信息观察和可读性判断由用户评分。 | [静态图请求与几何叠加参数](https://apidocs.geoapify.com/docs/maps/static/) |
| Geoapify 图像进入 CV、VLM、训练或派生地图数据库 | 当前未见足以确认这些用途的单独许可，故不执行这类分析、不训练、不向第三方 AI 传图。通用条款的服务访问许可与产品页的原图保留范围分别记录。 | [服务条款](https://www.geoapify.com/terms-and-conditions/) · [静态图许可说明](https://www.geoapify.com/static-maps-api/) |
| API 隐私与凭据 | 请求仅含公开地图研究场景的坐标及样式等。供应商说明 API 可能保存请求正文、头、IP、时间用于访问控制和计量，成功请求一般不超过 24 小时。通过 HTTPS 官方端点和本机已验证回环代理传输，凭据仅在运行时读取首轮私有配置或进程环境，用 x-api-key 头，不落入请求收据或归档。只记录脱敏参数、HTTP 状态、耗时、结果摘要和明确允许的数值配额头。 | [隐私政策](https://www.geoapify.com/privacy-policy/) · [Geoapify OpenAPI 鉴权](https://www.geoapify.com/geoapify-openapi-specifications-ai-coding-tools/) |

## 请求与支出约束

官方 Free 计划为每天 3,000 credits、最高 5 请求/秒且不要求信用卡。R3 复用用户已授权的既有 Key，不变更套餐。最多五个新增场景，每个最多一次两点步行请求、两张原始静态图和两张带控件的叠加图，总上限 25 次。串行并至少间隔约一秒，鉴权、支付、配额或代理限制错误即停。首轮上海博物馆实物只作为历史记录读取。账户余额与实际扣减在无可信响应或账单时为 UNKNOWN。 [定价](https://www.geoapify.com/pricing/) · [定价说明](https://www.geoapify.com/pricing-details/) · [服务条款](https://www.geoapify.com/terms-and-conditions/)

用官方示例面积公式估计每张 1200×900 静态图约 5.12 credits，两点步行约 1 credit，25 个请求约 107.4 credits。地图控件使用 geometry，不使用另收费的 Map Markers API。实际底图瓦片数量取决于服务相机和请求，最终消费不能由这个估算推出。运行日志单独记载可见的 credits 证据。 [静态图计量公式](https://apidocs.geoapify.com/docs/maps/static/#pricing) · [Geoapify Routing](https://www.geoapify.com/routing-api/)

## 冻结字段与运行区分

- Route 请求沿用 R1 实测的 lonlat 前缀、mode=walk、type=balanced、units=metric、format=geojson。保留请求目标、折线末点、可能存在的独立 snap 字段与门身份间的区别。
- 静态图沿用 R1 的 area=rect、bearing=0、pitch=0、scaleFactor=1、1200×900、默认署名。相同 bounds 是请求约束，实际配对需控制点核验。
- R3 的新 HTTP 结果标记 LIVE。R1 原始 PNG 和已验证折线进入 R3 时标记 HISTORICAL，离线可复现为回放。
- 自本机输入复核日起，具体执行的请求次数、HTTP 错误、控制点偏差和实际耗时见 runs/hosted_results.json。

## 本轮托管执行结果

- 五栋冻结新增建筑全部实际调用。25 次请求均为 HTTP 200，保留 5 份原始路由响应、5 份规范化路线及 20 张原始静态 PNG。没有新的上海博物馆请求。
- 10 个视野均为 1200×900。每个视野的四个标记控制点均通过对位，实际 bounds 在预先约定的 1px 阈值内，10 张叠加图的原路线像素校验通过。
- 请求耗时中位数 5.844 s，范围 0.610–8.453 s，累加 126.421 s。107.4 credits 是按文档估算。响应未暴露数值额度头，也未查看账户控制台，实际扣减和可用余额保持 UNKNOWN。本轮未购买或升级。
- 原始响应顶层的 waypoint 是请求回显，路线属性的 waypoint 坐标也贴近请求坐标，在五栋样本中与请求相差不足 0.20 m。返回折线末点另行记录。响应没有可独立认定的路网吸附点字段或门身份，相关字段保持 UNKNOWN。
- 托管流水、原始文件校验与数值复核见 `runs/hosted_results.json` 和 `audits/hosted_output_checks.json`。后者属于作者技术自查。图面质量偏好仍由用户在空白表中判断。
