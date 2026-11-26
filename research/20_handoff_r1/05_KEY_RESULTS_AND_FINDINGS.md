# 关键结果与负面结果

这里的数字全部保留各自分母，不生成一个“项目总成功率”。原CSV/JSON、版本及SHA均能从结论矩阵进入。

| 实验与单位 | 实际结果 | 允许的解释 | 不能推导 |
|---|---|---|---|
| NYC登记关系，1570个EP查询 | LambdaRank Top1 1408/1570，约89.68% | 已知登记EP的AP排序有学习证据 | 89.68%的人能进楼 |
| NYC P1条件几何，1570个EP查询 | 原端点32/1570；N1后1522/1570；N1+A3后1541/1570，约98.15% | 端点表示显著影响指定几何规则下路径是否可构造 | 98.15%真实导航成功；1541中含1条零长度 |
| NYC同域过夜主M，30个EP×起点查询 | 条件链24/30；完整来源支持链0/30 | 可以画出不等于每一段有通路来源 | 现实没有道路或算法已解决整链 |
| NAV-END V1，240图／28有参考图 | 未知任务到自选点208/240；登记入口Top1 9/28；已知独立几何23/28 | 浏览器开放图建库与几何原型可实现 | 自选候选是真门，或商业App截图自动成功 |
| 北门N0/N1/N2，单开发门 | N2允许域31.80m²，仍选与N1相同约7.95m直线 | 无冲突的可行直线本来就是该局部最短 | 同层或公众通行证据得到提升 |
| 草地修复，六裁片源身份去重 | 恢复377原生片段、754有向弧 | 背景草地不应抹去已有有效步道 | 377栋楼或377条新造通道 |
| 区域恢复R3，7面参考 | 覆盖18.88/3996.53m²，约0.47%；7面无一过半 | 区域表示机制实现，但当前恢复能力不足 | 独立泛化或稳定恢复已成功 |
| FREE-SPACE，33正例查询 | M1-C 20/33；F0/F1同26/33，增加6、失去0 | 明示规划假设可扩展条件可达集合 | 26栋独立建筑、100%真实可通行 |
| FREE-SPACE共同26查询 | F1假设段总长较F0少约24.65m，几何总长多约4.67m | 同图不同有限代价改变偏好 | 风险概率下降或全程更安全 |
| 已知门E2E功能验收 | 8/8合法应用请求真实求解；7固定受控失败保留NO_PATH | CLI/HTTP/页面能提交新请求，失败可追溯 | 8/8是公众导航可靠率 |
| 完整步行面，8个业务请求 | FULL_FACE较边缘带6缩短、2持平；南门159.20→148.86m | 图表示造成的绕行可改善 | 现实全局最短，或北exit可入馆 |
| CONNECTIVITY-R1，8局部机制 | B0/B1/B2/B3为3/8、4/8、5/8、5/8；新增82唯一面 | 源面完整性和局部接口改善 | 四条业务路线已改善；实际均不变 |
| CONNECTIVITY-R2，82新增唯一面 | 36在业务面池：更贵19、其他有向分量16、无当前owner1；46在池外 | 解释固定业务路线为何不使用新增对象 | 其他起终点也无收益，或现实无路 |
| PG1侧向小试，18格最终主矩阵 | R0四连通+二零长；R1三连通+一断+二无端点；R2四连通+二断 | 侧别机制与假设可以被显式表达 | R2普遍更好、示意偏移是真实人行道 |

上述表格的逐指标证据：[L-NYC-MATCH](evidence/claims.html#L-NYC-MATCH) [L-P1-RAW](evidence/claims.html#L-P1-RAW) [L-P1-N1](evidence/claims.html#L-P1-N1) [L-P1-A3](evidence/claims.html#L-P1-A3) [L-NYC-CHAIN](evidence/claims.html#L-NYC-CHAIN) [E01-03](evidence/claims.html#E01-03) [E01-04](evidence/claims.html#E01-04) [E01-05](evidence/claims.html#E01-05) [R-OSM-GEOAPIFY-R4-NORTH-ACCESS-R1](evidence/claims.html#R-OSM-GEOAPIFY-R4-NORTH-ACCESS-R1) [M-S377](evidence/claims.html#M-S377) [M-R3AREA](evidence/claims.html#M-R3AREA) [M-FREE-REACH](evidence/claims.html#M-FREE-REACH) [M-FREE-COST](evidence/claims.html#M-FREE-COST) [M-E2E-APP](evidence/claims.html#M-E2E-APP) [M-E2E-FAIL](evidence/claims.html#M-E2E-FAIL) [M-FACE-APP](evidence/claims.html#M-FACE-APP) [M-CONNECT-MECH](evidence/claims.html#M-CONNECT-MECH) [M-DIAG-82](evidence/claims.html#M-DIAG-82) [PG1-I06](evidence/claims.html#PG1-I06)

## 必须保留的负面或不确定结果

早期严格通路方案在许多图像任务中无法给出路线；G5新增确认未优于旧候选选择；本地与托管返回率不同但状态、终点身份和底层引擎并不等价；扩大观察上下文没有新增正例可达；区域恢复覆盖率很低；F0扩大范围同时带来大量参考外未证实扩张；七个stairs-only失败不能用平面吸附消除；接口局部成功未转化成四业务收益；批量成本构建7/8更慢。各项完整分母、失败原因和原文见逐轮目录，不把这些结果藏在成功图后。

## 哪些认识属于归纳

`INTERPRETATION`：当前问题同时包括数据和表示。缺少同层、宽度、许可或真实连接证据时，复杂算法不能制造事实；但已有步行面漏读、草地误排有效步道、接口没进图、地图绑定错等确实是可修复的工程/表示问题。两者必须分别记录，不能把全部失败归为数据不足，也不能以算通替代真实通行证据。
