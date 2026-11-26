# 步行面衔接：实际计算与审查入口

本轮 OSM-GEOAPIFY-PED-AREA-CONNECTIVITY-R1 仅使用六份冻结OSM裁片，不调用Geoapify或外部API，不新增费用、采集、训练或入口。上轮穿行观察保持 PENDING_USER_OBSERVATION，截图原请求保持 SCREENSHOT_REQUEST_UNBOUND。

## 启动与停止

在本目录PowerShell中运行：

```powershell
python -X utf8 -B scripts/serve_app.py --port 53441
```

打开 [实际求路](http://127.0.0.1:53441/)、[真实结果总览](http://127.0.0.1:53441/review)、[源诊断](http://127.0.0.1:53441/diagnosis)。实际地址/PID保存在 runs/service.json，只监听127.0.0.1。APP须使用HTTP地址；index.html和图片可以离线阅读。

选择场景、登记门、合法原生起点、用途、F0/F1和衔接模式；点击计算会真实调用同一规划内核。对比按钮分别求旧B0和选定新模式，保留run_id，不换图冒充求解。地图可切街区与局部，检查原始P、合法Ω、补入源面、原生步道、障碍、精确接口和条件接缝；导出请求、视野、选中对象和路线供后续截图绑定。

北门node/6897145227仍为entrance=exit。接近门外与入馆用途分开；无适用登记门不生成新门。

```powershell
python -X utf8 -B scripts/serve_app.py --stop
```

停止命令只管理本工程记录的PID，不停止旧53421/53431服务。勿关闭全部Python进程。

## 运行与证据

```powershell
python -X utf8 -B scripts/plan.py --help
python -X utf8 -B scripts/plan.py --request data/example_request.json --connectivity-mode CONDITIONAL_SEAMS --output results/manual_cli_response.json
python -X utf8 -B -m unittest discover -s tests
python -X utf8 -B scripts/summarize_results.py
```

CLI和POST /api/plan共用src.planner.plan；POST /api/mechanism只接受锁定mechanism_id，如M04，不冒称入口任务。真实路线答案缓存关闭，预处理按源、代码、配置和图hash复用。

正式104请求事先冻结于data/formal_requests_lock.json，results/formal_registry.jsonl逐条关联run文件和SHA。演示不必重跑全量。scripts/run_formal.py --url http://127.0.0.1:53441 会跳过已记录请求。独立冷解包求路应使用新端口、新PID与无运行态目录，不能误接原服务。

example_request.json直接取固定APP-01的原始起点与南门，不是新选择的容易样本。命令会产生一次新的实际求路，不读取旧路线答案。F0/F1只改变假设段倍率。首次构图可耗时数分钟，同一场景/门的预处理命中后会快得多；演示原型尚未达到即时导航性能。

METHOD.md说明方法与边界，RESULTS.md给出真实正负结果。data/connectivity为源盘点、P/Ω、关系和查询锁；results/segment_evidence.csv为实际逐段来源；audits/independent_review.md说明独立审核范围；audits/development_run_registry.json保留小试、中断和修复。

新增面是从原裁片补读的显式步行面，不是新采集，不是放开公园/草地。条件接缝宽度未知，仅为逻辑连接假设。计算连通、路线缩短不证明公众现实可走、门当前可用或完整导航完成。没有独立面积真值，不报告边界准确率或伪IoU。

基线OPEN_REVIEW_R1_FINAL_FIXED.zip SHA256：c5472838de6320d983d80e4defd448e08c017777f23bc7aa083d38e7ce10b08a。新包提供必要运行源码、六裁片和新增证据，不复制整个历史工程；历史结论依赖按SHA引用原包。保留OSM署名和NOTICE.md；包不含凭据、Cookie或浏览器痕迹。

## 固定包与包外回执

ZIP内的STATUS和报告是封包时的固定字节快照，因此会保留“最终ZIP解包求路待回执”的时序状态。最终独立解包、测试、新起点实际求路与临时服务停止结果写在ZIP旁的独立JSON回执，绑定最后ZIP的SHA256；没有通过修改包内状态制造自引用哈希。只有该回执对应实际交付ZIP并通过，才在包外交付状态中标记READY_FOR_GPT_AND_USER_REVIEW。它仍不代表用户观察或现场通行已验收。

归档包含逐次原始响应、源几何与独立证据；解包约1.4GB，以内容清单的实际大小为准。重新求路还会新增派生文件，建议在有数GB余量的目录解包。运行核心依赖见requirements.txt；重绘图和浏览器复核的可选版本见requirements-visuals.txt。已有PNG/SVG/PDF可直接阅读，无需重绘或下载新浏览器。
