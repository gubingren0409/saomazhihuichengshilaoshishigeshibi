# Q2 / Q6 / Q7 / Q8 统一研究审查报告

生成：2026-11-15T05:34:44.018137+08:00。**本轮已有可执行工作收尾；缺失输入和未完成资格单列，没有补造结果。**

## 1. 实验范围和未完成项目

本轮按用户附件执行5个独立ID，全部写入新目录。Q2是地图内部核验及新求路；Q6A是源身份、保存轨迹复算及当前冻结草地策略复核；Q6B因缺现场资料受阻；Q7包含新状态注入适配器和未修改APP的负控；Q8测小裁片、相邻两裁片合并、Top-3和指定断边重求路。不是现场导航验收，也不是新的盲测。

| 项目 | 状态 |
| --- | --- |
| Q2 | PASS |
| Q6A | INCONCLUSIVE |
| Q6B | BLOCKED_BY_MISSING_INPUT |
| Q7 原接口 | FAIL |
| Q8 总体一秒要求 | FAIL |

缺项及精确原因：[机器可读清单](audit/MISSING_AND_UNTESTED.csv)。不得将同一建筑多个门、重复计算或重叠裁片计为独立建筑。全轮仅2栋建筑提供合格登记门，Q2是3个门，Q8独立计时地点为2处；同址重复不增加样本独立性。

## 2. 输入数据和代码版本

主运行代码/6裁片来自固定 Connectivity-R1 ZIP，SHA256 `d5934ae928e656f7bdc5618b63e2293403ce0b736809d2050fc2f41caac393ed`；49个冻结源码/配置/输入的逐文件SHA见 [冻结清单](audit/FROZEN_RUNTIME_MANIFEST.json)。版本身份采用内容哈希，不新建commit、不处理历史暂存。Q6另核验6个固定阶段归档SHA，见 [来源表](Q6-LOCAL-MAP-CONSISTENCY-R1/provenance.csv)。

本轮新增状态注入、CLI计时、Yen Top-3与合并输入适配器代码单列，见 scripts/ 和 audit/NEW_CODE_MANIFEST.csv；**不是“完全没有新增算法代码”**。旧源码、旧结果、入口标签及原坐标不改。原生线类包含原合同允许的道路轴，不能统一叫“已知人行道”。工作CRS为 EPSG:32651 米。Python/依赖、RAM、CPU和时钟见 environment.json。随机算法未使用，PYTHONHASHSEED未控制；图哈希与路线输出实际核对。没有下载新地图或调用API，没有训练。

初次B3非主分支构图在512.49秒被本轮主动中止，只能作为未完成诊断下界，不是完整求路耗时。随后按公开默认 FROZEN_FULL_FACE/B0 预先记录主协议修订。计时执行时已观察Q2性能，属于公开工程诊断，不是盲评。

## 3. Q2 入口坐标、门身份与接入结果

南门 node/6897141353、北出口 node/6897145227 均属于 way/161090899；图书馆门 node/11300000483 属于 way/293434188。三个点均在各自原生外环上，坐标和标签吻合，边界距离均0米。**main/exit不代表当前开放；北门只请求到门外，不能用于入馆。**

| 场景 | 目标 | 状态 | 长度 m | 离登记门 m | run_id |
| --- | --- | --- | --- | --- | --- |
| sh-huangpu-01 / node/6897141353 | REGISTERED_DOOR | PASS | 148.863 | 0.0 | Q2-TARGET-0-REGISTERED_DOOR |
| sh-huangpu-01 / node/6897141353 | BUILDING_CENTROID | NO_PATH | — | 37.833 | Q2-TARGET-0-BUILDING_CENTROID |
| sh-huangpu-01 / node/6897141353 | NATIVE_OUTSIDE_APPROACH_POINT | PASS | 430.083 | 55.015 | Q2-TARGET-0-NATIVE_OUTSIDE_APPROACH_POINT |
| sh-huangpu-01 / node/6897145227 | REGISTERED_DOOR | PASS | 300.784 | 0.0 | Q2-TARGET-1-REGISTERED_DOOR |
| sh-huangpu-01 / node/6897145227 | BUILDING_CENTROID | NO_PATH | — | 47.769 | Q2-TARGET-1-BUILDING_CENTROID |
| sh-huangpu-01 / node/6897145227 | NATIVE_OUTSIDE_APPROACH_POINT | PASS | 286.35 | 16.397 | Q2-TARGET-1-NATIVE_OUTSIDE_APPROACH_POINT |
| sh-library / node/11300000483 | REGISTERED_DOOR | PASS | 180.581 | 0.0 | Q2-TARGET-2-REGISTERED_DOOR |
| sh-library / node/11300000483 | BUILDING_CENTROID | NO_PATH | — | 37.39 | Q2-TARGET-2-BUILDING_CENTROID |
| sh-library / node/11300000483 | NATIVE_OUTSIDE_APPROACH_POINT | PASS | 180.581 | 0.0 | Q2-TARGET-2-NATIVE_OUTSIDE_APPROACH_POINT |

