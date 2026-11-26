# 请求、输出与隔离合同

统一接口：`src.planner.plan(request)`；CLI、HTTP `POST /api/plan` 和页面按钮调用同一函数。

```json
{"request_id":"my-local-query","scene_id":"sh-huangpu-01","start_id":"node/10073042336","door_id":"node/6897145227","purpose":"APPROACH_OUTSIDE","method":"F1"}
```

`GET /api/scenes` 给出六个真实目标及登记门。`GET /api/scene?scene_id=...&door_id=...` 给出冻结原图、覆盖范围、合法原生节点与门身份。`GET /api/runs/{run_id}` 提供本次实际结果，不是将历史文件冒充新求路。

仅允许列表中现有源节点，原坐标与节点 ID 一致。不提供任意位置吸附。无登记门返回 `NO_ELIGIBLE_REGISTERED_ENTRANCE`，exit 请求入馆返回 `REJECTED_ENTRANCE_ROLE`，非法起点返回 `INVALID_START`，不合合同输入返回 `INVALID_REQUEST`。合法请求无法连通时返回 `NO_VALID_ROUTE` 和最后可达前沿、端点状态、失败位置。

成功状态为 `ROUTED_NATIVE_OR_MAPPED` 或 `ROUTED_CONDITIONAL`。包含规范化输入、真实 solver invocation_id、代码/源/区域/共享无权图 SHA、分段源 ID、标签、原生/面派生/假设长度、几何长度、加权代价、连续性、原门残差和全程约束检查。费用不是米制几何长度或概率。零长度单列，不混作正长度成功。

APP 预处理缓存绑定 `APP_NATURAL_QUERY` 命名空间、源及面边 SHA、观测、共同限制、代码、配置、门心域和1米格网。性能时间不进入身份哈希。每次请求重新实际图搜索，路线答案缓存关闭；图使用请求私有拓扑与纯权重回调，有限代价不写回共享边。服务发现src/config所覆盖的规划内核变更会要求重启；HTTP包装器和页面版本另由固定包清单绑定。避免把旧加载内核与磁盘新版本混写。

`BENCHMARK_REGRESSION` 是独立受控命名空间。固定25父任务/41查询不变，30米评价和1米格网不变。可信源导出只提供独立负向权限面；隐藏正向几何、成员数组、参考与旧路线不进入预测。所有历史旧答案只在新结果完成后进行比较。

前段来自完整取得源图，整段限制按完整源范围检查；自由空间连接只在原门心30米内检查。原生草地步道的背景例外不开放整片草地；private 面的精确原生沿边例外不允许进入私有面内部。已标步行面派生边仍按非原生线接受共同限制检查。

所有坐标单位为米，工作 CRS EPSG:32651；原 OSM WGS84 原件不变。未知同层/漏标障碍/权限不是已证实事实，条件规划许可与来源事实分开。
