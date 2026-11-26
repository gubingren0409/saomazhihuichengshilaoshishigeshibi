# PG1 初始基础轮：供 G0 / G1 / G2 审核

本轮执行 Phase0、并行Phase1/2，以及现有开发集内的一项有界TrackA工程探针。Parent仍处于FOUNDATION，未宣告整个项目PASS，未首次Push、冻结Validation/Blind、开展盲测或大规模参数搜索。

## 先看真实图和逐对象结果

- 本地总览：http://127.0.0.1:53501/。断开互联网后仍可用本机HTTP服务浏览六场景交互；直接file打开根index.html可看六张静态图，phase2图册自包含可直接file打开。phase1交互需要本机HTTP读取分文件JSON，不能冒称file协议也能加载。
- 六开发场景：phase1/index.html。比较A原始源、B实际导入语义、C路由语义与已有保存图对象、D旧R1显示策略和真实历史路线；支持同视野、图层开关、点选原生ID/tags和来源、全景/街区/局部。D为旧显示规则复现，不冒称本轮打开旧APP截得的新图。
- 非校园候选：phase2/index.html。纽约中央车站周边、林肯中心周边、赫尔辛基Oodi和Meilahti为真实矢量样本；Kallio仅显示明确标注的元数据范围，不造地图。
- 全量机器表：audit/baseline_registry_private.csv；phase1/family_lineage.csv和每scene/object_lineage.jsonl.gz；phase2/candidate_registry.csv、dimension_contract.csv、field_inventory.csv、spatial_pairs.csv；track_a/TA-PG1-01/results.csv。

## G0：历史成果与个人仓库

核对16个历史名称线索，15个实际包完成新测SHA、ZIP CRC，并与历史包外回执的SHA吻合。包括V1/V2、OSM/Geoapify R1补齐版/R2/R3、R4-REV1、北门接入R1、WALKABILITY R2/R3/CONTEXT、FREE-SPACE最终版、已知入口APP修复版、完整步行面修复版，以及衔接R1/R2。未找到单独命名的WALKABILITY-R1固定包；北门接入R1保留其本来身份，不强行改名。此项是命名/来源待确认，不是重建历史成果的理由。

早期失败/部分候选保留：FREE-SPACE的PARTIAL、E2E首包、完整面首个FINAL与其FIXED、R2包内封包前PENDING及包外最终回执分别登记；不能拿旧包内PENDING否定随后真实复验，也不能把内部PASS当成用户科学验收。

目标仅为gubingren0409/saomazhihuichengshilaoshishigeshibi。GitHub连接器只有pull权限且身份woobowen；本机现有凭据身份为gubingren0409，个人仓库权限含push/admin。API确认Public、size0、main；commits端点409明确空仓库。原Git命令被未运行的本机7897代理阻断，以单条命令HTTP/1.1、Windows证书后端及空代理完成ls-remote和push --dry-run，不关闭TLS、不改全局设置，不上传任何内容。

新的repository子目录是隔离Git仓库，未重写旧history/remotes/index。Base Commit、Final Commit、Git tree、完整精确文件清单及变更统计见audit/ROUND_BINDING.json和audit/PUBLIC_FILE_INVENTORY.csv。最终Commit只存在本机；远程仍未同步，不能声称GitHub已经有可审源码。

首次公开候选只含新的自有通用源码、模板、测试、schema与概括/哈希registry。地图原件/候选坐标、图片、API响应、私有截图、旧包、旧Git快照与缓存不在清单。新增源码许可证暂未代用户指定；旧代码和OSM/市政数据不改授许可证。审查ZIP包含本地审核实物，**不是**获准上传Public的文件集合。

## G1：地图信息并非简单“丢了”

六裁片合计306,927条源记录，跨裁片大量重复；53,624个对象有真实可定位显示几何。8,025条机动车道路对象均保留在地图上下文和旧诊断显示中，旧页面道路名称/等级缺绘、灰细线和视野选择会造成信息稀少感。新审图恢复源字段标注，显示线宽仍是符号，不是实测路宽。

源中没有独立area:highway道路面或area=yes车行道路面，不能靠描粗中心线补造道路边界、两侧人行道或过街位置。道路轴上的sidewalk标签与独立footway=sidewalk几何分别统计。

原生准入回放保留30,420段，其中含旧规则允许/假设共享道路中心线；机动车道路对象中4,272个有保留段。native只说明原生线经过旧规则准入，不等于专用步道、确认人行道或现实安全。该语义风险保留，不在G1审核前修改准入定义。

