# 上海博物馆人民广场馆：目标绑定重建R2

打开本机 `http://127.0.0.1:53531/`，或直接离线打开[web/index.html](web/index.html)。默认视野是实际上海博物馆建筑及两扇登记门；不再用附近人行道中点定窗。

目标为原始OSM `way/161090899`，不是上海市历史博物馆、上海大剧院或旧锚点`way/39764359`。南门`node/6897141353 entrance=main`，北侧`node/6897145227 entrance=exit`；原坐标未动，exit只作门外目标。

可切换完整街区、目标概览、黄陂北路、南门、北出口五个视野。四面板使用同一底图和范围；原始对象、目标高亮及冻结R0/R1/R2分别显示。图层和审计信息可展开，点击对象查看原生ID、tags、版本、来源与算法引用身份，可导出当前视野JSON和SVG。

**旧算法叠加仍是西北侧步道诊断，不是博物馆到门路线。** 旧查询没有绑定两扇门，不因换上正确街区底图而变成已知门请求。当前门前没有旧诊断边时显示OUTSIDE_VIEW，不补线。历史24次尝试、22次实际求解和所有输入结果不变。

## 运行与停止

在本目录前台运行：

```powershell
python -X utf8 -B src/serve_review.py --port 53531
```

按Ctrl+C停止。本次实际隐藏服务PID122288，仅停止它可执行 `Stop-Process -Id 122288`。旧53511、53521服务未停止、重启或改数据。

从包内完整冻结OSM重新构建数据、图件和页面：

```powershell
python -X utf8 -B src/build_target_scene.py --from-packaged
python -X utf8 -B src/render_maps.py
python -X utf8 -B src/build_target_scene.py --finalize-inventory
python -X utf8 -B src/build_web.py
```

这里只解析和绘图，不运行求路、构建新的路由图或调用地图API。不要运行任何旧算法或路线实验。包内保留完整同字节6.36MB上海冻结OSM、必要旧记录与原生lineage，支持本轮地图重建；其他历史全工程仅按SHA引用。字体与图形依赖使用本机已安装版本，没有打包字体，也不宣称跨系统二进制图像必然相同。

## 先看哪些证据

- [正式纠错说明](TARGET_SCENE_CORRECTION.md)
- [目标身份审计](audit/TARGET_IDENTITY_AUDIT.md)
- [目标及原门对象](audit/target_objects.json)
- [黄陂北路七条道路证据](audit/huangpi_north_road_objects.json)
- [定窗规则](audit/window_definition.json)
- [现实参照验证边界](audit/REAL_SCENE_VALIDATION.md)
- [对象到图件清单](audit/source_to_render_inventory.csv)
- [独立审核](audits/INDEPENDENT_REVIEW.md)

本轮新增算法/求路/地图下载/API/费用/Push均0，R0默认不变。冻结源中的目标身份和窗口覆盖可以核验；目前缺少可用的独立实景配准参考，保留`REAL_WORLD_GEOMETRY_UNVERIFIED`。图面技术检查不等于现场通行、用户验收或Parent Goal完成。

© OpenStreetMap contributors，沿用已保存ODbL来源记录；不伪造源中没有的道路面、路宽、路缘或人行道位置。本包仅供本地私有审查，未选择新源码许可证、未扩展原38项公开候选，也未获公开上传批准。