登记南门路线包含58.302米原生段和90.561米面派生段；北出口为125.565米原生、165.537米面派生及9.682米假设段；图书馆为180.581米原生段。原生线类仍可能包含原合同允许的道路轴，不等于全程独立人行道。

相同起点/源/成本下，3个中心点均未能合法绑定到楼内目标而 NO_PATH；3个登记门请求都形成条件路线。该对照是终点定义与契约可行性控制，不是对现实导航方案优越性的准确率测试；身份注释另见target_definition_comparison_annotated.csv。原生接近点不是另一扇门，也不是同一门的替代真值；博物馆南门对照的原生点在楼旁另一位置，430米路线不能写成“最佳入口更差”。图书馆接近点与门重合，该次对照未观察到额外收益，不能外推“无需接入补全”。

证据：[身份表](Q2-LOCAL-ENTRY-AUDIT-R1/entry_identity_audit.csv)、[目标对照](Q2-LOCAL-ENTRY-AUDIT-R1/target_definition_comparison.csv)、[接入价值](Q2-LOCAL-ENTRY-AUDIT-R1/entry_access_value.csv)。逐条原始响应 outputs/Q2-TARGET-*.json，raw_results.jsonl 中有同名run_id。距离对象分别是道路轴、原始步道和当前准入面Omega，不能当路缘/全部人行空间。补充的全源障碍/关系上下文见 entry_constraint_context_A1.csv；原nearby_restrictions列只是way线筛查，不能据空列表称附近无障碍。

补充审计A0还发生了本轮新脚本的CRS错误：把Source.coord返回的经纬度与米制面比较，使上下文误空、身份重核出现约347万米假距离。原始6行保留但明确失效，错误版本不用于结论；A1改用Source.projected，重新得到3个边界距离0米及源上下文。原entry_identity_audit与9条规划请求本来就正确使用米制，未受影响。修正记录见 audit/Q2_SUPPLEMENTARY_CRS_CORRECTION.json；不能把测试器错误归因于入口或旧算法。

旧博物馆路侧窗口确有场景绑定错误：其范围未覆盖真正博物馆；本轮保留旧证据，并以正确目标建筑/登记门和源数据重新核验，不改旧路线。见 window_binding_audit.csv 和 outputs/window_definition_sources.json。

## 4. Q6A OSM内部一致性结果

核对6裁片306,927条源记录与保存的适配器清单，ID/标签匹配差异0。这个数量包含重复源对象，不是独立对象数。377条恢复原生片段的节点、源ID、标签、版本及长度一致，754是有向弧声明数；**不是754条独立步道，更不是现实同层已核验。** 本轮实际用当前冻结S0/S1策略再次评估377条，377条表现为旧策略拒绝、修正策略保留；4项合成检查另列，不混作现场证据。未标通行线/私有步道/无桥水体反例仍拒绝。原生步道例外只适用于明确线对象，没有将草地面全部开放。

82个新增唯一登记面源身份均对齐，36个在保存的业务面池中；47个从未出现在保存的业务查询命名空间，19个涉及“旧路线严格更便宜”，16个涉及“其他有向分量”（各面原因集合详见 added_face_usage.csv）。这些是**重核原ID后的保存分量/owner/替代证据**，不是本轮新建所有历史SCC。新增面与路线几何相交也不等于路线使用了该面；池外与未采用不是漏读。

