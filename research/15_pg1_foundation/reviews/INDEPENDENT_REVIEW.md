# PG1 独立技术审查（封包前定稿）

状态：`PASS_FOR_DEFINED_INITIAL_FOUNDATION_TECHNICAL_REVIEW_SCOPE`。没有当前未决工程修复；新固定 ZIP 的安全解包、最终字节重放和包内浏览器回执尚待封包后单独出具。整体 PG1 仍为 `FOUNDATION`，G0/G1/G2、首次公开、GPT 审查及用户验收均待决，不是整体项目 PASS。

实际审查者：独立子角色 `pg1_independent`。本角色未制作 Phase 0/1/2 或 Track A 作者产物；仅写 `reviews/`。此记录不代表 GPT 最终审查或用户验收。

## 已执行实证

- 已完整读取三个当前输入文件，独立 SHA256 计算与父记录逐字节一致；已核对五个当前权威规则文件 SHA256。见 `independent_initial.json` 及 `src/independent_initial.py`。
- 独立读取旧 R2 与 R1 最终 ZIP，SHA256 分别是 `3988e9fba95da70dc03b8191a177740a3ccd13602019afe3765e566648b55711` 和 `d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed`，265 / 764 成员均完成 CRC；未发现绝对路径、冒号或 `..` 路径成员。尚未重跑旧 104 任务或任何旧 VG。
- 又对旧 R1 763 / R2 264 个内容成员逐个读取、比较 manifest bytes 与 SHA256；全部一致，唯一不自列项为 manifest 本身。见 `independent_historical_manifest.json`。此为包内容校验，不冒称算法结果重放。
- ZIP 内状态如实保留封包前 `PENDING_POSTSEAL_REPLAY`。旧包外 R2 `delivery/FINAL_STATUS.json` 与 R1 `delivery/DELIVERY_STATUS.json` 分别说明后续解包回放完成，仍待 GPT / 用户审查；不能把包内候选时间状态误认最终失败，也不能据此声称用户已接受。
- 旧 R1 的 104 是 primary 任务计数，121 是 actual attempts，92 是 solver invocations；它们均不是独立建筑数量。旧 R2 是 8 次正式求解、16 次 SSSP，四个固定业务任务。已读现存回执，未将历史回执冒充本角色本轮新重放。
- 独立从 R1 ZIP 内原始 `source.osm.json` 与 `mapped_edges.jsonl.gz` 实算六场景对象计数、道路类别、名称、入口、人行道标签、过街标签、access/foot/barrier，以及 ID / bbox 重叠。见 `independent_raw_inventory.json` 与 `src/independent_raw_inventory.py`，不导入作者函数。

## 分母与空间泄漏

六场景包含六个不同目标建筑；六建筑的等权 macro 可用于描述开发建筑结果，但不能称为六个独立地理组。15/15 场景对共享原生对象 ID，且均共享 way（最少 15、最多 5489）。其中部分 bbox 不相交但仍共享长 way / relation 闭包对象，应以原生 ID、完整几何与上下游网络依赖检查，不能仅靠截图边界判独立。当前六场景应留在同一开发来源／网络组。

R1 原生 mapped-edge 记录：exhibition=0、huangpu=98102、library=5435、newworld=47732、tower=3957、wukang=0。空图不代表原始源无道路；Phase 1 必须如实区分未预处理图、原始 context 与 routing graph。

六 clip 合计 highway way 计数 11411，跨 clip 有重复，不能当独立道路总数。未由原始标签缺失推断现实世界设施不存在。

## 本轮批准边界与后续检查

整体状态仅为 `FOUNDATION`；G0/G1/G2 等待用户审核。首 Public push 必须先审精确清单并获用户明确批准。新发现／下载场景即已对作者暴露，不自动成为 blind；还须审许可、独立参考、分组、可见性与访问日志。不得开展 blind 评估、批量下载、收费地图 API、训练或未经批准的新方法家族。

父提出的 Track A 同图 CSR 权重构建探针（8 固定任务、F0=w / F1=w+h、固定原始端点、只读旧薄图）属于当前有界开发范围。独立审查将检查全弧最优性证书、路径与权重、原端点、输入哈希及宏／微分母，不调用作者求路函数；此探针的重复一致性不能自动推导现场安全或新机制收益。

