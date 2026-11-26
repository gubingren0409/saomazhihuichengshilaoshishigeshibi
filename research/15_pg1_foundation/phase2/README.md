# PG1 Phase 2 — 有界数据发现与G2审查包

截至2026-11-12，完成来源发现、真实小样本字段核查、四张真实矢量地图和保守空间分组提案。**未取得完整注册入口/过街/步行路网合同，没有可冻结的Validation或Blind组；G2等待用户审查，不能记为数据集已就绪。**

直接打开 [index.html](index.html)。它完全离线，不请求瓦片或地图API。四个有几何的街区是New York Grand Central、Lincoln Center周边及Helsinki Oodi、Meilahti周边；Kallio只显示明确标注的metadata extent，没有虚构建筑。地图类别表示非校园采样意图，不代表已经逐栋验证用途或目标身份。原始完整几何、内环、对象ID、空值和失败响应全部可追溯。

## 实际候选与合同

|街区/site候选|实际读取|未取得|是否可作为完整已注册入口评测建筑|
|---|---|---|---|
|Grand Central周边|362建筑、81人行道面|目标建筑关联、注册入口、过街、道路面、限制|否|
|Lincoln Center周边|330建筑、91人行道面|同上；广场另层未取|否|
|Oodi周边|112建筑；官方到达页提供入口方位/开放时间文字|注册入口坐标/ID、空间匹配、步行面/道路/绿地完整响应|否|
|Meilahti周边|259建筑|注册入口、步行面、道路、障碍及目标建筑关联|否|
|Kallio|官方schema和预设范围；无有效几何样本|全部对象计数为UNKNOWN|否|

共有1235条feature记录：1063建筑与172人行道面。它们不是1235个独立研究建筑。四张实图也不是四个已独立空间组。商业/办公/文化/医院/住宅/交通/公园开放空间/混合街区均进入发现意图；公园与医院精确对象、用途、开放权限仍需独立核定，不能因图中留白判定为开放面。

- [candidate_registry.json](candidate_registry.json)、[CSV](candidate_registry.csv)：来源、范围、读取层、对象ID、SHA、用途意图、未知值、暴露状态。
- [dimension_contract.csv](dimension_contract.csv)：每site十二个任务维度的SILVER/BRONZE及具体依据与缺口；未滥授GOLD。UNKNOWN计数不填0。
- [field_inventory.csv](field_inventory.csv)：每个已读取字段的实际非空分子/feature分母及有限观察值。
- [layer_audit.json](layer_audit.json)：空几何/无效几何均0，真实内环数、是否触及分页限、query/output CRS、响应时间戳。Meilahti两个多边形与请求框不实际相交，可能是服务端包围框筛选，保留并明确计数，未静默删掉。
- [object_inventory.csv](object_inventory.csv)：source-object-ID与原件SHA，可独立重算；不含新入口或新路线。

图中黄色是已取得的NYC人行道原始面，紫色是建筑。Helsinki本轮只取得建筑，不能把未读取的道路/人行道/绿地渲染为事实。投影仅用于显示：EPSG:4326/CRS84源经局部等距圆柱近似映射为SVG，北向/100m近似比例尺有标示，不用于精确测量。所有原始环保留，SVG按请求框显示裁切；完整对象可能超出框。

## 当前许可证据

[sources.json](sources.json)/[sources.csv](sources.csv)记录八类来源的官方URL、短支持摘录、原文或观察快照SHA、存留/再分发边界。SHA的对象明确区分raw response与作者保存的web观察。