353组保存路线、13,924个保存段实例（不去重，不等于独立现实路段）重新计算几何。最终316组 PASS、37组 INCONCLUSIVE：29组不能可靠关联原始场景，8组聚合几何不能拆回原生/派生构成。分组数含同一请求/版本相关保存结果，不能当353条独立业务案例。已知场景的本轮二维源接触检查没有保留明确冲突标志，但这**不是全层级、全历史准入例外或现实可走证明**。严格1e-8数值差异与原1e-6约束容差同时保留，没有改旧值。

新审计器曾将8个聚合文件误判为缺layer的FAIL；只修了本轮解析口径，原错误表保留在 attempts/A2_AGGREGATE_SCHEMA_FALSE_FLAGS，改为信息不足的INCONCLUSIVE，未改旧算法。另两次审计器字段接口错误保留 RUNTIME_ERROR。104个旧响应的SHA绑定均匹配。

证据：[恢复表](Q6-LOCAL-MAP-CONSISTENCY-R1/restored_native_edges.csv)、[377条新策略复核](Q6-LOCAL-MAP-CONSISTENCY-R1/grass_policy_recheck.csv)、[82面](Q6-LOCAL-MAP-CONSISTENCY-R1/added_face_usage.csv)、[保存几何复算](Q6-LOCAL-MAP-CONSISTENCY-R1/replay_comparison.csv)、[约束审计](Q6-LOCAL-MAP-CONSISTENCY-R1/route_constraint_audit.csv)。各行包含run_id、stage、source_file。run `Q6-GRASS-CURRENT-FROZEN-POLICY-377` 与 `Q6-AUDITOR-A3-AGGREGATE-SCHEMA-RECHECK` 对应本轮检查。

## 5. Q6B 现场真值对照

**BLOCKED_BY_MISSING_INPUT。真实调查0栋、0条路线、0个逐段现场标签。** 六行route_level_comparison只是计划槽位，不能当实走分母。没有独立调查人员、带时戳照片/轨迹、同层/门禁状态，也没有第三栋建筑及足够目标。现实可走比例、假阳性、漏报、距离误差和假设段命中率均不可计算，表内留空，不填0。

证据：[现场协议](Q6-FIELD-TRUTH-COMPARISON-R1/field_protocol.md)、route_level_comparison.csv 和 raw_results.jsonl 中6条 BLOCKED记录。没有用地图/AI审核补造真值。

## 6. Q7 动态封闭与障碍模拟

2个场景 × 6状态 × 3次 = 36次新状态适配器请求；不是36个独立场景。封闭状态每次从S0单独构图，不累计；禁用答案缓存。主表状态适配器的实际结果为{'PASS': 18, 'NO_PATH': 18}；适配器违规使用被禁对象0次，S5六次都恢复S0几何。首次状态图构建/热重复与**进程冷启动**不同，Q7未冒称测了完整冷进程，Q8另测。

| 场景 | 状态 | 重复 | 结果 | 违规数 | run_id |
| --- | --- | --- | --- | --- | --- |
| sh-huangpu-01 | S0 | 3 | {'PASS': 3} | 0 | Q7-A1-NATIVE-WALKWAY-0-S0-0 |
| sh-huangpu-01 | S1 | 3 | {'NO_PATH': 3} | 0 | Q7-A1-NATIVE-WALKWAY-0-S1-0 |
| sh-huangpu-01 | S2 | 3 | {'PASS': 3} | 0 | Q7-A1-NATIVE-WALKWAY-0-S2-0 |
| sh-huangpu-01 | S3 | 3 | {'PASS': 3} | 0 | Q7-A1-NATIVE-WALKWAY-0-S3-0 |
| sh-huangpu-01 | S4 | 3 | {'NO_PATH': 3} | 0 | Q7-A1-NATIVE-WALKWAY-0-S4-0 |
| sh-huangpu-01 | S5 | 3 | {'PASS': 3} | 0 | Q7-A1-NATIVE-WALKWAY-0-S5-0 |
| sh-library | S0 | 3 | {'PASS': 3} | 0 | Q7-2-S0-0 |
| sh-library | S1 | 3 | {'NO_PATH': 3} | 0 | Q7-2-S1-0 |
| sh-library | S2 | 3 | {'NO_PATH': 3} | 0 | Q7-2-S2-0 |
| sh-library | S3 | 3 | {'NO_PATH': 3} | 0 | Q7-2-S3-0 |
| sh-library | S4 | 3 | {'NO_PATH': 3} | 0 | Q7-2-S4-0 |
| sh-library | S5 | 3 | {'PASS': 3} | 0 | Q7-2-S5-0 |

