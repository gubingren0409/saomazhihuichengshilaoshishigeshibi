# 标签角色核对：不是新地图采集

2026-11-11查阅OSM Wiki两份原始标签说明，3次web工具调用、6次页面操作（2次open、2次find、2次定位open），2个唯一页面；底层实际HTTP次数不可见，不编造。地图/API请求仍为0，没有取得新地理场景或修改旧地图。

1. [Tag:amenity=parking](https://wiki.openstreetmap.org/wiki/Tag:amenity=parking)，OpenStreetMap Wiki，How to map：停车设施通常作为面绘制；停车范围不清时可用点。支持结合原闭合停车环识别其面角色，不支持把停车区直接设为可通行。
2. [Key:area](https://wiki.openstreetmap.org/wiki/Key:area)，OpenStreetMap Wiki，area定义与Summary：闭合way的面/线角色需要结合其他标签；area=yes并不是所有面的必要字段，barrier或highway闭环通常仍需区分线角色。支持修正“缺area=yes就把私有停车闭环当墙”的解释，不支持把所有闭合道路都填成面。

本例原始节点、共边、面内穿越长度由两独立上下文在本机冻结OSM重算，事实依据不是Wiki，也不是聊天摘要。`access=private`保留；仅原生foot=yes步道在已核共享边界上的精确线允许按原网络使用，停车内部继续限制。未推断当前公众资格、现场同层、门的真实身份或地图更新时间。
