# 独立技术复核

审查者：`/root/free_evaluation`，独立实际代理上下文；未编写主分类器、路由器或共同约束提取函数。

状态：**发现待修复项，不能据此宣布通过**。执行时间：2026-11-11T14:53:22.323720+08:00。

## 实际核验

- raw_guard_sources：exit=0，实际记录 `audits/independent_raw_guard_sources.log`。
- closed_access_source_scope：exit=0，实际记录 `audits/independent_closed_access_source_scope.log`。
- metrics：exit=1，实际记录 `audits/independent_metrics.log`。
- geometry_graph_isolation：exit=0，实际记录 `audits/independent_geometry_graph_isolation.log`。
- historical_common_bridge：exit=0，实际记录 `audits/independent_historical_common_bridge.log`。
- budget_surface_cache：exit=0，实际记录 `audits/independent_budget_surface_cache.log`。
- source_known_access_graph_impact：exit=0，实际记录 `audits/independent_source_known_access_graph_impact.log`。

固定输入字节、30米域、1米格网和原查询分母由原封包清单对照。默认区域由独立Shapely几何运算检查是否等于有效域减共同限制；F0/F1区域、接口及无权图身份和有限代价可达集合分别对照。区域覆盖、参考外未证实扩张、路线坐标、逐段长度、原生有向边来源、终端及共同障碍/道路政策由独立代码重算。拒读探针及先冻结区域后读查询检查实际读取事件。

完整JSON回执给出本轮到底检查了哪些输入、图段、路线和有限权重；不能把抽样、源哈希或局部图检查扩大描述成全市原始拓扑独立重建。

北门沿用同一观测字节的历史M0/M1纯区域缓存，缓存不含旧路线、query、reference、read_log或features。原分类源码、配置锁、区域cells/hash及旧日志“先冻区域后读query”独立核查；新运行只构建共同约束M1-C和F0区域，F1只重赋有限代价。它不属于本轮重新执行旧分类器，不能与25受控任务的实际分类重建混称。中断预算原4次上界收据保留，依据当时完整worker目录没有constraints输出及冻结源码先后顺序，追加修订最多2次；这个上界修订不等于知道中断时精确完成了2次。实际缓存及预算依据见`free_budget_cache_review.json`。

北门第一次路由只有3/8可达，5个原可见端点被16个通用接口截断，并非新障碍或区域被限制。修复只在原query读入后，为精确存在于同一可见源图且层级/权限兼容的端点提供同容差整段终端绑定；它不产生新门，不改原角色/坐标。原3/8结果保留，原区域与无权图不变。此次路由续算实际加载整份旧prediction作冻结元数据及历史对账，旧路线未传入新router；继承的分类读取日志与实际resume日志分开核查，不能冒称本次重新触发原来的拒读探针。最终纯输入ZIP重放另核修复无需旧路线。LOCAL基线原合同未计算，不把它当作原生不可达，也不把自然多端点到达称为隐藏参考恢复。

## 发现与修复的承接

首轮发现负例水体的格片分割产生微小假设区域交叠：`free_geometry_defect_R0.json`保留原SHA和具体格片；受影响结果应修复后重新构建，不能通过提高指标阈值隐去。该记录是历史缺陷，最新复核结果见当前回执，不把旧失败覆盖成当时通过。

最后来源复核还发现一项未修复问题：主25任务中的`W7a6b5a10076_G_080`漏导了原源已登记private停车面，F0/F1开放其内部约128.39平方米。M1-C在该区保持UNKNOWN；F0/F1原固定两条查询路线都没有穿入这块私有面，不能把它们伪报为路线违规，也不能借路线恰好避开掩盖区域和图中存在已知权限冲突。原25任务和33正例查询分母保留，受影响比较标`COMMON_CONSTRAINT_INCOMPLETE`。F0公式相对声明的B_common成立，但B_common不完整；区域构建上界200已达，不在本轮偷偷重建或补改原预测。详见`closed_access_D30_independent.json`、`source_access_graph_impact.json`和逐行指标的源权限字段。这不是可以用原4个已知障碍零误放替代的问题。

北门的另一处7/8评分争议来自把一个闭合private停车面外环误当墙。源证据证明既有明确foot=yes步道沿共享原节点的精确边界走，停车面内部穿越为0；评分仅对机器可核的具体原生共边给予精确线例外，私有内部及真实非闭合限制线继续检查，不使用全球native或foot=yes通配豁免。该解释修复不会为上述128.39平方米区域违规开脱。

## 未核验范围

这批参考已暴露，属于同源受控配对诊断。未核验现实中漏标障碍、公众许可、实时开放和全部同层关系；已知4个障碍控制服从约束不能证明未知空间安全。北门仍是原`entrance=exit`，到门外路线不等于可以入馆。完整自然案例旧前段图按哈希和实际采用边的方向、坐标核验，本记录不声称重新独立构建全市网络。最终ZIP解包复放有单独收据；未生成收据前不宣称通过。用户自然语言验收仍待完成。
