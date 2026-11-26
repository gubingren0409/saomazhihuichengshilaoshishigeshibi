# 已登记面源几何与限制核验

角色：`/root/face_geometry`，源几何/约束作者，与主APP集成、可见图实现和独立审核为不同实际上下文。只处理本机六冻结源，未调用地图API、未求路线、未生成入口。

## 面集合与准入

`data/face_selection_lock.json`在任何FULL_FACE实际查询前按每scene冻结mapped_edges中的source_area_id去重锁定。ID只选择旧表示相同面集合，不构成通行放行；每个面仍从原生JSON重建，核对显式pedestrian area语义、权限、层级、完整outer/inner和取得覆盖。

主museum集合正好是relation/2153738与relation/2385771；library为way/1160136226。其余集合见lock。Source.area使用完整源member lines polygonize，并检查全部线段被拼合边界覆盖、inner被outer覆盖。原P、实际Ω、拼合洞数、members缺失及几何修复分别保存。

## 旧净空的实际定义

已直接读取旧R4-REV1的area_model.py：旧带是P与各外环buffer(3,quad16)相交，P外环不整体内缩；所有非BARRIER areal障碍与靠带的原生inner转面buffer(.25,quad16)扣除。源BARRIER本身不作.25膨胀，而是整段相交必须精确命中合法gate（.001m仅交点数值容差）。后来的APP共同限制另有.15m屏障mask和.30m原gate开口、权限面及道路零宽策略。

FULL_FACE对完整P的所有洞（包括远离旧外带者）与完整面范围内的同类源areal障碍扣.25；继续扣完整APP common blocked，而非只门心D30/160m。P外边不内缩，不用凸包、不任意简化。道路中心线以零宽分区并逐边复检，不把它当测得车道边界。每组件独立；不以点接触合并成有宽通道。

buffer quad16将圆角离散为64边，最大径向弦误差为.25*(1-cos(pi/64))≈.000301136m。因此最短路保证针对实际多边形化Ω，不能把贴弦最短路称作连续圆角或现场严格.25m安全保证。净空、数值EPS和gate交点容差三者分开。

## 权限和例外

当前APP按foot-specific优先于一般access，旧R4 area准入any access/foot不允许即拒绝有细小差异。新face准入统一APP；固定oldmapped集合防止悄悄增加新面。Source旧AREA若S1/common已判脚行公开覆盖普通access，则不再冒充物理障碍，记录legacy_foot_priority_override_differences；主南北面实际该列表为空，Ω与旧strict准入源审计完全一致。

真正原生步道、桥隧和精确沿私有面边界例外仍在既有native图上，不将例外扩成面积。新面边不享受native权限/层级例外。原注册门touch-building的旧terminal connector仍保留其有限、来源明确例外；不扩大门洞，不移动原门。

.25规则不是整个系统所有片段都具有的同一物理安全保证：门心D30旧local grid、原生通道与旧terminal规则分别继承，仅新增FULL_FACE边须处于本Ω及其完整逐边限制内。

## 已实跑源审计（无solver）

- 北P19271.107344m²，1part/12拼合洞/248顶点；Ω18387.797226m²，1part/13洞/1872顶点。3条fence无allowed gate，1道路仅单点接触Ω、交长度0；缺失hazard0。原12洞均保留，额外限制形成第13洞。
- 南P5880.020892m²，1part/2洞/50顶点；Ω5826.120745m²，1part/2洞/195顶点；无barrier/road。缺失hazard0。
- 图书馆P及Ω723.914083m²，1part/0洞/10顶点，无barrier/road。

所有主面members完整，make_valid未触发。源审计的full_common为不建密集native图的几何审计版本；不含native沿权限边界的例外列表，故其constraint hash不是正式APP native route hash。实际APP调用compile_faces必须传入自己的完整source common并记录真实hash；本源审计不冒称路线/完整图核验。

`face_edge_conflicts`对整段检查Ω及单正宽component、实际full_common、原zero barrier exact gate；prepared几何和空间索引仅缓存数学相同对象。所有导出geoJSON显式EPSG32651米。