**原APP功能检查FAIL**：2次未修改公开plan接口负控，传入closed_doors后仍返回该门路线，因为旧接口不处理动态状态参数。证据主表run `Q7-NATIVE-API-CONTROL-2`、`Q7-A1-NATIVE-WALKWAY-NATIVE-API-CONTROL-0`；原始响应保留。本轮负控直接调用P.plan，没有另测HTTP服务器是否先拒绝未知字段；这说明当前产品缺动态状态入口，不能用新增实验包装器的0违规写成“现有APP动态容错已通过”。

博物馆A1 S2/S3各3次得到151.961475米条件绕行，比原148.863122米增加3.098353米，仍为原生/登记面派生且假设段0米；被删步道的几何重叠为0。图书馆相应S2/S3各3次仍NO_PATH，不能推断现实无路。

首版博物馆按“native”取中间边，实际取到residential道路轴，不符合原生步道封闭要求。保留首版19行（含旧接口负控）为secondary压力测试，按原baseline中的源标签锁定footway way/178737605后重跑博物馆组；图书馆way/1219527813本来就是footway，保留原19行。主表仍为38行（36状态请求+2接口负控），另存一次基线重核。关闭对象不同，不能把结果变化写成算法增强；原核心/目标/起点/成本不变。

前置“两个场景都有合法备用接近方向”未完整建立。图上重求路结果逐行保留，**没有证明两个场景均具现实备用路线恢复能力**，也没有证明现实无其他路。Top-3图书馆路径是节点序列不同的候选，仍共享主要走廊，不能补充为三个独立现场通道。没有自动感知关门、施工、人流/GPS或门禁。

证据：[逐次状态结果](Q7-DYNAMIC-CLOSURE-SIMULATION-R1/dynamic_route_results.csv)、closure_edge_changes.csv、forbidden_object_usage.csv、fallback_route_comparison.csv、outputs/Q7-*.json；逐条物理几何重叠和增距见 [replanning_geometry_comparison.csv](Q7-DYNAMIC-CLOSURE-SIMULATION-R1/replanning_geometry_comparison.csv)。删除对象为保存edge_id的有向边，障碍是2米或更小的合成方框，不是新增现场障碍事实。

## 7. Q8 性能结果

当前计时结果：453次观测，其中33次warm-up排除，420次正式观测。正式观测的重复是性能重复，不是新的地理样本。小规模：图书馆单裁片；中规模：与武康相邻裁片按原生ID兼容字段合并，64,368个唯一源对象、36,107个共享ID，缺失元数据补齐而非任意版本覆盖，真实覆盖用两个采集窗口的几何并集，不把包围盒空角伪装为采集覆盖。合并后图仅有适度增大，不能冒称接近城市级规模。

主单路径/Top3/指定断边配置3次热身后30次热进程请求、10次新进程冷请求；博物馆K2构建昂贵，预先采用允许的10次热、10次冷最小配置；冷构建较慢，采用协议允许的至少10次。F0/F1同图只改假设段代价。Top-3是本轮新增Yen实验适配器，只测小图FULL_FACE/F1，三个节点序列不同，不保证三个独立通道。指定断边后的重求路若NO_PATH，照样保留耗时，不能把它当成功导航。

