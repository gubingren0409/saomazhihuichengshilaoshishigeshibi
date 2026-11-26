# FREE-SPACE-R1 审查入口

**PARTIAL_WITH_EVIDENCE**：主25任务及北门已运行，发现1个主域的原始私有停车面漏导，F0/F1错误允许128.388559 m²。实际两条新增路线未进入其内部，但区域权限门禁未通过；200次区域构建上限已到，不越界重建、不删除样本。地图 `#risk` 的审后红斜纹显示这个真实负结果。F1仅改代价，不能消除同一F0区域的权限缺口。

本轮比较 M1-C 正向证据、F0 排障默认可行、F1 相同区域加原生步道优先代价。全部为冻结地图上的条件规划诊断；事实未知与规划允许分开。

地图：打开 `visuals/index.html`。浏览器离线可读，也可在本目录运行：

```powershell
python -X utf8 -B scripts/serve_review.py
```

使用命令实际返回的127.0.0.1地址；停止本目录服务：

```powershell
python -X utf8 -B scripts/serve_review.py --stop
```

`RESULTS.md` 是结果说明；`runs/paired_metrics.csv` 与 `runs/query_outcomes.csv` 保留固定分母和逐查询结果。`data/regions` 为原始事实/规划假设双轴区域，F1引用F0同一几何；`data/routes` 保存逐段几何与代价。`audits/INDEPENDENT_REVIEW.md` 说明真实独立审核范围。

主25任务与自然北门分开，历史M1与M1-C分开。额外H80/40/160压力实验因包含失败修复的200次区域构建上限而不运行；原任务manifest保留，未运行不会消失。

固定包包含新源码、实际输入、输出、图件、审核，以及单份完整冻结依赖ZIP。展开的历史依赖不重复打包。外部审核者可运行：

```powershell
python -X utf8 -B scripts/replay.py --archive delivery/OPEN_REVIEW.zip --out runtime/clean_review_replay
```

该命令安全解包、核对清单和CRC、运行12个合成测试，实际重放4个受控代表任务、W7已知权限区域反例与自然北门，以及原来已有的有限代价分支。它不重跑整个主面板，计时和gzip文件头不声称逐字节复现。原工程、API密钥、网络请求均不需要；使用现有Python依赖 `shapely,networkx,pyproj,psutil`。浏览器复验另需 `playwright` 及本机Edge。

本轮不产生新入口，不改变原北门exit身份，不发新地图请求、不训练、不选择最终产品方案。等待GPT审核与用户自然语言验收。

来源补审的关键材料：`audits/common_constraint_gap_W7a6b5a10076.json`、`audits/access_scope_26.json`、`audits/access_area_prediction_impact.json`。原四个建筑/水体反例零误放不能覆盖新增查明的权限冲突。原数据已有该private标签，此项是导出遗漏，不是必须新增地图才能解决的缺标。

重放PASS只说明源码能复现原结果（包括已知负例），不代表这个权限缺口已经修好。程序从纯观测/北门纯分类区域缓存重放，旧模型和整个原工程不需要复制；完整原源还在单份冻结ZIP里。全源附加审计可在解包工程先执行 `python -X utf8 -B frozen_context/scripts/stage_frozen.py`，再运行：

```powershell
python -X utf8 -B scripts/audit_north_source.py --source frozen_context/frozen_r3/inputs/rev1/frozen_r4/data/source/sh-huangpu-01.osm.json --adapter frozen_context/frozen_r3/inputs/rev1/src/native_adapter.py --output runtime/source_reaudit.json
```

该命令使用包内已提供的权限角色登记及原源，不要求旧Windows绝对路径。审计输出应保留新路径，不覆盖原审查记录。
