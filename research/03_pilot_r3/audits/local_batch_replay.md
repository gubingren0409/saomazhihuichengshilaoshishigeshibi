# 本地 OSM 分支复现说明

本轮新增地点的范围由原始 PBF 的已命名建筑原生 ID 确认。候选清单在路线执行前记录于 runs/local_candidate_identity.json。最终共用请求保存在 runs/scene_contracts.json。

- 源为 R1 已冻结的 Geofabrik Shanghai PBF，版本 2026-11-08T21:21:00Z。只读复用该文件，本地分支未新增下载。各场景裁片包含原生 ID、几何和标签，许可证 ODbL 1.0。地图保留 © OpenStreetMap contributors。
- src/frozen_r1 中的裁片、视野、渲染和路由实现逐字节复制自 R1。程序在计算前检查路由器及渲染器 SHA。沿用 OSM_PEDESTRIAN_CONSERVATIVE_V1、起终点 35 米门槛、EPSG:3857 投影、1200×900、近景 18／上下文 16。未加入新开放空间、跨边、人行道或入口连接逻辑。
- 同一栋建筑的两张图是两个视野。靠西外轮廓的接近代理点只提供固定请求坐标，不声明真实入口。OSM 标签也不提供现场可达性保证。馆舍面积关系和整片场地边界分别记录。
- 本地路线状态仅反映原算法、快照和阈值下的结果。到最近步网候选的诊断线保留独立身份，末端缺口不补线。源数据未标、未纳入图、未通行等结论分开记录。

## 离线再算

在解包后的工作目录运行下列命令即可从保留裁片和冻结场景再算，不需要 PBF 文件或网络：

```powershell
python -X utf8 -B -m src.local_batch run --output runtime/local_replay
```

路线、GeoJSON 与图片输出到指定新目录。已有结果时程序拒绝覆盖。只有需要重新裁片时才需 pyosmium 4.3.2 和 SHA 匹配的上游 PBF。用于验证选样的合成测试单独存放在 tests/test_local_batch.py，不计作实际样本。

[OSM 版权和许可](https://www.openstreetmap.org/copyright) · [Geofabrik Shanghai](https://download.geofabrik.de/asia/china/shanghai.html)

## 新世界城局部断连

运行 `python -X utf8 -B -m src.local_topology_check` 可复核 audits/local_newworld_topology.json。起点与目标代理点分别落在原生 way/1047377660 和 way/85796883 的接入候选上，目标候选距请求点 8.45 米。冻结图中两处归属不同弱连通分量，节点数分别为 4,741 和 34，忽略方向后仍无法互达。该诊断适用于本轮裁片和路由配置，不能据此判断现场是否有通道或锁定具体缺边原因。