少量源几何在适配器中有真实转换，另有54个源不可解析对象被旧适配器转成UNKNOWN包围盒；这类对象应在B标为导入派生未知框，不能在A画成原始面。当前图的全局可视图、持久化补充图、只读原生准入回放和源面也有明确身份，未冷构建全图。

博物馆/图书馆有三个登记门和SHA绑定历史APP路线；其余四目标没有原登记门，不生成门、起点或业务路线。C的可观察保存图范围与NOT_EXPORTED字段须按实际graph receipt解释，不把未知当0。

独立浏览器发现的water LineString假填面已修复：只有真正Polygon/MultiPolygon可填色。该修复不改源数据。54个UNKNOWN框与准入车道轴的标注也在最终版本中明确，旧错误证据保留。

## G2：找到真实候选，但尚无可冻结完整评测集

5个site/街区候选中，4个有实际矢量几何，1个仅metadata。已读取1235条feature记录（1063建筑、172人行道面）；这些既不是1235个独立研究建筑，也不是四个已确认独立的建筑任务。没有候选同时满足登记入口关联、完整步行网/面、过街/障碍、独立参考的全合同，可冻结Validation/Blind数量为0。

OSM/Geofabrik/BBBike属于同一地图数据家族，不互为独立真值；NYC与Helsinki官方来源分别审查条款、schema、CRS、缺失字段与再分发边界。NYC不能擅称CC0；Helsinki CC BY4.0的网页观察与真正raw页SHA分开。商业服务仅审条款，没有收费地图API、Key或消费者界面抓取。

采集是已批准的有界source-preview/schema检查，并非0 API：下载器38次HTTP尝试，其中23次vector预览，6非空、12空NO_OBSERVATION、4触发字节上限、1超时。WFS空响应定位为bbox CRS接口问题，原窗口修复后取得真实建筑；原空结果保留而不冒称当地无建筑。已知vector应用层读取5,000,001B，超时实际传输UNKNOWN并预留3,000,000B，预算记账估计为8,000,001B。旧limit+1检测哨兵使该记账值超过8MB的1B与修复实物保留；它不是已证明的网络传输上界，真实总传输UNKNOWN，未再取数。费用/训练均0。网页搜索工具的后端流量无法获得，不伪写为0。

55个空间pair按实际ID、范围和保守网络依赖检查，合为Shanghai/NYC/Helsinki三个暂定组；这不是已证独立性PASS。当前六上海裁片两两共享源对象，不能随机拆query、门或相邻图到不同集合。所有展示候选均EXPOSED，不可重新称独立盲测。12–20验证和8–12盲测只是后续规划目标，未以降低合同凑配额。

## Track A：真实继续，候选未选留

TA-PG1-01在四个固定业务端点×F0/F1完成8次新solver调用。只比较同图平行选项的标量与批处理成本构建，沿用原端点/区域/约束、F0=w和F1=w+h。最小代价全部复现R2，独立逐弧/路径/原端点证书通过；不宣称新路线收益或泛化。

批处理没有稳定加速，保留标量实现，不因代码更复杂就选留。实际运行源码保存在Base Commit；随后仅修有限可达mask核验和跨平台provenance路径，不重跑8次或伪改原run。全部负结果与source SHA见track_a和audit/development_probe_source_history.json。

下一步A优先按具体错误假设处理语义/道路轴证据、原生/面接口和冷预处理成本，逐项同输入对照，不能继续为四条已最优路线制造变化。下一步B优先补候选的注册入口/外部路网/过街与独立参考，并由独立curator设计尚未暴露的参考；具体再取数/分组冻结需G2批准。

## 审核、保护与限制

作者自检、实际独立技术复核、GPT后审、用户自然语言验收、首次公开许可分别登记。新包实际解包后的机器/浏览器回执在delivery；CRC不是科学验收。

两个旧Git的HEAD/index/tracked状态与remotes保持；历史包不变。旧53421/53431/53441/53451当前TCP拒绝连接，初始无HTTP可用快照，不能说本轮使其停止，也不能声称仍在线。本轮没有停/起旧服务；原APP包和启动源仍登记，当前旧服务功能未重验。新53501仅只读审图，不提供新求路或推送接口。

现场公众通行、开放状态、未记录高差/障碍、独立真实物理入口与通路仍未验证。G0/G1/G2未获用户批准；本轮停止于这些关口，不自动进入验证/盲测或下一研究范围。