| 规模 | 任务 | 模式 | 计时 | n | p95 ms | 最慢 ms | 一秒门槛 | 返回结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 图书馆小裁片 | 单路径 | 边缘带 / F0 | 热 · 求解阶段 | 30 | 6.6 | 7.21 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 边缘带 / F0 | 热 · 核心请求 | 30 | 107.82 | 110.15 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 边缘带 / F0 | 冷 · 新进程端到端 | 10 | 24884.92 | 25369.74 | 不满足 | PASS×10 |
| 图书馆小裁片 | 单路径 | 边缘带 / F1 | 热 · 求解阶段 | 30 | 2.64 | 2.73 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 边缘带 / F1 | 热 · 核心请求 | 30 | 101.83 | 102.68 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 边缘带 / F1 | 冷 · 新进程端到端 | 10 | 24296.38 | 24499.88 | 不满足 | PASS×10 |
| 图书馆小裁片 | 单路径 | 完整面 / F0 | 热 · 求解阶段 | 30 | 10.64 | 10.95 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 完整面 / F0 | 热 · 核心请求 | 30 | 151.0 | 155.16 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 完整面 / F0 | 冷 · 新进程端到端 | 10 | 34105.14 | 34870.44 | 不满足 | PASS×10 |
| 图书馆小裁片 | 单路径 | 完整面 / F1 | 热 · 求解阶段 | 30 | 3.05 | 4.51 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 完整面 / F1 | 热 · 核心请求 | 30 | 106.45 | 112.4 | 满足 | PASS×30 |
| 图书馆小裁片 | 单路径 | 完整面 / F1 | 冷 · 新进程端到端 | 10 | 35529.5 | 35617.35 | 不满足 | PASS×10 |
| 两裁片合并 | 单路径 | 边缘带 / F0 | 热 · 求解阶段 | 30 | 6.38 | 6.42 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 边缘带 / F0 | 热 · 核心请求 | 30 | 121.22 | 122.57 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 边缘带 / F0 | 冷 · 新进程端到端 | 10 | 31896.15 | 31963.32 | 不满足 | PASS×10 |
| 两裁片合并 | 单路径 | 边缘带 / F1 | 热 · 求解阶段 | 30 | 4.03 | 4.25 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 边缘带 / F1 | 热 · 核心请求 | 30 | 146.64 | 160.88 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 边缘带 / F1 | 冷 · 新进程端到端 | 10 | 30742.33 | 30913.38 | 不满足 | PASS×10 |
| 两裁片合并 | 单路径 | 完整面 / F0 | 热 · 求解阶段 | 30 | 9.01 | 10.5 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 完整面 / F0 | 热 · 核心请求 | 30 | 151.84 | 166.5 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 完整面 / F0 | 冷 · 新进程端到端 | 10 | 39722.07 | 40267.82 | 不满足 | PASS×10 |
| 两裁片合并 | 单路径 | 完整面 / F1 | 热 · 求解阶段 | 30 | 4.47 | 4.51 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 完整面 / F1 | 热 · 核心请求 | 30 | 167.72 | 169.74 | 满足 | PASS×30 |
| 两裁片合并 | 单路径 | 完整面 / F1 | 冷 · 新进程端到端 | 10 | 38739.95 | 38877.16 | 不满足 | PASS×10 |
| 图书馆小裁片 | 删边重求路 | 完整面 / F1 | 热 · 求解阶段 | 30 | 98.83 | 103.34 | 满足 | NO_PATH×30 |
| 图书馆小裁片 | 删边重求路 | 完整面 / F1 | 热 · 核心请求 | 30 | 711.05 | 727.58 | 满足 | NO_PATH×30 |
| 图书馆小裁片 | 删边重求路 | 完整面 / F1 | 冷 · 新进程端到端 | 10 | 35292.73 | 35800.85 | 不满足 | NO_PATH×10 |
| 图书馆小裁片 | Top3新适配器 | 完整面 / F1 | 热 · Top3生成 | 30 | 519.33 | 530.26 | 满足 | PASS×30 |
| 图书馆小裁片 | Top3新适配器 | 完整面 / F1 | 热 · 核心请求 | 30 | 659.77 | 674.56 | 满足 | PASS×30 |
| 图书馆小裁片 | Top3新适配器 | 完整面 / F1 | 冷 · 新进程端到端 | 10 | 37398.97 | 37429.8 | 不满足 | PASS×10 |
| 博物馆双门 | 双门新适配器 | 完整面 / F1 | 热 · 求解阶段 | 10 | 1029.09 | 1043.38 | 不满足 | PASS×10 |
| 博物馆双门 | 双门新适配器 | 完整面 / F1 | 热 · 核心请求 | 10 | 6229.08 | 6324.6 | 不满足 | PASS×10 |
| 博物馆双门 | 双门新适配器 | 完整面 / F1 | 冷 · 新进程端到端 | 10 | 350142.5 | 350561.06 | 不满足 | PASS×10 |

