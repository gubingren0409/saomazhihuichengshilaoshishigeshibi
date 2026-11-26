# 地图制作与核验记录

制图角色：`/root/free_visuals`，不同于主算法、共同约束、独立评价角色。以下是制图作者检查与单独实现的载荷几何核对，不冒称对自己网页制作的完全独立审核，也不替代其他角色的源数据/路由/评价检查。

## 最终实物

`visuals/index.html`：26个真实案例、78份主方法载荷，7,249,610 bytes。

SHA256：`8663acdc78fdb24dff1a7db2dc65707a72e8e8f7fee060e041b9407bb635ff9e`。

三个入口：北门街区／局部与全程、三方法同图对照、共同限制与扩张。参考默认关闭；用户开启参考不改变算法输入。F0/F1同一表面载荷共享存储，原生事实与条件规划状态点击可查。

六个代表视图各有PNG/SVG：

1. `01-north-full-route`：原起点到原出口，完整路线与固定局部。
2. `02-north-three-methods`：三法北门局部；几何米数、假设米数、广义代价分别显示。
3. `03-library-expansion`：默认域明显扩张；原合同0路线查询，只进行区域评价。
4. `04-new-reachability`：`W2b809bbe6b8` 的实际新增可达Q1。该路线仍由条件假设支持。
5. `05-still-no-path`：`W0caca58bc41` 的Q1，三法仍NO_PATH，扩大允许面积未自动解决连接。
6. `06-water-and-policy`：原生路线与共同限制，避障绕行不自动计错误放行。

另有 `user-export-north.png`，用于核验用户点击PNG导出能力，是第一视图的导出样例，不是第七个研究案例。被替换的早期示例图在本轮runtime下保留，不进入最终图册。

## 实际检查

- `visual_browser_check.json`：Edge 147.0.3912.72，实际 file:// 和 localhost 三入口，方法切换视野固定、三图相同输入、F0/F1表面身份、双轴格片、参考选择、图层、联动点击和缩放、原出口坐标/exit身份、全程、SVG和PNG导出均PASS。浏览器只允许文件、本地blob/data和当前回环服务，外部请求与页面错误均为0。
- `visual_geometry_check.json`：独立脚本没有导入制图函数，逐个逆变换页面格片和路线坐标。26案例78载荷共1,257,596顶点，最大取整误差0.00069494891m，不超过0.000708m；事实/规划字段、区域和无权图指纹核对PASS。权威数据仍为原metric GeoJSON，不以SVG取整结果代替评价数据。
- `visual_live_service.json`：持久回环入口实际GET返回200，HTML响应SHA与本地最终文件相同。服务只读，临时进程/服务令牌记录在runtime，不交付。
- 实际目视检查：北门全程、北门三法、真实新增可达、仍失败视图。地图保留植被、水体、道路、建筑、来源时间、比例尺和原生ID。未手工补线、移门或平滑路线。
- 首次最终浏览器循环发现测试脚本同URL导航不会重置参考开关的预期错误；修复和全量重跑见 `visual_harness_repair.md`，没有降低默认关闭要求或修改算法。

## 复现与限制

`python -X utf8 -B src/build_free_visuals.py` 构建页面；`python -X utf8 -B scripts/check_free_payload.py` 重算页面几何；`python -X utf8 -B scripts/check_free_visuals.py` 执行实际Edge验证并从页面导图。`python -X utf8 -B scripts/serve_review.py` 启动自动空闲端口服务，加 `--stop` 只停止本目录登记服务。

最终ZIP的成员/CRC/安全解包及代表任务再运行由父任务与独立角色另记，此视觉记录本身不宣称已完成最终ZIP复验。真实预测文件的SHA溯源在 `visual_build.json`，未把含elapsed的文件SHA嵌入纯结果页面，从而不以运行时变化造成无意义页面字节差异。若实际重放不逐字节一致，仍须分别报告字节与数值容差结果。

灰色阅读背景不是预测可见层。自然全程1000m背景只含闭合原生way和highway线，未重建所有relation，不是完整障碍审计。页面检查不证明当前公众可进入、真实同层、未标障碍不存在或条件路线现实可走。北门始终是原登记 `entrance=exit`，未生成任何新入口。
