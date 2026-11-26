# 地图传输与回放合同

本页不调用求解器。`source_context.json`中的四案例×四模式×F0/F1共32条路线，是按原响应SHA核验的R1历史几何；本轮替代路线在`results/map_ui.json`的`cases[].alternatives`中，单独绘制。历史F0/F1路线本来可以不同，“四模式不变”指同一方法的B0到B3比较。

`results/map_ui.json`为人读诊断数据；`interface_definitions`保留接口公共字段，`shared_evidence_values`共享相同的来源/模式证据。定义中仅形如`{"__ui_pool_ref__":整数}`的值引用共享池。每case的`interface_metrics`按`interface_metric_fields`顺序保存动态字段，首项是定义池下标，末项是字段存在性位掩码，区分缺失字段与null。重建时补`case`。构建器对全部92096条接口×方法证据记录逐行复原并与原字段相等，不按接口ID去重或覆盖。

浏览器的`ui_record_key=case/method/array-index`只用于选中、导出和区分同ID的不同节点绑定，不冒充OSM原生ID。`graph_node_ids`、所属面、原接受状态和逐模式证据仍完整保留。当前B3采用读该证据记录；其他模式同ID出现而未逐条核定节点绑定时保留UNKNOWN。起点可达是有向正向关系，能到门是反向关系，WCC标签另外保留，不能相互替代。

每个case附`counterfactuals`为既有删除证书摘要，完整witness仍在`results/counterfactual_certificates.json`。摘要带原文件SHA、上下界、删除/保留选项数和见证数量，不是新增实验。新面总览区分82个全局新身份与124条场景记录；其他场景未加载进业务图不等于现实不连通。

HTML内嵌所有页面数据的gzip，不请求外部地图、字体或脚本。`map_payload_manifest.json`记录压缩/未压缩SHA。直接离线打开`visuals/index.html`，或在解包根目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py --port 53451
```

浏览`http://127.0.0.1:53451/`，前台服务按Ctrl+C停止。它只有GET静态诊断页与健康检查，不能提交新的求路请求。

源图上下文、历史路线与原始来源哈希已随包保存；重新从固定R1 ZIP生成源显示层仍依赖外部基线文件，不能因此宣称整个历史工程离线自包含。使用包内已有显示数据重新生成页面可运行：

```powershell
python -X utf8 -B src/build_maps.py --render-only --strict
```

`--figures`可重绘四张标准matplotlib科学图。实际作者浏览器检查与独立检查分别记录，不等同于用户自然语言验收或现场通行验证。
