# 运行入口与复现范围

直接打开根目录 `index.html` 即可离线阅读真实源地图、切换本轮已计算结果和查看报告。页面明确是结果回放，不是即时求路服务。

## 一次新的真实求路

在本补充包解压目录打开 PowerShell，用已有 Python 3.12 环境执行：

```powershell
python -X utf8 -B scripts/replay_request.py --case library --method F1 --mode FULL_FACE
python -X utf8 -B scripts/replay_request.py --case south --method F1 --mode FULL_FACE
python -X utf8 -B scripts/replay_request.py --case north --method F0 --mode FULL_FACE
python -X utf8 -B scripts/replay_request.py --case library --method F1 --mode FULL_FACE --medium
```

每次生成新的 `replay_runs/REPLAY-<uuid>/result.json`，实际调用冻结求解器，禁用路线答案缓存。不改原门坐标，北侧 exit 仅到门外；不修改主结果表。会在包内运行时副本写入新的预处理收据/派生图，属于可重新计算的缓存，不写历史工程。

依赖版本见各实验 `environment.json`。没有依赖安装、下载或API调用藏在运行脚本内；缺库时按明确错误停止，不自动改全局环境。首次完整构图可能需要几十秒或更长，不能用热求路数字估计冷启动。

## 全部实验重现

先创建**不含旧结果行的新复现目录**，再进入该目录运行驱动；不要直接在已封存交付目录重跑全量驱动，也不要将旧raw结果与新结果追加混合。

```powershell
python -X utf8 -B scripts/new_run_namespace.py --destination "E:\智慧城市和位置服务\_task_runtime\SUPPLEMENTARY_REPLAY_NEW"
Set-Location "E:\智慧城市和位置服务\_task_runtime\SUPPLEMENTARY_REPLAY_NEW"
```

目标若已存在会拒绝，不删除或覆盖。全量历史审计和旧窗口比较仍依赖同级原固定工程，换机器时须补齐明确依赖。新求路入口本身不需要这些旧ZIP。

```powershell
python -X utf8 -B scripts/run_entries_and_closures_v2.py
python -X utf8 -B scripts/finish_entry_audit.py
python -X utf8 -B scripts/complete_entry_context.py
python -X utf8 -B scripts/recheck_entry_identity.py
python -X utf8 -B scripts/record_field_blocker.py
python -X utf8 -B scripts/audit_sources.py
python -X utf8 -B scripts/recheck_grass_policy.py
python -X utf8 -B scripts/run_benchmark.py
python -X utf8 -B scripts/run_supplementary_benchmarks.py
python -X utf8 -B scripts/run_replan_benchmark.py
python -X utf8 -B scripts/run_joint_benchmark.py
python -X utf8 -B scripts/build_figures.py
python -X utf8 -B scripts/assemble_results.py
python -X utf8 -B scripts/plot_performance.py
python -X utf8 -B scripts/assemble_results.py
python -X utf8 -B scripts/check_browser.py
```

中规模派生输入和源码已随包保留；`prepare_medium.py` 是其生成过程。如重新生成，来源内容不变，但生成时间写入派生来源记录，会改变该派生JSON的字节哈希，应作为新运行记录，不能覆盖本轮来源版本。

Q6保存结果全量审计使用6个旧固定审查ZIP及旧档案索引，**未重复装入本包**。其SHA/成员/实际历史路径见 Q6 `provenance.csv` 与脚本 `audit_sources.py`。只在历史依赖齐备时运行：

```powershell
python -X utf8 -B scripts/audit_sources.py
python -X utf8 -B scripts/recheck_grass_policy.py
```

本包可离线查看全部图表，并重算所含源输入上的已登记门请求；**不是6个历史阶段全部独立自包含复现包**。Q6B现场实验需要独立人员提供真实资料，脚本不能替代实走。当前公开APP没有动态封闭或Top-3接口，本轮新适配器不自动装入旧服务。

`recheck_aggregated_schema.py` 保留了本轮审计器纠错过程；当前 `audit_sources.py` 已包含该修复，新复现不需要重复套用历史纠错脚本。`assemble_results.py` 的研究叙述针对本轮固定实验，重用时须区分继承的原轮工程历史与新的实际运行；原始表和计时不能被叙述模板替代。

本轮没有启动需要常驻的服务；不需要停止旧项目的任何服务或进程。耗时驱动可在本终端用 Ctrl+C 中止；未完成记录不能当完整基准。

原 `run_entries_and_closures.py` 保留为首版执行源码；它的博物馆删边对象包含道路轴。正式复现使用 `_v2.py` 的原生步道标签筛选，不能把历史驱动当当前修正版。
