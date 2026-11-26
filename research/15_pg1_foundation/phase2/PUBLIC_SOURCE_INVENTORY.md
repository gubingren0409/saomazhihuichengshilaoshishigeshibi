# Phase2 自有通用源码提议清单

未公开push；最终文件清单/commit由父任务审查。以下自有源码不含真实候选坐标、用户home、key或数据，输入从CLI提供：

|文件|用途|依赖版权|
|---|---|---|
|src/build_atlas.py|离线GeoJSON字段/几何/真实SVG图册|调用Shapely，不内嵌第三方源码或数据|
|src/spatial_groups.py|原生ID/几何包围范围/保守同城组pair审查|调用Shapely；不执行冻结|
|src/summarize_audit.py|本地source证据hash和实际请求核算|Python标准库|
|src/verify_atlas.py|离线file URI浏览器截图/图层toggle工程核验|调用Playwright、本机Edge，不分发二进制|
|src/fetch_bounded.py|通用有界公开请求、预算与证据日志|Python标准库；默认**不运行**，公开代码不授权继续取数|

**不纳入首次公开：** src/prepare_samples.py（本地带真实窗口的取数准备器）、所有JSON清单/scene_config、request_log、samples、evidence、地图/截图、候选对象/坐标/CSV详细表。通用代码虽可公开，仍需父任务secrets/license/privacy scan与用户精确清单首次push批准。

源码为本轮新写，无复制第三方实现；依赖许可证由其分发包保留。map数据/官方网页不因用自有代码读取或生成SVG而变成自有无条件版权。OSM数据ODbL、Helsinki CC BY4.0、NYC条款分别独立记录；不把数据再许可为代码许可证。
