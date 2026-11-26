# 源对象盘点与源几何诊断（作者范围）

用户对上轮面内穿行效果的意见保持 `PENDING_USER_OBSERVATION`。截图请求尚未唯一绑定，状态为 `SCREENSHOT_REQUEST_UNBOUND`。本记录是作者盘点、源几何诊断与自检，不是现场验证、完整路线核验或用户验收。

原始六份裁片 SHA256 均按冻结 manifest 验证；未改源字节、源坐标、门、起点或旧工程。新地图/API/采集/训练为 0。主盘点与 P/Ω/关系导出串行运行 124.52 秒，未构建密集面内可见图、未运行 APP、未求路。

| 场景 | 旧选面 | 显式源候选 | 源准入 | 旧选面遗漏 | 有非空合法 Ω |
|---|---:|---:|---:|---:|---:|
| 上海博物馆人民广场馆 | 2 | 32 | 29 | 27 | 29 |
| 武康大楼 | 0 | 5 | 3 | 3 | 3 |
| 上海中心大厦 | 1 | 54 | 48 | 47 | 47 |
| 新世界城 | 2 | 24 | 19 | 17 | 19 |
| 上海图书馆淮海路馆 | 1 | 12 | 12 | 11 | 12 |
| 上海展览中心 | 0 | 22 | 19 | 19 | 19 |
| 合计（scene-ID） | 6 | 149 | 130 | 124 | 129 |

130 是“场景—源对象”记录数。按 OSM type/id、version 与源时间戳去重后为 88 个原生面，其中 6 个曾在任一旧集合出现，82 个未在任一旧集合出现。38 个对象在多个裁片重复，不能作为独立面积证据。88 个均来自 `2026-11-08T21:21:00Z` 的冻结源时间戳。完整身份表见 `data/connectivity/global_source_identity.json`。

沿用 `area_reason` 的显式标签、步行权限优先级、普通室外地面假设和层级规则。149 个显式候选中，7 个因非地面/层级拒绝，12 个因几何超出真实覆盖拒绝。另将公园、草地及其它似面对象列入相关候选表并给出拒绝原因；未将其泛化为步行面。所有候选记录完整源 tags、对象版本、members、成员 way 的完整 nodes/tags/version/hash、内环数量、缺成员检查、源几何 hash 与覆盖差面积。六场景均未发现应再扣除的完全相同几何且 tags 相同的准入面副本。不同语义或层级的重叠没有按相近几何合并。

源准入不等于存在合法自由空间。`sh-tower:way/166128036` 的 P 面积为 947.023679816 m²，继承全源约束和原净空后 Ω 为空，状态为 `NO_LEGAL_COMPONENT`。其余 129 个场景面具有合法 Ω。此负结果保留在源锁中，不能为制造路线变化而填回限制。

## 博物馆疑点的源事实

建筑为 `way/161090899`；南门为原登记 `node/6897141353`，北门 `node/6897145227` 的 `entrance=exit` 未变。南门前旧面为 `relation/2385771`，内环含草地 `way/178721634`、`way/178721647`。北侧人民广场旧面为 `relation/2153738`，其 outer member `way/178719573` 保持独立 `highway=footway` 线身份。

- 两旧面 P 的最近距离为 10.3033632254 m；Ω 的最近距离为 10.6649470753 m。该对超过 10 m 通用探测窗，单独作为博物馆既定疑点补记；超过本轮最大 5 m 条件接缝，不能硬补。
- 南门面与东侧 `way/178737608` 共享 `node/1890935415`，与西侧 `way/178737605` 共享 `node/1890935454`，与过街线 `way/761403177` 共享 `node/1890745480`。三者的 P/Ω 距离均为 0，源关系为线端接边。
- 东北延伸步道 `way/564255372` 与南门面 P/Ω 的距离均为 7.06720947991 m，无共享源节点；超过本轮 5 m 接缝上限。
- 北侧广场与 `way/1303211746` 在 P 上线端接边，Ω 间距为 0.2500000023 m。该间隔由扣障/内环净空造成，不能当作 OSM 未画缺口填回。

这些事实解释已有源对象的接触和间隔，不能证明截图中哪一处视觉对象就是原请求。`museum_diagnostic.geojson` 提供可点选源对象，供后续同图观察和请求绑定。

## 原生线与面关系

独立回看并导出 11,411 个原始 highway 线的场景记录：6,945 个具有冻结引擎步行标签证据，902 个权限/条件拒绝，957 个非地面或未解析层级，2,465 个无冻结引擎步行证据，142 个是非独立线身份的显式面积边界。这里的标签合格不冒称逐段已入图；路由实际准入仍由原生 segment 语义、公共约束与接口实现核验。