1. OSM、Geofabrik、BBBike均按ODbL 1.0审查；三者不能充当互相独立的地图真值。只向Overpass提交一个小bbox，timeout，没有任何OSM feature原件或伪地图。Geofabrik/BBBike没有下城市/区域包。
2. NYC按实际OpenData Terms审查，不擅称CC0/public domain。官方policy索引说明广泛开放使用，但额外agency条款仍需核。现阶段原件、坐标和图册只用于本地审查，未获公开发布许可。BUILDING与Sidewalk实际schema原件已留。
3. Helsinki官方HRI及国家开放数据目录显示CC BY4.0；直接HTTP403，当前官方web工具可读取索引文本。保存的观察JSON只绑定观察内容，不冒充原站原始字节；独立审查应再查官方URL。CC BY4.0要求署名、许可链接、修改说明。[CC BY4.0](https://creativecommons.org/licenses/by/4.0/)。建筑登记字段包括id、ratu、vtj_prt与质量/对应关系；存在null，不能把所有feature称作强可靠注册建筑。
4. Oodi官方到达页是独立文本证据，三处入口方位与开放时间文字不等于入口坐标真值；未把到达页图像/照片复制为数据。
5. Google/Geoapify仅审政策网页，地图API调用、账户、key、收费均0。Geoapify允许部分存储的说明不能替代具体API/底层数据许可；Google有限缓存例外不能用于批量复刻几何。没有消费导航界面抓取、入口生成、训练、Validation/Blind运行。

注意失效证据：旧NYC技术标准URL返回HTTP200但重定向到nyc.gov/opendata HTML，历史文件名`evidence/terms/nyc_standard.pdf`不是PDF，**不作为许可全文证据，不得按扩展名解析**。原件和final_url/content_type日志保留；有效NYC terms是k9k7-3cje页面。HRI403和官方web证据缺少raw页SHA的局限没有隐去。

## 请求预算与负结果

[request_log.jsonl](request_log.jsonl)逐HTTP请求保存URL、UTC、bytes、耗时、Content-Type、状态、原件SHA或错误。清单只是计划；实际请求以日志为准。[collection_receipt.json](collection_receipt.json)可离线重算。

- 38个audited downloader HTTP attempts：15个许可/schema/capabilities，23个vector preview。
- vector：6非空成功，12空响应NO_OBSERVATION，4 byte-cap失败且不保留截断JSON，1 Overpass timeout。
- 已知应用层读取vector响应5,000,001 bytes；保留3,409,629 bytes（含12个空响应147B各）；原Overpass timeout缺失实读计数，实际读取和传输UNKNOWN。记账时为该超时项采用3,000,000B的假设预留。
- 因预算记账估计耗尽停止，六个原清单repair项目未尝试；没有追加数据下载。已知应用读取量加假设预留得到8,000,001B，**仅是保守预算记账估计，不是经过证明的真实网络传输上界**。原超时调用使用旧`read(limit+1)`且没有实读计数，该预留没有计入可能多出的一个检测字节，也未测量HTTP/TLS/socket实际传输。记账估计比预算多1字节，真实总传输量和实际超预算量均为UNKNOWN，不宣称严格预算通过或精确超额。后续源码已修正为不读过remaining cap；历史原receipt快照保存在`evidence/revisions/collection_receipt_before_budget_wording.json`。没有再请求来重试。
- web搜索/open工具另用于官方来源核对，其底层传输bytes/HTTP次数工具不可见，不能报0；不混入可复算Python downloader计数。
- 费用0；无付费API、训练、方法调参、评测或split冻结。

Helsinki首次12个空FeatureCollection不证明现实中没有对象。官方GetCapabilities确认原生EPSG:3879；首轮WFS1.0 bbox未声明CRS，24/60数值按native米坐标解释。修复只在原锁窗口BBOX第五项明确EPSG:4326，经Oodi112/112几何与原框相交验证。其余大型面响应触发字节限制，未把截断数据用于地图或计数。原12空原件与修复新原件分开保留。

## 空间独立与盲测治理

[spatial_pairs.csv](spatial_pairs.csv)包含6个发展场景+5个候选共55对；[spatial_groups.json](spatial_groups.json)是可复算的保守分组。当前只有三个提案组：Shanghai已有发展集合、New York两个候选、Helsinki三个候选（含metadata-only）。

- 原六scene十五对均共享native OSM对象，即使有些bbox不重叠，仍按一个发展source/network group处理。六栋目标可作按建筑macro统计，但不是六个独立地理组。
- 用完整已观察对象包围范围，而非只用小请求框，检查范围重叠、原生ID共享。相同数据源才比较source-ID命名空间；未读/跨源不捏造0。
- 每侧500m是发现阶段保守警戒缓冲，并非已验证路网依赖会在500m截止。没有新路网闭包证据，**同城候选无论距离均暂合组**；跨城地理分离也只标provisional，不宣称完整网络独立PASS。
- 正式冻结前需逐栋注册目标、完整建筑/公园/广场site范围、源way/relation/节点闭包、道路与步行邻接、跨源几何同物识别、重叠/近重复快照、障碍及独立入口reference。任何UNKNOWN阻止对应独立性通过。
- 计划仍为12–20 validation +8–12 blind候选，当前有据池更小，**实际可冻结完整合同数0**，没有为配额降低标准。
- 本轮所有展示/读取候选已经暴露，只能提议后续validation发现池；不得再称这些候选“真正盲测”。Blind暂不提具体已暴露建筑名单。未来需用户批准独立curator保留未公开reference和独立地点，建立访问控制、hash承诺和access log，方法冻结后才执行。

[access_log.jsonl](access_log.jsonl)只记录实际已知访问/生成事件；未知历史人类/模型访问标UNKNOWN，没有伪造独立curator或隐藏盲标签。

## 离线复现与公开边界

在PG1目录执行（仅本地已许可证据，不触发取数）：

```powershell
python phase2/src/build_atlas.py --root phase2 --config phase2/scene_config.json
python phase2/src/spatial_groups.py --root phase2 --development phase1/development_source_identity.json.gz
python phase2/src/summarize_audit.py --root phase2 --config phase2/source_audit_input.json
python phase2/src/verify_atlas.py --root phase2
```

Python依赖：Shapely用于几何审查和SVG；Playwright及已安装本机Edge仅用于离线浏览器截图（不下载浏览器）。`visual_check_receipt.json`是作者工程检查，不等同独立技术复核或用户地图验收。

[PUBLIC_SOURCE_INVENTORY.md](PUBLIC_SOURCE_INVENTORY.md)列出可提议进入个人公开仓库的通用CLI源码。真实数据、带坐标输入清单、原文缓存、地图和访问日志只留本地审查；父任务按最终commit重放并纳入固定审查ZIP。没有改旧工程、历史包、根状态或仓库，没有push。

## G2需要的决定

本轮发现可供审查，完整数据合同不足以冻结组。用户/GPT需先审四张真实地图、许可证据与UNKNOWN，再决定是否批准下一轮按新预算补充独立入口reference、路网/过街/障碍、精确建筑身份，以及独立curator盲参考流程。当前边界内停止取数和评测。