Phase 1 / 2 / Track A、实际浏览器与 Public 清单的具体检查已完成，范围详见下文。这里只对明确执行的初始技术范围签署；不预签新 ZIP 的封包后回放。

父在消息中澄清：对本独立角色的“0 新 API 地图采集”不限制已事先授权的数据作者三公共来源、数 MB 级、先核许可的候选预览。全 PG1 必须报告实际预览请求与字节，不能报全项目 0 地图请求。独立角色本身未再次采集矢量地图；只另读三个官方许可网页。

## 官方许可独立抽查

2026-11-12 实际 web 查看 [OSM copyright](https://www.openstreetmap.org/copyright) 与 [Geofabrik download](https://download.geofabrik.de/)：OSM 数据为 ODbL，须归属并遵守适用 share-alike；Geofabrik 明示去除用户名称、用户 ID、changeset ID 以保护贡献者个人信息。Public 发布不能因此跳过具体 derived database / produced work 判断。

NYC 历史 overview `#termsofuse` URL 当前重定向到 [What is Open Data?](https://www.nyc.gov/opendata/get-started/what-is-open-data-)；该说明页不能替代适用许可全文。已反馈数据作者核对直接条款 URL 与标准 PDF。

## 审核身份

- 作者自检：由各作者另存，当前记录不代签。
- 独立技术 review：本角色已完成下述封包前检查，无当前未决修复；固定 ZIP 封包后另出独立回执。
- GPT 审查：待审。
- 用户 G0/G1/G2 地图、数据与公开清单审查：待审。
- 整体 PG1：未完成。

## 封包前最终核验范围

1. `independent_phase1.json`：六场景全部 raw ID / tags 与 lineage 集合相同；53,509 个原始 point / way 投影几何逐对象比较，0 错误。另核对 B / D 的 point / way 阶段几何、标签保留／缺失分区、全部原生线的原始节点／segment_index／端点，以及 family raw/render 汇总。关系面的完整独立多边形重建和全局 VG 不在此项范围；不能用这项通过代替完整几何模型或物理通行真值。
2. `independent_current_graph.json`：四场景 B3 接口、接缝、portal、face 清单逐对象等于固定 R1 ZIP 中 SHA 绑定的实际 saved result；另两场景的实例化图保持 UNKNOWN / null，不伪写为 0。54 个 B 层 UNKNOWN 框的 ID / tags 与源相同，范围等于可知原始成员坐标包围盒加旧 0.01m 缓冲；A 未增加这些派生面。所有 full-global-edge 状态明确 NOT_EXPORTED，未冷建图。
3. 原生准入包含 residential / service 等车辆道路轴及 `SHARED_STREET_ASSUMPTION`，不能叫全部专用步道、人行道或已验证安全通道。C 以紫虚线区分道路轴，蓝线为人行源线。此为旧方法语义风险，未改准入规则。
4. `browser/receipt.json`：最终 map.js `3cc0072e3242626b6413058621672b3b09b9b2bbde2cfbc694a6365cd309ec02` 在实际独立 Edge / 临时本机 GET 服务中完成六场景、全景／街区／局部、图层开关、道路点选、同尺度视图、审核 JSON 导出，以及保存 B3 接口／接缝实际点选。40 个请求全为该临时本机 GET，0 新 solver，浏览器与自建服务已关闭。页面无 JS error。六个最终四联 PNG 和五个候选 section 截图已实际逐图查看。
5. 本角色实际发现 `water` LineString 被 SVG 隐式闭合填成蓝面的错误：`sh-huangpu-01` 的 `way/47088277` 黄浦江折线造成全街区假填色。作者只修渲染：Polygon / MultiPolygon 可填色，线强制 none，集合按子几何分发。保留 `renderer_failure/` 原错误实物，最终六场景增加 no-line-fill 浏览器回归，已通过；源数据未改。
6. `independent_phase2.json`：独立从原样本核对 1,235 个 feature、75,271 个 atlas SVG 顶点（包括原始内环）、全部图册 tags / source hashes / bounds；NYC 数为 362/81 与 330/91，Helsinki 为 112 与 259 个建筑 feature；Kallio 0 已观测几何、所有 12 维 BRONZE。1,063 建筑 feature / 172 sidewalk feature 不是独立任务建筑分母；五候选均未绑定注册入口，均 EXPOSED，0 个已冻结评测建筑，0 个 blind。
7. 55 个 pair 的可比较 native-ID 交集及不可比较／未采得身份的 UNKNOWN 全独立核对；三组为保守暂定来源／城市网络组，没有独立性 PASS、冻结或 blind 使用。原源 12 个空 WFS 响应被保留为错误 CRS 请求／NO_OBSERVATION，未说成现场无设施。
8. 下载器真实 ledger 是 38 次 HTTP / 23 次 vector：6 个非空保留、12 空、4 cap、1 timeout。已知 vector 应用读取 5,000,001B，OSM timeout 真正传输 UNKNOWN；3MB 仅预留假设，8,000,001B 是预算记账估计，不能证明网络传输上界。旧 limit+1 哨兵的记账边界问题已披露，代码修后没有继续采集。独立角色未重复采地图；0 paid API、训练、blind 评估。
9. `independent_track_a.json`：8 请求合计 1,665,460 弧的 min-option 成本、finite-source Bellman 证书、原始端点 ID / 坐标、连续无环路径、每段原图选项／几何／来源逐项独立通过；primal = dual = 旧 optimum。独立 reviewer solver = 0。结果只证明固定图上的工程构建与路径一致，不证明新机制收益、泛化或现实安全。批处理未稳定更快，负结果保留。
10. `independent_public_release.json` 与 `independent_binding.json`：Final Commit `3134c0ea68e00871ed6dc86ca7bc905071449dae`，tree `d2cc0492d6f4d2c739e1af373a8b82017972a4d1`；38 个 Git blob、working file、精确清单的 bytes / SHA 与集合全相同，工作树 clean。独立扫描三个可达本轮提交的 54 个 blob，未发现本检查规则下的秘密、私人绝对路径、冻结坐标、受限二进制／原始地图数据。12 个私有输出生成源与 Public 通用源码镜像逐字节相同。Git bundle SHA `0da7a0e741ee1fa6b7e4134e59e6288babb82e3f51878938e4fa51187b4a2351` 实际 `git bundle verify` 通过且两 ref 同指 Final；TA executed source 在 `81eaf8fc8a3f3997813ffef2921b169f54e05adc` 中的 blob SHA 与 protocol 全相同。没有首次 Push。
11. `browser/overview_final_receipt.json`：最终总览在实际 Edge 显示 Final Commit、全部 38 文件与 history / publication 导航，独立临时 GET 服务已关闭。秘密扫描是技术抽查，不是全部权利的法律意见；新源码许可证仍由用户决定，Public GitHub 可见性不是开源许可证，私有审核 ZIP 不是 Public 发布清单。
12. `independent_protection.json`：两个旧 Git 的 index / HEAD 文件、tracked status / HEAD / branch / remotes 与初始 SHA 全相同。四旧端口当前 TCP 拒绝（10061）；初始没有有效 HTTP 快照，无法归因或宣称其一直在线。本角色未停／起旧服务。其余 13 个历史包是作者 inventory 范围；本角色直接独立 SHA / CRC / 全 manifest 验证的是指定的最终 R1 / R2。

## 检查过程与限制

本角色两次测试选择器失败已保留：第一次点到延伸出 SVG viewport 的对象 bbox；后一次严格要求选中多个同坐标接口中的某个指定 ID。修正独立测试的可见道路名选择和同层实际选中 ID 判断后通过；没有为它们修改作者算法或假造通过。较早工具输出中的 Kallio SILVER 观察没有保存当时 raw JSON SHA；当前冻结 `build_atlas.py` `6ddf39d3592efc05d9d31d2e05030902737760f1b159e97de16c49e9b8c94073` 与当前矩阵已独立确认全 BRONZE，不将旧观察说成当前版本缺陷。

仍待后续关口：用户地图观感／现场可达性、实际注册入口与公众开放、完整独立参考、真正独立验证／盲测、G3 / G4 方法冻结及端到端功能验收。初始 foundation 的技术通过不越过这些关口。
