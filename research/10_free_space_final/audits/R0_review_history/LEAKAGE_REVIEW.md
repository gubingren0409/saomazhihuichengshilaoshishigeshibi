# 输入与评价隔离复核

独立角色：`/root/free_evaluation`。原始参考只由评价器读入。实际worker开放日志检查observed/common guards/config在区域冻结前读取，query和自然案例完整前段图在冻结后读取；reference和提前query拒读探针必须实际触发。F0/F1复用相同冻结区域和无权图，参考不能决定障碍、候选域、权重和接口。

共同道路补导逐条从原始OSM节点序列重建后，只按固定观测上下文裁切；禁止把隐藏目标或成员way原样导回，也不使用参考形状刻出孔洞。独立道路与隐藏路径共享坐标时，独立道路几何可保留，其隐藏节点ID、成员数组不会被序列化为预测输入。原v1过度删除共享节点道路的版本留存，正式以v2来源审查回执为准。

这里是应用层文件打开审计和已记录几何依赖检查，不是操作系统隔离或未知事实的证明。可执行状态和覆盖数量见`free_review_receipt.json`、`free_input_identity.json`、`free_guard_source_audit_v2.json`和`free_independent_checks.json`。未完成或失败不得用本段说明替代通过记录。

自然北门另允许显式标记的旧observed-only classifier surface缓存；其observed、源码及配置绑定必须相同，且纯surface载荷中不能有旧查询/路线/参考。缓存身份与本轮新分类执行分开，旧表面在历史阶段的冻结先于query；当前MC/F0仍在当前query/full-route-graph之前冻结。实际载荷审查与预算阶段证明见`free_budget_cache_review.json`，不把这一缓存通道推广到受控隐藏目标。

北门随后ROUTE_ONLY_RESUME是断点修复角色，确实读取旧prediction整份元数据，其范围不伪装成observed-only分类器或操作系统沙箱。原分类阶段拒读日志是继承证据，本次实际read_bytes/GZIP日志单列，区域/图/固定query的原哈希及父prediction哈希逐项核对。独立源码检查确认旧routes只用于历史可达数对账，新绑定只使用可见源图精确ID/坐标与整段约束。最终ZIP中从纯observed和surface-only缓存重放北门，才是新增无旧路线输入的复验。

权限面源解释文件是POST_AUDIT_EVALUATION角色，未回灌预测器。原私有面漏导仍保留为已知共同约束缺口；不能将本次评价端追加证据说成模型运行时已拥有该输入。