**不能宣称系统总体一秒返回。** 仅某配置某计时口径的p95和最慢值都≤1000ms才能称该配置达标；冷进程端到端包含Python启动/导入/读取/构图/绑定/求解/检查/写出/退出；热core时间不含之后的序列化落盘，不含HTTP/页面。求解器阶段不能代替完整请求时间。每个图/方法/任务配置先做3次热进程warm-up并排除；冷请求均从新Python进程开始，不在同一进程内预热，也不事后丢弃较慢冷启动。阶段计时相互包含，不能相加；read_ms只计Path.read_bytes/read_text，gzip等内部IO未全部单独分离；index_ms只计STRtree构造，不代表所有数据结构索引。图预处理包含解析、约束、构图、哈希和收据写出，不是纯建图独占时间；这些相互嵌套，不能相加。钩子仅代理原操作，测量开销未扣。10ms RSS采样是观察峰值，不是系统连续精确峰值。OS文件缓存、桌面负载与hashseed未隔离，不能据此断言因果加速或生产SLA。

计算图节点/有向弧含格网、面派生可见边和接口，不等于真实路口/道路数；博物馆单裁片图比“两裁片合并”的图书馆图更密，不能按裁片数推断规模。K2的solver_ms是两次原求解之和，candidate_ranking_ms才是对两个代价值排序。

候选数实测K=1和K=2。K2是新增适配器：同一博物馆、同一原起点，对原登记南门/北出口分别按APPROACH_OUTSIDE求路，再按冻结F1代价/原生ID选留；北出口没有当入馆门。该实现保留两个按原门分别生成的预处理对象，不合并成新的全局多目标图。K2的图节点/弧数量报告单个候选图的最大值，不把重复全图相加制造规模。它与图书馆K1不是同图配对，不能据耗时比值推导候选数增长复杂度。10/100真实登记候选缺失，原APP仍未提供联合选择接口。大规模同合同数据未就绪，NOT_RUN。没有用其他城市旧网络替代。原接口没有的Top3/EDGE能力与实验适配明确分开。

证据：[全分布](Q8-SCALE-LATENCY-BENCHMARK-R1/latency_distribution.csv)、observations_normalized.csv、benchmark_matrix.csv、medium_benchmark_matrix.csv、top3_benchmark_matrix.csv、replan_benchmark_matrix.csv（存在时）、memory_usage.csv、route_quality_comparison.csv和failure_and_timeout.csv。各benchmark_matrix中的status只表示工作进程退出是否正常，不能当作路线成功；worker_process_outcomes.csv对齐子请求状态，实际NO_PATH见raw及route_quality表。原始每次输出使用同名run_id，Q8-A1为主小图、Q8-MEDIUM为合并图、Q8-TOP3-ADAPTER为新多路径适配器、Q8-REPLAN为指定边封闭。计时前缀不同不可混池。

Top-3 A1的43条观测保留为secondary_results版本，整体计时与路线仍有效；因缺读/索引分阶段时钟，预先记录原因后用同输入、同核心补测A2。主统计采用A2，原A1日志/输出/源码均保留，不混池、不按速度选留，也不称算法变强。

第一次性能工程运行因3个warm-up与正式输出ID碰撞整批作废。38条当时原始行仍保留，但3个warm-up的独立输出文件曾被覆盖，不能冒称全部独立输出可恢复；留存实物在 attempts/ATTEMPT_A0_WARMUP_ID_COLLISION，不纳入主统计；修复只改本轮run_id命名。合并输入第一次严格全字典相等检查被缺元数据阻断，保留 medium_merge_A0_exact_equality_block.json；后续规则要求所有共有字段相同，仅填缺字段，无冲突坐标/标签覆盖。

Top3两次有效观测均披露；差异属于负载/测量版本变化，不是算法速度改善，也不能只挑较快的一版：

