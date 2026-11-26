# OSM基底确认后的完整研究阶段与原实现

1. 01–03：OSM/Geoapify对照、路线诊断和六场景输入。
2. 04–06：原生衔接、3米面边缘派生、北出口条件接入。
3. 07–10：草地步道修复、区域恢复、上下文、F0/F1。
4. 11–14：已知门APP、完整面最短路、面线接口和业务收益诊断。
5. 15–19：PG1审计、街区侧拓扑、场景身份纠错、动态与性能补证。
6. 20–22：研究交接/中期材料及R3纠错。

每轮独立目录保留原代码、配置、测试、结果和图件，导入commit见[ARTIFACTS.csv](ARTIFACTS.csv)。[SOURCE_FILES.csv](SOURCE_FILES.csv)绑定原文件SHA和固定包SHA；[EXCLUSIONS.csv](EXCLUSIONS.csv)披露未公开的依赖、重复包、运行缓存及许可例外。

这些是补录历史快照，不是新实验。原代码中保留历史路径和外部数据依赖，不承诺所有阶段脱离原输入即可运行。地图条件可达不是公众通行认证；exit仅到门外；跨域指标不拼成端到端成功率。动态适配器不是原APP已部署功能。R3是较新的材料纠错口径。

## 许可与来源

地图© OpenStreetMap contributors：https://www.openstreetmap.org/copyright ，OSM数据库沿用ODbL：https://opendatacommons.org/licenses/odbl/1-0/ 。保留原归属/NOTICE/第三方许可，不给研究源码代选新许可证。Geoapify托管图像/响应及私有截图、用户评分的公开再分发许可未确认，因此列例外而不上传。没有新增采集、API、训练、求路或费用。

北门7.95米前导小试05a单列，源为正式NORTH-R1包内的原实现；与正式R1不混作同一次实验。缺失的WALKABILITY-R1没有重建或编造。代码/页面统计包含历史重复版本，不能解释为独立算法数。

Geoapify适配器源代码属于研究实现，已包含在03/src/hosted_support及hosted_batch.py；未公开的是实际托管导出/响应，不是调用服务的算法代码。ARTIFACTS的completion_commit记录这项补全，不伪改最初导入提交。