准入面的 10 m 关系表冻结了 1,181 对：257 条线共边、206 条线端接边、200 条进入/穿越 Ω、40 条面内线、32 对面共边、13 对点触、429 对非零间隙，另 4 条关系的 Ω 为空。每对含 P/Ω 距离、相交/重合长度或面积、端点状态、共享原生节点、来源 tags、最近 Ω 连接段与约束冲突，明确区分扣障产生的分离。原生线无论是否属于面都保留独立记录。

另在 `*_rejected_relations.json` 保存 115 对涉及 19 个拒绝显式面 P 的额外关系，仅用于拒绝与层级/覆盖诊断，不进入已冻结准入集合，不参与选取新成绩。所有点触均只分类，不据此建立双侧正宽通道。几何不接触的关系不伪称精确接口。

## 事前冻结与复现

`scripts/inventory_connectivity.py` 串行重扫六源，验证 hash，使用实际 `scene_data.load_scene` 的全源 observed/guards 构建 `full_common`，再复用原 `compile_faces` 的全部准入、障碍、道路分区与 0.25 m 净空逻辑。唯一共享模块改动为 `compile_faces(..., selected_area_ids=None)` 的可选参数及迭代选集：None 保留旧锁和旧行为；提供 IDs 仍验证旧源 SHA，仅排序去重替换迭代选集。

冻结顺序为完整源集合 → P/Ω 与关系 → 最多 8 个机制类别和稳定对象 ID → 同端点证书，均未读取新路线成绩。选取优先博物馆南门 450 m 源 ROI，再按稳定 relation ID。八类为无共享节点的真实进入、面内独立线、线共边、面共边/重叠、点触、2 m 内间隙、扣障分离、明确层级/权限拒绝。未按可达性或收益挑选。

`mechanism_request_endpoints_lock.json` 给出同一原生 node ID、米制 xy、WGS84、tags、version 和绑定规则。M04 的 `way/1275365117` 没有独立合格线节点位于 P，使用 Ω 精确覆盖的最低原 outer node ID `node/2613044111`，明确为源面边界机制接口，不是入口；B0 面未纳入时应报告 `UNBOUND_TO_INACTIVE_FACE`。M08 保留层级图 ID，不能作为普通 APP 合法地面起点。作者自检发现并在任何新结果之前修正了拒绝类别 predicate 过宽的问题，以及 M04 原生线端点缺项；首个状态与原因均保存在 `source_inventory_mechanism_predicate_correction.json`、`source_inventory_endpoint_missing_resolution.json`。最终锁后不改选。

| 文件 | SHA256 |
|---|---|
| `source_selection_lock.json` | `855ebd865f893eeb7edaa90860b819b39a64ef28407329a3a235286e93793c57` |
| `relations_lock.json` | `9b74ff6ddd6bdbd797b765da7fea37ebd8e106b35df577f470ab29b2423fc8b7` |
| `mechanism_queries_lock.json` | `a9df8f9bf58f9c130c6b6b6c207b2180732f9fbac3c7adaaf9a3f213cdec307f` |
| `mechanism_request_endpoints_lock.json` | `d88d4a30508eaea694cb48100dce85951744ca4c5a0ffee514e60f030e55f57d` |

主要机器输出位于 `data/connectivity/`：每场景 `_source_inventory.json`、`_inventory_summary.json`、`_faces.json`（米制原 schema）、`_full_common.json`、`_native_lines.json`、`_relations.json`、`_rejected_relations.json`、`_boundaries.geojson`。GeoJSON 坐标为标准 WGS84，数值测量为 EPSG:32651。`museum_diagnostic.geojson` 的 `properties.geometry_role` 区分 `SOURCE_P`、`LEGAL_OMEGA`、`SOURCE_CONTEXT`、`INDEPENDENT_NATIVE_SOURCE_LINE`、`UNCHANGED_REGISTERED_DOOR`，线属性包含对应关系数组。

作者自检使用 9 个简单几何夹具核对线跨面、线端接边、面内线、共边、重叠、点触与非零间隙分类。另逐场景比较默认 None 与显式旧 ID 集合的序列化 face 输出，验证向后相同行为；证据位于 `source_inventory_geometry_selfcheck.json` 与 `source_inventory_default_api_regression.json`。独立审核由另一执行者另行记录，不将本作者检查算独立核验。

限制：没有独立面积真值或现场调查，不能报告边界准确率；这里尚未核验 portal 是否入图、父边分割、实际 route 使用和 APP 行为。整体实现与最终交付由父任务继续完成。