| 版本 | 计时 | 温度 | n | p95 ms | 最慢 ms |
| --- | --- | --- | --- | --- | --- |
| A1_VALID_TOTAL_TIMING_NO_PHASE_SPLIT | end_to_end_worker_ms | HOT_PROCESS | 30 | 595.49 | 834.54 |
| A1_VALID_TOTAL_TIMING_NO_PHASE_SPLIT | topk_ms | HOT_PROCESS | 30 | 469.75 | 673.41 |
| A1_VALID_TOTAL_TIMING_NO_PHASE_SPLIT | cold_process_end_to_end_ms | COLD_PROCESS | 10 | 31207.81 | 31314.87 |
| A2_PHASE_INSTRUMENTED_PRIMARY | end_to_end_worker_ms | HOT_PROCESS | 30 | 659.77 | 674.56 |
| A2_PHASE_INSTRUMENTED_PRIMARY | topk_ms | HOT_PROCESS | 30 | 519.33 | 530.26 |
| A2_PHASE_INSTRUMENTED_PRIMARY | cold_process_end_to_end_ms | COLD_PROCESS | 10 | 37398.97 | 37429.8 |

## 8. 每个质询的状态和证据定位

Q2地图身份与终点对照 PASS（限地图内部）；Q6A INCONCLUSIVE（316/353保存组通过本轮有限复核，37组未足够核验）；Q6B BLOCKED_BY_MISSING_INPUT；Q7原接口 FAIL，新状态包装器仅完成无失效路线/恢复检查，备用方向资格 INCONCLUSIVE；Q8总体一秒目标 FAIL；新增K2门外选择适配器实测，原APP接口未改变；K10/K100/城市网络 BLOCKED_BY_MISSING_INPUT。

逐实验 summary.csv / summary.json、raw_results.jsonl、failures.csv 和 provenance.csv 对应各ID。run_id与输出文件逐条绑定；Q6保存几何的行级标识在replay_comparison.csv。旧阶段数值引用与本轮计算不同，不把旧结果写成本轮实跑。

## 9. 已解决的问题

完成三个原门地图身份核验及9条终点定义控制；核查旧窗口绑定偏差；核对恢复原生片段/新增面源身份；重算已保存几何；提供不伪装成旧APP功能的动态状态实验包装器；建立真实冷/热、单路径/Top3及两裁片输入计时。没有用数据对象计数充当业务收益。

## 10. 仍未达到要求的问题

缺现实真值；旧APP不处理关门/封路状态；两个动态场景未证明合法备用方向前提；37组保存轨迹未完整核验；冷启动不满足一秒；10/100候选、原APP联合选择接口与城市级性能没有验证；新增K2逐门选择适配器不能冒充可扩展联合算法。负结果和受阻项均保留，不删分母。

## 11. 没有测试过的问题

现场门是否存在/当前开放/允许公众、真实同层和动态障碍、独立盲测、跨城泛化、HTTP并发/页面总延迟、生产资源隔离、真实主备通道多样性、精确路缘宽度和完整障碍普查均未测试。合并相邻裁片是已暴露开发数据，不产生新独立验证组。

## 12. 不允许作出的结论

不得称“证明真实可走”“公众一定能进”“OSM正确”“完整导航已完成”“系统总体一秒”“377或82个对象就是路线提升”“三条节点路径就是三条现实备用通道”。北门exit不能改称入馆门；假设段不能升级为原生事实；作者检查不能写成独立现场核验。

## 13. 后续最小必要实验

首先补独立、有时间戳的6条现场逐段记录及合格第三建筑；补37组保存轨迹缺少的关联/构成字段；若开发产品动态状态接口，另行验收参数实际生效与确有备选通道的场景；准备具有同域身份/约束合同的更大网络及真实候选集合后才做联合/城市级基准。这里是缺项说明，不自动执行下一轮。

本轮来源与结果核验是**作者检查及独立脚本/新进程交叉复算**，没有额外独立人员/代理，不能冒称独立角色审核。截止本报告记录起累计约156.6分钟（含下载前旧资料定位、失败诊断、重试和等待；无本轮外网请求）。最终封包校验结果另见包外复验回执。
