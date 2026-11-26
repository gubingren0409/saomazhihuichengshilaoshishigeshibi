# 当前能力与限制

状态只描述对应范围，不用一个百分比代替整个项目成熟度。

|模块|状态|实际范围与限制|证据|
|---|---|---|---|
|地图源接入|`IMPLEMENTED_AND_TESTED`|本地OSM结构化输入与Geoapify历史地图/路线基线；非两套独立真值|[R-OSM-GEOAPIFY-PILOT-R3](evidence/claims.html#R-OSM-GEOAPIFY-PILOT-R3)|
|源地图上下文渲染|`IMPLEMENTED_AND_TESTED`|冻结数据源到图可追溯，最新馆体已纠正；源一致不等于现实精度|[PG1-I11](evidence/claims.html#PG1-I11)|
|建筑身份|`IMPLEMENTED_AND_TESTED`|上海博物馆way/161090899源内核对；非任意建筑自动实体对齐|[PG1-I08](evidence/claims.html#PG1-I08)|
|登记门身份与语义|`IMPLEMENTED_AND_TESTED`|南main/北exit原坐标保留；当前开放/公众权限未知|[PG1-I08](evidence/claims.html#PG1-I08)|
|原生步行线网络|`IMPLEMENTED_AND_TESTED`|草地修复保留有效原生步道；仍有源缺标/层级问题|[M-S377](evidence/claims.html#M-S377)|
|道路轴/共享街道|`CONDITIONAL_PROTOTYPE`|明确标识轴线假设，不叫人行道|[PG1-I07](evidence/claims.html#PG1-I07)|
|原生步行面库存|`IMPLEMENTED_AND_TESTED`|修复82个漏纳唯一面；跨裁片重复不作独立样本|[M-CONNECT-82](evidence/claims.html#M-CONNECT-82)|
|面线/面面衔接|`MECHANISM_TESTED_ONLY`|精确接口机制5/8，固定业务不变；条件接缝另标|[M-CONNECT-MECH](evidence/claims.html#M-CONNECT-MECH)|
|已登记面内部穿行|`IMPLEMENTED_AND_TESTED`|完整合法面可见图接全程；8固定请求6缩短2持平|[M-FACE-APP](evidence/claims.html#M-FACE-APP)|
|街区侧向通道|`MECHANISM_TESTED_ONLY`|侧别拓扑小试，缺几何宽度/可靠路缘；候选非默认|[PG1-I06](evidence/claims.html#PG1-I06)|
|道路/过街约束|`CONDITIONAL_PROTOTYPE`|保留已知合法过街与限制，不能自由跨车道；事实缺失仍未知|[R-PG1-RESUME-STREET-SIDE-R1](evidence/claims.html#R-PG1-RESUME-STREET-SIDE-R1)|
|F0/F1局部缺标空间|`CONDITIONAL_PROTOTYPE`|同图同域有限代价；默认允许属于规划假设，非原生标签|[M-FREE-REACH](evidence/claims.html#M-FREE-REACH)|
|路线求解器|`IMPLEMENTED_AND_TESTED`|固定图真实新请求及有限图证书；非现实连续空间最优|[M-DIAG-OPT](evidence/claims.html#M-DIAG-OPT)|
|路线来源与不确定性|`IMPLEMENTED_AND_TESTED`|原生线/面派生/条件假设及失败原因分别输出|[M-E2E-APP](evidence/claims.html#M-E2E-APP)|
|CLI/HTTP/交互APP|`IMPLEMENTED_AND_TESTED`|历史功能验收和UI后修复有原记录；本交接轮不重启/重验服务|[M-E2E-APP](evidence/claims.html#M-E2E-APP)|
|未标记入口生成|`NOT_INDEPENDENTLY_VALIDATED`|历史NAV-END做过候选试验；当前PG1未实施/批准此分支，不能视为通用能力|[R-NAV-END-V2](evidence/claims.html#R-NAV-END-V2)|
|跨城市泛化|`NOT_INDEPENDENTLY_VALIDATED`|已有候选已暴露且合同不足；未冻结Validation/Blind|[PG1-I05](evidence/claims.html#PG1-I05)|
|现场真实通行与公众到达|`NOT_INDEPENDENTLY_VALIDATED`|物理门、同层、开门/权限和未登记障碍仍缺独立证据|[PG1-I11](evidence/claims.html#PG1-I11)|

## 实际业务边界

目前适用的是已有登记门、固定地图场景和合法起点下的条件末段接近原型。目标为北exit时只能请求门外接近，不能请求入馆。没有登记门的四个开发目标不能伪装成真实入口整链评价。

地图与算法结果属于开发证据；当前没有独立现场真值支持“公众一定可走”“已经找到真实主门”或“任意建筑端到端导航”。展示清楚的地图、图内最短路径和接口HTTP成功分别是有效工程成果，但不能互相替代科学证据。

门禁保留：G0首次公开/软件许可证待用户决定；G1视觉验收未由技术审查自动通过；G2数据合同和独立分组未冻结。整个Parent Goal未完成。
