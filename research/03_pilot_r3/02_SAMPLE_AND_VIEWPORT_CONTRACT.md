# 冻结样本与视野合同

本轮在同一上海日期版 OSM 数据下先冻结对象、入口参考、起点和视野，再运行各自路线。所有冻结项留在分母。上海博物馆单列为历史回放，原来两个视野、原评分与请求沿用。

| 新样本 | 类别及口径 | OSM 对象 | 请求参考等级 | 近景 / 上下文 |
| --- | --- | --- | --- | --- |
| 武康大楼 | STREET_FRONT_RESIDENTIAL_MIXED · 沿街住宅/混合类型；单门属性未独立核验 | way/293434151 | PROXY_OR_UNCERTAIN | 18/ 16 |
| 上海中心大厦 | OFFICE_MIXED_HIGHRISE · 办公主导的混合用途高层；原生 building=commercial | way/165792123 | PROXY_OR_UNCERTAIN | 18/ 16 |
| 新世界城 | STREET_FRONT_RETAIL · 沿街商业；原生 building=retail、shop=mall；实体多入口状态未核验 | way/51317339 | PROXY_OR_UNCERTAIN | 18/ 16 |
| 上海图书馆淮海路馆 | PUBLIC_LIBRARY · 公共服务；目标为淮海中路1555号原生馆舍轮廓 | way/293434188 | OSM_TAGGED | 18/ 16 |
| 上海展览中心 | OPEN_SPACE_EXHIBITION_COMPLEX · 退线场馆复合体；采用含内环的馆舍建筑关系，区别于外部场地 way/438483942 | relation/7469147 | PROXY_OR_UNCERTAIN | 18/ 16 |

两档 1200×900、正北、无倾斜。尺度从 WGS84/投影范围和实际像素核验。入口来源分为 OSM 标签、代理和未知。本轮没有现场验证入口。某个 OSM 标记存在，只说明地图中有这个对象。

冻结合同 SHA256 `7e81ea652bc94f0a65e161666fda6f2bc2db7447227a2ca6fbbd09213ce8dbcd`。 [锁定合同](runs/scene_contracts.json) · [预登记判定规则](runs/decision_protocol.json)
